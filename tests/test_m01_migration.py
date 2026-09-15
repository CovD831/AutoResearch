"""K6 (``StateMigration``) tests: explicit unknown-field policy + replayability."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from autoresearch.contracts import ResearchState
from autoresearch.migration import (
    FieldCollisionError,
    MigrationChain,
    StateMigration,
    UnknownFieldError,
    UnknownFieldPolicy,
    state_version,
    version_key,
)


def _migration(**overrides) -> StateMigration:
    payload = {
        "from_version": "v1",
        "to_version": "v2",
        "unknown_field_policy": "reject",
    }
    payload.update(overrides)
    return StateMigration(**payload)


# --------------------------------------------------------------------------- #
# K6-1: the unknown-field policy must be explicit (no default, no silent drop)
# --------------------------------------------------------------------------- #


def test_unknown_field_policy_must_be_stated() -> None:
    with pytest.raises(ValidationError):
        StateMigration(from_version="v1", to_version="v2")
    with pytest.raises(ValidationError):
        StateMigration(from_version="v1", to_version="v2", unknown_field_policy="drop")
    assert (
        _migration().unknown_field_policy == UnknownFieldPolicy.REJECT
    )  # a stated policy is accepted


def test_reject_policy_raises_on_an_unknown_field() -> None:
    """N-2: unknown field + reject -> a loud error carrying the field names."""

    migration = _migration(field_mapping={"title": "name"}, unknown_field_policy="reject")
    with pytest.raises(UnknownFieldError) as excinfo:
        migration.apply({"title": "t", "legacy_note": "must not vanish silently"})
    assert excinfo.value.fields == ["legacy_note"]
    assert isinstance(excinfo.value, ValueError)


def test_preserve_policy_keeps_the_unknown_field() -> None:
    """N-3: unknown field + preserve -> the field is *present*, not merely no-crash."""

    migration = _migration(field_mapping={"title": "name"}, unknown_field_policy="preserve")
    result = migration.apply({"title": "t", "legacy_note": "carried over"})
    assert result == {"name": "t", "legacy_note": "carried over"}
    assert "legacy_note" in result


def test_field_mapping_renames_and_defaults_fill_missing_fields() -> None:
    migration = _migration(
        field_mapping={"title": "name", "abstract": "summary"},
        defaults={"schema": "ResearchState/v2"},
    )
    assert migration.apply({"title": "t", "abstract": "a"}) == {
        "name": "t",
        "summary": "a",
        "schema": "ResearchState/v2",
    }


def test_existing_target_fields_are_not_overwritten_by_defaults() -> None:
    migration = _migration(defaults={"schema": "ResearchState/v2"})
    assert migration.apply({"schema": "pinned"})["schema"] == "pinned"


# --------------------------------------------------------------------------- #
# K6-2: replayable (same input, same output)
# --------------------------------------------------------------------------- #


def test_migration_is_replayable() -> None:
    migration = _migration(
        field_mapping={"title": "name"},
        unknown_field_policy="preserve",
        defaults={"version": 2},
    )
    payload = {"abstract": "a", "title": "t", "notes": ["n"]}
    first = migration.apply(payload)
    second = migration.apply(payload)
    assert first == second
    assert list(first) == list(second)
    assert first == {"name": "t", "abstract": "a", "notes": ["n"], "version": 2}
    assert payload == {"abstract": "a", "title": "t", "notes": ["n"]}  # input untouched


# --------------------------------------------------------------------------- #
# K6-3: to_version strictly increases (numeric, not lexical)
# --------------------------------------------------------------------------- #


def test_to_version_must_strictly_increase() -> None:
    with pytest.raises(ValidationError, match="strictly greater"):
        _migration(from_version="v2", to_version="v1")
    with pytest.raises(ValidationError, match="strictly greater"):
        _migration(from_version="v1", to_version="v1")
    assert _migration(from_version="v1", to_version="v10").to_version == "v10"


def test_unparseable_version_is_rejected_instead_of_ranked_as_zero() -> None:
    with pytest.raises(ValueError, match="no numeric component"):
        version_key("draft")
    with pytest.raises(ValidationError):
        _migration(from_version="draft", to_version="v2")


def test_version_key_orders_numerically() -> None:
    assert version_key("v2") < version_key("v10")
    assert version_key("1.2") < version_key("1.10")


# --------------------------------------------------------------------------- #
# ResearchState bridge: K6 versions are str, ResearchState.schema_version is int
# --------------------------------------------------------------------------- #


def test_research_state_version_bridges_to_a_k6_label() -> None:
    state = ResearchState(project_id="p1", idea="i")
    assert state.schema_version == 1
    assert state_version(state) == "v1"
    assert version_key(state_version(state)) < version_key("v2")


def test_bridge_rejects_objects_without_an_integer_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        state_version(object())
    with pytest.raises(ValueError, match="schema_version"):
        state_version(SimpleNamespace(schema_version="1"))
    with pytest.raises(ValueError, match="schema_version"):
        state_version(SimpleNamespace(schema_version=True))


def test_migrating_a_research_state_dump_preserves_fields_but_not_the_version() -> None:
    """End-to-end on the real type, including what K6 **cannot** express.

    ``schema_version`` is an existing field whose *value* must change, and K6
    offers only rename + new-field defaults — no value transform. So the dump
    migrates field-wise while the version label stays behind; bumping it is the
    caller's job (registered as D-L01-09, a contract gap, not papered over here).
    """

    state = ResearchState(project_id="p1", idea="idea", schema_version=1)
    migration = StateMigration(
        from_version=state_version(state),
        to_version="v2",
        unknown_field_policy="preserve",
        defaults={"new_in_v2": True},
    )
    payload = state.model_dump()
    result = migration.apply(payload)
    assert result["project_id"] == "p1"
    assert result["idea"] == "idea"
    assert result["new_in_v2"] is True
    assert len(result) == len(payload) + 1
    assert result["schema_version"] == 1  # K6 cannot bump an existing value


# --------------------------------------------------------------------------- #
# Ambiguity that would silently lose a value must be rejected up front
# --------------------------------------------------------------------------- #


def test_field_mapping_collision_is_rejected() -> None:
    with pytest.raises(ValidationError, match="several source fields"):
        _migration(field_mapping={"a": "x", "b": "x"})


def test_defaults_shadowed_by_mapping_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unreachable"):
        _migration(field_mapping={"a": "x"}, defaults={"x": 1})


def test_payload_carrying_both_old_and_new_field_is_rejected() -> None:
    migration = _migration(field_mapping={"title": "name"}, unknown_field_policy="preserve")
    with pytest.raises(FieldCollisionError):
        migration.apply({"title": "old", "name": "new"})


def test_apply_rejects_a_non_mapping_payload() -> None:
    with pytest.raises(TypeError, match="must be a mapping"):
        _migration().apply(["not", "a", "mapping"])


# --------------------------------------------------------------------------- #
# MigrationChain (extension): contiguity + end-to-end replay
# --------------------------------------------------------------------------- #


def _v1_to_v2() -> StateMigration:
    return _migration(
        field_mapping={"title": "name"}, unknown_field_policy="preserve"
    )


def _v2_to_v3() -> StateMigration:
    return _migration(
        from_version="v2",
        to_version="v3",
        field_mapping={"summary": "abstract"},
        unknown_field_policy="preserve",
        defaults={"schema": "ResearchState/v3"},
    )


def test_chain_requires_contiguous_versions() -> None:
    with pytest.raises(ValidationError, match="not contiguous"):
        MigrationChain(
            migrations=[
                _v1_to_v2(),
                _migration(
                    from_version="v3", to_version="v4", unknown_field_policy="preserve"
                ),
            ]
        )


def test_chain_migrates_a_v1_payload_to_v3_and_replays() -> None:
    chain = MigrationChain(migrations=[_v1_to_v2(), _v2_to_v3()])
    payload = {"title": "t", "summary": "s", "note": "n"}
    first = chain.migrate(payload)
    assert first == {
        "name": "t",
        "abstract": "s",
        "note": "n",
        "schema": "ResearchState/v3",
    }
    assert first == chain.migrate(payload)
    assert chain.from_version == "v1"
    assert chain.to_version == "v3"


def test_chain_stops_at_the_requested_target_version() -> None:
    chain = MigrationChain(migrations=[_v1_to_v2(), _v2_to_v3()])
    assert chain.migrate({"title": "t", "summary": "s"}, to_version="v2") == {
        "name": "t",
        "summary": "s",
    }


def test_empty_chain_returns_a_copy() -> None:
    chain = MigrationChain()
    payload = {"a": 1}
    result = chain.migrate(payload)
    assert result == payload
    assert result is not payload
    assert chain.from_version is None
    assert chain.to_version is None

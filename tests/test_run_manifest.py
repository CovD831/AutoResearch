"""K1 ``RunManifest`` tests (M08-01, contract-first package).

The project hard rule ("discriminating power", ``docs/process/DISCRIMINATING-POWER.md``)
is applied here: every K1 invariant is tested with a **violating** input and
asserted to be *rejected*, never merely that a legal input passes.

Coverage map
------------
* N-1 / K1-1  ``command`` as a shell string is rejected -- and not split
* N-2 / K1-2  ``seeds=[]`` is rejected; ``seeds=[0]`` (explicit, deterministic) passes
* N-3 / K1-3  ``exit_code=None`` (not executed) and ``exit_code=0`` (executed, ok)
              stay semantically distinct -- ``None`` is never coerced to ``0``
* N-4 / K1-3  ``exit_code=1`` (executed, failed) passes and is **not** read as
              "never ran"

**K1-4 intentionally has no behavioural test.**  ``output_hashes`` authenticity is
an architectural intent that no schema can check; a "passing" assertion for it
would be vacuously true and would fake coverage.  The only test here asserts the
*absence* of a validator for that field.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

import autoresearch.run_manifest as run_manifest_module
from autoresearch.contracts import ArtifactRef, WorkPackage, utc_now
from autoresearch.run_manifest import RunManifest

# The 13 fields frozen in R-007 L2 §K1, verbatim and in contract order.
K1_FIELDS: tuple[str, ...] = (
    "run_id",
    "project_id",
    "work_package_id",
    "code_revision",
    "data_refs",
    "environment",
    "parameters",
    "seeds",
    "command",
    "exit_code",
    "output_hashes",
    "rerun_of",
    "created_at",
)


def _fields(**overrides: Any) -> dict[str, Any]:
    """Valid field values, minus the two work-package identifiers."""
    values: dict[str, Any] = {
        "code_revision": "8dd8780",
        "data_refs": ["dataset:alpha"],
        "environment": {"python": "3.13.12", "lock": "sha256:deadbeef"},
        "parameters": {"lr": 0.1, "epochs": 3},
        "seeds": [0],
        "command": ["python", "train.py", "--epochs", "3"],
        "output_hashes": {"metrics.json": "sha256:abc123"},
    }
    values.update(overrides)
    return values


def _kwargs(**overrides: Any) -> dict[str, Any]:
    """A fully populated manifest's constructor arguments."""
    return {"project_id": "demo", "work_package_id": "wp_0000000000000001", **_fields(**overrides)}


# ---------------------------------------------------------------------------
# 0. The frozen shape: exactly 13 fields, no more, no fewer.
# ---------------------------------------------------------------------------


def test_frozen_field_set_is_exactly_the_13_k1_fields():
    assert tuple(RunManifest.model_fields) == K1_FIELDS
    assert len(RunManifest.model_fields) == 13


def test_a_fully_populated_manifest_validates_and_survives_a_json_round_trip():
    manifest = RunManifest(**_kwargs())
    restored = RunManifest.model_validate_json(manifest.model_dump_json())
    assert restored == manifest
    assert restored.command == ["python", "train.py", "--epochs", "3"]
    assert restored.data_refs == ["dataset:alpha"]
    assert restored.parameters == {"lr": 0.1, "epochs": 3}


# ---------------------------------------------------------------------------
# 0b. The reused primitives are actually called, not re-implemented.
# ---------------------------------------------------------------------------


def test_run_id_default_is_produced_by_the_existing_new_id(monkeypatch: pytest.MonkeyPatch):
    """Proves the call site: the default factory looks up `new_id` at call time."""
    monkeypatch.setattr(run_manifest_module, "new_id", lambda prefix: f"{prefix}_SENTINEL")
    assert RunManifest(**_kwargs()).run_id == "run_SENTINEL"


def test_run_id_default_has_the_existing_new_id_shape():
    first = RunManifest(**_kwargs())
    second = RunManifest(**_kwargs())
    assert first.run_id.startswith("run_")
    assert len(first.run_id.split("_", 1)[1]) == 16
    assert first.run_id != second.run_id


def test_created_at_default_is_the_existing_utc_now():
    factory = RunManifest.model_fields["created_at"].default_factory
    assert factory is utc_now
    manifest = RunManifest(**_kwargs())
    assert manifest.created_at.tzinfo is not None


def test_for_work_package_consumes_the_existing_work_package_model():
    package = WorkPackage(
        project_id="demo",
        title="train the baseline",
        objective="produce the baseline metrics",
        tasks=["run training"],
        expected_artifacts=["metrics.json"],
        acceptance_checks=["exit code is 0"],
    )
    manifest = RunManifest.for_work_package(package, **_fields())
    assert manifest.work_package_id == package.work_package_id
    assert manifest.project_id == package.project_id


def test_for_work_package_refuses_a_silent_identifier_override():
    """Re-passing an identifier is a TypeError, not a quiet overwrite of the package's."""
    package = WorkPackage(
        project_id="demo",
        title="t",
        objective="o",
        tasks=[],
        expected_artifacts=[],
        acceptance_checks=[],
    )
    with pytest.raises(TypeError):
        RunManifest.for_work_package(package, project_id="someone-elses-project", **_fields())


def test_output_refs_uses_the_existing_artifact_ref_type():
    manifest = RunManifest(**_kwargs(output_hashes={"b.json": "sha256:b", "a.json": "sha256:a"}))
    refs = manifest.output_refs()
    # ArtifactRef comes from autoresearch.contracts: not redefined in run_manifest.
    assert ArtifactRef.__module__ == "autoresearch.contracts"
    assert all(type(ref) is ArtifactRef for ref in refs)
    assert [ref.checksum for ref in refs] == ["sha256:a", "sha256:b"]
    assert [ref.artifact_id for ref in refs] == [
        f"{manifest.run_id}:a.json",
        f"{manifest.run_id}:b.json",
    ]
    assert {ref.kind for ref in refs} == {"run_output"}
    assert {ref.uri for ref in refs} == {None}


def test_output_refs_of_a_run_that_produced_nothing_is_empty_not_a_placeholder():
    manifest = RunManifest(**_kwargs(output_hashes={}))
    assert manifest.output_hashes == {}
    assert manifest.output_refs() == []


# ---------------------------------------------------------------------------
# N-1 / K1-1: `command` is an argv list; a shell string is rejected.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "shell_string",
    [
        "python train.py",
        "python train.py && rm -rf /",
        "python",
        "",
    ],
)
def test_k1_1_shell_string_command_is_rejected(shell_string: str):
    with pytest.raises(ValidationError) as excinfo:
        RunManifest(**_kwargs(command=shell_string))
    assert "argv" in str(excinfo.value)


def test_k1_1_a_rejected_shell_string_is_not_split_into_argv():
    """The string must not be turned into a runnable argv behind the caller's back."""
    with pytest.raises(ValidationError) as excinfo:
        RunManifest(**_kwargs(command="python train.py"))
    # The error names the rule and carries no fabricated argv.
    assert "argv list" in str(excinfo.value)
    assert excinfo.value.errors()[0]["type"] == "value_error"


def test_k1_1_an_argv_list_is_preserved_verbatim_without_rejoining_or_splitting():
    argv = ["python", "-c", "print('a b')", "--flag=1"]
    assert RunManifest(**_kwargs(command=argv)).command == argv
    # An element containing spaces stays a single element: no re-splitting.
    assert RunManifest(**_kwargs(command=["echo", "a b"])).command == ["echo", "a b"]


def test_k1_1_non_string_command_elements_are_rejected():
    with pytest.raises(ValidationError):
        RunManifest(**_kwargs(command=["python", 3]))


# ---------------------------------------------------------------------------
# N-2 / K1-2: `seeds` is never empty; deterministic runs write an explicit [0].
# ---------------------------------------------------------------------------


def test_k1_2_empty_seeds_is_rejected():
    with pytest.raises(ValidationError):
        RunManifest(**_kwargs(seeds=[]))


def test_k1_2_explicit_zero_seed_is_the_way_to_declare_a_deterministic_run():
    manifest = RunManifest(**_kwargs(seeds=[0]))
    assert manifest.seeds == [0]


@pytest.mark.parametrize("seeds", [[1], [0, 1, 2], [42, 42], [-1]])
def test_k1_2_non_empty_seed_lists_pass(seeds: list[int]):
    assert RunManifest(**_kwargs(seeds=seeds)).seeds == seeds


def test_k1_2_missing_seeds_is_rejected_rather_than_defaulted():
    """Omitting the seed is what K1-2 forbids, so there is no default to fall back on."""
    kwargs = _kwargs()
    kwargs.pop("seeds")
    with pytest.raises(ValidationError):
        RunManifest(**kwargs)


# ---------------------------------------------------------------------------
# N-3 / K1-3 (the core case): None == not executed; 0 == executed and fine.
# ---------------------------------------------------------------------------


def test_k1_3_unexecuted_none_is_never_coerced_to_zero():
    not_executed = RunManifest(**_kwargs(exit_code=None))
    # `is None`, not `== 0`: a truthiness check would pass for both states.
    assert not_executed.exit_code is None
    assert not_executed.executed is False
    assert not_executed.model_dump()["exit_code"] is None
    assert '"exit_code":null' in not_executed.model_dump_json()


def test_k1_3_the_default_is_unexecuted_not_a_successful_run():
    assert RunManifest(**_kwargs()).exit_code is None


def test_k1_3_executed_success_and_unexecuted_stay_semantically_distinct():
    not_executed = RunManifest(**_kwargs(exit_code=None))
    succeeded = RunManifest(**_kwargs(exit_code=0))
    assert succeeded.exit_code == 0
    assert succeeded.executed is True
    assert not_executed.exit_code != succeeded.exit_code
    assert not_executed.executed != succeeded.executed
    # The distinction survives serialisation in both directions.
    assert RunManifest.model_validate_json(not_executed.model_dump_json()).executed is False
    assert RunManifest.model_validate_json(succeeded.model_dump_json()).exit_code == 0


def test_k1_3_a_serialised_unexecuted_manifest_stays_unexecuted():
    """Re-reading must not turn "unknown" into a normal value."""
    for _ in range(2):
        manifest = RunManifest(**_kwargs(exit_code=None))
        round_tripped = RunManifest.model_validate_json(manifest.model_dump_json())
        assert round_tripped.exit_code is None


# ---------------------------------------------------------------------------
# N-4 / K1-3: a non-zero exit code is an executed (failed) run.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [1, 2, 137, -9])
def test_k1_3_non_zero_exit_code_is_accepted_as_an_executed_run(code: int):
    manifest = RunManifest(**_kwargs(exit_code=code))
    assert manifest.exit_code == code
    assert manifest.executed is True
    assert manifest.model_dump()["exit_code"] == code


def test_k1_3_a_failed_run_is_not_read_as_never_run():
    failed = RunManifest(**_kwargs(exit_code=1))
    not_executed = RunManifest(**_kwargs(exit_code=None))
    assert failed.executed is not not_executed.executed
    assert failed.exit_code is not None
    assert RunManifest.model_validate_json(failed.model_dump_json()).exit_code == 1


# ---------------------------------------------------------------------------
# Registered strengthenings: the coercions pydantic would otherwise perform.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [False, True])
def test_exit_code_rejects_bools_that_pydantic_would_coerce_to_zero_or_one(value: bool):
    """`bool` is an `int` subclass; lax mode maps False -> 0 (i.e. "succeeded")."""
    with pytest.raises(ValidationError):
        RunManifest(**_kwargs(exit_code=value))


@pytest.mark.parametrize("value", ["0", "1", "137"])
def test_exit_code_rejects_strings_because_no_status_was_observed(value: str):
    with pytest.raises(ValidationError):
        RunManifest(**_kwargs(exit_code=value))


def test_an_unknown_field_is_rejected_instead_of_silently_dropped():
    """A typo such as `seed=` must not be recorded as "not provided"."""
    with pytest.raises(ValidationError):
        RunManifest(**_kwargs(seed=0))


# ---------------------------------------------------------------------------
# K1-4: architectural intent -- assert the ABSENCE of a validator, nothing else.
# ---------------------------------------------------------------------------


def test_k1_4_has_no_validator_because_authenticity_is_not_machine_checkable():
    """This asserts that K1-4 is honoured by *not* pretending to check it.

    Authenticity needs the real files at production time (executor + M08-07 gate).
    A validator here could only compare strings, so any test of it would be
    vacuously green.  If someone later adds one, this test must fail.
    """
    validated: set[str] = set()
    for decorator in RunManifest.__pydantic_decorators__.field_validators.values():
        validated.update(decorator.info.fields)
    assert "output_hashes" not in validated
    assert validated == {"command", "exit_code"}

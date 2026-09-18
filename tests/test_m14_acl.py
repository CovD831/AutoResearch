"""K11 ``AccessPolicy`` tests (M14-03) -- default deny, observable over-reach, elevation.

Negative example **N-1** lives here: an access with no policy is denied *and* the
denial is observable (a raised ``AccessDenied`` plus a recorded denial) -- never a
silent empty list.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autoresearch.acl import (
    ELEVATED_ACTIONS,
    NO_POLICY_REASON,
    POLICY_NOT_GRANTED_REASON,
    AccessDenied,
    AccessPolicy,
    AccessPolicyStore,
    MissingJustification,
    ResourceAction,
    ResourceKind,
    as_action,
    as_kind,
)

SUBJECT = "alice"


def _grant(
    store: AccessPolicyStore,
    *,
    resource_id: str = "art-1",
    kind: str = "artifact",
    actions: list[str] | None = None,
    subject: str = SUBJECT,
    granted: bool = True,
    justification: str | None = None,
) -> AccessPolicy:
    return store.grant(
        AccessPolicy(
            subject=subject,
            resource_kind=kind,  # type: ignore[arg-type]
            resource_id=resource_id,
            actions=actions or ["read"],  # type: ignore[arg-type]
            granted=granted,
        ),
        justification=justification,
    )


# ---------------------------------------------------------------------------
# Vocabulary / model
# ---------------------------------------------------------------------------


def test_resource_kind_and_action_members_match_the_contract():
    assert {k.value for k in ResourceKind} == {"project", "partition", "artifact"}
    assert {a.value for a in ResourceAction} == {"read", "write", "export", "delete"}
    assert {ResourceAction.EXPORT, ResourceAction.DELETE} == set(ELEVATED_ACTIONS)


def test_actions_accept_plain_strings_and_reject_unknown_ones():
    policy = AccessPolicy(
        subject=SUBJECT,
        resource_kind="artifact",  # type: ignore[arg-type]
        resource_id="art-1",
        actions=["read", "write"],  # type: ignore[arg-type]
        granted=True,
    )
    assert policy.actions == [ResourceAction.READ, ResourceAction.WRITE]
    with pytest.raises(ValidationError):
        AccessPolicy(
            subject=SUBJECT,
            resource_kind="artifact",  # type: ignore[arg-type]
            resource_id="art-1",
            actions=["read", "publish"],  # type: ignore[arg-type]
            granted=True,
        )


def test_duplicate_actions_are_rejected():
    with pytest.raises(ValidationError):
        AccessPolicy(
            subject=SUBJECT,
            resource_kind="artifact",  # type: ignore[arg-type]
            resource_id="art-1",
            actions=["read", "read"],  # type: ignore[arg-type]
            granted=True,
        )


def test_narrowing_helpers_reject_typos_loudly():
    assert as_kind("artifact") is ResourceKind.ARTIFACT
    assert as_action("read") is ResourceAction.READ
    with pytest.raises(ValueError, match="unknown resource_kind"):
        as_kind("artefact")
    with pytest.raises(ValueError, match="unknown resource action"):
        as_action("publish")


# ---------------------------------------------------------------------------
# K11-1 default deny
# ---------------------------------------------------------------------------


def test_no_policy_defaults_to_denied():
    store = AccessPolicyStore()
    decision = store.check(SUBJECT, "artifact", "art-1", "read")
    assert decision.allowed is False
    assert decision.reason == NO_POLICY_REASON
    assert decision.policy is None


def test_a_policy_row_that_does_not_grant_is_still_denied_and_distinguishable():
    store = AccessPolicyStore()
    _grant(store, granted=False)
    decision = store.check(SUBJECT, "artifact", "art-1", "read")
    assert decision.allowed is False
    # "a row exists but does not grant" is not the same fact as "no row at all".
    assert decision.reason == POLICY_NOT_GRANTED_REASON
    assert decision.reason != NO_POLICY_REASON


def test_action_outside_the_granted_set_is_denied():
    store = AccessPolicyStore()
    _grant(store, actions=["read"])
    assert store.check(SUBJECT, "artifact", "art-1", "read").allowed is True
    write = store.check(SUBJECT, "artifact", "art-1", "write")
    assert write.allowed is False
    assert write.reason == "action_not_granted"


def test_revoke_returns_the_resource_to_default_deny():
    store = AccessPolicyStore()
    _grant(store)
    assert store.check(SUBJECT, "artifact", "art-1", "read").allowed is True
    store.revoke(SUBJECT, "artifact", "art-1")
    decision = store.check(SUBJECT, "artifact", "art-1", "read")
    assert decision.allowed is False
    assert decision.reason == NO_POLICY_REASON


def test_grants_are_scoped_to_subject_and_resource():
    store = AccessPolicyStore()
    _grant(store, resource_id="art-1")
    assert store.check("bob", "artifact", "art-1", "read").allowed is False
    assert store.check(SUBJECT, "artifact", "art-2", "read").allowed is False
    assert store.check(SUBJECT, "partition", "art-1", "read").allowed is False


# ---------------------------------------------------------------------------
# N-1: over-reach must be observable, never a silent empty result
# ---------------------------------------------------------------------------


def test_require_raises_and_records_the_denial():
    store = AccessPolicyStore()
    assert store.denials == ()
    with pytest.raises(AccessDenied) as excinfo:
        store.require(SUBJECT, "artifact", "art-1", "read")
    assert excinfo.value.decision.reason == NO_POLICY_REASON
    assert len(store.denials) == 1
    denial = store.denials[0]
    assert denial.subject == SUBJECT
    assert denial.resource_id == "art-1"
    assert denial.action is ResourceAction.READ
    assert denial.reason == NO_POLICY_REASON


def test_require_is_a_no_op_on_an_allowed_action():
    store = AccessPolicyStore()
    _grant(store)
    decision = store.require(SUBJECT, "artifact", "art-1", "read")
    assert decision.allowed is True
    assert store.denials == ()


def test_check_alone_does_not_record_a_denial():
    store = AccessPolicyStore()
    store.check(SUBJECT, "artifact", "art-1", "read")
    assert store.denials == ()


def test_readable_resources_raises_for_an_unknown_subject_not_empty_list():
    """N-1 core: ``[]`` must never stand in for "you are not allowed"."""
    store = AccessPolicyStore()
    with pytest.raises(AccessDenied) as excinfo:
        store.readable_resources(SUBJECT, "artifact", ["art-1", "art-2"])
    assert excinfo.value.decision.reason == NO_POLICY_REASON
    assert len(store.denials) == 1


def test_readable_resources_filters_once_the_subject_is_known():
    store = AccessPolicyStore()
    _grant(store, resource_id="art-1", actions=["read"])
    _grant(store, resource_id="art-2", actions=["write"])  # known, but not readable
    assert store.readable_resources(SUBJECT, "artifact", ["art-1", "art-2"]) == ["art-1"]
    # a known subject with nothing readable may legitimately get [] -- no denial
    assert store.readable_resources(SUBJECT, "artifact", ["art-3"]) == []
    assert store.denials == ()


# ---------------------------------------------------------------------------
# K11-3 export/delete need a higher threshold
# ---------------------------------------------------------------------------


def test_elevated_grant_without_justification_is_rejected():
    store = AccessPolicyStore()
    for action in ("export", "delete"):
        with pytest.raises(MissingJustification):
            store.grant(
                AccessPolicy(
                    subject=SUBJECT,
                    resource_kind="artifact",  # type: ignore[arg-type]
                    resource_id="art-1",
                    actions=[action],  # type: ignore[arg-type]
                    granted=True,
                )
            )
    # nothing was inserted
    assert store.check(SUBJECT, "artifact", "art-1", "export").reason == NO_POLICY_REASON


def test_blank_justification_does_not_count():
    store = AccessPolicyStore()
    with pytest.raises(MissingJustification):
        store.grant(
            AccessPolicy(
                subject=SUBJECT,
                resource_kind="artifact",  # type: ignore[arg-type]
                resource_id="art-1",
                actions=["export"],  # type: ignore[arg-type]
                granted=True,
            ),
            justification="   ",
        )


def test_elevated_grant_with_justification_allows_the_action():
    store = AccessPolicyStore()
    _grant(store, actions=["read", "export"], justification="legal-approved: ticket OPS-1")
    assert store.check(SUBJECT, "artifact", "art-1", "read").allowed is True
    export = store.check(SUBJECT, "artifact", "art-1", "export")
    assert export.allowed is True
    assert export.elevated is True


def test_a_denying_policy_needs_no_justification():
    """A ``granted=False`` row can only ever remove access, so K11-3 does not apply."""
    store = AccessPolicyStore()
    _grant(store, actions=["read", "export", "delete"], granted=False)
    decision = store.check(SUBJECT, "artifact", "art-1", "export")
    assert decision.allowed is False


def test_elevation_loses_its_justification_if_the_grant_is_replaced():
    """The justification is re-checked at authorization time, not only at grant time."""
    store = AccessPolicyStore()
    _grant(store, actions=["export"], justification="legal-approved")
    assert store.check(SUBJECT, "artifact", "art-1", "export").allowed is True
    # replace with a read-only grant: the elevation record must be dropped with it
    _grant(store, actions=["read"])
    assert store.check(SUBJECT, "artifact", "art-1", "export").allowed is False


def test_elevation_added_after_the_grant_is_denied():
    """Reachability proof for the authorization-time re-check.

    ``AccessPolicy`` is a mutable pydantic model, so a holder can widen
    ``actions`` *after* ``grant()`` ran.  ``grant()`` would have rejected an
    unjustified ``export`` up front; this asserts the widened row cannot slip
    through later, which is the whole point of re-checking at use time.
    """
    store = AccessPolicyStore()
    policy = _grant(store, actions=["read"])  # no justification was recorded
    policy.actions.append(ResourceAction.EXPORT)  # a later mutation widens the grant
    decision = store.check(SUBJECT, "artifact", "art-1", "export")
    assert decision.allowed is False
    assert decision.reason == "missing_justification"
    assert decision.elevated is True


def test_a_justification_covers_only_the_action_it_was_written_for():
    """A justification for ``export`` must not launder a later-added ``delete``."""
    store = AccessPolicyStore()
    policy = _grant(store, actions=["read", "export"], justification="legal: export only")
    assert store.check(SUBJECT, "artifact", "art-1", "export").allowed is True

    policy.actions.append(ResourceAction.DELETE)  # widened after the grant
    delete = store.check(SUBJECT, "artifact", "art-1", "delete")
    assert delete.allowed is False
    assert delete.reason == "missing_justification"
    # ... while the original, properly justified action still works
    assert store.check(SUBJECT, "artifact", "art-1", "export").allowed is True

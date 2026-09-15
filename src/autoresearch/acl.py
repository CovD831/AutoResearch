"""K11 ``AccessPolicy`` -- default-deny resource access control (M14-03).

Contract: ``docs/rearchitecture/R007-parallel-modules/04-l2-contracts.md`` K11.
Three invariants drive this module:

* **K11-1 默认拒绝** -- a resource with no matching policy is *not* readable.
  :meth:`AccessPolicyStore.check` therefore starts from ``allowed=False`` and only
  ever flips it after a matching, granted policy has been found.  A revoked
  policy (``granted=False``) denies too, but with a *different* reason
  (``policy_not_granted`` vs ``no_policy``) so the two are distinguishable.
* **K11-2 越权必须可观测** -- a denied access is never a silent empty result.
  :meth:`AccessPolicyStore.require` raises :class:`AccessDenied`, and
  :meth:`AccessPolicyStore.readable_resources` raises for a subject that holds no
  policy at all instead of returning ``[]``: an empty list is indistinguishable
  from "there was nothing to read", which is precisely the defect this clause
  forbids.  Every denial is also appended to :attr:`AccessPolicyStore.denials`
  so a telemetry/audit consumer can count them (K13 ``metric="denied"``).
* **K11-3 export/delete 需更高门槛** -- :data:`ELEVATED_ACTIONS` must carry a
  non-empty justification before the grant is accepted, and the justification is
  re-checked at authorization time.

This module owns no storage and no audit chain: it is a pure policy engine whose
only input is the policy table it is handed.  It never writes to
``storage.py`` / ``knowledge.py`` / ``contracts.py``.

Measured existence check (word boundary, *not* ``grep -i acl`` -- that matches
``dataclasses``): ``grep -rniE "\\bACL\\b" src tests`` == 0 lines, i.e. this is a
green-field build.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id, utc_now

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class ResourceKind(StrEnum):
    """The three resource kinds K11 names."""

    PROJECT = "project"
    PARTITION = "partition"
    ARTIFACT = "artifact"


class ResourceAction(StrEnum):
    """The four actions K11 names."""

    READ = "read"
    WRITE = "write"
    EXPORT = "export"
    DELETE = "delete"


#: K11-3: the actions that need a *higher* threshold than a plain read/write
#: grant.  A policy covering one of these is rejected unless it names a
#: justification, and the justification is re-checked when it is used.
ELEVATED_ACTIONS: frozenset[ResourceAction] = frozenset(
    {ResourceAction.EXPORT, ResourceAction.DELETE}
)

#: Reason string for "we found no policy at all".  Kept as a constant so tests
#: and callers branch on a name, not on free-form prose.
NO_POLICY_REASON = "no_policy"
POLICY_NOT_GRANTED_REASON = "policy_not_granted"
ACTION_NOT_GRANTED_REASON = "action_not_granted"
MISSING_JUSTIFICATION_REASON = "missing_justification"
GRANTED_REASON = "granted"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AccessError(PermissionError):
    """Base class for the ACL failures.  Derives from ``PermissionError`` for
    parity with the existing ``promote()`` failure semantics."""


class MissingJustification(AccessError):
    """K11-3: an elevated grant arrived without a justification.

    Raised from :meth:`AccessPolicyStore.grant` -- it is a *policy authoring*
    error, not an authorization result, so it never reaches the denial log.
    """


class AccessDenied(AccessError):
    """K11-1/K11-2: an authorization decision came back ``allowed=False``.

    Carries the full :class:`AccessDecision` so the caller can log the reason;
    the message is a stable, greppable one-liner.  Raising (rather than
    returning ``False``/``[]``) is what makes an over-reach *observable*.
    """

    def __init__(self, decision: AccessDecision) -> None:
        super().__init__(
            f"access denied: subject={decision.subject!r} "
            f"kind={decision.resource_kind.value} resource={decision.resource_id!r} "
            f"action={decision.action.value} reason={decision.reason}"
        )
        self.decision = decision


# ---------------------------------------------------------------------------
# Policy + decisions
# ---------------------------------------------------------------------------


class AccessPolicy(BaseModel):
    """K11 ``AccessPolicy`` -- one (subject, resource) grant/deny row.

    ``actions`` is narrowed to :class:`ResourceAction` (the L2 table writes
    ``list[str]``); a bare ``"read"`` string is still accepted and coerced, but
    an unknown action now fails validation instead of being silently ignored.
    """

    subject: str = Field(min_length=1, max_length=200)
    resource_kind: ResourceKind
    resource_id: str = Field(min_length=1, max_length=400)
    actions: list[ResourceAction] = Field(default_factory=list)
    granted: bool = False

    @model_validator(mode="after")
    def _reject_duplicate_actions(self) -> AccessPolicy:
        if len(set(self.actions)) != len(self.actions):
            raise ValueError("actions must be unique")
        return self

    @property
    def elevated_actions(self) -> frozenset[ResourceAction]:
        return frozenset(self.actions) & ELEVATED_ACTIONS


class AccessDecision(BaseModel):
    """The outcome of one authorization query (always returned by ``check``)."""

    subject: str
    resource_kind: ResourceKind
    resource_id: str
    action: ResourceAction
    allowed: bool
    reason: str
    policy: AccessPolicy | None = None
    elevated: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class DenialRecord(BaseModel):
    """One observable denial (K11-2).  Consumed by the audit/telemetry layer."""

    denial_id: str = Field(default_factory=lambda: new_id("denial"))
    subject: str
    resource_kind: ResourceKind
    resource_id: str
    action: ResourceAction
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

_PolicyKey = tuple[str, str, str]


def as_kind(value: ResourceKind | str) -> ResourceKind:
    """Narrow the contract's plain ``str`` to :class:`ResourceKind`.

    K11 declares ``resource_kind`` / ``actions`` as ``str``; the store accepts
    either a member or the literal and fails loudly on an unknown value instead
    of silently treating it as "not granted".
    """
    if isinstance(value, ResourceKind):
        return value
    try:
        return ResourceKind(value)
    except ValueError as exc:
        raise ValueError(
            f"unknown resource_kind {value!r}; expected one of "
            f"{sorted(k.value for k in ResourceKind)}"
        ) from exc


def as_action(value: ResourceAction | str) -> ResourceAction:
    """Narrow the contract's plain ``str`` to :class:`ResourceAction`."""
    if isinstance(value, ResourceAction):
        return value
    try:
        return ResourceAction(value)
    except ValueError as exc:
        raise ValueError(
            f"unknown resource action {value!r}; expected one of "
            f"{sorted(a.value for a in ResourceAction)}"
        ) from exc


def _key(subject: str, resource_kind: ResourceKind, resource_id: str) -> _PolicyKey:
    return (subject, resource_kind.value, resource_id)


class AccessPolicyStore:
    """An in-memory policy table with default-deny authorization.

    Not a persistence layer: the caller decides where policies come from.  The
    store is deliberately small -- ``grant`` / ``revoke`` / ``check`` /
    ``require`` / ``readable_resources`` -- so the whole K11 surface is
    inspectable in one screen.
    """

    def __init__(self) -> None:
        self._policies: dict[_PolicyKey, AccessPolicy] = {}
        # key -> {action value -> justification}.  Stored *per action*, not per
        # policy row: a justification written for ``export`` must not silently
        # cover a ``delete`` that gets appended to the same row later.
        self._justifications: dict[_PolicyKey, dict[str, str]] = {}
        self._denials: list[DenialRecord] = []

    # -- authoring ---------------------------------------------------------

    def grant(self, policy: AccessPolicy, *, justification: str | None = None) -> AccessPolicy:
        """Insert/replace a policy.

        K11-3: a *granted* policy that covers :data:`ELEVATED_ACTIONS` must name
        a non-empty ``justification``.  A denying policy (``granted=False``)
        never needs one -- it can only ever remove access.
        """
        key = _key(policy.subject, policy.resource_kind, policy.resource_id)
        elevated = policy.elevated_actions
        text = (justification or "").strip()
        if policy.granted and elevated and not text:
            raise MissingJustification(
                f"elevated grant for {policy.resource_id!r} covers "
                f"{sorted(a.value for a in elevated)} and needs a justification"
            )
        self._policies[key] = policy
        if policy.granted and elevated:
            self._justifications[key] = {action.value: text for action in elevated}
        else:
            self._justifications.pop(key, None)
        return policy

    def revoke(
        self, subject: str, resource_kind: ResourceKind | str, resource_id: str
    ) -> None:
        """Drop a policy entirely.  Absent afterwards == default deny."""
        key = _key(subject, as_kind(resource_kind), resource_id)
        self._policies.pop(key, None)
        self._justifications.pop(key, None)

    # -- reading -----------------------------------------------------------

    def policy_for(
        self, subject: str, resource_kind: ResourceKind | str, resource_id: str
    ) -> AccessPolicy | None:
        return self._policies.get(_key(subject, as_kind(resource_kind), resource_id))

    @property
    def denials(self) -> tuple[DenialRecord, ...]:
        """Every recorded denial, oldest first (K11-2 observability channel)."""
        return tuple(self._denials)

    def has_any_policy(self, subject: str, resource_kind: ResourceKind | str) -> bool:
        """Does *subject* hold at least one policy for *resource_kind*?

        This is the "is this subject known at all?" probe that
        :meth:`readable_resources` uses to avoid returning a misleading ``[]``.
        """
        kind = as_kind(resource_kind)
        return any(
            key[0] == subject and key[1] == kind.value for key in self._policies
        )

    # -- authorization -----------------------------------------------------

    def check(
        self,
        subject: str,
        resource_kind: ResourceKind | str,
        resource_id: str,
        action: ResourceAction | str,
    ) -> AccessDecision:
        """Pure authorization query.  Never raises, never records a denial.

        Use :meth:`require` when an over-reach must be observable by default.
        """
        kind = as_kind(resource_kind)
        act = as_action(action)
        elevated = act in ELEVATED_ACTIONS
        policy = self.policy_for(subject, kind, resource_id)

        def decision(allowed: bool, reason: str) -> AccessDecision:
            return AccessDecision(
                subject=subject,
                resource_kind=kind,
                resource_id=resource_id,
                action=act,
                allowed=allowed,
                reason=reason,
                policy=policy,
                elevated=elevated,
            )

        if policy is None:
            # K11-1: default deny.
            return decision(False, NO_POLICY_REASON)
        if not policy.granted:
            return decision(False, POLICY_NOT_GRANTED_REASON)
        if act not in policy.actions:
            return decision(False, ACTION_NOT_GRANTED_REASON)
        if elevated and not self._justifications.get(
            _key(subject, kind, resource_id), {}
        ).get(act.value, ""):
            # K11-3: this specific elevated action has no live justification --
            # either the row lost it, or the action was widened after the grant.
            return decision(False, MISSING_JUSTIFICATION_REASON)
        return decision(True, GRANTED_REASON)

    def require(
        self,
        subject: str,
        resource_kind: ResourceKind | str,
        resource_id: str,
        action: ResourceAction | str,
    ) -> AccessDecision:
        """K11-2: ``check`` + record the denial + raise :class:`AccessDenied`."""
        result = self.check(subject, resource_kind, resource_id, action)
        if not result.allowed:
            self._record_denial(result)
            raise AccessDenied(result)
        return result

    def readable_resources(
        self,
        subject: str,
        resource_kind: ResourceKind | str,
        resource_ids: list[str],
    ) -> list[str]:
        """Return the subset of *resource_ids* the subject may ``read``.

        K11-2: if the subject holds **no** policy for this kind, this raises
        :class:`AccessDenied` instead of returning ``[]``.  A caller that
        receives ``[]`` from here can rely on the fact that the subject is known
        and simply has nothing readable -- "you are not allowed" and "there is
        nothing here" are never conflated.
        """
        kind = as_kind(resource_kind)
        if not self.has_any_policy(subject, kind):
            result = self.check(subject, kind, "*", ResourceAction.READ)
            self._record_denial(result)
            raise AccessDenied(result)
        readable: list[str] = []
        for resource_id in resource_ids:
            result = self.check(subject, kind, resource_id, ResourceAction.READ)
            if result.allowed:
                readable.append(resource_id)
        return readable

    # -- internals ---------------------------------------------------------

    def _record_denial(self, decision: AccessDecision) -> DenialRecord:
        record = DenialRecord(
            subject=decision.subject,
            resource_kind=decision.resource_kind,
            resource_id=decision.resource_id,
            action=decision.action,
            reason=decision.reason,
        )
        self._denials.append(record)
        return record

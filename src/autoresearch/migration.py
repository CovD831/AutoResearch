"""K6 state migration (M01-02).

Contract authority: R-007 ``docs/rearchitecture/R007-parallel-modules/04-l2-contracts.md``
§K6 (``StateMigration``).

The whole point of this module is the *silent loss* defence (K6-1): the
``unknown_field_policy`` is a required field with no default, so a migration
cannot be constructed without stating what happens to fields it does not know.
``reject`` fails loudly; ``preserve`` carries them through unchanged.

Version labels are only ever ordered through :func:`version_key`. A label with no
numeric component is rejected rather than sorted as ``0`` — treating an
unparsable version as the lowest one is exactly the "missing recorded as a
normal value" defect family this repository keeps hitting.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from autoresearch.contracts import new_id

_VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)*")


class UnknownFieldPolicy(StrEnum):
    """K6-1: the policy must be stated explicitly, never assumed."""

    REJECT = "reject"
    PRESERVE = "preserve"


class MigrationError(ValueError):
    """Base class for migration failures."""


class UnknownFieldError(MigrationError):
    """Raised when ``reject`` meets a field the migration cannot place."""

    def __init__(self, fields: Sequence[str]) -> None:
        self.fields = sorted(fields)
        super().__init__(
            "unknown_field_policy is 'reject' and the payload carries "
            f"unmapped field(s): {', '.join(self.fields)}"
        )


class FieldCollisionError(MigrationError):
    """Raised when two values would land on the same output field."""


def version_key(version: str) -> tuple[int, ...]:
    """Order version labels numerically (``v1 < v2 < v10``), not lexically.

    Rejects labels without a numeric component instead of ranking them as zero.
    """

    match = _VERSION_PATTERN.search(version)
    if match is None:
        raise ValueError(
            f"cannot order version label {version!r}: no numeric component to compare"
        )
    return tuple(int(part) for part in match.group(0).split("."))


def state_version(model: object) -> str:
    """Bridge an existing state object's version onto a K6 version label.

    K6 declares ``from_version``/``to_version`` as ``str``, while the existing
    ``ResearchState.schema_version`` (``contracts.py:642``) is an ``int``
    (currently only ever ``1``). The two are reconciled in exactly one place so
    callers do not each invent a label scheme. Raises when there is no integer
    version to read — an absent version is not silently treated as the first one.
    """

    version = getattr(model, "schema_version", None)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(
            "cannot bridge to a K6 version label: object has no integer "
            f"`schema_version` (got {version!r})"
        )
    return f"v{version}"


class StateMigration(BaseModel):
    """A single migration step (K6)."""

    migration_id: str = Field(default_factory=lambda: new_id("mig"))
    from_version: str = Field(min_length=1)
    to_version: str = Field(min_length=1)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    #: Required, deliberately without a default (K6-1).
    unknown_field_policy: Literal["reject", "preserve"]
    defaults: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_step(self) -> StateMigration:
        if version_key(self.to_version) <= version_key(self.from_version):
            raise ValueError(
                f"to_version {self.to_version!r} must be strictly greater than "
                f"from_version {self.from_version!r} (K6-3)"
            )
        targets = list(self.field_mapping.values())
        duplicated = sorted({name for name in targets if targets.count(name) > 1})
        if duplicated:
            raise ValueError(
                f"field_mapping maps several source fields onto {duplicated}; "
                "the later value would silently overwrite the earlier one"
            )
        shadowed = sorted(set(self.defaults) & set(targets))
        if shadowed:
            raise ValueError(
                f"defaults for {shadowed} are unreachable: field_mapping already "
                "produces those fields, so the default would never apply"
            )
        return self

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Apply the step. Deterministic: same input, same output (K6-2)."""

        if not isinstance(payload, Mapping):
            raise TypeError(f"payload must be a mapping, got {type(payload).__name__}")

        known_targets = set(self.field_mapping.values()) | set(self.defaults)
        result: dict[str, Any] = {}
        unknown: list[str] = []
        for key, value in payload.items():
            if key in self.field_mapping:
                target: str | None = self.field_mapping[key]
            elif key in known_targets:
                # The field already carries its post-migration name.
                target = key
            else:
                target = None
            if target is None:
                unknown.append(key)
                continue
            if target in result:
                raise FieldCollisionError(
                    f"field {target!r} would be written twice in one payload "
                    f"(at least once from {key!r}); the later value would "
                    "silently overwrite the earlier one"
                )
            result[target] = value

        if unknown and self.unknown_field_policy == UnknownFieldPolicy.REJECT:
            raise UnknownFieldError(unknown)
        for key in unknown:
            result[key] = payload[key]
        for key, default in self.defaults.items():
            result.setdefault(key, default)
        return result


class MigrationChain(BaseModel):
    """An ordered, contiguous set of steps (K6-3).

    Extension, not a K6 field: the contract's steps are single hops, and
    "``to_version`` strictly increases" only becomes a real constraint once
    several hops are composed.
    """

    migrations: list[StateMigration] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_chain(self) -> MigrationChain:
        # Contiguity is checked here; *strict increase across the chain* is not a
        # separate check because it is implied: each step already requires
        # to_version > from_version (K6-3, enforced on StateMigration) and
        # contiguity pins step i's target to step i+1's source. A standalone
        # ordering check here would be unreachable, and an unreachable invariant
        # is not an invariant — so none is written (see L3 §Deliberate non-goals).
        for current, following in zip(self.migrations, self.migrations[1:], strict=False):
            if current.to_version != following.from_version:
                raise ValueError(
                    "migration chain is not contiguous: "
                    f"{current.to_version!r} -> {following.from_version!r}"
                )
        return self

    @property
    def from_version(self) -> str | None:
        return self.migrations[0].from_version if self.migrations else None

    @property
    def to_version(self) -> str | None:
        return self.migrations[-1].to_version if self.migrations else None

    def migrate(self, payload: Mapping[str, Any], *, to_version: str | None = None) -> dict:
        """Run the chain (up to ``to_version`` when given) over ``payload``."""

        target = version_key(to_version) if to_version is not None else None
        result = dict(payload)
        for step in self.migrations:
            if target is not None and version_key(step.to_version) > target:
                break
            result = step.apply(result)
        return result

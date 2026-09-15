"""SHIM: symbols + field declarations only; no validators, no algorithm bodies."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UnknownFieldPolicy(StrEnum):
    REJECT = "reject"
    PRESERVE = "preserve"


class MigrationError(ValueError):
    pass


class UnknownFieldError(MigrationError):
    def __init__(self, fields) -> None:
        self.fields = sorted(fields)
        super().__init__("shim")


class FieldCollisionError(MigrationError):
    pass


def version_key(version: str) -> tuple[int, ...]:
    raise NotImplementedError("shim")


def state_version(model: object) -> str:
    raise NotImplementedError("shim")


class StateMigration(BaseModel):
    migration_id: str = "shim"
    from_version: str
    to_version: str
    field_mapping: dict[str, str] = Field(default_factory=dict)
    unknown_field_policy: str = "preserve"  # naive default: no explicit-policy rule
    defaults: dict[str, Any] = Field(default_factory=dict)

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("shim")


class MigrationChain(BaseModel):
    migrations: list[StateMigration] = Field(default_factory=list)

    def migrate(self, payload: Mapping[str, Any], *, to_version: str | None = None) -> dict:
        raise NotImplementedError("shim")

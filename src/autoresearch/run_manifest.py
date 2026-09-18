"""K1 ``RunManifest`` -- the frozen run-identity contract (R-007 L2, `accepted`).

Why this module exists
----------------------
Every run record in the program has to answer one question first: *which run was
this?*  R-006 shipped without a frozen answer, and each lane invented its own run
identifier, so the records could not be joined afterwards.  K1 freezes the schema
once, here, and the other lanes **reference** it:

* L-02 ``PrefetchRecord`` -- ``run_id`` must reference :attr:`RunManifest.run_id`
* L-09 ``TelemetryPoint`` -- ``dimensions["run"]`` must reference :attr:`RunManifest.run_id`

This module is the exclusive definition site of K1 (R-007 dispatch sheet §2).  It
deliberately does **not** live in ``contracts.py``: that file is held by the
L-06/L-07 lanes (R-007 §5, "three places must stay serial"), so the K1 types are
defined in this new module.  Whether they are later hoisted into ``contracts.py``
is an owner decision, not this package's.

Reused primitives (imported and called, never re-implemented)
-------------------------------------------------------------
``new_id``      :func:`autoresearch.contracts.new_id` -> default for ``run_id``
``utc_now``     :func:`autoresearch.contracts.utc_now` -> default for ``created_at``
``WorkPackage`` :class:`autoresearch.contracts.WorkPackage` -> consumed by
                :meth:`RunManifest.for_work_package`; K1 stores only the
                *reference* ``work_package_id`` and never redefines the model
``ArtifactRef`` :class:`autoresearch.contracts.ArtifactRef` -> :meth:`RunManifest.output_refs`
                projects ``output_hashes`` into the existing artifact-reference
                type; no new artifact type is introduced

Invariants (K1, R-007 L2 §K1)
-----------------------------
**K1-1** ``command`` is an argv list, never a shell string.  A ``str`` is
*rejected* -- it is neither split nor accepted silently.
**K1-2** ``seeds`` is never empty; a deterministic run writes an explicit ``[0]``.
**K1-3** ``exit_code is None`` **iff** the run never executed.  An executed run
carries a code, *including a non-zero one*: a failed run is an executed run.
**K1-4** ``output_hashes`` must not name artifacts that were never produced.

.. warning::
   **K1-4 is an architectural intent, not a machine-checkable rule.**  Deciding
   whether a named artifact really exists (and really hashes to that value) needs
   the actual files, which only the executor can observe at production time.
   Therefore:

   * **no validator exists for K1-4 here**, and
   * **no passing assertion may be written for it** in the test suite -- a test
     that asserts "no fake hash was passed" would be vacuously true for every
     input a validator can see, i.e. a permanently-green assertion that fakes
     coverage.

   The obligation is discharged by the executor writing hashes at production
   time, and verified by the M08-07 execution gate.  An empty dict ``{}`` is the
   correct representation of "nothing was produced" and is the only honest
   representation; a placeholder such as ``{"metrics.json": "unknown"}`` is a
   lie the schema cannot detect and the gate must not accept.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autoresearch.contracts import ArtifactRef, WorkPackage, new_id, utc_now

__all__ = ["RunManifest"]


class RunManifest(BaseModel):
    """The record of a single run: code, data, environment, params, seed, command,
    exit status and output hashes (原表 M08-02).

    All 13 fields are exactly the ones frozen in R-007 L2 §K1 -- none added, none
    dropped.  The four invariants and the K1-4 limitation are documented in the
    module docstring; read it before changing anything here.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: new_id("run"))
    project_id: str
    work_package_id: str
    code_revision: str
    data_refs: list[str]
    environment: dict[str, str]
    parameters: dict[str, Any]
    # K1-2: never empty.  Deterministic runs write an explicit [0]; omitting the
    # seed is what K1-2 forbids, so an empty list must not be a legal way out.
    seeds: list[int] = Field(min_length=1)
    command: list[str]
    # K1-3: None == NOT EXECUTED.  Never the default 0: see _exit_code_semantics.
    exit_code: int | None = None
    # K1-4 (architectural intent, NOT validated here -- see the module docstring):
    # artifact name -> hash.  `{}` when nothing was produced.  Never a fake value.
    output_hashes: dict[str, str]
    rerun_of: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("command", mode="before")
    @classmethod
    def _command_must_be_argv(cls, value: Any) -> Any:
        """K1-1: reject a shell string instead of splitting it.

        Splitting would look helpful and would destroy the audit trail: the argv
        that actually ran would no longer be the argv that was recorded.  The
        caller must pass the argv list it really intends to execute.
        """
        if isinstance(value, str):
            raise ValueError(
                "command must be an argv list (K1-1); "
                "a shell string is rejected, not split: pass e.g. ['python', 'train.py']"
            )
        return value

    @field_validator("exit_code", mode="before")
    @classmethod
    def _exit_code_semantics(cls, value: Any) -> Any:
        """K1-3: ``None`` stays ``None``; only a real int counts as an exit code.

        Two coercions are refused, both of the same defect family this contract
        exists to block -- "record an unknown/failed state as a normal value":

        * ``bool`` -- ``bool`` is a subclass of ``int``, and pydantic's lax mode
          turns ``False`` into ``0``.  ``exit_code=False`` would therefore be
          stored as *executed successfully*, which is exactly a silent
          not-executed -> 0 collapse.
        * ``str`` -- ``"0"`` / ``"1"`` come from a producer that never parsed the
          status, so coercing them fabricates an exit code that was never
          observed.  Pass ``int`` (or ``None``).

        ``0`` and non-zero ints are both accepted: a failed run is still an
        executed run (K1-3).
        """
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(
                "exit_code must be an int or None (K1-3); "
                "a bool would be coerced to 0/1 and silently report an unexecuted run as successful"
            )
        if isinstance(value, str):
            raise ValueError(
                "exit_code must be an int or None (K1-3); "
                "a string carries no observed status, so it is not coerced"
            )
        return value

    @property
    def executed(self) -> bool:
        """Read side of K1-3: ``True`` iff the run actually executed.

        A *failed* run is executed: ``executed`` is ``True`` for ``exit_code=1``.
        Only ``None`` means "never ran".
        """
        return self.exit_code is not None

    @classmethod
    def for_work_package(cls, package: WorkPackage, **fields: Any) -> RunManifest:
        """Build a manifest bound to an existing :class:`WorkPackage`.

        K1 stores a *reference* to the work package; this helper is the call site
        that consumes the existing model (``package.project_id`` /
        ``package.work_package_id``) instead of letting callers retype the two
        identifiers.  ``project_id`` / ``work_package_id`` are taken from the
        package; passing either again is a ``TypeError`` rather than a silent
        override.
        """
        return cls(
            project_id=package.project_id,
            work_package_id=package.work_package_id,
            **fields,
        )

    def output_refs(self) -> list[ArtifactRef]:
        """Project ``output_hashes`` onto the existing :class:`ArtifactRef` type.

        The keys are artifact *names*, not paths -- K1 keeps data/output references
        as stable IDs -- so ``uri`` stays ``None`` and only ``checksum`` is filled.
        The identifiers are derived (``"{run_id}:{name}"``) so a reference can be
        traced back to the run that produced it without a second lookup table.

        Note this does not assess authenticity; that is K1-4, and it is not
        machine-checkable here (module docstring).
        """
        return [
            ArtifactRef(
                artifact_id=f"{self.run_id}:{name}",
                kind="run_output",
                checksum=digest,
            )
            for name, digest in sorted(self.output_hashes.items())
        ]

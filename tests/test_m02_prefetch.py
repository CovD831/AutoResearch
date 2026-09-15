"""M02-07 / K7 ``PrefetchRecord`` tests (L-02 lane).

Discriminating power for a greenfield module is established by *mutation*, not
by running these tests on the pre-fix baseline: on ``main@8dd8780`` this module
does not exist, so the failure there would be ``ModuleNotFoundError`` (a
symbol-missing failure, which this project does not count as evidence). See
``docs/tasks/M02-prefetch/tasks/L3.md`` §5-§6.

K7-1, stated at its real strength (two layers, not one):

* **Globally**, "an L2+ action must have a prefetch record written before it"
  is a *temporal* constraint. No validator can check it, and no test here can
  check it either -- it would have to constrain code in other modules.
* **Within this module's entry** (``execute_l2_action``), "the record is durable
  before the action body runs" *is* asserted, and is genuinely falsifiable:
  ``test_l2_entry_passes_the_written_record_into_the_action`` fails, with a
  judgement-type assertion error, when persistence is deferred until after the
  action runs. That is a *scope-limited* guarantee, not a vacuous pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoresearch.contracts import new_id
from autoresearch.evidence_prefetch import (
    PREFETCH_RECORD_KIND,
    EvidencePrefetchService,
    L0L1NotGatedError,
    MissingBundleError,
    PrefetchDecision,
    PrefetchRecord,
    validate_final_bundle,
)
from autoresearch.storage import RecordStore

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "autoresearch" / "evidence_prefetch.py"


class StubBundles:
    def __init__(self, known: set[str]) -> None:
        self.known = known

    def exists(self, bundle_id: str) -> bool:
        return bundle_id in self.known


def _service(tmp_path: Path, known: set[str] | None = None) -> EvidencePrefetchService:
    store = RecordStore(tmp_path / "prefetch.sqlite3")
    return EvidencePrefetchService(store, bundles=StubBundles(known or set()))


# ---------------------------------------------------------------------------
# K7-2 fail-closed (N-1)
# ---------------------------------------------------------------------------


def test_n1_missing_evidence_decides_blocked_not_proceed(tmp_path: Path) -> None:
    """N-1: with no candidates there is nothing to proceed on."""

    service = _service(tmp_path, {"bundle-a"})
    record = service.write_prefetch(
        action_level=2,
        query="does the source exist",
        candidates=[],
        bundle_id="bundle-a",
    )
    assert record.decision is PrefetchDecision.BLOCKED
    assert record.final_bundle_id is None


def test_proceed_without_bundle_is_rejected_by_the_model(tmp_path: Path) -> None:
    """K7-2 is enforced on the artifact, not only in the decision helper."""

    with pytest.raises(ValidationError):
        PrefetchRecord(
            action_level=2,
            query="q",
            candidates=["ev-1"],
            decision=PrefetchDecision.PROCEED,
        )


def test_proceed_with_no_candidates_is_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError):
        PrefetchRecord(
            action_level=2,
            query="q",
            candidates=[],
            final_bundle_id="bundle-a",
            decision=PrefetchDecision.PROCEED,
        )


def test_blocked_with_a_bundle_is_rejected_by_the_model() -> None:
    """The converse half: a blocked record must not claim the bundle it refused."""

    with pytest.raises(ValidationError):
        PrefetchRecord(
            action_level=3,
            query="q",
            candidates=["ev-1"],
            final_bundle_id="bundle-a",
            decision=PrefetchDecision.BLOCKED,
        )


# ---------------------------------------------------------------------------
# K7-3 foreign key (N-2)
# ---------------------------------------------------------------------------


def test_n2_final_bundle_id_must_resolve_to_an_existing_bundle(tmp_path: Path) -> None:
    """N-2: a dangling bundle id is a contract violation, never a silent pass."""

    service = _service(tmp_path, known={"bundle-real"})
    with pytest.raises(MissingBundleError):
        service.write_prefetch(
            action_level=2,
            query="q",
            candidates=["ev-1"],
            bundle_id=new_id("bundle"),
        )


def test_rejected_bundle_is_not_persisted(tmp_path: Path) -> None:
    service = _service(tmp_path, known=set())
    with pytest.raises(MissingBundleError):
        service.write_prefetch(action_level=2, query="q", candidates=["ev-1"], bundle_id="b-x")
    assert service.store.list(PREFETCH_RECORD_KIND) == []


def test_proceed_with_a_real_bundle_is_persisted(tmp_path: Path) -> None:
    service = _service(tmp_path, known={"bundle-real"})
    record = service.write_prefetch(
        action_level=2,
        query="q",
        candidates=["ev-1"],
        bundle_id="bundle-real",
    )
    assert record.decision is PrefetchDecision.PROCEED
    assert record.final_bundle_id == "bundle-real"
    stored = service.store.get(PREFETCH_RECORD_KIND, record.prefetch_id)
    assert stored is not None
    assert stored["decision"] == "proceed"


def test_validate_final_bundle_uses_the_injected_registry() -> None:
    record = PrefetchRecord(
        action_level=2,
        query="q",
        candidates=["ev-1"],
        final_bundle_id="bundle-real",
        decision=PrefetchDecision.PROCEED,
    )
    validate_final_bundle(record, bundles=StubBundles({"bundle-real"}))
    with pytest.raises(MissingBundleError):
        validate_final_bundle(record, bundles=StubBundles(set()))


def test_blocked_record_does_not_consult_the_bundle_registry(tmp_path: Path) -> None:
    """A blocked record has no bundle, so there is no foreign key to check."""

    class Exploding:
        def exists(self, bundle_id: str) -> bool:  # pragma: no cover - must not run
            raise AssertionError("blocked records must not probe the bundle registry")

    store = RecordStore(tmp_path / "prefetch.sqlite3")
    service = EvidencePrefetchService(store, bundles=Exploding())
    record = service.write_prefetch(action_level=2, query="q", candidates=[])
    assert record.decision is PrefetchDecision.BLOCKED


# ---------------------------------------------------------------------------
# K7-1 structural compensation (NOT an invariant assertion -- see L3 §2.3)
# ---------------------------------------------------------------------------


def test_l2_entry_writes_a_blocked_record_and_does_not_run_the_action(tmp_path: Path) -> None:
    """Fail-closed through the L2+ entry: no evidence -> the action never runs."""

    service = _service(tmp_path)
    calls: list[PrefetchRecord] = []

    def action(record: PrefetchRecord) -> str:  # pragma: no cover - must not run
        calls.append(record)
        return "ran"

    outcome = service.execute_l2_action(
        action_level=2,
        query="q",
        candidates=[],
        action=action,
    )
    assert outcome.executed is False
    assert outcome.result is None
    assert calls == []
    assert outcome.record.decision is PrefetchDecision.BLOCKED
    # The blocked attempt is still an audit fact.
    assert service.store.get(PREFETCH_RECORD_KIND, outcome.record.prefetch_id) is not None


def test_l2_entry_passes_the_written_record_into_the_action(tmp_path: Path) -> None:
    """The action signature *requires* a record, so a record must exist first."""

    service = _service(tmp_path, {"bundle-real"})
    seen: list[str] = []

    def action(record: PrefetchRecord) -> str:
        # The record is already durable by the time the body runs.
        assert service.store.get(PREFETCH_RECORD_KIND, record.prefetch_id) is not None
        seen.append(record.prefetch_id)
        return "done"

    outcome = service.execute_l2_action(
        action_level=3,
        query="q",
        candidates=["ev-1"],
        bundle_id="bundle-real",
        action=action,
    )
    assert outcome.executed is True
    assert outcome.result == "done"
    assert seen == [outcome.record.prefetch_id]


def test_l2_entry_refuses_l0_l1_levels(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(L0L1NotGatedError):
        service.execute_l2_action(action_level=1, query="q", candidates=[], action=lambda _: None)


def test_write_path_has_exactly_one_call_site(tmp_path: Path) -> None:
    """AUXILIARY guard for the compensation mechanism (cheap, narrowly scoped).

    This asserts a *structural* property of this module -- it is NOT the
    unverifiable K7-1 timing claim.

    **Known, measured limitation** (reported by the falsifier, reproduced here):
    it matches one literal syntax shape only. ``getattr(self.store, "put")(...)``,
    a module-level alias ``_PUT = RecordStore.put``, a bound alias
    ``_p = self.store.put``, and ``transaction() + _write_record`` all bypass it
    while the whole suite stays green. It is kept only as a cheap first line --
    ``test_prefetch_is_written_exactly_once_per_entry_call`` is the guard that
    actually has to hold, because it observes behaviour rather than syntax.
    """

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    call_sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "put"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "PREFETCH_RECORD_KIND"
    ]
    assert len(call_sites) == 1, f"expected one prefetch write site, found {len(call_sites)}"


def test_prefetch_is_written_exactly_once_per_entry_call(tmp_path: Path, monkeypatch) -> None:
    """PRIMARY guard: observes writes, so non-literal call forms cannot hide.

    Two assertions, chosen because measurement showed they cover *different*
    holes (a partition-filtered record count was measured to miss two of the
    bypass shapes below, so no partition filter is used):

    * ``seen`` catches an extra write of *any* kind made through **this store
      handle** -- including ``getattr(self.store, "put")`` and a bound alias
      ``_p = self.store.put``.
    * the record count catches a write of ``prefetch_record`` arriving from
      **anywhere**: another handle, another module, or ``transaction()`` +
      ``_write_record``.

    Measured open (each fires this test): ``getattr`` with and without
    ``partition=``, module-level alias ``_PUT = RecordStore.put``,
    ``transaction() + _write_record``, and an extra write of a different kind
    through the same handle.

    **Declared boundaries -- measured, not assumed:**

    1. A write in a code path this test never executes is invisible.
    2. A write of a *different* kind through a *different* handle is invisible
       (both assertions look at this handle or at this kind).
    3. A write made **outside** ``write_prefetch`` / ``execute_l2_action`` --
       e.g. another module writing ``prefetch_record`` during its own work -- is
       invisible, because this test only counts writes made while exercising
       these three calls. Measured by the falsifier: such a write in
       ``context_assembler.py`` left the full suite green, and would leave this
       guard green too. Guarding that needs an invariant at the store level, not
       a test in this module.
    """

    store = RecordStore(tmp_path / "guard.sqlite3")
    service = EvidencePrefetchService(store, bundles=StubBundles({"bundle-real"}))
    seen: list[str] = []
    real_put = store.put

    def counting_put(kind, record_id, value, **kwargs):
        seen.append(kind)
        return real_put(kind, record_id, value, **kwargs)

    monkeypatch.setattr(store, "put", counting_put)

    service.write_prefetch(action_level=1, query="q", candidates=["ev-1"])
    service.execute_l2_action(
        action_level=2,
        query="q",
        candidates=["ev-1"],
        bundle_id="bundle-real",
        action=lambda record: "ok",
    )
    service.execute_l2_action(action_level=3, query="q", candidates=[], action=lambda record: "no")

    assert seen == [PREFETCH_RECORD_KIND] * 3, f"unexpected writes through store.put: {seen}"
    assert len(store.list(PREFETCH_RECORD_KIND)) == 3, "more than one prefetch record per call"


def test_module_does_not_mint_a_run_identifier() -> None:
    """L-02 must reference K1's run id, never invent one.

    The no-import half is also what keeps this lane independently mergeable:
    ``run_manifest.py`` is owned by L-05 and is not in ``main``, so importing it
    would make this module unimportable on its own branch (the stacked-branch
    failure R-006 hit).
    """

    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }
    assert "run_manifest" not in imported
    assert "RunManifest" not in imported

    run_id_mints = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "new_id"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "run"
    ]
    assert run_id_mints == []

    record = PrefetchRecord(action_level=2, query="q", candidates=[], decision="blocked")
    assert record.run_id is None


def test_run_id_is_taken_from_the_manifest_not_generated(tmp_path: Path) -> None:
    """K1 integration point: the run id is *read* from the manifest."""

    class StubManifest:
        """Mirrors the K1 surface this module depends on: ``.run_id``."""

        run_id = "run_from_k1"

    service = _service(tmp_path, {"bundle-real"})
    record = service.write_prefetch_for_run(
        StubManifest(),
        action_level=2,
        query="q",
        candidates=["ev-1"],
        bundle_id="bundle-real",
    )
    assert record.run_id == "run_from_k1"
    stored = service.store.get(PREFETCH_RECORD_KIND, record.prefetch_id)
    assert stored is not None
    assert stored["run_id"] == "run_from_k1"

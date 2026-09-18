"""ADR-01 slot 14 / K11 is wired into the release path, and says which mode ran.

Before this wiring ``acl.py`` was a 379-line module with no production consumer:
the ``AccessPolicyStore`` existed, was tested in isolation, and was never asked
anything at runtime. The external release is the one action in this pipeline
that is both **irreversible** and **outward-facing**, so it is where an
authorization layer has real meaning -- the human approval recorded by the L4
gate is the *justification* for an elevated export, and the policy is the
*authorization* for it. K11-3 exists to keep those two apart.

The tests pin all three states, because a wiring that only has a "denies" case
can be satisfied by a layer that denies everything:

* access control off  -> released, **and the run says so** (stated mode);
* on, no policy       -> refused (K11-1 default deny);
* on, policy granted  -> released.
"""

from __future__ import annotations

from pathlib import Path

from autoresearch.acl import AccessPolicy, ResourceAction, ResourceKind
from autoresearch.application import AutoResearchApplication
from autoresearch.config import Settings
from autoresearch.contracts import (
    PaperRecord,
    ProjectCreate,
    ResumeRequest,
    RunRequest,
)

IDEA = "evidence gates for automated research pipelines"
REVIEWER = "alice"
SEED_PAPERS = [
    PaperRecord(
        project_id="proj",
        title=title,
        abstract=(
            "Evidence admission gates require traceable identifiers and provenance. "
            "Metric definitions must be registered before results are reported so "
            "that every number can be traced to a supporting evidence record."
        ),
        year=2024,
        source=source,
        source_record_id=f"seed-{index}",
        doi=f"10.1000/acl{index}",
    )
    for index, (title, source) in enumerate(
        [
            ("Evidence gates for automated research", "openalex"),
            ("Provenance-aware manuscript assembly", "semantic_scholar"),
            ("Traceable metric definitions in agent pipelines", "crossref"),
        ],
        start=1,
    )
]


def _runtime(tmp_path: Path, *, access_control: bool) -> AutoResearchApplication:
    repository_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="offline",
        AUTORESEARCH_DATA_DIR=tmp_path / "var",
        AUTORESEARCH_DB_PATH=tmp_path / "var" / "autoresearch.sqlite3",
        AUTORESEARCH_CHECKPOINT_PATH=tmp_path / "var" / "checkpoints.sqlite3",
        AUTORESEARCH_PROJECTS_DIR=tmp_path / "paper-projects",
        AUTORESEARCH_TEMPLATE_DIR=repository_root / "paper-projects" / "_template",
        AUTORESEARCH_NETWORK_ENABLED=False,
        AUTORESEARCH_ACCESS_CONTROL_ENABLED=access_control,
    )
    application = AutoResearchApplication(settings)
    application.create_project(ProjectCreate(project_id="proj", title="Demo", idea=IDEA))
    return application


def _park_at_release(application: AutoResearchApplication) -> dict:
    result = application.run(
        RunRequest(
            project_id="proj", idea=IDEA, seed_papers=SEED_PAPERS, request_release=True
        )
    )
    assert result["state"]["lifecycle_state"] in {"release_pending", "RELEASE_PENDING"}, (
        "the run must reach the human gate before the authorization layer is exercised"
    )
    return result["state"]


def _resume(application: AutoResearchApplication, run_id: str) -> dict:
    return application.resume(
        run_id, ResumeRequest(approval=True, reviewer=REVIEWER)
    )["state"]


def test_without_access_control_the_release_states_that_no_policy_was_checked(tmp_path):
    """Off is a *stated* mode, not a silent pass.

    If this were implicit, "K11 is wired" and "K11 is not wired" would produce
    indistinguishable run records — which is how an absent control layer gets
    mistaken for a satisfied one.
    """
    application = _runtime(tmp_path, access_control=False)
    try:
        state = _park_at_release(application)
        after = _resume(application, state["run_id"])
    finally:
        application.close()

    assert after["lifecycle_state"] in {"released", "RELEASED"}
    assert any(
        "access control is not enabled" in warning for warning in after["warnings"]
    ), after["warnings"]


def test_a_release_with_no_policy_is_refused(tmp_path):
    """K11-1 default deny, and this is the criterion test for the wiring.

    On the pre-wiring code the release succeeded here: nothing consulted the
    policy store, so the assertion below failed on ``lifecycle_state``. The
    refusal must also name *who* was refused and *what* they were refused —
    a denial an operator cannot attribute is not usable evidence.
    """
    application = _runtime(tmp_path, access_control=True)
    try:
        state = _park_at_release(application)
        after = _resume(application, state["run_id"])
    finally:
        application.close()

    assert after["lifecycle_state"] in {"release_pending", "RELEASE_PENDING"}, (
        "an unauthorized release must not complete"
    )
    refusals = [b for b in after["blockers"] if "access policy" in b]
    assert refusals, after["blockers"]
    assert "no_policy" in refusals[0]
    assert REVIEWER in refusals[0]
    assert state["manuscript_id"] in refusals[0]


def test_a_granted_export_policy_lets_the_release_through(tmp_path):
    """The other half of the criterion: the layer refuses unauthorized releases
    *and* permits authorized ones. Without this, "deny everything" would pass."""
    application = _runtime(tmp_path, access_control=True)
    try:
        state = _park_at_release(application)
        assert application.access_policy is not None
        application.access_policy.grant(
            AccessPolicy(
                subject=REVIEWER,
                resource_kind=ResourceKind.ARTIFACT,
                resource_id=state["manuscript_id"],
                actions=[ResourceAction.EXPORT],
                granted=True,
            ),
            justification="external release approved by the project owner",
        )
        after = _resume(application, state["run_id"])
    finally:
        application.close()

    assert after["lifecycle_state"] in {"released", "RELEASED"}, after["blockers"]
    assert not [b for b in after["blockers"] if "access policy" in b]


def test_an_ungranted_policy_does_not_count_as_authorization(tmp_path):
    """``granted=False`` is a stored row, not a permission.

    A policy that merely *exists* must not authorize anything; treating presence
    as consent is how a revocation gets silently ignored.
    """
    application = _runtime(tmp_path, access_control=True)
    try:
        state = _park_at_release(application)
        assert application.access_policy is not None
        application.access_policy.grant(
            AccessPolicy(
                subject=REVIEWER,
                resource_kind=ResourceKind.ARTIFACT,
                resource_id=state["manuscript_id"],
                actions=[ResourceAction.EXPORT],
                granted=False,
            )
        )
        after = _resume(application, state["run_id"])
    finally:
        application.close()

    refusals = [b for b in after["blockers"] if "access policy" in b]
    assert refusals, after["blockers"]
    assert "policy_not_granted" in refusals[0]

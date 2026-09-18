"""M05-06 retraction / correction / access-basis tests (K10).

Offline only: every Crossref interaction goes through an ``httpx.MockTransport``
or a recorded fixture. No request leaves the process -- and
``test_retraction_module_cannot_issue_network_requests`` fails the build if
``retraction.py`` ever gains a way to.

The recorded payloads in ``tests/fixtures/m05_retraction/`` are real live
Crossref responses captured 2026-09-15 (see the fixture's ``_provenance``); the
two Lancet records were re-captured on that date and agree with B5's fixture on
the relation arrays, which is what makes the direction assertions below
evidence rather than a restatement of the implementation.
"""

from __future__ import annotations

import ast
import json
from enum import StrEnum
from pathlib import Path

import httpx
import pytest

from autoresearch import retraction as retraction_module
from autoresearch.external_sources import (
    AccessStatus,
    CrossrefAdapter,
    CrossrefClient,
    LicenceVerdict,
    SourceSnapshot,
    SourceStatus,
    TransportOutcome,
    _is_open_licence_url,
)
from autoresearch.retraction import (
    K8_MODULE,
    K8_REASONS,
    PERMANENT_BLOCK_REASONS,
    SOURCE_STATUS_TO_RETRACTION,
    InvalidationSink,
    K8InvalidationAdapter,
    K8UnavailableError,
    PaywallBypassRefused,
    PropagationContext,
    PropagationContractMismatchError,
    PropagationRequiredError,
    RetractionChecker,
    RetractionStatus,
    UnmappedPropagationReasonError,
    UnmappedSourceStatusError,
    k8_action_for,
    retraction_status_for,
)

M05_FIXTURES = Path(__file__).parent / "fixtures" / "m05_retraction"
B5_FIXTURES = Path(__file__).parent / "fixtures" / "external_sources"

# The retracted 1998 article and the 2010 notice that retracted it are distinct
# works and must never be conflated (real DOIs, real payloads).
RETRACTED_ARTICLE = "10.1016/S0140-6736(97)11096-0"
RETRACTION_NOTICE = "10.1016/S0140-6736(10)60175-4"
NORMAL_ARTICLE = "10.1038/s41586-025-10072-4"
OPEN_WORK = "10.1371/journal.pone.0000308"  # PLOS ONE, CC-BY
SPRINGER_TDM_WORK = "10.1038/nature12373"
WILEY_EMBARGOED_WORK = "10.1002/asi.4630260504"


def _fixture(name: str) -> dict:
    return json.loads((M05_FIXTURES / name).read_text(encoding="utf-8"))


def _responses() -> dict:
    """M05's real captures merged with B5's (adds the notice and a normal work)."""

    merged = json.loads((B5_FIXTURES / "crossref_responses.json").read_text(encoding="utf-8"))
    merged.update({k: v for k, v in _fixture("crossref_responses.json").items() if k[0] != "_"})
    return merged


def _message(doi: str) -> dict:
    return json.loads(json.dumps(_responses()[doi]["body"]["message"]))


def _transport(mapping: dict | None = None) -> httpx.MockTransport:
    table = _responses() if mapping is None else mapping

    def handler(request: httpx.Request) -> httpx.Response:
        entry = table.get(request.url.path.removeprefix("/works/"))
        if entry is None:
            return httpx.Response(404, json={"status": "not_found"})
        status = entry.get("status", 200)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json=entry["body"])

    return httpx.MockTransport(handler)


def _adapter(mapping: dict | None = None) -> CrossrefAdapter:
    return CrossrefAdapter(client=CrossrefClient(transport=_transport(mapping)))


class _RaisingTransport(httpx.BaseTransport):
    def __init__(self, error: Exception):
        self.error = error

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise self.error


class RecordingSink:
    """Stand-in for L-02's K8 sink; records the exact call shape."""

    implements_retraction_sink = True

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def propagate(
        self,
        *,
        source_evidence_id: str,
        reason: str,
        affected_claims: tuple[str, ...],
        affected_gates: tuple[str, ...],
        action: str,
    ) -> object:
        call = {
            "source_evidence_id": source_evidence_id,
            "reason": reason,
            "affected_claims": affected_claims,
            "affected_gates": affected_gates,
            "action": action,
        }
        self.calls.append(call)
        return {"propagation_id": f"prop-{len(self.calls)}"}


def _context(**overrides) -> PropagationContext:
    values = {
        "source_evidence_id": "ev-1",
        "affected_claims": ("cl-1", "cl-2"),
        "affected_gates": ("gate-a",),
    }
    values.update(overrides)
    return PropagationContext(**values)


# ---------------------------------------------------------------------------
# K10 shape
# ---------------------------------------------------------------------------


def test_k10_enum_matches_the_frozen_contract():
    assert {member.name: member.value for member in RetractionStatus} == {
        "ACTIVE": "active",
        "RETRACTED": "retracted",
        "CORRECTED": "corrected",
        "UNAVAILABLE": "unavailable",
    }


def test_only_an_explicit_found_projects_to_active():
    """K10-1 as a total mapping: every non-``found`` status has a non-ACTIVE image."""

    assert set(SOURCE_STATUS_TO_RETRACTION) == set(SourceStatus)
    active_images = {
        status
        for status, projected in SOURCE_STATUS_TO_RETRACTION.items()
        if projected is RetractionStatus.ACTIVE
    }
    assert active_images == {SourceStatus.FOUND}


def test_unmapped_source_status_raises_instead_of_defaulting_to_active():
    """A status K10 cannot express must fail loudly -- never fall back to "fine"."""

    class _Novel(StrEnum):
        INVENTED = "invented"

    with pytest.raises(UnmappedSourceStatusError):
        retraction_status_for(_Novel.INVENTED)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# N-4: recorded payloads, relation direction
# ---------------------------------------------------------------------------


def test_recaptured_payload_agrees_with_b5_on_the_relation_arrays():
    """The live re-capture and B5's fixture must describe the same relations.

    Without this, the direction tests below would only be checking my code
    against my own fixture.
    """

    b5 = json.loads((B5_FIXTURES / "crossref_responses.json").read_text(encoding="utf-8"))
    for doi in (RETRACTED_ARTICLE, RETRACTION_NOTICE):
        mine = _message(doi)
        theirs = b5[doi]["body"]["message"]
        for key in ("updated-by", "update-to"):
            assert mine.get(key) == theirs.get(key), f"{doi} {key} drifted"


def test_recorded_retracted_article_resolves_retracted_not_active():
    check = RetractionChecker(adapter=_adapter()).classify(RETRACTED_ARTICLE)
    assert check.status is RetractionStatus.RETRACTED
    assert check.source_status is SourceStatus.RETRACTED
    assert check.confirmed_active is False
    assert check.needs_propagation is True
    assert RETRACTION_NOTICE.casefold() in [d.casefold() for d in check.related_dois]


def test_recorded_retraction_notice_resolves_active():
    """The notice is a published, citable work: it is not itself retracted."""

    check = RetractionChecker(adapter=_adapter()).classify(RETRACTION_NOTICE)
    assert check.status is RetractionStatus.ACTIVE
    assert check.source_status is SourceStatus.FOUND
    assert check.confirmed_active is True


def test_recorded_payload_puts_the_retraction_in_updated_by_only():
    """The real payload's direction, asserted on the payload itself.

    A retracted article carries the retraction in ``updated-by[]`` (the works
    that updated it) and no ``update-to[]``; the notice is the mirror image.
    Reading the wrong array inverts both verdicts -- B5's original defect.
    """

    article = _message(RETRACTED_ARTICLE)
    notice = _message(RETRACTION_NOTICE)
    assert [item["type"] for item in article["updated-by"]] == ["correction", "retraction"]
    assert "update-to" not in article
    assert [item["type"] for item in notice["update-to"]] == ["retraction"]
    assert "updated-by" not in notice


def test_relation_direction_is_load_bearing_swapping_the_arrays_flips_the_verdict():
    """Counterfactual: the direction is not cosmetic.

    Swap ``updated-by[]`` and ``update-to[]`` on the recorded retracted article
    and it resolves ``found`` -- i.e. it becomes ``ACTIVE``. That is exactly
    what B5's inverted criterion produced, and it is what K10-1 exists to keep
    out of the retraction axis. If the criterion ever moved to ``update-to[]``,
    this assertion fails.
    """

    real = _message(RETRACTED_ARTICLE)
    swapped = {k: v for k, v in real.items() if k not in {"updated-by", "update-to"}}
    swapped["updated-by"] = real.get("update-to", [])
    swapped["update-to"] = real["updated-by"]

    adapter = _adapter()
    assert adapter.verdict_from_message(RETRACTED_ARTICLE, real).status is SourceStatus.RETRACTED
    flipped = adapter.verdict_from_message(RETRACTED_ARTICLE, swapped)
    assert flipped.status is SourceStatus.FOUND
    assert (
        retraction_status_for(flipped.status) is RetractionStatus.ACTIVE
    ), "the inverted reading would have published a retracted paper as active"


# ---------------------------------------------------------------------------
# N-1: UNAVAILABLE is never ACTIVE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("network unreachable"), httpx.TimeoutException("timed out")],
    ids=["connect-error", "timeout"],
)
def test_network_failure_is_unavailable_never_active(error):
    adapter = CrossrefAdapter(client=CrossrefClient(transport=_RaisingTransport(error)))
    check = RetractionChecker(adapter=adapter).classify("10.1000/unreachable")
    assert check.status is RetractionStatus.UNAVAILABLE
    assert check.status is not RetractionStatus.ACTIVE
    assert check.confirmed_active is False
    assert check.source_status is SourceStatus.UNKNOWN
    assert check.transport is not TransportOutcome.OK


@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
def test_permission_and_server_refusals_are_unavailable_never_active(status_code):
    """A refusal to serve us says nothing about whether the work is retracted."""

    check = RetractionChecker(
        adapter=_adapter({"10.1000/denied": {"status": status_code}})
    ).classify("10.1000/denied")
    assert check.status is RetractionStatus.UNAVAILABLE
    assert check.confirmed_active is False


def test_rate_limiting_is_unavailable_never_active():
    check = RetractionChecker(adapter=_adapter({NORMAL_ARTICLE: {"status": 429}})).classify(
        NORMAL_ARTICLE
    )
    assert check.status is RetractionStatus.UNAVAILABLE
    assert check.transport is TransportOutcome.RATE_LIMITED


def test_a_doi_that_does_not_resolve_is_unavailable_never_active():
    """A 404 is decisive, and what it decides is *not* "the work is fine"."""

    check = RetractionChecker(adapter=_adapter({})).classify("10.1000/does-not-exist")
    assert check.status is RetractionStatus.UNAVAILABLE
    assert check.source_status is SourceStatus.NOT_FOUND
    assert check.confirmed_active is False
    assert any("404" in reason for reason in check.reasons)


def test_an_unexpected_resolver_exception_is_unavailable_never_active():
    class _Exploding(CrossrefAdapter):
        def resolve(self, doi: str):
            raise RuntimeError("socket layer exploded")

    check = RetractionChecker(adapter=_Exploding()).classify("10.1000/whatever")
    assert check.status is RetractionStatus.UNAVAILABLE
    assert check.confirmed_active is False
    assert "RuntimeError" in check.reasons[0]


def test_an_unavailable_work_needs_no_sink_and_propagates_nothing():
    sink = RecordingSink()
    checker = RetractionChecker(adapter=_adapter({}), sink=sink)
    check = checker.check("10.1000/does-not-exist", context=_context())
    assert check.status is RetractionStatus.UNAVAILABLE
    assert sink.calls == []
    assert check.propagation is None


def test_not_found_and_unknown_merge_at_the_projection_layer_only():
    """Owner ruling on D-M05-01: the projection may merge, the audit record may not.

    K10 is a frozen four-value enum with no ``not_found``, so a decisive 404 and
    a transport failure both project to ``UNAVAILABLE``. That coarseness is
    correct at the contract boundary -- the alternative (404 -> ``ACTIVE``) is
    what K10-1 exists to forbid -- but the two facts must stay distinguishable,
    or an auditor can no longer tell "this DOI does not exist" from "we could
    not reach Crossref". Losing ``source_status`` here would be silent: every
    other test in this file would still pass.
    """

    merged = {
        status
        for status, projected in SOURCE_STATUS_TO_RETRACTION.items()
        if projected is RetractionStatus.UNAVAILABLE
    }
    assert merged == {SourceStatus.NOT_FOUND, SourceStatus.UNKNOWN}

    not_found = RetractionChecker(adapter=_adapter({})).classify("10.1000/does-not-exist")
    unknown = RetractionChecker(adapter=_adapter({NORMAL_ARTICLE: {"status": 429}})).classify(
        NORMAL_ARTICLE
    )

    # Projection layer: deliberately merged onto one frozen contract value.
    assert not_found.status is RetractionStatus.UNAVAILABLE
    assert unknown.status is RetractionStatus.UNAVAILABLE
    assert not_found.status is unknown.status
    assert not_found.confirmed_active is unknown.confirmed_active is False

    # Audit layer: NOT merged. This is what a reviewer must be able to read.
    assert not_found.source_status is SourceStatus.NOT_FOUND
    assert unknown.source_status is SourceStatus.UNKNOWN
    assert not_found.source_status is not unknown.source_status
    assert not_found.reasons != unknown.reasons


def test_active_with_a_degraded_transport_is_flagged():
    """``ACTIVE`` does not imply "reachable today" (owner hardening, D-M05-02).

    A live lookup that fails falls back to an offline snapshot, which may say
    ``found`` -- so the status is ``ACTIVE`` while nothing about today's
    availability was confirmed. Callers needing freshness must be able to see
    that from ``transport_degraded`` alone.
    """

    snapshot = SourceSnapshot(
        version="m05-test",
        records=[
            {
                "doi": NORMAL_ARTICLE,
                "title": "recorded earlier",
                "status": SourceStatus.FOUND,
            }
        ],
    )
    adapter = CrossrefAdapter(
        client=CrossrefClient(transport=_transport({NORMAL_ARTICLE: {"status": 429}})),
        snapshot=snapshot,
    )
    check = RetractionChecker(adapter=adapter).classify(NORMAL_ARTICLE)
    assert check.status is RetractionStatus.ACTIVE
    assert check.source_status is SourceStatus.FOUND
    assert check.transport_degraded is True

    fresh = RetractionChecker(adapter=_adapter()).classify(NORMAL_ARTICLE)
    assert fresh.status is RetractionStatus.ACTIVE
    assert fresh.transport_degraded is False


# ---------------------------------------------------------------------------
# N-2: RETRACTED propagates to K8, not just a status flag
# ---------------------------------------------------------------------------


def test_retracted_triggers_k8_propagation():
    sink = RecordingSink()
    checker = RetractionChecker(adapter=_adapter(), sink=sink)
    check = checker.check(RETRACTED_ARTICLE, context=_context())

    assert check.status is RetractionStatus.RETRACTED
    assert len(sink.calls) == 1
    assert sink.calls[0] == {
        "source_evidence_id": "ev-1",
        "reason": "retracted",
        "affected_claims": ("cl-1", "cl-2"),
        "affected_gates": ("gate-a",),
        "action": "recompute",
    }
    assert check.propagation == {"propagation_id": "prop-1"}


def test_an_active_work_propagates_nothing():
    sink = RecordingSink()
    check = RetractionChecker(adapter=_adapter(), sink=sink).check(
        NORMAL_ARTICLE, context=_context()
    )
    assert check.status is RetractionStatus.ACTIVE
    assert sink.calls == []


def test_a_corrected_work_does_not_propagate():
    """K10-2 names ``RETRACTED`` only, and K8 has no ``corrected`` reason.

    Registered as a deliberate boundary rather than an oversight: the contract
    does not put a correction on the invalidation path, so this lane must not
    invent one.
    """

    # Derived from the recorded payload: the real article carries a correction
    # *and* a retraction, so the retraction entry is filtered out to reach the
    # corrected-only shape.
    message = _message(RETRACTED_ARTICLE)
    message["updated-by"] = [
        item for item in message["updated-by"] if item["type"] == "correction"
    ]
    mapping = {
        RETRACTED_ARTICLE: {"status": 200, "body": {"status": "ok", "message": message}}
    }
    sink = RecordingSink()
    check = RetractionChecker(adapter=_adapter(mapping), sink=sink).check(
        RETRACTED_ARTICLE, context=_context()
    )
    assert check.status is RetractionStatus.CORRECTED
    assert check.needs_propagation is False
    assert sink.calls == []


def test_a_retraction_without_a_wired_sink_is_refused():
    """Reporting ``RETRACTED`` while nothing propagated is the defect, not the fix."""

    checker = RetractionChecker(adapter=_adapter())
    with pytest.raises(PropagationRequiredError, match="no invalidation sink"):
        checker.check(RETRACTED_ARTICLE, context=_context())


def test_the_claim_set_is_left_to_the_k8_owner():
    """D1: this module must not demand a claim set it cannot know.

    K8-2 makes the evidence -> claim -> gate walk the K8 owner's job, because
    only the graph knows those relations. An empty claim set must therefore
    *reach* the sink and be judged there (K8-3), by the side that can actually
    perform the walk. Rejecting it here is what forced callers to invent facts
    about a graph this module cannot see.
    """

    class _BrokenChainSink:
        implements_retraction_sink = True

        def propagate(
            self,
            *,
            source_evidence_id: str,
            reason: str,
            affected_claims: tuple[str, ...],
            affected_gates: tuple[str, ...],
            action: str,
        ) -> object:
            raise RuntimeError("K8-3: the invalidation reached no claim")

    checker = RetractionChecker(adapter=_adapter(), sink=_BrokenChainSink())
    with pytest.raises(RuntimeError, match="K8-3"):
        checker.check(
            RETRACTED_ARTICLE, context=PropagationContext(source_evidence_id="ev-1")
        )


def test_a_retraction_without_a_source_evidence_id_is_refused():
    checker = RetractionChecker(adapter=_adapter(), sink=RecordingSink())
    with pytest.raises(PropagationRequiredError, match="source_evidence_id"):
        checker.check(RETRACTED_ARTICLE, context=_context(source_evidence_id=""))


def test_k8_permanent_block_reasons_cannot_be_downgraded():
    assert {"forged", "paywall_bypass", "unapproved_egress"} == PERMANENT_BLOCK_REASONS
    for reason in PERMANENT_BLOCK_REASONS:
        assert k8_action_for(reason) == "permanent_block"
    assert k8_action_for("retracted") == "recompute"
    assert k8_action_for("expired") == "recompute"
    with pytest.raises(UnmappedPropagationReasonError):
        k8_action_for("a-reason-nobody-froze")


# ---------------------------------------------------------------------------
# M05-06: OA / licence / unavailable must be distinguishable
# ---------------------------------------------------------------------------


def test_access_basis_separates_open_from_restricted():
    adapter = _adapter()
    assert adapter.licence(OPEN_WORK).status is AccessStatus.OPEN
    assert adapter.licence(OPEN_WORK).open_access is True
    assert adapter.licence(SPRINGER_TDM_WORK).status is AccessStatus.RESTRICTED
    assert adapter.licence(RETRACTED_ARTICLE).status is AccessStatus.RESTRICTED


def test_a_recorded_licence_is_not_automatically_open_access():
    """Both recorded subscription payloads *do* carry a ``license[]`` entry.

    Elsevier ships a text-and-data-mining user licence and Springer ships
    ``.../tdm``. Reading "a licence exists" as open access would have handed out
    both paywalled works -- the same collapse as reading "unknown" as "fine".
    """

    verdict = _adapter().licence(SPRINGER_TDM_WORK)
    assert verdict.status is AccessStatus.RESTRICTED
    assert verdict.content_versions == ["tdm"]
    assert any("text-and-data-mining" in reason for reason in verdict.reasons)


def test_a_permissive_url_under_tdm_terms_is_not_open_access():
    """Derived payload (not a capture): a CC URL under ``content-version=tdm``.

    The recorded TDM payloads have non-permissive URLs, so this synthetic one
    is the only way to exercise the ``tdm`` veto on its own. Disclosed as
    derived because it is not a real response.
    """

    message = _message(OPEN_WORK)
    message["license"] = [
        {"URL": "http://creativecommons.org/licenses/by/4.0/", "content-version": "tdm"}
    ]
    verdict = _adapter().licence(OPEN_WORK, message=message)
    assert verdict.status is AccessStatus.RESTRICTED
    assert any("not a reading basis" in reason for reason in verdict.reasons)


def test_missing_licence_metadata_is_unavailable_not_open():
    """Derived payload: no ``license[]`` at all. Absence is not permission."""

    message = _message(OPEN_WORK)
    message.pop("license")
    verdict = _adapter().licence(OPEN_WORK, message=message)
    assert verdict.status is AccessStatus.UNAVAILABLE
    assert verdict.open_access is False
    assert any("no license[] metadata" in reason for reason in verdict.reasons)


def test_a_failed_licence_lookup_is_unavailable_not_open():
    adapter = CrossrefAdapter(
        client=CrossrefClient(transport=_RaisingTransport(httpx.ConnectError("down")))
    )
    verdict = adapter.licence(OPEN_WORK)
    assert verdict.status is AccessStatus.UNAVAILABLE
    assert verdict.transport is not TransportOutcome.OK
    assert verdict.open_access is False


def test_a_refused_licence_lookup_is_unavailable_not_open():
    adapter = _adapter({OPEN_WORK: {"status": 403}})
    verdict = adapter.licence(OPEN_WORK)
    assert verdict.status is AccessStatus.UNAVAILABLE
    assert verdict.open_access is False


def test_a_licence_lookup_without_a_client_is_unavailable_not_open():
    verdict = CrossrefAdapter().licence(OPEN_WORK)
    assert verdict.status is AccessStatus.UNAVAILABLE
    assert verdict.open_access is False


def test_a_nonexistent_doi_has_no_stated_access_basis():
    verdict = _adapter({}).licence("10.1000/does-not-exist")
    assert verdict.status is AccessStatus.UNAVAILABLE
    assert any("404" in reason for reason in verdict.reasons)


def test_an_embargo_is_recorded_as_a_reason_without_becoming_open():
    """A real Wiley payload carries ``delay-in-days``; it must not vanish."""

    verdict = _adapter().licence(WILEY_EMBARGOED_WORK)
    assert verdict.status is AccessStatus.RESTRICTED
    assert any("delay-in-days" in reason for reason in verdict.reasons)


# ---------------------------------------------------------------------------
# `_is_open_licence_url` must match on host + path, never on a substring.
#
# The discriminating property of this test set: the three forged forms below
# (marker in path, marker in query, domain that merely *ends* in the marker
# host) all returned True under the old ``marker in url.casefold()`` substring
# matching -- i.e. a forged URL smuggled an "open licence" past the gate. The
# urlparse fix makes each of them return False. Run against the unfixed version
# to confirm at least 4 of these fail (3 forged + the protocol-relative / no
# scheme cases); against the fixed version all 15 pass.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # 5 positives: absolute http(s) URLs on creativecommons.org whose path
        # begins with /licenses/ or /publicdomain/, including upper-case forms.
        "https://creativecommons.org/licenses/by/4.0/",
        "http://creativecommons.org/licenses/by/4.0/",
        "https://creativecommons.org/publicdomain/zero/1.0/",
        "HTTPS://CREATIVECOMMONS.ORG/LICENSES/BY/4.0/",
        "https://CreativeCommons.org/PublicDomain/zero/1.0/",
    ],
)
def test_open_licence_url_accepts_genuine_cc_landing_pages(url):
    assert _is_open_licence_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # 10 negatives. Each is something a substring matcher would wrongly
        # accept (or that must fail closed by construction).
        # forged: marker sits in the *path* of an unrelated host
        "https://example.com/creativecommons.org/licenses/by/4.0/",
        # forged: marker sits in the *query* of an unrelated host
        "https://evil.test/?next=creativecommons.org/licenses/by/4.0",
        # forged: domain only *ends with* the marker host, not equal
        "https://notcreativecommons.org/licenses/by/4.0/",
        # ordinary commercial licence page, never permissive
        "https://www.elsevier.com/tdm/userlicense/1.0/",
        # genuine CC host but a non-licence path
        "https://creativecommons.org/about/",
        # bare string with no scheme at all
        "creativecommons.org/licenses/by/4.0/",
        # empty string: not a URL
        "",
        # protocol-relative URL: no scheme -> fail closed
        "//creativecommons.org/licenses/by/4.0/",
        # wrong scheme entirely
        "ftp://creativecommons.org/licenses/by/4.0/",
        # subdomain of the marker host, not the host itself
        "https://api.creativecommons.org/licenses/by/4.0/",
    ],
)
def test_open_licence_url_rejects_non_cc_or_forged_urls(url):
    assert _is_open_licence_url(url) is False


# ---------------------------------------------------------------------------
# N-3: bypassing a paywall is refused
# ---------------------------------------------------------------------------


def test_bypassing_a_paywall_is_refused():
    checker = RetractionChecker(adapter=_adapter())
    with pytest.raises(PaywallBypassRefused, match="not a retrieval mode"):
        checker.decide_retrieval(SPRINGER_TDM_WORK, bypass_paywall=True)


def test_bypass_is_refused_even_for_an_open_work():
    """The mode itself is invalid, so the licence state cannot authorise it."""

    checker = RetractionChecker(adapter=_adapter())
    with pytest.raises(PaywallBypassRefused):
        checker.decide_retrieval(OPEN_WORK, bypass_paywall=True)


def test_a_restricted_work_is_not_granted():
    decision = RetractionChecker(adapter=_adapter()).decide_retrieval(SPRINGER_TDM_WORK)
    assert decision.granted is False
    assert decision.access is AccessStatus.RESTRICTED
    assert decision.basis == "restricted"


def test_an_unavailable_work_is_not_granted():
    decision = RetractionChecker(adapter=_adapter({OPEN_WORK: {"status": 429}})).decide_retrieval(
        OPEN_WORK
    )
    assert decision.granted is False
    assert decision.access is AccessStatus.UNAVAILABLE
    assert decision.basis == "unavailable"


def test_an_open_work_is_granted():
    decision = RetractionChecker(adapter=_adapter()).decide_retrieval(OPEN_WORK)
    assert decision.granted is True
    assert decision.basis == "open_licence"


def test_a_bypass_attempt_is_recorded_as_a_permanent_block():
    """K8 pins ``paywall_bypass`` to ``permanent_block`` and it may not be waived."""

    sink = RecordingSink()
    checker = RetractionChecker(adapter=_adapter(), sink=sink)
    with pytest.raises(PaywallBypassRefused):
        checker.decide_retrieval(
            SPRINGER_TDM_WORK, bypass_paywall=True, context=_context(source_evidence_id="ev-9")
        )
    assert len(sink.calls) == 1
    assert sink.calls[0]["reason"] == "paywall_bypass"
    assert sink.calls[0]["action"] == "permanent_block"
    assert sink.calls[0]["source_evidence_id"] == "ev-9"


# ---------------------------------------------------------------------------
# Structural guarantees
# ---------------------------------------------------------------------------

RETRACTION_SOURCE = Path(__file__).parents[1] / "src" / "autoresearch" / "retraction.py"


def _tree() -> ast.Module:
    return ast.parse(RETRACTION_SOURCE.read_text(encoding="utf-8"))


def test_retraction_module_cannot_issue_network_requests():
    """The offline guarantee is structural, not a convention about the tests."""

    tree = _tree()
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "httpx" not in imported

    constructed = [
        node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
    assert "CrossrefClient" not in constructed


def test_retraction_module_does_not_re_read_the_relation_arrays():
    """K10-3: reuse B5's criterion. A second reader of it is a second truth.

    Docstrings are excluded so the rule bites on executable literals only.
    """

    tree = _tree()
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))

    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }
    assert "updated-by" not in literals
    assert "update-to" not in literals
    assert "license" not in literals


# ---------------------------------------------------------------------------
# Cross-lane seam: L-02's K8 ``invalidation.py``
#
# ``invalidation.py`` is L-02's exclusive file and is NOT on this lane's base
# (``main@8dd8780``), so these tests skip here and run once L-02 merges. The skip
# is deliberate and greppable -- ``grep -n importorskip tests/test_m05_retraction.py``
# -- and **at merge the ``importorskip`` calls must be deleted**, so a regression
# in the seam cannot skip its way to green forever. Evidence for today is the
# merged-tree run recorded in L3 §5.5.
# ---------------------------------------------------------------------------

L02_ABSENT = (
    "autoresearch.invalidation (L-02's K8 owner) is not in this lane's base; "
    "these tests activate when L-02 merges -- see L3 §5.5"
)


def _k8():
    return pytest.importorskip("autoresearch.invalidation", reason=L02_ABSENT)


def _wired_service(tmp_path, evidence_id: str):
    """A real ``InvalidationService`` with a real evidence -> claim -> gate edge."""

    from autoresearch.contracts import GraphEdge, GraphEdgeKind, KnowledgePartition
    from autoresearch.storage import RecordStore

    invalidation = _k8()
    service = invalidation.InvalidationService(RecordStore(tmp_path / "k8.sqlite3"))
    service.store.put(
        "graph_edge",
        "e1",
        GraphEdge(
            partition=KnowledgePartition.PAPERS,
            source_id="claim_alpha",
            target_id="gate_release",
            relation=GraphEdgeKind.CITES,
            evidence_ids=[evidence_id],
        ),
        partition="papers",
    )
    return invalidation, service


def test_the_retraction_propagates_into_the_real_k8_service(tmp_path):
    """End-to-end: a ``RETRACTED`` verdict drives the real K8 service, and lands.

    This replaces an earlier assertion that ``isinstance(RecordingSink(),
    InvalidationSink)``. ``runtime_checkable`` Protocols check method *names*, not
    signatures, and ``RecordingSink`` is this file's own stub shaped to the port
    -- so its passing said nothing about L-02. Here the **real**
    ``InvalidationService`` is driven through ``K8InvalidationAdapter``.
    """

    invalidation, service = _wired_service(tmp_path, "ev-wakefield")
    sink = K8InvalidationAdapter(service)
    assert isinstance(sink, InvalidationSink)

    check = RetractionChecker(adapter=_adapter(), sink=sink).check(
        RETRACTED_ARTICLE, context=PropagationContext(source_evidence_id="ev-wakefield")
    )

    assert check.status is RetractionStatus.RETRACTED
    record = check.propagation
    assert record is not None
    assert record.source_evidence_id == "ev-wakefield"
    assert record.reason.value == "retracted"
    assert record.action.value == "recompute"
    # Derived by K8 from the graph -- not passed in by this lane.
    assert record.affected_claims == ["claim_alpha"]
    assert record.affected_gates == ["gate_release"]

    # The fact really landed in the store, under K8's own kind and partition.
    stored = service.store.list(
        invalidation.INVALIDATION_KIND, partition="invalidation"
    )
    assert len(stored) == 1
    assert stored[0]["propagation_id"] == record.propagation_id
    assert stored[0]["reason"] == "retracted"
    assert stored[0]["affected_claims"] == ["claim_alpha"]

    # ...and as an audit event, which is what makes it a propagated *fact*.
    with service.store.connection() as connection:
        events = connection.execute(
            "SELECT event_type, actor FROM audit_events WHERE event_type=?",
            ("invalidation.propagated",),
        ).fetchall()
    assert len(events) == 1
    assert events[0]["actor"] == "system"


def test_the_raw_k8_service_is_not_a_sink(tmp_path):
    """The reported trap, pinned on the **real** object rather than a stand-in.

    ``InvalidationService`` has a method called ``propagate`` but takes ``actor``
    in place of the assertion/action keywords, so it cannot serve as a sink. Both
    halves are asserted here: the discriminator says so, and the wiring guard
    refuses it with the fix in the message instead of failing mid-propagation.
    """

    _, service = _wired_service(tmp_path, "ev-1")
    assert not isinstance(service, InvalidationSink)
    with pytest.raises(PropagationRequiredError, match="K8InvalidationAdapter"):
        RetractionChecker(adapter=_adapter(), sink=service)
    assert isinstance(K8InvalidationAdapter(service), InvalidationSink)


def test_l04_and_l02_agree_on_the_k8_reason_domain_and_actions():
    """D2: one concept, two implementations -- so compare them, both directions.

    The domain check is two-sided on purpose: a table that is a strict subset of
    K8's would otherwise look exactly like one that matches.
    """

    invalidation = _k8()
    l02_reasons = {reason.value for reason in invalidation.InvalidationReason}
    assert l02_reasons == set(K8_REASONS)

    l02_permanent = {reason.value for reason in invalidation.PERMANENT_BLOCK_REASONS}
    assert l02_permanent == set(PERMANENT_BLOCK_REASONS)

    for reason in invalidation.InvalidationReason:
        assert k8_action_for(reason.value) == invalidation.action_for_reason(reason).value


def test_the_adapter_accepts_a_propagation_whose_assertions_match_the_graph(tmp_path):
    _, service = _wired_service(tmp_path, "ev-1")
    record = K8InvalidationAdapter(service).propagate(
        source_evidence_id="ev-1",
        reason="retracted",
        affected_claims=("claim_alpha",),
        affected_gates=("gate_release",),
        action="recompute",
    )
    assert record.affected_claims == ["claim_alpha"]


def test_the_adapter_verifies_an_assertion_against_what_the_graph_derived(tmp_path):
    """An asserted claim set is cross-checked, never forwarded as the input.

    The graph says ``claim_alpha``; asserting anything else means the caller and
    K8 disagree about the blast radius, which is a broken chain.
    """

    _, service = _wired_service(tmp_path, "ev-1")
    with pytest.raises(PropagationContractMismatchError, match="affected_claims"):
        K8InvalidationAdapter(service).propagate(
            source_evidence_id="ev-1",
            reason="retracted",
            affected_claims=("claim_somewhere_else",),
            affected_gates=(),
            action="recompute",
        )
    # The refusal is clean: nothing was recorded on the way to the error.
    with service.store.connection() as connection:
        rows = connection.execute("SELECT COUNT(*) AS n FROM records").fetchone()
    assert rows["n"] == 1  # only the graph edge


def test_the_adapter_refuses_an_action_that_disagrees_with_k8(tmp_path):
    """D2 caught live: an ``action`` disagreement is stale-table drift, not noise."""

    _, service = _wired_service(tmp_path, "ev-1")
    with pytest.raises(PropagationContractMismatchError, match="action disagreement"):
        K8InvalidationAdapter(service).propagate(
            source_evidence_id="ev-1",
            reason="paywall_bypass",
            affected_claims=(),
            affected_gates=(),
            action="recompute",  # K8-1 says permanent_block
        )


def test_the_adapter_carries_a_permanent_block_through(tmp_path):
    _, service = _wired_service(tmp_path, "ev-1")
    record = K8InvalidationAdapter(service).propagate(
        source_evidence_id="ev-1",
        reason="paywall_bypass",
        affected_claims=(),
        affected_gates=(),
        action="permanent_block",
    )
    assert record.reason.value == "paywall_bypass"
    assert record.action.value == "permanent_block"


def test_the_adapter_requires_the_two_step_plan_api():
    """No ``plan()`` means no pre-write check -- so refuse, don't check late."""

    _k8()
    adapter = K8InvalidationAdapter(object())  # a service with neither plan nor record
    with pytest.raises(K8UnavailableError, match="plan"):
        adapter.propagate(
            source_evidence_id="ev-1",
            reason="retracted",
            affected_claims=("claim_alpha",),
            affected_gates=(),
            action="recompute",
        )


def test_the_adapter_rejects_a_reason_outside_k8s_domain(tmp_path):
    _, service = _wired_service(tmp_path, "ev-1")
    with pytest.raises(UnmappedPropagationReasonError):
        K8InvalidationAdapter(service).propagate(
            source_evidence_id="ev-1",
            reason="a-reason-nobody-froze",
            affected_claims=(),
            affected_gates=(),
            action="recompute",
        )


def test_a_missing_k8_module_fails_loudly(monkeypatch):
    """The lazy import moves the failure to the point of use -- and names it.

    Runs on this lane's base too (no L-02 needed): the module is made absent by
    pointing the seam at a name that does not exist.
    """

    monkeypatch.setattr(retraction_module, "K8_MODULE", "autoresearch.no_such_k8_module")
    adapter = K8InvalidationAdapter(object())
    with pytest.raises(K8UnavailableError, match=K8_MODULE.split(".")[-1]):
        adapter.propagate(
            source_evidence_id="ev-1",
            reason="retracted",
            affected_claims=(),
            affected_gates=(),
            action="recompute",
        )


def test_the_port_rejects_a_sink_whose_propagate_has_the_wrong_shape():
    """``runtime_checkable`` checks member *names*, not signatures (P2 finding).

    A K8 service has a method called ``propagate`` with three different keywords,
    so a name-only check would green-light it and the first real call would raise
    a bare ``TypeError`` -- a trap with a green light on it. The port therefore
    declares one non-method member, and here it is exercised on both sides. This
    test needs no L-02 module: the wrong shape is reproduced locally.
    """

    class _ThreeArgSink:  # L-02's shape -- not this port's shape
        def propagate(
            self, *, source_evidence_id: str, reason: str, actor: str = "system"
        ) -> object:
            return None

    assert not isinstance(_ThreeArgSink(), InvalidationSink)
    assert isinstance(RecordingSink(), InvalidationSink)


def test_wiring_a_wrong_shaped_sink_is_refused_at_construction_time():
    """Fail at the wiring line, with the fix in the message.

    Without this guard the mistake surfaces as ``TypeError: ... unexpected
    keyword argument 'affected_claims'`` from inside the first propagation --
    naming the service rather than the wiring, and only once work is under way.
    """

    with pytest.raises(PropagationRequiredError, match="K8InvalidationAdapter"):
        RetractionChecker(adapter=_adapter(), sink=object())


def test_a_conforming_sink_must_declare_its_conformance():
    """The cost of the discriminator, pinned rather than left implicit.

    A sink with the *right* call shape but no declared marker is refused. That is
    a deliberate trade: a declared marker can produce a **false reject** (loud,
    at the wiring line, with the fix in the message) where a name-only check
    produced a **false accept** (a green light on a trap). Pinning it here keeps
    the trade-off visible instead of accidental.
    """

    class _UndeclaredSink:  # right shape, no marker
        def propagate(
            self,
            *,
            source_evidence_id: str,
            reason: str,
            affected_claims: tuple[str, ...],
            affected_gates: tuple[str, ...],
            action: str,
        ) -> object:
            return None

    assert not isinstance(_UndeclaredSink(), InvalidationSink)
    with pytest.raises(PropagationRequiredError, match="K8InvalidationAdapter"):
        RetractionChecker(adapter=_adapter(), sink=_UndeclaredSink())


def test_licence_verdict_is_the_shared_model():
    assert isinstance(_adapter().licence(OPEN_WORK), LicenceVerdict)

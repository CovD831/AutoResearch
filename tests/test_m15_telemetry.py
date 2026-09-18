"""K13 ``TelemetryPoint`` tests (M15-02/04) -- N-3 (unpriced cost is ``None``) + K13-3/K13-4.

The two negative examples this file owns:

* **N-3** -- a ``cost_usd`` point whose price table did not match keeps
  ``value is None``.  It is asserted with ``is None`` and explicitly *not* with
  ``== 0`` / ``== 0.0``.
* **N-4** -- writing a prompt / full text / token / secret is *refused*, so no
  original text can be persisted.

Plus the K13-1 discipline for every metric, not just cost: ``None`` and ``0``
must never collapse.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autoresearch.pii import SensitivityClass  # noqa: F401  (proves the modules coexist)
from autoresearch.telemetry import (
    DIMENSION_KEYS,
    MAX_DIMENSION_VALUE,
    REDACTED,
    Metric,
    TelemetryError,
    TelemetryInterrupt,
    TelemetryPoint,
    TelemetrySink,
    cost_usd_point,
    dimensions_for,
    doctor_diagnostics,
    redact_health_report,
    redact_value,
    run_id_of,
)

RUN = "run_0123456789abcdef"


def _point(
    metric: str = "latency_ms",
    *,
    value: float | None = 12.0,
    threshold: float | None = None,
    dimensions: dict[str, str] | None = None,
) -> TelemetryPoint:
    return TelemetryPoint(
        metric=metric,  # type: ignore[arg-type]
        dimensions=dimensions if dimensions is not None else {"run": RUN},
        value=value,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_metrics_and_dimension_whitelist_match_the_contract():
    assert {m.value for m in Metric} == {
        "blocked",
        "denied",
        "retry",
        "latency_ms",
        "cost_usd",
    }
    assert {"project", "run", "node", "agent", "gate"} == set(DIMENSION_KEYS)


# ---------------------------------------------------------------------------
# K13-1: value=None means NOT MEASURED -- for every metric
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metric", [m.value for m in Metric])
def test_unmeasured_value_stays_none_for_every_metric(metric: str):
    point = _point(metric, value=None)
    assert point.value is None
    assert point.value != 0
    assert point.measured is False


@pytest.mark.parametrize("metric", [m.value for m in Metric])
def test_zero_is_an_honest_measurement_and_differs_from_none(metric: str):
    measured_zero = _point(metric, value=0.0)
    unmeasured = _point(metric, value=None)
    assert measured_zero.value == 0.0
    assert measured_zero.measured is True
    assert unmeasured.value is None
    assert unmeasured.measured is False
    # the whole point: these two must never be interchangeable
    assert measured_zero.value != unmeasured.value


def test_a_point_cannot_default_its_way_into_a_zero():
    """``value`` has no default-at-0; omitting it is an explicit "not measured"."""
    from inspect import signature

    assert signature(TelemetryPoint).parameters["value"].default is None


# ---------------------------------------------------------------------------
# K13-2 / N-3: cost_usd with no matching price table
# ---------------------------------------------------------------------------


def test_unpriced_cost_is_none_never_zero():
    """N-3 core."""
    point = cost_usd_point(total=None, price_source=None, project="demo", run=RUN)
    assert point.metric is Metric.COST_USD
    assert point.value is None
    assert point.value != 0
    assert point.value != 0.0
    assert point.measured is False


def test_a_zero_total_with_a_price_source_is_a_real_zero():
    """The flip side: a genuinely free call *with* a price table is 0.0, not None."""
    point = cost_usd_point(total=0.0, price_source="models.dev@2026-09-01", run=RUN)
    assert point.value == 0.0
    assert point.measured is True


def test_a_missing_price_source_wins_over_a_present_total():
    """A total without a price table cannot be attributed to any rate -> unmeasured."""
    point = cost_usd_point(total=1.23, price_source=None, run=RUN)
    assert point.value is None


def test_cost_folds_attempts_in_as_the_upper_bound():
    point = cost_usd_point(
        total=0.25, price_source="models.dev@2026-09-01", attempts=4, run=RUN
    )
    assert point.value == pytest.approx(1.0)


def test_cost_rejects_an_impossible_attempt_count():
    with pytest.raises(TelemetryError):
        cost_usd_point(total=1.0, price_source="tbl", attempts=0, run=RUN)


def test_unpriced_cost_does_not_fire_a_threshold():
    """An unmeasured cost cannot breach a budget -- and must not be read as "ok"."""
    point = cost_usd_point(
        total=None, price_source=None, threshold=0.01, project="demo", run=RUN
    )
    assert point.value is None
    assert point.breaches_threshold is None  # unknown, NOT False
    assert point.breaches_threshold is not False


# ---------------------------------------------------------------------------
# K13-3 / N-4: no prompt, full text, token or secret can be recorded
# ---------------------------------------------------------------------------


def test_non_whitelisted_dimension_key_is_refused():
    for key in ("prompt", "full_text", "content", "tokens", "secret", "note"):
        with pytest.raises(ValidationError, match="dimensions may only use"):
            _point(dimensions={key: "whatever"})


def test_full_text_is_refused_by_length():
    with pytest.raises(ValidationError, match="never full text"):
        _point(dimensions={"gate": "x" * (MAX_DIMENSION_VALUE + 1)})


def test_multiline_content_is_refused():
    with pytest.raises(ValidationError, match="newline"):
        _point(dimensions={"gate": "line one\nline two"})


@pytest.mark.parametrize(
    "secret",
    [
        "sk-abcdefghijklmnop",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        "xoxb-1234567890-abcdefghij",
        "api_key=abcdef",
        "password: hunter2",
        "Bearer abcdefghijklmnop",
    ],
)
def test_secret_shaped_dimension_values_are_refused(secret: str):
    with pytest.raises(ValidationError, match="secret/token pattern"):
        _point(dimensions={"agent": secret})


def test_pii_shaped_dimension_values_are_refused():
    with pytest.raises(ValidationError, match="personal-data pattern"):
        _point(dimensions={"agent": "alice@example.com"})


def test_blank_and_non_string_dimension_values_are_refused():
    with pytest.raises(ValidationError, match="non-empty string"):
        _point(dimensions={"agent": "   "})
    with pytest.raises(ValidationError):
        _point(dimensions={"agent": 123})  # type: ignore[dict-item]


def test_redacted_false_is_refused_outright():
    """This module only emits redacted points -- there is no un-redacted mode."""
    with pytest.raises(ValidationError, match="only emits redacted points"):
        TelemetryPoint(metric=Metric.DENIED, dimensions={"run": RUN}, value=None, redacted=False)


def test_a_legitimate_point_is_redacted_by_default():
    assert _point().redacted is True


# ---------------------------------------------------------------------------
# K13-4: threshold breach triggers an interrupt
# ---------------------------------------------------------------------------


def test_above_threshold_interrupts_and_records_the_breach():
    sink = TelemetrySink()
    point = _point(value=250.0, threshold=200.0)
    with pytest.raises(TelemetryInterrupt) as excinfo:
        sink.record(point)
    assert point.breaches_threshold is True
    assert len(sink.breaches) == 1
    breach = sink.breaches[0]
    assert breach.point_id == point.point_id
    assert breach.value == 250.0
    assert breach.threshold == 200.0
    assert "breached threshold" in str(excinfo.value)
    # the point itself is still recorded -- an interrupt must not erase evidence
    assert sink.points == (point,)


def test_at_or_below_threshold_does_not_interrupt():
    sink = TelemetrySink()
    sink.record(_point(value=200.0, threshold=200.0))
    sink.record(_point(value=199.9, threshold=200.0))
    assert sink.breaches == ()
    assert sink.unmeasured == ()


def test_no_threshold_configured_is_not_a_breach():
    sink = TelemetrySink()
    point = sink.record(_point(value=1e9, threshold=None))
    assert point.breaches_threshold is False
    assert sink.breaches == ()


def test_threshold_with_an_unmeasured_value_is_a_gap_not_a_pass():
    """K13-1 + K13-4: an unmeasured alert is unknown -- recorded, not silently OK."""
    sink = TelemetrySink()
    point = sink.record(_point(value=None, threshold=200.0))
    assert point.breaches_threshold is None
    assert sink.breaches == ()
    assert sink.unmeasured == (point,)


def test_truthiness_would_be_wrong_so_the_sink_branches_explicitly():
    """A guard against a future ``if point.breaches_threshold:`` refactor.

    ``None`` is falsy, so a truthiness check would classify an *unmeasured*
    alert as healthy and drop it from both lists.
    """
    point = _point(value=None, threshold=1.0)
    assert bool(point.breaches_threshold) is False
    assert point.breaches_threshold is None  # ... but it is emphatically not False
    sink = TelemetrySink()
    sink.record(point)
    assert sink.unmeasured == (point,)
    assert point not in sink.points[:0]  # trivially true; kept for readability
    assert len(sink.points) == 1


def test_interrupt_can_be_disabled_for_batch_collection():
    sink = TelemetrySink(interrupt_on_breach=False)
    point = sink.record(_point(value=300.0, threshold=200.0))
    assert point.breaches_threshold is True
    assert len(sink.breaches) == 1


def test_record_all_collects_breaches_instead_of_stopping_at_the_first():
    sink = TelemetrySink()
    points = [
        _point(value=300.0, threshold=200.0),
        _point(value=10.0, threshold=200.0),
        _point(value=500.0, threshold=200.0),
    ]
    sink.record_all(points)
    assert len(sink.breaches) == 2
    assert len(sink.points) == 3


# ---------------------------------------------------------------------------
# K1 linkage (structural, no import)
# ---------------------------------------------------------------------------


def test_run_dimension_accepts_a_plain_run_id():
    assert dimensions_for(run=RUN) == {"run": RUN}
    assert run_id_of(RUN) == RUN


def test_run_dimension_accepts_any_object_exposing_run_id():
    """This is how a K1 ``RunManifest`` is consumed without importing it."""

    class FakeManifest:
        run_id = RUN

    assert run_id_of(FakeManifest()) == RUN
    assert dimensions_for(project="demo", run=FakeManifest()) == {
        "project": "demo",
        "run": RUN,
    }


def test_run_id_is_never_self_invented_or_blank():
    assert run_id_of(None) is None
    with pytest.raises(TelemetryError, match="non-empty"):
        run_id_of("   ")
    with pytest.raises(TelemetryError, match=r"expose \.run_id"):
        run_id_of(42)  # type: ignore[arg-type]


def test_dimensions_drop_unset_keys_rather_than_sending_empty_strings():
    assert dimensions_for(project="demo") == {"project": "demo"}
    assert "run" not in dimensions_for(project="demo")


def test_interop_with_the_real_k1_run_manifest():
    """Runs only once K1 is on the path (L-05's ``run_manifest.py``).

    Before the K1 module is merged this is **skipped**, not passed -- the point
    of the test is the join, and a skipped join is not evidence of one.
    """
    run_manifest = pytest.importorskip("autoresearch.run_manifest")
    manifest = run_manifest.RunManifest(
        project_id="demo",
        work_package_id="wp-1",
        code_revision="deadbeef",
        data_refs=["d1"],
        environment={"python": "3.12"},
        parameters={},
        seeds=[0],
        command=["python", "train.py"],
        output_hashes={},
    )
    assert dimensions_for(project="demo", run=manifest)["run"] == manifest.run_id
    point = cost_usd_point(total=None, price_source=None, project="demo", run=manifest)
    assert point.dimensions["run"] == manifest.run_id  # K1's id, not an invented one
    assert point.value is None


# ---------------------------------------------------------------------------
# M15-02: log redaction
# ---------------------------------------------------------------------------


def test_redact_value_redacts_by_key_name():
    for key in ("api_key", "token", "password", "prompt", "full_text", "Authorization"):
        assert redact_value(key, "anything at all") == REDACTED


def test_redact_value_redacts_by_content_even_under_a_harmless_key():
    assert redact_value("note", "sk-abcdefghijklmnop") == REDACTED
    assert redact_value("note", "reach me at alice@example.com") == REDACTED
    assert redact_value("note", "api_key: abcdef") == REDACTED


def test_redact_value_truncates_oversized_content():
    out = redact_value("note", "x" * (MAX_DIMENSION_VALUE + 50))
    assert isinstance(out, str)
    assert out.startswith("x" * MAX_DIMENSION_VALUE)
    assert f"<truncated {MAX_DIMENSION_VALUE + 50} chars>" in out


def test_redact_value_passes_through_ordinary_values_unchanged():
    assert redact_value("version", "0.1.0") == "0.1.0"
    assert redact_value("agent_count", 5) == 5
    assert redact_value("ok", True) is True


def test_redact_health_report_keeps_the_shape_and_hides_the_secrets():
    report = {
        "ok": True,
        "version": "0.1.0",
        "settings": {"api_key": "sk-abcdefghijklmnop"},
        "prompt": "summarise this paper: ...",
        "database_ready": True,
    }
    redacted = redact_health_report(report)
    assert set(redacted) == set(report)  # shape preserved for the caller
    assert redacted["version"] == "0.1.0"
    assert redacted["prompt"] == REDACTED
    dumped = repr(redacted)
    assert "sk-abcdefghijklmnop" not in dumped
    assert "summarise this paper" not in dumped


def test_doctor_diagnostics_only_names_unhealthy_signals():
    assert doctor_diagnostics({"ok": True, "database_ready": True}) == []
    diagnostics = doctor_diagnostics(
        {"ok": False, "database_ready": False, "projects_dir_exists": True}
    )
    assert len(diagnostics) == 2
    assert any("ok=False" in line for line in diagnostics)
    assert any("database_ready=False" in line for line in diagnostics)


def test_doctor_diagnostics_never_echoes_a_redacted_value():
    diagnostics = doctor_diagnostics({"ok": True, "token": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"})
    assert diagnostics == []


def test_doctor_diagnostics_ignores_absent_keys():
    """An absent key is not a healthy key -- but it is also not a diagnosis."""
    assert doctor_diagnostics({"ok": True}) == []


def test_redact_health_report_recurses_into_nested_containers():
    """M15-02 recursion: a sensitive key buried one level down must be redacted.

    The single-level implementation leaked ``password`` because it only looked at
    the (non-sensitive) outer key and the string repr of the inner dict.
    """
    report = {
        "ok": True,
        "cfg": {"password": "hunter2-example"},
        "endpoints": [{"token": "secret-inside-list"}],
        "pairs": ({"api_key": "plaintext-nested"},),
    }
    redacted = redact_health_report(report)
    assert set(redacted) == set(report)
    assert redacted["ok"] is True
    assert redacted["cfg"]["password"] == REDACTED
    assert redacted["endpoints"][0]["token"] == REDACTED
    assert redacted["pairs"][0]["api_key"] == REDACTED


def test_redact_health_report_redacts_whole_container_under_sensitive_key():
    """A container under a sensitive key is replaced wholesale, not drilled into."""
    report = {"secret": {"anything": "at all", "even": ["nested", "data"]}}
    redacted = redact_health_report(report)
    assert redacted["secret"] == REDACTED


def test_redact_value_truncates_after_validation():
    """M15-02: validation (REDACTED) precedes truncation, never the reverse.

    A long value that is *also* a secret must be fully redacted, not leaked as a
    truncated prefix; a long but harmless value is still shortened.
    """
    long_harmless = "x" * (MAX_DIMENSION_VALUE + 40)
    out = redact_value("note", long_harmless)
    assert isinstance(out, str)
    assert out.startswith("x" * MAX_DIMENSION_VALUE)
    assert f"<truncated {MAX_DIMENSION_VALUE + 40} chars>" in out

    # long AND secret -> fully redacted, no partial leak
    long_secret = "sk-abcdefghijklmnop" + "y" * MAX_DIMENSION_VALUE
    assert redact_value("note", long_secret) == REDACTED

    # long value under a sensitive key -> redacted, not truncated
    assert redact_value("token", "z" * (MAX_DIMENSION_VALUE + 40)) == REDACTED


def test_redact_value_redacts_jwt_tokens():
    """M15-02: an RFC 7519 JWT (header.payload.signature) is a bearer secret."""
    jwt = "eyJ" + "A" * 12 + "." + "B" * 12 + "." + "C" * 12
    assert redact_value("note", jwt) == REDACTED
    assert redact_value("token_header", "Bearer " + jwt) == REDACTED

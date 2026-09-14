"""L2 contract tests for ``CapabilityManifest`` and its registration boundary.

Acceptance map (S3-A2): A1 (required identity/refs), A2 (network allowlist),
A4 (derive + override visibility), A6 (lifecycle), A7 (conformance fixture),
A8 (restricted license).

Discriminating power is labelled per test, because the two kinds are not equal:

* **criterion-level** -- the assertion only uses symbols that already exist on the
  pre-change code (``CapabilityRegistrationError``) and depends on behaviour that
  changed. These fail on the old code *because the old code allowed the thing*,
  which is what makes them evidence.
* **symbol-level** -- the assertion names a symbol introduced by this change, so it
  fails on the old code with ``ImportError``/``AttributeError``. That proves the
  symbol exists, not that the rule works. It is reported, never counted.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from autoresearch.capability_registry import (
    CapabilityAdapterResult,
    CapabilityKind,
    CapabilityManifestInvalidError,
    CapabilityRegistrationError,
    CapabilityRegistry,
    CapabilityTrustTier,
    manifest_warnings,
    validate_manifest,
)
from autoresearch.invocation_contracts import (
    CapabilityManifest,
    CapabilityTrustClass,
)
from autoresearch.search_adapters import (
    ARXIV_SOURCE,
    OPENALEX_SOURCE,
    SEMANTIC_SCHOLAR_SOURCE,
    register_search_adapters,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "capabilities"

CATALOG_FIELDS = (
    "manifest_id",
    "contract_version",
    "version",
    "kind",
    "input_schema_ref",
    "output_schema_ref",
    "evidence_mode",
    "network_required",
    "allowed_network_domains",
    "license_spdx",
    "requires_credentials",
    "supports_offline",
    "selection_tags",
    "trust_class",
    "lifecycle_status",
    "conformance_fixture",
)


class _StubAdapter:
    """No-op adapter: these tests exercise the boundary, never the adapter."""

    def __init__(self, name: str, version: str = "1", *, network_required: bool = False):
        self.capability_name = name
        self.capability_version = version
        self.network_required = network_required

    def invoke(self, request, context) -> CapabilityAdapterResult:  # pragma: no cover
        raise AssertionError("adapter must not be invoked by registration tests")


def base_manifest(name: str = "probe", *, version: str = "1", **overrides) -> CapabilityManifest:
    payload = {
        "name": name,
        "manifest_id": name,
        "version": version,
        "entrypoint": f"tests.test_capability_manifest_contract:{name}",
        "evidence_mode": "candidate_only",
        "input_schema_ref": "SearchAdapterRequest",
        "output_schema_ref": "RetrievedPaper",
        "conformance_fixture": "tests/fixtures/capabilities/probe.json",
    }
    payload.update(overrides)
    return CapabilityManifest(**payload)


def register(registry: CapabilityRegistry, manifest: CapabilityManifest, adapter=None):
    return registry.register(
        manifest,
        adapter or _StubAdapter(manifest.name, manifest.version),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )


# --------------------------------------------------------------------------- #
# A1 -- required identity and schema refs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "field",
    ["manifest_id", "input_schema_ref", "output_schema_ref"],
)
def test_missing_required_manifest_field_is_rejected(field: str):
    """criterion-level: the old code registered this manifest successfully."""

    registry = CapabilityRegistry()
    with pytest.raises(CapabilityRegistrationError):
        register(registry, base_manifest(**{field: None}))
    assert registry.list() == []


def test_malformed_schema_ref_is_rejected():
    """criterion-level: 'Not A Contract Name' cannot resolve to a typed contract."""

    registry = CapabilityRegistry()
    with pytest.raises(CapabilityRegistrationError):
        register(registry, base_manifest(input_schema_ref="Not A Contract Name!"))


def test_manifest_invalid_error_is_the_narrower_type():
    """symbol-level: proves the dedicated error type exists."""

    registry = CapabilityRegistry()
    with pytest.raises(CapabilityManifestInvalidError):
        register(registry, base_manifest(input_schema_ref=None))


def test_complete_manifest_is_admissible():
    """criterion-level: the admissible case must stay admissible."""

    assert validate_manifest(base_manifest()) == []


# --------------------------------------------------------------------------- #
# A2 -- network allowlist must not be empty while egress is declared
# --------------------------------------------------------------------------- #


def test_network_manifest_without_allowlist_is_rejected():
    """criterion-level: the old code accepted network_required=True with no domains."""

    registry = CapabilityRegistry(allow_network=True)
    manifest = base_manifest(network_required=True, allowed_network_domains=[])
    with pytest.raises(CapabilityRegistrationError):
        register(registry, manifest)
    assert registry.list() == []


def test_network_manifest_with_allowlist_is_admissible():
    """criterion-level: the fix must not reject a well-formed network capability."""

    registry = CapabilityRegistry(allow_network=True)
    manifest = base_manifest(network_required=True, allowed_network_domains=["api.example"])
    view = register(registry, manifest)
    assert view.network_required is True
    assert view.allowed_network_domains == ("api.example",)


def test_no_candidates_case_is_untouched_by_validation():
    """criterion-level: a non-network manifest keeps working with no domains."""

    registry = CapabilityRegistry()
    view = register(registry, base_manifest(network_required=False))
    assert view.allowed_network_domains == ()
    assert view.network_required is False


# --------------------------------------------------------------------------- #
# A4 -- derive from the manifest; never diverge silently
# --------------------------------------------------------------------------- #


def test_domains_are_derived_from_the_manifest_when_not_supplied():
    """criterion-level: the old code defaulted the stored allowlist to () instead."""

    registry = CapabilityRegistry(allow_network=True)
    manifest = base_manifest(network_required=True, allowed_network_domains=["api.example"])

    view = registry.register(
        manifest,
        _StubAdapter("derive"),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
        # kind / network_required / allowed_network_domains deliberately omitted
    )

    assert view.kind is CapabilityKind.NATIVE
    assert view.network_required is True
    assert view.allowed_network_domains == ("api.example",)
    assert view.overridden_fields == ()


def test_disagreeing_override_is_recorded_not_hidden():
    """symbol-level: proves overridden_fields exists and is populated."""

    registry = CapabilityRegistry(allow_network=True)
    manifest = base_manifest(network_required=True, allowed_network_domains=["api.example"])

    view = registry.register(
        manifest,
        _StubAdapter("override"),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
        allowed_network_domains=["other.example"],
    )

    assert view.allowed_network_domains == ("other.example",)
    assert "allowed_network_domains" in view.overridden_fields
    assert "kind" not in view.overridden_fields


def test_agreeing_override_is_not_reported_as_a_divergence():
    """criterion-level: restating the manifest value is not an override."""

    registry = CapabilityRegistry(allow_network=True)
    manifest = base_manifest(network_required=True, allowed_network_domains=["api.example"])
    view = registry.register(
        manifest,
        _StubAdapter("agree"),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
        kind=CapabilityKind.NATIVE,
        network_required=True,
        allowed_network_domains=["api.example"],
    )
    assert view.overridden_fields == ()


# --------------------------------------------------------------------------- #
# A6 -- lifecycle
# --------------------------------------------------------------------------- #


def test_retired_manifest_is_rejected():
    """criterion-level: the old code registered a retired manifest like any other."""

    registry = CapabilityRegistry()
    with pytest.raises(CapabilityRegistrationError):
        register(registry, base_manifest(lifecycle_status="retired"))
    assert registry.list() == []


def test_deprecated_manifest_registers_with_a_warning():
    """symbol-level: proves the non-fatal warning channel exists and is separate."""

    registry = CapabilityRegistry()
    view = register(registry, base_manifest(lifecycle_status="deprecated"))

    assert view.warnings
    assert any("deprecated" in item for item in view.warnings)
    # the warning channel must never be able to reject anything
    assert validate_manifest(base_manifest(lifecycle_status="deprecated")) == []


def test_manifest_warnings_does_not_reject_admissible_manifests():
    """criterion-level: warnings are advisory, never blocking."""

    for manifest in (
        base_manifest(),
        base_manifest(lifecycle_status="deprecated"),
    ):
        assert validate_manifest(manifest) == []
        assert isinstance(manifest_warnings(manifest), list)


# --------------------------------------------------------------------------- #
# A8 -- restricted licences need a recorded reason
# --------------------------------------------------------------------------- #


def test_restricted_license_without_reason_is_rejected():
    """criterion-level: the old code accepted any license string at all."""

    registry = CapabilityRegistry()
    with pytest.raises(CapabilityRegistrationError):
        register(registry, base_manifest(license_spdx="AGPL-3.0"))
    assert registry.list() == []


def test_restricted_license_with_reason_is_admissible():
    """criterion-level: the rule must gate the reason, not the licence."""

    registry = CapabilityRegistry()
    manifest = base_manifest(
        license_spdx="AGPL-3.0",
        selection_restricted_reason="offline fallback only when the default parser is unavailable",
    )
    view = register(registry, manifest)
    assert view.license_spdx == "AGPL-3.0"
    assert view.manifest.is_restricted_license is True


@pytest.mark.parametrize("license_id", ["MIT", "Apache-2.0", "BSD-3-Clause"])
def test_permissive_licenses_need_no_reason(license_id: str):
    """criterion-level: the restriction must not spill onto permissive licences."""

    assert validate_manifest(base_manifest(license_spdx=license_id)) == []


# --------------------------------------------------------------------------- #
# A3 / A7 -- exhaustive built-in coverage and conformance fixtures
# --------------------------------------------------------------------------- #


def test_every_builtin_adapter_registers_and_pins_a_fixture():
    """criterion-level for A7 (a missing fixture file fails); A3 for the rest."""

    registry = CapabilityRegistry(allow_network=True)
    views = register_search_adapters(registry)

    assert set(views) == {SEMANTIC_SCHOLAR_SOURCE, ARXIV_SOURCE, OPENALEX_SOURCE}

    for source, view in views.items():
        # A3: every built-in manifest survives the new validation untouched
        assert validate_manifest(view.manifest) == [], source

        # A3: derivation introduces no divergence for the real adapters
        assert view.overridden_fields == (), source
        assert view.kind is CapabilityKind.NATIVE
        assert view.network_required is True
        assert view.allowed_network_domains == tuple(view.manifest.allowed_network_domains)

        # A7: the fixture exists and matches the declared catalog surface
        fixture = Path(view.manifest.conformance_fixture)
        assert fixture.is_file(), f"{source} conformance fixture is missing: {fixture}"

        declared = _catalog_surface(view.manifest)
        recorded = json.loads(fixture.read_text(encoding="utf-8"))
        assert recorded == declared, (
            f"{source} fixture drifted from the manifest; "
            f"regenerate {fixture} only when the change is intended"
        )


def test_registry_list_matches_registration_views():
    """criterion-level: list() must not drop the new metadata."""

    registry = CapabilityRegistry(allow_network=True)
    registered = register_search_adapters(registry)
    listed = {view.manifest.name: view for view in registry.list()}

    assert set(listed) == {view.manifest.name for view in registered.values()}
    for view in registered.values():
        assert listed[view.manifest.name] == view


def _catalog_surface(manifest: CapabilityManifest) -> dict:
    """The subset of the manifest a selection layer enumerates."""

    dumped = manifest.model_dump(mode="json")
    return {field: dumped[field] for field in CATALOG_FIELDS}


def test_catalog_surface_is_fully_populated_for_builtins():
    """criterion-level: an option nobody can compare is not selectable."""

    registry = CapabilityRegistry(allow_network=True)
    views = register_search_adapters(registry)

    for source, view in views.items():
        surface = _catalog_surface(view.manifest)
        for field in CATALOG_FIELDS:
            value = surface[field]
            assert value is not None or field in {"license_spdx"}, f"{source}.{field}"
        assert surface["manifest_id"], source
        assert surface["trust_class"] == CapabilityTrustClass.LOCAL.value, source
        assert surface["input_schema_ref"] and surface["output_schema_ref"], source


def test_trust_class_never_grants_an_effective_tier():
    """criterion-level: self-description must not move the operator policy."""

    registry = CapabilityRegistry(allow_network=True)
    manifest = base_manifest(trust_class=CapabilityTrustClass.REVIEWED_EXTERNAL)
    view = registry.register(
        manifest,
        _StubAdapter("tier-probe"),
        trust_tier=CapabilityTrustTier.CANDIDATE_ONLY,
    )
    assert view.manifest.trust_class is CapabilityTrustClass.REVIEWED_EXTERNAL
    assert view.trust_tier is CapabilityTrustTier.CANDIDATE_ONLY


# ---------------------------------------------------------------------------
# D-O13-09: the contract's required fields are actually required
# ---------------------------------------------------------------------------


def test_missing_entrypoint_is_rejected_at_registration():
    """The contract lists ``entrypoint`` as required; registration must enforce it.

    It did not: ``entrypoint`` defaulted to ``None`` and ``validate_manifest``
    never looked at it, so every built-in adapter -- none of which declared one --
    registered cleanly. This is the check that closes that gap; it is the
    registration-time counterpart of the field being called "required".
    """

    from autoresearch.capability_registry import validate_manifest

    problems = validate_manifest(base_manifest(entrypoint=None))
    assert any("entrypoint" in problem for problem in problems), problems

    registry = CapabilityRegistry(allow_network=True)
    with pytest.raises(CapabilityManifestInvalidError):
        register(registry, base_manifest(entrypoint=None))


def test_missing_evidence_mode_is_rejected_at_registration():
    """``evidence_mode`` is a required contract field, not an optional nicety."""

    from autoresearch.capability_registry import validate_manifest

    problems = validate_manifest(base_manifest(evidence_mode=None))
    assert any("evidence_mode" in problem for problem in problems), problems


def test_a_manifest_satisfying_the_contract_registers():
    """The inverse: a manifest with every required field is admissible.

    Without this the rejection tests above could pass on a validator that
    rejects everything.
    """

    from autoresearch.capability_registry import validate_manifest

    manifest = base_manifest()
    assert validate_manifest(manifest) == []

    registry = CapabilityRegistry(allow_network=True)
    view = register(registry, manifest)
    assert view.manifest.entrypoint == manifest.entrypoint
    assert view.manifest.evidence_mode == "candidate_only"


def test_every_builtin_adapter_declares_a_resolvable_entrypoint():
    """Every shipped adapter must satisfy the contract it is registered under."""

    from autoresearch.capability_registry import (
        CapabilityRegistry,
        validate_manifest,
    )
    from autoresearch.search_adapters import register_search_adapters

    registry = CapabilityRegistry(allow_network=True)
    register_search_adapters(registry)

    views = registry.list()
    assert views, "the built-ins must actually register"
    for view in views:
        assert validate_manifest(view.manifest) == [], view.manifest.name
        entrypoint = view.manifest.entrypoint
        assert entrypoint and ":" in entrypoint, (view.manifest.name, entrypoint)
        module_name, _, attribute = entrypoint.partition(":")
        module = importlib.import_module(module_name)
        assert hasattr(module, attribute), (
            f"{view.manifest.name} declares entrypoint {entrypoint!r}, "
            "which does not resolve"
        )

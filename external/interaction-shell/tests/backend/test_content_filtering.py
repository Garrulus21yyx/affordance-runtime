from __future__ import annotations

import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest
from interaction_shell.content_filtering import (
    PINNED_UBOL_COMPLETE_PATCH_ID,
    PINNED_UBOL_VERSION,
    ContentFilterProfile,
    ContentFilterSessionAttestation,
    CosmeticFilterExtensionAttestation,
)
from interaction_shell.provision_content_filter import (
    attestation_environment,
    build_complete_filtering_artifact,
    verify_pinned_artifact,
)


def _extension() -> CosmeticFilterExtensionAttestation:
    return CosmeticFilterExtensionAttestation(
        "ext_ubol_pinned",
        "uBOLite_2026_825_1619",
        "2026-08-25T16:20:50Z",
        "2026-08-25T16:20:50Z",
        "1" * 64,
    )


def test_extension_attestation_environment_round_trip() -> None:
    extension = _extension()

    restored = CosmeticFilterExtensionAttestation.from_environment(
        attestation_environment(extension)
    )

    assert restored == extension


def test_extension_attestation_environment_is_all_or_none() -> None:
    assert CosmeticFilterExtensionAttestation.from_environment({}) is None

    with pytest.raises(ValueError, match="attestation is incomplete"):
        CosmeticFilterExtensionAttestation.from_environment(
            {"INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_ID": "ext_partial"}
        )


def test_strict_session_attestation_uses_the_pinned_artifact_identity() -> None:
    applied = ContentFilterSessionAttestation.applied(
        ContentFilterProfile.ADS_AND_COSMETIC,
        _extension(),
    )

    assert applied.engine_version == f"{PINNED_UBOL_VERSION}+{PINNED_UBOL_COMPLETE_PATCH_ID}"
    assert applied.ruleset_digest == f"sha256:{'1' * 64}"


def test_pinned_artifact_verification_rejects_size_and_digest_drift() -> None:
    content = b"pinned-extension"
    digest = hashlib.sha256(content).hexdigest()
    verify_pinned_artifact(content, expected_size=len(content), expected_sha256=digest)

    with pytest.raises(RuntimeError, match="size mismatch"):
        verify_pinned_artifact(content, expected_size=len(content) + 1, expected_sha256=digest)
    with pytest.raises(RuntimeError, match="digest mismatch"):
        verify_pinned_artifact(content, expected_size=len(content), expected_sha256="0" * 64)


def test_complete_filtering_artifact_has_one_bounded_mode_owner_patch() -> None:
    upstream = BytesIO()
    original = b"    optimal: [ 'all-urls' ],\n    complete: [],"
    with ZipFile(upstream, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        archive.writestr("js/mode-manager.js", b"before\n" + original + b"\nafter")
    upstream_content = upstream.getvalue()

    derived = build_complete_filtering_artifact(
        upstream_content,
        expected_size=len(upstream_content),
        expected_sha256=hashlib.sha256(upstream_content).hexdigest(),
    )

    with ZipFile(BytesIO(derived), "r") as archive:
        patched = archive.read("js/mode-manager.js")
    assert original not in patched
    assert b"    optimal: [],\n    complete: [ 'all-urls' ]," in patched

"""One-time provisioning for the pinned Steel cosmetic-filter extension."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from dotenv import load_dotenv

from .content_filtering import (
    PINNED_UBOL_COMPLETE_PATCH_ID,
    PINNED_UBOL_FILENAME,
    PINNED_UBOL_SHA256,
    PINNED_UBOL_SIZE_BYTES,
    PINNED_UBOL_SOURCE_URL,
    PINNED_UBOL_VERSION,
    CosmeticFilterExtensionAttestation,
)

_STEEL_API_ORIGIN = "https://api.steel.dev"
_PROVISION_TIMEOUT_S = 120.0
_MODE_MANAGER_PATH = "js/mode-manager.js"
_OPTIMAL_DEFAULT = b"    optimal: [ 'all-urls' ],\n    complete: [],"
_COMPLETE_DEFAULT = b"    optimal: [],\n    complete: [ 'all-urls' ],"


def verify_pinned_artifact(
    content: bytes,
    *,
    expected_size: int = PINNED_UBOL_SIZE_BYTES,
    expected_sha256: str = PINNED_UBOL_SHA256,
) -> None:
    if len(content) != expected_size:
        raise RuntimeError("pinned cosmetic filter artifact size mismatch")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise RuntimeError("pinned cosmetic filter artifact digest mismatch")


def build_complete_filtering_artifact(
    upstream_content: bytes,
    *,
    expected_size: int = PINNED_UBOL_SIZE_BYTES,
    expected_sha256: str = PINNED_UBOL_SHA256,
) -> bytes:
    """Apply the one pinned configuration patch required for generic cosmetic rules."""

    verify_pinned_artifact(
        upstream_content,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
    )
    output = BytesIO()
    patched = 0
    with ZipFile(BytesIO(upstream_content), "r") as upstream, ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED,
    ) as derived:
        for info in upstream.infolist():
            content = upstream.read(info.filename)
            if info.filename == _MODE_MANAGER_PATH:
                if content.count(_OPTIMAL_DEFAULT) != 1:
                    raise RuntimeError("pinned cosmetic filter patch witness mismatch")
                content = content.replace(_OPTIMAL_DEFAULT, _COMPLETE_DEFAULT)
                patched += 1
            derived.writestr(info, content)
    if patched != 1:
        raise RuntimeError("pinned cosmetic filter mode owner is unavailable")
    return output.getvalue()


def provision_pinned_extension(
    api_key: str,
    *,
    client: httpx.Client,
    existing_extension_id: str = "",
) -> CosmeticFilterExtensionAttestation:
    if not api_key.strip():
        raise RuntimeError("Steel API key is unavailable")
    artifact_response = client.get(PINNED_UBOL_SOURCE_URL, follow_redirects=True)
    artifact_response.raise_for_status()
    derived_artifact = build_complete_filtering_artifact(artifact_response.content)
    derived_digest = hashlib.sha256(derived_artifact).hexdigest()

    method = "PUT" if existing_extension_id else "POST"
    endpoint = (
        f"{_STEEL_API_ORIGIN}/v1/extensions/{existing_extension_id}"
        if existing_extension_id
        else f"{_STEEL_API_ORIGIN}/v1/extensions"
    )
    upload_response = client.request(
        method,
        endpoint,
        headers={"steel-api-key": api_key},
        files={
            "file": (
                PINNED_UBOL_FILENAME.replace(".chromium.zip", ".complete.chromium.zip"),
                derived_artifact,
                "application/zip",
            )
        },
    )
    if upload_response.status_code not in {200, 201}:
        raise RuntimeError("Steel cosmetic filter extension upload failed")
    try:
        payload = upload_response.json()
        return CosmeticFilterExtensionAttestation(
            extension_id=_required_text(payload, "id"),
            name=_required_text(payload, "name"),
            created_at=_required_text(payload, "createdAt"),
            updated_at=_required_text(payload, "updatedAt"),
            artifact_sha256=derived_digest,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Steel cosmetic filter extension response is invalid") from exc


def attestation_environment(
    attestation: CosmeticFilterExtensionAttestation,
) -> dict[str, str]:
    return {
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_ID": attestation.extension_id,
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_NAME": attestation.name,
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_CREATED_AT": attestation.created_at,
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_UPDATED_AT": attestation.updated_at,
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_SHA256": attestation.artifact_sha256,
    }


def main() -> int:
    repository_root = Path(__file__).resolve().parents[4]
    load_dotenv(repository_root / ".env", override=False)
    api_key = os.environ.get("Viewer_API_KEY", "").strip() or os.environ.get(
        "STEEL_API_KEY", ""
    ).strip()
    with httpx.Client(timeout=_PROVISION_TIMEOUT_S) as client:
        attestation = provision_pinned_extension(
            api_key,
            client=client,
            existing_extension_id=os.environ.get(
                "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_ID", ""
            ).strip(),
        )
    print(
        json.dumps(
            {
                "artifact": {
                    "filename": PINNED_UBOL_FILENAME,
                    "patch_id": PINNED_UBOL_COMPLETE_PATCH_ID,
                    "source_sha256": PINNED_UBOL_SHA256,
                    "derived_sha256": attestation.artifact_sha256,
                    "source_url": PINNED_UBOL_SOURCE_URL,
                    "version": PINNED_UBOL_VERSION,
                },
                "environment": attestation_environment(attestation),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {field}")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())

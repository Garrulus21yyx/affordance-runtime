"""Browser-owned content-filter configuration for Shell Surface acquisition."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

PINNED_UBOL_VERSION = "2026.825.1619"
PINNED_UBOL_FILENAME = f"uBOLite_{PINNED_UBOL_VERSION}.chromium.zip"
PINNED_UBOL_SOURCE_URL = (
    "https://github.com/uBlockOrigin/uBOL-home/releases/download/"
    f"{PINNED_UBOL_VERSION}/{PINNED_UBOL_FILENAME}"
)
PINNED_UBOL_SHA256 = "9f0acbe3eabd4ba1c1c0629438cfacafbdaf04cd150769932d5d265b2fac117e"
PINNED_UBOL_SIZE_BYTES = 9_646_761
PINNED_UBOL_COMPLETE_PATCH_ID = "default-filtering-complete.v1"

_EXTENSION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{3,128}")
_COSMETIC_EXTENSION_ENV = {
    "extension_id": "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_ID",
    "name": "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_NAME",
    "created_at": "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_CREATED_AT",
    "updated_at": "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_UPDATED_AT",
    "artifact_sha256": "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_SHA256",
}


class ContentFilterProfile(StrEnum):
    """Closed filtering strengths supported by Shell browser-session adapters."""

    OFF = "off"
    NETWORK_ADS = "network_ads.v1"
    ADS_AND_COSMETIC = "ads_and_cosmetic.v1"

    @property
    def blocks_ad_networks(self) -> bool:
        return self is not ContentFilterProfile.OFF

    @property
    def requires_cosmetic_filtering(self) -> bool:
        return self is ContentFilterProfile.ADS_AND_COSMETIC


@dataclass(frozen=True)
class CosmeticFilterExtensionAttestation:
    """Deployment-owned identity for one already uploaded pinned extension."""

    extension_id: str
    name: str
    created_at: str
    updated_at: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        if not _EXTENSION_ID_PATTERN.fullmatch(self.extension_id):
            raise ValueError("cosmetic filter extension id is invalid")
        if not self.name.strip() or len(self.name) > 160:
            raise ValueError("cosmetic filter extension name is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.artifact_sha256):
            raise ValueError("cosmetic filter extension artifact digest is invalid")
        for label, value in (
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
        ):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"cosmetic filter extension {label} is invalid") from exc
            if parsed.tzinfo is None:
                raise ValueError(f"cosmetic filter extension {label} must include a timezone")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
    ) -> CosmeticFilterExtensionAttestation | None:
        values = {
            field: environment.get(variable, "").strip()
            for field, variable in _COSMETIC_EXTENSION_ENV.items()
        }
        configured = {field for field, value in values.items() if value}
        if not configured:
            return None
        missing = sorted(set(values) - configured)
        if missing:
            missing_variables = ", ".join(_COSMETIC_EXTENSION_ENV[field] for field in missing)
            raise ValueError(
                f"cosmetic filter extension attestation is incomplete: {missing_variables}"
            )
        return cls(**values)


@dataclass(frozen=True)
class ContentFilterSessionAttestation:
    """Private acquisition metadata created by the browser-session owner."""

    profile: ContentFilterProfile
    engine_id: str
    engine_version: str
    ruleset_digest: str
    extension_id: str = ""
    activation_latency_ms: int = 0
    blocked_request_count: int | None = None
    cosmetic_rule_count: int | None = None

    @classmethod
    def applied(
        cls,
        profile: ContentFilterProfile,
        extension: CosmeticFilterExtensionAttestation | None = None,
        *,
        activation_latency_ms: int = 0,
    ) -> ContentFilterSessionAttestation:
        if activation_latency_ms < 0:
            raise ValueError("content filter activation latency must be nonnegative")
        if profile is ContentFilterProfile.OFF:
            return cls(profile, "none", "", "", activation_latency_ms=activation_latency_ms)
        if profile is ContentFilterProfile.NETWORK_ADS:
            return cls(
                profile,
                "steel.block_ads",
                "provider-managed",
                "",
                activation_latency_ms=activation_latency_ms,
            )
        if extension is None:
            raise ValueError("strict content filtering requires an extension attestation")
        return cls(
            profile,
            "ublock-origin-lite",
            f"{PINNED_UBOL_VERSION}+{PINNED_UBOL_COMPLETE_PATCH_ID}",
            f"sha256:{extension.artifact_sha256}",
            extension.extension_id,
            activation_latency_ms,
        )


__all__ = [
    "PINNED_UBOL_COMPLETE_PATCH_ID",
    "PINNED_UBOL_FILENAME",
    "PINNED_UBOL_SHA256",
    "PINNED_UBOL_SIZE_BYTES",
    "PINNED_UBOL_SOURCE_URL",
    "PINNED_UBOL_VERSION",
    "ContentFilterProfile",
    "ContentFilterSessionAttestation",
    "CosmeticFilterExtensionAttestation",
]

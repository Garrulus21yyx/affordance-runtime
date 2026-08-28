"""Browser-owned content-filter configuration for Shell Surface acquisition."""

from __future__ import annotations

from enum import StrEnum


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


__all__ = ["ContentFilterProfile"]

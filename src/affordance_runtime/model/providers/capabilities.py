"""Authoritative provider/model capability declarations."""

from __future__ import annotations

import re


def model_supports_multimodal(provider: str, model_id: str) -> bool:
    """Return declared input capability without probing or call-site guessing.

    Unknown provider/model families fail closed. GLM visual models use the
    provider's declared ``glm-<version>v-*`` naming family.
    """

    if provider.strip().casefold() != "zhipu":
        return False
    normalized_model = model_id.strip().casefold()
    return re.match(r"^glm-\d+(?:\.\d+)?v(?:-|$)", normalized_model) is not None


__all__ = ["model_supports_multimodal"]

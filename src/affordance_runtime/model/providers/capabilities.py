"""Authoritative provider/model capability declarations."""

from __future__ import annotations

import re


def model_supports_multimodal(provider: str, model_id: str) -> bool:
    """Return declared input capability without probing or call-site guessing.

    Unknown provider/model families fail closed. GLM visual models use the
    provider's declared ``glm-<version>v-*`` naming family.
    """

    normalized_provider = provider.strip().casefold()
    normalized_model = model_id.strip().casefold()
    if normalized_provider == "zhipu":
        return re.match(r"^glm-\d+(?:\.\d+)?v(?:-|$)", normalized_model) is not None
    if normalized_provider == "deepseek":
        return re.fullmatch(r"deepseek-v\d+(?:-[a-z0-9]+)*-vision(?:-[a-z0-9]+)*", normalized_model) is not None
    if normalized_provider == "gemini":
        return normalized_model.startswith("gemini-")
    return False


__all__ = ["model_supports_multimodal"]

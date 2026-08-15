"""Thin OmniParser HTTP adapter for bounded visual entity observation.

This module implements only the official ``POST /parse/`` screen-parser API.
It does not import OmniTool, its agent loop, planner, memory, or executor.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from affordance_runtime.model.providers.port import StructuredModelError, _post_json
from affordance_runtime.surfaces.visual.grounding import VisualRegion, VisualRegionProposalRequest

_MAX_SERVER_ELEMENTS = 4_096


@dataclass
class OmniParserHttpRegionProposer:
    base_url: str
    provider: str = "omniparser"
    model: str = "microsoft/omniparser-v2"
    prompt_version: str = "omniparser-http-v1"
    timeout_s: float = 90.0
    headers: dict[str, str] = field(default_factory=dict, repr=False)

    def propose(self, request: VisualRegionProposalRequest) -> list[VisualRegion]:
        if request.max_regions <= 0:
            raise ValueError("visual region max_regions must be positive")
        response, _, _ = _post_json(
            f"{self.base_url.rstrip('/')}/parse/",
            {"base64_image": base64.b64encode(request.image_bytes).decode("ascii")},
            timeout_s=self.timeout_s,
            headers=self.headers,
        )
        raw = response.get("parsed_content_list")
        if not isinstance(raw, list) or len(raw) > _MAX_SERVER_ELEMENTS:
            raise StructuredModelError("OmniParser response requires a bounded parsed_content_list")
        ranked = sorted(
            enumerate(raw),
            key=lambda pair: _element_rank(pair[0], pair[1], request.instruction),
        )
        regions: list[VisualRegion] = []
        for _index, item in ranked:
            region = _parse_element(item, request.image_size)
            if region is None:
                continue
            regions.append(region)
            if len(regions) >= request.max_regions:
                break
        return regions


def omniparser_region_proposer_from_environment(
    environment: Mapping[str, str] | None = None,
) -> OmniParserHttpRegionProposer:
    env = os.environ if environment is None else environment
    base_url = env.get("OMNIPARSER_BASE_URL", "").strip()
    if not base_url:
        raise ValueError("missing required visual region configuration: OMNIPARSER_BASE_URL")
    token = env.get("OMNIPARSER_API_KEY", "").strip()
    return OmniParserHttpRegionProposer(
        base_url=base_url,
        model=env.get("OMNIPARSER_MODEL_ID", "microsoft/omniparser-v2").strip()
        or "microsoft/omniparser-v2",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


def _parse_element(item: object, image_size: tuple[int, int]) -> VisualRegion | None:
    if not isinstance(item, dict):
        return None
    bbox = item.get("bbox")
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None
    try:
        left, top, right, bottom = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return None
    normalized = max(abs(value) for value in (left, top, right, bottom)) <= 1.0
    if not normalized:
        width, height = image_size
        left, right = left / width, right / width
        top, bottom = top / height, bottom / height
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        return None
    element_type = str(item.get("type") or "region").strip().casefold()
    interactive = item.get("interactivity") is True
    content = str(item.get("content") or "").strip()[:240]
    role = "img" if element_type == "icon" else "text" if element_type == "text" else "region"
    state: dict[str, Any] = {}
    if content:
        state["text"] = content
    if interactive:
        state["interactable"] = True
    return VisualRegion(
        (left, top, right - left, bottom - top),
        content or element_type,
        0.5,
        True,
        role,
        "observe_only",
        state,
    )


def _element_rank(index: int, item: object, instruction: str) -> tuple[int, int, int]:
    if not isinstance(item, dict):
        return (1, 1, index)
    content_tokens = set(re.findall(r"[\w]+", str(item.get("content") or "").casefold()))
    instruction_tokens = set(re.findall(r"[\w]+", instruction.casefold()))
    relevant = bool(content_tokens.intersection(instruction_tokens))
    interactive = item.get("interactivity") is True
    return (0 if relevant else 1, 0 if interactive else 1, index)

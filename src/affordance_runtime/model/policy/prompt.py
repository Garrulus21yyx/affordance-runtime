"""The single stable GUI-agent prompt shared by every model transport."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from typing import Final

import yaml


def _load_prompt(name: str, key: str) -> tuple[str, str, str]:
    resource = files("affordance_runtime.model.policy").joinpath(f"prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", "evidence_status", key}:
        raise ValueError(f"{name} prompt bundle has an invalid shape")
    version = str(raw["version"])
    prompt = str(raw[key])
    evidence_status = str(raw["evidence_status"])
    if not version or not prompt.strip() or not evidence_status.strip():
        raise ValueError(f"{name} prompt bundle is incomplete")
    marker = "{{evidence_status}}"
    if prompt.count(marker) != 1:
        raise ValueError(f"{name} prompt bundle must place its evidence-status rule exactly once")
    normalized_evidence_status = evidence_status.strip()
    return version, prompt.replace(marker, normalized_evidence_status), normalized_evidence_status


_prompt_version, _actor_instructions, _evidence_status = _load_prompt(
    "grounded_agent.yaml", "actor"
)
MODEL_POLICY_PROMPT_VERSION: Final = _prompt_version
MODEL_POLICY_EVIDENCE_STATUS: Final = _evidence_status
MODEL_POLICY_INSTRUCTIONS: Final = _actor_instructions
__all__ = [
    "MODEL_POLICY_EVIDENCE_STATUS",
    "MODEL_POLICY_INSTRUCTIONS",
    "MODEL_POLICY_PROMPT_VERSION",
]

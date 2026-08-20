"""The single stable GUI-agent prompt shared by every model transport."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from typing import Final

import yaml


def _load_prompt(name: str, key: str) -> tuple[str, str]:
    resource = files("affordance_runtime.model.policy").joinpath(f"prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", key}:
        raise ValueError(f"{name} prompt bundle has an invalid shape")
    version = str(raw["version"])
    prompt = str(raw[key])
    if not version or not prompt.strip():
        raise ValueError(f"{name} prompt bundle is incomplete")
    return version, prompt


_prompt_version, _prompt_instructions = _load_prompt("grounded_agent.yaml", "actor")
MODEL_POLICY_PROMPT_VERSION: Final = _prompt_version
MODEL_POLICY_INSTRUCTIONS: Final = _prompt_instructions
__all__ = [
    "MODEL_POLICY_INSTRUCTIONS",
    "MODEL_POLICY_PROMPT_VERSION",
]

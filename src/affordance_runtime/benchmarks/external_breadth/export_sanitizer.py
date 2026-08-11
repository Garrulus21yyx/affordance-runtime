"""Public benchmark-export privacy sanitation; never Runtime truth authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FORBIDDEN_FIELDS = frozenset({
    "raw_prompt", "raw_response", "chain_of_thought", "hidden_reasoning", "api_key",
    "authorization", "endpoint_url", "credential", "selector", "xpath", "locator",
    "browsergym_id", "private_bid", "coordinate", "bbox", "private_href", "raw_reward",
    "hidden_benchmark_state", "expected_answer", "reference_action", "reference_trajectory",
    "success_script", "benchmark_oracle",
})
_FORBIDDEN_VALUE_MARKERS = (
    "browsergym/miniwob.", "http://", "https://", "authorization:", "bearer ",
    "api_key=", "selector:", "xpath:", "locator:", "coordinate:", "private_bid:",
    "private_href:",
)


def privacy_scan(output_dir: Path) -> tuple[str, ...]:
    """Reject private material only at the serialized export boundary."""

    errors: list[str] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        relative = str(path.relative_to(output_dir))
        if path.suffix != ".json":
            errors.append(f"{relative} is an unexpected non-JSON evidence file")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"{relative} is not valid readable JSON")
            continue
        errors.extend(_privacy_errors(payload, relative))
    return tuple(errors)


def _privacy_errors(payload: Any, relative: str, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).casefold().replace("-", "_")
            child = f"{location}.{key}"
            if normalized in _FORBIDDEN_FIELDS:
                errors.append(f"{relative} contains forbidden field {normalized} at {child}")
            errors.extend(_privacy_errors(value, relative, child))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            errors.extend(_privacy_errors(value, relative, f"{location}[{index}]"))
    elif isinstance(payload, str):
        folded = payload.casefold()
        for marker in _FORBIDDEN_VALUE_MARKERS:
            if marker in folded:
                errors.append(f"{relative} contains forbidden value {marker} at {location}")
    return errors

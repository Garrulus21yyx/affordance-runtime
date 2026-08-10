"""Read-only validation for a completed breadth report tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def validate_campaign_tree(output_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    attestation = _object(output_dir / "attestation.json")
    cases = attestation.get("case_report_sha256")
    if not isinstance(cases, dict) or len(cases) != 60:
        errors.append("attestation does not bind exactly 60 case reports")
        return tuple(errors)
    expected = {f"miniwob-60-{index:02d}" for index in range(1, 61)}
    if set(cases) != expected:
        errors.append("attested case IDs are missing, extra, or duplicated")
    for case_id, digest in cases.items():
        path = output_dir / "cases" / f"{case_id}.json"
        if not path.is_file() or digest != _sha256(path):
            errors.append(f"{case_id}: case report digest mismatch")
    for name, field in (("summary.json", "summary_sha256"), ("campaign.json", "campaign_sha256")):
        path = output_dir / name
        if not path.is_file() or attestation.get(field) != _sha256(path):
            errors.append(f"{name}: report digest mismatch")
    return tuple(errors)


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

"""Deterministic host/container benchmark agreement checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_IGNORED_RUN_FIELDS = frozenset({"latency_ms", "trace_path"})
_REQUIRED_ENVIRONMENT_FIELDS = (
    "runtime_commit",
    "runtime_version",
    "browser_version",
    "playwright_version",
    "fixture_version",
    "suite_version",
    "seed_semantics",
)


def compare_benchmark_reports(host_path: Path, container_path: Path) -> dict[str, Any]:
    """Compare stable outcomes while excluding expected timing/path differences."""

    host = json.loads(host_path.read_text(encoding="utf-8"))
    container = json.loads(container_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for field in ("suite_version", "metrics_by_variant", "acceptance_errors"):
        if host.get(field) != container.get(field):
            errors.append(f"{field} differs")

    host_runs = [_stable_run(run) for run in host.get("runs", [])]
    container_runs = [_stable_run(run) for run in container.get("runs", [])]
    if host_runs != container_runs:
        errors.append("stable per-run outcomes differ")

    host_environment = host.get("environment", {})
    container_environment = container.get("environment", {})
    environment_agreement = {
        field: {
            "host": host_environment.get(field),
            "container": container_environment.get(field),
            "matches": host_environment.get(field) == container_environment.get(field),
        }
        for field in _REQUIRED_ENVIRONMENT_FIELDS
    }
    errors.extend(
        f"environment.{field} differs"
        for field, result in environment_agreement.items()
        if not result["matches"]
    )

    return {
        "schema_version": "host-container-agreement-v1",
        "host_report": str(host_path),
        "container_report": str(container_path),
        "compared_runs": len(host_runs),
        "ignored_run_fields": sorted(_IGNORED_RUN_FIELDS),
        "environment_agreement": environment_agreement,
        "errors": errors,
        "acceptance": "passed" if not errors else "failed",
    }


def _stable_run(run: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in run.items() if key not in _IGNORED_RUN_FIELDS}

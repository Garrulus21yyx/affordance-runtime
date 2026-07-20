"""WorkArena L1 deployment preflight without loading credentials or tasks.

WorkArena is a BrowserGym suite backed by gated ServiceNow instances.  This
module proves whether a runner is configured to attempt its official L1 track;
it never reads, logs, or transmits an instance credential and never invokes the
benchmark's oracle/``cheat`` helper.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

WORKARENA_L1_EXPECTED_TASK_COUNT = 33
WORKARENA_PLAYWRIGHT_VERSION = "1.44.0"
_INSTANCE_ENV = ("SNOW_INSTANCE_URL", "SNOW_INSTANCE_UNAME", "SNOW_INSTANCE_PWD")


@dataclass(frozen=True)
class WorkArenaPreflight:
    package_version: str
    playwright_version: str
    instance_source: str
    l1_task_count: int
    ready: bool
    errors: tuple[str, ...]


def inspect_workarena_l1(
    *,
    environment: Mapping[str, str] | None = None,
    package_version: str | None = None,
    playwright_version: str | None = None,
    l1_task_count: int | None = None,
) -> WorkArenaPreflight:
    """Inspect prerequisites without importing a task environment or its secrets."""

    values = os.environ if environment is None else environment
    workarena_version = package_version if package_version is not None else _distribution_version("browsergym-workarena")
    installed_playwright = playwright_version if playwright_version is not None else _distribution_version("playwright")
    errors: list[str] = []
    if not workarena_version:
        errors.append("browsergym-workarena is not installed")
    if installed_playwright != WORKARENA_PLAYWRIGHT_VERSION:
        errors.append(f"WorkArena requires playwright=={WORKARENA_PLAYWRIGHT_VERSION}")

    configured = [name for name in _INSTANCE_ENV if values.get(name)]
    if configured and len(configured) != len(_INSTANCE_ENV):
        errors.append("ServiceNow instance configuration is incomplete")
    if len(configured) == len(_INSTANCE_ENV):
        instance_source = "explicit_instance"
    elif values.get("SNOW_INSTANCE_POOL"):
        instance_source = "custom_instance_pool"
    elif values.get("HUGGING_FACE_HUB_TOKEN"):
        instance_source = "gated_instance_pool"
    else:
        instance_source = "unconfigured"
        errors.append("configure ServiceNow instance credentials or gated WorkArena instance access")

    discovered_count = l1_task_count if l1_task_count is not None else _discover_l1_task_count()
    if discovered_count is None:
        effective_count = 0
        errors.append("WorkArena L1 task registration is unavailable")
    else:
        effective_count = discovered_count
        if effective_count != WORKARENA_L1_EXPECTED_TASK_COUNT:
            errors.append(
                f"expected {WORKARENA_L1_EXPECTED_TASK_COUNT} WorkArena L1 tasks, found {effective_count}"
            )
    return WorkArenaPreflight(
        package_version=workarena_version,
        playwright_version=installed_playwright,
        instance_source=instance_source,
        l1_task_count=effective_count,
        ready=not errors,
        errors=tuple(errors),
    )


def write_workarena_preflight(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = inspect_workarena_l1()
    report = {
        "schema_version": "workarena-l1-preflight-v1",
        "official_track": True,
        "oracle_used": False,
        **asdict(preflight),
    }
    (output_dir / "workarena-preflight.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _discover_l1_task_count() -> int | None:
    try:
        from browsergym.workarena import workarena_tasks_l1  # type: ignore[import-not-found]
    except Exception:
        return None
    return len(workarena_tasks_l1)

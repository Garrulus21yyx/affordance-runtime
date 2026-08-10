"""Fail-closed census of the installed pinned MiniWoB registry."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version

from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus

PACKAGE_NAME = "browsergym-miniwob"
PACKAGE_VERSION = "0.14.3"
CORE_VERSION = "0.14.3"
SOURCE_COMMIT = "7fd85d71a4b60325c6585396ec4f48377d049838"


def load_registry_census() -> MiniWobRegistryCensus:
    try:
        package_version = version(PACKAGE_NAME)
        core_version = version("browsergym-core")
        import browsergym.miniwob  # type: ignore[import-not-found,import-untyped]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]
    except (PackageNotFoundError, ImportError) as exc:
        raise RuntimeError("pinned BrowserGym/MiniWoB dependency is unavailable") from exc
    if package_version != PACKAGE_VERSION or core_version != CORE_VERSION:
        raise RuntimeError("BrowserGym/MiniWoB dependency version does not match the pinned profile")
    task_ids = tuple(sorted(str(item) for item in gym.registry if str(item).startswith("browsergym/miniwob.")))
    if not task_ids:
        raise RuntimeError("installed MiniWoB registry is empty")
    return MiniWobRegistryCensus(
        PACKAGE_NAME,
        package_version,
        core_version,
        SOURCE_COMMIT,
        task_ids,
        registry_digest(task_ids),
    )


def registry_digest(task_ids: tuple[str, ...]) -> str:
    payload = json.dumps(tuple(sorted(task_ids)), separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

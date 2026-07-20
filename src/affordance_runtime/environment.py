"""Reproducibility metadata for benchmark and evolution evidence."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EnvironmentManifest:
    runtime_version: str
    runtime_commit: str
    worktree_dirty: bool
    python_version: str
    platform: str
    playwright_version: str
    browser_version: str
    fixture_version: str
    suite_version: str
    seed_semantics: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def environment_manifest(
    *,
    browser_version: str = "",
    fixture_version: str = "",
    suite_version: str = "",
    seed_semantics: str = "label_only_v1",
    repository: Path | None = None,
) -> EnvironmentManifest:
    root = repository or Path.cwd()
    commit = _git(root, "rev-parse", "HEAD") or "unknown"
    dirty = bool(_git(root, "status", "--porcelain"))
    return EnvironmentManifest(
        runtime_version=_package_version("affordance-runtime"),
        runtime_commit=commit,
        worktree_dirty=dirty,
        python_version=platform.python_version(),
        platform=f"{platform.system()}-{platform.release()}-{platform.machine()}",
        playwright_version=_package_version("playwright"),
        browser_version=browser_version,
        fixture_version=fixture_version,
        suite_version=suite_version,
        seed_semantics=seed_semantics,
    )


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def _git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()

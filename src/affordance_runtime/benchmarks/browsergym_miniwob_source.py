"""Pinned MiniWoB source acquisition and official task discovery."""

from __future__ import annotations

import subprocess
from pathlib import Path

BROWSERGYM_MINIWOB_COMMIT = "7fd85d71a4b60325c6585396ec4f48377d049838"


def ensure_browsergym_miniwob(checkout_root: Path) -> Path:
    """Fetch the exact MiniWoB source pinned by BrowserGym 0.14.3."""

    repository = checkout_root.resolve() / "MiniWoB-plusplus"
    checkout_root.mkdir(parents=True, exist_ok=True)
    if not (repository / ".git").exists():
        _git(
            checkout_root,
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            "https://github.com/Farama-Foundation/MiniWoB-plusplus.git",
            str(repository),
        )
        _git(repository, "sparse-checkout", "init", "--cone")
        _git(repository, "sparse-checkout", "set", "miniwob/html")
    _git(repository, "fetch", "--depth", "1", "origin", BROWSERGYM_MINIWOB_COMMIT)
    _git(repository, "checkout", "--detach", BROWSERGYM_MINIWOB_COMMIT)
    commit = _git(repository, "rev-parse", "HEAD", capture=True)
    if commit != BROWSERGYM_MINIWOB_COMMIT:
        raise RuntimeError(f"BrowserGym MiniWoB commit mismatch: {commit}")
    root = repository / "miniwob" / "html"
    if not (root / "miniwob").is_dir():
        raise RuntimeError(f"BrowserGym MiniWoB HTML root is missing: {root}")
    return root


def registered_miniwob_tasks() -> tuple[str, ...]:
    """Discover BrowserGym registrations without maintaining a local task list."""

    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "BrowserGym is not installed; use an isolated affordance-runtime[browsergym] environment"
        ) from exc
    prefix = "browsergym/miniwob."
    return tuple(sorted(str(item).removeprefix(prefix) for item in gym.envs.registry if str(item).startswith(prefix)))


def _git(cwd: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git executable and repository arguments
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip() if capture else ""

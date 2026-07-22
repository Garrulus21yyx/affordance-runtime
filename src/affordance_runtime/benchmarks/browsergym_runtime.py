"""Validation boundary for the isolated BrowserGym benchmark interpreter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

BROWSERGYM_RUNTIME_PYTHON_ENV = "AFFORDANCE_BROWSERGYM_PYTHON"
DEFAULT_BROWSERGYM_RUNTIME_PYTHON = Path.home() / ".venvs/affordance-browsergym-py312/bin/python"
REQUIRED_PYTHON = (3, 12)
REQUIRED_BROWSERGYM_MINIWOB = "0.14.3"
REQUIRED_PLAYWRIGHT = "1.44.0"

_PREFLIGHT_PROGRAM = """
import importlib.metadata as metadata
import json
import sys
import browsergym.miniwob  # noqa: F401
import playwright  # noqa: F401
print(json.dumps({
    \"sys_executable\": sys.executable,
    \"python_version\": list(sys.version_info[:3]),
    \"browsergym_miniwob\": metadata.version(\"browsergym-miniwob\"),
    \"playwright\": metadata.version(\"playwright\"),
}, sort_keys=True))
"""


def configured_browsergym_python(environment: Mapping[str, str] | None = None) -> Path:
    """Return the explicit interpreter path without loading dotenv files."""

    env = os.environ if environment is None else environment
    configured = env.get(BROWSERGYM_RUNTIME_PYTHON_ENV, "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_BROWSERGYM_RUNTIME_PYTHON


def validate_browsergym_runtime_payload(
    payload: Mapping[str, Any], *, repository_root: Path
) -> dict[str, Any]:
    """Validate only stable interpreter identity/version facts from preflight."""

    executable = Path(str(payload.get("sys_executable") or "")).absolute()
    ordinary_venv = (repository_root / ".venv/bin/python").absolute()
    version = payload.get("python_version")
    if executable == ordinary_venv:
        raise ValueError("BrowserGym must not run from the repository .venv")
    if not isinstance(version, list) or tuple(version[:2]) != REQUIRED_PYTHON:
        raise ValueError("BrowserGym requires the isolated Python 3.12 runtime")
    if payload.get("browsergym_miniwob") != REQUIRED_BROWSERGYM_MINIWOB:
        raise ValueError(f"BrowserGym requires browsergym-miniwob=={REQUIRED_BROWSERGYM_MINIWOB}")
    if payload.get("playwright") != REQUIRED_PLAYWRIGHT:
        raise ValueError(f"BrowserGym requires playwright=={REQUIRED_PLAYWRIGHT}")
    return {
        "schema_version": "browsergym-runtime-preflight-v1",
        "sys_executable": str(executable),
        "python_version": ".".join(str(part) for part in version[:3]),
        "browsergym_miniwob": str(payload["browsergym_miniwob"]),
        "playwright": str(payload["playwright"]),
        "ready": True,
    }


def inspect_browsergym_runtime(python: Path, *, repository_root: Path) -> dict[str, Any]:
    """Invoke the candidate interpreter and return a checked, redacted manifest."""

    selected = python.expanduser().absolute()
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise ValueError(f"BrowserGym interpreter is not executable: {selected}")
    completed = subprocess.run(
        [str(selected), "-c", _PREFLIGHT_PROGRAM],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError("BrowserGym interpreter cannot import its pinned runtime dependencies")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("BrowserGym runtime preflight returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("BrowserGym runtime preflight must return an object")
    return validate_browsergym_runtime_payload(payload, repository_root=repository_root)

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
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

WORKARENA_L1_EXPECTED_TASK_COUNT = 33
WORKARENA_PLAYWRIGHT_VERSION = "1.44.0"
WORKARENA_RUNTIME_PYTHON_ENV = "AFFORDANCE_WORKARENA_PYTHON"
DEFAULT_WORKARENA_RUNTIME_PYTHON = Path.home() / ".venvs/affordance-workarena/bin/python"
_INSTANCE_ENV = ("SNOW_INSTANCE_URL", "SNOW_INSTANCE_UNAME", "SNOW_INSTANCE_PWD")

_RUNTIME_PREFLIGHT_PROGRAM = """
import importlib.metadata as metadata
import json
import sys
from browsergym.workarena import workarena_tasks_l1
print(json.dumps({
    "sys_executable": sys.executable,
    "python_version": list(sys.version_info[:3]),
    "browsergym_workarena": metadata.version("browsergym-workarena"),
    "playwright": metadata.version("playwright"),
    "l1_task_count": len(workarena_tasks_l1),
}, sort_keys=True))
"""


@dataclass(frozen=True)
class WorkArenaPreflight:
    package_version: str
    playwright_version: str
    instance_source: str
    l1_task_count: int
    ready: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class WorkArenaRuntimePreflight:
    sys_executable: str
    python_version: str
    package_version: str
    playwright_version: str
    l1_task_count: int
    ready: bool
    errors: tuple[str, ...]


def configured_workarena_python(environment: Mapping[str, str] | None = None) -> Path:
    """Return a dedicated WorkArena interpreter path without reading dotenv."""

    values = os.environ if environment is None else environment
    configured = values.get(WORKARENA_RUNTIME_PYTHON_ENV, "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_WORKARENA_RUNTIME_PYTHON


def inspect_workarena_runtime(
    python: Path,
    *,
    repository_root: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> WorkArenaRuntimePreflight:
    """Inspect an isolated interpreter with a credential-free child environment."""

    selected = python.expanduser().absolute()
    errors: list[str] = []
    if selected == (repository_root / ".venv/bin/python").absolute():
        errors.append("WorkArena must not run from the repository .venv")
    if not selected.is_file() or not os.access(selected, os.X_OK):
        errors.append("WorkArena interpreter is not executable")
    if errors:
        return WorkArenaRuntimePreflight(str(selected), "", "", "", 0, False, tuple(errors))

    child_environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        completed = runner(
            [str(selected), "-c", _RUNTIME_PREFLIGHT_PROGRAM],
            check=False,
            capture_output=True,
            text=True,
            env=child_environment,
        )
    except OSError as exc:
        return WorkArenaRuntimePreflight(
            str(selected), "", "", "", 0, False,
            (f"WorkArena runtime inspection unavailable: {type(exc).__name__}",),
        )
    if completed.returncode != 0:
        return WorkArenaRuntimePreflight(
            str(selected), "", "", "", 0, False,
            ("WorkArena interpreter cannot import its runtime dependencies",),
        )
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return WorkArenaRuntimePreflight(
            str(selected), "", "", "", 0, False,
            ("WorkArena runtime preflight returned invalid JSON",),
        )
    if not isinstance(payload, dict):
        return WorkArenaRuntimePreflight(
            str(selected), "", "", "", 0, False,
            ("WorkArena runtime preflight must return an object",),
        )
    return validate_workarena_runtime_payload(payload, repository_root=repository_root)


def validate_workarena_runtime_payload(
    payload: Mapping[str, Any], *, repository_root: Path
) -> WorkArenaRuntimePreflight:
    executable = Path(str(payload.get("sys_executable") or "")).absolute()
    version = payload.get("python_version")
    package_version = str(payload.get("browsergym_workarena") or "")
    playwright_version = str(payload.get("playwright") or "")
    task_count = payload.get("l1_task_count")
    errors: list[str] = []
    if executable == (repository_root / ".venv/bin/python").absolute():
        errors.append("WorkArena must not run from the repository .venv")
    if not isinstance(version, list) or len(version) < 3 or any(
        isinstance(part, bool) or not isinstance(part, int) for part in version[:3]
    ):
        errors.append("WorkArena runtime returned an invalid Python version")
        python_version = ""
    else:
        python_version = ".".join(str(part) for part in version[:3])
    if not package_version:
        errors.append("browsergym-workarena is not installed")
    if playwright_version != WORKARENA_PLAYWRIGHT_VERSION:
        errors.append(f"WorkArena requires playwright=={WORKARENA_PLAYWRIGHT_VERSION}")
    if isinstance(task_count, bool) or not isinstance(task_count, int):
        errors.append("WorkArena L1 task registration is unavailable")
        task_count = 0
    elif task_count != WORKARENA_L1_EXPECTED_TASK_COUNT:
        errors.append(
            f"expected {WORKARENA_L1_EXPECTED_TASK_COUNT} WorkArena L1 tasks, found {task_count}"
        )
    return WorkArenaRuntimePreflight(
        sys_executable=str(executable),
        python_version=python_version,
        package_version=package_version,
        playwright_version=playwright_version,
        l1_task_count=task_count,
        ready=not errors,
        errors=tuple(errors),
    )


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


def write_workarena_preflight(
    output_dir: Path,
    *,
    runtime_python: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    values = os.environ if environment is None else environment
    runtime = inspect_workarena_runtime(
        runtime_python or configured_workarena_python(values),
        repository_root=Path(__file__).resolve().parents[3],
    )
    access = inspect_workarena_l1(
        environment=values,
        package_version=runtime.package_version,
        playwright_version=runtime.playwright_version,
        l1_task_count=runtime.l1_task_count if runtime.l1_task_count else None,
    )
    errors = tuple(dict.fromkeys((*runtime.errors, *access.errors)))
    report = {
        "schema_version": "workarena-l1-preflight-v2",
        "official_track": True,
        "oracle_used": False,
        "runtime": asdict(runtime),
        "instance_source": access.instance_source,
        "ready": runtime.ready and access.ready,
        "errors": errors,
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

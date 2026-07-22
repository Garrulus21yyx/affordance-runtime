import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _launcher_module():
    path = Path(__file__).parents[1] / "scripts" / "run_browsergym_generalist.py"
    spec = importlib.util.spec_from_file_location("browsergym_launcher", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_loads_literal_dotenv_without_overriding_exported_values(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# local only\nLLM_ZHIPU_API_KEY='local-key'\nLLM_ZHIPU_BASE_URL=https://example.test\nINVALID LINE\n",
        encoding="utf-8",
    )

    environment = _launcher_module()._local_dotenv_environment(
        dotenv,
        {"LLM_ZHIPU_API_KEY": "exported-key", "KEEP": "1"},
    )

    assert environment["LLM_ZHIPU_API_KEY"] == "exported-key"
    assert environment["LLM_ZHIPU_BASE_URL"] == "https://example.test"
    assert environment["KEEP"] == "1"
    assert "INVALID" not in environment


def test_launcher_excludes_concurrent_runs_for_the_same_output(tmp_path: Path) -> None:
    launcher = _launcher_module()
    first = launcher._acquire_output_run_lock(tmp_path / "same-output")
    try:
        with pytest.raises(launcher.OutputRunLockedError, match="already in use"):
            launcher._acquire_output_run_lock(tmp_path / "same-output")
    finally:
        launcher._release_output_run_lock(first)

    next_run = launcher._acquire_output_run_lock(tmp_path / "same-output")
    launcher._release_output_run_lock(next_run)


def test_launcher_allows_distinct_output_directories(tmp_path: Path) -> None:
    launcher = _launcher_module()
    first = launcher._acquire_output_run_lock(tmp_path / "first")
    second = launcher._acquire_output_run_lock(tmp_path / "second")
    launcher._release_output_run_lock(second)
    launcher._release_output_run_lock(first)


def test_launcher_runtime_lock_serializes_distinct_output_directories(tmp_path: Path) -> None:
    launcher = _launcher_module()
    first = launcher._acquire_runtime_run_lock(tmp_path / "runtime")
    try:
        with pytest.raises(launcher.OutputRunLockedError, match="matrix is already running"):
            launcher._acquire_runtime_run_lock(tmp_path / "runtime")
    finally:
        launcher._release_output_run_lock(first)


def test_launcher_process_fails_before_preflight_when_output_is_locked(tmp_path: Path) -> None:
    launcher = _launcher_module()
    output = tmp_path / "locked-output"
    first = launcher._acquire_output_run_lock(output)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "scripts" / "run_browsergym_generalist.py"),
                "--output",
                str(output),
                "--preflight-only",
                "--runtime-python",
                str(tmp_path / "missing-python"),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "XDG_RUNTIME_DIR": str(tmp_path / "runtime")},
        )
    finally:
        launcher._release_output_run_lock(first)

    assert completed.returncode == 2
    assert "already in use" in completed.stderr
    assert "interpreter is not executable" not in completed.stderr

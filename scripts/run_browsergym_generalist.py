#!/usr/bin/env python3
"""The sole launch path for an isolated BrowserGym Generalist matrix."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TextIO

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from affordance_runtime.benchmarks.browsergym_runtime import (  # noqa: E402
    BROWSERGYM_RUNTIME_PYTHON_ENV,
    configured_browsergym_python,
    inspect_browsergym_runtime,
)
from affordance_runtime.provider_preflight import inspect_ollama_gpu  # noqa: E402

_DOTENV_ASSIGNMENT = re.compile(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)")


class OutputRunLockedError(RuntimeError):
    pass


def _acquire_lock(path: Path, *, occupied_message: str) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise OutputRunLockedError(occupied_message) from exc
    lock.seek(0)
    lock.truncate()
    lock.write(f"pid={os.getpid()}\n")
    lock.flush()
    return lock


def _acquire_output_run_lock(directory: Path) -> TextIO:
    """Hold one non-blocking writer lock for a checkpoint/output directory."""

    directory.mkdir(parents=True, exist_ok=True)
    return _acquire_lock(
        directory / ".browsergym-run.lock",
        occupied_message=f"BrowserGym output directory is already in use: {directory}",
    )


def _acquire_runtime_run_lock(runtime_dir: Path | None = None) -> TextIO:
    """Serialize local BrowserGym matrices that share one provider/device."""

    if runtime_dir is None:
        configured = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        runtime_dir = Path(configured) if configured else Path(f"/tmp/affordance-runtime-{os.getuid()}")
    runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return _acquire_lock(
        runtime_dir / "browsergym-generalist.lock",
        occupied_message="another BrowserGym Generalist matrix is already running for this user",
    )


def _release_output_run_lock(lock: TextIO) -> None:
    try:
        lock.seek(0)
        lock.truncate()
        lock.flush()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    finally:
        lock.close()


def _local_dotenv_environment(path: Path, inherited: dict[str, str]) -> dict[str, str]:
    """Read literal local dotenv assignments without evaluating shell syntax.

    Explicit process variables win. Values stay only in the child process
    environment; this launcher never prints or writes them.
    """

    environment = dict(inherited)
    if not path.is_file():
        return environment
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _DOTENV_ASSIGNMENT.fullmatch(line)
        if match is None:
            continue
        name, value = match.groups()
        value = value.strip()
        if len(value) >= 2 and value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        environment.setdefault(name, value)
    return environment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-python", type=Path, help=f"override ${BROWSERGYM_RUNTIME_PYTHON_ENV}")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--profile", choices=("smoke", "pr", "diagnostic", "nightly", "release"), default="smoke")
    parser.add_argument(
        "--planner-profile",
        choices=("strict-generalist", "historical-compatibility"),
        default="strict-generalist",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument("--seed-count", type=int)
    parser.add_argument("--visual-grounding", action="store_true")
    parser.add_argument("--episode-timeout-s", type=float, default=165.0)
    parser.add_argument("--model-call-timeout-s", type=float, default=10.0)
    parser.add_argument("--max-model-calls", type=int, default=15)
    parser.add_argument("--execution-reserve-s", type=float, default=15.0)
    args = parser.parse_args()

    repository_root = REPOSITORY_ROOT
    try:
        runtime_lock = _acquire_runtime_run_lock()
    except OutputRunLockedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        try:
            output_lock = _acquire_output_run_lock(args.output)
        except OutputRunLockedError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        try:
            environment = _local_dotenv_environment(repository_root / ".env", dict(os.environ))
            runtime_python = args.runtime_python or configured_browsergym_python(environment)
            preflight = inspect_browsergym_runtime(runtime_python, repository_root=repository_root)
            (args.output / "browsergym-runtime-preflight.json").write_text(
                json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            local_provider = environment.get("LLM_LOCAL_PROVIDER", "ollama").strip().lower().replace("-", "_")
            if local_provider == "ollama":
                ollama_preflight = inspect_ollama_gpu(
                    base_url=environment.get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434").removesuffix("/v1"),
                    model=(
                        environment.get("LLM_LOCAL_MODEL_ID")
                        or environment.get("LLM_LOCAL_MODEL")
                        or "qwen2.5:7b"
                    ),
                    container_name=environment.get("LLM_LOCAL_OLLAMA_CONTAINER", "ollama"),
                )
                (args.output / "ollama-gpu-preflight.json").write_text(
                    json.dumps(ollama_preflight.to_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                if not ollama_preflight.ready:
                    print(
                        "local Ollama GPU preflight failed: " + ", ".join(ollama_preflight.errors),
                        file=sys.stderr,
                    )
                    return 1
            if args.preflight_only:
                print(json.dumps(preflight, indent=2, sort_keys=True))
                return 0
            environment["PYTHONPATH"] = str(repository_root / "src")
            environment["LLM_ACTIVE_PROFILE"] = "local"
            command = [
                preflight["sys_executable"],
                "-m",
                "affordance_runtime",
                "benchmark-browsergym-generalist",
                "--output",
                str(args.output),
                "--profile",
                args.profile,
                "--planner-profile",
                args.planner_profile,
                "--episode-timeout-s",
                str(args.episode_timeout_s),
                "--model-call-timeout-s",
                str(args.model_call_timeout_s),
                "--max-model-calls",
                str(args.max_model_calls),
                "--execution-reserve-s",
                str(args.execution_reserve_s),
            ]
            if args.resume:
                command.append("--resume")
            for task_id in args.task:
                command.extend(("--task", task_id))
            if args.seed_count is not None:
                command.extend(("--seed-count", str(args.seed_count)))
            if args.visual_grounding:
                command.append("--visual-grounding")
            return subprocess.run(command, cwd=repository_root, env=environment, check=False).returncode
        finally:
            _release_output_run_lock(output_lock)
    finally:
        _release_output_run_lock(runtime_lock)


if __name__ == "__main__":
    raise SystemExit(main())

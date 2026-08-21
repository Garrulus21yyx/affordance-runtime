"""Narrow fixed-suite target-loop benchmark command."""

import argparse
import asyncio
import json
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from affordance_runtime.benchmarks.target_loop.detached_run import (
    detached_status,
    launch_detached,
)
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.result_store import (
    SQLiteRunResultStore,
)
from affordance_runtime.benchmarks.target_loop.runner import (
    abandon_detached_watchdog_tasks,
    run_suite,
)
from affordance_runtime.benchmarks.webarena_verified import (
    inspect_webarena_verified_w1b_world,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite")
    parser.add_argument("--profile")
    parser.add_argument("--case-id")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--w1b-world", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--detach", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(detached_status(args.output_dir), indent=2, sort_keys=True))
        return 0
    if args.w1b_world:
        result = asyncio.run(
            inspect_webarena_verified_w1b_world(Path(args.output_dir), seed=args.seed)
        )
        return 0 if result["ready"] else 1
    if not args.suite or not args.profile:
        parser.error("--suite and --profile are required unless --w1b-world is used")
    manifest = get_manifest(args.suite, args.profile, args.seed)
    if args.case_id:
        cases = tuple(item for item in manifest.cases if item.case_id == args.case_id)
        if not cases:
            parser.error("case ID is not part of the selected fixed manifest")
        manifest = replace(manifest, cases=cases)
    if args.detach:
        identity = launch_detached(
            _foreground_command(args),
            args.output_dir,
            cwd=Path.cwd(),
        )
        print(
            json.dumps(
                {
                    "state": "started",
                    "pid": identity.pid,
                    "session_id": identity.session_id,
                    "output_dir": identity.output_dir,
                    "log_path": identity.log_path,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    return _run_foreground_benchmark(manifest, Path(args.output_dir))


def _run_foreground_benchmark(manifest, output_dir: Path) -> int:
    """Run with bounded shutdown for tasks already detached by the watchdog."""

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_benchmark(manifest, output_dir))
    finally:
        abandon_detached_watchdog_tasks(loop)
        loop.close()
        asyncio.set_event_loop(None)


def _foreground_command(args) -> tuple[str, ...]:
    command = [
        sys.executable,
        "-m",
        "affordance_runtime.benchmarks.target_loop.cli",
        "--suite",
        args.suite,
        "--profile",
        args.profile,
        "--seed",
        str(args.seed),
        "--output-dir",
        str(Path(args.output_dir).resolve()),
    ]
    if args.case_id:
        command.extend(("--case-id", args.case_id))
    return tuple(command)


async def _run_benchmark(manifest, output_dir: Path) -> int:
    interruption_requested = asyncio.Event()
    received_signal: list[int] = []
    loop = asyncio.get_running_loop()
    status = {"phase": "running"}

    def status_changed(phase: str) -> None:
        status["phase"] = phase

    def request_interruption(signum: int) -> None:
        if not received_signal:
            received_signal.append(signum)
            print(
                f"benchmark interruption requested signal={signal.Signals(signum).name}",
                flush=True,
            )
        interruption_requested.set()

    installed = []
    for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, request_interruption, signum)
            installed.append(signum)
        except (NotImplementedError, RuntimeError):
            continue

    heartbeat = asyncio.create_task(_heartbeat(lambda: status["phase"]))
    try:
        result = await run_suite(
            manifest,
            trace_dir=output_dir,
            interruption_requested=interruption_requested,
            status_changed=status_changed,
        )
        store = SQLiteRunResultStore(output_dir / "run-results.sqlite3")
        store.commit_run_report(result)
        store.export_run_report(result.identity.run_id, output_dir)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        for signum in installed:
            loop.remove_signal_handler(signum)
    if received_signal:
        return 128 + received_signal[0]
    return 0 if result.acceptance.accepted else 1


async def _heartbeat(
    phase: Callable[[], str] = lambda: "running",
    interval_s: float = 30.0,
) -> None:
    started = time.monotonic()
    while True:
        await asyncio.sleep(interval_s)
        print(
            f"benchmark heartbeat phase={phase()} elapsed_s={int(time.monotonic() - started)}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI for deterministic local MiniWoB breadth diagnostics without a policy."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.diagnostics import run_local_diagnostics


def main() -> int:
    _initialize_runtime_imports()
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--archive", type=Path, required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.seed != 7:
        raise ValueError("M4.4 diagnostics require historical seed 7")
    source = os.environ.get("MINIWOB_SOURCE_DIR", "").strip()
    asyncio.run(
        run_local_diagnostics(
            args.archive, args.seed, args.output_dir, Path(source) if source else None,
        ),
    )
    return 0


def _initialize_runtime_imports() -> None:
    import affordance_runtime.agent  # noqa: F401, PLC0415


if __name__ == "__main__":
    raise SystemExit(main())

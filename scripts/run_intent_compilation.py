#!/usr/bin/env python3
"""Run the controlled intent-compilation suite with configured model profiles."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from affordance_runtime.benchmarks.intent_compilation import controlled_intent_cases, run_intent_compilation_suite
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import model_port_from_environment


async def _run(output: Path) -> None:
    compiler = LLMIntentCompiler(model_port_from_environment())
    report = await run_intent_compilation_suite(compiler, controlled_intent_cases())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

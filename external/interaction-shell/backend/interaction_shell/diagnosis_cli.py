from __future__ import annotations

import argparse
from pathlib import Path

from .diagnosis import BenchmarkResultExport, CaseDiagnosisProjector, PublicTraceExport


def main() -> int:
    parser = argparse.ArgumentParser(description="Project public benchmark/trace exports")
    parser.add_argument("result", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = BenchmarkResultExport.model_validate_json(args.result.read_text())
    trace = PublicTraceExport.model_validate_json(args.trace.read_text())
    diagnosis = CaseDiagnosisProjector().project(result, trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(diagnosis.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

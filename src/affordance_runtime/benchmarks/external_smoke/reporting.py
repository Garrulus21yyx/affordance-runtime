"""Secret-free external preflight and execution report serialization."""

import json
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.contracts import (
    ExternalBenchmarkAdmission,
    ExternalBenchmarkAdmissionEvidence,
    ExternalSmokeExecution,
)


def write_preflight_report(
    output: Path,
    evidence: ExternalBenchmarkAdmissionEvidence,
    admission: ExternalBenchmarkAdmission,
    execution: ExternalSmokeExecution,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "schema_version": "external-smoke-preflight.v1",
        "evidence": asdict(evidence),
        "admission": asdict(admission),
        "execution": asdict(execution),
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8")

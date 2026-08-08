"""Triple-gated external execution entry; no environment is built during preflight."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

from affordance_runtime.benchmarks.external_smoke.contracts import (
    ExternalBenchmarkAdmission,
    ExternalSmokeExecution,
    ExternalSmokeManifest,
)


def run_external_smoke(
    admission: ExternalBenchmarkAdmission,
    manifest: ExternalSmokeManifest,
    *,
    execute: bool,
    executor: Callable[[ExternalSmokeManifest], Sequence[object]],
) -> ExternalSmokeExecution:
    errors = list(admission.errors)
    if not admission.admitted:
        return ExternalSmokeExecution(False, "not_run", tuple(errors))
    if os.environ.get("RUN_EXTERNAL_SMOKE") != "1":
        errors.append("RUN_EXTERNAL_SMOKE=1 is required")
    if not execute:
        errors.append("explicit --execute is required")
    if errors:
        return ExternalSmokeExecution(False, "not_run", tuple(errors))
    results = tuple(executor(manifest))
    return ExternalSmokeExecution(True, "executed_fixed_manifest", (), len(results))

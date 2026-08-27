from __future__ import annotations

import pytest
from interaction_shell.diagnosis import (
    BenchmarkResultExport,
    CaseDiagnosisProjector,
    PublicTraceExport,
    TraceStep,
    project_fail_open,
)


def result(**updates):
    values = dict(
        schema_version="benchmark.v1",
        case_id="case-1",
        status="failed",
        success=False,
        terminal_stage="control",
        terminal_code="no_progress",
        complete_request_tokens=700,
        effective_input_limit=1000,
    )
    values.update(updates)
    return BenchmarkResultExport(**values)


def trace():
    return PublicTraceExport(
        schema_version="trace.v1",
        case_id="case-1",
        steps=(
            TraceStep(step=1, stage="policy", progress=True, evidence_refs=("trace:1",)),
            TraceStep(step=2, stage="control", abnormal=True, evidence_refs=("trace:2",)),
        ),
    )


def test_deterministic_projection_preserves_owner_terminal_and_unknown_cause():
    projector = CaseDiagnosisProjector()
    first = projector.project(result(), trace())
    second = projector.project(result(), trace())
    assert first == second
    assert (first.terminal_stage, first.terminal_code) == ("control", "no_progress")
    assert first.likely_upstream_stage == "unknown"
    assert first.first_abnormal_step == 2
    assert first.last_progress_step == 1


@pytest.mark.parametrize(
    ("updates", "classification"),
    [
        ({"context_capacity_rejections": 1}, "capacity_failure"),
        ({"complete_request_tokens": 1001}, "capacity_failure"),
        ({"complete_request_tokens": 900}, "pressure"),
        ({"complete_request_tokens": 400, "compaction_count": 2}, "pressure"),
        ({"complete_request_tokens": 400, "history_tokens": 700}, "pressure"),
        ({"complete_request_tokens": 400}, "healthy"),
        ({"complete_request_tokens": None, "effective_input_limit": None}, "unknown"),
    ],
)
def test_context_capacity_requires_owner_evidence_while_pressure_does_not(updates, classification):
    diagnosis = CaseDiagnosisProjector().project(result(**updates), trace())
    assert diagnosis.context_health.classification == classification


def test_explicit_upstream_origin_still_requires_linked_evidence():
    diagnosis = CaseDiagnosisProjector().project(result(failure_origin="policy"), trace())
    assert diagnosis.likely_upstream_stage == "policy"
    assert diagnosis.confidence == 0.8
    assert "trace:2" in diagnosis.evidence_refs


class BrokenSink:
    async def project(self, diagnosis):
        raise RuntimeError("Langfuse unavailable")


@pytest.mark.asyncio
async def test_langfuse_unavailable_is_fail_open():
    diagnosis = CaseDiagnosisProjector().project(result(), trace())
    assert await project_fail_open(diagnosis, BrokenSink()) is False
    assert diagnosis.terminal_code == "no_progress"

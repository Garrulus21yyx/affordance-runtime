from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ExportModel(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class EvidenceRef(ExportModel):
    ref: str
    step: int | None = Field(default=None, ge=1)
    stage: str | None = None


class TraceStep(ExportModel):
    step: int = Field(ge=1)
    stage: str
    progress: bool = False
    abnormal: bool = False
    provider_attempts: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    recoveries: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    evidence_refs: tuple[str, ...] = ()


class BenchmarkResultExport(ExportModel):
    schema_version: str
    case_id: str
    status: str
    success: bool | None = None
    terminal_stage: str = "unknown"
    terminal_code: str = "unknown"
    failure_origin: str | None = None
    reporting_failure_code: str | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    model_latency_ms: float = Field(default=0, ge=0)
    runtime_latency_ms: float = Field(default=0, ge=0)
    no_progress_count: int = Field(default=0, ge=0)
    cycle_count: int = Field(default=0, ge=0)
    context_capacity_rejections: int = Field(default=0, ge=0)
    complete_request_tokens: int | None = Field(default=None, ge=0)
    effective_input_limit: int | None = Field(default=None, gt=0)
    history_tokens: int = Field(default=0, ge=0)
    compaction_count: int = Field(default=0, ge=0)


class PublicTraceExport(ExportModel):
    schema_version: str
    case_id: str
    steps: tuple[TraceStep, ...] = ()


class ContextHealth(ExportModel):
    classification: Literal["healthy", "pressure", "capacity_failure", "unknown"]
    fill_ratio: float | None = Field(default=None, ge=0)
    capacity_rejections: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = ()


class TrajectoryMetrics(ExportModel):
    steps: int = Field(ge=0)
    provider_attempts: int = Field(ge=0)
    retries: int = Field(ge=0)
    recoveries: int = Field(ge=0)
    no_progress_count: int = Field(ge=0)
    cycle_count: int = Field(ge=0)
    model_latency_ms: float = Field(ge=0)
    runtime_latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class CaseDiagnosis(ExportModel):
    schema_version: Literal["interaction-shell.diagnosis.v1"] = "interaction-shell.diagnosis.v1"
    case_id: str
    status: str
    success: bool | None
    terminal_stage: str
    terminal_code: str
    first_abnormal_step: int | None
    last_progress_step: int | None
    likely_upstream_stage: str
    confidence: float = Field(ge=0, le=1)
    context_health: ContextHealth
    trajectory_metrics: TrajectoryMetrics
    evidence_refs: tuple[str, ...]


class CaseDiagnosisProjector:
    """Deterministic non-authoritative diagnosis over versioned public exports."""

    def project(self, result: BenchmarkResultExport, trace: PublicTraceExport) -> CaseDiagnosis:
        if result.case_id != trace.case_id:
            raise ValueError("result and trace case identity differ")
        steps = tuple(sorted(trace.steps, key=lambda item: item.step))
        if len({item.step for item in steps}) != len(steps):
            raise ValueError("trace step identity must be unique")
        abnormal = next((item for item in steps if item.abnormal), None)
        progress = [item for item in steps if item.progress]
        context = self._context_health(result)
        likely, confidence, diagnostic_refs = self._likely_stage(result, abnormal)
        refs = tuple(
            dict.fromkeys(
                [ref for item in steps for ref in item.evidence_refs]
                + list(context.evidence_refs)
                + list(diagnostic_refs)
            )
        )
        return CaseDiagnosis(
            case_id=result.case_id,
            status=result.status,
            success=result.success,
            terminal_stage=result.terminal_stage or "unknown",
            terminal_code=result.terminal_code or "unknown",
            first_abnormal_step=abnormal.step if abnormal else None,
            last_progress_step=progress[-1].step if progress else None,
            likely_upstream_stage=likely,
            confidence=confidence,
            context_health=context,
            trajectory_metrics=TrajectoryMetrics(
                steps=len(steps),
                provider_attempts=sum(item.provider_attempts for item in steps),
                retries=sum(item.retries for item in steps),
                recoveries=sum(item.recoveries for item in steps),
                no_progress_count=result.no_progress_count,
                cycle_count=result.cycle_count,
                model_latency_ms=result.model_latency_ms,
                runtime_latency_ms=result.runtime_latency_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
            ),
            evidence_refs=refs,
        )

    @staticmethod
    def _context_health(result: BenchmarkResultExport) -> ContextHealth:
        complete = result.complete_request_tokens
        limit = result.effective_input_limit
        if result.context_capacity_rejections > 0 or (complete is not None and limit is not None and complete > limit):
            ratio = complete / limit if complete is not None and limit else None
            refs = ("request_budget.capacity",)
            return ContextHealth(
                classification="capacity_failure",
                fill_ratio=ratio,
                capacity_rejections=result.context_capacity_rejections,
                evidence_refs=refs,
            )
        if complete is None or limit is None:
            return ContextHealth(classification="unknown", fill_ratio=None, capacity_rejections=0)
        ratio = complete / limit
        pressure = ratio >= 0.8 or result.compaction_count > 0 or result.history_tokens > limit // 2
        return ContextHealth(
            classification="pressure" if pressure else "healthy",
            fill_ratio=ratio,
            capacity_rejections=0,
            evidence_refs=("request_budget",),
        )

    @staticmethod
    def _likely_stage(result: BenchmarkResultExport, abnormal: TraceStep | None):
        # Only an explicit exported failure origin supports upstream attribution.
        if result.failure_origin in {
            "perception",
            "policy",
            "grounding",
            "binding",
            "execution",
            "evaluation",
        }:
            refs = abnormal.evidence_refs if abnormal else ()
            if refs:
                return result.failure_origin, 0.8, refs
        # Control terminal facts do not make Monitor an upstream cause.
        return "unknown", 0.0, ()


class DiagnosisSink(Protocol):
    async def project(self, diagnosis: CaseDiagnosis) -> None: ...


async def project_fail_open(diagnosis: CaseDiagnosis, sink: DiagnosisSink | None) -> bool:
    if sink is None:
        return False
    try:
        await sink.project(diagnosis)
        return True
    except Exception:  # noqa: BLE001 - optional external projection is intentionally fail-open
        return False

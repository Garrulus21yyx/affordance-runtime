"""Bounded, non-authoritative analysis over benchmark-owned result and trace facts."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.runtime_failure import FailureStage
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    TerminalReasonCode,
)
from affordance_runtime.evaluation import TaskOutcomeKind

ANALYSIS_SCHEMA_VERSION = "target-loop-analysis.v2"

PROVIDER_USAGE_METRICS = ("prompt_tokens", "completion_tokens", "total_tokens")
MODEL_TIMING_METRICS = ("model_latency_ms",)
REQUEST_ADMISSION_METRICS = (
    "system_tokens",
    "actor_world_tokens",
    "history_tokens",
    "tool_schema_tokens",
    "image_estimated_tokens",
    "repair_tokens",
    "estimated_input_tokens",
    "output_reserve_tokens",
    "complete_request_tokens",
    "effective_input_limit",
    "context_capacity_rejections",
)
RUNTIME_MECHANICAL_METRICS = (
    "turns",
    "effectful_dispatches",
    "provider_retry_count",
    "action_policy_recovery_calls",
    "representation_repair_calls",
    "control_stall_count",
    "state_oscillation_count",
)


class BadCaseCategory(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    STRUCTURED_OUTPUT_INVALID = "structured_output_invalid"
    PROVIDER_FAILURE = "provider_failure"
    CONTROL_STALL = "control_stall"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"
    HARNESS_TIMEOUT = "harness_timeout"
    EXTERNAL_INTERRUPTION = "external_interruption"
    ACQUISITION_FAILURE = "acquisition_failure"
    EXECUTION_FAILURE = "execution_failure"
    EVALUATION_FAILURE = "evaluation_failure"
    NATIVE_TASK_FAILURE = "native_task_failure"
    RUNTIME_REJECTED = "runtime_rejected"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    CANCELLED = "cancelled"
    CLEANUP_FAILURE = "cleanup_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    EVIDENCE_FAILURE = "evidence_failure"
    UNCLASSIFIED_TYPED_FAILURE = "unclassified_typed_failure"


@dataclass(frozen=True)
class BadCasePresentation:
    applicable: bool
    category: BadCaseCategory
    stage: str = ""
    origin: str = ""
    code: str = ""
    termination_source: str = ""
    summary: str = ""
    evidence_refs: tuple[str, ...] = ()


def project_bad_case(result: BenchmarkCaseResult) -> BadCasePresentation:
    """Project display facts without changing benchmark truth or parsing prose."""

    facts = result.failure_facts
    runtime = facts.runtime_failure
    stage = runtime.stage.value if runtime is not None else ""
    origin = facts.component_origin.value
    code = result.case_failure_code or (
        result.terminal_reason_code.value if result.terminal_reason_code is not None else ""
    )
    refs: list[str] = []
    if runtime is not None:
        refs.append("case:failure_facts.runtime_failure")
    if facts.policy_failure_code:
        refs.append("case:failure_facts.policy_failure_code")
    if facts.component_origin is not CaseFailureOrigin.NONE:
        refs.append("case:failure_facts.component_origin")
    if result.terminal_reason_code is not None:
        refs.append("case:terminal_reason_code")

    if result.status == "done" and not facts.cleanup_code:
        return BadCasePresentation(False, BadCaseCategory.NOT_APPLICABLE)
    if facts.harness_integrity_code:
        return _bad_case(
            BadCaseCategory.EVIDENCE_FAILURE,
            result,
            stage="harness",
            origin="harness_integrity",
            code=facts.harness_integrity_code,
            summary="Persisted benchmark evidence failed its integrity contract.",
            refs=(*refs, "case:failure_facts.harness_integrity_code"),
        )
    if facts.watchdog_code:
        return _bad_case(
            BadCaseCategory.HARNESS_TIMEOUT,
            result,
            stage="harness",
            origin=CaseFailureOrigin.HARNESS_WATCHDOG.value,
            code=facts.watchdog_code,
            summary="The benchmark watchdog stopped the case after its time limit.",
            refs=(*refs, "case:failure_facts.watchdog_code"),
        )
    if facts.component_origin is CaseFailureOrigin.HARNESS_EXTERNAL_INTERRUPTION:
        return _bad_case(
            BadCaseCategory.EXTERNAL_INTERRUPTION,
            result,
            stage="harness",
            origin=origin,
            code=facts.component_code,
            summary="The harness received an external stop request.",
            refs=refs,
        )
    if result.status == "cancelled" or (runtime is not None and runtime.kind.value == "cancelled"):
        return _bad_case(
            BadCaseCategory.CANCELLED,
            result,
            stage=stage or "session",
            origin=origin,
            code=code or "cancelled",
            summary="The run was cancelled before the native verifier completed it.",
            refs=refs,
        )
    if facts.policy_failure_code in {
        ModelFailureKind.INVALID_RESPONSE.value,
        ModelFailureKind.SCHEMA_ERROR.value,
    }:
        summary = (
            "The model returned an invalid response after bounded repair."
            if facts.policy_failure_code == ModelFailureKind.INVALID_RESPONSE.value
            else "The model output did not satisfy the required schema after bounded repair."
        )
        return _bad_case(
            BadCaseCategory.STRUCTURED_OUTPUT_INVALID,
            result,
            stage=FailureStage.POLICY.value,
            origin="action_policy",
            code=facts.policy_failure_code,
            termination_source="action_policy",
            summary=summary,
            refs=refs,
        )
    if facts.policy_failure_code in {
        ModelFailureKind.PROVIDER_UNAVAILABLE.value,
        ModelFailureKind.PROVIDER_EXHAUSTED.value,
        ModelFailureKind.TIMEOUT.value,
        ModelFailureKind.REFUSED.value,
    }:
        return _bad_case(
            BadCaseCategory.PROVIDER_FAILURE,
            result,
            stage=FailureStage.POLICY.value,
            origin="model_provider",
            code=facts.policy_failure_code,
            termination_source="model_provider",
            summary="The model provider did not return an admissible decision.",
            refs=refs,
        )

    reason = result.terminal_reason_code
    if reason is TerminalReasonCode.CONTROL_STALLED:
        oscillations = _measurement(result, "state_oscillation_count")
        summary = (
            "State oscillation exhausted the Runtime monitor recovery path."
            if oscillations > 0
            else "Repeated control attempts made no progress and the Runtime monitor stopped the run."
        )
        return _bad_case(
            BadCaseCategory.CONTROL_STALL,
            result,
            stage=FailureStage.CONTROL.value,
            origin="runtime_control",
            code=TerminalReasonCode.CONTROL_STALLED.value,
            termination_source=result.control_termination_owner or "runtime_control",
            summary=summary,
            refs=refs,
        )
    if reason in {
        TerminalReasonCode.NO_PROGRESS_REPETITION,
        TerminalReasonCode.NO_PROGRESS_CONTROL_REPETITION,
    }:
        return _bad_case(
            BadCaseCategory.NO_PROGRESS,
            result,
            stage=FailureStage.CONTROL.value,
            origin="runtime_control",
            code=reason.value if reason is not None else "",
            termination_source=result.control_termination_owner or "runtime_control",
            summary="The run repeated equivalent actions or control states without progress.",
            refs=refs,
        )
    if reason in {
        TerminalReasonCode.TURN_BUDGET_EXHAUSTED,
        TerminalReasonCode.WAIT_BUDGET_EXHAUSTED,
    }:
        return _bad_case(
            BadCaseCategory.BUDGET_EXHAUSTED,
            result,
            stage=FailureStage.CONTROL.value,
            origin="runtime_control",
            code=reason.value if reason is not None else "",
            termination_source=result.control_termination_owner or "core_transition",
            summary="The Runtime exhausted the bounded turn or wait budget.",
            refs=refs,
        )
    if facts.task_outcome_kind == TaskOutcomeKind.TERMINAL_FAILURE.value:
        return _bad_case(
            BadCaseCategory.NATIVE_TASK_FAILURE,
            result,
            stage=FailureStage.EVALUATION.value,
            origin="native_verifier",
            code=facts.task_outcome_code,
            termination_source="native_verifier",
            summary="The native verifier reported that the task failed.",
            refs=(*refs, "case:failure_facts.task_outcome_kind"),
        )
    if result.status == "waiting_user":
        return _bad_case(
            BadCaseCategory.WAITING_USER,
            result,
            stage="control",
            origin="runtime_control",
            code=result.pending_kind or "waiting_user",
            summary="The run needs user-owned information or effect resolution.",
            refs=(*refs, "case:pending_kind"),
        )
    if result.status == "waiting_confirmation":
        return _bad_case(
            BadCaseCategory.WAITING_CONFIRMATION,
            result,
            stage="control",
            origin="runtime_control",
            code=result.pending_kind or "confirmation",
            summary="The run stopped at a required confirmation boundary.",
            refs=(*refs, "case:pending_kind"),
        )
    if runtime is not None:
        category = {
            FailureStage.ACQUISITION: BadCaseCategory.ACQUISITION_FAILURE,
            FailureStage.EXECUTION: BadCaseCategory.EXECUTION_FAILURE,
            FailureStage.EVALUATION: BadCaseCategory.EVALUATION_FAILURE,
        }.get(runtime.stage, BadCaseCategory.RUNTIME_REJECTED)
        return _bad_case(
            category,
            result,
            stage=stage,
            origin="runtime",
            code=runtime.code,
            summary=f"The Runtime stopped in the {stage} stage with a typed {runtime.kind.value} outcome.",
            refs=refs,
        )
    if facts.component_origin in {
        CaseFailureOrigin.ENVIRONMENT_FACTORY,
        CaseFailureOrigin.TASK_FACTORY,
        CaseFailureOrigin.COMPOSITION_FACTORY,
        CaseFailureOrigin.LOOP_CONSTRUCTION,
        CaseFailureOrigin.SESSION_START,
        CaseFailureOrigin.ENVIRONMENT_RESET,
    }:
        return _bad_case(
            BadCaseCategory.ENVIRONMENT_FAILURE,
            result,
            stage="environment",
            origin=origin,
            code=facts.component_code,
            summary="The benchmark environment or task composition could not start.",
            refs=refs,
        )
    if facts.component_origin is CaseFailureOrigin.EXECUTION:
        category = BadCaseCategory.EXECUTION_FAILURE
    elif facts.component_origin in {
        CaseFailureOrigin.ACTION_EVALUATION,
        CaseFailureOrigin.TASK_EVALUATION,
    }:
        category = BadCaseCategory.EVALUATION_FAILURE
    elif facts.component_origin in {
        CaseFailureOrigin.INITIAL_OBSERVATION,
        CaseFailureOrigin.OBSERVATION_PROJECTION,
        CaseFailureOrigin.POST_ACTION_OBSERVATION,
    }:
        category = BadCaseCategory.ACQUISITION_FAILURE
    else:
        category = BadCaseCategory.UNCLASSIFIED_TYPED_FAILURE
    if facts.cleanup_code and result.status == "done":
        category = BadCaseCategory.CLEANUP_FAILURE
        origin = "cleanup"
        code = facts.cleanup_code
    return _bad_case(
        category,
        result,
        stage=stage,
        origin=origin,
        code=code,
        summary="The run ended with a typed failure; inspect the linked evidence for details.",
        refs=refs,
    )


def _bad_case(
    category: BadCaseCategory,
    result: BenchmarkCaseResult,
    *,
    stage: str,
    origin: str,
    code: str,
    summary: str,
    refs: Sequence[str],
    termination_source: str = "",
) -> BadCasePresentation:
    return BadCasePresentation(
        True,
        category,
        stage[:80],
        origin[:96],
        code[:96],
        termination_source[:96],
        summary[:240],
        tuple(dict.fromkeys(refs))[:12],
    )


def project_case_analysis(result: BenchmarkCaseResult) -> dict[str, object]:
    """Copy facts from their owners without deriving evaluation or billing truth."""

    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "identity": {
            "run_id": result.run_id,
            "run_attempt_id": result.run_attempt_id,
            "suite_id": result.suite_id,
            "profile_id": result.profile_id,
            "case_id": result.case_id,
            "seed": result.seed,
            "manifest_digest": result.manifest_digest,
        },
        "evaluator_truth": {
            "status": result.status,
            "execution_completed": result.execution_completed,
            "terminal_reason_code": (
                result.terminal_reason_code.value if result.terminal_reason_code is not None else ""
            ),
            "latest_task_status": result.latest_task_status,
        },
        "bad_case": _json_value(asdict(project_bad_case(result))),
        "provider_usage": _measurements(result, PROVIDER_USAGE_METRICS),
        "model_timing": _measurements(result, MODEL_TIMING_METRICS),
        "request_admission_estimate": {
            **_measurements(result, REQUEST_ADMISSION_METRICS),
            "semantics": "capacity_estimate_not_provider_usage_or_cost",
        },
        "runtime_mechanical": {
            **_measurements(result, RUNTIME_MECHANICAL_METRICS),
            "no_progress_count": result.no_progress_count,
        },
        "local_evidence": {
            "case_result": f"cases/{result.case_id}.json",
            "trace": f"traces/{result.case_id}/trace.jsonl",
            "artifacts": f"traces/{result.case_id}/artifacts/",
        },
        "langfuse_locator": {
            "session_id": result.run_attempt_id,
            "case_tag": f"case_id:{result.case_id}",
        },
    }


def export_case_analysis(analysis: Mapping[str, object], run_directory: Path) -> Path:
    """Atomically persist a non-authoritative read model beside result evidence."""

    identity = analysis.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("case analysis identity is unavailable")
    case_id = str(identity.get("case_id", ""))
    if not case_id or Path(case_id).name != case_id:
        raise ValueError("case analysis identity is invalid")
    directory = Path(run_directory).resolve() / "analysis"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{case_id}.json"
    encoded = json.dumps(dict(analysis), indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{case_id}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return destination


def _measurements(result: BenchmarkCaseResult, names: Sequence[str]) -> dict[str, int | float | None]:
    return {name: result.measurements[name].value if name in result.measurements else None for name in names}


def _measurement(result: BenchmarkCaseResult, name: str) -> int | float:
    value = result.measurements.get(name)
    return value.value if value is not None and value.measured and value.value is not None else 0


def _json_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class TrajectoryComparison:
    run_attempt_id: str
    case_id: str
    task_contract_id: str
    environment_id: str
    profile_id: str
    successful: bool
    turns: int
    prompt_tokens: int
    effectful_dispatches: int
    recovery_count: int
    semantic_page_revisits: int = 0
    semantic_action_revisits: int = 0
    longest_no_progress_span: int = 0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DetourAssessment:
    disposition: Literal["suspected_detour", "not_assessed"]
    comparison_run_attempt_ids: tuple[str, ...] = ()
    measured_deltas: Mapping[str, int] | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrajectoryFacts:
    first_abnormal_step: int | None
    last_progress_step: int | None
    longest_no_progress_span: int
    semantic_action_revisits: int
    public_world_revisits: int
    post_terminal_model_calls: int
    recovery_to_progress_count: int
    evidence_refs: tuple[str, ...]


def derive_trajectory_facts(events: Sequence[Mapping[str, object]]) -> TrajectoryFacts:
    """Derive mechanics only from versioned typed trace fields."""

    sequences = [event.get("sequence") for event in events]
    if any(type(value) is not int or value < 1 for value in sequences) or len(set(sequences)) != len(sequences):
        raise ValueError("trace event sequence must be positive and unique")
    if any(event.get("schema_version") != "gui-agent-trace.v1" for event in events):
        raise ValueError("trace event schema is unsupported")
    ordered = tuple(sorted(events, key=lambda item: _positive_event_int(item, "sequence")))
    first_abnormal = None
    last_progress = None
    longest_no_progress = 0
    current_no_progress = 0
    actions_seen: set[str] = set()
    worlds_seen: set[str] = set()
    action_revisits = 0
    world_revisits = 0
    post_terminal_calls = 0
    terminal_seen = False
    recovery_pending = False
    recovery_to_progress = 0
    refs: list[str] = []
    for event in ordered:
        event_type = event.get("event")
        if event_type == "model_turn" and terminal_seen:
            post_terminal_calls += 1
        if event_type == "native_evaluator_returned" and event.get("evaluation_status") == "complete":
            terminal_seen = True
        if event_type != "step_completed":
            continue
        step = _positive_event_int(event, "step")
        result = event.get("result")
        lineage = event.get("lineage")
        result = result if isinstance(result, Mapping) else {}
        lineage = lineage if isinstance(lineage, Mapping) else {}
        delta = result.get("public_world_delta")
        delta = delta if isinstance(delta, Mapping) else {}
        recovery = result.get("recovery_signal")
        recovery = recovery if isinstance(recovery, Mapping) else {}
        progress = delta.get("changed") is True
        abnormal = bool(recovery) or result.get("runtime_failure") is not None
        if abnormal and first_abnormal is None:
            first_abnormal = step
        if recovery:
            recovery_pending = True
        if progress:
            last_progress = step
            current_no_progress = 0
            if recovery_pending:
                recovery_to_progress += 1
                recovery_pending = False
        else:
            current_no_progress += 1
            longest_no_progress = max(longest_no_progress, current_no_progress)
        action_id = str(lineage.get("action_id", ""))
        if action_id:
            action_revisits += int(action_id in actions_seen)
            actions_seen.add(action_id)
        world_digest = str(lineage.get("after_world_digest", ""))
        if world_digest:
            world_revisits += int(world_digest in worlds_seen)
            worlds_seen.add(world_digest)
        refs.append(f"trace:sequence:{event['sequence']}")
    return TrajectoryFacts(
        first_abnormal,
        last_progress,
        longest_no_progress,
        action_revisits,
        world_revisits,
        post_terminal_calls,
        recovery_to_progress,
        tuple(refs),
    )


def _positive_event_int(event: Mapping[str, object], name: str) -> int:
    value = event.get(name)
    if type(value) is not int or value < 1:
        raise ValueError(f"trace {name} must be a positive integer")
    return value


def assess_suspected_detour(
    candidate: TrajectoryComparison,
    cohort: Sequence[TrajectoryComparison],
) -> DetourAssessment:
    """Compare compatible successful trajectories without claiming optimality."""

    compatible = tuple(
        item
        for item in cohort
        if item.successful
        and item.run_attempt_id != candidate.run_attempt_id
        and item.task_contract_id == candidate.task_contract_id
        and item.environment_id == candidate.environment_id
        and item.profile_id == candidate.profile_id
    )
    if not compatible:
        return DetourAssessment("not_assessed")
    baseline = min(
        compatible,
        key=lambda item: (
            item.turns,
            item.prompt_tokens,
            item.effectful_dispatches,
            item.recovery_count,
            item.run_attempt_id,
        ),
    )
    deltas = {
        "turns": candidate.turns - baseline.turns,
        "prompt_tokens": candidate.prompt_tokens - baseline.prompt_tokens,
        "effectful_dispatches": candidate.effectful_dispatches - baseline.effectful_dispatches,
        "recovery_count": candidate.recovery_count - baseline.recovery_count,
        "semantic_page_revisits": candidate.semantic_page_revisits - baseline.semantic_page_revisits,
        "semantic_action_revisits": candidate.semantic_action_revisits - baseline.semantic_action_revisits,
        "longest_no_progress_span": candidate.longest_no_progress_span - baseline.longest_no_progress_span,
    }
    materially_higher = (
        deltas["turns"] >= 2
        or deltas["prompt_tokens"] >= max(256, baseline.prompt_tokens // 4)
        or deltas["effectful_dispatches"] >= 2
        or deltas["recovery_count"] >= 1
        or deltas["semantic_page_revisits"] >= 2
        or deltas["semantic_action_revisits"] >= 2
        or deltas["longest_no_progress_span"] >= 2
    )
    if not materially_higher:
        return DetourAssessment("not_assessed")
    return DetourAssessment(
        "suspected_detour",
        comparison_run_attempt_ids=(baseline.run_attempt_id,),
        measured_deltas=deltas,
        evidence_refs=tuple(dict.fromkeys((*candidate.evidence_refs, *baseline.evidence_refs))),
    )

"""Benchmark-only routing/payload/end-to-end two-stage matrix runner."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from affordance_runtime.agent.context.failures import ModelFailure
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.model.policy.parser import parse_agent_decision
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
)

from ..decision_matrix import DecisionMatrixCase, decision_matches_expectation
from ..matrix_progress import write_json_report
from ..runtime_decision_matrix import (
    replay_runtime_decision,
    run_scripted_runtime_decision_matrix,
    runtime_outcome_matches,
)
from .contracts import (
    DecisionKind,
    DecisionKindRoute,
    PacingConfiguration,
    TwoStageAttemptResult,
    TwoStageDecisionIdentity,
    TwoStageMatrixResult,
    TwoStageRunMode,
)
from .payload_schema import payload_output_model
from .progress import (
    TwoStageProgressAttempt,
    TwoStageProgressStage,
    write_two_stage_progress,
)
from .route_schema import route_output_model

_ROUTE_SYSTEM = "Choose only the decision kind justified by the current public AgentContext."
_PAYLOAD_SYSTEM = "Fill the complete canonical payload for the selected diagnostic decision kind."


async def run_two_stage_matrix(
    *,
    run_id: str,
    mode: TwoStageRunMode,
    port_factory,
    cases: tuple[DecisionMatrixCase, ...],
    repetitions: int,
    output_dir: Path,
    pacing: PacingConfiguration = PacingConfiguration(),
) -> TwoStageMatrixResult:
    if not 1 <= repetitions <= 20:
        raise ValueError("two-stage repetitions must be in [1, 20]")
    selected_mode = TwoStageRunMode(mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "two-stage-progress.json"
    progress: list[TwoStageProgressAttempt] = []
    attempts: list[TwoStageAttemptResult] = []
    planned = len(cases) * repetitions
    pacer = _Pacer(pacing)
    _write_progress(progress_path, run_id, pacing, progress, planned, 0, False)
    for case in cases:
        for repetition in range(repetitions):
            await pacer.before_attempt()
            attempt = await _run_attempt(
                run_id, case, repetition, selected_mode, port_factory, pacer,
                progress, progress_path, pacing, planned, len(attempts),
            )
            attempts.append(attempt)
            _write_progress(progress_path, run_id, pacing, progress, planned, len(attempts), False)
    runtime = await run_scripted_runtime_decision_matrix()
    result = _result(run_id, selected_mode, repetitions, pacing, attempts, runtime)
    write_json_report(output_dir / f"{selected_mode.value}.json", asdict(result))
    _write_progress(progress_path, run_id, pacing, progress, planned, len(attempts), True)
    return result


async def _run_attempt(
    run_id, case, repetition, mode, port_factory, pacer, progress, progress_path,
    pacing, planned, completed,
) -> TwoStageAttemptResult:
    identity = _identity(run_id, case, repetition)
    expected = DecisionKind(case.expected_variant)
    route: DecisionKindRoute | None = None
    route_record = None
    if mode is TwoStageRunMode.PAYLOAD_ONLY:
        route = DecisionKindRoute(identity.context_id, expected)
    else:
        progress.append(_event(identity, TwoStageProgressStage.ROUTING_STARTED, 1, 0))
        _write_progress(progress_path, run_id, pacing, progress, planned, completed, False)
        route, failure, route_record = await _call_route(port_factory(), case)
        progress.append(_event(
            identity, TwoStageProgressStage.ROUTING_COMPLETED, 1, 0, failure,
            route_record, routing_digest=_schema_digest(route_output_model(case.serialized_context)),
        ))
        _write_progress(progress_path, run_id, pacing, progress, planned, completed, False)
        expected_context = json.loads(case.serialized_context)["context_id"]
        if route is not None and route.context_id != expected_context:
            failure = "routing_stale_context"
        if failure or route is None or route.decision_type is not expected:
            category = failure or "routing_wrong_variant"
            return _attempt_result(identity, case, mode, route, False, False, category, route_record, None)
    if mode is TwoStageRunMode.ROUTING_ONLY:
        return _attempt_result(identity, case, mode, route, False, False, "", route_record, None)
    await pacer.between_stages()
    progress.append(_event(identity, TwoStageProgressStage.PAYLOAD_STARTED, int(route_record is not None), 1))
    _write_progress(progress_path, run_id, pacing, progress, planned, completed, False)
    decision, failure, payload_record = await _call_payload(port_factory(), case, route.decision_type)
    progress.append(_event(
        identity, TwoStageProgressStage.PAYLOAD_COMPLETED, int(route_record is not None), 1,
        failure, payload_record, payload_digest=_schema_digest(payload_output_model(route.decision_type, case.serialized_context)),
    ))
    _write_progress(progress_path, run_id, pacing, progress, planned, completed, False)
    if failure or decision is None:
        return _attempt_result(identity, case, mode, route, False, False, failure, route_record, payload_record)
    payload_correct = decision_matches_expectation(decision, case.expectation)
    if not payload_correct:
        return _attempt_result(
            identity, case, mode, route, False, False, "payload_wrong_field_domain",
            route_record, payload_record,
        )
    replay = await replay_runtime_decision(case, decision)
    failure = "" if replay.success else (
        "payload_runtime_rejected" if replay.status == "blocked" else "payload_runtime_outcome_mismatch"
    )
    progress.append(_event(
        identity, TwoStageProgressStage.RUNTIME_COMPLETED, int(route_record is not None), 1, failure,
    ))
    _write_progress(progress_path, run_id, pacing, progress, planned, completed, False)
    return _attempt_result(
        identity, case, mode, route, payload_correct, replay.success, failure,
        route_record, payload_record,
    )


async def _call_route(port: ModelPort, case: DecisionMatrixCase):
    model = route_output_model(case.serialized_context)
    messages = _messages(_ROUTE_SYSTEM, case.serialized_context)
    try:
        route = await port.generate_structured(messages, cast(Any, model), _config(128))
    except Exception as exc:
        return None, _failure("routing", exc), port.last_call
    return cast(DecisionKindRoute, route), "", port.last_call


async def _call_payload(port: ModelPort, case: DecisionMatrixCase, kind: DecisionKind):
    model = payload_output_model(kind, case.serialized_context)
    messages = _messages(_PAYLOAD_SYSTEM + f" Selected kind: {kind.value}.", case.serialized_context)
    try:
        payload = await port.generate_structured(messages, cast(Any, model), _config(2_048))
    except Exception as exc:
        return None, _failure("payload", exc), port.last_call
    raw = payload.model_dump_json()
    decision = parse_agent_decision(raw, json.loads(case.serialized_context)["context_id"])
    if isinstance(decision, ModelFailure | PolicyFailure):
        return None, "payload_structured_output", port.last_call
    return decision, "", port.last_call


def _messages(system: str, serialized_context: str) -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(role="system", content=system),
        ModelMessage(role="user", content=json.dumps(
            {"agent_context": json.loads(serialized_context)},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )),
    )


def _config(max_tokens: int) -> ModelConfig:
    return ModelConfig(
        temperature=0, max_tokens=max_tokens, timeout_s=89,
        rate_limit_retries=0, transient_retries=0, prompt_version="p5-m3.6-two-stage",
    )


def _failure(stage: str, error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return f"{stage}_timeout"
    if isinstance(error, ProviderModelError):
        return f"{stage}_provider_unavailable"
    if isinstance(error, StructuredOutputError | StructuredModelError | ValueError):
        return f"{stage}_structured_output"
    return f"{stage}_provider_unavailable"


def _identity(run_id: str, case: DecisionMatrixCase, repetition: int) -> TwoStageDecisionIdentity:
    logical = f"{run_id}:{case.case_id}:{repetition + 1}"
    context_id = str(json.loads(case.serialized_context)["context_id"])
    return TwoStageDecisionIdentity(logical, context_id, logical + ":route", logical + ":payload")


def _attempt_result(identity, case, mode, route, payload, runtime, failure, route_record, payload_record):
    records = tuple(item for item in (route_record, payload_record) if item is not None)
    routing_correct = route is not None and route.decision_type.value == case.expected_variant
    success = routing_correct and (mode is TwoStageRunMode.ROUTING_ONLY or (payload and runtime))
    routing_attempts = int(mode is not TwoStageRunMode.PAYLOAD_ONLY)
    payload_attempts = int(
        mode is not TwoStageRunMode.ROUTING_ONLY
        and route is not None and routing_correct
    )
    return TwoStageAttemptResult(
        identity.logical_decision_id, case.case_id, mode, DecisionKind(case.expected_variant),
        route.decision_type if route else None, routing_correct, payload, runtime, success, failure,
        routing_attempts, payload_attempts, routing_attempts + payload_attempts,
        sum(item.prompt_tokens for item in records), sum(item.completion_tokens for item in records),
        sum(item.latency_ms for item in records),
    )


def _event(
    identity, stage, routing_attempts, payload_attempts, failure="", record=None,
    routing_digest="", payload_digest="",
):
    return TwoStageProgressAttempt(
        identity, stage, failure, routing_attempts, payload_attempts,
        routing_attempts + payload_attempts,
        record.prompt_tokens if record else 0, record.completion_tokens if record else 0,
        record.latency_ms if record else 0, routing_digest, payload_digest,
    )


def _schema_digest(model: type[Any]) -> str:
    encoded = json.dumps(model.model_json_schema(), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_progress(path, run_id, pacing, progress, planned, completed, complete):
    write_two_stage_progress(
        path, run_id=run_id, pacing=pacing, attempts=tuple(progress),
        planned_attempt_count=planned, completed_attempt_count=completed, complete=complete,
    )


def _result(run_id, mode, repetitions, pacing, attempts, runtime):
    return TwoStageMatrixResult(
        "two-stage-matrix.v1", run_id, mode, repetitions, pacing, tuple(attempts),
        sum(item.success for item in attempts), sum(item.provider_calls for item in attempts),
        sum(item.prompt_tokens for item in attempts), sum(item.completion_tokens for item in attempts),
        sum(item.latency_ms for item in attempts), 0, 0,
        sum(runtime_outcome_matches(item) for item in runtime),
    )


class _Pacer:
    def __init__(self, pacing: PacingConfiguration) -> None:
        self.pacing = pacing
        self.next_attempt_at = 0.0

    async def before_attempt(self) -> None:
        delay = max(0.0, self.next_attempt_at - time.monotonic())
        if delay:
            await asyncio.sleep(delay)
        self.next_attempt_at = time.monotonic() + self.pacing.inter_attempt_delay_s

    async def between_stages(self) -> None:
        if self.pacing.inter_stage_delay_s:
            await asyncio.sleep(self.pacing.inter_stage_delay_s)

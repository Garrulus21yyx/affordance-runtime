"""Complete, non-authoritative tracing for the single GUI-agent Runtime loop."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import queue
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from affordance_runtime.goals.plan import Failed, NeedsInput, NotRequired, Ready, Unsupported


class RunTraceSink(Protocol):
    """Observe Runtime facts without participating in Runtime control."""

    def run_started(self, task: object, state: object) -> None: ...

    def benchmark_case_started(
        self, *, case_id: str, description: str, timeout_s: float
    ) -> None: ...

    def benchmark_case_finished(self, *, case_id: str, status: str) -> None: ...

    def run_start_failed(self, task: object, acquisition: object) -> None: ...

    def goal_compiler_completed(self, diagnostic: object) -> None: ...

    def model_turn(
        self,
        context: object,
        outcome: object,
        policy: object,
        *,
        exception: str = "",
    ) -> None: ...

    def mission_role_invocation(
        self,
        role: str,
        call_index: int,
        request: object,
        result: object,
        *,
        trigger_kind: str,
        execution_mode: str,
        subtask_id: str,
        mission_version: int,
    ) -> None: ...

    def finalization_protocol(
        self,
        *,
        stop_send_count: int,
        post_stop_capture_count: int,
        native_evaluator_count: int,
        dispatch_status: str,
    ) -> None: ...

    def native_evaluator_returned(self, evaluation: object) -> None: ...

    def official_outcome_persistence(
        self,
        *,
        checkpoint_id: str,
        persistence_status: str,
        persistence_error: str,
    ) -> None: ...

    def final_response_boundary_evaluated(
        self,
        *,
        mission_version: int,
        review_world_observation_id: str,
        schema_digest: str,
        cited_evidence_refs: tuple[str, ...],
        admitted: bool,
        rejection_code: str,
        response_digest: str,
    ) -> None: ...

    def benchmark_lifecycle_phase(
        self,
        phase: str,
        *,
        primary_result_available: bool,
        primary_snapshot_available: bool,
    ) -> None: ...

    def case_lifecycle_phase(self, phase: str) -> None: ...

    def primary_result_available(
        self,
        *,
        case_id: str,
        checkpoint_id: str,
        status: str,
        step_count: int,
    ) -> None: ...

    def benchmark_watchdog(
        self,
        code: str,
        *,
        cancel_grace_exceeded: bool,
    ) -> None: ...

    def step_completed(self, step_number: int, result: object) -> None: ...
    def run_paused(self, state: object) -> None: ...

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None: ...

    def run_error(self, error: BaseException, state: object) -> None: ...

    def run_finished(self, state: object) -> None: ...


@dataclass(frozen=True)
class NullRunTraceSink:
    def benchmark_case_started(self, **event: object) -> None:
        del event

    def benchmark_case_finished(self, **event: object) -> None:
        del event

    def run_started(self, task: object, state: object) -> None:
        return None

    def run_start_failed(self, task: object, acquisition: object) -> None:
        return None

    def goal_compiler_completed(self, diagnostic: object) -> None:
        return None

    def model_turn(
        self,
        context: object,
        outcome: object,
        policy: object,
        *,
        exception: str = "",
    ) -> None:
        return None

    def mission_role_invocation(
        self,
        role: str,
        call_index: int,
        request: object,
        result: object,
        *,
        trigger_kind: str,
        execution_mode: str,
        subtask_id: str,
        mission_version: int,
    ) -> None:
        del role, call_index, request, result, trigger_kind, execution_mode, subtask_id, mission_version
        return None

    def finalization_protocol(
        self,
        *,
        stop_send_count: int,
        post_stop_capture_count: int,
        native_evaluator_count: int,
        dispatch_status: str,
    ) -> None:
        del stop_send_count, post_stop_capture_count, native_evaluator_count, dispatch_status
        return None

    def native_evaluator_returned(self, evaluation: object) -> None:
        del evaluation
        return None

    def official_outcome_persistence(self, **event: object) -> None:
        del event
        return None

    def final_response_boundary_evaluated(self, **event: object) -> None:
        del event
        return None

    def benchmark_lifecycle_phase(self, phase: str, **event: object) -> None:
        del phase, event
        return None

    def case_lifecycle_phase(self, phase: str) -> None:
        del phase

    def primary_result_available(self, **event: object) -> None:
        del event
        return None

    def benchmark_watchdog(self, code: str, **event: object) -> None:
        del code, event
        return None

    def step_completed(self, step_number: int, result: object) -> None:
        return None

    def run_paused(self, state: object) -> None:
        return None

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        return None

    def run_error(self, error: BaseException, state: object) -> None:
        return None

    def run_finished(self, state: object) -> None:
        return None


@dataclass
class RunTraceRecorder:
    """Append complete Runtime facts locally; tracing failures never alter the run."""

    directory: Path | None = None
    run_id: str = field(default_factory=lambda: f"run:{uuid.uuid4().hex}")
    events: list[dict[str, object]] = field(default_factory=list, init=False)
    errors: list[str] = field(default_factory=list, init=False)
    _sequence: int = field(default=0, init=False, repr=False)
    _observations: set[str] = field(default_factory=set, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.directory is not None:
            self.directory = Path(self.directory).resolve()
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / "artifacts").mkdir(exist_ok=True)
            if (self.directory / "trace.jsonl").exists():
                raise FileExistsError("trace directory already contains trace.jsonl")

    @property
    def path(self) -> Path | None:
        return self.directory / "trace.jsonl" if self.directory is not None else None

    def run_started(self, task: object, state: object) -> None:
        self._emit(
            "run_started",
            task=_json_value(task, self.directory),
            initial_status=_enum_value(getattr(state, "status", "")),
            max_steps=getattr(state, "remaining_steps", None),
            goal_guidance=_goal_guidance_payload(state),
        )
        self._observation(getattr(state, "current_world", None))

    def benchmark_case_started(
        self, *, case_id: str, description: str, timeout_s: float
    ) -> None:
        self._emit(
            "benchmark_case_started",
            case_id=case_id,
            description=description,
            timeout_s=timeout_s,
        )

    def benchmark_case_finished(self, *, case_id: str, status: str) -> None:
        self._emit("benchmark_case_finished", case_id=case_id, status=status)

    def run_start_failed(self, task: object, acquisition: object) -> None:
        self._emit(
            "run_start_failed",
            task=_json_value(task, self.directory),
            acquisition=_json_value(acquisition, self.directory),
        )

    def goal_compiler_completed(self, diagnostic: object) -> None:
        self._emit(
            "goal_compiler_completed",
            diagnostic=_json_value(diagnostic, self.directory),
        )

    def model_turn(
        self,
        context: object,
        outcome: object,
        policy: object,
        *,
        exception: str = "",
    ) -> None:
        payload = model_turn_payload(context, outcome, policy, exception=exception)
        payload["agent_context"] = _json_value(context, self.directory)
        self._emit("model_turn", **payload)

    def mission_role_invocation(
        self,
        role: str,
        call_index: int,
        request: object,
        result: object,
        *,
        trigger_kind: str,
        execution_mode: str,
        subtask_id: str,
        mission_version: int,
    ) -> None:
        metadata = getattr(result, "metadata", None)
        failure = getattr(result, "failure", None)
        attempts = tuple(getattr(result, "attempts", ()))
        output = getattr(result, "output", None)
        if output is None and isinstance(result, Mapping):
            output = result.get("decision")
        self._emit(
            "mission_role_invocation",
            role=role,
            call_index=call_index,
            trigger_kind=trigger_kind,
            execution_mode=execution_mode,
            subtask_id=subtask_id,
            mission_version=mission_version,
            manager_request_mode=_enum_value(getattr(request, "mode", "")),
            assessment=_enum_value(getattr(output, "assessment", "")),
            route=_enum_value(getattr(output, "route", "")),
            optional_auditor_trigger=(trigger_kind if role == "auditor" else ""),
            input_tokens=int(getattr(metadata, "prompt_tokens", 0)),
            output_tokens=int(getattr(metadata, "completion_tokens", 0)),
            latency_ms=float(getattr(metadata, "latency_ms", 0.0)),
            provider_attempts=len(attempts),
            result="failure" if failure is not None else "accepted",
            failure=_json_value(failure, self.directory),
            role_request=_json_value(request, self.directory),
            model_invocation=_json_value(result, self.directory),
        )

    def finalization_protocol(
        self,
        *,
        stop_send_count: int,
        post_stop_capture_count: int,
        native_evaluator_count: int,
        dispatch_status: str,
    ) -> None:
        self._emit(
            "finalization_protocol",
            stop_send_count=stop_send_count,
            post_stop_capture_count=post_stop_capture_count,
            native_evaluator_count=native_evaluator_count,
            dispatch_status=dispatch_status,
        )

    def native_evaluator_returned(
        self,
        evaluation: object,
        *,
        checkpoint_id: str = "",
    ) -> None:
        outcome = getattr(evaluation, "outcome", None)
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    *tuple(getattr(evaluation, "completion_evidence_refs", ())),
                    *tuple(getattr(outcome, "evidence_refs", ())),
                    *(
                        ref
                        for criterion in tuple(getattr(evaluation, "criteria", ()))
                        for ref in tuple(getattr(criterion, "evidence_refs", ()))
                    ),
                    *(
                        ref
                        for output in tuple(getattr(evaluation, "outputs", ()))
                        for ref in tuple(getattr(output, "evidence_refs", ()))
                    ),
                )
            )
        )
        self._emit(
            "native_evaluator_returned",
            evaluation_status=_enum_value(getattr(evaluation, "status", "")),
            outcome_kind=_enum_value(getattr(outcome, "kind", "")),
            outcome_code=str(getattr(outcome, "code", "")),
            evidence_refs=evidence_refs,
            observation_id=str(getattr(evaluation, "observation_id", "")),
            checkpoint_id=checkpoint_id,
        )

    def official_outcome_persistence(
        self,
        *,
        checkpoint_id: str,
        persistence_status: str,
        persistence_error: str,
    ) -> None:
        self._emit(
            "official_outcome_persistence",
            checkpoint_id=checkpoint_id,
            persistence_status=persistence_status,
            persistence_error=persistence_error,
        )

    def benchmark_lifecycle_phase(
        self,
        phase: str,
        *,
        primary_result_available: bool,
        primary_snapshot_available: bool,
    ) -> None:
        self._emit(
            "benchmark_lifecycle_phase",
            phase=phase,
            primary_result_available=primary_result_available,
            primary_snapshot_available=primary_snapshot_available,
        )

    def case_lifecycle_phase(self, phase: str) -> None:
        self._emit("case_lifecycle_phase", phase=phase)

    def primary_result_available(
        self,
        *,
        case_id: str,
        checkpoint_id: str,
        status: str,
        step_count: int,
    ) -> None:
        self._emit(
            "primary_result_available",
            case_id=case_id,
            checkpoint_id=checkpoint_id,
            status=status,
            step_count=step_count,
        )

    def benchmark_watchdog(
        self,
        code: str,
        *,
        cancel_grace_exceeded: bool,
    ) -> None:
        self._emit(
            "benchmark_watchdog",
            code=code,
            cancel_grace_exceeded=cancel_grace_exceeded,
        )

    def final_response_boundary_evaluated(
        self,
        *,
        mission_version: int,
        review_world_observation_id: str,
        schema_digest: str,
        cited_evidence_refs: tuple[str, ...],
        admitted: bool,
        rejection_code: str,
        response_digest: str,
    ) -> None:
        self._emit(
            "final_response_boundary_evaluated",
            mission_version=mission_version,
            review_world_observation_id=review_world_observation_id,
            schema_digest=schema_digest,
            cited_evidence_refs=cited_evidence_refs,
            cited_evidence_count=len(cited_evidence_refs),
            admitted=admitted,
            rejection_code=rejection_code,
            response_digest=response_digest,
        )

    def step_completed(self, step_number: int, result: object) -> None:
        self._observation(getattr(result, "before_world", None))
        self._observation(getattr(result, "after_world", None))
        self._emit(
            "step_completed",
            step=step_number,
            result=_step_payload(result, self.directory),
            lineage=_step_lineage(result),
        )

    def run_paused(self, state: object) -> None:
        self._emit(
            "run_paused",
            status=_enum_value(getattr(state, "status", "")),
            reason=_enum_value(getattr(state, "yield_reason", "")),
        )

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        self._emit("run_resumed", kind=kind, details=_json_value(details, self.directory))

    def run_error(self, error: BaseException, state: object) -> None:
        self._emit(
            "run_error",
            exception_class=type(error).__name__,
            error=str(error),
            status=_enum_value(getattr(state, "status", "")),
        )

    def run_finished(self, state: object) -> None:
        status = _enum_value(getattr(state, "status", ""))
        self._emit(
            "run_finished",
            status=status,
            step_count=getattr(state, "step_count", None),
            observation_count=getattr(state, "observation_count", None),
            execution_count=getattr(state, "execution_count", None),
            task_evaluation=_json_value(
                getattr(state, "current_task_evaluation", None), self.directory
            ),
        )

    def _observation(self, observation: object) -> None:
        observation_id = getattr(observation, "observation_id", "")
        if not observation_id or observation_id in self._observations:
            return
        self._observations.add(observation_id)
        self._emit(
            "observation",
            observation_id=observation_id,
            observation=_json_value(observation, self.directory),
        )

    def _emit(self, event_type: str, **payload: object) -> None:
        try:
            with self._lock:
                self._sequence += 1
                event: dict[str, object] = {
                    "schema_version": "gui-agent-trace.v1",
                    "run_id": self.run_id,
                    "sequence": self._sequence,
                    "event": event_type,
                    **payload,
                }
                self.events.append(event)
                if self.path is not None:
                    encoded = (
                        json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                    ).encode()
                    descriptor = os.open(
                        self.path,
                        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                        0o600,
                    )
                    try:
                        remaining = memoryview(encoded)
                        while remaining:
                            written = os.write(descriptor, remaining)
                            if written <= 0:
                                raise OSError("trace write made no progress")
                            remaining = remaining[written:]
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
        except Exception as exc:  # observability must never become control authority
            self.errors.append(f"{event_type}:{type(exc).__name__}")


def _goal_guidance_payload(state: object) -> dict[str, object]:
    """Project optional goal guidance for tracing without creating control state."""

    return goal_guidance_trace_payload(
        getattr(state, "goal_resolution", None),
    )


def goal_guidance_trace_payload(
    resolution: object,
) -> dict[str, object]:
    """Mechanically project a resolution for run-start or revision tracing."""

    if isinstance(resolution, Ready):
        return {
            "disposition": "ready",
            "plan_version": resolution.accepted_plan.plan_version,
            "plan_digest": resolution.accepted_plan.digest,
        }
    if isinstance(resolution, NotRequired):
        return {"disposition": "not_required", "reason": resolution.reason}
    if isinstance(resolution, Failed):
        return {
            "disposition": "unavailable",
            "outcome": "failed",
            "reason": resolution.reason,
        }
    if isinstance(resolution, Unsupported):
        return {
            "disposition": "unavailable",
            "outcome": "unsupported",
            "reason": resolution.reason,
        }
    if isinstance(resolution, NeedsInput):
        return {"disposition": "needs_input"}
    return {"disposition": "unavailable", "reason": "goal_guidance_not_resolved"}


def goal_compiler_trace_diagnostic(
    compiler: object,
    resolution: object,
    *,
    task_revision: int,
    trigger: object,
    initial_evidence: object | None,
) -> dict[str, object]:
    """Project one completed compilation lineage without creating Runtime state."""

    invocation = getattr(compiler, "last_invocation_result", None)
    attempts = tuple(getattr(invocation, "attempts", ()))
    repair_diagnostics = tuple(getattr(invocation, "repair_diagnostics", ()))
    if isinstance(resolution, Ready):
        disposition = "ready"
        reason = ""
        question = ""
        fields: tuple[str, ...] = ()
        plan_version: int | None = resolution.accepted_plan.plan_version
    elif isinstance(resolution, NotRequired):
        disposition, reason, question, fields, plan_version = (
            "not_required", resolution.reason, "", (), None,
        )
    elif isinstance(resolution, NeedsInput):
        disposition, reason, question, fields, plan_version = (
            "needs_input", "", resolution.question, resolution.fields, None,
        )
    elif isinstance(resolution, Unsupported):
        disposition, reason, question, fields, plan_version = (
            "unsupported", resolution.reason, "", (), None,
        )
    elif isinstance(resolution, Failed):
        disposition, reason, question, fields, plan_version = (
            "failed", resolution.reason, "", (), None,
        )
    else:
        disposition, reason, question, fields, plan_version = (
            "failed", "invalid_goal_compiler_outcome", "", (), None,
        )
    port = getattr(compiler, "port", None)
    config = getattr(compiler, "config", None)
    return {
        "task_revision": task_revision,
        "trigger": _enum_value(trigger),
        "final_disposition": disposition,
        "accepted_plan_version": plan_version,
        "reason": reason,
        "question": question,
        "missing_fields": tuple(fields),
        "schema_repair_count": _diagnostic_count(
            repair_diagnostics,
            kind="structured_output_repair",
        ),
        "contract_repair_count": sum(
            getattr(item, "phase", "") == "goal_compile_contract_repair"
            for item in attempts
        ),
        "provider_attempt_count": len(attempts),
        "generation_attempts": attempts,
        "compiler_prompt_version": str(getattr(config, "prompt_version", "")),
        "provider_id": str(getattr(port, "provider", "")),
        "model_id": str(getattr(port, "model", "")),
        "initial_evidence_observation_id": str(
            getattr(initial_evidence, "observation_id", "")
        ),
    }


def _diagnostic_count(
    diagnostics: tuple[object, ...],
    *,
    kind: str,
) -> int:
    count = 0
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, Mapping) or diagnostic.get("kind") != kind:
            continue
        value = diagnostic.get("count", 1)
        try:
            count += int(value)
        except (TypeError, ValueError):
            count += 1
    return count


class TraceEventSink(Protocol):
    """Worker-owned consumer of an already-recorded typed trace event."""

    def record(self, event: Mapping[str, object]) -> None: ...

    def flush(self) -> None: ...


@dataclass
class LangfuseOtelSink:
    """Worker-confined Langfuse SDK adapter; never called by Runtime owners."""

    client: Any
    session_id: str = ""
    benchmark_managed: bool = False
    root: Any | None = field(default=None, init=False)
    _root_context: Any | None = field(default=None, init=False)
    _attribute_context: Any | None = field(default=None, init=False)
    _ended: bool = field(default=False, init=False)

    def record(self, event: Mapping[str, object]) -> None:
        event_type = str(event.get("event", "unknown"))
        if event_type == "benchmark_case_started":
            self._start_root(event)
            return
        if event_type in {"run_started", "run_start_failed"}:
            if self.root is None:
                self._start_root(event)
                if event_type == "run_start_failed":
                    self._finish(event, error=True)
                return
            if event_type == "run_start_failed" and not self.benchmark_managed:
                self._finish(event, error=True)
                return
        if self.root is None or self._ended:
            return
        if event_type in {"model_turn", "mission_role_invocation"}:
            self._record_model_event(event)
        else:
            projection = _langfuse_event_projection(event)
            with self.client.start_as_current_observation(
                name=_langfuse_event_name(event),
                as_type=_langfuse_observation_type(event),
                output=projection,
                metadata={
                    "event": event_type,
                    "sequence": event.get("sequence"),
                    "local_run_id": event.get("run_id"),
                },
            ):
                pass
        if event_type == "run_error":
            self._finish(event, error=True)
        elif event_type == "run_finished" and not self.benchmark_managed:
            self._finish(event)
        elif event_type == "benchmark_case_finished":
            self._finish(event, error=str(event.get("status")) not in {"done", "blocked"})

    def flush(self) -> None:
        self.client.flush()

    def _record_model_event(self, event: Mapping[str, object]) -> None:
        event_type = str(event.get("event", ""))
        with self.client.start_as_current_observation(
            name=_langfuse_event_name(event),
            as_type="agent",
            output=_langfuse_event_projection(event),
            metadata={
                "event": event_type,
                "sequence": event.get("sequence"),
                "local_run_id": event.get("run_id"),
            },
        ):
            for attempt in _langfuse_generation_attempts(event):
                transcript = attempt.get("transcript")
                transcript = transcript if isinstance(transcript, Mapping) else {}
                metadata = _langfuse_model_metadata(event)
                with self.client.start_as_current_observation(
                    name=_langfuse_generation_name(event),
                    as_type="generation",
                    input=_bounded_remote_projection({
                        "messages": transcript.get("llm.input_messages", ()),
                    }),
                    output=_bounded_remote_projection({
                        "messages": transcript.get("llm.output_messages", ()),
                    }),
                    model=str(metadata.get("model_id", "")) or None,
                    model_parameters={
                        "max_output_tokens": int(attempt.get("max_output_tokens", 0)),
                        "thinking": str(attempt.get("thinking_effective", "")),
                    },
                    usage_details={
                        "input": int(attempt.get("prompt_tokens", 0)),
                        "output": int(attempt.get("completion_tokens", 0)),
                        "total": int(attempt.get("total_tokens", 0)),
                    },
                    level="ERROR" if attempt.get("status") == "failed" else None,
                    metadata=_bounded_remote_projection({
                        "attempt": attempt.get("attempt"),
                        "phase": attempt.get("phase"),
                        "trigger": attempt.get("trigger"),
                        "status": attempt.get("status"),
                        "finish_reason": attempt.get("finish_reason"),
                        "thinking_requested": attempt.get("thinking_requested"),
                        "thinking_effective": attempt.get("thinking_effective"),
                        "reasoning_tokens": attempt.get("reasoning_tokens"),
                        "final_content_tokens": attempt.get("final_content_tokens"),
                        "final_tool_call_present": attempt.get("final_tool_call_present"),
                        "provider_id": metadata.get("provider_id"),
                        "prompt_version": metadata.get("prompt_version"),
                        "schema_version": attempt.get("schema_version"),
                        "latency_ms": attempt.get("latency_ms"),
                    }),
                ):
                    pass

    def _start_root(self, event: Mapping[str, object]) -> None:
        if self.root is not None:
            return
        self._root_context = self.client.start_as_current_observation(
            name="benchmark-gui-agent-case" if self.benchmark_managed else "run-gui-agent-case",
            as_type="agent",
            input=(
                _bounded_remote_projection({
                    "case_id": event.get("case_id"),
                    "description": event.get("description"),
                })
                if event.get("event") == "benchmark_case_started"
                else _public_task_projection(event.get("task"))
            ),
            metadata={"local_run_id": event.get("run_id")},
            end_on_exit=False,
        )
        self.root = self._root_context.__enter__()
        if self.session_id:
            from langfuse import propagate_attributes  # type: ignore[import-not-found]

            self._attribute_context = propagate_attributes(session_id=self.session_id)
            self._attribute_context.__enter__()

    def _finish(self, event: Mapping[str, object], *, error: bool = False) -> None:
        if self.root is None or self._ended:
            return
        self.root.update(
            output=_langfuse_event_projection(event),
            **({"level": "ERROR"} if error else {}),
        )
        if self._attribute_context is not None:
            self._attribute_context.__exit__(None, None, None)
        self.root.end()
        if self._root_context is not None:
            self._root_context.__exit__(None, None, None)
        self._ended = True


@dataclass
class LangfuseViewerWorker:
    """Per-case daemon that exclusively owns Langfuse SDK calls."""

    client_factory: Callable[[], Any]
    session_id: str = ""
    benchmark_managed: bool = False
    queue_capacity: int = 256
    errors: list[str] = field(default_factory=list, init=False)
    dropped_event_count: int = field(default=0, init=False)
    disabled: bool = field(default=False, init=False)
    flush_timeout: bool = field(default=False, init=False)
    _queue: queue.Queue[Mapping[str, object]] = field(init=False, repr=False)
    _stop_requested: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread = field(init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 1 <= self.queue_capacity <= 4096:
            raise ValueError("viewer queue capacity is outside bounds")
        self._queue = queue.Queue(maxsize=self.queue_capacity)
        self._thread = threading.Thread(
            target=self._run,
            name="langfuse-viewer-worker",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, event: Mapping[str, object]) -> bool:
        with self._lock:
            if self.disabled or self._stop_requested.is_set():
                self.dropped_event_count += 1
                return False
            try:
                self._queue.put_nowait(dict(event))
            except queue.Full:
                self.dropped_event_count += 1
                self.disabled = True
                self.errors.append("viewer_queue_full")
                return False
        return True

    def close(self, *, timeout_s: float = 5.0) -> bool:
        if timeout_s < 0:
            raise ValueError("viewer close timeout cannot be negative")
        self._stop_requested.set()
        self._thread.join(timeout_s)
        if self._thread.is_alive():
            with self._lock:
                self.disabled = True
                self.flush_timeout = True
                if "viewer_flush_timeout" not in self.errors:
                    self.errors.append("viewer_flush_timeout")
            return False
        return not self.disabled

    def _run(self) -> None:
        try:
            client = self.client_factory()
            sink = LangfuseOtelSink(
                client,
                session_id=self.session_id,
                benchmark_managed=self.benchmark_managed,
            )
        except Exception as exc:
            self._disable(f"viewer_init:{type(exc).__name__}")
            return
        while True:
            if self.disabled:
                return
            if self._stop_requested.is_set() and self._queue.empty():
                break
            try:
                event = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                sink.record(event)
            except Exception as exc:
                self._disable(f"viewer_record:{type(exc).__name__}")
                return
            finally:
                self._queue.task_done()
        try:
            sink.flush()
        except Exception as exc:
            self._disable(f"viewer_flush:{type(exc).__name__}")

    def _disable(self, reason: str) -> None:
        with self._lock:
            self.disabled = True
            self.errors.append(reason)


@dataclass
class QueuedViewerRunTraceRecorder(RunTraceRecorder):
    """Persist JSONL first, then enqueue without invoking a viewer SDK."""

    viewer_worker: LangfuseViewerWorker | None = None

    def _emit(self, event_type: str, **payload: object) -> None:
        error_count = len(self.errors)
        sequence = self._sequence
        super()._emit(event_type, **payload)
        if (
            self.viewer_worker is None
            or self._sequence == sequence
            or len(self.errors) != error_count
        ):
            return
        self.viewer_worker.enqueue(self.events[-1])

    @property
    def viewer_errors(self) -> list[str]:
        return self.viewer_worker.errors if self.viewer_worker is not None else []

    @property
    def viewer_dropped_event_count(self) -> int:
        return self.viewer_worker.dropped_event_count if self.viewer_worker is not None else 0

    @property
    def viewer_disabled(self) -> bool:
        return bool(self.viewer_worker is not None and self.viewer_worker.disabled)

    def flush_viewer(self, *, timeout_s: float = 5.0) -> None:
        if self.viewer_worker is None:
            return
        completed = self.viewer_worker.close(timeout_s=timeout_s)
        if not completed:
            RunTraceRecorder._emit(
                self,
                "viewer_status",
                viewer_disabled=True,
                viewer_flush_timeout=self.viewer_worker.flush_timeout,
                viewer_dropped_event_count=self.viewer_worker.dropped_event_count,
                viewer_errors=tuple(self.viewer_worker.errors),
            )


def trace_recorder_from_environment(
    environment: Mapping[str, str],
    *,
    directory: Path | None = None,
    run_id: str | None = None,
    session_id: str = "",
    benchmark_managed: bool = False,
) -> RunTraceSink:
    raw_directory = environment.get("AFFORDANCE_TRACE_DIR", "").strip()
    local_directory = directory or (Path(raw_directory) if raw_directory else None)
    enabled = environment.get("AFFORDANCE_LANGFUSE_ENABLED", "").strip().casefold()
    langfuse_enabled = enabled in {"1", "true", "yes", "on"}
    if langfuse_enabled and local_directory is None:
        raise ValueError("Langfuse viewing requires a local JSONL trace")
    if langfuse_enabled and not all(
        environment.get(name, "").strip()
        for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    ):
        raise ValueError("Langfuse viewing requires configured SDK credentials")
    if local_directory is None:
        return NullRunTraceSink()
    recorder_arguments: dict[str, object] = {"directory": local_directory}
    if run_id:
        recorder_arguments["run_id"] = run_id
    if not langfuse_enabled:
        return RunTraceRecorder(**recorder_arguments)
    return QueuedViewerRunTraceRecorder(
        **recorder_arguments,
        viewer_worker=LangfuseViewerWorker(
            _langfuse_client_from_environment,
            session_id=session_id,
            benchmark_managed=benchmark_managed,
        ),
    )


def _langfuse_client_from_environment() -> Any:
    """Construct one client inside its owning daemon worker."""

    from langfuse import Langfuse  # type: ignore[import-not-found]

    return Langfuse()


def _langfuse_event_name(event: Mapping[str, object]) -> str:
    event_type = str(event.get("event", "runtime-event"))
    if event_type == "mission_role_invocation":
        return f"{event.get('role', 'mission-role')}-call"
    return {
        "model_turn": "action-policy-call",
        "step_completed": "runtime-step",
        "native_evaluator_returned": "native-evaluator",
        "primary_result_available": "sqlite-checkpoint",
        "benchmark_lifecycle_phase": str(event.get("phase") or "lifecycle"),
    }.get(event_type, event_type.replace("_", "-"))


def _langfuse_observation_type(event: Mapping[str, object]) -> str:
    return {
        "step_completed": "tool",
    }.get(str(event.get("event", "")), "span")


def _langfuse_generation_name(event: Mapping[str, object]) -> str:
    if event.get("event") == "mission_role_invocation":
        return f"{event.get('role', 'mission-role')}-generation"
    return "action-policy-generation"


def _langfuse_generation_attempts(
    event: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    raw = event.get("generation_attempts")
    if not isinstance(raw, tuple | list):
        invocation = event.get("model_invocation")
        raw = invocation.get("attempts", ()) if isinstance(invocation, Mapping) else ()
    return tuple(item for item in raw if isinstance(item, Mapping))


def _langfuse_model_metadata(event: Mapping[str, object]) -> Mapping[str, object]:
    metadata = event.get("model_metadata")
    if isinstance(metadata, Mapping):
        return metadata
    invocation = event.get("model_invocation")
    if isinstance(invocation, Mapping):
        metadata = invocation.get("metadata")
        if isinstance(metadata, Mapping):
            return metadata
    return {}


def _public_task_projection(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return _bounded_remote_projection({
        key: _external_projection(value[key])
        for key in ("task_id", "request_id", "instruction", "objective", "goal")
        if key in value
    })


def _langfuse_event_projection(event: Mapping[str, object]) -> dict[str, object]:
    event_type = str(event.get("event", ""))
    common = {
        "event": event_type,
        "sequence": event.get("sequence"),
    }
    allowed = {
        "goal_compiler_completed": (
            "diagnostic",
        ),
        "model_turn": (
            "context_id", "outcome", "decision", "policy_failure", "model_metadata",
            "visible_action_count", "exception",
        ),
        "mission_role_invocation": (
            "role", "call_index", "trigger_kind", "execution_mode", "subtask_id",
            "mission_version", "assessment", "route", "input_tokens", "output_tokens",
            "latency_ms", "provider_attempts", "result", "failure",
        ),
        "step_completed": ("step", "lineage", "result"),
        "observation": ("observation_id", "observation"),
        "native_evaluator_returned": (
            "evaluation_status", "outcome_kind", "outcome_code", "evidence_refs",
            "observation_id", "checkpoint_id",
        ),
        "official_outcome_persistence": (
            "checkpoint_id", "persistence_status", "persistence_error",
        ),
        "primary_result_available": (
            "case_id", "checkpoint_id", "status", "step_count",
        ),
        "benchmark_lifecycle_phase": (
            "phase", "primary_result_available", "primary_snapshot_available",
        ),
        "benchmark_case_started": ("case_id", "description", "timeout_s"),
        "benchmark_case_finished": ("case_id", "status"),
        "case_lifecycle_phase": ("phase",),
        "finalization_protocol": (
            "stop_send_count", "post_stop_capture_count", "native_evaluator_count",
            "dispatch_status",
        ),
        "run_finished": ("status", "step_count", "observation_count", "execution_count"),
        "run_error": ("exception_class", "status"),
        "benchmark_watchdog": ("code", "cancel_grace_exceeded"),
    }.get(event_type, ())
    projected = {
        key: _external_projection(event.get(key))
        for key in allowed
    }
    if event_type == "goal_compiler_completed":
        diagnostic = projected.get("diagnostic")
        if isinstance(diagnostic, Mapping):
            projected["diagnostic"] = {
                key: diagnostic.get(key)
                for key in (
                    "task_revision", "trigger", "final_disposition",
                    "accepted_plan_version", "reason", "provider_attempt_count",
                )
            }
    elif event_type == "observation":
        projected["observation"] = _compact_world_summary(event.get("observation"))
    elif event_type == "step_completed":
        result = projected.get("result")
        if isinstance(result, Mapping):
            projected["result"] = {
                key: result.get(key)
                for key in (
                    "status_before", "status_after", "feedback", "yield_reason",
                    "decision", "action_outcome", "task_evaluation", "runtime_failure",
                )
                if key in result
            }
    if event_type in {"model_turn", "mission_role_invocation"}:
        active_subtask = _public_active_subtask(event)
        if active_subtask:
            projected["active_subtask"] = active_subtask
    return _bounded_remote_projection({**common, **projected})


def _public_active_subtask(event: Mapping[str, object]) -> dict[str, object]:
    candidates: list[object] = []
    context = event.get("agent_context")
    if isinstance(context, Mapping):
        task = context.get("task")
        if isinstance(task, Mapping):
            candidates.append(task.get("active_subtask"))
    role_request = event.get("role_request")
    if isinstance(role_request, Mapping):
        candidates.append(role_request.get("active_subtask"))
    subtask = next((item for item in candidates if isinstance(item, Mapping)), None)
    if not isinstance(subtask, Mapping):
        return {}
    return {
        key: _external_projection(subtask[key])
        for key in (
            "objective", "done_when", "outcome_kind", "constraints", "required_evidence",
        )
        if key in subtask
    }


def _compact_world_summary(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    facts = value.get("facts")
    actions = value.get("actions") or value.get("affordances")
    documents = value.get("documents")
    summary = {
        "observation_id": value.get("observation_id"),
        "fact_count": len(facts) if isinstance(facts, (list, tuple)) else 0,
        "action_count": len(actions) if isinstance(actions, (list, tuple)) else 0,
        "document_count": len(documents) if isinstance(documents, (list, tuple)) else 0,
    }
    for key in ("route", "url", "primary_heading", "document_title"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            summary[key] = candidate[:512]
    return summary


def model_turn_payload(
    context: object,
    outcome: object,
    policy: object,
    *,
    exception: str = "",
) -> dict[str, object]:
    """Build the single model-turn diagnostic used by traces and benchmark views."""

    backed = _model_backed_policy(policy)
    invocation = getattr(backed, "last_invocation_result", None)
    metadata = getattr(invocation, "metadata", None)
    attempts = tuple(getattr(invocation, "attempts", ()))
    diagnostics = getattr(invocation, "diagnostics", {}) if invocation is not None else {}
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    payload: dict[str, object] = {
        "context_id": getattr(context, "context_id", ""),
        "visible_action_count": len(getattr(getattr(context, "actions", None), "options", ())),
        "provider_attempts": _json_value(attempts, None),
        "generation_attempts": _json_value(attempts, None),
        "model_metadata": _json_value(metadata, None),
        "model_invocation": _json_value(invocation, None),
        "exception": exception,
        "decision": _json_value(outcome, None),
        "outcome": type(outcome).__name__ if not exception else "exception",
    }
    context_id = str(payload["context_id"])
    payload["private_model_capture"] = {
        "context_id": context_id,
        "policy_request_id": (
            "model-request:" + hashlib.sha256(context_id.encode()).hexdigest()[:24]
            if context_id
            else ""
        ),
    }
    selected_grounding = _selected_grounding(context, outcome)
    if selected_grounding is not None:
        payload["selected_grounding"] = selected_grounding
    if diagnostics:
        payload["tool_catalog"] = {
            "count": int(diagnostics.get("tool_catalog_count", 0)),
            "bytes": int(diagnostics.get("tool_catalog_bytes", 0)),
            "specs": _json_value(diagnostics.get("tool_catalog_specs", ()), None),
            "resolution_code": str(diagnostics.get("tool_resolution_code", "")),
            "structured_output_violations": _json_value(
                diagnostics.get("structured_output_violations", ()), None
            ),
            "image_input_count": int(diagnostics.get("model_image_input_count", 0)),
            "model_call_count": int(diagnostics.get("policy_model_call_count", 0)),
            "request_breakdowns": _json_value(diagnostics.get("request_breakdowns", ()), None),
            "admission_action": str(diagnostics.get("admission_action", "")),
            "estimated_total_tokens": int(diagnostics.get("estimated_total_tokens", 0)),
        }
    return payload


def _selected_grounding(context: object, decision: object) -> dict[str, object] | None:
    action_id = getattr(decision, "action_id", "")
    if not action_id:
        return None
    options = getattr(getattr(context, "actions", None), "options", ())
    option = next((item for item in options if getattr(item, "action_id", "") == action_id), None)
    if option is None:
        return None
    destination_id = getattr(decision, "destination_id", "")
    destinations = getattr(getattr(option, "destinations", None), "items", ())
    destination = next(
        (item for item in destinations if getattr(item, "destination_id", "") == destination_id),
        None,
    )
    return {
        "source": {
            "target_id": getattr(option, "target_id", ""),
            "target_ref": getattr(option, "target_ref", ""),
            "label": getattr(option, "target_label", ""),
            "role": getattr(option, "target_role", ""),
            "semantics": _json_value(getattr(option, "target_semantics", {}), None),
            "state": _json_value(getattr(option, "target_state", {}), None),
        },
        "destination": (
            {
                "destination_id": getattr(destination, "destination_id", ""),
                "grounding_ref": getattr(destination, "grounding_ref", ""),
                "label": getattr(destination, "label", ""),
                "semantics": _json_value(getattr(destination, "semantics", {}), None),
            }
            if destination is not None
            else None
        ),
    }


def _step_lineage(result: object) -> dict[str, object]:
    decision = getattr(result, "decision", None)
    execution = getattr(result, "execution", None)
    request = getattr(execution, "request", None)
    return {
        "context_id": getattr(decision, "context_id", ""),
        "tool_call_id": getattr(decision, "tool_call_id", ""),
        "action_id": getattr(decision, "action_id", ""),
        "destination_id": getattr(decision, "destination_id", ""),
        "request_id": getattr(request, "request_id", ""),
        "before_observation_id": getattr(getattr(result, "before_world", None), "observation_id", ""),
        "after_observation_id": getattr(getattr(result, "after_world", None), "observation_id", ""),
    }


def _step_payload(result: object, directory: Path | None) -> dict[str, object]:
    if not is_dataclass(result) or isinstance(result, type):
        return {"value": _json_value(result, directory)}
    return {
        item.name: _json_value(getattr(result, item.name), directory)
        for item in fields(result)
        if item.name not in {"before_world", "after_world"}
    }

def _json_value(value: Any, directory: Path | None) -> Any:
    if isinstance(value, str) and value.startswith("data:image/") and ";base64," in value:
        header, encoded = value.split(",", 1)
        try:
            projected = _json_value(base64.b64decode(encoded, validate=True), directory)
        except (binascii.Error, ValueError):
            return value
        projected["artifact"]["mime_type"] = header.removeprefix("data:").removesuffix(";base64")
        return projected
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, bytes):
        digest = hashlib.sha256(value).hexdigest()
        reference: dict[str, object] = {"sha256": digest, "size_bytes": len(value)}
        if directory is not None:
            relative = Path("artifacts") / f"sha256-{digest}.bin"
            path = directory / relative
            if not path.exists():
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    remaining = memoryview(value)
                    while remaining:
                        written = os.write(descriptor, remaining)
                        if written <= 0:
                            raise OSError("artifact write made no progress")
                        remaining = remaining[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            reference["path"] = str(relative)
        return {"artifact": reference}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name), directory)
            for item in fields(value)
            if item.metadata.get("serialize", True)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item, directory) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item, directory) for item in value]
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(), directory)
    return repr(value)


_REMOTE_PRIVATE_KEYS = frozenset(
    {
        "backend_node_id",
        "binding",
        "private_binding",
        "request_messages",
        "response_content",
        "screenshot",
        "selector",
    }
)
_REMOTE_PUBLIC_ID_KEYS = frozenset(
    {
        "case_id",
        "checkpoint_id",
        "context_id",
        "observation_id",
        "request_id",
        "run_id",
        "subtask_id",
        "task_id",
    }
)
_REMOTE_MAX_DEPTH = 6
_REMOTE_MAX_ITEMS = 40
_REMOTE_MAX_STRING = 512
_REMOTE_MAX_BYTES = 16_384


def _external_projection(value: object, *, _depth: int = 0) -> object:
    if _depth >= _REMOTE_MAX_DEPTH:
        return "[projection-depth-limit]"
    if isinstance(value, Mapping):
        return {
            str(key): _external_projection(item, _depth=_depth + 1)
            for key, item in list(value.items())[:_REMOTE_MAX_ITEMS]
            if not _is_remote_private_key(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [
            _external_projection(item, _depth=_depth + 1)
            for item in value[:_REMOTE_MAX_ITEMS]
        ]
    if isinstance(value, str):
        if value.lstrip().casefold().startswith("data:"):
            return "[binary-content-omitted]"
        return value[:_REMOTE_MAX_STRING]
    return value


def _is_remote_private_key(key: str) -> bool:
    normalized = key.casefold()
    compact = normalized.replace("_", "")
    return normalized in _REMOTE_PRIVATE_KEYS or (
        compact.endswith("id") and normalized not in _REMOTE_PUBLIC_ID_KEYS
    )


def _bounded_remote_projection(value: Mapping[str, object]) -> dict[str, object]:
    projected = _external_projection(value)
    if not isinstance(projected, dict):
        return {"projection_truncated": True}
    serialized = json.dumps(projected, sort_keys=True, default=str).encode()
    if len(serialized) <= _REMOTE_MAX_BYTES:
        return projected
    bounded = {
        "projection_truncated": True,
        "serialized_bytes": len(serialized),
    }
    for key in ("event", "sequence"):
        if key in projected:
            bounded[key] = projected[key]
    return bounded


def _model_backed_policy(value: object) -> object:
    return _find_wrapped(value, "last_invocation_result") or value


def _find_wrapped(value: object, attribute: str) -> object | None:
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if hasattr(item, attribute):
            return item
        for name in ("wrapped", "policy", "port", "decision_port"):
            nested = getattr(item, name, None)
            if nested is not None:
                pending.append(nested)
    return None


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, Enum) else value

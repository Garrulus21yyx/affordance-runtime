"""Complete, non-authoritative tracing for the single GUI-agent Runtime loop."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class RunTraceSink(Protocol):
    """Observe Runtime facts without participating in Runtime control."""

    def run_started(self, task: object, state: object) -> None: ...

    def run_start_failed(self, task: object, acquisition: object) -> None: ...

    def model_turn(
        self,
        context: object,
        outcome: object,
        policy: object,
        *,
        exception: str = "",
    ) -> None: ...

    def step_completed(self, step_number: int, result: object) -> None: ...
    def run_paused(self, state: object) -> None: ...

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None: ...

    def run_error(self, error: BaseException, state: object) -> None: ...

    def run_finished(self, state: object) -> None: ...


@dataclass(frozen=True)
class NullRunTraceSink:
    def run_started(self, task: object, state: object) -> None:
        return None

    def run_start_failed(self, task: object, acquisition: object) -> None:
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
    exporter: Any | None = None
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
        )
        self._observation(getattr(state, "current_world", None))

    def run_start_failed(self, task: object, acquisition: object) -> None:
        self._emit(
            "run_start_failed",
            task=_json_value(task, self.directory),
            acquisition=_json_value(acquisition, self.directory),
        )
        self._export_flush()

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
        self._emit("run_paused", status=_enum_value(getattr(state, "status", "")))
        self._export_flush()

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        self._emit("run_resumed", kind=kind, details=_json_value(details, self.directory))

    def run_error(self, error: BaseException, state: object) -> None:
        self._emit(
            "run_error",
            exception_class=type(error).__name__,
            error=str(error),
            status=_enum_value(getattr(state, "status", "")),
        )
        self._export_flush()

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
        self._export_flush()
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
            if self.exporter is not None:
                self.exporter.emit(event)
        except Exception as exc:  # observability must never become control authority
            self.errors.append(f"{event_type}:{type(exc).__name__}")

    def _export_flush(self) -> None:
        if self.exporter is None:
            return
        try:
            self.exporter.flush()
        except Exception as exc:
            self.errors.append(f"flush:{type(exc).__name__}")


@dataclass
class LangfuseTraceExporter:
    """Optional Langfuse viewer for the same local trace facts."""

    client: Any
    root: Any | None = field(default=None, init=False)

    def emit(self, event: Mapping[str, object]) -> None:
        event_type = event["event"]
        if event_type == "run_started":
            self.root = self.client.start_observation(
                name="gui-agent-run",
                as_type="agent",
                input=_external_projection(event.get("task")),
                metadata={"run_id": event["run_id"]},
            )
            return
        if event_type == "run_start_failed":
            self.root = self.client.start_observation(
                name="gui-agent-run",
                as_type="agent",
                input=_external_projection(event.get("task")),
                metadata={"run_id": event["run_id"]},
            )
            self.root.update(
                output=_external_projection(event.get("acquisition")), level="ERROR"
            )
            self.root.end()
            return
        if self.root is None:
            return
        if event_type == "model_turn":
            turn = self.root.start_observation(
                name="model-turn",
                as_type="chain",
                input=event.get("agent_context"),
                output=event.get("decision") or event.get("policy_failure"),
                metadata=_external_projection({
                    key: event.get(key)
                    for key in (
                        "run_id",
                        "sequence",
                        "context_id",
                        "outcome",
                        "provider_attempts",
                        "model_metadata",
                        "tool_catalog",
                        "private_model_capture",
                        "exception",
                    )
                }),
            )
            attempts = event.get("generation_attempts", ())
            if not isinstance(attempts, (list, tuple)):
                attempts = ()
            for attempt in attempts:
                if not isinstance(attempt, Mapping):
                    continue
                transcript = attempt.get("transcript")
                transcript = transcript if isinstance(transcript, Mapping) else {}
                child = turn.start_observation(
                    name=str(attempt.get("phase") or "model-generation"),
                    as_type="generation",
                    input=_external_projection(transcript.get("llm.input_messages")),
                    output=_external_projection(transcript.get("llm.output_messages")),
                    model=transcript.get("llm.model_name"),
                    usage_details={
                        "input": transcript.get("llm.token_count.prompt", 0),
                        "output": transcript.get("llm.token_count.completion", 0),
                        "total": transcript.get("llm.token_count.total", 0),
                    },
                    metadata={
                        "attempt": attempt.get("attempt"),
                        "schema_name": attempt.get("schema_name"),
                        "status": attempt.get("status"),
                        "violations": attempt.get("violations"),
                        "tools": transcript.get("llm.tools"),
                    },
                )
                child.end()
            turn.end()
        elif event_type == "step_completed":
            child = self.root.start_observation(
                name="runtime-step",
                as_type="tool",
                input=event.get("lineage"),
                output=_external_projection(event.get("result", {})),
            )
            child.end()
        elif event_type == "run_error":
            self.root.update(output=_external_projection(event), level="ERROR")
            self.root.end()
        elif event_type == "run_finished":
            self.root.update(output=_external_projection(event))
            self.root.end()

    def flush(self) -> None:
        self.client.flush()


def langfuse_exporter_from_environment(environment: Mapping[str, str]) -> LangfuseTraceExporter | None:
    enabled = environment.get("AFFORDANCE_LANGFUSE_ENABLED", "").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        return None
    from langfuse import get_client  # type: ignore[import-not-found]

    return LangfuseTraceExporter(get_client())


def trace_recorder_from_environment(environment: Mapping[str, str]) -> RunTraceSink:
    raw_directory = environment.get("AFFORDANCE_TRACE_DIR", "").strip()
    langfuse_enabled = environment.get("AFFORDANCE_LANGFUSE_ENABLED", "").strip().casefold()
    if langfuse_enabled in {"1", "true", "yes", "on"} and not raw_directory:
        raise ValueError("Langfuse export requires AFFORDANCE_TRACE_DIR")
    exporter = langfuse_exporter_from_environment(environment)
    if not raw_directory and exporter is None:
        return NullRunTraceSink()
    return RunTraceRecorder(Path(raw_directory) if raw_directory else None, exporter)


def model_turn_payload(
    context: object,
    outcome: object,
    policy: object,
    *,
    exception: str = "",
) -> dict[str, object]:
    """Build the single model-turn diagnostic used by traces and benchmark views."""

    adapter = _dynamic_tool_adapter(policy)
    backed = _model_backed_policy(policy)
    metadata = getattr(backed, "last_metadata", None)
    attempts = getattr(backed, "last_provider_attempts", ())
    payload: dict[str, object] = {
        "context_id": getattr(context, "context_id", ""),
        "visible_action_count": len(getattr(getattr(context, "actions", None), "options", ())),
        "provider_attempts": _json_value(attempts, None),
        "model_metadata": _json_value(metadata, None),
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
    if adapter is not None:
        payload["tool_catalog"] = {
            "count": int(getattr(adapter, "last_catalog_count", 0)),
            "bytes": int(getattr(adapter, "last_catalog_bytes", 0)),
            "specs": _json_value(getattr(adapter, "last_catalog_specs", ()), None),
            "selected_operation": str(getattr(adapter, "last_selected_operation", "")),
            "resolution_code": _enum_value(getattr(adapter, "last_resolution_code", "")),
            "argument_repair_count": int(getattr(adapter, "last_argument_repair_count", 0)),
            "argument_violation_code": str(getattr(adapter, "last_argument_violation_code", "")),
            "argument_violation_paths": list(getattr(adapter, "last_argument_violation_paths", ())),
            "structured_output_violations": _json_value(
                getattr(adapter, "last_structured_output_violations", ()), None
            ),
            "image_input_count": int(
                getattr(adapter, "last_image_input_count", len(getattr(context, "image_inputs", ())))
            ),
            "model_call_count": int(getattr(adapter, "last_model_call_count", 0)),
        }
        payload["generation_attempts"] = _json_value(
            getattr(adapter, "last_generation_attempts", ()), None
        )
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
        return {item.name: _json_value(getattr(value, item.name), directory) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item, directory) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item, directory) for item in value]
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(), directory)
    return repr(value)


def _external_projection(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _external_projection(item)
            for key, item in value.items()
            if key not in {"binding", "private_binding", "request_messages", "response_content"}
        }
    if isinstance(value, list):
        return [_external_projection(item) for item in value]
    return value


def _dynamic_tool_adapter(value: object) -> object | None:
    return _find_wrapped(value, "last_catalog_count")


def _model_backed_policy(value: object) -> object:
    return _find_wrapped(value, "last_provider_attempts") or value


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

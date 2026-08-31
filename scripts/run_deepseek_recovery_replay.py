#!/usr/bin/env python3
"""Replay frozen recovery turns across DeepSeek model/reasoning arms.

The replay stops at the model boundary: it never binds or dispatches the
returned ToolCall.  Every arm receives the same recorded messages, current
tool schemas, output cap, and atomic-recovery instruction.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.model.policy.pydantic_ai_bridge import (
    _pydantic_atomic_recovery_prompt,
    pydantic_ai_model_from_environment,
)

_SCHEMA_VERSION = "deepseek-recovery-replay.v2"
_DEFAULT_TRACE_ROOT = Path("evidence/live/webarena-diagnostic10b-deepseek-v4-flash-20260831-de6ff135/all10/traces")
_ARM_SPECS = {
    "F0": ("deepseek-v4-flash", False),
    "F1": ("deepseek-v4-flash", True),
    "P0": ("deepseek-v4-pro", False),
    "P1": ("deepseek-v4-pro", True),
}


@dataclass(frozen=True)
class FrozenRecoveryContext:
    case_id: str
    task_instruction: str
    trace_path: str
    sequence: int
    context_id: str
    source_digest: str
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolDefinition, ...]
    tool_schemas: Mapping[str, Mapping[str, Any]]
    prior_call: Mapping[str, Any] | None
    original_call: Mapping[str, Any] | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", type=Path, default=_DEFAULT_TRACE_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", choices=tuple(_ARM_SPECS), default=tuple(_ARM_SPECS))
    parser.add_argument("--limit", type=int, default=0, help="maximum contexts; zero means all")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--tool-choice", choices=("auto", "required"), default="auto")
    return parser.parse_args()


def _json_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _tool_definitions(raw_tools: Sequence[object]) -> tuple[tuple[ToolDefinition, ...], dict[str, Mapping[str, Any]]]:
    definitions: list[ToolDefinition] = []
    schemas: dict[str, Mapping[str, Any]] = {}
    for raw in raw_tools:
        if not isinstance(raw, Mapping):
            raise ValueError("recorded tool must be an object")
        name = str(raw.get("tool.name") or "").strip()
        schema = raw.get("tool.json_schema")
        if not name or not isinstance(schema, Mapping):
            raise ValueError("recorded tool is missing name or schema")
        normalized_schema = dict(schema)
        definitions.append(
            ToolDefinition(
                name=name,
                description=str(raw.get("tool.description") or ""),
                parameters_json_schema=normalized_schema,
            )
        )
        schemas[name] = normalized_schema
    return tuple(definitions), schemas


def _task_instruction(messages: Sequence[ModelMessage]) -> str:
    def text_values(value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list | tuple):
            return tuple(text for item in value for text in text_values(item))
        content = getattr(value, "content", None)
        return text_values(content) if content is not None else ()

    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if not isinstance(part, UserPromptPart):
                continue
            for value in text_values(part.content):
                try:
                    payload = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, Mapping):
                    continue
                task = payload.get("task")
                if isinstance(task, Mapping) and isinstance(task.get("instruction"), str):
                    return task["instruction"].strip()
    return ""


def _decision_call(raw: object) -> Mapping[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    name = str(raw.get("tool_name") or raw.get("kind") or "").strip()
    if not name:
        return None
    explicit_arguments = raw.get("arguments")
    if isinstance(explicit_arguments, Mapping):
        arguments = dict(explicit_arguments)
    else:
        metadata_keys = {
            "context_id",
            "kind",
            "rejected_attempt_signature",
            "result",
            "tool_call_id",
            "tool_name",
        }
        arguments = {str(key): value for key, value in raw.items() if key not in metadata_keys}
    return {"tool_name": name, "arguments": arguments}


def _call_value(part: ToolCallPart) -> dict[str, Any]:
    return {
        "tool_name": part.tool_name,
        "arguments": part.args_as_dict(raise_if_invalid=False),
    }


def _prior_call(messages: Sequence[ModelMessage]) -> Mapping[str, Any] | None:
    latest_return: ToolReturnPart | None = None
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        latest_return = next((part for part in reversed(message.parts) if isinstance(part, ToolReturnPart)), None)
        if latest_return is not None:
            break
    if latest_return is None:
        return None
    for message in reversed(messages):
        if not isinstance(message, ModelResponse):
            continue
        for part in reversed(message.parts):
            if isinstance(part, ToolCallPart) and part.tool_call_id == latest_return.tool_call_id:
                return _call_value(part)
    return {"tool_name": latest_return.tool_name, "arguments": {}}


def _serialized_tool_calls(raw_messages: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw_messages, list):
        return ()
    calls: list[dict[str, Any]] = []
    for message in raw_messages:
        if not isinstance(message, Mapping):
            continue
        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, Mapping) or part.get("part_kind") != "tool-call":
                continue
            raw_args = part.get("args", part.get("arguments", {}))
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {"_invalid_json": raw_args[:240]}
            calls.append(
                {
                    "tool_name": str(part.get("tool_name") or ""),
                    "arguments": raw_args if isinstance(raw_args, Mapping) else {},
                }
            )
    return tuple(calls)


def _append_atomic_instruction(messages: Sequence[ModelMessage]) -> tuple[ModelMessage, ...]:
    instruction = _pydantic_atomic_recovery_prompt("", complete_retry=False)[-1]
    updated = list(messages)
    for index in range(len(updated) - 1, -1, -1):
        message = updated[index]
        if not isinstance(message, ModelRequest):
            continue
        parts = list(message.parts)
        for part_index in range(len(parts) - 1, -1, -1):
            part = parts[part_index]
            if not isinstance(part, UserPromptPart):
                continue
            if isinstance(part.content, list | tuple):
                content = [*part.content, instruction]
            else:
                content = [part.content, instruction]
            parts[part_index] = replace(part, content=content)
            updated[index] = replace(message, parts=parts)
            return tuple(updated)
        parts.append(UserPromptPart(instruction))
        updated[index] = replace(message, parts=parts)
        return tuple(updated)
    raise ValueError("recorded recovery context has no ModelRequest")


def _load_contexts(trace_root: Path, *, limit: int) -> tuple[FrozenRecoveryContext, ...]:
    contexts: list[FrozenRecoveryContext] = []
    for trace_path in sorted(trace_root.glob("*/trace.jsonl")):
        selected: FrozenRecoveryContext | None = None
        last_decision_call: Mapping[str, Any] | None = None
        with trace_path.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("event") != "model_turn":
                    continue
                attempts = event.get("generation_attempts")
                if not isinstance(attempts, list):
                    continue
                for attempt in attempts:
                    if not isinstance(attempt, Mapping):
                        continue
                    if attempt.get("phase") != "deliberate" or attempt.get("trigger") != "control_stall":
                        continue
                    transcript = attempt.get("transcript")
                    if not isinstance(transcript, Mapping):
                        continue
                    raw_messages = transcript.get("llm.input_messages")
                    raw_tools = transcript.get("llm.tools")
                    if not isinstance(raw_messages, list) or not isinstance(raw_tools, list):
                        continue
                    messages = tuple(ModelMessagesTypeAdapter.validate_python(raw_messages))
                    tools, schemas = _tool_definitions(raw_tools)
                    source_value = {
                        "messages": raw_messages,
                        "tools": raw_tools,
                        "context_id": event.get("context_id"),
                    }
                    selected = FrozenRecoveryContext(
                        case_id=trace_path.parent.name,
                        task_instruction=_task_instruction(messages),
                        trace_path=str(trace_path),
                        sequence=int(event.get("sequence") or 0),
                        context_id=str(event.get("context_id") or ""),
                        source_digest=_json_digest(source_value),
                        messages=_append_atomic_instruction(messages),
                        tools=tools,
                        tool_schemas=schemas,
                        prior_call=last_decision_call or _prior_call(messages),
                        original_call=next(
                            iter(_serialized_tool_calls(transcript.get("llm.output_messages"))),
                            None,
                        ),
                    )
                    break
                if selected is not None:
                    break
                current_decision = _decision_call(event.get("decision"))
                if current_decision is not None:
                    last_decision_call = current_decision
        if selected is not None:
            contexts.append(selected)
            if limit and len(contexts) >= limit:
                break
    if not contexts:
        raise ValueError("no recorded deliberate control_stall contexts found")
    return tuple(contexts)


def _json_value(value: object) -> object:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _semantic_signature(call: Mapping[str, Any] | None) -> str:
    if call is None:
        return ""
    arguments = call.get("arguments")
    normalized = dict(arguments) if isinstance(arguments, Mapping) else {}
    normalized.pop("public_intent", None)
    return json.dumps(
        {"tool_name": str(call.get("tool_name") or ""), "arguments": normalized},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _response_result(
    response: ModelResponse,
    context: FrozenRecoveryContext,
    *,
    arm: str,
    repetition: int,
    latency_ms: float,
) -> dict[str, Any]:
    calls = tuple(_call_value(part) for part in response.parts if isinstance(part, ToolCallPart))
    text = "\n".join(
        str(getattr(part, "content", ""))
        for part in response.parts
        if not isinstance(part, ThinkingPart | ToolCallPart) and str(getattr(part, "content", "")).strip()
    )
    reasoning_chars = sum(
        len(part.content) for part in response.parts if isinstance(part, ThinkingPart) and isinstance(part.content, str)
    )
    schema_error = ""
    if len(calls) == 1:
        call = calls[0]
        schema = context.tool_schemas.get(str(call.get("tool_name") or ""))
        if schema is None:
            schema_error = "unknown_tool"
        else:
            try:
                validate_value(call.get("arguments"), schema)
            except (TypeError, ValueError) as error:
                schema_error = str(error)
    else:
        schema_error = "tool_call_count"
    selected_call = calls[0] if len(calls) == 1 else None
    prior_signature = _semantic_signature(context.prior_call)
    original_signature = _semantic_signature(context.original_call)
    selected_signature = _semantic_signature(selected_call)
    finish_reason = str(response.finish_reason or "")
    usage = _json_value(response.usage)
    return {
        "case_id": context.case_id,
        "sequence": context.sequence,
        "context_id": context.context_id,
        "source_digest": context.source_digest,
        "arm": arm,
        "repetition": repetition,
        "model": _ARM_SPECS[arm][0],
        "thinking": "high" if _ARM_SPECS[arm][1] else "disabled",
        "status": "accepted" if not schema_error and finish_reason not in {"length", "max_tokens"} else "invalid",
        "finish_reason": finish_reason,
        "latency_ms": round(latency_ms, 3),
        "tool_calls": calls,
        "tool_call_count": len(calls),
        "schema_error": schema_error,
        "exact_replay": bool(selected_signature and selected_signature == prior_signature),
        "matches_original_recovery_call": bool(
            selected_signature and original_signature and selected_signature == original_signature
        ),
        "operation_changed": bool(
            selected_call
            and context.prior_call
            and selected_call.get("tool_name") != context.prior_call.get("tool_name")
        ),
        "arguments_changed": bool(selected_call and prior_signature and selected_signature != prior_signature),
        "reasoning_chars": reasoning_chars,
        "final_text_chars": len(text),
        "final_text_preview": text[:480],
        "usage": usage,
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.repeats < 1 or args.repeats > 10:
        raise ValueError("repeats must be within [1, 10]")
    if args.concurrency < 1 or args.concurrency > 16:
        raise ValueError("concurrency must be within [1, 16]")
    if args.limit < 0:
        raise ValueError("limit must be non-negative")
    contexts = _load_contexts(args.trace_root, limit=args.limit)
    models = {}
    for arm in args.arms:
        model_name, _thinking = _ARM_SPECS[arm]
        if model_name in models:
            continue
        environment = dict(os.environ)
        environment["LLM_ACTIVE_PROFILE"] = "deepseek"
        environment["LLM_DEEPSEEK_MODEL"] = model_name
        configured = pydantic_ai_model_from_environment(environment, call_timeout_s=args.timeout)
        models[model_name] = configured.model

    semaphore = asyncio.Semaphore(args.concurrency)

    async def invoke(context: FrozenRecoveryContext, arm: str, repetition: int) -> dict[str, Any]:
        model_name, thinking = _ARM_SPECS[arm]
        settings: dict[str, object] = {
            "max_tokens": args.max_tokens,
            "parallel_tool_calls": False,
            "temperature": 0.0,
            "thinking": thinking,
            "timeout": args.timeout,
            "tool_choice": args.tool_choice,
        }
        if thinking:
            settings["reasoning_effort"] = "high"
        parameters = ModelRequestParameters(
            function_tools=list(context.tools),
            allow_text_output=True,
        )
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await models[model_name].request(list(context.messages), settings, parameters)
                return _response_result(
                    response,
                    context,
                    arm=arm,
                    repetition=repetition,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            except Exception as error:  # noqa: BLE001 - provider failures are experiment outcomes
                return {
                    "case_id": context.case_id,
                    "sequence": context.sequence,
                    "context_id": context.context_id,
                    "source_digest": context.source_digest,
                    "arm": arm,
                    "repetition": repetition,
                    "model": model_name,
                    "thinking": "high" if thinking else "disabled",
                    "status": "provider_error",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error_class": type(error).__name__,
                    "error": str(error)[:1000],
                }

    results = await asyncio.gather(
        *(
            invoke(context, arm, repetition)
            for context in contexts
            for repetition in range(1, args.repeats + 1)
            for arm in args.arms
        )
    )
    summaries: dict[str, dict[str, object]] = {}
    for arm in args.arms:
        arm_results = [item for item in results if item["arm"] == arm]
        accepted = [item for item in arm_results if item["status"] == "accepted"]

        def usage_count(item: Mapping[str, object], name: str) -> int:
            usage = item.get("usage")
            value = usage.get(name) if isinstance(usage, Mapping) else None
            return value if type(value) is int and value >= 0 else 0

        def reasoning_tokens(item: Mapping[str, object]) -> int:
            usage = item.get("usage")
            details = usage.get("details") if isinstance(usage, Mapping) else None
            value = details.get("reasoning_tokens") if isinstance(details, Mapping) else None
            return value if type(value) is int and value >= 0 else 0

        summaries[arm] = {
            "model": _ARM_SPECS[arm][0],
            "thinking": "high" if _ARM_SPECS[arm][1] else "disabled",
            "calls": len(arm_results),
            "accepted": len(accepted),
            "provider_errors": sum(item["status"] == "provider_error" for item in arm_results),
            "length_truncations": sum(item.get("finish_reason") in {"length", "max_tokens"} for item in arm_results),
            "tool_call_count_errors": sum(item.get("schema_error") == "tool_call_count" for item in arm_results),
            "zero_tool_calls": sum(int(item.get("tool_call_count") or 0) == 0 for item in arm_results),
            "multiple_tool_calls": sum(int(item.get("tool_call_count") or 0) > 1 for item in arm_results),
            "exact_replays": sum(bool(item.get("exact_replay")) for item in accepted),
            "matches_original_recovery_call": sum(
                bool(item.get("matches_original_recovery_call")) for item in accepted
            ),
            "operation_changes": sum(bool(item.get("operation_changed")) for item in accepted),
            "responses_with_final_text": sum(int(item.get("final_text_chars") or 0) > 0 for item in arm_results),
            "mean_latency_ms": round(
                sum(float(item["latency_ms"]) for item in arm_results) / len(arm_results),
                3,
            ),
            "mean_reasoning_chars": round(
                sum(int(item.get("reasoning_chars") or 0) for item in arm_results) / len(arm_results),
                3,
            ),
            "mean_output_tokens": round(
                sum(usage_count(item, "output_tokens") for item in arm_results) / len(arm_results),
                3,
            ),
            "mean_reasoning_tokens": round(
                sum(reasoning_tokens(item) for item in arm_results) / len(arm_results),
                3,
            ),
        }
    return {
        "schema_version": _SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": os.environ.get("REPLAY_SOURCE_COMMIT", "").strip(),
        "trace_root": str(args.trace_root),
        "contract": {
            "dispatch": False,
            "same_recorded_context_for_all_arms": True,
            "atomic_recovery_instruction": True,
            "max_tokens": args.max_tokens,
            "tool_choice": args.tool_choice,
            "reasoning_effort_when_enabled": "high",
            "repeats": args.repeats,
        },
        "contexts": [
            {
                "case_id": context.case_id,
                "task_instruction": context.task_instruction,
                "trace_path": context.trace_path,
                "sequence": context.sequence,
                "context_id": context.context_id,
                "source_digest": context.source_digest,
                "prior_call": context.prior_call,
                "original_call": context.original_call,
                "tool_count": len(context.tools),
            }
            for context in contexts
        ],
        "summary": summaries,
        "results": results,
    }


def main() -> None:
    args = _arguments()
    report = asyncio.run(_run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

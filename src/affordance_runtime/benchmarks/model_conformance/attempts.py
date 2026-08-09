"""One-call structured conformance attempt; no retries or fallback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from affordance_runtime.model_port import (
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
)

from .contracts import ConformanceAttempt, ModelConformanceStage, SecretFreeSalienceMetrics
from .stages import attribute_decision_payload


async def run_structured_attempt(
    port: ModelPort,
    output_schema: type[BaseModel],
    messages: tuple[str, str],
    *,
    level: str,
    grounding_variant: str,
    attempt_number: int,
    config: ModelConfig | None = None,
    expected_context_id: str = "",
    visible_action_ids: tuple[str, ...] = (),
    visible_destinations: dict[str, tuple[str, ...]] | None = None,
    visible_targets: dict[str, str] | None = None,
    context_bytes: int | None = None,
) -> ConformanceAttempt:
    system, user = messages
    config = config or ModelConfig(
        timeout_s=89, rate_limit_retries=0, transient_retries=0, prompt_version="p5-m1.1",
    )
    schema = output_schema.model_json_schema()
    started = perf_counter()
    output = ""
    stage = ModelConformanceStage.SUCCESS
    failure = ""
    variant = ""
    try:
        payload = await port.generate_structured(
            (ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)),
            output_schema,
            config,
        )
        output = payload.model_dump_json()
        variant = str(getattr(getattr(payload, "root", payload), "type", ""))
    except TimeoutError:
        stage, failure = ModelConformanceStage.TIMEOUT, "timeout"
    except ProviderModelError as exc:
        stage, failure = ModelConformanceStage.TRANSPORT, exc.kind.value
    except StructuredOutputError:
        stage, failure = ModelConformanceStage.STRUCTURED_OUTPUT, "structured_output"
    except StructuredModelError:
        stage, failure = ModelConformanceStage.STRUCTURED_OUTPUT, "provider_schema_or_envelope"
    except Exception as exc:
        stage, failure = ModelConformanceStage.TRANSPORT, type(exc).__name__
    elapsed = (perf_counter() - started) * 1_000
    record = port.last_call
    schema_bytes = len(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode())
    output_bytes = len(output.encode())
    digest = f"sha256:{hashlib.sha256(output.encode()).hexdigest()}" if output else ""
    salience = _salience_metrics(
        user,
        visible_action_ids[0] if len(visible_action_ids) == 1 else "",
        (visible_targets or {}).get(visible_action_ids[0], "") if len(visible_action_ids) == 1 else "",
        tuple(
            item
            for values in (visible_destinations or {}).values()
            for item in values
            if item
        ),
    )
    attempt = ConformanceAttempt(
        f"attempt:{grounding_variant}:{level}:{attempt_number}", level, grounding_variant,
        stage, stage == ModelConformanceStage.SUCCESS, failure, variant,
        len(user.encode()) if context_bytes is None else context_bytes,
        len(system.encode()), len(user.encode()), schema_bytes,
        len(system.encode()) + len(user.encode()) + schema_bytes,
        _visible_count(user, "action_id"), _visible_count(user, "target_id"),
        _visible_count(user, "fact_ref"), _history_count(user),
        record.prompt_tokens if record else 0, record.completion_tokens if record else 0,
        record.total_tokens if record else 0, output_bytes, digest,
        record.latency_ms if record else elapsed,
        salience_metrics=salience,
    )
    if stage != ModelConformanceStage.SUCCESS or not expected_context_id:
        return attempt
    attributed = attribute_decision_payload(
        output,
        expected_context_id,
        visible_action_ids,
        visible_destinations or {},
        visible_targets=visible_targets or {},
    )
    return replace(
        attempt,
        stage=attributed.stage,
        success=attributed.stage == ModelConformanceStage.SUCCESS,
        failure_kind=attributed.failure_kind,
        decision_variant=attributed.decision_variant,
        destination_failure_shape=attributed.destination_failure_shape,
    )


def _visible_count(user: str, key: str) -> int:
    try:
        return _count_key(json.loads(user), key)
    except (json.JSONDecodeError, TypeError):
        return 0


def _count_key(value: Any, key: str) -> int:
    if isinstance(value, dict):
        return int(key in value) + sum(_count_key(item, key) for item in value.values())
    if isinstance(value, list):
        return sum(_count_key(item, key) for item in value)
    return 0


def _history_count(user: str) -> int:
    try:
        value = json.loads(user)
        return len(value.get("history", {}).get("items", ()))
    except (AttributeError, json.JSONDecodeError, TypeError):
        return 0


def _salience_metrics(
    user: str,
    action_id: str,
    target_id: str,
    destination_ids: tuple[str, ...],
) -> SecretFreeSalienceMetrics:
    encoded = user.encode()
    context = _public_context(user)
    return SecretFreeSalienceMetrics(
        selected_target_id_occurrences=user.count(target_id) if target_id else 0,
        allowed_destination_id_occurrences=sum(user.count(item) for item in set(destination_ids)),
        selected_action_id_occurrences=user.count(action_id) if action_id else 0,
        last_target_id_distance_from_end_bytes=_distance_from_end(encoded, target_id),
        last_destination_id_distance_from_end_bytes=_last_destination_distance(encoded, destination_ids),
        actions_block_distance_from_end_bytes=_distance_from_end(encoded, '"actions"'),
        context_bytes=len(encoded),
        facts_count=_visible_count(json.dumps(context), "fact_ref"),
        artifacts_count=_section_count(context, "artifact_summaries"),
        target_count=_section_count(context, "targets"),
    )


def _public_context(user: str) -> dict[str, Any]:
    try:
        value = json.loads(user)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    nested = value.get("agent_context")
    return nested if isinstance(nested, dict) else value


def _section_count(context: dict[str, Any], name: str) -> int:
    world = context.get("world", {})
    section = world.get(name, {}) if isinstance(world, dict) else {}
    items = section.get("items", ()) if isinstance(section, dict) else ()
    return len(items) if isinstance(items, list | tuple) else 0


def _distance_from_end(encoded: bytes, value: str) -> int | None:
    if not value:
        return None
    token = value.encode()
    position = encoded.rfind(token)
    return None if position < 0 else len(encoded) - position - len(token)


def _last_destination_distance(encoded: bytes, values: tuple[str, ...]) -> int | None:
    distances = tuple(
        distance
        for item in set(values)
        if (distance := _distance_from_end(encoded, item)) is not None
    )
    return min(distances) if distances else None

"""Run fixed conformance levels against one exact model profile."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.model_policy.spec import AgentDecisionPayload
from affordance_runtime.model_port import ModelPort

from .attempts import run_structured_attempt
from .classification import classify_policy_capabilities, classify_support
from .contracts import (
    ConformanceAttempt,
    ConformanceCellSummary,
    ModelInputComplexity,
    ModelProfileConformanceResult,
    ModelProfileIdentity,
)
from .destination_ladder import build_destination_case
from .grounding import GroundingVariant, build_grounded_input, diagnostic_schema_model
from .levels import Level0Payload, Level1SelectActionPayload, minimal_select_context, minimal_union_context
from .loop_attempt import run_level_four_attempt
from .scenario import LiveDomScenario, build_live_dom_scenario


async def run_profile(
    identity: ModelProfileIdentity,
    port_factory: Callable[[], ModelPort],
    *,
    levels: tuple[str, ...],
    grounding_variants: tuple[str, ...],
    repetitions: int,
    output_dir: Path,
    support_attestation: bool = False,
) -> ModelProfileConformanceResult:
    if repetitions < 1 or repetitions > 20:
        raise ValueError("conformance repetitions must be in [1, 20]")
    variants = tuple(GroundingVariant(item) for item in grounding_variants)
    scenario = await build_live_dom_scenario() if set(levels) - {"0"} else None
    attempts = []
    for grounding in variants:
        for level in levels:
            for number in range(1, repetitions + 1):
                port = port_factory()
                attempts.append(
                    await _run_level(port, scenario, level, grounding, number)
                )
    counts = {
        level: (
            sum(item.success for item in attempts if item.level == level),
            sum(item.level == level for item in attempts),
        )
        for level in levels
    }
    status = classify_support(
        counts, tuple(item.stage for item in attempts if not item.success),
        support_attestation=support_attestation,
    )
    capabilities = classify_policy_capabilities(
        counts,
        tuple(item.stage for item in attempts if not item.success),
        support_attestation=support_attestation,
        recurrent_matrix=None,
    )
    result = ModelProfileConformanceResult(
        identity, tuple(attempts),
        tuple(level for level, (passed, total) in counts.items() if passed == total and total),
        tuple(level for level, (passed, total) in counts.items() if passed < total),
        status.value, tuple(f"level {level}: {passed}/{total}" for level, (passed, total) in counts.items()),
        scenario.complexity if scenario is not None else ModelInputComplexity(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ),
        _cell_summaries(tuple(attempts)),
        capabilities.structured_output_status.value,
        capabilities.action_selection_status.value,
        capabilities.full_recurrent_decision_status.value,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(asdict(result), sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return result


def _cell_summaries(attempts: tuple[ConformanceAttempt, ...]) -> tuple[ConformanceCellSummary, ...]:
    cells = []
    keys = sorted({(item.grounding_variant, item.level) for item in attempts})
    for grounding, level in keys:
        selected = tuple(
            item for item in attempts
            if item.grounding_variant == grounding and item.level == level
        )
        shapes = Counter(item.destination_failure_shape.value for item in selected if item.destination_failure_shape)
        variants = Counter(item.decision_variant for item in selected if item.decision_variant)
        cells.append(ConformanceCellSummary(
            level,
            grounding,
            len(selected),
            sum(item.success for item in selected),
            tuple(sorted(shapes.items())),
            tuple(sorted(variants.items())),
            tuple(item.prompt_tokens for item in selected),
            tuple(item.completion_tokens for item in selected),
            tuple(item.latency_ms for item in selected),
        ))
    return tuple(cells)


async def _run_level(port, scenario, level, grounding: GroundingVariant, number):
    if level == "0":
        return await run_structured_attempt(
            port, Level0Payload, ("Return the required JSON object.", "{}"),
            level=level, grounding_variant=grounding.value, attempt_number=number,
        )
    if scenario is None:
        raise ValueError("levels 1-4 require the live DOM scenario")
    if level.startswith("D"):
        return await _run_destination_level(port, scenario, level, grounding, number)
    option = scenario.context.actions.options[0]
    destination = option.destinations.items[0].destination_id if option.destination_required else ""
    destinations = (
        tuple(item.destination_id for item in option.destinations.items)
        if option.destination_required
        else ("",)
    )
    if level == "4":
        if grounding not in {GroundingVariant.FORMAT_ONLY, GroundingVariant.COMPACT_CONTRACT}:
            raise ValueError("level 4 admits only production format-only or compact-contract variants")
        return await run_level_four_attempt(
            port, grounding_variant=grounding.value, attempt_number=number,
        )
    user = _level_user(scenario, level, destination)
    schema = Level1SelectActionPayload if level == "1" else AgentDecisionPayload
    base_schema = schema.model_json_schema()
    grounded = build_grounded_input(
        user, base_schema, grounding, guide_context=scenario.serialized_context,
    )
    output_schema = (
        diagnostic_schema_model(schema, grounded.provider_schema)
        if grounded.provider_schema != base_schema else schema
    )
    return await run_structured_attempt(
        port, output_schema, (grounded.system_message, grounded.user_message), level=level,
        grounding_variant=grounding.value, attempt_number=number,
        expected_context_id=scenario.context.context_id,
        visible_action_ids=(option.action_id,), visible_destinations={option.action_id: destinations},
        visible_targets={option.action_id: option.target_id},
        context_bytes=len(scenario.serialized_context.encode()),
    )


async def _run_destination_level(port, scenario, level, grounding, number):
    case = build_destination_case(level, scenario)
    base_schema = AgentDecisionPayload.model_json_schema()
    grounded = build_grounded_input(
        case.serialized_context,
        base_schema,
        grounding,
        guide_context=case.serialized_context,
    )
    output_schema = (
        diagnostic_schema_model(AgentDecisionPayload, grounded.provider_schema)
        if grounded.provider_schema != base_schema else AgentDecisionPayload
    )
    return await run_structured_attempt(
        port,
        output_schema,
        (grounded.system_message, grounded.user_message),
        level=level,
        grounding_variant=grounding.value,
        attempt_number=number,
        expected_context_id=scenario.context.context_id,
        visible_action_ids=(case.action_id,),
        visible_destinations=dict(case.visible_destinations),
        visible_targets={case.action_id: case.target_id},
        context_bytes=len(case.serialized_context.encode()),
        required_decision_variant="select_action",
    )


def _level_user(scenario: LiveDomScenario, level: str, destination: str) -> str:
    option = scenario.context.actions.options[0]
    args = (
        scenario.context.context_id, option.action_id, option.semantic_action,
        option.target_id, option.target_label, destination,
    )
    if level == "1":
        return minimal_select_context(*args)
    if level == "2":
        return minimal_union_context(*args)
    if level == "3":
        return scenario.serialized_context
    raise ValueError(f"unsupported conformance level: {level}")


__all__ = [
    "LiveDomScenario", "build_live_dom_scenario", "run_profile", "run_structured_attempt",
]

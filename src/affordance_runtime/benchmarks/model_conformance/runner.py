"""Run fixed conformance levels against one exact model profile."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.model_policy.spec import AgentDecisionPayload
from affordance_runtime.model_port import ModelPort

from .attempts import run_structured_attempt
from .classification import classify_support
from .contracts import ModelInputComplexity, ModelProfileConformanceResult, ModelProfileIdentity
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
    result = ModelProfileConformanceResult(
        identity, tuple(attempts),
        tuple(level for level, (passed, total) in counts.items() if passed == total and total),
        tuple(level for level, (passed, total) in counts.items() if passed < total),
        status.value, tuple(f"level {level}: {passed}/{total}" for level, (passed, total) in counts.items()),
        scenario.complexity if scenario is not None else ModelInputComplexity(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(asdict(result), sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return result


async def _run_level(port, scenario, level, grounding: GroundingVariant, number):
    if level == "0":
        return await run_structured_attempt(
            port, Level0Payload, ("Return the required JSON object.", "{}"),
            level=level, grounding_variant=grounding.value, attempt_number=number,
        )
    if scenario is None:
        raise ValueError("levels 1-4 require the live DOM scenario")
    option = scenario.context.actions.options[0]
    destination = option.destinations.items[0].destination_id if option.destination_required else ""
    destinations = tuple(["", *(item.destination_id for item in option.destinations.items)])
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
        context_bytes=len(scenario.serialized_context.encode()),
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

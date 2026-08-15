"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.actor_world_snapshot import actor_world_for_delivery
from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.contracts import AgentTurnView
from affordance_runtime.model_boundary.projection import project_public_value
from affordance_runtime.model_policy.contracts import ModelDecisionRequest
from affordance_runtime.model_policy.grounded_tool_contracts import MAX_GROUNDED_WORKSPACE_BYTES
from affordance_runtime.model_policy.model_port_bridge import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model_policy.tool_contracts import ToolSpec
from affordance_runtime.model_port import ModelImageURLPart, ModelMessage, ModelTextPart


@dataclass(frozen=True)
class GroundedAgentPrompts:
    version: str
    actor: str

    def __post_init__(self) -> None:
        if not self.version or not self.actor.strip():
            raise ValueError("grounded-agent prompt bundle is incomplete")


@lru_cache(maxsize=1)
def load_grounded_agent_prompts() -> GroundedAgentPrompts:
    resource = files("affordance_runtime.model_policy").joinpath("prompts/grounded_agent.yaml")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"version", "actor"}:
        raise ValueError("grounded-agent prompt bundle has an invalid shape")
    return GroundedAgentPrompts(
        str(raw["version"]),
        str(raw["actor"]),
    )


@dataclass(frozen=True)
class GroundedPolicyContextBinder:
    """Convert one canonical AgentContext to one provider message boundary."""

    prompts: GroundedAgentPrompts = field(default_factory=load_grounded_agent_prompts)

    def action_messages(
        self,
        context: AgentContext,
        tools: tuple[ToolSpec, ...],
        request: ModelDecisionRequest,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> tuple[ModelMessage, ...]:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        public = self._public_context(context, include_images)
        if include_tool_menu:
            public["tools"] = _tool_menu(tools)
        return self._messages(self.prompts.actor, public, request, include_images)

    @staticmethod
    def _public_context(
        context: AgentContext,
        include_images: bool,
    ) -> dict[str, object]:
        refs = dict(context.grounding.target_refs)
        evidence_refs = _evidence_refs(context)
        if context.actor_world is None:
            raise ValueError("grounded policy requires an ActorWorldSnapshot")
        public: dict[str, object] = {
            "task": _task(context),
            "world": to_json_compatible(
                actor_world_for_delivery(context.actor_world, include_images=include_images)
            ),
            "progress": _progress(context, refs, evidence_refs),
            "last_transition": to_json_compatible(context.last_transition),
            "history": _section(context.history, lambda item: _turn(item, refs)),
            "control_feedback": _control_feedback(context, refs),
        }
        return public

    @staticmethod
    def _include_images(
        request: ModelDecisionRequest,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
    ) -> bool:
        include_images = perception_uses_images(request, perception_profile)
        if include_images and (not supports_multimodal or not request.image_inputs):
            raise ValueError("selected grounded perception requires a current image input")
        return include_images

    @staticmethod
    def _messages(
        system_prompt: str,
        public: Mapping[str, object],
        request: ModelDecisionRequest,
        include_images: bool,
    ) -> tuple[ModelMessage, ...]:
        text = json.dumps(public, separators=(",", ":"), ensure_ascii=False)
        if len(text.encode()) > MAX_GROUNDED_WORKSPACE_BYTES:
            raise ValueError("grounded AgentContext exceeds its model workspace bound")
        if not include_images:
            return (
                ModelMessage(role="system", content=system_prompt),
                ModelMessage(role="user", content=text),
            )
        parts: list[ModelTextPart | ModelImageURLPart] = [ModelTextPart(text=text)]
        for image in request.image_inputs:
            encoded = base64.b64encode(image.data).decode("ascii")
            parts.append(ModelImageURLPart(image_url=f"data:{image.mime_type};base64,{encoded}"))
        return (
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=tuple(parts)),
        )


def _task(context: AgentContext) -> dict[str, object]:
    task = context.task
    return {
        "instruction": task.instruction,
        "constraints": _section(task.constraints),
        "allowed_effects": _section(task.allowed_effects),
        "forbidden_effects": _section(task.forbidden_effects),
        "success_criteria": _section(
            task.success_criteria,
            lambda item: {
                "criterion_id": item.criterion_id,
                "definition": project_public_value(item.definition),
            },
        ),
        "requested_outputs": _section(task.requested_output_ids),
        "risk_profile": str(task.risk_profile),
        "public_inputs": project_public_value(task.public_inputs),
        "public_inputs_total_count": task.public_inputs_total_count,
        "public_inputs_truncated": task.public_inputs_truncated,
        "material_bindings": _section(
            task.material_bindings,
            lambda item: {
                "name": item.name,
                "media_type": item.media_type,
                "public_reference": item.public_reference,
            },
        ),
    }


def _progress(
    context: AgentContext,
    refs: Mapping[str, str],
    evidence_refs: Mapping[str, str],
) -> dict[str, object]:
    progress = context.progress
    return {
        "validated_task_status": progress.validated_task_status,
        "verified_public_facts": tuple(
            {
                "evidence_ref": evidence_refs[item.fact_ref],
                "subject": _subject(item.subject_id, refs),
                "field": item.predicate,
                "value": project_public_value(item.value),
            }
            for item in progress.verified_public_facts
        ),
        "unresolved_criteria": _section(progress.unresolved_criteria),
        "unresolved_outputs": _section(progress.unresolved_outputs),
        "events": _section(
            progress.events,
            lambda item: {
                "event_type": item.event_type,
                "semantic_action": item.semantic_action,
                "target": _subject(item.target_id, refs, unknown=""),
                "effect_status": item.effect_status,
                "task_status": item.task_status,
                "strategy_transition_required": item.strategy_transition_required,
            },
        ),
        "truncated": progress.truncated,
    }


def _turn(item: AgentTurnView, refs: Mapping[str, str]) -> dict[str, object]:
    result = {
        "decision": item.decision_kind,
        "semantic_action": item.semantic_action,
        "target": _subject(item.target_id, refs, unknown=""),
        "parameters": project_public_value(item.public_parameters),
        "dispatch": item.dispatch_status,
        "effect": item.action_evaluation_status,
        "task": item.task_evaluation_status,
        "reason": item.reason,
    }
    if item.semantic_summary:
        result["decision_details"] = _replace_target_refs(
            project_public_value(item.semantic_summary), refs
        )
    return result


def _control_feedback(context: AgentContext, refs: Mapping[str, str]) -> object:
    feedback = context.control_feedback
    if feedback is None:
        return None
    result: dict[str, object] = {
        "kind": feedback.kind,
        "code": feedback.code,
        "source": feedback.source,
        "next_decision_disposition": feedback.next_decision_disposition,
        "strategy_transition_required": feedback.strategy_transition_required,
        "public_subject": _subject(feedback.public_subject_id or "", refs, unknown=""),
        "public_field_paths": feedback.public_field_paths,
    }
    if feedback.related_decision is not None:
        result["related_decision"] = {
            "kind": feedback.related_decision.kind,
            "target": _subject(feedback.related_decision.target_id, refs, unknown=""),
            "parameters": project_public_value(feedback.related_decision.parameters),
        }
    if feedback.violation is not None:
        result["violation"] = {
            "contract_owner": feedback.violation.contract_owner,
            "code": feedback.violation.code,
            "field_paths": feedback.violation.field_paths,
            "expected": project_public_value(feedback.violation.expected),
            "actual": project_public_value(feedback.violation.actual),
        }
    if feedback.semantic_effect is not None:
        result["semantic_effect"] = to_json_compatible(feedback.semantic_effect)
    if feedback.recovery is not None:
        result["recovery"] = {
            "must_change_fields": feedback.recovery.must_change_fields,
            "repeat_previous_decision_allowed": feedback.recovery.repeat_previous_decision_allowed,
            "retry_allowed": feedback.recovery.retry_allowed,
            "rollback_available": feedback.recovery.rollback_available,
            "strategy_change_required": feedback.recovery.strategy_change_required,
        }
    return result


def _tool_menu(tools: tuple[ToolSpec, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in tools
    )


def _evidence_refs(context: AgentContext) -> dict[str, str]:
    fact_ids = dict.fromkeys(
        (
            *(item.fact_ref for item in context.world.facts.items),
            *(item.fact_ref for item in context.progress.verified_public_facts),
        )
    )
    return {fact_id: f"F{index}" for index, fact_id in enumerate(fact_ids, start=1)}


def _section(
    section: BoundedSection[Any],
    convert: Callable[[Any], object] = to_json_compatible,
) -> dict[str, object]:
    return {
        "items": tuple(convert(item) for item in section.items),
        "total_count": section.total_count,
        "truncated": section.truncated,
    }


def _subject(value: str, refs: Mapping[str, str], *, unknown: str = "task") -> str:
    return refs.get(value, unknown)


def _replace_target_refs(value: object, refs: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return refs.get(value, value)
    if isinstance(value, Mapping):
        return {str(key): _replace_target_refs(item, refs) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return tuple(_replace_target_refs(item, refs) for item in value)
    return value

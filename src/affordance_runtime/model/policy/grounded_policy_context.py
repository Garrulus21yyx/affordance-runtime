"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.agent.context.actor_world_snapshot import actor_world_for_delivery
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_tool_contracts import MAX_GROUNDED_WORKSPACE_BYTES
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model.policy.prompt import (
    MODEL_POLICY_INSTRUCTIONS,
    MODEL_POLICY_PROMPT_VERSION,
)
from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.model.providers.port import ModelImageURLPart, ModelMessage, ModelTextPart


@dataclass(frozen=True)
class GroundedAgentPrompts:
    version: str
    actor: str

    def __post_init__(self) -> None:
        if not self.version or not self.actor.strip():
            raise ValueError("grounded-agent prompt bundle is incomplete")


def load_grounded_agent_prompts() -> GroundedAgentPrompts:
    return GroundedAgentPrompts(MODEL_POLICY_PROMPT_VERSION, MODEL_POLICY_INSTRUCTIONS)


@dataclass(frozen=True)
class GroundedPolicyContextBinder:
    """Convert one canonical AgentContext to one provider message boundary."""

    prompts: GroundedAgentPrompts = field(default_factory=load_grounded_agent_prompts)

    def action_messages(
        self,
        request: ModelDecisionRequest,
        tools: tuple[ToolSpec, ...],
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> tuple[ModelMessage, ...]:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        public = self._public_context(request.agent_context, include_images)
        if include_tool_menu:
            public["tools"] = _tool_menu(tools)
        return self._messages(self.prompts.actor, public, request, include_images)

    @staticmethod
    def _public_context(
        context: AgentContext,
        include_images: bool,
    ) -> dict[str, object]:
        refs = dict(context.grounding.target_refs)
        public: dict[str, object] = {
            "task": _task(context),
            "observation": to_json_compatible(
                actor_world_for_delivery(context.actor_world, include_images=include_images)
            ),
            "progress": _progress(context),
            "recent_steps": _recent_steps(context.recent_steps.items, refs),
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
) -> dict[str, object]:
    progress = context.progress
    unresolved_criteria = tuple(progress.unresolved_criteria.items)
    unresolved_outputs = tuple(progress.unresolved_outputs.items)
    satisfied_criteria = tuple(
        item.criterion_id
        for item in context.task.success_criteria.items
        if item.criterion_id not in unresolved_criteria
    )
    confirmed_outputs = tuple(
        item
        for item in context.task.requested_output_ids.items
        if item not in unresolved_outputs
    )
    return {
        "status": progress.validated_task_status,
        "satisfied_criteria": satisfied_criteria,
        "unresolved_criteria": unresolved_criteria,
        "confirmed_outputs": confirmed_outputs,
        "unresolved_outputs": unresolved_outputs,
        "evidence": tuple(
            {
                "evidence_ref": item.fact_ref,
                "subject": item.subject_id,
                "field": item.predicate,
                "value": project_public_value(item.value),
            }
            for item in progress.verified_public_facts
        ),
        "truncated": progress.truncated,
    }


def _recent_steps(
    items: tuple[AgentTurnView, ...],
    refs: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    visible = items[-8:]
    return tuple(
        _turn(item, refs, detailed=index == len(visible) - 1)
        for index, item in enumerate(visible)
    )


def _turn(
    item: AgentTurnView,
    refs: Mapping[str, str],
    *,
    detailed: bool,
) -> dict[str, object]:
    action: dict[str, object] = {
        "kind": item.decision_kind,
        "tool": item.semantic_action,
        "target": _subject(item.target_id, refs, unknown=""),
    }
    result_details = None
    if detailed:
        action["arguments"] = project_public_value(item.public_parameters)
        if item.destination_id:
            action["destination"] = _subject(item.destination_id, refs, unknown="")
        if item.semantic_summary:
            details = _replace_target_refs(project_public_value(item.semantic_summary), refs)
            if isinstance(details, Mapping):
                details = dict(details)
                result_details = details.pop("result", None)
            if details:
                action["details"] = details
    result = {
        "dispatch": item.dispatch_status,
        "effect": item.action_evaluation_status,
        "task": item.task_evaluation_status,
        "reason": item.reason,
    }
    if result_details is not None:
        result["details"] = result_details
    return {"action": action, "result": result}


def _tool_menu(tools: tuple[ToolSpec, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in tools
    )


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

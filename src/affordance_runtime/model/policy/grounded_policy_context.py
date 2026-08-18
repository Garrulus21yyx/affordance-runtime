"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.compact_world_renderer import render_compact_actor_world
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
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
        public: dict[str, object] = {
            "task": _task(context),
            "observation": render_compact_actor_world(
                context.actor_world,
                context.grounding,
                include_images=include_images,
            ),
            "goal_plan": _goal_plan(context),
            "recent_steps": _recent_steps(context.recent_steps.items),
            "affordances": tuple(
                {"ref": item.ref, "verbs": item.verbs}
                for item in context.grounding.entities
                if item.verbs
            ),
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
    result: dict[str, object] = {
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
    evaluation = {
            "status": str(task.evaluation.status),
            "criteria": tuple(
                {
                    "criterion_id": item.criterion_id,
                    "status": str(item.status),
                }
                for item in task.evaluation.criteria
            ),
            "outputs": tuple(
                {
                    "output_id": item.output_id,
                    "value": project_public_value(item.value),
                }
                for item in task.evaluation.outputs
            ),
            "evidence": tuple(
                {
                    "evidence_ref": item.fact_ref,
                    "field": item.predicate,
                    "value": project_public_value(item.value),
                }
                for item in task.evaluation.verified_public_facts
            ),
    }
    if (
        evaluation["status"] not in {"", "unknown", "incomplete"}
        or evaluation["criteria"]
        or evaluation["outputs"]
        or evaluation["evidence"]
    ):
        result["formal_evaluation"] = evaluation
    return result


def _goal_plan(context: AgentContext) -> dict[str, object]:
    plan = context.goal_plan
    return {
        "resolution": plan.resolution,
        "plan_version": plan.plan_version,
        "plan_digest": plan.plan_digest,
        "items": tuple(
            {
                "id": item.id,
                "objective": _redact_expired_refs(item.objective),
                "done_when": _redact_expired_refs(item.done_when),
                "depends_on": item.depends_on,
                "final": item.final,
            }
            for item in plan.items
        ),
    }


def _recent_steps(
    items: tuple[AgentTurnView, ...],
) -> dict[str, object]:
    visible = items[-8:]
    recent = visible[-4:]
    earlier = visible[:-4]
    return {
        "earlier_actions": tuple(_earlier_action(item) for item in earlier),
        "recent_trajectory": tuple(_turn(item, detailed=True) for item in recent),
        "retained_count": len(visible),
    }


def _earlier_action(item: AgentTurnView) -> dict[str, object]:
    result: dict[str, object] = {
        "tool": _redact_expired_refs(item.semantic_action),
        "outcome": _redact_expired_refs(item.reason),
    }
    if item.target is not None:
        result["target"] = _historical_target(item.target)
    return result


def _turn(
    item: AgentTurnView,
    *,
    detailed: bool,
) -> dict[str, object]:
    action: dict[str, object] = {
        "kind": item.decision_kind,
        "tool": _redact_expired_refs(item.semantic_action),
    }
    if item.target is not None:
        action["target"] = _historical_target(item.target)
    result_details = None
    if detailed:
        action["arguments"] = _historical_value(project_public_value(item.public_parameters))
        if item.expected_outcome:
            action["expected_outcome"] = _redact_expired_refs(item.expected_outcome)
        if item.destination is not None:
            action["destination"] = _historical_target(item.destination)
        if item.semantic_summary:
            details = _historical_value(project_public_value(item.semantic_summary))
            if isinstance(details, Mapping):
                details = dict(details)
                result_details = details.pop("result", None)
            if details:
                action["details"] = details
    result: dict[str, object] = {
        "dispatch": _redact_expired_refs(item.dispatch_status),
        "local_postcondition": _redact_expired_refs(item.local_postcondition),
        "reason": _redact_expired_refs(item.reason),
    }
    if item.task_evaluation_status not in {"", "unknown", "incomplete"}:
        result["task"] = item.task_evaluation_status
    if item.transition:
        result["transition"] = _historical_value(item.transition)
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


def _historical_target(value: AgentHistoricalTargetView) -> dict[str, object]:
    result: dict[str, object] = {
        "role": _redact_expired_refs(value.role),
        "label": _redact_expired_refs(value.label),
    }
    if value.context:
        result["context"] = tuple(_redact_expired_refs(item) for item in value.context)
    return result


def _historical_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_expired_refs(value)
    if isinstance(value, Mapping):
        return {
            _redact_expired_refs(str(key)): _historical_value(item)
            for key, item in value.items()
            if str(key) not in {"subject_id", "target_id", "destination_id"}
            and not str(key).endswith("_ref")
        }
    if isinstance(value, tuple | list):
        return tuple(_historical_value(item) for item in value)
    return value


def _redact_expired_refs(value: str) -> str:
    return re.sub(r"\bE[1-9][0-9]{0,2}\b", "<expired-ref>", value)

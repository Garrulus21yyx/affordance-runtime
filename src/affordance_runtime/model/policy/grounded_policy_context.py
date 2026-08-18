"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.compact_world_renderer import render_compact_actor_world
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.episode_history import render_episode_history
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.working_facts import public_working_facts
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
            "recent_steps": render_episode_history(
                context.recent_steps.items,
                context.history_byte_budget,
            ),
            "affordances": tuple(
                {"ref": item.ref, "verbs": item.verbs}
                for item in context.grounding.entities
                if item.verbs
            ),
        }
        if context.working_facts:
            public["working_set"] = public_working_facts(context.working_facts)
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
                "objective": item.objective,
                "done_when": item.done_when,
                "depends_on": item.depends_on,
                "final": item.final,
            }
            for item in plan.items
        ),
    }


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

"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.model_turn_delivery import (
    ModelTurnDelivery,
    build_model_turn_delivery,
)
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.workspace import render_current_activities, render_recent_trajectory
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model.policy.prompt import (
    MODEL_POLICY_INSTRUCTIONS,
    MODEL_POLICY_PROMPT_VERSION,
)
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest


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
    """Project the public ActionPolicy context consumed by the envelope binder."""

    prompts: GroundedAgentPrompts = field(default_factory=load_grounded_agent_prompts)

    def prompt_version(self, context: AgentContext) -> str:
        del context
        return self.prompts.version

    @staticmethod
    def _public_context(
        context: AgentContext,
        include_images: bool,
        delivery: ModelTurnDelivery,
    ) -> dict[str, object]:
        public = GroundedPolicyContextBinder._public_context_sections(
            context,
            include_images,
            delivery,
        )["public"]
        if not isinstance(public, dict):
            raise TypeError("grounded policy public context must be a mapping")
        return dict(
            cast(
                dict[str, object],
                public,
            )
        )

    @staticmethod
    def _public_context_sections(
        context: AgentContext,
        include_images: bool,
        delivery: ModelTurnDelivery,
    ) -> dict[str, object]:
        if delivery.context_id != context.context_id:
            raise ValueError("model turn delivery belongs to another Context")
        if bool(delivery.media) != include_images:
            raise ValueError("model turn delivery image selection is inconsistent")
        task = _task(context)
        view = delivery.view
        observation = view.text
        public: dict[str, object] = {
            "task": task,
            "observation": observation,
            "goal_plan": _goal_plan(context),
        }
        current_turn: dict[str, object] = {"observation": observation}
        recent_trajectory = render_recent_trajectory(context.workspace)
        if recent_trajectory:
            public["recent_trajectory"] = recent_trajectory
            current_turn["recent_trajectory"] = recent_trajectory
        if context.current_observation is None:
            raise TypeError("grounded policy context requires the fresh current observation")
        current_activities = render_current_activities(
            context.workspace,
            current_world_digest=public_world_semantic_digest(context.current_observation),
        )
        if current_activities:
            public["current_activity"] = current_activities
            current_turn["current_activity"] = current_activities
        if context.control_feedback:
            control_feedback = project_public_value(context.control_feedback)
            public["control_feedback"] = control_feedback
            current_turn["control_feedback"] = control_feedback
        return {
            "public": public,
            "task_plan": {"task": task, "goal_plan": public["goal_plan"]},
            "actor_world": {"observation": observation},
            "current_turn": current_turn,
            "history": {"control_feedback": context.control_feedback},
            "delivery_view": view,
            "delivery_id": delivery.delivery_id,
        }

    @staticmethod
    def public_task_plan(context: AgentContext) -> dict[str, object]:
        """Return the one task/plan anchor reused across model turns."""

        return {"task": _task(context), "goal_plan": _goal_plan(context)}

    def model_turn_delivery(
        self,
        request: ModelDecisionRequest,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
    ) -> ModelTurnDelivery:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        return build_model_turn_delivery(
            request.agent_context,
            include_images=include_images,
        )

    @staticmethod
    def _include_images(
        request: ModelDecisionRequest,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
    ) -> bool:
        include_images = perception_uses_images(request, perception_profile)
        if include_images and (not supports_multimodal or not request.agent_context.image_inputs):
            raise ValueError("selected grounded perception requires a current image input")
        return include_images


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
                "definition": to_json_compatible(item.definition),
            },
        ),
        "requested_outputs": _section(task.requested_output_ids),
        "risk_profile": str(task.risk_profile),
        # Task intake already owns bounded typed admission. Preserve that
        # admitted public value exactly; World/history privacy filters do not
        # own TaskGoal semantics and must not delete route-shaped key names.
        "public_inputs": to_json_compatible(task.public_inputs),
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


def _section(
    section: BoundedSection[Any],
    convert: Callable[[Any], object] = to_json_compatible,
) -> dict[str, object]:
    return {
        "items": tuple(convert(item) for item in section.items),
        "total_count": section.total_count,
        "truncated": section.truncated,
    }

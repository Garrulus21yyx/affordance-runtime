"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.episode_history import render_episode_history
from affordance_runtime.agent.context.model_turn_delivery import (
    ModelTurnDelivery,
    build_model_turn_delivery,
)
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
from affordance_runtime.model.policy.request_admission import (
    AdmittedModelRequest,
    ModelRequestBudget,
    ModelRequestCapacityError,
    admit_model_request,
    estimate_model_request,
)
from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.model.providers.port import ModelImageURLPart, ModelMessage, ModelTextPart

_MODEL_HISTORY_MAX_BYTES = 6 * 1024


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
    request_budget: ModelRequestBudget = field(default_factory=ModelRequestBudget)

    def prompt_version(self, context: AgentContext) -> str:
        del context
        return self.prompts.version

    def action_messages(
        self,
        request: ModelDecisionRequest,
        tools: tuple[ToolSpec, ...],
        delivery: ModelTurnDelivery,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> tuple[ModelMessage, ...]:
        return self.action_request(
            request,
            tools,
            delivery,
            supports_multimodal=supports_multimodal,
            perception_profile=perception_profile,
            include_tool_menu=include_tool_menu,
        ).messages

    def action_request(
        self,
        request: ModelDecisionRequest,
        tools: tuple[ToolSpec, ...],
        delivery: ModelTurnDelivery,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> AdmittedModelRequest:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        if delivery.context_id != request.context_id:
            raise ValueError("model turn delivery belongs to another Context")
        if delivery.includes_images != include_images:
            raise ValueError("model turn delivery image selection is inconsistent")
        selected = self._candidate(
            request,
            tools,
            delivery,
            include_images=include_images,
            include_tool_menu=include_tool_menu,
        )
        selected_projection = delivery.view.projection
        try:
            admitted = admit_model_request(
                messages=selected.messages,
                tools=selected.tools,
                budget=self.request_budget,
                phase="initial",
                component_payloads=selected.component_payloads,
                image_inputs=request.image_inputs if include_images else (),
            )
        except ModelRequestCapacityError as exc:
            raise ModelRequestCapacityError(
                replace(
                    exc.breakdown,
                    prefit_estimated_total_tokens=selected.breakdown.estimated_total_tokens,
                    delivery_projection=selected_projection,
                    full_candidate_tokens=0,
                    lens_candidate_tokens=selected.breakdown.estimated_total_tokens,
                    expanded_region_count=selected.expanded_region_count,
                    folded_region_count=selected.folded_region_count,
                    direct_action_count=selected.direct_action_count,
                    searchable_action_count=selected.searchable_action_count,
                )
            ) from exc
        return AdmittedModelRequest(
            admitted.messages,
            admitted.tools,
            replace(
                admitted.breakdown,
                prefit_estimated_total_tokens=selected.breakdown.estimated_total_tokens,
                delivery_projection=selected_projection,
                full_candidate_tokens=0,
                lens_candidate_tokens=selected.breakdown.estimated_total_tokens,
                expanded_region_count=selected.expanded_region_count,
                folded_region_count=selected.folded_region_count,
                direct_action_count=selected.direct_action_count,
                searchable_action_count=selected.searchable_action_count,
            ),
        )

    def _candidate(
        self,
        request: ModelDecisionRequest,
        tools: tuple[ToolSpec, ...],
        delivery: ModelTurnDelivery,
        *,
        include_images: bool,
        include_tool_menu: bool,
        max_actor_bytes: int | None = None,
    ) -> "_PolicyRequestCandidate":
        sections = self._public_context_sections(
            request.agent_context,
            include_images,
            delivery,
            max_actor_bytes=max_actor_bytes,
        )
        view = sections["delivery_view"]
        if view is not delivery.view:
            raise ValueError("policy observation must use the supplied ModelTurnDelivery")
        direct_tools = tools
        public = dict(sections["public"])
        if include_tool_menu:
            public["tools"] = _tool_menu(direct_tools)
        messages = self._messages(
            self.prompts.actor,
            public,
            request,
            include_images,
        )
        component_payloads = {
            "task_plan": sections["task_plan"],
            "actor_world": sections["actor_world"],
            "history": sections["history"],
            "working_set": sections["working_set"],
        }
        breakdown = estimate_model_request(
            messages=messages,
            tools=direct_tools,
            budget=self.request_budget,
            phase="initial",
            component_payloads=component_payloads,
            image_inputs=request.image_inputs if include_images else (),
        )
        expanded = int(view.coverage.get("expanded_regions", 0))
        folded = int(view.coverage.get("folded_regions", 0))
        direct_refs = frozenset(view.manifest.executable_refs)
        searchable = sum(
            1
            for option in request.agent_context.complete_actions
            if option.target_ref not in direct_refs
        )
        return _PolicyRequestCandidate(
            messages,
            direct_tools,
            component_payloads,
            breakdown,
            expanded,
            folded,
            len(request.agent_context.complete_actions) - searchable,
            searchable,
        )

    @staticmethod
    def _public_context(
        context: AgentContext,
        include_images: bool,
        delivery: ModelTurnDelivery,
    ) -> dict[str, object]:
        return dict(
            GroundedPolicyContextBinder._public_context_sections(
                context,
                include_images,
                delivery,
            )["public"]
        )

    @staticmethod
    def _public_context_sections(
        context: AgentContext,
        include_images: bool,
        delivery: ModelTurnDelivery,
        *,
        max_actor_bytes: int | None = None,
    ) -> dict[str, object]:
        del max_actor_bytes
        if delivery.context_id != context.context_id:
            raise ValueError("model turn delivery belongs to another Context")
        if delivery.includes_images != include_images:
            raise ValueError("model turn delivery image selection is inconsistent")
        task = _task(context)
        view = delivery.view
        observation = view.text
        recent_steps = render_episode_history(
            context.recent_steps.items,
            min(context.history_byte_budget, _MODEL_HISTORY_MAX_BYTES),
        )
        working_set = public_working_facts(context.working_facts) if context.working_facts else ()
        public: dict[str, object] = {
            "task": task,
            "observation": observation,
            "goal_plan": _goal_plan(context),
            "recent_steps": recent_steps,
        }
        if context.control_feedback:
            public["control_feedback"] = project_public_value(context.control_feedback)
        if working_set:
            public["working_set"] = working_set
        return {
            "public": public,
            "task_plan": {"task": task, "goal_plan": public["goal_plan"]},
            "actor_world": {"observation": observation},
            "history": {"recent_steps": recent_steps, "control_feedback": context.control_feedback},
            "working_set": working_set,
            "delivery_view": view,
            "delivery_id": delivery.delivery_id,
        }

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
    if task.final_response_contract:
        result["final_response_contract"] = to_json_compatible(task.final_response_contract)
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


@dataclass(frozen=True)
class _PolicyRequestCandidate:
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolSpec, ...]
    component_payloads: Mapping[str, object]
    breakdown: object
    expanded_region_count: int
    folded_region_count: int
    direct_action_count: int
    searchable_action_count: int


def _section(
    section: BoundedSection[Any],
    convert: Callable[[Any], object] = to_json_compatible,
) -> dict[str, object]:
    return {
        "items": tuple(convert(item) for item in section.items),
        "total_count": section.total_count,
        "truncated": section.truncated,
    }

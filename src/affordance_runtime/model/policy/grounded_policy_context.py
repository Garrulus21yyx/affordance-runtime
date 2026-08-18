"""Single model-message binder for the canonical AgentContext."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
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
from affordance_runtime.model.policy.request_admission import (
    AdmittedModelRequest,
    ModelRequestBudget,
    ModelRequestCapacityError,
    admit_model_request,
    estimate_model_request,
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
    request_budget: ModelRequestBudget = field(default_factory=ModelRequestBudget)

    def action_messages(
        self,
        request: ModelDecisionRequest,
        tools: tuple[ToolSpec, ...],
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> tuple[ModelMessage, ...]:
        return self.action_request(
            request,
            tools,
            supports_multimodal=supports_multimodal,
            perception_profile=perception_profile,
            include_tool_menu=include_tool_menu,
        ).messages

    def action_request(
        self,
        request: ModelDecisionRequest,
        tools: tuple[ToolSpec, ...],
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> AdmittedModelRequest:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        sections = self._public_context_sections(request.agent_context, include_images)
        public = dict(sections["public"])
        if include_tool_menu:
            public["tools"] = _tool_menu(tools)
        messages = self._messages(self.prompts.actor, public, request, include_images)
        breakdown = estimate_model_request(
            messages=messages,
            tools=tools,
            budget=self.request_budget,
            phase="initial",
            component_payloads={
                "task_plan": sections["task_plan"],
                "actor_world": sections["actor_world"],
                "history": sections["history"],
                "working_set": sections["working_set"],
            },
            image_inputs=request.image_inputs if include_images else (),
        )
        prefit_estimated_total_tokens = breakdown.estimated_total_tokens
        delivery_projection = "full"
        if breakdown.estimated_total_tokens > self.request_budget.soft_target_tokens:
            delivery_projection = "action_focused"
            sections = self._public_context_sections(
                request.agent_context,
                include_images,
                focus_refs=_tool_refs(tools),
                max_actor_bytes=max(
                    3 * max(1, self.request_budget.soft_target_tokens - _non_actor_tokens(breakdown)),
                    4_096,
                ),
            )
            public = dict(sections["public"])
            if include_tool_menu:
                public["tools"] = _tool_menu(tools)
            messages = self._messages(self.prompts.actor, public, request, include_images)
        try:
            admitted = admit_model_request(
                messages=messages,
                tools=tools,
                budget=self.request_budget,
                phase="initial",
                component_payloads={
                    "task_plan": sections["task_plan"],
                    "actor_world": sections["actor_world"],
                    "history": sections["history"],
                    "working_set": sections["working_set"],
                },
                image_inputs=request.image_inputs if include_images else (),
            )
        except ModelRequestCapacityError as exc:
            raise ModelRequestCapacityError(
                replace(
                    exc.breakdown,
                    prefit_estimated_total_tokens=prefit_estimated_total_tokens,
                    delivery_projection=delivery_projection,
                )
            ) from exc
        return AdmittedModelRequest(
            admitted.messages,
            admitted.tools,
            replace(
                admitted.breakdown,
                prefit_estimated_total_tokens=prefit_estimated_total_tokens,
                delivery_projection=delivery_projection,
            ),
        )

    @staticmethod
    def _public_context(
        context: AgentContext,
        include_images: bool,
    ) -> dict[str, object]:
        return dict(GroundedPolicyContextBinder._public_context_sections(context, include_images)["public"])

    @staticmethod
    def _public_context_sections(
        context: AgentContext,
        include_images: bool,
        *,
        focus_refs: frozenset[str] | None = None,
        max_actor_bytes: int | None = None,
    ) -> dict[str, object]:
        task = _task(context)
        observation = render_compact_actor_world(
            context.actor_world,
            context.grounding,
            include_images=include_images,
            focus_refs=focus_refs,
            max_rendered_bytes=max_actor_bytes,
        )
        recent_steps = render_episode_history(
            context.recent_steps.items,
            context.history_byte_budget,
        )
        affordances = tuple(
            {"ref": item.ref, "verbs": item.verbs}
            for item in context.grounding.entities
            if item.verbs
        )
        working_set = public_working_facts(context.working_facts) if context.working_facts else ()
        public: dict[str, object] = {
            "task": task,
            "observation": observation,
            "goal_plan": _goal_plan(context),
            "recent_steps": recent_steps,
            "affordances": affordances,
        }
        if working_set:
            public["working_set"] = working_set
        return {
            "public": public,
            "task_plan": {"task": task, "goal_plan": public["goal_plan"]},
            "actor_world": {"observation": observation, "affordances": affordances},
            "history": recent_steps,
            "working_set": working_set,
        }

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


def _tool_refs(tools: tuple[ToolSpec, ...]) -> frozenset[str]:
    refs: set[str] = set()
    for spec in tools:
        properties = spec.input_schema.get("properties") if isinstance(spec.input_schema, Mapping) else None
        if not isinstance(properties, Mapping):
            continue
        for name in ("target", "source", "destination"):
            field = properties.get(name)
            enum = field.get("enum") if isinstance(field, Mapping) else None
            if isinstance(enum, tuple | list):
                refs.update(str(item) for item in enum if isinstance(item, str) and item.startswith("E"))
    return frozenset(refs)


def _non_actor_tokens(breakdown) -> int:
    return (
        breakdown.system_tokens
        + breakdown.task_plan_tokens
        + breakdown.history_tokens
        + breakdown.working_set_tokens
        + breakdown.tool_schema_tokens
        + breakdown.image_estimated_tokens
        + breakdown.repair_tokens
        + breakdown.provider_envelope_tokens
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

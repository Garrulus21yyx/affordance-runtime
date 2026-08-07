"""Direct provider-payload serialization for immutable PlanningRequest.

SAR-4 foundation only: this module establishes the replacement boundary for
PlanningRequest -> provider messages without creating a second PlannerContext
domain object. It is pure projection and does not call planners, mutate state,
write trace, or decide progress.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from affordance_runtime.choice_contracts import ChoicePlanningRequest
from affordance_runtime.immutable import FrozenDict, freeze_json, thaw_json_at_external_boundary, to_json_compatible
from affordance_runtime.model_port import ModelMessage
from affordance_runtime.planning_request import (
    PlanningRequest,
    thaw_request_mapping,
    thaw_request_value,
)

if TYPE_CHECKING:
    from affordance_runtime.task_planner import TaskPlanningRequest

DEFAULT_PLANNING_PROVIDER_PROMPT_VERSION = "sar-4-foundation-v1"
DEFAULT_PLANNING_PROVIDER_SYSTEM_PROMPT = (
    "Produce one semantic planner response from the supplied immutable runtime request. "
    "Do not invent selectors, coordinates, backend handles, approvals, or capabilities."
)


@dataclass(frozen=True)
class PlanningProviderPayload:
    """Immutable provider invocation payload produced directly from PlanningRequest."""

    prompt_version: str
    messages: tuple[ModelMessage, ...]
    context: FrozenDict

    def __post_init__(self) -> None:
        if not self.prompt_version.strip():
            raise ValueError("prompt version cannot be blank")
        if not isinstance(self.messages, tuple):
            raise ValueError("messages must be immutable")
        if not self.messages:
            raise ValueError("provider payload requires messages")
        object.__setattr__(self, "context", freeze_json(dict(self.context)))


@dataclass(frozen=True)
class PlanningRequestProviderSerializer:
    """Serialize immutable PlanningRequest into deterministic model messages."""

    system_prompt: str = DEFAULT_PLANNING_PROVIDER_SYSTEM_PROMPT
    prompt_version: str = DEFAULT_PLANNING_PROVIDER_PROMPT_VERSION

    def __post_init__(self) -> None:
        if not self.system_prompt.strip():
            raise ValueError("system prompt cannot be blank")
        if not self.prompt_version.strip():
            raise ValueError("prompt version cannot be blank")

    def serialize(self, request: PlanningRequest) -> PlanningProviderPayload:
        context = _request_context(request)
        content = json.dumps(
            to_json_compatible(context),
            sort_keys=True,
            separators=(",", ":"),
        )
        return PlanningProviderPayload(
            prompt_version=self.prompt_version,
            messages=(
                ModelMessage(role="system", content=self.system_prompt),
                ModelMessage(role="user", content=content),
            ),
            context=freeze_json(context),
        )


def _request_context(request: PlanningRequest) -> dict[str, Any]:
    active_step = request.step.active_step
    return {
        "identity": {
            "task_spec_identity": request.identity.task_spec_identity,
            "task_revision": request.identity.task_revision,
            "evaluated_at_state_version": request.identity.evaluated_at_state_version,
            "snapshot_id": request.identity.snapshot_id,
            "page_revision": request.identity.page_revision,
            "environment_revision": request.identity.environment_revision,
        },
        "task": {
            "objective": request.task.objective,
            "constraints": list(request.task.constraints),
            "capabilities": list(request.task.capabilities),
            "completion_projection_status": request.task.task_completion_projection_status,
            "summary": thaw_request_mapping(request.task.task_summary),
        },
        "step": {
            "activity_status": request.step.activity_status.value,
            "projection_status": request.step.projection_status.value,
            "projection_reason": request.step.projection_reason,
            "active_step_id": active_step.step_id if active_step is not None else "",
            "active_step_objective": active_step.objective if active_step is not None else "",
            "active_step_action_family": request.step.active_step_action_family,
        },
        "observation": {
            "snapshot_id": request.observation.snapshot_id,
            "page_revision": request.observation.page_revision,
            "environment_revision": request.observation.environment_revision,
            "observed_text": request.observation.observed_text,
            "artifact_refs": list(request.observation.artifact_refs),
            "affordances": [
                {
                    "target_id": item.target_id,
                    "surface": item.surface,
                    "role": item.role,
                    "label": item.label,
                    "supported_actions": list(item.supported_actions),
                    "state": {key: thaw_request_value(value) for key, value in item.state},
                    "confidence": item.confidence,
                    "conflict_codes": list(item.conflict_codes),
                    "source_refs": list(item.source_refs),
                }
                for item in request.observation.affordances
            ],
        },
        "runtime": {
            "permitted_action_kinds": list(request.permitted_action_kinds),
            "verified_effects": list(request.verified_effects),
            "pending_evidence_obligations": list(request.pending_evidence_obligations),
            "remaining_budget": {
                "steps": request.remaining_budget.steps,
                "observations": request.remaining_budget.observations,
                "recoveries": request.remaining_budget.recoveries,
                "effectful_actions": request.remaining_budget.effectful_actions,
                "model_calls": request.remaining_budget.model_calls,
            },
            "latest_outcome": thaw_request_mapping(request.latest_outcome),
            "recent_proposals": [thaw_request_mapping(item) for item in request.recent_proposals],
            "satisfied_action_targets": {key: list(value) for key, value in request.satisfied_action_targets},
        },
    }


def serialize_task_planning_request(request: TaskPlanningRequest) -> dict[str, object]:
    """Pure bounded projection of the long-horizon typed request."""

    task = request.task_spec
    return {
        "task_spec": {
            "schema_version": task.schema_version,
            "revision": task.revision,
            "objective": task.objective,
            "operation_class": task.operation_class.value,
            "requirements": [item.model_dump(mode="json") for item in task.requirements],
            "inputs": [item.model_dump(mode="json") for item in task.inputs],
            "allowed_effect_refs": list(task.allowed_effect_refs),
            "hard_constraint_refs": list(task.hard_constraint_refs),
            "preference_refs": list(task.preference_refs),
            "forbidden_effect_refs": list(task.forbidden_effect_refs),
            "capability_ceiling": list(task.capability_ceiling),
            "success": task.success.model_dump(mode="json"),
            "required_outputs": [item.model_dump(mode="json") for item in task.required_outputs],
            "risk_policy": (task.risk_policy.model_dump(mode="json") if task.risk_policy else None),
            "source_envelope_ref": task.source_envelope_ref,
            "source_binding_digest": task.source_binding_digest,
        },
        "planning": request.model_dump(mode="json", exclude={"task_spec"}),
    }


def serialize_choice_planning_request(
    request: ChoicePlanningRequest,
) -> dict[str, object]:
    """Pure projection of one displayed ChoicePage; it cannot recover hidden choices."""

    return {
        "task_revision": request.task_revision,
        "plan_revision": request.plan_revision,
        "catalog_id": request.catalog_ref.catalog_id,
        "catalog_digest": request.catalog_ref.catalog_digest,
        "active_step_id": request.active_step_id,
        "budget": {
            "model_calls_remaining": request.budget.model_calls_remaining,
            "pages_remaining": request.budget.pages_remaining,
        },
        "recent_outcomes": [
            {
                "action_kind": item.action_kind,
                "target_id": item.target_id,
                "verification_passed": item.verification_passed,
                "effect_satisfied": item.effect_satisfied,
            }
            for item in request.recent_outcomes
        ],
        "choices": [
            {
                "choice_id": choice.choice_id,
                "action_kind": choice.action_kind.value,
                "target_id": choice.target_id,
                "target_label": choice.target_label,
                "target_role": choice.target_role,
                "destination_id": choice.destination_id,
                "destination_label": choice.destination_label,
                "relevant_current_state": thaw_json_at_external_boundary(choice.relevant_current_state),
                "requirement_refs": list(choice.requirement_refs),
                "effect_refs": list(choice.effect_refs),
                "conflict_status": choice.conflict_status.value,
                "risk": choice.risk,
                "generation_reason_codes": list(choice.generation_reason_codes),
            }
            for choice in request.page.choices
        ],
    }

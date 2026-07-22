"""Provider-neutral structured candidate generation and bounded repair."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Generic, Literal, TypeVar, cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, create_model, field_validator

from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort, StructuredModelError
from affordance_runtime.planner_context import PlannerContext
from affordance_runtime.planning import PlannerActionKind, PlannerProposal


class PlannerCandidateModel(BaseModel):
    """Model-authored proposal fields without runtime binding authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subgoal: str = ""
    action_kind: PlannerActionKind
    target_affordance_id: str = ""
    destination_affordance_id: str = ""
    parameters: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)
    expected_effects: tuple[str, ...] = Field(
        default=(), validation_alias=AliasChoices("expected_effects", "expected_effect")
    )
    evidence_requirements: tuple[str, ...] = Field(
        default=(), validation_alias=AliasChoices("evidence_requirements", "evidence_need")
    )
    uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_clarification: bool = False
    done: bool = False
    result: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    @field_validator("expected_effects", "evidence_requirements", mode="before")
    @classmethod
    def normalize_single_semantic_text(cls, value: Any) -> Any:
        """Accept one semantic text item without admitting arbitrary payloads."""

        return (value,) if isinstance(value, str) else value


class EmptyPlannerParameters(BaseModel):
    """Schema-only empty object for parameterless constrained actions."""

    model_config = ConfigDict(extra="forbid")


CandidateT = TypeVar("CandidateT", bound=PlannerCandidateModel)

CandidateIssueFn = Callable[[CandidateT, PlannerContext], str]
CandidateBindFn = Callable[[CandidateT, PlannerContext], PlannerProposal]
ProposalIssueFn = Callable[[PlannerProposal, PlannerContext], str]
RepairConstraintsFn = Callable[
    [PlannerContext, CandidateT, str, list[str], dict[str, list[str]]],
    tuple[list[str], dict[str, list[str]]],
]
CandidateValueFn = Callable[[CandidateT, PlannerContext], str]


@dataclass(frozen=True)
class PlannerCandidateRepairPolicy(Generic[CandidateT]):
    """Generalist-owned semantic decisions used by the repair orchestrator."""

    prebind_issue: CandidateIssueFn[CandidateT]
    bind_candidate: CandidateBindFn[CandidateT]
    context_issue: ProposalIssueFn
    repair_constraints: RepairConstraintsFn[CandidateT]
    required_slider_direction: CandidateValueFn[CandidateT]
    autocomplete_prefix: Callable[[PlannerContext], str]


@dataclass(frozen=True)
class PlannerModelOrchestrator:
    """Run one initial structured generation plus bounded semantic repairs."""

    async def propose(
        self,
        *,
        model: ModelPort,
        config: ModelConfig,
        messages: list[ModelMessage],
        context: PlannerContext,
        candidate_type: type[CandidateT],
        initial_schema: type[CandidateT],
        repair_permitted: list[str],
        repair_targets: dict[str, list[str]],
        max_candidate_repairs: int,
        reserve_model_call: Callable[[], None],
        policy: PlannerCandidateRepairPolicy[CandidateT],
    ) -> PlannerProposal:
        candidate = await self._generate_candidate(
            model=model,
            config=config,
            messages=messages,
            candidate_type=candidate_type,
            output_schema=initial_schema,
            reserve_model_call=reserve_model_call,
        )
        repair_messages = list(messages)
        proposal: PlannerProposal | None = None
        repair_issue = ""
        for repair_attempt in range(max_candidate_repairs + 1):
            repair_issue = policy.prebind_issue(candidate, context)
            if not repair_issue:
                try:
                    proposal = policy.bind_candidate(candidate, context)
                except ValidationError as exc:
                    repair_issue = _candidate_validation_types(exc) or "validation_error"
                else:
                    repair_issue = policy.context_issue(proposal, context)
            if not repair_issue:
                break
            if repair_attempt >= max_candidate_repairs:
                raise StructuredModelError(
                    f"planner candidate failed semantic validation: "
                    f"{repair_issue}:{candidate.action_kind.value}"
                )
            repair_permitted, repair_targets = policy.repair_constraints(
                context,
                candidate,
                repair_issue,
                repair_permitted,
                repair_targets,
            )
            allowed_press_keys: tuple[str, ...] = ()
            allowed_text_values: tuple[str, ...] = ()
            require_drag_destination = False
            if repair_issue == "proposal_drag_destination_missing":
                repair_permitted = [PlannerActionKind.DRAG.value]
                repair_targets = {
                    PlannerActionKind.DRAG.value: compatible_target_ids(context).get(
                        PlannerActionKind.DRAG.value,
                        [],
                    )
                }
                require_drag_destination = True
            if repair_issue == "proposal_slider_wrong_direction":
                required_key = policy.required_slider_direction(candidate, context)
                if required_key and candidate.target_affordance_id:
                    repair_permitted = [PlannerActionKind.PRESS_KEY.value]
                    repair_targets = {
                        PlannerActionKind.PRESS_KEY.value: [candidate.target_affordance_id]
                    }
                    allowed_press_keys = (required_key,)
            if repair_issue == "proposal_autocomplete_requires_prefix":
                required_prefix = policy.autocomplete_prefix(context)
                if required_prefix and candidate.target_affordance_id:
                    repair_permitted = [PlannerActionKind.TYPE_TEXT.value]
                    repair_targets = {
                        PlannerActionKind.TYPE_TEXT.value: [candidate.target_affordance_id]
                    }
                    allowed_text_values = (required_prefix,)
            repair_context = {
                "validation_error_types": repair_issue.split(","),
                "permitted_action_kinds": repair_permitted,
                "compatible_target_ids": repair_targets,
                "allowed_press_keys": list(allowed_press_keys),
                "allowed_text_values": list(allowed_text_values),
                "rejected_action_kind": candidate.action_kind.value,
                "instruction": "Return a replacement semantic candidate that repairs only this issue. action_kind MUST be in permitted_action_kinds and its target MUST be in the corresponding compatible_target_ids. When validation_error_types contains proposal_action_not_permitted, rejected_action_kind is forbidden. A progress-blocked or already-satisfied action signature is forbidden; choose the next still-required task action. Keep the supplied task, affordances, and constraints unchanged.",
            }
            repair_messages.extend(
                (
                    ModelMessage(role="assistant", content=candidate.model_dump_json()),
                    ModelMessage(role="user", content=json.dumps(repair_context, sort_keys=True)),
                )
            )
            candidate = await self._generate_candidate(
                model=model,
                config=config,
                messages=repair_messages,
                candidate_type=candidate_type,
                output_schema=build_repair_candidate_schema(
                    candidate_type,
                    repair_permitted,
                    repair_targets,
                    allowed_press_keys=allowed_press_keys,
                    allowed_text_values=allowed_text_values,
                    require_drag_destination=require_drag_destination,
                    drag_destination_ids=tuple(compatible_drag_destination_ids(context)),
                ),
                reserve_model_call=reserve_model_call,
            )
        if proposal is None:
            raise StructuredModelError("planner candidate failed semantic validation")
        return proposal

    async def _generate_candidate(
        self,
        *,
        model: ModelPort,
        config: ModelConfig,
        messages: list[ModelMessage],
        candidate_type: type[CandidateT],
        output_schema: type[CandidateT],
        reserve_model_call: Callable[[], None],
    ) -> CandidateT:
        reserve_model_call()
        generated = await model.generate_structured(messages, output_schema, config)
        if output_schema is candidate_type:
            return generated
        return candidate_type.model_validate(generated.model_dump())


def compatible_target_ids(context: PlannerContext) -> dict[str, list[str]]:
    """Project semantic actions onto current compatible target ids."""

    action_map = {
        "activate": {"activate", "click", "download", "invoke", "write_property"},
        "point_activate": {"point_activate"},
        "type_text": {"fill", "type", "type_text"},
        "select_option": {"select", "select_option"},
        "press_key": {"press", "press_key"},
        "drag": {"drag"},
    }
    return {
        action_kind: [
            item.id
            for item in context.affordances
            if item.action in actions
            and not (action_kind == "drag" and bool(item.state.get("accepts_drop")))
            and not (
                action_kind == "activate"
                and item.role == "option"
                and item.state.get("programmatic_option") is not True
            )
        ]
        for action_kind, actions in action_map.items()
        if action_kind in context.permitted_action_kinds
    }


def compatible_drag_destination_ids(context: PlannerContext) -> list[str]:
    """Return endpoint targets that can receive a drag without making them sources."""

    return [
        item.id
        for item in context.affordances
        if item.action in {"drag", "drop"} or bool(item.state.get("accepts_drop"))
    ]


def build_repair_candidate_schema(
    candidate_type: type[CandidateT],
    permitted_action_kinds: list[str],
    compatible_targets: dict[str, list[str]],
    *,
    allowed_press_keys: tuple[str, ...] = (),
    allowed_text_values: tuple[str, ...] = (),
    require_drag_destination: bool = False,
    drag_destination_ids: tuple[str, ...] = (),
) -> type[CandidateT]:
    """Constrain repair decoding to current semantic actions and targets."""

    if not permitted_action_kinds:
        permitted_action_kinds = [PlannerActionKind.ASK_USER.value]
        compatible_targets = {}
    allowed_actions = tuple(PlannerActionKind(item) for item in permitted_action_kinds)
    targetless_actions = {"ask_user", "finish", "navigate", "scroll", "wait"}
    allow_empty_target = bool(targetless_actions.intersection(permitted_action_kinds))
    allowed_targets = tuple(
        dict.fromkeys(
            [
                *([""] if allow_empty_target else []),
                *(
                    target_id
                    for action_kind in permitted_action_kinds
                    for target_id in compatible_targets.get(action_kind, [])
                ),
            ]
        )
    )
    if not allowed_targets:
        permitted_action_kinds = [PlannerActionKind.ASK_USER.value]
        allowed_actions = (PlannerActionKind.ASK_USER,)
        allow_empty_target = True
        allowed_targets = ("",)
    action_type = Literal.__getitem__(allowed_actions)
    target_type = Literal.__getitem__(allowed_targets)
    fields: dict[str, Any] = {
        "action_kind": (action_type, ...),
        "target_affordance_id": (target_type, "" if allow_empty_target else ...),
    }
    if permitted_action_kinds == [PlannerActionKind.DRAG.value]:
        destination_targets = drag_destination_ids or tuple(compatible_targets["drag"])
        fields["destination_affordance_id"] = (Literal.__getitem__(destination_targets), ...)
    if require_drag_destination:
        destination_targets = drag_destination_ids or tuple(compatible_targets.get("drag", []))
        if not destination_targets:
            raise ValueError("drag repair requires at least one compatible destination")
        fields["destination_affordance_id"] = (Literal.__getitem__(destination_targets), ...)
    if set(permitted_action_kinds) <= {"activate", "point_activate", "ask_user", "finish"}:
        fields["parameters"] = (EmptyPlannerParameters, Field(default_factory=EmptyPlannerParameters))
    elif allowed_press_keys and permitted_action_kinds == [PlannerActionKind.PRESS_KEY.value]:
        parameters_type = create_model(
            "SliderDirectionPlannerParameters",
            __config__=ConfigDict(extra="forbid"),
            key=(Literal.__getitem__(allowed_press_keys), ...),
        )
        fields["parameters"] = (parameters_type, ...)
    elif allowed_text_values and permitted_action_kinds == [PlannerActionKind.TYPE_TEXT.value]:
        parameters_type = create_model(
            "AutocompletePrefixPlannerParameters",
            __config__=ConfigDict(extra="forbid"),
            text=(Literal.__getitem__(allowed_text_values), ...),
        )
        fields["parameters"] = (parameters_type, ...)
    return cast(
        type[CandidateT],
        create_model(
            "PlannerProposalRepairCandidate",
            __base__=candidate_type,
            **fields,
        ),
    )


def build_initial_candidate_schema(
    candidate_type: type[CandidateT],
    permitted_action_kinds: list[str],
) -> type[CandidateT]:
    """Constrain initial decoding without requiring repair-only target fields."""

    if not permitted_action_kinds:
        permitted_action_kinds = [PlannerActionKind.ASK_USER.value]
    allowed_actions = tuple(PlannerActionKind(item) for item in permitted_action_kinds)
    return cast(
        type[CandidateT],
        create_model(
            "PlannerProposalConstrainedCandidate",
            __base__=candidate_type,
            action_kind=(Literal.__getitem__(allowed_actions), ...),
        ),
    )


def _candidate_validation_types(error: ValidationError) -> str:
    """Return only validation categories, never candidate values."""

    return ",".join(str(item.get("type") or "validation_error") for item in error.errors()[:4])

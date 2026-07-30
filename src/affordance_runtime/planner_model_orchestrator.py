"""Provider-neutral structured candidate generation and bounded repair."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Generic, Literal, Mapping, TypeVar, cast

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


@dataclass(frozen=True)
class SemanticTextInputConstraint:
    relation: str
    target_id: str
    allowed_text_values: tuple[str, ...]
    satisfied: bool = False


CandidateT = TypeVar("CandidateT", bound=Any)

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
class PlannerModelRequest(Generic[CandidateT]):
    """Immutable model-invocation boundary for one semantic planner turn."""

    model: ModelPort
    config: ModelConfig
    messages: tuple[ModelMessage, ...]
    context: PlannerContext
    candidate_type: type[CandidateT]
    initial_schema: type[CandidateT]
    repair_permitted: tuple[str, ...]
    repair_targets: Mapping[str, tuple[str, ...]]
    max_candidate_repairs: int
    reserve_model_call: Callable[[], None]
    policy: PlannerCandidateRepairPolicy[CandidateT]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "repair_targets",
            MappingProxyType({key: tuple(value) for key, value in self.repair_targets.items()}),
        )


@dataclass(frozen=True)
class PlannerModelOrchestrator:
    """Run one initial structured generation plus bounded semantic repairs."""

    async def propose(
        self,
        request: PlannerModelRequest[CandidateT],
    ) -> PlannerProposal:
        model = request.model
        config = request.config
        messages = list(request.messages)
        context = request.context
        candidate_type = request.candidate_type
        initial_schema = request.initial_schema
        repair_permitted = list(request.repair_permitted)
        repair_targets = {key: list(value) for key, value in request.repair_targets.items()}
        max_candidate_repairs = request.max_candidate_repairs
        reserve_model_call = request.reserve_model_call
        policy = request.policy
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
            validation_types = set(repair_issue.split(","))
            if validation_types.intersection(
                {
                    "proposal_action_parameter_required",
                    "proposal_forbidden_parameters",
                    "proposal_unsupported_parameters",
                }
            ):
                action_kind = candidate.action_kind.value
                if action_kind in repair_permitted:
                    repair_permitted = [action_kind]
                    repair_targets = (
                        {action_kind: list(repair_targets[action_kind])}
                        if action_kind in repair_targets
                        else {}
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
    targets = {
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
    rejection = context.recovery_summary.get("proposal_rejection")
    if not isinstance(rejection, dict):
        return targets
    if rejection.get("reason_code") != "relational_evidence_not_proven":
        return targets
    rejected_target_id = rejection.get("semantic_target_id")
    if not isinstance(rejected_target_id, str) or not rejected_target_id:
        return targets
    return {
        action_kind: [
            target_id for target_id in target_ids if target_id != rejected_target_id
        ]
        for action_kind, target_ids in targets.items()
    }


def restrict_targets_to_active_subgoal(
    context: PlannerContext,
    compatible_targets: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Keep every target action within a real active subgoal's semantic phase."""

    objective = str(context.task_spec.get("objective") or "").strip().casefold()
    active_subgoal = context.active_subgoal.strip().casefold()
    if not active_subgoal or active_subgoal == objective:
        return {key: list(value) for key, value in compatible_targets.items()}
    affordance_by_id = {item.id: item for item in context.affordances}
    active_tokens = _semantic_target_tokens(active_subgoal)
    declared_action_family = context.active_subgoal_action_family.strip()
    active_action_kinds = (
        frozenset({declared_action_family})
        if declared_action_family
        else _active_subgoal_action_kinds(active_subgoal)
    )
    return {
        action_kind: [
            target_id
            for target_id in target_ids
            if (
                (not active_action_kinds or action_kind in active_action_kinds)
                and (target := affordance_by_id.get(target_id)) is not None
                and _target_tokens_match_active_subgoal(
                    _semantic_target_tokens(target.label),
                    active_tokens,
                )
            )
        ]
        for action_kind, target_ids in compatible_targets.items()
    }


def _active_subgoal_action_kinds(active_subgoal: str) -> frozenset[str]:
    """Return only action families stated unambiguously by the active step."""

    tokens = set(_semantic_target_tokens(active_subgoal))
    if tokens.intersection({"type", "fill", "input", "write"}) or (
        "enter" in tokens and "press" not in tokens
    ):
        return frozenset({PlannerActionKind.TYPE_TEXT.value})
    if tokens.intersection({"drag", "drop"}):
        return frozenset({PlannerActionKind.DRAG.value})
    if tokens.intersection({"select", "choose"}):
        return frozenset(
            {PlannerActionKind.SELECT_OPTION.value, PlannerActionKind.ACTIVATE.value}
        )
    if tokens.intersection({"click", "press", "open", "activate"}):
        return frozenset(
            {
                PlannerActionKind.ACTIVATE.value,
                PlannerActionKind.POINT_ACTIVATE.value,
                PlannerActionKind.PRESS_KEY.value,
            }
        )
    return frozenset()


def _semantic_target_tokens(value: str) -> tuple[str, ...]:
    aliases = {
        "box": "input",
        "field": "input",
        "textbox": "input",
        "text": "input",
        "value": "input",
    }
    return tuple(
        aliases.get(token, token)
        for token in re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)
        if len(token) >= 3
    )


def _target_tokens_match_active_subgoal(
    target_tokens: tuple[str, ...],
    active_tokens: tuple[str, ...],
) -> bool:
    return bool(target_tokens) and all(
        any(
            target == active
            or (len(target) >= 4 and active.startswith(target))
            or (len(active) >= 4 and target.startswith(active))
            for active in active_tokens
        )
        for target in target_tokens
    )


def compatible_drag_destination_ids(context: PlannerContext) -> list[str]:
    """Return endpoint targets that can receive a drag without making them sources."""

    return [
        item.id
        for item in context.affordances
        if item.action in {"drag", "drop"} or bool(item.state.get("accepts_drop"))
    ]


def semantic_text_input_constraint(
    context: PlannerContext,
    compatible_targets: dict[str, list[str]],
) -> SemanticTextInputConstraint | None:
    """Bind one still-open explicit value obligation to one enabled text target."""

    target_ids = compatible_targets.get(PlannerActionKind.TYPE_TEXT.value, [])
    if len(target_ids) != 1:
        return None
    target_id = target_ids[0]
    target = next((item for item in context.affordances if item.id == target_id), None)
    if target is None or target.state.get("enabled") is False:
        return None
    raw_constraints = context.task_spec.get("semantic_value_constraints")
    if not isinstance(raw_constraints, list):
        return None
    for relation in ("prefix", "exact"):
        values = tuple(
            dict.fromkeys(
                str(item.get("value"))
                for item in raw_constraints
                if isinstance(item, dict)
                and item.get("relation") == relation
                and isinstance(item.get("value"), str)
                and str(item.get("value")).strip()
            )
        )
        if len(values) == 1:
            current_value = target.state.get("control_value")
            satisfied = isinstance(current_value, str) and _semantic_value_is_present(
                current_value,
                relation=relation,
                required_value=values[0],
            )
            return SemanticTextInputConstraint(
                relation,
                target_id,
                values,
                satisfied=satisfied,
            )
        if values:
            return None
    return None


def _semantic_value_is_present(
    current_value: str,
    *,
    relation: str,
    required_value: str,
) -> bool:
    """Use only current observed control state to retire an input obligation."""

    if relation == "prefix":
        return current_value.startswith(required_value)
    if relation == "exact":
        return current_value == required_value
    return False


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
    else:
        parameter_fields = _single_action_parameter_fields(permitted_action_kinds)
        if parameter_fields is not None:
            fields["parameters"] = parameter_fields
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


def _single_action_parameter_fields(
    permitted_action_kinds: list[str],
) -> tuple[type[BaseModel], Any] | None:
    """Return a strict parameter object when decoding one semantic action."""

    if len(permitted_action_kinds) != 1:
        return None
    action_kind = PlannerActionKind(permitted_action_kinds[0])
    if action_kind in {
        PlannerActionKind.ACTIVATE,
        PlannerActionKind.POINT_ACTIVATE,
        PlannerActionKind.DRAG,
        PlannerActionKind.ASK_USER,
        PlannerActionKind.FINISH,
    }:
        return EmptyPlannerParameters, Field(default_factory=EmptyPlannerParameters)
    parameter_field: tuple[str, Any]
    if action_kind == PlannerActionKind.TYPE_TEXT:
        parameter_field = ("text", (str, ...))
    elif action_kind == PlannerActionKind.SELECT_OPTION:
        parameter_field = ("option", (str | list[str], ...))
    elif action_kind == PlannerActionKind.PRESS_KEY:
        parameter_field = ("key", (str, ...))
    else:
        return None
    parameter_definitions: dict[str, Any] = {
        parameter_field[0]: parameter_field[1],
    }
    parameter_type = create_model(
        f"{action_kind.value.title().replace('_', '')}PlannerParameters",
        __config__=ConfigDict(extra="forbid"),
        **parameter_definitions,
    )
    return parameter_type, ...


def _candidate_validation_types(error: ValidationError) -> str:
    """Return only validation categories, never candidate values."""

    return ",".join(str(item.get("type") or "validation_error") for item in error.errors()[:4])

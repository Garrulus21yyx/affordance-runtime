"""Logical full Runtime action catalog and realization strategies."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, TypeAlias

from affordance_runtime.action_choice_authority import authorize_choice
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.choice_contracts import (
    ActionChoice,
    ActionChoiceFailure,
    CatalogRef,
    CatalogSlice,
    ChoiceBuildReport,
    ChoiceConflictStatus,
    ChoiceRejection,
    ChoiceRole,
    ChoiceSource,
)
from affordance_runtime.criteria import (
    LiteralValue,
    PredicateExpr,
    PredicateOperator,
    criterion_nodes,
)
from affordance_runtime.criteria import (
    criterion_ids as canonical_criterion_ids,
)
from affordance_runtime.grounding import GroundingCandidate
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.interaction_grounding import (
    GroundingResult,
    GroundingRole,
    GroundingStatus,
    GroundingTarget,
    InteractionGrounder,
)
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.recovery_protocol import FailureKind, FailureOwner
from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    ElementOperationKind,
    RegionIntent,
    RelationIntent,
    StepSpec,
)
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import (
    CanonicalTarget,
    UnifiedObservation,
    UnifiedObservationTarget,
)

CanonicalChoiceTarget: TypeAlias = CanonicalTarget | UnifiedObservationTarget


@dataclass(frozen=True)
class _GeneratedChoiceSet:
    grounding: GroundingResult
    choices: tuple[ActionChoice, ...]


ActionChoiceBuildResult: TypeAlias = _GeneratedChoiceSet | ActionChoiceFailure


class CatalogMembership(Protocol):
    def count(self) -> int: ...
    def contains(self, choice_id: str) -> bool: ...
    def get(self, choice_id: str) -> ActionChoice | None: ...
    def page(self, cursor: str | None, size: int) -> CatalogSlice: ...


class _Membership:
    def __init__(self, choices: tuple[ActionChoice, ...]) -> None:
        self._choices = choices
        self._index = {choice.choice_id: choice for choice in choices}

    def count(self) -> int:
        return len(self._choices)

    def contains(self, choice_id: str) -> bool:
        return choice_id in self._index

    def get(self, choice_id: str) -> ActionChoice | None:
        return self._index.get(choice_id)

    def page(self, cursor: str | None, size: int) -> CatalogSlice:
        if size < 1:
            raise ValueError("catalog page size must be positive")
        offset = int(cursor or 0)
        values = self._choices[offset : offset + size]
        following = offset + len(values)
        return CatalogSlice(values, str(following) if following < len(self._choices) else None)


class _LazyMembership(_Membership):
    def __init__(self, factory: Callable[[], tuple[ActionChoice, ...]]) -> None:
        self._factory = factory
        self._loaded: _Membership | None = None

    def _value(self) -> _Membership:
        if self._loaded is None:
            self._loaded = _Membership(self._factory())
        return self._loaded

    def count(self) -> int:
        return self._value().count()

    def contains(self, choice_id: str) -> bool:
        return self._value().contains(choice_id)

    def get(self, choice_id: str) -> ActionChoice | None:
        return self._value().get(choice_id)

    def page(self, cursor: str | None, size: int) -> CatalogSlice:
        return self._value().page(cursor, size)


@dataclass(frozen=True)
class ActionChoiceCatalog:
    catalog_id: str
    catalog_digest: str
    task_revision: int
    plan_revision: int
    state_version: int
    observation_ref: str
    active_step_id: str
    membership: CatalogMembership
    build_report: ChoiceBuildReport

    @classmethod
    def from_choices(
        cls,
        *,
        task_revision: int,
        plan_revision: int,
        state_version: int,
        observation_ref: str,
        active_step_id: str,
        choices: tuple[ActionChoice, ...],
        build_report: ChoiceBuildReport | None = None,
        realization: str = "eager",
    ) -> "ActionChoiceCatalog":
        ordered = tuple(sorted(choices, key=lambda item: item.choice_id))
        if len({item.choice_id for item in ordered}) != len(ordered):
            raise ValueError("catalog choice IDs must be unique")
        payload = {
            "task_revision": task_revision,
            "plan_revision": plan_revision,
            "state_version": state_version,
            "observation_ref": observation_ref,
            "active_step_id": active_step_id,
            "choices": [
                {
                    "choice_id": item.choice_id,
                    "action_kind": item.action_kind.value,
                    "target_id": item.target_id,
                    "target_label": item.target_label,
                    "destination_id": item.destination_id,
                    "destination_label": item.destination_label,
                    "parameters": to_json_compatible(item.parameters),
                    "criteria": item.criterion_ids,
                    "requirements": item.requirement_refs,
                    "effects": item.effect_refs,
                    "effectful": item.effectful,
                    "risk": item.risk,
                    "role": item.role.value,
                    "authorization_scope_digest": item.authorization_scope_digest,
                }
                for item in ordered
            ],
            "rejections": [
                (item.target_id, item.action_kind.value if item.action_kind else None, item.reason_code)
                for item in (build_report.rejections if build_report else ())
            ],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if realization == "lazy":
            membership: CatalogMembership = _LazyMembership(lambda: ordered)
        elif realization in {"eager", "indexed"}:
            membership = _Membership(ordered)
        else:
            raise ValueError("unsupported catalog realization")
        report = build_report or ChoiceBuildReport(0, len(ordered))
        return cls(
            f"catalog:{digest}",
            digest,
            task_revision,
            plan_revision,
            state_version,
            observation_ref,
            active_step_id,
            membership,
            report,
        )

    @property
    def ref(self) -> CatalogRef:
        return CatalogRef(self.catalog_id, self.catalog_digest, self.observation_ref)

    @property
    def count(self) -> int:
        return self.membership.count()

    def contains(self, choice_id: str) -> bool:
        return self.membership.contains(choice_id)

    def get(self, choice_id: str) -> ActionChoice | None:
        return self.membership.get(choice_id)

    def page(self, cursor: str | None, size: int) -> CatalogSlice:
        return self.membership.page(cursor, size)


class ActionChoiceCatalogBuilder:
    """Build one logical Catalog from canonical Runtime inputs.

    The active-step semantic generator is deliberately invoked before any
    presentation projection. Its output is immediately sealed as Catalog
    membership; page/provider policy is not accepted by this API.
    """

    def build(
        self,
        *,
        task_revision: int,
        task_spec: TaskSpec,
        plan_revision: int,
        state_version: int,
        step: object,
        scope: object,
        observation: object,
        capabilities: frozenset[str] = frozenset(),
        realization: str = "eager",
    ) -> ActionChoiceCatalog | ActionChoiceFailure:
        result = _SemanticChoiceGenerator().build(
            task_revision=task_revision,
            state_version=state_version,
            step=step,
            scope=scope,
            observation=observation,
            capabilities=capabilities,
        )
        if isinstance(result, ActionChoiceFailure):
            fallback = _deterministic_semantic_choices(
                task_revision=task_revision,
                state_version=state_version,
                step=step,
                observation=observation,
                task_spec=task_spec,
            )
            if not fallback:
                return ActionChoiceFailure(result.kind, result.reason_code, result.owner)
            report = ChoiceBuildReport(len(observation.targets), len(fallback))
            return ActionChoiceCatalog.from_choices(
                task_revision=task_revision,
                plan_revision=plan_revision,
                state_version=state_version,
                observation_ref=observation.epoch_id,
                active_step_id=step.step_id,
                choices=fallback,
                build_report=report,
                realization=realization,
            )
        by_target = {item.target_id: item for item in observation.targets}
        choices: list[ActionChoice] = []
        rejections: list[ChoiceRejection] = []
        for choice in result.choices:
            target = by_target.get(choice.target_id)
            conflict = getattr(getattr(target, "conflict_status", None), "value", "")
            if conflict in {"material_conflict", "inconclusive"}:
                rejections.append(
                    ChoiceRejection(
                        choice.target_id,
                        choice.action_kind,
                        "MATERIAL_SOURCE_CONFLICT",
                        tuple(getattr(target, "source_assertion_refs", ())),
                    )
                )
                continue
            candidate_choice = ActionChoice(
                choice_id=choice.choice_id,
                task_revision=choice.task_revision,
                state_version=choice.state_version,
                snapshot_id=choice.snapshot_id,
                active_step_id=choice.active_step_id,
                action_kind=choice.action_kind,
                target_id=choice.target_id,
                target_label=getattr(target, "label", "") or choice.target_id,
                target_role=getattr(target, "role", "") or "semantic_target",
                relevant_current_state=_semantic_presentation_state(getattr(target, "state", {})),
                destination_id=choice.destination_id,
                parameters=choice.parameters,
                criterion_ids=choice.criterion_ids,
                requirement_refs=step.requirement_refs,
                effect_refs=(),
                effectful=False,
                evidence_refs=tuple(getattr(target, "source_assertion_refs", ())),
                conflict_status=ChoiceConflictStatus.CLEAR,
            )
            authority = authorize_choice(candidate_choice, step, task_spec, observation)
            if not authority.authorized:
                rejections.append(
                    ChoiceRejection(
                        choice.target_id,
                        choice.action_kind,
                        authority.reason_code,
                    )
                )
                continue
            choices.append(
                ActionChoice(
                    **{
                        **candidate_choice.__dict__,
                        "destination_label": authority.destination_identity,
                        "effect_refs": authority.effect_refs,
                        "effectful": authority.effectful,
                        "risk": authority.risk.value,
                        "authorization_scope_digest": authority.scope_digest,
                    }
                )
            )
        report = ChoiceBuildReport(len(observation.targets), len(choices), tuple(rejections))
        if not choices:
            return ActionChoiceFailure(
                FailureKind.NO_FEASIBLE_ACTION,
                "no_feasible_action_choice",
            )
        return ActionChoiceCatalog.from_choices(
            task_revision=task_revision,
            plan_revision=plan_revision,
            state_version=state_version,
            observation_ref=observation.epoch_id,
            active_step_id=step.step_id,
            choices=tuple(choices),
            build_report=report,
            realization=realization,
        )


def _deterministic_semantic_choices(
    *, task_revision: int, state_version: int, step: StepSpec, observation: UnifiedObservation, task_spec: TaskSpec
) -> tuple[ActionChoice, ...]:
    """Narrow a legacy abstract active-step target without model assistance."""

    criteria = tuple(getattr(step, "completion_criteria", ()))
    criterion_ids = tuple(value for item in criteria if (value := getattr(item, "criterion_id", "")))
    values: list[ActionChoice] = []
    for target in observation.targets:
        conflict = getattr(getattr(target, "conflict_status", None), "value", "")
        if conflict in {"material_conflict", "inconclusive"}:
            continue
        supported = set(target.supported_actions)
        action = next(
            (
                kind
                for kind, aliases in (
                    (PlannerActionKind.ACTIVATE, {"activate", "click", "invoke", "write_property"}),
                    (PlannerActionKind.TYPE_TEXT, {"fill", "type", "type_text"}),
                    (PlannerActionKind.SELECT_OPTION, {"select", "select_option"}),
                    (PlannerActionKind.PRESS_KEY, {"press", "press_key"}),
                    (PlannerActionKind.POINT_ACTIVATE, {"point_activate"}),
                )
                if supported.intersection(aliases)
            ),
            None,
        )
        if action is None:
            continue
        payload = (
            task_revision,
            state_version,
            observation.epoch_id,
            step.step_id,
            action.value,
            target.target_id,
            criterion_ids,
        )
        digest = hashlib.sha256(repr(payload).encode()).hexdigest()
        values.append(
            ActionChoice(
                choice_id=f"choice:{digest}",
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=observation.epoch_id,
                active_step_id=step.step_id,
                action_kind=action,
                target_id=target.target_id,
                target_label=getattr(target, "label", "") or target.target_id,
                target_role=getattr(target, "role", "") or "semantic_target",
                relevant_current_state=_semantic_presentation_state(getattr(target, "state", {})),
                criterion_ids=criterion_ids,
                requirement_refs=step.requirement_refs,
                effect_refs=(),
                effectful=False,
                evidence_refs=tuple(getattr(target, "source_assertion_refs", ())),
                generation_reason_codes=("deterministic_active_step_narrowing",),
            )
        )
    admitted: list[ActionChoice] = []
    for choice in values:
        authority = authorize_choice(choice, step, task_spec, observation)
        if not authority.authorized:
            continue
        admitted.append(
            ActionChoice(
                **{
                    **choice.__dict__,
                    "destination_label": authority.destination_identity,
                    "effect_refs": authority.effect_refs,
                    "effectful": authority.effectful,
                    "risk": authority.risk.value,
                    "authorization_scope_digest": authority.scope_digest,
                }
            )
        )
    return tuple(admitted)


_PRESENTABLE_STATE_KEYS = frozenset(
    {
        "enabled",
        "visible",
        "checked",
        "selected",
        "expanded",
        "value",
        "current_value",
        "input_type",
        "min",
        "max",
        "step",
    }
)


def _semantic_presentation_state(state: object) -> dict[str, object]:
    if not isinstance(state, Mapping):
        return {}
    return {key: value for key, value in state.items() if key in _PRESENTABLE_STATE_KEYS}


class _SemanticChoiceGenerator:
    def build(
        self,
        *,
        task_revision: int,
        state_version: int,
        step: StepSpec,
        scope: ActiveStepScope,
        observation: UnifiedObservation,
        capabilities: frozenset[str] = frozenset(),
    ) -> ActionChoiceBuildResult:
        stale_reason = _validate_scope_identity(
            task_revision=task_revision,
            state_version=state_version,
            step=step,
            scope=scope,
            observation=observation,
        )
        if stale_reason:
            return ActionChoiceFailure(
                kind=FailureKind.AUTHORITY_BLOCKED,
                reason_code=stale_reason,
                owner=FailureOwner.TERMINAL,
            )
        if scope.active_step_id is None:
            return ActionChoiceFailure(
                kind=FailureKind.NO_FEASIBLE_ACTION,
                reason_code="no_active_step",
            )

        targets = {item.target_id: item for item in observation.targets}
        grounding = InteractionGrounder().ground(
            step.interaction,
            tuple(_grounding_target(item, observation.bindings) for item in observation.targets),
            capabilities=capabilities,
        )
        if grounding.status != GroundingStatus.RESOLVED:
            return ActionChoiceFailure(
                kind=(
                    FailureKind.CAPABILITY_MISSING
                    if grounding.status == GroundingStatus.CAPABILITY_MISSING
                    else FailureKind.GROUNDING_AMBIGUOUS
                ),
                reason_code=grounding.reason_code or "interaction_grounding_failed",
                owner=FailureOwner.STEP_PLANNER,
            )
        choices: list[ActionChoice] = []
        criterion_ids = canonical_criterion_ids(step.completion_criteria)
        criteria = tuple(item for expression in step.completion_criteria for item in _action_criteria(expression))
        if grounding.role == GroundingRole.ENABLING:
            target = targets.get(grounding.targets[0].target_id)
            enabler = step.interaction.enabler if isinstance(step.interaction, ElementIntent) else None
            if target is not None and enabler is not None:
                choice = _element_operation_choice(
                    task_revision=task_revision,
                    state_version=state_version,
                    snapshot_id=observation.snapshot_id,
                    step_id=step.step_id,
                    intent=enabler,
                    target=target,
                    role=ChoiceRole.ENABLING,
                )
                if choice is not None:
                    choices.append(choice)
        elif isinstance(step.interaction, CollectionIntent):
            target = targets.get(grounding.targets[0].target_id)
            if target is not None and _supports(target, PlannerActionKind.SELECT_OPTION):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.SELECT_OPTION,
                        target_id=target.target_id,
                        parameters=dict(grounding.parameters),
                        criterion_ids=criterion_ids,
                    )
                )
        elif isinstance(step.interaction, RelationIntent):
            source = targets.get(grounding.targets[0].target_id)
            destination = targets.get(grounding.destinations[0].target_id)
            if (
                step.interaction.relation == "value_transfer"
                and source is not None
                and destination is not None
                and source.target_id != destination.target_id
                and _supports(destination, PlannerActionKind.TYPE_TEXT)
                and (transfer_value := _exact_transfer_value(source)) is not None
            ):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.TYPE_TEXT,
                        target_id=destination.target_id,
                        parameters={"text": transfer_value},
                        criterion_ids=criterion_ids,
                    )
                )
            elif (
                step.interaction.relation != "value_transfer"
                and source is not None
                and destination is not None
                and _supports(source, PlannerActionKind.DRAG)
            ):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.DRAG,
                        target_id=source.target_id,
                        destination_id=destination.target_id,
                        parameters={},
                        criterion_ids=criterion_ids,
                    )
                )
        elif isinstance(step.interaction, RegionIntent):
            target = targets.get(grounding.targets[0].target_id)
            if target is not None and _supports(target, PlannerActionKind.POINT_ACTIVATE):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.POINT_ACTIVATE,
                        target_id=target.target_id,
                        parameters={},
                        criterion_ids=criterion_ids,
                    )
                )
        elif isinstance(step.interaction, ElementIntent) and step.interaction.operation != ElementOperationKind.AUTO:
            target = targets.get(grounding.targets[0].target_id)
            if target is not None:
                choice = _element_operation_choice(
                    task_revision=task_revision,
                    state_version=state_version,
                    snapshot_id=observation.snapshot_id,
                    step_id=step.step_id,
                    intent=step.interaction,
                    target=target,
                    role=ChoiceRole.DIRECT,
                    criterion_ids=criterion_ids,
                )
                if choice is not None:
                    choices.append(choice)
        else:
            grounded_targets = tuple(targets[item.target_id] for item in grounding.targets if item.target_id in targets)
            for criterion in criteria:
                for target in grounded_targets:
                    choice = _choice_for_criterion(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        criterion=criterion,
                        target=target,
                    )
                    if choice is not None:
                        choices.append(choice)

        choices = _coalesce_semantic_choices(choices)
        if not choices:
            return ActionChoiceFailure(
                kind=FailureKind.NO_FEASIBLE_ACTION,
                reason_code="no_feasible_action_choice",
            )
        return _GeneratedChoiceSet(grounding=grounding, choices=tuple(choices))


def _coalesce_semantic_choices(choices: list[ActionChoice]) -> list[ActionChoice]:
    grouped: dict[tuple[object, ...], list[ActionChoice]] = {}
    for choice in choices:
        key = (
            choice.task_revision,
            choice.state_version,
            choice.snapshot_id,
            choice.active_step_id,
            choice.action_kind,
            choice.target_id,
            choice.destination_id,
            choice.role,
            json.dumps(
                to_json_compatible(choice.parameters),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        grouped.setdefault(key, []).append(choice)
    return [
        _make_choice(
            task_revision=members[0].task_revision,
            state_version=members[0].state_version,
            snapshot_id=members[0].snapshot_id,
            step_id=members[0].active_step_id,
            action_kind=members[0].action_kind,
            target_id=members[0].target_id,
            destination_id=members[0].destination_id,
            parameters=dict(members[0].parameters),
            criterion_ids=tuple(
                dict.fromkeys(criterion_id for member in members for criterion_id in member.criterion_ids)
            ),
            role=members[0].role,
        )
        for members in grouped.values()
    ]


@dataclass(frozen=True)
class _ActionCriterion:
    criterion_id: str
    subject: str
    relation: CriterionRelation
    expected_value: object | None


def _action_criteria(expression: object) -> tuple[_ActionCriterion, ...]:
    relations = {
        PredicateOperator.EQUALS: CriterionRelation.EQUALS,
        PredicateOperator.CONTAINS: CriterionRelation.CONTAINS,
        PredicateOperator.SELECTED: CriterionRelation.IS_SELECTED,
        PredicateOperator.CHECKED: CriterionRelation.IS_CHECKED,
        PredicateOperator.CHANGED: CriterionRelation.HAS_CHANGED,
    }
    return tuple(
        _ActionCriterion(
            item.criterion_id,
            item.subject.reference,
            relations.get(item.operator, CriterionRelation.IS_COMPLETED),
            item.value.value if isinstance(item.value, LiteralValue) else None,
        )
        for item in criterion_nodes(expression)  # type: ignore[arg-type]
        if isinstance(item, PredicateExpr)
    )


def _choice_for_criterion(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: _ActionCriterion,
    target: CanonicalChoiceTarget,
) -> ActionChoice | None:
    if target.state.get("enabled") is False or target.state.get("visible") is False:
        return None
    if criterion.relation != CriterionRelation.EQUALS:
        if criterion.relation == CriterionRelation.IS_CHECKED:
            return _checked_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.IS_EXPANDED:
            return _expanded_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.IS_SELECTED:
            return _selected_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.IS_COMPLETED:
            return _activation_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.HAS_CHANGED:
            return _changed_activation_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        return None
    if isinstance(criterion.expected_value, str) and _supports(
        target,
        PlannerActionKind.TYPE_TEXT,
    ):
        return _make_choice(
            task_revision=task_revision,
            state_version=state_version,
            snapshot_id=snapshot_id,
            step_id=step_id,
            action_kind=PlannerActionKind.TYPE_TEXT,
            target_id=target.target_id,
            parameters={"text": criterion.expected_value},
            criterion_ids=(criterion.criterion_id,),
        )
    numeric_expected_value = _numeric_expected_value(criterion.expected_value)
    if numeric_expected_value is not None and _supports(target, PlannerActionKind.PRESS_KEY):
        current_value = _numeric_state_value(target)
        if current_value is None and numeric_expected_value == 0:
            return None
        if current_value == numeric_expected_value:
            return None
        key = (
            "ArrowRight"
            if current_value is None and numeric_expected_value > 0
            else (
                "ArrowLeft"
                if current_value is None
                else ("ArrowRight" if numeric_expected_value > current_value else "ArrowLeft")
            )
        )
        return _make_choice(
            task_revision=task_revision,
            state_version=state_version,
            snapshot_id=snapshot_id,
            step_id=step_id,
            action_kind=PlannerActionKind.PRESS_KEY,
            target_id=target.target_id,
            parameters={"key": key},
            criterion_ids=(criterion.criterion_id,),
        )
    return None


def _grounding_target(
    target: CanonicalChoiceTarget,
    bindings: tuple[GroundingCandidate, ...] = (),
) -> GroundingTarget:
    if isinstance(target, CanonicalTarget):
        surface = target.surfaces[0].value if len(target.surfaces) == 1 else "multi_surface"
        target_bindings = tuple(item for item in bindings if item.semantic_target_id == target.target_id)
        # A semantic target with several valid bindings has no representative
        # surface or winning confidence. Routing belongs to contract building.
        confidence = None
        source_refs = tuple(
            dict.fromkeys(
                (
                    *target.source_assertion_refs,
                    *(ref for item in target_bindings for ref in item.evidence_refs),
                )
            )
        )
    else:
        surface = target.surface
        confidence = target.confidence
        source_refs = target.source_refs
    return GroundingTarget(
        target_id=target.target_id,
        role=target.role,
        label=target.label,
        supported_actions=target.supported_actions,
        state=target.state,
        surface=surface,
        confidence=confidence,
        source_refs=source_refs,
    )


def _exact_transfer_value(target: CanonicalChoiceTarget) -> str | None:
    if target.state.get("input_type") == "password":
        return None
    if "control_value_prefix" in target.state or "control_value_suffix" in target.state:
        return None
    value = target.state.get("control_value")
    if not isinstance(value, str) or not value or len(value) > 240:
        return None
    return value


def _element_operation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    intent: ElementIntent,
    target: UnifiedObservationTarget,
    role: ChoiceRole,
    criterion_ids: tuple[str, ...] = (),
) -> ActionChoice | None:
    if intent.operation == ElementOperationKind.AUTO:
        action_kind = PlannerActionKind.ACTIVATE
        parameters: dict[str, object] = {}
    elif intent.operation == ElementOperationKind.FOCUS:
        action_kind = PlannerActionKind.FOCUS
        parameters = {}
    else:
        action_kind = PlannerActionKind.PRESS_KEY
        parameters = {"key": ("PageDown" if intent.operation == ElementOperationKind.SCROLL_FORWARD else "PageUp")}
    if not _supports(target, action_kind):
        return None
    return _make_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        action_kind=action_kind,
        target_id=target.target_id,
        parameters=parameters,
        criterion_ids=criterion_ids,
        role=role,
    )


def _expanded_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: _ActionCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if target.state.get("expanded") is not False:
        return None
    return _activation_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        criterion=criterion,
        target=target,
    )


def _checked_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: _ActionCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if not _supports(target, PlannerActionKind.ACTIVATE):
        return None
    if target.state.get("checked") is True:
        return None
    return _activation_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        criterion=criterion,
        target=target,
    )


def _selected_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: _ActionCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if not isinstance(criterion.expected_value, str):
        return None
    if not _supports(target, PlannerActionKind.SELECT_OPTION):
        return None
    selected_value = _selected_value(target)
    if selected_value is not None and criterion.expected_value.strip().casefold() == selected_value.strip().casefold():
        return None
    return _make_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        action_kind=PlannerActionKind.SELECT_OPTION,
        target_id=target.target_id,
        parameters={"option": criterion.expected_value},
        criterion_ids=(criterion.criterion_id,),
    )


def _selected_value(target: UnifiedObservationTarget) -> str | None:
    for key in ("selected_value", "value", "current_value", "control_value"):
        value = target.state.get(key)
        if isinstance(value, str) and value.strip():
            return value
    selected = target.state.get("selected")
    if isinstance(selected, str) and selected.strip():
        return selected
    return None


def _activation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: _ActionCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if not _supports(target, PlannerActionKind.ACTIVATE):
        return None
    return _make_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        action_kind=PlannerActionKind.ACTIVATE,
        target_id=target.target_id,
        parameters={},
        criterion_ids=(criterion.criterion_id,),
    )


def _changed_activation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: _ActionCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if _target_looks_text_entry(target) or _target_looks_slider(target):
        return None
    return _activation_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        criterion=criterion,
        target=target,
    )


def _make_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    action_kind: PlannerActionKind,
    target_id: str,
    parameters: dict[str, object],
    criterion_ids: tuple[str, ...],
    destination_id: str = "",
    role: ChoiceRole = ChoiceRole.DIRECT,
) -> ActionChoice:
    payload = {
        "task_revision": task_revision,
        "state_version": state_version,
        "snapshot_id": snapshot_id,
        "active_step_id": step_id,
        "action_kind": action_kind.value,
        "target_id": target_id,
        "destination_id": destination_id,
        "parameters": to_json_compatible(freeze_json(parameters)),
        "criterion_ids": criterion_ids,
        "role": role.value,
        "source": ChoiceSource.RUNTIME.value,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ActionChoice(
        choice_id=f"choice:{digest}",
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        active_step_id=step_id,
        action_kind=action_kind,
        target_id=target_id,
        destination_id=destination_id,
        parameters=parameters,
        criterion_ids=criterion_ids,
        role=role,
    )


def _validate_scope_identity(
    *,
    task_revision: int,
    state_version: int,
    step: StepSpec,
    scope: ActiveStepScope,
    observation: UnifiedObservation,
) -> str:
    if task_revision != scope.task_revision:
        return "stale_scope_task_revision"
    if state_version != scope.evaluated_at_state_version:
        return "stale_scope_state_version"
    if observation.snapshot_id != scope.snapshot_id:
        return "stale_scope_snapshot"
    if scope.active_step_id != step.step_id:
        return "scope_active_step_mismatch"
    return ""


def _supports(target: UnifiedObservationTarget, kind: PlannerActionKind) -> bool:
    compatible = {
        PlannerActionKind.ACTIVATE: {"activate", "click"},
        PlannerActionKind.FOCUS: {"focus", "fill", "type", "type_text"},
        PlannerActionKind.TYPE_TEXT: {"fill", "type", "type_text"},
        PlannerActionKind.SELECT_OPTION: {"select", "select_option"},
        PlannerActionKind.PRESS_KEY: {"press", "press_key"},
        PlannerActionKind.DRAG: {"drag"},
        PlannerActionKind.POINT_ACTIVATE: {"point_activate"},
    }.get(kind, set())
    return bool(compatible.intersection(target.supported_actions))


def _numeric_state_value(target: UnifiedObservationTarget) -> int | float | None:
    for key in ("value", "current_value", "aria-valuenow"):
        value = target.state.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    context_values = re.findall(
        r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])",
        str(target.state.get("context_text") or ""),
    )
    if len(context_values) == 1:
        return float(context_values[0])
    return None


def _numeric_expected_value(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
        return float(value)
    return None


def _target_looks_text_entry(target: UnifiedObservationTarget) -> bool:
    role = target.role.casefold()
    input_type = str(target.state.get("input_type", "")).casefold()
    return role in {"textbox", "searchbox", "textarea"} or input_type in {
        "email",
        "number",
        "password",
        "search",
        "tel",
        "text",
        "textarea",
        "url",
    }


def _target_looks_slider(target: UnifiedObservationTarget) -> bool:
    role = target.role.casefold()
    input_type = str(target.state.get("input_type", "")).casefold()
    return role in {"slider", "range"} or input_type == "range"


def _require_nonblank(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be blank")


def _require_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def _require_no_blank_values(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot contain blank values")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    _require_no_blank_values(label, values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")

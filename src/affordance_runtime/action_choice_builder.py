"""Runtime semantic action-choice generation and structural admission."""

from __future__ import annotations

import hashlib
from typing import Mapping, TypeAlias

from affordance_runtime.action_choice_authority import authorize_choice
from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.action_choice_generation import (
    _SemanticChoiceGenerator,
)
from affordance_runtime.choice_contracts import (
    ActionChoice,
    ActionChoiceFailure,
    ChoiceBuildReport,
    ChoiceConflictStatus,
    ChoiceRejection,
)
from affordance_runtime.effect_authority_contracts import AuthorityStatus
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.recovery_protocol import FailureKind
from affordance_runtime.simplified_runtime_contracts import (
    StepSpec,
)
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import (
    CanonicalTarget,
    UnifiedObservation,
    UnifiedObservationTarget,
)

CanonicalChoiceTarget: TypeAlias = CanonicalTarget | UnifiedObservationTarget


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
        inherited_rejections: tuple[ChoiceRejection, ...] = ()
        if isinstance(result, ActionChoiceFailure):
            generated_choices = _deterministic_semantic_choices(
                task_revision=task_revision,
                state_version=state_version,
                step=step,
                observation=observation,
            )
            inherited_rejections = result.build_report.rejections if result.build_report else ()
            if not generated_choices:
                report = ChoiceBuildReport(
                    len(observation.targets),
                    0,
                    inherited_rejections,
                )
                return ActionChoiceFailure(
                    result.kind,
                    result.reason_code,
                    result.owner,
                    build_report=report,
                )
        else:
            generated_choices = result.choices
        by_target = {item.target_id: item for item in observation.targets}
        choices: list[ActionChoice] = []
        rejections: list[ChoiceRejection] = list(inherited_rejections)
        for choice in generated_choices:
            target = by_target.get(choice.target_id)
            conflict = getattr(getattr(target, "conflict_status", None), "value", "")
            if conflict in {"material_conflict", "inconclusive"}:
                rejections.append(
                    ChoiceRejection(
                        choice.target_id,
                        choice.action_kind,
                        AuthorityStatus.UNPROVEN,
                        ("MATERIAL_SOURCE_CONFLICT",),
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
                evidence_refs=tuple(getattr(target, "source_assertion_refs", ())),
                conflict_status=ChoiceConflictStatus.CLEAR,
            )
            authority = authorize_choice(candidate_choice, step, task_spec, observation)
            if not authority.authorized:
                rejections.append(
                    ChoiceRejection(
                        choice.target_id,
                        choice.action_kind,
                        authority.status,
                        authority.reason_codes,
                    )
                )
                continue
            choices.append(
                ActionChoice(
                    **{
                        **candidate_choice.__dict__,
                        "destination_label": getattr(by_target.get(choice.destination_id), "label", ""),
                        "effect_refs": authority.effect_refs,
                        "risk": authority.risk.value if authority.risk is not None else "unknown",
                        "action_authority_proof": authority,
                        "effect_summary": _effect_summary(authority),
                        "authorization_reason_codes": authority.reason_codes,
                    }
                )
            )
        report = ChoiceBuildReport(len(observation.targets), len(choices), tuple(rejections))
        if not choices:
            reason = (
                "authority_unproven"
                if any(item.status == AuthorityStatus.UNPROVEN for item in report.rejections)
                else "authority_denied"
            )
            return ActionChoiceFailure(FailureKind.NO_FEASIBLE_ACTION, reason, build_report=report)
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
    *, task_revision: int, state_version: int, step: StepSpec, observation: UnifiedObservation
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
                evidence_refs=tuple(getattr(target, "source_assertion_refs", ())),
                generation_reason_codes=("deterministic_active_step_narrowing",),
            )
        )
    return tuple(values)


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


def _effect_summary(proof: object) -> str:
    effect_class = getattr(getattr(proof, "effect_class", None), "value", "unknown")
    risk = getattr(getattr(proof, "runtime_risk", None), "value", "critical")
    return f"{effect_class}; runtime risk {risk}"


def _semantic_presentation_state(state: object) -> dict[str, object]:
    if not isinstance(state, Mapping):
        return {}
    return {key: value for key, value in state.items() if key in _PRESENTABLE_STATE_KEYS}

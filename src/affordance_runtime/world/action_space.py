"""Task-aware construction and validation of offered semantic actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import time
from typing import Any

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.task.planning_contracts import LocalObjective
from affordance_runtime.world.action_classification import EffectCategory
from affordance_runtime.world.admission_issue import AdmissionIssue, AdmissionIssueCode
from affordance_runtime.world.contracts import (
    ActionBinding,
    ActionOption,
    ActionRisk,
    ActionSpace,
    AdmittedActionSelection,
    WorldObservation,
    validate_selected_destination,
)
from affordance_runtime.world.schema_validation import (
    reject_private_parameter_values,
    validate_value,
    validate_value_issue,
)

_FORBIDDEN_PARAMETER_KEYS = frozenset(
    {
        "backend",
        "bbox",
        "coordinate",
        "coordinates",
        "endpoint",
        "credential",
        "href",
        "method",
        "point",
        "security",
        "security_scheme",
        "selector",
        "x",
        "y",
    }
)
_GroupKey = tuple[str, str, str, tuple[str, ...], str, bool, bool, tuple[str, ...]]


@dataclass(frozen=True)
class ActionAdmissionResult:
    admitted: AdmittedActionSelection | None = None
    issue: AdmissionIssue | None = None

    def __post_init__(self) -> None:
        if (self.admitted is None) == (self.issue is None):
            raise ValueError("action admission result must contain exactly one outcome")


@dataclass(frozen=True)
class ActionSpaceBuilder:
    def build(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        objective: LocalObjective | None = None,
    ) -> ActionSpace:
        del objective  # Reserved for desired-state narrowing; it never grants effects.
        conflicted_targets = {conflict.subject_id for conflict in observation.conflicts}
        grouped: dict[_GroupKey, list[ActionBinding]] = {}
        for binding in observation.bindings:
            if binding.target_id in conflicted_targets:
                continue
            if not _binding_is_current(binding, observation) or not _effects_allowed(task, binding):
                continue
            schema_key = json.dumps(to_json_compatible(binding.parameter_schema), sort_keys=True, separators=(",", ":"))
            group_key = (
                binding.target_id,
                binding.semantic_action,
                binding.effect_category,
                binding.semantic_effects,
                schema_key,
                binding.observation_barrier,
                binding.destination_required,
                binding.eligible_destination_ids,
            )
            grouped.setdefault(group_key, []).append(binding)
        options = []
        for group_key, bindings in sorted(grouped.items()):
            target_id, action, category, effects, schema_key, barrier, destination_required, destinations = group_key
            risk = max((binding.risk for binding in bindings), key=_risk_rank)
            parameter_schema_digest = schema_digest(bindings[0].parameter_schema)
            eligible_binding_ids = tuple(sorted(binding.binding_id for binding in bindings))
            digest = hashlib.sha256(
                json.dumps(
                    [
                        observation.observation_id,
                        target_id,
                        action,
                        category,
                        effects,
                        parameter_schema_digest,
                        eligible_binding_ids,
                        barrier,
                        destination_required,
                        destinations,
                    ],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:16]
            options.append(
                ActionOption(
                    action_id=f"action:{digest}",
                    observation_id=observation.observation_id,
                    semantic_action=action,
                    target_id=target_id,
                    effect_category=category,
                    parameter_schema=to_json_compatible(bindings[0].parameter_schema),
                    schema_digest=parameter_schema_digest,
                    eligible_binding_ids=eligible_binding_ids,
                    description=f"{action} {target_id}",
                    semantic_effects=effects,
                    risk=risk,
                    destination_required=bool(destination_required),
                    eligible_destination_ids=tuple(str(item) for item in destinations),
                    observation_barrier=barrier,
                )
            )
        return ActionSpace(observation.observation_id, tuple(options))

    def validate_parameters(self, option: ActionOption, parameters: dict[str, Any]) -> None:
        if _FORBIDDEN_PARAMETER_KEYS.intersection(parameters):
            raise ValueError("policy parameters contain runtime-private execution fields")
        reject_private_parameter_values(parameters)
        validate_value(parameters, option.parameter_schema)

    def admit(
        self,
        option: ActionOption,
        parameters: dict[str, Any],
        destination_id: str = "",
    ) -> AdmittedActionSelection:
        result = self.try_admit(option, parameters, destination_id)
        if result.admitted is not None:
            return result.admitted
        assert result.issue is not None
        # Compatibility wrapper only. Production routing consumes the typed result.
        if result.issue.code is AdmissionIssueCode.INVALID_ACTION_PARAMETERS:
            self.validate_parameters(option, parameters)
        _validate_destination(option, destination_id)
        raise AssertionError("typed admission rejected without compatibility error")

    def try_admit(
        self,
        option: ActionOption,
        parameters: dict[str, Any],
        destination_id: str = "",
    ) -> ActionAdmissionResult:
        issue = self.parameter_issue(option, parameters)
        if issue is None:
            issue = _destination_issue(option, destination_id)
        if issue is not None:
            return ActionAdmissionResult(issue=issue)
        return ActionAdmissionResult(admitted=AdmittedActionSelection(
            option.action_id,
            option.observation_id,
            option.semantic_action,
            option.target_id,
            option.effect_category,
            option.semantic_effects,
            option.schema_digest,
            option.eligible_binding_ids,
            option.risk,
            option.observation_barrier,
            parameters,
            destination_id,
            option.destination_required,
            option.eligible_destination_ids,
        ))

    def try_admit_selection(
        self,
        action_space: ActionSpace,
        action_id: str,
        parameters: dict[str, Any],
        destination_id: str = "",
    ) -> ActionAdmissionResult:
        """Admit by public selection identity without throwing or parsing prose."""

        option = action_space.find(action_id)
        if option is None:
            return ActionAdmissionResult(issue=AdmissionIssue(
                AdmissionIssueCode.ACTION_OUTSIDE_ACTION_SPACE,
                ("action_id",),
            ))
        return self.try_admit(option, parameters, destination_id)

    def parameter_issue(
        self,
        option: ActionOption,
        parameters: dict[str, Any],
    ) -> AdmissionIssue | None:
        if _FORBIDDEN_PARAMETER_KEYS.intersection(parameters):
            return AdmissionIssue(
                AdmissionIssueCode.INVALID_ACTION_PARAMETERS,
                ("parameters",),
            )
        return validate_value_issue(parameters, option.parameter_schema)


def _binding_is_current(binding: ActionBinding, observation: WorldObservation) -> bool:
    if binding.world_observation_id != observation.observation_id:
        return False
    if not binding.target_fingerprint or (binding.expires_at_s and time() > binding.expires_at_s):
        return False
    if not observation.sources:
        return binding.source_observation_id == observation.observation_id
    source = next((item for item in observation.sources if item.surface == binding.surface), None)
    return bool(
        source
        and binding.source_observation_id == source.observation_id
        and binding.source_revision == source.revision
    )


def _effects_allowed(task: TaskGoal, binding: ActionBinding) -> bool:
    effects = set(binding.semantic_effects)
    if effects.intersection(task.forbidden_effects):
        return False
    observation_action = (
        binding.effect_category == EffectCategory.OBSERVATION
        and binding.semantic_action == "read"
        and not effects
        and binding.risk == ActionRisk.LOW
    )
    if binding.semantic_action == "read" and not observation_action:
        return False
    if task.risk_profile == RiskProfile.READ_ONLY:
        return observation_action
    return observation_action or bool(effects) and effects.issubset(task.allowed_effects)


def _risk_rank(risk: ActionRisk) -> int:
    return (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE).index(risk)


def _validate_destination(option: ActionOption, destination_id: str) -> None:
    if destination_id and not option.eligible_destination_ids:
        raise ValueError("action does not accept a semantic destination")
    validate_selected_destination(destination_id, option.destination_required, option.eligible_destination_ids)


def _destination_issue(option: ActionOption, destination_id: str) -> AdmissionIssue | None:
    try:
        _validate_destination(option, destination_id)
    except ValueError:
        return AdmissionIssue(
            AdmissionIssueCode.INVALID_ACTION_PARAMETERS,
            ("destination_id",),
        )
    return None

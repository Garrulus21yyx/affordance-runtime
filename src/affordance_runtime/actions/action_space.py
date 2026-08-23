"""Task-aware construction and validation of offered semantic actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import time
from typing import Any

from affordance_runtime.actions.admission import AdmissionIssue, AdmissionIssueCode
from affordance_runtime.actions.classification import EffectCategory
from affordance_runtime.actions.schema_validation import (
    reject_private_parameter_values,
    validate_value,
    validate_value_issue,
)
from affordance_runtime.actions.space_contracts import (
    ActionOption,
    ActionRisk,
    ActionSpace,
    ActionSpaceIssue,
    ActionSpaceIssueCode,
    AdmittedActionSelection,
    validate_selected_destination,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task.contracts import RiskProfile, TaskGoal
from affordance_runtime.world.contracts import (
    ActionBinding,
    WorldObservation,
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
_GroupKey = tuple[str, str, str, tuple[str, ...], str, bool, bool, tuple[str, ...], str, str]


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
    ) -> ActionSpace:
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
                binding.verification_family,
                binding.verification_contract_digest,
            )
            grouped.setdefault(group_key, []).append(binding)
        selectors: dict[tuple[str, str], list[_GroupKey]] = {}
        for group_key in grouped:
            selectors.setdefault((group_key[0], group_key[1]), []).append(group_key)
        conflicted_routes_by_group: dict[_GroupKey, set[str]] = {}
        atomic_conflicts: dict[tuple[str, str, tuple[str, ...]], set[str]] = {}
        for selector, group_keys in sorted(selectors.items()):
            for index, left in enumerate(group_keys):
                left_routes = set(left[7]) or {""}
                for right in group_keys[index + 1 :]:
                    overlapping_routes = left_routes.intersection(set(right[7]) or {""})
                    if not overlapping_routes:
                        continue
                    conflict_fields = _conflicting_contract_fields([left, right])
                    if not conflict_fields:
                        continue
                    conflicted_routes_by_group.setdefault(left, set()).update(overlapping_routes)
                    conflicted_routes_by_group.setdefault(right, set()).update(overlapping_routes)
                    destinations = tuple(sorted(item for item in overlapping_routes if item))
                    atomic_conflicts.setdefault((selector[0], selector[1], destinations), set()).update(conflict_fields)
        issues = [
            ActionSpaceIssue(
                ActionSpaceIssueCode.ACTION_ROUTE_CONFLICT,
                operation,
                target_id,
                destinations,
                tuple(fields),
            )
            for (target_id, operation, destinations), fields in sorted(atomic_conflicts.items())
        ]
        publishable: dict[tuple[object, ...], tuple[_GroupKey, list[ActionBinding]]] = {}
        for group_key, bindings in grouped.items():
            conflicted_routes = conflicted_routes_by_group.get(group_key, set())
            if not group_key[7] and "" in conflicted_routes:
                continue
            destinations = tuple(item for item in group_key[7] if item not in conflicted_routes)
            if group_key[6] and not destinations:
                continue
            group_key = (*group_key[:7], destinations, *group_key[8:])
            contract_key = (*group_key[:7], *group_key[8:])
            existing = publishable.get(contract_key)
            if existing is None:
                publishable[contract_key] = (group_key, list(bindings))
                continue
            representative, merged_bindings = existing
            merged_destinations = tuple(sorted(set(representative[7]).union(group_key[7])))
            publishable[contract_key] = (
                (*representative[:7], merged_destinations, *representative[8:]),
                [*merged_bindings, *bindings],
            )
        target_order = {target.target_id: index for index, target in enumerate(observation.targets)}
        options = []
        ordered_groups = sorted(
            (value for value in publishable.values()),
            key=lambda item: (
                target_order.get(item[0][0], len(target_order)),
                item[0][1],
                tuple(target_order.get(target_id, len(target_order)) for target_id in item[0][7]),
                item[0][2:7],
                item[0][8:],
            ),
        )
        for group_key, bindings in ordered_groups:
            (
                target_id,
                action,
                category,
                effects,
                schema_key,
                barrier,
                destination_required,
                destinations,
                verification_family,
                verification_digest,
            ) = group_key
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
                        verification_family,
                        verification_digest,
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
                    verification_family=verification_family,
                    verification_contract_digest=verification_digest,
                )
            )
        return ActionSpace(observation.observation_id, tuple(options), tuple(issues))

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
        expected_outcome: str = "",
    ) -> AdmittedActionSelection:
        result = self.try_admit(option, parameters, destination_id, expected_outcome)
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
        expected_outcome: str = "",
    ) -> ActionAdmissionResult:
        issue = self.parameter_issue(option, parameters)
        if issue is None:
            issue = _destination_issue(option, destination_id)
        if issue is not None:
            return ActionAdmissionResult(issue=issue)
        return ActionAdmissionResult(
            admitted=AdmittedActionSelection(
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
                option.verification_contract_digest,
                option.verification_family,
                _expected_outcome(expected_outcome),
            )
        )

    def try_admit_selection(
        self,
        action_space: ActionSpace,
        action_id: str,
        parameters: dict[str, Any],
        destination_id: str = "",
        expected_outcome: str = "",
    ) -> ActionAdmissionResult:
        """Admit by public selection identity without throwing or parsing prose."""

        option = action_space.find(action_id)
        if option is None:
            return ActionAdmissionResult(
                issue=AdmissionIssue(
                    AdmissionIssueCode.ACTION_OUTSIDE_ACTION_SPACE,
                    ("action_id",),
                    expected={"offered_action_ids": tuple(item.action_id for item in action_space.options[:32])},
                    actual={"action_id_offered": False},
                )
            )
        return self.try_admit(option, parameters, destination_id, expected_outcome)

    def parameter_issue(
        self,
        option: ActionOption,
        parameters: dict[str, Any],
    ) -> AdmissionIssue | None:
        if _FORBIDDEN_PARAMETER_KEYS.intersection(parameters):
            from affordance_runtime.actions.admission import invalid_parameters_issue

            return invalid_parameters_issue(
                expected={"private_fields_allowed": False},
                actual={"contains_private_field": True},
            )
        return validate_value_issue(parameters, option.parameter_schema)


def _binding_is_current(binding: ActionBinding, observation: WorldObservation) -> bool:
    if binding.world_observation_id != observation.observation_id:
        return False
    if not binding.target_fingerprint or (binding.expires_at_s and time() > binding.expires_at_s):
        return False
    if not observation.sources:
        return binding.source_observation_id == observation.observation_id
    source = next(
        (item for item in observation.sources if item.observation_id == binding.source_observation_id),
        None,
    )
    return bool(source and binding.surface == source.surface and binding.source_revision == source.revision)


def _expected_outcome(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 240:
        raise ValueError("expected outcome must be one bounded string")
    return value.strip()


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
    interaction_action = (
        binding.effect_category == EffectCategory.INTERACTION
        and binding.semantic_action == "activate"
        and not effects
        and binding.risk == ActionRisk.LOW
    )
    if binding.semantic_action == "read" and not observation_action:
        return False
    if task.risk_profile == RiskProfile.READ_ONLY:
        return observation_action or interaction_action
    return observation_action or interaction_action or bool(effects) and effects.issubset(task.allowed_effects)


def _risk_rank(risk: ActionRisk) -> int:
    return (ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE).index(risk)


def _conflicting_contract_fields(group_keys: list[_GroupKey]) -> tuple[str, ...]:
    names = (
        "effect_category",
        "semantic_effects",
        "parameter_schema",
        "observation_barrier",
        "destination_required",
        "verification_family",
        "verification_contract",
    )
    indexes = (2, 3, 4, 5, 6, 8, 9)
    return tuple(
        name
        for name, index in zip(names, indexes, strict=True)
        if len({group_key[index] for group_key in group_keys}) > 1
    )


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
            expected={
                "required": option.destination_required,
                "offered_destination_ids": option.eligible_destination_ids,
            },
            actual={"destination_id_offered": destination_id in option.eligible_destination_ids},
        )
    return None

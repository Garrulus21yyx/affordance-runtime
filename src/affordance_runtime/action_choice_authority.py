"""Exact TaskSpec authorization checks for concrete Runtime action choices."""

from __future__ import annotations

import re

from affordance_runtime.choice_contracts import ActionChoice
from affordance_runtime.scope_authorization import ProposalScopeEvaluator
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation

EFFECT_ACTION_TOKENS = frozenset(
    {
        "activate",
        "add",
        "button",
        "click",
        "create",
        "delete",
        "download",
        "enable",
        "export",
        "invoke",
        "open",
        "remove",
        "save",
        "send",
        "submit",
        "update",
    }
)


def choice_matches_task_authority(
    choice: ActionChoice,
    step: StepSpec,
    task_spec: TaskSpec,
    observation: UnifiedObservation,
) -> bool:
    """Admit a concrete effectful target only under the step's exact TaskSpec refs."""

    known = {item.requirement_id: item for item in task_spec.requirements}
    if set(choice.requirement_refs) - set(known):
        return False
    if set(choice.effect_refs) - set(task_spec.allowed_effect_refs):
        return False
    if not choice.effectful:
        return True
    if not choice.effect_refs or set(choice.effect_refs) - set(choice.requirement_refs):
        return False
    authority_terms = tuple(
        value
        for requirement_id in choice.effect_refs
        for value in (
            known[requirement_id].payload.subject,
            known[requirement_id].payload.value,
        )
        if requirement_id in known and value.strip()
    )
    target = next((item for item in observation.targets if item.target_id == choice.target_id), None)
    if target is None or not authority_terms:
        return False
    authority_tokens = _tokens(" ".join(authority_terms))
    target_tokens = _tokens(target.label)
    authority_entity_tokens = authority_tokens - EFFECT_ACTION_TOKENS
    target_entity_tokens = target_tokens - EFFECT_ACTION_TOKENS
    shared_effect_action = bool(authority_tokens & target_tokens & EFFECT_ACTION_TOKENS)
    if (
        shared_effect_action
        and authority_entity_tokens
        and target_entity_tokens
        and authority_entity_tokens.isdisjoint(target_entity_tokens)
    ):
        return False
    if not shared_effect_action or not target_entity_tokens:
        return True
    return (
        ProposalScopeEvaluator()
        .evaluate(
            action_kind=choice.action_kind.value,
            target_id=choice.target_id,
            target_label=target.label,
            target_role=target.role,
            parameters=choice.parameters,
            objective="",
            targets=authority_terms,
            unified_affordances=tuple(observation.targets),
            observation=observation,
            bindings=observation.bindings,
        )
        .authorized
    )


def requires_relational_scope_check(label: str, authority_terms: tuple[str, ...]) -> bool:
    label_tokens = _tokens(label)
    authority_tokens = _tokens(" ".join(authority_terms))
    return bool(label_tokens & authority_tokens & EFFECT_ACTION_TOKENS and label_tokens - EFFECT_ACTION_TOKENS)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))

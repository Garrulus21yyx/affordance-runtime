"""Identity-free digests over authoritative public semantics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.action_paging import InternalActionPage
from affordance_runtime.world.contracts import ActionOption, ActionSpace, SemanticTarget, WorldObservation


def _digest(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def target_semantics(
    target: SemanticTarget,
    target_bases: Mapping[str, tuple[object, ...]] | None = None,
) -> tuple[object, ...]:
    relations = to_json_compatible(target.relations)
    if target_bases is not None:
        relations = _replace_public_ids(relations, target_bases)
    return (
        target.role,
        target.label,
        to_json_compatible(target.state),
        relations,
    )


def public_world_semantics(observation: WorldObservation) -> dict[str, object]:
    bases = {
        target.target_id: (target.role, target.label, to_json_compatible(target.state))
        for target in observation.targets
    }
    targets = {
        target.target_id: target_semantics(target, bases)
        for target in observation.targets
    }
    facts = sorted((
        (
            targets.get(fact.subject_id, ("unresolved_subject",)),
            fact.predicate,
            to_json_compatible(fact.value),
        )
        for fact in observation.facts
    ), key=_sort_key)
    conflicts = sorted((
        (
            targets.get(conflict.subject_id, ("unresolved_subject",)),
            conflict.predicate,
            conflict.summary,
        )
        for conflict in observation.conflicts
    ), key=_sort_key)
    inventories = sorted(
        (
            source.surface,
            source.semantic_inventory.profile_id,
            source.semantic_inventory.status.value,
            source.semantic_inventory.recognized_target_count,
            source.semantic_inventory.projected_target_count,
            source.semantic_inventory.actionable_target_count,
            source.semantic_inventory.non_executable_target_count,
            source.semantic_inventory.omitted_target_count,
            source.semantic_inventory.informational_target_count,
        )
        for source in observation.sources
    )
    return {
        "targets": sorted(targets.values(), key=_sort_key),
        "facts": facts,
        "conflicts": conflicts,
        "inventory": inventories,
        "coverage": sorted((str(key), str(value)) for key, value in observation.coverage.items()),
    }


def public_world_semantic_digest(observation: WorldObservation) -> str:
    return _digest(public_world_semantics(observation))


def public_subject_semantics(observation: WorldObservation, subject_id: str) -> object:
    target = next((item for item in observation.targets if item.target_id == subject_id), None)
    if target is None:
        return ("unknown_public_subject",)
    bases = {
        item.target_id: (item.role, item.label, to_json_compatible(item.state))
        for item in observation.targets
    }
    return target_semantics(target, bases)


def action_option_semantics(
    option: ActionOption,
    target_map: Mapping[str, tuple[object, ...]],
    *,
    visible_destinations: tuple[str, ...] | None = None,
    relevance: object = None,
) -> tuple[object, ...]:
    destinations = option.eligible_destination_ids if visible_destinations is None else visible_destinations
    description = option.description
    for public_id in target_map:
        description = description.replace(public_id, "<public-target>")
    return (
        option.semantic_action,
        target_map.get(option.target_id, ("unknown_public_target",)),
        tuple(sorted(target_map.get(item, ("unknown_public_target",)) for item in destinations)),
        to_json_compatible(option.parameter_schema),
        option.effect_category,
        tuple(sorted(option.semantic_effects)),
        option.risk.value,
        option.destination_required,
        option.observation_barrier,
        description,
        to_json_compatible(relevance),
    )


def public_action_page_semantics(
    observation: WorldObservation,
    action_space: ActionSpace,
    page: InternalActionPage,
) -> dict[str, object]:
    bases = {
        target.target_id: (target.role, target.label, to_json_compatible(target.state))
        for target in observation.targets
    }
    target_map = {
        target.target_id: target_semantics(target, bases)
        for target in observation.targets
    }
    destination_map = dict(page.visible_destinations)
    relevance_map = dict(page.relevance)
    options = []
    for action_id in page.visible_action_ids:
        option = action_space.find(action_id)
        if option is None:
            continue
        options.append(action_option_semantics(
            option,
            target_map,
            visible_destinations=destination_map.get(action_id, ()),
            relevance=relevance_map.get(action_id),
        ))
    contract_options = [
        action_option_semantics(option, target_map)
        for option in action_space.options
    ]
    target_filter = target_map.get(page.target_id, ("none",)) if page.target_id else ("none",)
    return {
        "options": sorted(options, key=_sort_key),
        "contract_options": sorted(contract_options, key=_sort_key),
        "total_count": page.total_count,
        "has_more": page.has_more,
        "offset": page.offset,
        "query": page.query,
        "target_filter": target_filter,
        "relevance_role": str(page.relevance_role or ""),
    }


def public_action_page_digest(
    observation: WorldObservation,
    action_space: ActionSpace,
    page: InternalActionPage,
) -> str:
    return _digest(public_action_page_semantics(observation, action_space, page))


def task_progress_fingerprint(evaluation: TaskEvaluation | None) -> str:
    if evaluation is None:
        return _digest({"status": "unassessed"})
    return _digest({
        "status": evaluation.status.value,
        "criteria": sorted(
            (item.criterion_id, item.status.value) for item in evaluation.criteria
        ),
        "outputs": sorted(item.output_id for item in evaluation.outputs),
        "outcome": evaluation.outcome.kind.value if evaluation.outcome else "",
        "outcome_code": evaluation.outcome.code if evaluation.outcome else "",
    })


def semantic_scope_digest(
    task_revision: int,
    world_digest: str,
    page_digest: str,
    progress_digest: str,
) -> str:
    return _digest((task_revision, world_digest, page_digest, progress_digest))


def issue_digest(
    *,
    scope_digest: str,
    kind: str,
    source: str,
    code: str,
    subject_semantics: object,
    public_field_paths: tuple[str, ...],
    request_digest: str = "",
    result_digest: str = "",
) -> str:
    return _digest((
        scope_digest,
        kind,
        source,
        code,
        subject_semantics,
        tuple(sorted(set(public_field_paths))),
        request_digest,
        result_digest,
    ))


def action_page_request_digest(
    observation: WorldObservation,
    *,
    query: str,
    target_id: str,
    relevance_role: str,
    semantic_offset: int,
) -> str:
    return _digest((
        query,
        public_subject_semantics(observation, target_id) if target_id else ("none",),
        relevance_role,
        semantic_offset,
    ))


def observation_request_digest(
    observation: WorldObservation,
    *,
    subject_id: str,
    modality: str,
    required_assurance: str,
) -> str:
    return _digest((
        public_subject_semantics(observation, subject_id), modality, required_assurance,
    ))


def policy_observation_result_digest(
    observation: WorldObservation,
    action_space: ActionSpace,
    page: InternalActionPage,
    evaluation: TaskEvaluation | None,
) -> str:
    return _digest((
        public_world_semantics(observation),
        public_action_page_semantics(observation, action_space, page),
        task_progress_fingerprint(evaluation),
    ))


def _sort_key(value: object) -> str:
    return json.dumps(to_json_compatible(value), sort_keys=True, separators=(",", ":"))


def _replace_public_ids(value: object, targets: Mapping[str, tuple[object, ...]]) -> object:
    if isinstance(value, str):
        return targets.get(value, value)
    if isinstance(value, Mapping):
        return {
            str(key): _replace_public_ids(item, targets)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return tuple(_replace_public_ids(item, targets) for item in value)
    return value

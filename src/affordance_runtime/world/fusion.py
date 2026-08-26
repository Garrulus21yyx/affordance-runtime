"""Pure deterministic fusion of source-local observations into one canonical world."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import (
    ActionBinding,
    CanonicalObservationMedia,
    EntityAlignmentDecision,
    EntityAlignmentDisposition,
    EntityAlignmentProposal,
    EntityAllocation,
    EntitySourceLink,
    ObservationConflict,
    SemanticTarget,
    SourceEntityEndpoint,
    SourceObservationManifest,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)
from affordance_runtime.world.predicate_fusion import (
    OBSERVATION_PREDICATE_REGISTRY,
    PredicateFusionError,
)


class FusionStatus(StrEnum):
    FUSED = "fused"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class WorldFusionResult:
    status: FusionStatus
    observation: WorldObservation | None
    reason_code: str

    def __post_init__(self) -> None:
        if (self.status is FusionStatus.FUSED) != isinstance(self.observation, WorldObservation):
            raise ValueError("fusion status and observation disagree")


@dataclass(frozen=True)
class _AlignmentPlan:
    decisions: tuple[EntityAlignmentDecision, ...]
    links: tuple[EntitySourceLink, ...]
    mapping: dict[SourceEntityEndpoint, str]
    canonical_order: tuple[str, ...]


@dataclass(frozen=True)
class WorldFusion:
    def fuse(self, sources: tuple[SurfaceObservation, ...]) -> WorldFusionResult:
        if not sources:
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, "no_acquired_source")
        if len({source.observation_id for source in sources}) != len(sources):
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, "duplicate_source_observation_id")
        ordered_sources = tuple(sorted(sources, key=lambda item: item.observation_id))
        try:
            for source in ordered_sources:
                OBSERVATION_PREDICATE_REGISTRY.validate_source(source)
        except PredicateFusionError as exc:
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, str(exc))
        source_error = _source_domain_error(ordered_sources)
        if source_error:
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, source_error)
        visual_error = _visual_binding_authority_error(ordered_sources)
        if visual_error:
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, visual_error)
        proposal_error = _proposal_set_error(ordered_sources)
        if proposal_error:
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, proposal_error)

        plan = _alignment_plan(ordered_sources)
        world_id = _world_id(ordered_sources)
        source_by_id = {source.observation_id: source for source in ordered_sources}
        targets_by_source = {
            source.observation_id: {target.target_id: target for target in source.targets}
            for source in ordered_sources
        }
        targets: list[SemanticTarget] = []
        facts: list[StateFact] = []
        conflicts: list[ObservationConflict] = []
        bindings: list[ActionBinding] = []
        links_by_canonical: dict[str, list[EntitySourceLink]] = defaultdict(list)
        for link in plan.links:
            links_by_canonical[link.canonical_target_id].append(link)

        for canonical_id in plan.canonical_order:
            endpoint_targets = tuple(
                (
                    source_by_id[link.source_observation_id],
                    targets_by_source[link.source_observation_id][link.source_target_id],
                )
                for link in sorted(
                    links_by_canonical[canonical_id],
                    key=lambda item: (item.source_observation_id, item.source_target_id),
                )
            )
            target, target_conflicts = _fuse_target(canonical_id, endpoint_targets, plan.mapping)
            targets.append(target)
            conflicts.extend(target_conflicts)

        conflicted_keys = {(item.subject_id, item.predicate) for item in conflicts}
        fact_claims: dict[tuple[str, str], list[tuple[SurfaceObservation, StateFact]]] = defaultdict(list)
        for source in ordered_sources:
            for fact in source.facts:
                endpoint = SourceEntityEndpoint(source.observation_id, fact.subject_id)
                fact_claims[(plan.mapping[endpoint], fact.predicate)].append((source, fact))
        used_fact_ids: set[str] = set()
        for key in sorted(fact_claims):
            claims = tuple(fact_claims[key])
            _, disputed = OBSERVATION_PREDICATE_REGISTRY.resolve(
                "state", tuple((source, fact.value) for source, fact in claims)
            )
            if disputed:
                if key not in conflicted_keys:
                    conflicts.append(_conflict(*key))
                    conflicted_keys.add(key)
                continue
            for source, fact in sorted(claims, key=lambda item: (item[0].observation_id, item[1].fact_id)):
                fact_id = fact.fact_id
                if fact_id in used_fact_ids:
                    fact_id = "fact:" + _digest(source.observation_id, fact.fact_id)
                used_fact_ids.add(fact_id)
                facts.append(replace(fact, fact_id=fact_id, subject_id=key[0]))

        conflicted_by_target: dict[str, set[str]] = defaultdict(set)
        for conflict in conflicts:
            conflicted_by_target[conflict.subject_id].add(conflict.predicate)
        targets = [
            replace(
                target,
                state={
                    key: value
                    for key, value in target.state.items()
                    if key not in conflicted_by_target[target.target_id]
                },
            )
            for target in targets
        ]

        for source in ordered_sources:
            for binding in source.bindings:
                endpoint = SourceEntityEndpoint(source.observation_id, binding.target_id)
                canonical_target_id = plan.mapping[endpoint]
                bindings.append(replace(
                    binding,
                    world_observation_id=world_id,
                    target_id=canonical_target_id,
                    resource_ref=(
                        canonical_target_id
                        if binding.resource_ref == binding.target_id
                        else binding.resource_ref
                    ),
                    eligible_destination_ids=tuple(
                        plan.mapping[SourceEntityEndpoint(source.observation_id, item)]
                        for item in binding.eligible_destination_ids
                    ),
                ))

        canonical_media = tuple(sorted((
            CanonicalObservationMedia(
                source.observation_id,
                replace(
                    media,
                    grounding_regions=tuple(
                        replace(
                            region,
                            target_id=plan.mapping[
                                SourceEntityEndpoint(source.observation_id, region.target_id)
                            ],
                        )
                        for region in media.grounding_regions
                    ),
                ),
            )
            for source in ordered_sources
            for media in source.media
        ), key=lambda item: (
            item.media.capture_group_id,
            str(item.media.variant),
            item.media.coordinate_space_id,
            item.source_observation_id,
            item.media.media_id,
        )))
        manifests = tuple(
            SourceObservationManifest(
                source.observation_id,
                source.surface,
                str(source.source_profile.modality),
                source.source_profile.debug_source,
                source.acquisition_root_id or source.observation_id,
                source.coverage,
            )
            for source in ordered_sources
        )
        world = WorldObservation(
            observation_id=world_id,
            targets=tuple(targets),
            facts=tuple(facts),
            bindings=tuple(bindings),
            source_manifest=manifests,
            conflicts=tuple(sorted(
                {(item.subject_id, item.predicate): item for item in conflicts}.values(),
                key=lambda item: (item.subject_id, item.predicate),
            )),
            sources=ordered_sources,
            entity_alignment_decisions=plan.decisions,
            entity_source_links=plan.links,
            media=canonical_media,
        )
        return WorldFusionResult(FusionStatus.FUSED, world, "world_fused")


def _source_domain_error(sources: tuple[SurfaceObservation, ...]) -> str:
    for source in sources:
        local_ids = {item.target_id for item in source.targets}
        if any(item.subject_id not in local_ids for item in source.facts):
            return "unresolved_source_subject"
        if any(
            item.target_id not in local_ids
            or any(destination not in local_ids for destination in item.eligible_destination_ids)
            for item in source.bindings
        ):
            return "unresolved_source_binding"
        if any(
            region.target_id not in local_ids
            for media in source.media
            for region in media.grounding_regions
        ):
            return "unresolved_source_media_region"
        if any(_has_unresolved_relation(target.relations, local_ids) for target in source.targets):
            return "unresolved_source_relation"
    return ""


def _has_unresolved_relation(relations: dict[str, object], local_ids: set[str]) -> bool:
    for key in ("parent_id", "label_for_id"):
        if key not in relations:
            continue
        value = relations[key]
        if not isinstance(value, str) or value not in local_ids:
            return True
    if "child_ids" in relations:
        value = relations["child_ids"]
        if not isinstance(value, tuple | list) or any(
            not isinstance(item, str) or item not in local_ids for item in value
        ):
            return True
    return False


def _proposal_set_error(sources: tuple[SurfaceObservation, ...]) -> str:
    proposals = tuple(item for source in sources for item in source.alignment_proposals)
    if len({item.proposal_id for item in proposals}) != len(proposals):
        return "duplicate_alignment_proposal_id"
    pairs = {tuple(sorted((item.source, item.candidate))) for item in proposals}
    if len(pairs) != len(proposals):
        return "duplicate_alignment_endpoint_pair"
    return ""


def _visual_binding_authority_error(sources: tuple[SurfaceObservation, ...]) -> str:
    structural_roots = {
        source.acquisition_root_id or source.observation_id
        for source in sources
        if source.source_profile.modality.value == "structural"
    }
    for source in sources:
        if source.source_profile.modality.value != "visual" or not source.bindings:
            continue
        bound_ids = {item.target_id for item in source.bindings}
        proposed_ids = {item.source.source_target_id for item in source.alignment_proposals}
        if bound_ids.intersection(proposed_ids):
            return "proposed_visual_binding_forbidden"
        if not bound_ids.issubset(source.visual_only_target_ids):
            return "visual_binding_identity_unclassified"
        if structural_roots and (
            source.acquisition_root_id or source.observation_id
        ) not in structural_roots:
            return "visual_binding_requires_shared_acquisition"
    return ""


def _alignment_plan(sources: tuple[SurfaceObservation, ...]) -> _AlignmentPlan:
    source_by_id = {source.observation_id: source for source in sources}
    target_by_endpoint = {
        SourceEntityEndpoint(source.observation_id, target.target_id): target
        for source in sources
        for target in source.targets
    }
    proposals = tuple(item for source in sources for item in source.alignment_proposals)
    valid: list[EntityAlignmentProposal] = []
    rejected: list[EntityAlignmentDecision] = []
    for proposal in proposals:
        left_source = source_by_id.get(proposal.source.source_observation_id)
        right_source = source_by_id.get(proposal.candidate.source_observation_id)
        left_target = target_by_endpoint.get(proposal.source)
        right_target = target_by_endpoint.get(proposal.candidate)
        reason = ""
        if left_source is None or right_source is None or left_target is None or right_target is None:
            reason = "alignment_endpoint_unresolved"
        elif proposal.source.source_observation_id == proposal.candidate.source_observation_id:
            reason = "alignment_same_source_forbidden"
        elif (
            not left_source.acquisition_root_id
            or left_source.acquisition_root_id != right_source.acquisition_root_id
        ):
            reason = "alignment_acquisition_root_mismatch"
        elif left_target.role != right_target.role:
            reason = "alignment_role_mismatch"
        elif not _coordinate_spaces_compatible(
            left_source,
            proposal.source.source_target_id,
            right_source,
            proposal.candidate.source_target_id,
        ):
            reason = "alignment_coordinate_space_mismatch"
        if reason:
            rejected.append(_decision(
                proposal,
                EntityAlignmentDisposition.REJECTED,
                reason,
            ))
        else:
            valid.append(proposal)

    adjacency: dict[SourceEntityEndpoint, set[SourceEntityEndpoint]] = defaultdict(set)
    for proposal in valid:
        adjacency[proposal.source].add(proposal.candidate)
        adjacency[proposal.candidate].add(proposal.source)

    components: list[tuple[SourceEntityEndpoint, ...]] = []
    visited: set[SourceEntityEndpoint] = set()
    for endpoint in sorted(target_by_endpoint):
        if endpoint in visited:
            continue
        pending = [endpoint]
        component_set: set[SourceEntityEndpoint] = set()
        while pending:
            current = pending.pop()
            if current in component_set:
                continue
            component_set.add(current)
            pending.extend(adjacency[current])
        visited.update(component_set)
        components.append(tuple(sorted(component_set)))

    conflicted: set[SourceEntityEndpoint] = set()
    for endpoint_component in components:
        source_ids = [item.source_observation_id for item in endpoint_component]
        if len(source_ids) != len(set(source_ids)):
            conflicted.update(endpoint_component)

    decisions = [*rejected]
    for proposal in valid:
        if proposal.source in conflicted or proposal.candidate in conflicted:
            decisions.append(_decision(
                proposal,
                EntityAlignmentDisposition.CONFLICTED,
                "alignment_component_conflicted",
            ))
        else:
            decisions.append(_decision(
                proposal,
                EntityAlignmentDisposition.ACCEPTED,
                "explicit_equivalence_accepted",
            ))

    accepted_adjacency: dict[SourceEntityEndpoint, set[SourceEntityEndpoint]] = defaultdict(set)
    proposals_by_id = {item.proposal_id: item for item in proposals}
    for decision in decisions:
        if decision.disposition is not EntityAlignmentDisposition.ACCEPTED:
            continue
        proposal = proposals_by_id[decision.proposal_id]
        accepted_adjacency[proposal.source].add(proposal.candidate)
        accepted_adjacency[proposal.candidate].add(proposal.source)
    final_components: list[tuple[SourceEntityEndpoint, ...]] = []
    visited = set()
    for endpoint in sorted(target_by_endpoint):
        if endpoint in visited:
            continue
        pending = [endpoint]
        component: set[SourceEntityEndpoint] = set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(accepted_adjacency[current])
        visited.update(component)
        final_components.append(tuple(sorted(component)))
    source_rank = {
        source.observation_id: (
            {
                "structural": 0,
                "environment_state": 1,
                "user": 2,
                "visual": 3,
            }.get(source.source_profile.modality.value, 99),
            source.observation_id,
        )
        for source in sources
    }
    target_rank = {
        (source.observation_id, target.target_id): index
        for source in sources
        for index, target in enumerate(source.targets)
    }
    final_components.sort(key=lambda component: min(
        (*source_rank[endpoint.source_observation_id], target_rank[
            (endpoint.source_observation_id, endpoint.source_target_id)
        ])
        for endpoint in component
    ))
    mapping: dict[SourceEntityEndpoint, str] = {}
    links: list[EntitySourceLink] = []
    canonical_order: list[str] = []
    used_canonical_ids: set[str] = set()
    for endpoint_component in final_components:
        primary = min(
            endpoint_component,
            key=lambda endpoint: (
                {
                    "structural": 0,
                    "environment_state": 1,
                    "user": 2,
                    "visual": 3,
                }.get(
                    str(source_by_id[endpoint.source_observation_id].source_profile.modality),
                    9,
                ),
                endpoint.source_target_id,
                endpoint.source_observation_id,
            ),
        )
        local_ids = {item.source_target_id for item in endpoint_component}
        canonical_id = (
            primary.source_target_id
            if len(local_ids) == 1
            else "entity:" + _digest(*(
                f"{item.source_observation_id}\0{item.source_target_id}"
                for item in sorted(endpoint_component)
            ))
        )
        if canonical_id in used_canonical_ids:
            canonical_id = "entity:" + _digest(
                *(f"{item.source_observation_id}\0{item.source_target_id}" for item in endpoint_component)
            )
        used_canonical_ids.add(canonical_id)
        canonical_order.append(canonical_id)
        accepted = len(endpoint_component) > 1
        for endpoint in endpoint_component:
            mapping[endpoint] = canonical_id
            source = source_by_id[endpoint.source_observation_id]
            links.append(EntitySourceLink(
                endpoint.source_observation_id,
                endpoint.source_target_id,
                canonical_id,
                source.acquisition_root_id or source.observation_id,
                EntityAllocation.EQUIVALENT if accepted else EntityAllocation.INDEPENDENT,
            ))
    return _AlignmentPlan(
        tuple(sorted(decisions, key=lambda item: item.proposal_id)),
        tuple(sorted(links, key=lambda item: (item.source_observation_id, item.source_target_id))),
        mapping,
        tuple(canonical_order),
    )


def _decision(
    proposal: EntityAlignmentProposal,
    disposition: EntityAlignmentDisposition,
    reason_code: str,
) -> EntityAlignmentDecision:
    return EntityAlignmentDecision(
        proposal.proposal_id,
        disposition,
        proposal.basis,
        proposal.evidence_refs,
        proposal.confidence,
        reason_code,
    )


def _coordinate_spaces_compatible(
    left_source: SurfaceObservation,
    left_target_id: str,
    right_source: SurfaceObservation,
    right_target_id: str,
) -> bool:
    left_spaces = {
        region.coordinate_space_id
        for media in left_source.media
        for region in media.grounding_regions
        if region.target_id == left_target_id
    }
    right_spaces = {
        region.coordinate_space_id
        for media in right_source.media
        for region in media.grounding_regions
        if region.target_id == right_target_id
    }
    return not left_spaces or not right_spaces or left_spaces == right_spaces


def _fuse_target(
    canonical_id: str,
    endpoint_targets: tuple[tuple[SurfaceObservation, SemanticTarget], ...],
    mapping: dict[SourceEntityEndpoint, str],
) -> tuple[SemanticTarget, list[ObservationConflict]]:
    conflicts: list[ObservationConflict] = []
    role, role_conflicted = OBSERVATION_PREDICATE_REGISTRY.resolve(
        "role", tuple((source, target.role) for source, target in endpoint_targets)
    )
    label, label_conflicted = OBSERVATION_PREDICATE_REGISTRY.resolve(
        "label", tuple((source, target.label) for source, target in endpoint_targets)
    )
    if role_conflicted:
        conflicts.append(_conflict(canonical_id, "role"))
    if label_conflicted:
        conflicts.append(_conflict(canonical_id, "label"))
    predicates = sorted({key for _, target in endpoint_targets for key in target.state})
    state: dict[str, object] = {}
    for predicate in predicates:
        value, disputed = OBSERVATION_PREDICATE_REGISTRY.resolve(
            "state",
            tuple(
                (source, target.state[predicate])
                for source, target in endpoint_targets
                if predicate in target.state
            ),
        )
        if disputed:
            conflicts.append(_conflict(canonical_id, predicate))
        elif value is not None:
            state[predicate] = value
    relation_claims: dict[str, list[object]] = defaultdict(list)
    for source, target in endpoint_targets:
        local_mapping = {
            endpoint.source_target_id: canonical
            for endpoint, canonical in mapping.items()
            if endpoint.source_observation_id == source.observation_id
        }
        for key, value in _rewrite_relations(dict(target.relations), local_mapping).items():
            relation_claims[key].append(value)
    relations: dict[str, object] = {}
    for key in sorted(relation_claims):
        encoded = {
            json.dumps(to_json_compatible(value), sort_keys=True, separators=(",", ":")): value
            for value in relation_claims[key]
        }
        if len(encoded) == 1:
            relations[key] = next(iter(encoded.values()))
        else:
            conflicts.append(_conflict(canonical_id, f"relation:{key}"))
    return SemanticTarget(
        canonical_id,
        str(role) if role is not None else "unknown",
        str(label) if label is not None else "",
        state,
        relations,
    ), conflicts


def _rewrite_relations(relations: dict[str, object], mapping: dict[str, str]) -> dict[str, object]:
    for key in ("parent_id", "label_for_id"):
        value = relations.get(key)
        if isinstance(value, str):
            if value not in mapping:
                raise ValueError("source relation endpoint is unresolved")
            relations[key] = mapping[value]
    value = relations.get("child_ids")
    if isinstance(value, tuple | list):
        if any(str(item) not in mapping for item in value):
            raise ValueError("source relation endpoint is unresolved")
        relations["child_ids"] = tuple(mapping[str(item)] for item in value)
    return relations


def _world_id(sources: tuple[SurfaceObservation, ...]) -> str:
    if len(sources) == 1:
        return sources[0].observation_id
    return "world:" + _digest(*(
        f"{item.observation_id}\0{item.revision}\0{item.acquisition_root_id or item.observation_id}"
        for item in sources
    ))


def _conflict(subject: str, predicate: str) -> ObservationConflict:
    return ObservationConflict(
        "conflict:" + _digest(subject, predicate),
        subject,
        predicate,
        "material source claims disagree",
    )


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()

"""Deterministic PerceptionCapture to canonical observation fusion."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass

from affordance_runtime.contracts import Affordance, RiskLevel
from affordance_runtime.grounding import (
    AssertionDecision,
    AssertionResolutionStatus,
    GroundingCandidate,
    SourceAssertion,
    UnifiedAffordance,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.unified_grounding import candidate_from_affordance
from affordance_runtime.unified_observation import (
    ActionSupport,
    CanonicalTarget,
    ConflictStatus,
    FactStatus,
    Freshness,
    ObservationConflict,
    StateFact,
    UnifiedObservation,
)


def _risk_rank(value: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.IRREVERSIBLE: 3,
    }[value]


@dataclass(frozen=True)
class CanonicalObservationBuilder:
    """Own canonical fusion without consulting any presentation policy."""

    acquisition_policy_id: str = "default"

    def build(self, capture: PerceptionCapture) -> UnifiedObservation:
        _validate_capture_epoch(capture)
        observation = capture.observation
        semantic_targets, candidates = _complete_semantic_inputs(capture)
        assertions_by_target: dict[str, list[SourceAssertion]] = defaultdict(list)
        for assertion in capture.source_assertions:
            assertions_by_target[assertion.entity_key].append(assertion)
        decisions_by_target: dict[str, list[AssertionDecision]] = defaultdict(list)
        for decision in capture.assertion_decisions:
            decisions_by_target[decision.entity_key].append(decision)
        affordances_by_id = {item.id: item for item in capture.affordances}
        canonical_targets = tuple(
            _canonical_target(
                target,
                observation_epoch_id=observation.snapshot_id,
                environment_revision=observation.environment_revision,
                page_revision=observation.page_revision,
                observed_at_s=observation.observed_at_s,
                assertions=tuple(assertions_by_target.get(target.semantic_target_id, ())),
                decisions=tuple(decisions_by_target.get(target.semantic_target_id, ())),
                affordances_by_id=affordances_by_id,
            )
            for target in sorted(semantic_targets, key=lambda item: item.semantic_target_id)
        )
        bindings = tuple(sorted(candidates, key=lambda item: item.candidate_id))
        coverage = tuple(
            sorted(capture.source_coverage, key=lambda item: item.source.value)
        )
        artifact_refs = tuple(sorted(set(observation.artifact_refs)))
        metadata = dict(observation.metadata)
        observed_text = str(metadata.get("visible_text") or "")
        payload = {
            "epoch_id": observation.snapshot_id,
            "page_revision": observation.page_revision,
            "environment_revision": observation.environment_revision,
            "targets": canonical_targets,
            "bindings": bindings,
            "coverage": coverage,
            "artifacts": artifact_refs,
            "acquisition_policy_id": self.acquisition_policy_id,
        }
        digest = "sha256:" + hashlib.sha256(
            json.dumps(
                to_json_compatible(payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        return UnifiedObservation(
            epoch_id=observation.snapshot_id,
            page_revision=observation.page_revision,
            environment_revision=observation.environment_revision,
            observed_text=observed_text,
            targets=canonical_targets,
            bindings=bindings,
            source_coverage=coverage,
            artifact_refs=artifact_refs,
            captured_at_s=observation.observed_at_s,
            digest=digest,
            acquisition_policy_id=self.acquisition_policy_id,
            metadata=metadata,
        )


def _validate_capture_epoch(capture: PerceptionCapture) -> None:
    observation = capture.observation
    identity = (
        observation.snapshot_id,
        observation.environment_revision,
        observation.page_revision,
    )
    if len(capture.source_coverage) != len(
        {item.source for item in capture.source_coverage}
    ):
        raise ValueError("capture source coverage must contain one record per source")
    for source in capture.source_observations:
        if (
            source.observation_epoch_id,
            source.environment_revision,
            source.page_revision,
        ) != identity:
            raise ValueError("source observation belongs to a different capture epoch")
    candidate_items = (
        *capture.grounding_candidates,
        *(
            candidate
            for target in capture.semantic_targets
            for candidate in target.grounding_candidates
        ),
    )
    candidates: dict[str, GroundingCandidate] = {}
    for candidate in candidate_items:
        existing = candidates.get(candidate.candidate_id)
        if existing is not None and existing != candidate:
            raise ValueError("candidate id cannot name different bindings in one epoch")
        candidates[candidate.candidate_id] = candidate
    target_ids = {item.semantic_target_id for item in capture.semantic_targets}
    for candidate in candidates.values():
        if (
            candidate.observation_epoch_id,
            candidate.environment_revision,
            candidate.page_revision,
        ) != identity:
            raise ValueError("grounding candidate belongs to a different capture epoch")
        if target_ids and candidate.semantic_target_id not in target_ids:
            raise ValueError("grounding candidate has no canonical target in this epoch")
    assertions = {
        item.assertion_id: item
        for item in (
            *capture.source_assertions,
            *(
                assertion
                for decision in capture.assertion_decisions
                for assertion in decision.assertions
            ),
        )
    }
    for assertion in assertions.values():
        if (
            assertion.observation_epoch_id,
            assertion.environment_revision,
            assertion.page_revision,
        ) != identity:
            raise ValueError("source assertion belongs to a different capture epoch")


def _complete_semantic_inputs(
    capture: PerceptionCapture,
) -> tuple[tuple[UnifiedAffordance, ...], tuple[GroundingCandidate, ...]]:
    if capture.semantic_targets:
        candidates = tuple(
            {
                item.candidate_id: item
                for item in (
                    *capture.grounding_candidates,
                    *(candidate for target in capture.semantic_targets for candidate in target.grounding_candidates),
                )
            }.values()
        )
        return capture.semantic_targets, candidates
    targets: list[UnifiedAffordance] = []
    candidates: list[GroundingCandidate] = []
    for affordance in capture.affordances:
        candidate = candidate_from_affordance(
            affordance,
            capture.observation,
            semantic_target_id=affordance.id,
            image_size=_image_size(capture),
        )
        candidates.append(candidate)
        targets.append(
            UnifiedAffordance(
                semantic_target_id=affordance.id,
                role=affordance.role,
                label=affordance.label,
                supported_actions=candidate.supported_actions,
                grounding_candidates=(candidate,),
            )
        )
    return tuple(targets), tuple(candidates)


def _image_size(capture: PerceptionCapture) -> tuple[int, int] | None:
    metadata = capture.observation.metadata
    width = metadata.get("image_width")
    height = metadata.get("image_height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        return width, height
    return None


def _canonical_target(
    target: UnifiedAffordance,
    *,
    observation_epoch_id: str,
    environment_revision: str,
    page_revision: str,
    observed_at_s: float,
    assertions: tuple[SourceAssertion, ...],
    decisions: tuple[AssertionDecision, ...],
    affordances_by_id: dict[str, Affordance],
) -> CanonicalTarget:
    candidates = tuple(sorted(target.grounding_candidates, key=lambda item: item.candidate_id))
    candidate_ids_by_action: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        for action in sorted(candidate.supported_actions):
            candidate_ids_by_action[action].append(candidate.candidate_id)
    action_support = tuple(
        ActionSupport(
            action,
            tuple(candidate_ids_by_action[action]),
            max(
                (candidate.risk for candidate in candidates if action in candidate.supported_actions),
                key=_risk_rank,
                default=RiskLevel.LOW,
            ),
        )
        for action in sorted(candidate_ids_by_action)
    )
    facts, conflicts = _facts_and_conflicts(
        target.semantic_target_id,
        assertions,
        decisions,
        candidates,
        affordances_by_id,
    )
    material_conflict = any(item.material for item in conflicts)
    conflict_status = (
        ConflictStatus.MATERIAL_CONFLICT
        if material_conflict
        else ConflictStatus.INCONCLUSIVE
        if target.unresolved_conflicts
        else ConflictStatus.RESOLVED
        if decisions and all(item.status == AssertionResolutionStatus.ACCEPTED for item in decisions)
        else ConflictStatus.NO_MATERIAL_CONFLICT
    )
    assertion_refs = tuple(sorted(item.assertion_id for item in assertions))
    expires_at = min(
        (item.expires_at_s for item in candidates if item.expires_at_s),
        default=0.0,
    )
    return CanonicalTarget(
        target_id=target.semantic_target_id,
        role=target.role,
        label=target.label,
        surfaces=tuple(sorted({item.source for item in candidates}, key=lambda item: item.value)),
        action_support=action_support,
        state_facts=facts,
        binding_ids=tuple(item.candidate_id for item in candidates),
        conflict_status=conflict_status,
        conflicts=conflicts,
        source_assertion_refs=assertion_refs,
        freshness=Freshness(
            observation_epoch_id=observation_epoch_id,
            environment_revision=environment_revision,
            page_revision=page_revision,
            observed_at_s=observed_at_s,
            expires_at_s=expires_at,
        ),
    )


def _facts_and_conflicts(
    target_id: str,
    assertions: tuple[SourceAssertion, ...],
    decisions: tuple[AssertionDecision, ...],
    candidates: tuple[GroundingCandidate, ...],
    affordances_by_id: dict[str, Affordance],
) -> tuple[tuple[StateFact, ...], tuple[ObservationConflict, ...]]:
    by_property: dict[str, list[SourceAssertion]] = defaultdict(list)
    for assertion in assertions:
        by_property[assertion.property_key].append(assertion)
    synthetic: dict[str, list[tuple[str, object, str]]] = defaultdict(list)
    for candidate in candidates:
        affordance = affordances_by_id.get(candidate.source_affordance_id)
        if affordance is None:
            continue
        for key, value in affordance.state.items():
            synthetic[str(key)].append(
                (candidate.source.value, value, f"affordance:{affordance.id}:{key}")
            )
    decision_by_property = {item.property_key: item for item in decisions}
    properties = sorted(set(by_property) | set(synthetic) | set(decision_by_property))
    facts: list[StateFact] = []
    conflicts: list[ObservationConflict] = []
    for property_name in properties:
        source_assertions = sorted(
            by_property.get(property_name, ()), key=lambda item: item.assertion_id
        )
        source_values = [
            (item.source.value, item.value, item.assertion_id) for item in source_assertions
        ] or sorted(synthetic.get(property_name, ()), key=lambda item: (item[0], item[2]))
        decision = decision_by_property.get(property_name)
        conflicted = decision is not None and decision.status == AssertionResolutionStatus.CONFLICT
        distinct_values = {
            json.dumps(to_json_compatible(value), sort_keys=True, ensure_ascii=False)
            for _source, value, _ref in source_values
        }
        conflicted = conflicted or len(distinct_values) > 1
        refs = tuple(item[2] for item in source_values)
        if conflicted:
            facts.append(
                StateFact(
                    property_name=property_name,
                    value=None,
                    status=FactStatus.CONFLICTED,
                    assertion_refs=refs,
                    source_values=tuple((source, value) for source, value, _ref in source_values),
                )
            )
            material = decision.material if decision is not None else True
            conflicts.append(
                ObservationConflict(
                    target_id=target_id,
                    property_name=property_name,
                    assertion_refs=refs,
                    material=material,
                    reason=decision.reason if decision is not None else "source values disagree",
                )
            )
            continue
        accepted = decision.accepted_assertion if decision is not None else None
        value = accepted.value if accepted is not None else source_values[0][1] if source_values else None
        facts.append(
            StateFact(
                property_name=property_name,
                value=value,
                status=FactStatus.ACCEPTED if source_values else FactStatus.UNKNOWN,
                assertion_refs=refs,
                source_values=tuple((source, item) for source, item, _ref in source_values),
            )
        )
    return tuple(facts), tuple(conflicts)

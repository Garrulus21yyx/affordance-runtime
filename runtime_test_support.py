"""Typed contract fixtures shared by tests that intentionally construct plans directly."""

import hashlib

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import (
    AllOf,
    AnyOf,
    LiteralValue,
    PredicateExpr,
    PredicateOperator,
    SubjectExpr,
)
from affordance_runtime.observation_store import ObservationCommit, ObservationRef
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.simplified_runtime_contracts import (
    CompositeCriterion,
    CompositeCriterionOperator,
    ElementIntent,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    SatisfactionMode,
)


def make_interaction(target: str) -> ElementIntent:
    return ElementIntent(
        target,
        (SourceReference("test-request", "test-request:interaction"),),
    )


def canonical_observation(snapshot: BrowserSnapshot) -> UnifiedObservation:
    return CanonicalObservationBuilder().build(PerceptionCapture.from_browser_snapshot(snapshot))


def legacy_step_spec(*args: object, **kwargs: object) -> StepSpec:
    """Build a strict StepSpec through the explicit legacy test ingress."""

    positional = list(args)
    if len(positional) > 3:
        positional[3] = _canonicalize_test_criteria(
            tuple(positional[3]),
            role="completion",  # type: ignore[arg-type]
        )
    elif "completion_criteria" in kwargs:
        kwargs["completion_criteria"] = _canonicalize_test_criteria(
            tuple(kwargs["completion_criteria"]),
            role="completion",  # type: ignore[arg-type]
        )
    if kwargs.get("preconditions"):
        kwargs["preconditions"] = _canonicalize_test_criteria(
            tuple(kwargs["preconditions"]),
            role="precondition",  # type: ignore[arg-type]
        )
    kwargs.setdefault("requirement_refs", ("requirement:test",))
    return StepSpec(*positional, **kwargs)  # type: ignore[arg-type]


def _canonicalize_test_criteria(
    criteria: tuple[object, ...], *, role: str
) -> tuple[PredicateExpr | AllOf | AnyOf, ...]:
    legacy = tuple(
        item for item in criteria if isinstance(item, (StateCriterion, CompositeCriterion))
    )
    if len(legacy) != len(criteria):
        raise TypeError("test criteria must be uniformly legacy or canonical")
    if any(item.role != role for item in legacy):
        raise ValueError("test criterion role mismatch")
    by_id = {item.criterion_id: item for item in legacy}
    referenced = {
        child
        for item in legacy
        if isinstance(item, CompositeCriterion)
        for child in item.child_criterion_ids
    }

    def convert(item: StateCriterion | CompositeCriterion) -> PredicateExpr | AllOf | AnyOf:
        if isinstance(item, CompositeCriterion):
            children = tuple(convert(by_id[child]) for child in item.child_criterion_ids)
            return (
                AllOf(item.criterion_id, children)
                if item.operator == CompositeCriterionOperator.ALL_OF
                else AnyOf(item.criterion_id, children)
            )
        operator, field = _TEST_RELATIONS[item.relation]
        action_caused = item.relation in {
            StateCriterionRelation.IS_COMPLETED,
            StateCriterionRelation.HAS_CHANGED,
        }
        return PredicateExpr(
            item.criterion_id,
            SubjectExpr("target", item.subject, field),
            operator,
            CriterionPolicy(
                satisfaction=(
                    SatisfactionMode.ACTION_CAUSED
                    if action_caused
                    else SatisfactionMode.STATE_HOLDS
                ),
                minimum_assurance=AssuranceLevel.STRUCTURAL,
                allowed_source_kinds=tuple(
                    EvidenceSourceKind(value)
                    for value in item.evidence_policy.allowed_source_kinds
                    if value in EvidenceSourceKind._value2member_map_
                ),
                causal_lineage_required=action_caused,
            ),
            None if item.expected_value is None else LiteralValue(item.expected_value),
            tuple(ref.source_unit_id for ref in item.source_refs),
        )

    return tuple(convert(item) for item in legacy if item.criterion_id not in referenced)


_TEST_RELATIONS = {
    StateCriterionRelation.EQUALS: (PredicateOperator.EQUALS, "equals"),
    StateCriterionRelation.CONTAINS: (PredicateOperator.CONTAINS, "contains"),
    StateCriterionRelation.MATCHES: (PredicateOperator.MATCHES_REGEX, "matches"),
    StateCriterionRelation.IS_VISIBLE: (PredicateOperator.EXISTS, ""),
    StateCriterionRelation.IS_ABSENT: (PredicateOperator.ABSENT, ""),
    StateCriterionRelation.IS_AVAILABLE: (PredicateOperator.EXISTS, ""),
    StateCriterionRelation.IS_SELECTED: (PredicateOperator.SELECTED, "selected"),
    StateCriterionRelation.IS_CHECKED: (PredicateOperator.CHECKED, "checked"),
    StateCriterionRelation.IS_EXPANDED: (PredicateOperator.EQUALS, "expanded"),
    StateCriterionRelation.IS_COMPLETED: (PredicateOperator.CHANGED, "completed"),
    StateCriterionRelation.IS_ORDERED_AS: (PredicateOperator.ORDERED_AS, "ordered_as"),
    StateCriterionRelation.HAS_CHANGED: (PredicateOperator.CHANGED, "changed"),
}


def remember_observation(state: StateKernel, observation: Observation) -> None:
    """Install typed observation identity in unit tests without a legacy StateKernel API."""

    identity = "\0".join(
        (
            observation.snapshot_id,
            observation.environment_revision,
            observation.page_revision,
        )
    )
    digest = "sha256:" + hashlib.sha256(identity.encode()).hexdigest()
    state.remember_observation_commit(
        ObservationCommit(
            ObservationRef(observation.snapshot_id, digest),
            observation.environment_revision,
            observation.page_revision,
        )
    )

"""Criteria-bound progress shared by task plans and accepted TaskSkills.

Verification success and progress success are deliberately separate.  A
verifier can establish a fact without that fact satisfying the active unit of
work.  Progress requires an explicit, fresh link from strong evidence to every
mandatory criterion and evidence requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, TypeAlias

from affordance_runtime.contracts import Observation
from affordance_runtime.immutable import freeze_json
from affordance_runtime.verification.contracts import CriterionPolicy
from affordance_runtime.verification.mechanical import VerificationEvidence, VerificationReport


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    STRONG = "strong"


class PredicateOperator(StrEnum):
    """Registered vocabulary; registration does not imply provider coverage."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES_REGEX = "matches_regex"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    BETWEEN = "between"
    IN_SET = "in_set"
    EXISTS = "exists"
    ABSENT = "absent"
    VISIBLE = "visible"
    AVAILABLE = "available"
    ENABLED = "enabled"
    SELECTED = "selected"
    CHECKED = "checked"
    EXPANDED = "expanded"
    ORDERED_AS = "ordered_as"
    CHANGED = "changed"
    CONTAINS_ENTITY = "contains_entity"


MECHANICAL_BASELINE_OPERATORS = frozenset(
    {
        PredicateOperator.EQUALS,
        PredicateOperator.CONTAINS,
        PredicateOperator.STARTS_WITH,
        PredicateOperator.ENDS_WITH,
        PredicateOperator.BETWEEN,
        PredicateOperator.EXISTS,
        PredicateOperator.ABSENT,
        PredicateOperator.SELECTED,
        PredicateOperator.CHECKED,
        PredicateOperator.CHANGED,
    }
)


@dataclass(frozen=True)
class SubjectExpr:
    kind: str
    reference: str
    field: str = ""

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.reference.strip():
            raise ValueError("criterion subject requires typed kind and reference")


@dataclass(frozen=True)
class LiteralValue:
    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ReferenceValue:
    kind: str
    reference: str

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.reference.strip():
            raise ValueError("criterion value reference cannot be blank")


ValueExpression: TypeAlias = LiteralValue | ReferenceValue


@dataclass(frozen=True)
class PredicateExpr:
    criterion_id: str
    subject: SubjectExpr
    operator: PredicateOperator
    policy: CriterionPolicy
    value: ValueExpression | None = None
    source_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("predicate criterion_id cannot be blank")
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "effect_refs", tuple(self.effect_refs))


@dataclass(frozen=True)
class AllOf:
    criterion_id: str
    children: tuple[CriterionExpr, ...]

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.children:
            raise ValueError("all_of requires identity and children")


@dataclass(frozen=True)
class AnyOf:
    criterion_id: str
    children: tuple[CriterionExpr, ...]

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.children:
            raise ValueError("any_of requires identity and children")


@dataclass(frozen=True)
class Not:
    criterion_id: str
    child: CriterionExpr

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("not requires identity")


@dataclass(frozen=True)
class OpenSemanticCriterion:
    criterion_id: str
    operator_name: str
    typed_arguments: tuple[tuple[str, Any], ...]
    source_refs: tuple[str, ...]
    policy: CriterionPolicy

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.operator_name.strip():
            raise ValueError("open semantic criterion requires stable identity")
        if not self.source_refs:
            raise ValueError("open semantic criterion must remain source-bound")
        object.__setattr__(
            self,
            "typed_arguments",
            tuple((key, freeze_json(value)) for key, value in self.typed_arguments),
        )


CriterionExpr: TypeAlias = PredicateExpr | AllOf | AnyOf | Not | OpenSemanticCriterion


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    description: str
    mandatory: bool = True


@dataclass(frozen=True)
class EvidenceRequirement:
    requirement_id: str
    description: str
    mandatory: bool = True


@dataclass(frozen=True)
class CriterionEvidenceLink:
    criterion_id: str
    evidence_id: str
    requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class RejectedEvidence:
    evidence_id: str
    reason: str


@dataclass(frozen=True)
class CriteriaEvidenceMatchReport:
    passed: bool
    links: tuple[CriterionEvidenceLink, ...] = ()
    matched_criterion_ids: tuple[str, ...] = ()
    unmatched_criterion_ids: tuple[str, ...] = ()
    matched_requirement_ids: tuple[str, ...] = ()
    unmatched_requirement_ids: tuple[str, ...] = ()
    rejected_evidence: tuple[RejectedEvidence, ...] = ()
    reason: str = ""

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(link.evidence_id for link in self.links))


@dataclass(frozen=True)
class SubgoalVerificationReport:
    subgoal_id: str
    match: CriteriaEvidenceMatchReport

    @property
    def passed(self) -> bool:
        return self.match.passed


@dataclass(frozen=True)
class SkillStepVerificationReport:
    skill_id: str
    skill_version: str
    step_id: str
    match: CriteriaEvidenceMatchReport

    @property
    def passed(self) -> bool:
        return self.match.passed


def criterion_id(owner_kind: str, owner_id: str, index: int) -> str:
    """Return the stable identity a verifier must explicitly claim."""

    return f"{owner_kind}:{owner_id}:criterion:{index}"


def evidence_requirement_id(owner_kind: str, owner_id: str, index: int) -> str:
    """Return the stable identity of an independent-evidence requirement."""

    return f"{owner_kind}:{owner_id}:evidence-requirement:{index}"


def skill_step_owner_id(skill_id: str, skill_version: str, step_id: str) -> str:
    return f"{skill_id}@{skill_version}:{step_id}"


def criteria_from_descriptions(
    owner_kind: str,
    owner_id: str,
    descriptions: Iterable[str],
) -> tuple[Criterion, ...]:
    return tuple(
        Criterion(criterion_id(owner_kind, owner_id, index), description)
        for index, description in enumerate(descriptions)
    )


def evidence_requirements_from_descriptions(
    owner_kind: str,
    owner_id: str,
    descriptions: Iterable[str],
) -> tuple[EvidenceRequirement, ...]:
    return tuple(
        EvidenceRequirement(
            evidence_requirement_id(owner_kind, owner_id, index),
            description,
        )
        for index, description in enumerate(descriptions)
    )


@dataclass(frozen=True)
class CriteriaEvidenceMatcher:
    """Match explicit strong evidence links at the current observation epoch."""

    def match(
        self,
        *,
        criteria: tuple[Criterion, ...],
        requirements: tuple[EvidenceRequirement, ...],
        verification: VerificationReport,
        observation: Observation,
    ) -> CriteriaEvidenceMatchReport:
        mandatory_criteria = {item.criterion_id for item in criteria if item.mandatory}
        mandatory_requirements = {item.requirement_id for item in requirements if item.mandatory}
        if not mandatory_criteria or not mandatory_requirements:
            return CriteriaEvidenceMatchReport(
                False,
                unmatched_criterion_ids=tuple(sorted(mandatory_criteria)),
                unmatched_requirement_ids=tuple(sorted(mandatory_requirements)),
                reason="progress requires mandatory criteria and evidence requirements",
            )
        if not verification.passed:
            return CriteriaEvidenceMatchReport(
                False,
                unmatched_criterion_ids=tuple(sorted(mandatory_criteria)),
                unmatched_requirement_ids=tuple(sorted(mandatory_requirements)),
                reason=f"verification report is {verification.status.value}",
            )

        links: list[CriterionEvidenceLink] = []
        rejected: list[RejectedEvidence] = []
        for evidence in verification.evidence:
            rejection = _evidence_rejection(evidence, observation)
            if rejection:
                rejected.append(RejectedEvidence(evidence.evidence_id, rejection))
                continue
            linked_criteria = mandatory_criteria.intersection(evidence.criterion_ids)
            linked_requirements = mandatory_requirements.intersection(evidence.requirement_ids)
            if not linked_criteria or not linked_requirements:
                rejected.append(
                    RejectedEvidence(
                        evidence.evidence_id,
                        "evidence has no explicit link to an active mandatory criterion and requirement",
                    )
                )
                continue
            requirement_ids = tuple(sorted(linked_requirements))
            links.extend(
                CriterionEvidenceLink(criterion, evidence.evidence_id, requirement_ids)
                for criterion in sorted(linked_criteria)
            )

        matched_criteria = {link.criterion_id for link in links}
        matched_requirements = {requirement_id for link in links for requirement_id in link.requirement_ids}
        unmatched_criteria = mandatory_criteria - matched_criteria
        unmatched_requirements = mandatory_requirements - matched_requirements
        passed = not unmatched_criteria and not unmatched_requirements
        return CriteriaEvidenceMatchReport(
            passed,
            links=tuple(links),
            matched_criterion_ids=tuple(sorted(matched_criteria)),
            unmatched_criterion_ids=tuple(sorted(unmatched_criteria)),
            matched_requirement_ids=tuple(sorted(matched_requirements)),
            unmatched_requirement_ids=tuple(sorted(unmatched_requirements)),
            rejected_evidence=tuple(rejected),
            reason=(
                "all mandatory criteria and evidence requirements matched"
                if passed
                else "mandatory progress evidence is incomplete"
            ),
        )


def _evidence_rejection(
    evidence: VerificationEvidence,
    observation: Observation,
) -> str:
    if not evidence.passed:
        return "verifier evidence did not pass"
    if evidence.source in {"execution_receipt", "receipt"} or evidence.strength != EvidenceStrength.STRONG:
        return "evidence is weak and not independent of execution"
    if not evidence.evidence_id:
        return "evidence identity is missing"
    if evidence.environment_revision != observation.environment_revision:
        return "evidence environment revision is stale"
    if not evidence.snapshot_id or evidence.snapshot_id != observation.snapshot_id:
        return "evidence observation snapshot is stale"
    return ""

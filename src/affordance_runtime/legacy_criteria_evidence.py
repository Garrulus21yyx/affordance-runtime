"""Compatibility-only matcher for the pre-P2 VerificationReport path.

Accepted TaskSkills still use this one-way edge.  It expires with the remaining
legacy completion interfaces at P5-4 and is intentionally separate from the
pure canonical criterion AST.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.verification.mechanical import VerificationEvidence, VerificationReport


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
class SkillStepVerificationReport:
    skill_id: str
    skill_version: str
    step_id: str
    match: CriteriaEvidenceMatchReport

    @property
    def passed(self) -> bool:
        return self.match.passed


def criteria_from_descriptions(
    owner_kind: str, owner_id: str, descriptions: Iterable[str]
) -> tuple[Criterion, ...]:
    return tuple(
        Criterion(criterion_id(owner_kind, owner_id, index), description)
        for index, description in enumerate(descriptions)
    )


def evidence_requirements_from_descriptions(
    owner_kind: str, owner_id: str, descriptions: Iterable[str]
) -> tuple[EvidenceRequirement, ...]:
    return tuple(
        EvidenceRequirement(
            evidence_requirement_id(owner_kind, owner_id, index), description
        )
        for index, description in enumerate(descriptions)
    )


@dataclass(frozen=True)
class CriteriaEvidenceMatcher:
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
        matched_requirements = {
            requirement_id for link in links for requirement_id in link.requirement_ids
        }
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


def _evidence_rejection(evidence: VerificationEvidence, observation: Observation) -> str:
    if not evidence.passed:
        return "verifier evidence did not pass"
    if evidence.source in {"execution_receipt", "receipt"} or evidence.strength != "strong":
        return "evidence is weak and not independent of execution"
    if not evidence.evidence_id:
        return "evidence identity is missing"
    if evidence.environment_revision != observation.environment_revision:
        return "evidence environment revision is stale"
    if not evidence.snapshot_id or evidence.snapshot_id != observation.snapshot_id:
        return "evidence observation snapshot is stale"
    return ""

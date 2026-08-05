"""Canonical evidence projections used by the Runtime coordinator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from affordance_runtime.contracts import ActionContract
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import (
    EvidenceSourceKind,
    PredicateEvidence,
)
from affordance_runtime.verification.mechanical import VerificationReport, VerificationStatus

if TYPE_CHECKING:
    from affordance_runtime.planning import PlannerProposal


def action_progress_signature(
    proposal: PlannerProposal | None,
    contract: ActionContract,
) -> str:
    """Return the canonical semantic identity used by progress guards."""

    if proposal is not None:
        payload: dict[str, Any] = {
            "action_kind": proposal.action_kind.value,
            "target": proposal.target_affordance_id,
            "parameters": proposal.parameters,
        }
        if proposal.subgoal:
            payload["subgoal"] = proposal.subgoal
        if proposal.destination_affordance_id:
            payload["destination"] = proposal.destination_affordance_id
    else:
        payload = {
            "action_kind": contract.action,
            "target": contract.locator.get("backend_handle") or contract.affordance_id,
            "parameters": contract.parameters,
        }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def verification_satisfies_effect(report: VerificationReport) -> bool:
    if not report.passed:
        return False
    return not any(
        item.verifier_kind == "control_state"
        and isinstance(item.expected, dict)
        and "changed_from" in item.expected
        for item in report.evidence
    )


def verification_confirms_effect_absent(report: VerificationReport) -> bool:
    return (
        report.status == VerificationStatus.FAILED
        and bool(report.evidence)
        and any(
            not item.passed and item.strength == "strong" for item in report.evidence
        )
    )


def semantic_progress_fingerprint(state: Any) -> str:
    progress = {
        "completed_steps": (
            list(state.task_progress.completed_step_ids)
            if state.task_progress is not None
            else []
        ),
        "satisfied_effects": [
            f"{item.key.action_kind}:{item.key.target_id}:{item.key.parameter_digest}"
            for item in state.recent_action_outcomes.records
            if item.verification_passed and item.effect_satisfied
        ],
    }
    return json.dumps(progress, sort_keys=True, separators=(",", ":"))


def semantic_target_descriptor(
    snapshot: UnifiedObservation,
    semantic_target_id: str,
) -> dict[str, str] | None:
    if not semantic_target_id:
        return None
    target = next(
        (
            item
            for item in snapshot.targets
            if item.target_id == semantic_target_id
        ),
        None,
    )
    if target is None:
        return None
    return {
        "semantic_target_id": target.target_id,
        "role": target.role,
        "label": target.label,
    }


@dataclass(frozen=True)
class CurrentObservationEvidence:
    """A ref to one current epoch fact; replacement invalidates it."""

    evidence_ref: str
    observation_ref: str
    criterion_id: str

    def current_at(self, observation_ref: str) -> bool:
        return bool(observation_ref and self.observation_ref == observation_ref)


@dataclass(frozen=True)
class RecentActionOutcomeEvidence:
    outcome_id: str
    contract_id: str
    receipt_ref: str
    pre_observation_ref: str
    post_observation_ref: str
    effect_criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    effect_satisfied: bool

    def __post_init__(self) -> None:
        required = (
            self.outcome_id,
            self.contract_id,
            self.receipt_ref,
            self.pre_observation_ref,
            self.post_observation_ref,
        )
        if not all(item.strip() for item in required):
            raise ValueError("recent action outcome requires complete causal lineage")
        if self.effect_satisfied and (
            not self.effect_criterion_ids or not self.evidence_refs
        ):
            raise ValueError("satisfied action outcome requires effect evidence")

    @classmethod
    def from_action_outcome(cls, outcome: Any) -> RecentActionOutcomeEvidence:
        criterion_ids = tuple(outcome.verification.verified_criterion_ids)
        evidence_refs = tuple(outcome.verification.evidence_refs)
        return cls(
            outcome_id=outcome.outcome_id,
            contract_id=outcome.attempt.contract_id,
            receipt_ref=(
                f"receipt:{outcome.receipt_contract_id}"
                if outcome.receipt_contract_id
                else ""
            ),
            pre_observation_ref=outcome.attempt.pre_observation.snapshot_id,
            post_observation_ref=outcome.verification.post_observation.snapshot_id,
            effect_criterion_ids=criterion_ids,
            evidence_refs=evidence_refs,
            effect_satisfied=bool(
                outcome.status.value == "verified_effect"
                and criterion_ids
                and evidence_refs
            ),
        )

    def proves_action_caused(
        self,
        *,
        criterion_id: str,
        contract_id: str,
        current_observation_ref: str,
    ) -> bool:
        return bool(
            self.effect_satisfied
            and self.contract_id == contract_id
            and self.post_observation_ref == current_observation_ref
            and criterion_id in self.effect_criterion_ids
            and self.evidence_refs
        )


@dataclass
class RecentActionOutcomeEvidenceIndex:
    capacity: int = 40
    records: list[RecentActionOutcomeEvidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("recent action outcome capacity must be positive")
        self.records = self.records[-self.capacity :]

    def append(self, record: RecentActionOutcomeEvidence) -> None:
        self.records.append(record)
        if len(self.records) > self.capacity:
            del self.records[: len(self.records) - self.capacity]


_DURABLE_SOURCE_KINDS = frozenset(
    {
        EvidenceSourceKind.ARTIFACT_INTEGRITY,
        EvidenceSourceKind.API_STATE,
        EvidenceSourceKind.WOT_PROPERTY_STATE,
        EvidenceSourceKind.DEVICE_STATE,
        EvidenceSourceKind.NETWORK_TRANSACTION,
        EvidenceSourceKind.HUMAN_CONFIRMATION,
    }
)


@dataclass
class DurableEvidenceStore:
    capacity: int = 64
    records: list[PredicateEvidence] = field(default_factory=list)

    def admit(self, evidence: PredicateEvidence) -> bool:
        if not evidence.durable or evidence.source_kind not in _DURABLE_SOURCE_KINDS:
            return False
        self.records = [
            item for item in self.records if item.evidence_ref != evidence.evidence_ref
        ]
        self.records.append(evidence)
        if len(self.records) > self.capacity:
            del self.records[: len(self.records) - self.capacity]
        return True

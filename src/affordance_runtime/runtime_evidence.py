"""Canonical evidence projections used by the Runtime coordinator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from affordance_runtime.contracts import ActionContract, RiskLevel
from affordance_runtime.immutable import freeze_json
from affordance_runtime.simplified_runtime_contracts import (
    EffectSettlementStatus,
    ExecutionAttempt,
)
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
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
        item.verifier_kind == "control_state" and isinstance(item.expected, dict) and "changed_from" in item.expected
        for item in report.evidence
    )


def verification_confirms_effect_absent(
    report: VerificationReport,
    contract: ActionContract | None = None,
    attempt: ExecutionAttempt | None = None,
) -> bool:
    required_strength = (
        "authoritative"
        if contract is not None and contract.risk in {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE}
        else "strong"
    )
    admitted_strengths = {"authoritative"} if required_strength == "authoritative" else {"strong", "authoritative"}
    high_risk = required_strength == "authoritative"
    return (
        report.status == VerificationStatus.FAILED
        and bool(report.evidence)
        and any(
            not item.passed
            and item.strength in admitted_strengths
            and (not high_risk or _evidence_binds_attempt(item, attempt))
            for item in report.evidence
        )
    )


def effect_settlement_status(
    report: VerificationReport,
    contract: ActionContract,
    attempt: ExecutionAttempt,
    *,
    uncertain_transport: bool = False,
) -> EffectSettlementStatus:
    effect_evidence = tuple(
        item
        for item in report.evidence
        if item.passed and item.source != "execution_receipt"
    )
    signature = contract.runtime_effect_signature
    external_effect = bool(
        signature is not None
        and getattr(getattr(signature, "externality", None), "value", "local") != "local"
    )
    high_risk = contract.risk in {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE}
    occurred_is_proven = bool(effect_evidence) and (
        not (high_risk or external_effect or uncertain_transport)
        or any(
            item.strength == "authoritative" and _evidence_binds_attempt(item, attempt)
            for item in effect_evidence
        )
    )
    if report.passed and occurred_is_proven:
        return EffectSettlementStatus.OCCURRED
    if verification_confirms_effect_absent(report, contract, attempt):
        return EffectSettlementStatus.NOT_OCCURRED
    return EffectSettlementStatus.STILL_UNCERTAIN


def _evidence_binds_attempt(item: object, attempt: ExecutionAttempt | None) -> bool:
    if attempt is None:
        return False
    admitted = {
        attempt.attempt_id,
        attempt.transaction_identity,
        attempt.idempotency_identity,
        attempt.contract_hash,
    } - {""}
    return any(
        str(getattr(item, field, "")) in admitted for field in ("semantic_evidence_key", "evidence_id", "target")
    )


def semantic_progress_fingerprint(state: Any) -> str:
    progress = {
        "completed_steps": (list(state.task_progress.completed_step_ids) if state.task_progress is not None else []),
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
        (item for item in snapshot.targets if item.target_id == semantic_target_id),
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
    facts: tuple[RecentActionFact, ...] = ()

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
        if self.effect_satisfied and (not self.effect_criterion_ids or not self.evidence_refs or not self.facts):
            raise ValueError("satisfied action outcome requires lossless effect facts")

    @classmethod
    def from_action_outcome(cls, outcome: Any) -> RecentActionOutcomeEvidence:
        criterion_ids = tuple(outcome.verification.verified_criterion_ids)
        evidence_refs = tuple(outcome.verification.evidence_refs)
        facts = tuple(
            RecentActionFact(
                subject_ref=delta.subject_id,
                before_value=delta.before_value,
                after_value=delta.after_value,
                source_kind=EvidenceSourceKind(delta.source_kind),
                assurance=AssuranceLevel(delta.assurance),
                effect_criterion_ids=delta.criterion_ids,
                evidence_refs=delta.evidence_refs,
                state_delta_id=(f"delta:{outcome.outcome_id}:{index}:{delta.subject_id}"),
            )
            for index, delta in enumerate(outcome.verification.state_deltas)
        )
        return cls(
            outcome_id=outcome.outcome_id,
            contract_id=outcome.attempt.contract_id,
            receipt_ref=(f"receipt:{outcome.receipt_contract_id}" if outcome.receipt_contract_id else ""),
            pre_observation_ref=outcome.attempt.pre_observation.snapshot_id,
            post_observation_ref=outcome.verification.post_observation.snapshot_id,
            effect_criterion_ids=criterion_ids,
            evidence_refs=evidence_refs,
            effect_satisfied=bool(
                outcome.status.value == "verified_effect" and criterion_ids and evidence_refs and facts
            ),
            facts=facts,
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
            and any(criterion_id in fact.effect_criterion_ids for fact in self.facts)
        )


@dataclass(frozen=True)
class RecentActionFact:
    subject_ref: str
    before_value: object | None
    after_value: object | None
    source_kind: EvidenceSourceKind
    assurance: AssuranceLevel
    effect_criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    state_delta_id: str

    def __post_init__(self) -> None:
        if not self.subject_ref.strip() or not self.state_delta_id.strip():
            raise ValueError("recent action fact requires subject and delta identity")
        object.__setattr__(self, "before_value", freeze_json(self.before_value))
        object.__setattr__(self, "after_value", freeze_json(self.after_value))
        object.__setattr__(self, "effect_criterion_ids", tuple(self.effect_criterion_ids))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if not self.effect_criterion_ids or not self.evidence_refs:
            raise ValueError("recent action fact requires criterion and evidence identity")


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
        self.records = [item for item in self.records if item.evidence_ref != evidence.evidence_ref]
        self.records.append(evidence)
        if len(self.records) > self.capacity:
            del self.records[: len(self.records) - self.capacity]
        return True


def observation_predicate_evidence(
    observation: UnifiedObservation,
) -> tuple[PredicateEvidence, ...]:
    """Return evidence admitted through the explicit typed capture channel."""

    return observation.predicate_evidence


def canonical_resource_versions(
    observation: UnifiedObservation,
) -> tuple[tuple[str, str], ...]:
    """Version canonical targets/facts without trusting observation metadata."""

    versions: dict[str, str] = {}
    for target in observation.targets:
        state_facts = tuple(getattr(target, "state_facts", ()))
        direct_state = dict(getattr(target, "state", {})) if not state_facts else {}
        target_payload = {
            "target_id": target.target_id,
            "facts": (
                [
                    {
                        "property": fact.property_name,
                        "status": fact.status.value,
                        "value": fact.value,
                        "sources": fact.source_values,
                    }
                    for fact in state_facts
                ]
                if state_facts
                else [{"property": key, "value": value} for key, value in sorted(direct_state.items())]
            ),
        }
        versions[target.target_id] = _resource_version(target_payload)
        for fact in state_facts:
            versions[f"{target.target_id}:{fact.property_name}"] = _resource_version(
                {
                    "target_id": target.target_id,
                    "property": fact.property_name,
                    "status": fact.status.value,
                    "value": fact.value,
                    "sources": fact.source_values,
                }
            )
        for property_name, value in direct_state.items():
            versions[f"{target.target_id}:{property_name}"] = _resource_version(
                {"target_id": target.target_id, "property": property_name, "value": value}
            )
    return tuple(sorted(versions.items()))


def _resource_version(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


def admit_observation_durable_evidence(
    observation: UnifiedObservation,
    store: DurableEvidenceStore,
) -> tuple[PredicateEvidence, ...]:
    """Admit only explicitly typed durable facts from a canonical epoch."""

    admitted: list[PredicateEvidence] = []
    for evidence in observation_predicate_evidence(observation):
        if store.admit(evidence):
            admitted.append(evidence)
    return tuple(admitted)

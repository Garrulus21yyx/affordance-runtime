"""Neutral typed contracts for loop and task-completion evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.immutable import freeze_json


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CriterionStatus(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"
    STALE = "stale"
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class SatisfactionMode(StrEnum):
    STATE_HOLDS = "state_holds"
    ACTION_CAUSED = "action_caused"


class EvidenceValidityMode(StrEnum):
    CURRENT_OBSERVATION = "current_observation"
    DURABLE = "durable"
    FINAL_RECHECK = "final_recheck"


class AssuranceLevel(StrEnum):
    WEAK = "weak"
    STRUCTURAL = "structural"
    AUTHORITATIVE = "authoritative"


class EvidenceSourceKind(StrEnum):
    DOM_STATE = "dom_state"
    ACCESSIBILITY_STATE = "accessibility_state"
    VISUAL_STATE = "visual_state"
    SVG_GEOMETRY = "svg_geometry"
    WOT_DESCRIPTION = "wot_description"
    WOT_PROPERTY_STATE = "wot_property_state"
    API_STATE = "api_state"
    DEVICE_STATE = "device_state"
    WOT_ACTION_RESULT = "wot_action_result"
    NETWORK_TRANSACTION = "network_transaction"
    ARTIFACT_INTEGRITY = "artifact_integrity"
    FILE_RECEIPT = "file_receipt"
    DOWNLOAD_RECEIPT = "download_receipt"
    MODEL_SEMANTIC = "model_semantic"
    HUMAN_CONFIRMATION = "human_confirmation"


@dataclass(frozen=True)
class CriterionPolicy:
    satisfaction: SatisfactionMode = SatisfactionMode.STATE_HOLDS
    validity: EvidenceValidityMode = EvidenceValidityMode.CURRENT_OBSERVATION
    minimum_assurance: AssuranceLevel = AssuranceLevel.STRUCTURAL
    allowed_source_kinds: tuple[EvidenceSourceKind, ...] = ()
    causal_lineage_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_source_kinds", tuple(self.allowed_source_kinds))
        if self.satisfaction == SatisfactionMode.ACTION_CAUSED and not self.causal_lineage_required:
            raise ValueError("ACTION_CAUSED policy requires causal lineage")


@dataclass(frozen=True)
class PredicateEvidence:
    evidence_ref: str
    subject_ref: str
    observed_value: Any
    source_kind: EvidenceSourceKind
    assurance: AssuranceLevel
    observation_ref: str = ""
    contract_id: str = ""
    receipt_ref: str = ""
    pre_observation_ref: str = ""
    post_observation_ref: str = ""
    effect_criterion_ids: tuple[str, ...] = ()
    durable: bool = False
    authoritative_final_recheck: bool = False
    conflict: bool = False
    error_code: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_ref.strip() or not self.subject_ref.strip():
            raise ValueError("predicate evidence requires identity and subject")
        object.__setattr__(self, "observed_value", freeze_json(self.observed_value))
        object.__setattr__(self, "effect_criterion_ids", tuple(self.effect_criterion_ids))


@dataclass(frozen=True)
class PredicateEvidenceContext:
    current_observation_ref: str
    evidence: tuple[PredicateEvidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))


class SuccessExpression(_FrozenModel):
    """One recursively typed TaskSpec.success expression node."""

    expression_id: str = Field(min_length=1)
    operator: Literal["criterion", "all_of", "any_of", "not"]
    criterion_id: str = ""
    children: tuple[SuccessExpression, ...] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> SuccessExpression:
        if self.operator == "criterion":
            if not self.criterion_id:
                raise ValueError("criterion expression requires criterion_id")
            if self.children:
                raise ValueError("criterion expression cannot have children")
            return self
        if self.criterion_id:
            raise ValueError("composite expression cannot carry criterion_id")
        if self.operator == "not":
            if len(self.children) != 1:
                raise ValueError("not expression requires exactly one child")
        elif not self.children:
            raise ValueError("composite expression requires children")
        child_ids = tuple(item.expression_id for item in self.children)
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("success expression child identities must be unique")
        if self.expression_id in child_ids:
            raise ValueError("success expression cannot contain itself")
        return self


class OutputSpec(_FrozenModel):
    output_id: str = Field(min_length=1)
    materialization_criterion_id: str = Field(min_length=1)
    result_key: str = ""
    source_binding_required: bool = True


@dataclass(frozen=True)
class EvidenceMetadata:
    evidence_ref: str
    source_kind: str
    assurance: str
    observation_ref: str = ""
    contract_id: str = ""
    authoritative_final_recheck: bool = False
    source_binding_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_binding_refs", tuple(self.source_binding_refs))


@dataclass(frozen=True)
class CriterionEvaluation:
    criterion_id: str
    status: CriterionStatus
    observed_value: Any = None
    evidence_refs: tuple[str, ...] = ()
    missing_source_kinds: tuple[str, ...] = ()
    evaluated_at_observation_ref: str = ""
    reason_code: str = ""
    authoritative_final_recheck: bool = False

    def __post_init__(self) -> None:
        if not self.criterion_id:
            raise ValueError("criterion evaluation requires criterion_id")
        object.__setattr__(self, "observed_value", freeze_json(self.observed_value))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "missing_source_kinds", tuple(self.missing_source_kinds))


@dataclass(frozen=True)
class OutputMaterializationEvaluation:
    output_id: str
    status: CriterionStatus
    materialization_criterion_id: str
    evidence_refs: tuple[str, ...] = ()
    source_binding_refs: tuple[str, ...] = ()
    reason_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "source_binding_refs", tuple(self.source_binding_refs))


@dataclass(frozen=True)
class TaskCompletionEvaluation:
    status: CriterionStatus
    root_criterion_id: str
    criterion_results: tuple[CriterionEvaluation, ...] = ()
    required_output_results: tuple[OutputMaterializationEvaluation, ...] = ()
    missing_required_outputs: tuple[str, ...] = ()
    missing_rechecks: tuple[str, ...] = ()
    constraint_violations: tuple[str, ...] = ()
    uncertain_external_effects: tuple[str, ...] = ()
    result_payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_results", tuple(self.criterion_results))
        object.__setattr__(self, "required_output_results", tuple(self.required_output_results))
        object.__setattr__(self, "missing_required_outputs", tuple(self.missing_required_outputs))
        object.__setattr__(self, "missing_rechecks", tuple(self.missing_rechecks))
        object.__setattr__(self, "constraint_violations", tuple(self.constraint_violations))
        object.__setattr__(self, "uncertain_external_effects", tuple(self.uncertain_external_effects))
        object.__setattr__(self, "result_payload", freeze_json(dict(self.result_payload)))

    @property
    def completed(self) -> bool:
        return self.status == CriterionStatus.SATISFIED


class ObservationDisposition(StrEnum):
    REUSE = "reuse"
    AUGMENT_TARGETED = "augment_targeted"
    RECAPTURE = "recapture"
    WAIT_AND_RECAPTURE = "wait_and_recapture"


@dataclass(frozen=True)
class ObservationContinuation:
    disposition: ObservationDisposition
    observation_ref: str
    reason_code: str


@dataclass(frozen=True)
class DurableEvidenceRecord:
    evidence_ref: str
    criterion_ids: tuple[str, ...]
    metadata: EvidenceMetadata


@dataclass(frozen=True)
class LoopEvaluation:
    action_effect: CriterionEvaluation | None = None
    step_completion: CriterionEvaluation | None = None
    task_completion: TaskCompletionEvaluation | None = None
    durable_evidence_updates: tuple[DurableEvidenceRecord, ...] = ()
    observation_continuation: ObservationContinuation | None = None
    failure: object | None = None

"""Generic complete-run accounting and immutable resume governance.

This module deliberately knows nothing about consumer-specific environments,
case taxonomies, scoring schemes, or transports. Evaluation consumers translate
their own case and stop metadata into these contracts.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluationBatchStatus(StrEnum):
    COMPLETE = "complete"
    STOPPED = "stopped"
    INCOMPLETE_RESUMABLE = "incomplete_resumable"
    INCOMPLETE_NONRESUMABLE = "incomplete_nonresumable"
    INVALIDATED = "invalidated"


class EvaluationStopCategory(StrEnum):
    SAFETY_AUTHORITY = "safety_authority"
    RESULT_INTEGRITY = "result_integrity"
    COMPARABILITY = "comparability"
    ISOLATION = "isolation"
    PROVIDER_INFRASTRUCTURE = "provider_infrastructure"
    RESOURCE = "resource"


class EvaluationRunIdentity(BaseModel):
    """Canonical identity for an immutable evaluation request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = "evaluation-run-identity-v1"
    canonical_dimensions: str
    digest: str

    @classmethod
    def from_dimensions(cls, dimensions: Mapping[str, Any]) -> EvaluationRunIdentity:
        canonical = json.dumps(
            dict(dimensions),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        digest = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        return cls(canonical_dimensions=canonical, digest=digest)

    @model_validator(mode="after")
    def validate_digest(self) -> EvaluationRunIdentity:
        expected = f"sha256:{hashlib.sha256(self.canonical_dimensions.encode('utf-8')).hexdigest()}"
        if self.digest != expected:
            raise ValueError("evaluation run identity digest mismatch")
        value = json.loads(self.canonical_dimensions)
        if not isinstance(value, dict) or not value:
            raise ValueError("evaluation run identity dimensions must be a non-empty object")
        return self

    def assert_same(self, other: EvaluationRunIdentity) -> None:
        if self.digest != other.digest or self.canonical_dimensions != other.canonical_dimensions:
            raise ValueError("evaluation run identity does not match; resume requires an exact immutable identity")


class EvaluationBatchStop(BaseModel):
    """An allowlisted batch-wide stop; ordinary case failure is not a stop."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    category: EvaluationStopCategory
    reason: str = Field(min_length=1)
    invalidates_observed_results: bool
    resume_allowed: bool

    @model_validator(mode="after")
    def validate_flags(self) -> EvaluationBatchStop:
        if self.invalidates_observed_results and self.resume_allowed:
            raise ValueError("an invalidated evaluation cannot resume into the same evidence set")
        return self


class EvaluationCaseRecord(BaseModel):
    """One scheduled case with collection, outcome, validity, and resume facts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_id: str = Field(min_length=1)
    observed: bool
    failed: bool
    runtime_failed: bool
    external_failed: bool
    invalidated: bool
    resumed: bool
    disposition: str

    @model_validator(mode="after")
    def validate_record(self) -> EvaluationCaseRecord:
        if not self.observed and (self.failed or self.runtime_failed or self.external_failed or self.resumed):
            raise ValueError("an unobserved case cannot have an outcome or resume receipt")
        if self.runtime_failed or self.external_failed:
            if not self.failed:
                raise ValueError("runtime/external failure must contribute to case failure")
        allowed = {
            "observed_passed",
            "observed_failed",
            "unobserved",
            "invalidated_observed",
            "invalidated_unobserved",
        }
        if self.disposition not in allowed:
            raise ValueError("unsupported evaluation case disposition")
        expected = (
            f"invalidated_{'observed' if self.observed else 'unobserved'}"
            if self.invalidated
            else "observed_failed"
            if self.observed and self.failed
            else "observed_passed"
            if self.observed
            else "unobserved"
        )
        if self.disposition != expected:
            raise ValueError("evaluation case disposition is inconsistent with its facts")
        return self


class EvaluationRunAudit(BaseModel):
    """Reconciled accounting for one immutable scheduled collection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = "evaluation-run-audit-v1"
    identity_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    status: EvaluationBatchStatus
    scheduled_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    runtime_failed_count: int = Field(ge=0)
    external_failed_count: int = Field(ge=0)
    unrun_count: int = Field(ge=0)
    invalidated_count: int = Field(ge=0)
    resumed_count: int = Field(ge=0)
    collection_closed: bool
    comparable: bool
    repair_selection_ready: bool
    resume_allowed: bool
    stop: EvaluationBatchStop | None = None
    cases: tuple[EvaluationCaseRecord, ...]

    @model_validator(mode="after")
    def validate_accounting(self) -> EvaluationRunAudit:
        if len(self.cases) != self.scheduled_count:
            raise ValueError("evaluation case ledger does not match scheduled count")
        if len({item.case_id for item in self.cases}) != len(self.cases):
            raise ValueError("evaluation case ledger contains duplicate case ids")
        derived = {
            "observed_count": sum(item.observed for item in self.cases),
            "failed_count": sum(item.failed for item in self.cases),
            "runtime_failed_count": sum(item.runtime_failed for item in self.cases),
            "external_failed_count": sum(item.external_failed for item in self.cases),
            "unrun_count": sum(not item.observed for item in self.cases),
            "invalidated_count": sum(item.invalidated for item in self.cases),
            "resumed_count": sum(item.resumed for item in self.cases),
        }
        for name, value in derived.items():
            if getattr(self, name) != value:
                raise ValueError(f"evaluation {name} does not match case ledger")
        if self.observed_count + self.unrun_count != self.scheduled_count:
            raise ValueError("evaluation observed and unrun counts do not reconcile")
        if self.collection_closed != (self.unrun_count == 0):
            raise ValueError("evaluation collection_closed is inconsistent")
        if self.comparable != (self.invalidated_count == 0):
            raise ValueError("evaluation comparability is inconsistent")
        expected_repair_ready = self.collection_closed and self.comparable and self.stop is None
        if self.repair_selection_ready != expected_repair_ready:
            raise ValueError("repair selection requires a closed, comparable collection")
        if self.status == EvaluationBatchStatus.COMPLETE and not self.repair_selection_ready:
            raise ValueError("complete evaluation must be closed and comparable")
        if self.status == EvaluationBatchStatus.INVALIDATED and self.invalidated_count != self.scheduled_count:
            raise ValueError("invalidated evaluation must mark every scheduled case invalid")
        if self.status == EvaluationBatchStatus.STOPPED and (
            self.stop is None or not self.collection_closed or not self.comparable
        ):
            raise ValueError("stopped evaluation requires a closed comparable ledger and a stop reason")
        if self.resume_allowed and (self.collection_closed or not self.comparable):
            raise ValueError("resume requires unrun cases in a comparable evidence set")
        return self


def build_evaluation_run_audit(
    *,
    identity: EvaluationRunIdentity,
    scheduled_case_ids: Sequence[str],
    observed_case_ids: Sequence[str],
    failed_case_ids: Sequence[str],
    runtime_failed_case_ids: Sequence[str],
    external_failed_case_ids: Sequence[str],
    resumed_case_ids: Sequence[str] = (),
    stop: EvaluationBatchStop | None = None,
    interrupted: bool = False,
) -> EvaluationRunAudit:
    schedule = tuple(scheduled_case_ids)
    if len(set(schedule)) != len(schedule):
        raise ValueError("evaluation schedule contains duplicate case ids")
    scheduled = set(schedule)
    observed = _validated_subset("observed", observed_case_ids, scheduled)
    failed = _validated_subset("failed", failed_case_ids, observed)
    runtime_failed = _validated_subset("runtime failed", runtime_failed_case_ids, failed)
    external_failed = _validated_subset("external failed", external_failed_case_ids, failed)
    resumed = _validated_subset("resumed", resumed_case_ids, observed)
    if failed != runtime_failed | external_failed:
        raise ValueError("case failure must be explained by runtime or external outcome")
    invalidate = bool(stop is not None and stop.invalidates_observed_results)
    records = tuple(
        _case_record(
            case_id,
            observed=case_id in observed,
            failed=case_id in failed,
            runtime_failed=case_id in runtime_failed,
            external_failed=case_id in external_failed,
            invalidated=invalidate,
            resumed=case_id in resumed,
        )
        for case_id in schedule
    )
    unrun_count = len(scheduled - observed)
    if invalidate:
        status = EvaluationBatchStatus.INVALIDATED
    elif unrun_count == 0 and stop is not None:
        status = EvaluationBatchStatus.STOPPED
    elif unrun_count == 0:
        status = EvaluationBatchStatus.COMPLETE
    elif interrupted or (stop is not None and stop.resume_allowed):
        status = EvaluationBatchStatus.INCOMPLETE_RESUMABLE
    else:
        status = EvaluationBatchStatus.INCOMPLETE_NONRESUMABLE
    comparable = not invalidate
    resume_allowed = bool(
        unrun_count
        and comparable
        and (interrupted or (stop is not None and stop.resume_allowed))
    )
    return EvaluationRunAudit(
        identity_digest=identity.digest,
        status=status,
        scheduled_count=len(schedule),
        observed_count=len(observed),
        failed_count=len(failed),
        runtime_failed_count=len(runtime_failed),
        external_failed_count=len(external_failed),
        unrun_count=unrun_count,
        invalidated_count=len(schedule) if invalidate else 0,
        resumed_count=len(resumed),
        collection_closed=unrun_count == 0,
        comparable=comparable,
        repair_selection_ready=unrun_count == 0 and comparable and stop is None,
        resume_allowed=resume_allowed,
        stop=stop,
        cases=records,
    )


def select_unobserved_cases_for_resume(
    *,
    stored_identity: EvaluationRunIdentity,
    requested_identity: EvaluationRunIdentity,
    audit: EvaluationRunAudit,
) -> tuple[str, ...]:
    stored_identity.assert_same(requested_identity)
    if audit.identity_digest != stored_identity.digest:
        raise ValueError("evaluation audit identity does not match stored run identity")
    if not audit.resume_allowed:
        raise ValueError("evaluation is not eligible for same-identity resume")
    return tuple(item.case_id for item in audit.cases if not item.observed)


def _validated_subset(name: str, values: Sequence[str], allowed: set[str]) -> set[str]:
    result = set(values)
    if len(result) != len(tuple(values)):
        raise ValueError(f"evaluation {name} case ids contain duplicates")
    unknown = sorted(result - allowed)
    if unknown:
        raise ValueError(f"evaluation {name} case ids are outside their allowed set: {', '.join(unknown)}")
    return result


def _case_record(
    case_id: str,
    *,
    observed: bool,
    failed: bool,
    runtime_failed: bool,
    external_failed: bool,
    invalidated: bool,
    resumed: bool,
) -> EvaluationCaseRecord:
    disposition = (
        f"invalidated_{'observed' if observed else 'unobserved'}"
        if invalidated
        else "observed_failed"
        if observed and failed
        else "observed_passed"
        if observed
        else "unobserved"
    )
    return EvaluationCaseRecord(
        case_id=case_id,
        observed=observed,
        failed=failed,
        runtime_failed=runtime_failed,
        external_failed=external_failed,
        invalidated=invalidated,
        resumed=resumed,
        disposition=disposition,
    )

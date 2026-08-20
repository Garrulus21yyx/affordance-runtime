"""Mechanical admission of a ManagerReview terminal business value."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    EvidenceBundle,
    ManagerAssessment,
    ManagerDecision,
    ManagerRequestMode,
    ManagerRoleRequest,
    ManagerRoute,
    MissionState,
)


class FinalResponseRejection(StrEnum):
    FINAL_RESPONSE_INVALID = "final_response_invalid"
    EVIDENCE_LINEAGE_INVALID = "evidence_lineage_invalid"
    ALREADY_FINALIZED = "already_finalized"


@dataclass(frozen=True)
class FinalResponseBoundaryResult:
    admitted: bool
    response: FinalResponse | None = None
    rejection_code: FinalResponseRejection | None = None
    schema_digest: str = ""
    response_digest: str = ""


@dataclass(frozen=True)
class FinalResponseBoundary:
    """Validate shape, public schema, current evidence lineage, and the send latch."""

    def admit(
        self,
        decision: ManagerDecision,
        review: ManagerRoleRequest,
        mission: MissionState,
        *,
        already_finalized: bool,
    ) -> FinalResponseBoundaryResult:
        schema_digest = _digest(review.final_response_schema)
        response_digest = _digest(decision.final_response) if decision.final_response is not None else ""
        if already_finalized:
            return _rejected(
                FinalResponseRejection.ALREADY_FINALIZED,
                schema_digest,
                response_digest,
            )
        if (
            review.mode is not ManagerRequestMode.REVIEW_AND_ROUTE
            or review.review_world is None
            or review.evidence_bundle is None
            or review.mission_state != mission
            or review.review_world.observation_id != review.evidence_bundle.observation_id
            or tuple(item.observation_id for item in review.review_world.sources)
            != review.evidence_bundle.source_observation_ids
        ):
            return _rejected(
                FinalResponseRejection.EVIDENCE_LINEAGE_INVALID,
                schema_digest,
                response_digest,
            )
        if (
            decision.route is not ManagerRoute.REQUEST_FINALIZATION
            or decision.assessment is not ManagerAssessment.SATISFIED
            or decision.final_response is None
            or not review.final_response_schema
        ):
            return _rejected(
                FinalResponseRejection.FINAL_RESPONSE_INVALID,
                schema_digest,
                response_digest,
            )
        refs = decision.final_response_evidence_refs
        if not refs and not _explicit_constant_response(
            review.final_response_schema,
            decision.final_response,
        ):
            return _rejected(
                FinalResponseRejection.EVIDENCE_LINEAGE_INVALID,
                schema_digest,
                response_digest,
            )
        allowed = set(review.allowed_evidence_refs)
        if any(
            ref not in allowed
            or not _current_public_record(review.evidence_bundle, ref)
            for ref in refs
        ):
            return _rejected(
                FinalResponseRejection.EVIDENCE_LINEAGE_INVALID,
                schema_digest,
                response_digest,
            )
        try:
            validate_value(
                to_json_compatible(decision.final_response),
                review.final_response_schema,
                path="final_response",
            )
            content = json.dumps(
                to_json_compatible(decision.final_response),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            response = FinalResponse(
                f"manager-review:{review.review_world.observation_id}",
                content,
            )
        except (TypeError, ValueError):
            return _rejected(
                FinalResponseRejection.FINAL_RESPONSE_INVALID,
                schema_digest,
                response_digest,
            )
        return FinalResponseBoundaryResult(
            True,
            response,
            schema_digest=schema_digest,
            response_digest=response_digest,
        )


def _current_public_record(bundle: EvidenceBundle, evidence_ref: str) -> bool:
    record = bundle.resolve(evidence_ref)
    return bool(
        record is not None
        and record.observation_id == bundle.observation_id
        and record.source_observation_id in set(bundle.source_observation_ids)
        and record.has_typed_source
        and bundle.source_coverages.get(record.source_observation_id, "") != "stale"
    )


def _explicit_constant_response(schema, value: object) -> bool:
    return "const" in schema and to_json_compatible(value) == to_json_compatible(schema["const"])


def _digest(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(encoded.encode()).hexdigest()}"


def _rejected(
    code: FinalResponseRejection,
    schema_digest: str,
    response_digest: str,
) -> FinalResponseBoundaryResult:
    return FinalResponseBoundaryResult(
        False,
        rejection_code=code,
        schema_digest=schema_digest,
        response_digest=response_digest,
    )

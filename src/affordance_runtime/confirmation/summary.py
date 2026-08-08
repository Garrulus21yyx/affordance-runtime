"""Human-readable semantic confirmation summaries."""

from __future__ import annotations

import uuid

from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.execution.contracts import ActionIntent
from affordance_runtime.risk.contracts import RiskAssessment


def build_confirmation_request(intent: ActionIntent, assessment: RiskAssessment) -> ConfirmationRequest:
    effects = ", ".join(assessment.semantic_effects) or "no declared effect"
    consequences = ", ".join(assessment.consequences)
    summary = (
        f"Confirm {intent.semantic_action} on {intent.target_id}. "
        f"Effects: {effects}. Risk: {assessment.risk.value}. Consequences: {consequences}."
    )
    return ConfirmationRequest(
        f"confirmation:{uuid.uuid4().hex}",
        assessment.subject_id,
        intent,
        assessment.semantic_effects,
        assessment.risk,
        assessment.consequences,
        summary,
    )

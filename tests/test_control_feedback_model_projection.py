from __future__ import annotations

from dataclasses import asdict

from affordance_runtime.agent.control_feedback import (
    ControlFeedback,
    ControlFeedbackKind,
    ControlFeedbackSource,
    NextDecisionDisposition,
    RecoveryConstraints,
)
from affordance_runtime.model_boundary.control_feedback_projection import project_control_feedback


def test_model_projection_is_public_safe_and_omits_internal_digests() -> None:
    feedback = ControlFeedback(
        ControlFeedbackKind.NO_INFORMATION_GAIN,
        "action_page_no_information_gain",
        ControlFeedbackSource.ACTION_PAGE,
        NextDecisionDisposition.CHANGE_STRATEGY,
        True,
        "target:public",
        ("actions",),
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        recovery=RecoveryConstraints(
            strategy_change_required=True,
            offered_action_ids=("action:1",),
        ),
    )

    payload = asdict(project_control_feedback(feedback))

    assert payload == {
        "kind": "no_information_gain",
        "code": "action_page_no_information_gain",
        "source": "action_page",
        "next_decision_disposition": "change_strategy",
        "strategy_transition_required": True,
        "public_subject_id": "target:public",
        "public_field_paths": ("actions",),
        "related_decision": None,
        "related_objective_operation": None,
        "violation": None,
        "semantic_effect": None,
        "recovery": {
            "must_change_fields": (),
            "repeat_previous_decision_allowed": False,
            "retry_allowed": False,
            "rollback_available": False,
            "strategy_change_required": True,
            "offered_action_ids": ("action:1",),
        },
    }
    assert not {"scope_digest", "issue_digest", "request_digest", "result_digest"} & payload.keys()

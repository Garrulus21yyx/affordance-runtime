from __future__ import annotations

from affordance_runtime.benchmarks.supervised_gui_flagship import (
    _request_factory,
    _trace_segments,
    flagship_acceptance_errors,
    flagship_profile_errors,
)


def _profile() -> dict[str, str]:
    return {
        "LLM_ACTIVE_PROFILE": "deepseek",
        "LLM_VISUAL_PROFILE": "deepseek",
        "LLM_DEEPSEEK_VISION_MODEL": "deepseek-v4-flash-vision-exp",
        "LLM_OBSERVATION_TOOL_PROFILE": "dynamic-visual.v1",
        "LLM_INTERACTION_TOOL_PROFILE": "structured-interaction.v1",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    }


def test_flagship_profile_is_explicit_and_provider_free_to_validate() -> None:
    assert flagship_profile_errors(_profile()) == ()
    assert flagship_profile_errors({}) == (
        "LLM_ACTIVE_PROFILE must equal deepseek",
        "LLM_VISUAL_PROFILE must equal deepseek",
        "LLM_DEEPSEEK_VISION_MODEL must equal deepseek-v4-flash-vision-exp",
        "LLM_OBSERVATION_TOOL_PROFILE must equal dynamic-visual.v1",
        "LLM_INTERACTION_TOOL_PROFILE must equal structured-interaction.v1",
        "LLM_PROFILE_FALLBACK_TO_LOCAL must equal false",
    )


def test_flagship_acceptance_requires_every_collaboration_segment() -> None:
    report = {
        "interaction": {"option_count": 3, "selected_option_id": "option:current"},
        "trace_segments": {
            "visual_property": [{"subject_count": 3}],
            "selected_action": {"dispatch_statuses": ["sent"]},
            "selection_confirmation": {"label": "Selected"},
        },
        "terminal_status": "done",
        "completion": {"outcome": "success", "artifact": {"title": "Selected candidate"}},
    }
    assert flagship_acceptance_errors(report) == ()

    report["trace_segments"] = {
        "visual_property": [],
        "selected_action": {"dispatch_statuses": []},
        "selection_confirmation": None,
    }
    report["completion"] = {"outcome": "success", "artifact": None}
    assert flagship_acceptance_errors(report) == (
        "missing batched three-subject visual_property evidence",
        "selected candidate GUI action was not dispatched",
        "fresh page did not expose the selected candidate",
        "final PublicArtifact was not materialized",
    )


def test_flagship_request_does_not_claim_native_evaluator_outputs() -> None:
    request = _request_factory("session", "compare candidates")

    assert request.boundary.requested_outputs == ()


def test_trace_segments_follow_refreshed_action_to_sent_receipt_and_fresh_confirmation() -> None:
    def action_turn(sequence: int, action_id: str) -> dict[str, object]:
        return {
            "sequence": sequence,
            "event": "model_turn",
            "outcome": "select_action",
            "decision": {"action_id": action_id},
            "selected_grounding": {
                "source": {"state": {"semantic_scope_label": "Field jacket"}}
            },
        }

    def action_step(sequence: int, action_id: str, status: str) -> dict[str, object]:
        receipt = (
            {
                "receipts": [
                    {
                        "result": {"dispatch_status": status},
                        "after_observation_id": "after-current",
                    }
                ]
            }
            if status == "sent"
            else {"receipts": [], "terminal_failure": {"dispatch_status": status}}
        )
        return {
            "sequence": sequence,
            "event": "step_completed",
            "result": {
                "decision": {"action_id": action_id},
                "execution_receipts": receipt,
                "feedback": "test",
            },
        }

    events = (
        action_turn(1, "stale-action"),
        action_step(2, "stale-action", "not_sent"),
        action_turn(3, "current-action"),
        action_step(4, "current-action", "sent"),
        {
            "sequence": 5,
            "event": "observation",
            "observation": {
                "observation_id": "after-current",
                "targets": [
                    {
                        "target_ref": "E4",
                        "label": "Selected",
                        "state": {"semantic_scope_label": "Field jacket"},
                    }
                ],
            },
        },
    )

    segments = _trace_segments(events, choice_title="Field jacket")

    assert segments["selected_action"]["action_id"] == "current-action"
    assert segments["selected_action"]["dispatch_statuses"] == ["not_sent", "sent"]
    assert segments["selection_confirmation"] == {
        "observation_id": "after-current",
        "target_ref": "E4",
        "label": "Selected",
        "semantic_scope_label": "Field jacket",
    }

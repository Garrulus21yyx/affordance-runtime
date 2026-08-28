from __future__ import annotations

from affordance_runtime.benchmarks.supervised_gui_flagship import (
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
        },
        "terminal_status": "done",
        "completion": {"outcome": "success", "artifact": {"title": "Selected candidate"}},
    }
    assert flagship_acceptance_errors(report) == ()

    report["trace_segments"] = {"visual_property": [], "selected_action": {"dispatch_statuses": []}}
    report["completion"] = {"outcome": "success", "artifact": None}
    assert flagship_acceptance_errors(report) == (
        "missing batched three-subject visual_property evidence",
        "selected candidate GUI action was not dispatched",
        "final PublicArtifact was not materialized",
    )

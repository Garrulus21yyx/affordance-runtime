from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.run_state import RunState

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "affordance_runtime"


def test_workspace_owns_bounded_diagnostics_and_only_explicit_working_views_are_model_visible() -> None:
    run_fields = {item.name for item in fields(RunState)}
    python_source = "\n".join(path.read_text() for path in _SRC.rglob("*.py"))

    assert "workspace" in run_fields
    assert "recent_steps" not in run_fields
    assert not (_SRC / "agent" / "context" / "episode_history.py").exists()
    for removed in (
        "EpisodeHistoryCapacityError",
        "render_episode_history",
        "can_remember_step",
        "fact_change_count",
        "max_history_serialized_bytes",
    ):
        assert removed not in python_source

    core = (_SRC / "agent" / "core_loop.py").read_text()
    binder = (_SRC / "model" / "policy" / "grounded_policy_context.py").read_text()
    bridge = (_SRC / "model" / "policy" / "pydantic_ai_bridge.py").read_text()
    assert "self.workspace_reducer.reduce(" in core
    assert "render_agent_workspace(" not in binder
    assert "render_recent_trajectory(" in binder
    assert "render_current_activities(" not in binder
    assert "message_history: tuple[object, ...]" in bridge
    assert "_compact_pydantic_history(" in bridge
    assert "SummarizingCompaction" in bridge
    assert not (_SRC / "model" / "policy" / "checkpoint_reducer.py").exists()
    assert not (_SRC / "model" / "policy" / "progress_checkpoint.py").exists()
    assert "knowledge_bootstrap" not in bridge
    assert "progress_checkpoint_reducer" not in bridge
    assert "working_facts" not in binder


def test_request_admission_is_the_only_complete_request_capacity_owner() -> None:
    admission = (_SRC / "model" / "policy" / "request_admission.py").read_text()
    binder = (_SRC / "model" / "policy" / "grounded_policy_context.py").read_text()
    envelope = (_SRC / "model" / "policy" / "canonical_provider_envelope.py").read_text()
    packer = (_SRC / "model" / "policy" / "turn_packer.py").read_text()
    other_source = "\n".join(path.read_text() for path in _SRC.rglob("*.py") if path.name != "request_admission.py")

    assert "class RequestAdmission" in admission
    assert "CanonicalProviderEnvelope" in admission
    assert "RequestAdmission().admit(envelope" in packer
    assert "class CanonicalProviderEnvelopeBinder" in envelope
    assert "component_payloads" not in admission
    assert "RequestAdmission" not in binder
    assert "estimate_model_request(" not in binder
    assert "admit_model_request(" not in binder
    assert "estimate_canonical_envelope(" not in other_source


def test_monitor_has_one_fixed_information_increment_state() -> None:
    monitor_fields = {item.name for item in fields(EpisodeMonitor)} - {"profile"}
    monitor_source = (_SRC / "agent" / "monitor.py").read_text()
    core_source = (_SRC / "agent" / "core_loop.py").read_text()

    assert monitor_fields == {
        "world_digest",
        "current_findings_digest",
        "observation_only_streak",
        "recovery_count",
        "latest_attempt_signature",
        "same_attempt_streak",
        "no_progress_count",
        "recent_transitions",
        "active_transition_cycle",
        "active_recovery",
        "recovery_epoch_counter",
    }
    for removed in (
        "EpisodeMonitorConfig",
        "route_history",
        "repeated_failure_key",
        "recovery_in_progress_key",
        "canonical_args",
    ):
        assert removed not in monitor_source
    assert "current_findings_digest(result.after_world)" in core_source
    assert "delivery_transition.information_delta" in core_source
    assert '"max_policy_decisions"' not in core_source
    assert "StandaloneRunBudget(task.loop_budget.max_turns)" in core_source
    assert '"control_stalled"' in monitor_source


def test_action_policy_is_the_only_semantic_recovery_owner() -> None:
    production = "\n".join(path.read_text() for path in _SRC.rglob("*.py"))
    policy = (_SRC / "model" / "policy" / "policy.py").read_text()
    reasoning = (_SRC / "model" / "policy" / "reasoning_policy.py").read_text()

    assert not (_SRC / "agent" / "strategy_revision.py").exists()
    assert "StrategyRevision" not in production
    assert "strategy_revision" not in production
    assert "revise_strategy" not in production
    assert "consumed_recovery_events" not in production
    assert "request = _build_request(context)" in policy
    assert "if signature and trigger is not None" in reasoning


def test_superseded_delivery_capacity_and_error_mapping_paths_are_absent() -> None:
    production = "\n".join(path.read_text() for pattern in ("*.py", "*.yaml", "*.yml") for path in _SRC.rglob(pattern))
    bridge = (_SRC / "model" / "policy" / "pydantic_ai_bridge.py").read_text()
    admission = (_SRC / "model" / "policy" / "request_admission.py").read_text()
    binder = (_SRC / "model" / "policy" / "grounded_policy_context.py").read_text()

    assert not (_SRC / "agent" / "context" / "evidence_candidate_projection.py").exists()
    assert "EvidenceCandidate" not in production
    assert "evidence_candidates" not in production
    assert "MAX_GROUNDED_WORKSPACE_BYTES" not in binder
    assert "def admit_model_request(" not in admission
    assert '_record_local_failure(error, "grounded_tool_resolution"' not in bridge
    assert "except ModelRequestCapacityError" in bridge
    assert "except GroundedToolResolutionError" in bridge
    assert "ModelFailureKind.INTERNAL_ERROR" in bridge

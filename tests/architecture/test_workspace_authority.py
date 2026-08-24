from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.run_state import RunState

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "affordance_runtime"


def test_agent_workspace_is_the_only_production_model_history_owner() -> None:
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
    assert "self.workspace_reducer.reduce(" in core
    assert "render_agent_workspace(" in binder


def test_request_admission_is_the_only_complete_request_capacity_owner() -> None:
    admission = (_SRC / "model" / "policy" / "request_admission.py").read_text()
    binder = (_SRC / "model" / "policy" / "grounded_policy_context.py").read_text()
    envelope = (_SRC / "model" / "policy" / "canonical_provider_envelope.py").read_text()
    packer = (_SRC / "model" / "policy" / "turn_packer.py").read_text()
    other_source = "\n".join(
        path.read_text()
        for path in _SRC.rglob("*.py")
        if path.name != "request_admission.py"
    )

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
        "working_facts_digest",
        "visible_public_result_digest",
        "observation_only_streak",
        "recovery_count",
        "latest_attempt_signature",
        "same_attempt_streak",
        "no_progress_count",
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
    assert "working_facts_digest(state.workspace, pending_fact)" in core_source
    assert "delivery_transition.next_store.visible_public_result_digest" in core_source
    assert '"max_policy_decisions"' in core_source
    assert '"control_stalled"' in monitor_source


def test_superseded_delivery_capacity_and_error_mapping_paths_are_absent() -> None:
    production = "\n".join(
        path.read_text()
        for pattern in ("*.py", "*.yaml", "*.yml")
        for path in _SRC.rglob(pattern)
    )
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

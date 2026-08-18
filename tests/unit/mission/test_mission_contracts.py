from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.evaluation import EvidenceMethod, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.contracts import (
    ActionOutcome,
    LocalPostconditionStatus,
    ObservedChange,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.mission import (
    AuditBoundary,
    AuditBundle,
    AuditDelta,
    AuditDeltaStatus,
    AuditorRoleRequest,
    EpisodeMonitor,
    ManagerDecision,
    ManagerRoleRequest,
    ManagerRoute,
    MissionState,
    OutcomeProposal,
    PromoteFactProposal,
    SubtaskContract,
    subtask_goal_resolution,
)
from affordance_runtime.model.mission_roles import (
    ModelBackedMissionAuditor,
    ModelBackedMissionManager,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import SemanticTarget, StateFact
from tests.support.world import fused_world


def _task() -> TaskGoal:
    return TaskGoal(
        "task:mission",
        "Find the answer and submit it.",
        allowed_effects=("external_ui_interaction",),
        requested_outputs=("final_response",),
        risk_profile=RiskProfile.LOW,
    )


def _world(value: object = "42"):
    target = SemanticTarget("target:answer", "text", "Answer", {"value": value})
    fact = StateFact("fact:obs:answer", target.target_id, "value", value, "obs")
    return fused_world("obs", (target,), (fact,), surface="browsergym")


@dataclass
class _Port:
    payload: dict[str, object]
    provider: str = "fixture"
    model: str = "fixture-model"
    endpoint_class: str = "fixture"
    last_call: object | None = None
    last_transcript: object | None = None
    messages: tuple[object, ...] = ()

    @property
    def supports_multimodal(self):
        return False

    async def generate_structured(self, messages, output_schema, config):
        del config
        self.messages = tuple(messages)
        return output_schema(**self.payload)


@dataclass
class _FailingPort(_Port):
    async def generate_structured(self, messages, output_schema, config):
        del messages, output_schema, config
        raise RuntimeError("provider down")


def test_manager_context_hides_world_screenshot_action_space_and_trajectory() -> None:
    port = _Port({"route": "blocked", "reason": "no route"})
    manager = ModelBackedMissionManager(port)

    result = asyncio.run(manager.decide(ManagerRoleRequest(_task(), MissionState.empty())))

    assert isinstance(result, ModelInvocationResult)
    payload = json.loads(port.messages[1].content)
    serialized = json.dumps(payload).casefold()
    assert result.output == ManagerDecision(ManagerRoute.BLOCKED, reason="no route")
    assert "screenshot" not in serialized
    assert "action_space" not in serialized
    assert "world" not in serialized
    assert "trajectory" not in serialized


def test_manager_route_is_closed_and_subtask_projects_to_one_goal_plan_without_compiler() -> None:
    contract = SubtaskContract("Collect the answer.", "The answer is visible.")
    decision = ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)
    resolution = subtask_goal_resolution(_task(), contract)

    assert decision.route is ManagerRoute.EXECUTE_SUBTASK
    assert len(resolution.accepted_plan.items) == 1
    item = resolution.accepted_plan.items[0]
    assert item.id == "active_subtask"
    assert item.objective == contract.objective
    assert item.done_when == contract.done_when
    assert item.depends_on == ()
    assert item.final is False
    with pytest.raises(ValueError):
        ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, contract)


def test_manager_and_auditor_return_model_invocation_result_and_failures_do_not_modify_state() -> None:
    mission = MissionState.empty()
    manager = ModelBackedMissionManager(_FailingPort({}))
    auditor = ModelBackedMissionAuditor(_FailingPort({}))
    task = _task()
    world = _world()
    bundle = AuditBundle.from_world(world)

    manager_result = asyncio.run(manager.decide(ManagerRoleRequest(task, mission)))
    auditor_result = asyncio.run(auditor.audit(AuditorRoleRequest(
        task,
        SubtaskContract("Read answer", "Answer visible"),
        mission,
        world,
        (),
        "ready_for_audit",
        (),
        bundle,
    )))

    assert isinstance(manager_result, ModelInvocationResult)
    assert isinstance(auditor_result, ModelInvocationResult)
    assert manager_result.failure is not None
    assert auditor_result.failure is not None
    assert mission == MissionState.empty()


def test_auditor_context_uses_public_world_view_evidence_and_compact_history() -> None:
    port = _Port({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port)
    world = _world("42")
    bundle = AuditBundle.from_world(world)
    history = tuple(
        AgentTurnView("selectaction", "activate", reason=f"step-{index}")
        for index in range(5)
    )

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        history,
        bundle,
    )))

    assert result.accepted
    payload = json.loads(port.messages[1].content)
    audit_world = payload["audit_world"]
    assert audit_world["targets"][0]["label"] == "Answer"
    assert audit_world["facts"][0]["subject_label"] == "Answer"
    assert audit_world["facts"][0]["evidence_ref"].startswith("fact:")
    assert payload["audit_bundle"]["evidence"][0]["evidence_ref"] == audit_world["facts"][0]["evidence_ref"]
    assert payload["episode_history"]["retained_count"] == 5
    assert len(payload["episode_history"]["recent_trajectory"]) == 4
    assert len(payload["episode_history"]["earlier_actions"]) == 1


def test_auditor_context_capacity_failure_is_typed_and_does_not_call_provider(monkeypatch) -> None:
    import affordance_runtime.model.mission_roles as roles

    port = _Port({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port)
    world = _world("42")
    monkeypatch.setattr(roles, "_AUDIT_HISTORY_BYTES", 1)

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        (AgentTurnView("selectaction", "activate", reason="large"),),
        AuditBundle.from_world(world),
    )))

    assert result.failure is not None
    assert result.failure.reason == "context_capacity"
    assert port.messages == ()


def test_new_roles_do_not_reference_adapter_last_diagnostics() -> None:
    import inspect

    import affordance_runtime.model.mission_roles as roles

    source = inspect.getsource(roles)
    assert "last_call" not in source
    assert "last_transcript" not in source
    assert "last_adapter" not in source
    assert "last_diagnostic" not in source


def test_audit_boundary_accepts_public_evidence_and_rejects_bad_lineage_value_and_version() -> None:
    mission = MissionState.empty()
    world = _world("42")
    bundle = AuditBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.kind == "fact")
    delta = AuditDelta(
        AuditDeltaStatus.AUDITED_SATISFIED,
        0,
        (OutcomeProposal("audit:answer", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "answer visible"),),
        (PromoteFactProposal("answer", record.evidence_ref, "42", "final answer"),),
    )

    accepted = AuditBoundary().accept(mission, delta, bundle)

    assert accepted.accepted is True
    assert accepted.mission_state.version == 1
    assert accepted.mission_state.accepted_facts[0].record.value == "42"
    assert AuditBoundary().accept(accepted.mission_state, delta, bundle).accepted is False
    wrong_value = AuditDelta(
        AuditDeltaStatus.AUDITED_SATISFIED,
        0,
        (OutcomeProposal("audit:wrong", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "wrong"),),
        (PromoteFactProposal("wrong", record.evidence_ref, "43", "wrong"),),
    )
    rejected = AuditBoundary().accept(mission, wrong_value, bundle)
    assert rejected.accepted is False
    assert rejected.mission_state == mission
    duplicate_delta = AuditDelta(
        AuditDeltaStatus.AUDITED_SATISFIED,
        1,
        (OutcomeProposal("audit:answer", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "answer visible"),),
    )
    duplicate = AuditBoundary().accept(accepted.mission_state, duplicate_delta, bundle)
    assert duplicate.accepted is False
    assert duplicate.reason_code == "audit_id_conflict"


def test_audit_boundary_rejects_missing_private_or_unknown_status_without_mutation() -> None:
    mission = MissionState.empty()
    bundle = AuditBundle.from_world(_world())
    unknown = AuditDelta(AuditDeltaStatus.UNKNOWN, 0, missing_evidence=("answer",))
    rejected = AuditBoundary().accept(mission, unknown, bundle)

    assert rejected.accepted is False
    assert rejected.mission_state == mission
    empty_satisfied = AuditBoundary().accept(mission, AuditDelta(AuditDeltaStatus.AUDITED_SATISFIED, 0), bundle)
    assert empty_satisfied.accepted is False
    assert empty_satisfied.reason_code == "audit_outcome_required"


def test_audit_boundary_rejects_noop_invalidations_and_duplicate_delta_outcomes() -> None:
    mission = MissionState.empty()
    world = _world("42")
    bundle = AuditBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.kind == "fact")
    duplicate = AuditDelta(
        AuditDeltaStatus.AUDITED_UNSATISFIED,
        0,
        (
            OutcomeProposal("audit:dup", AuditDeltaStatus.AUDITED_UNSATISFIED, (record.evidence_ref,), "one"),
            OutcomeProposal("audit:dup", AuditDeltaStatus.AUDITED_UNSATISFIED, (record.evidence_ref,), "two"),
        ),
    )
    invalidation_noop = AuditDelta(
        AuditDeltaStatus.AUDITED_UNSATISFIED,
        0,
        (OutcomeProposal("audit:missing", AuditDeltaStatus.AUDITED_UNSATISFIED, (record.evidence_ref,), "missing"),),
        invalidate_fact_keys=("answer",),
    )

    duplicate_result = AuditBoundary().accept(mission, duplicate, bundle)
    invalidation_result = AuditBoundary().accept(mission, invalidation_noop, bundle)

    assert duplicate_result.accepted is False
    assert duplicate_result.reason_code == "audit_id_conflict"
    assert invalidation_result.accepted is False
    assert invalidation_result.reason_code == "audit_delta_noop"


def test_audit_bundle_from_large_world_is_bounded_not_a_bare_error() -> None:
    target = SemanticTarget("target:large", "row", "Large row")
    facts = tuple(
        StateFact(f"fact:large:{index}", target.target_id, f"value_{index}", index, "obs:large")
        for index in range(140)
    )
    bundle = AuditBundle.from_world(fused_world("obs:large", (target,), facts))

    assert len(bundle.evidence_records) == 128
    assert bundle.total_evidence_count == 140
    assert bundle.truncated is True


def test_episode_monitor_mechanically_yields_repeated_unchanged_action() -> None:
    from affordance_runtime.agent import SelectAction
    from affordance_runtime.agent.context.contracts import AgentTurnView
    from affordance_runtime.agent.run_state import RunStatus, StepResult
    from affordance_runtime.benchmarks.target_loop.support import shared_task, shared_world

    task = shared_task()
    before = shared_world("dom:before", False, "dom")
    after = shared_world("dom:after", False, "dom")
    option = ActionSpaceBuilder().build(task, before).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, before, "context:test")
    execution = SimpleNamespace(
        request=request,
        result=ActionResult(request.request_id, DispatchStatus.SENT, "dom", True),
    )
    action = ActionOutcome(
        request.request_id,
        before.observation_id,
        after.observation_id,
        ObservedChange.UNCHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.NONE,
        "unchanged",
        ("artifact:dom-after:monitor",),
    )
    evaluation = TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown")
    result = StepResult(
        SelectAction("context:test", option.action_id),
        before,
        after,
        evaluation,
        RunStatus.RUNNING,
        execution,
        action_outcome=action,
        feedback="action_unchanged_change_strategy",
    )

    transition = EpisodeMonitor().evaluate(
        result,
        (
            AgentTurnView("selectaction", "activate", public_parameters={}),
            AgentTurnView("selectaction", "activate", public_parameters={}),
        ),
        after.observation_id,
    )

    assert transition.recommendation.value == "yield"
    assert transition.reason in {"stalled", "oscillation"}


def test_episode_monitor_detects_world_fingerprint_oscillation() -> None:
    from affordance_runtime.agent import SelectAction
    from affordance_runtime.agent.run_state import RunStatus, StepResult
    from affordance_runtime.benchmarks.target_loop.support import shared_task, shared_world

    task = shared_task()
    before = shared_world("obs:b", False, "dom")
    after = shared_world("obs:a", False, "dom")
    option = ActionSpaceBuilder().build(task, before).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, before, "context:test")
    execution = SimpleNamespace(
        request=request,
        result=ActionResult(request.request_id, DispatchStatus.SENT, "dom", True),
    )
    action = ActionOutcome(
        request.request_id,
        before.observation_id,
        after.observation_id,
        ObservedChange.CHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.STRUCTURAL,
        "changed back",
        ("artifact:obs-a:monitor",),
    )
    result = StepResult(
        SelectAction("context:test", option.action_id),
        before,
        after,
        TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"),
        RunStatus.RUNNING,
        execution,
        action_outcome=action,
        feedback="changed",
    )

    transition = EpisodeMonitor().evaluate(
        result,
        (
            AgentTurnView(
                "selectaction",
                "activate",
                transition={"before_world": "obs:a", "after_world": "obs:b", "observed_change": "changed"},
            ),
        ),
        "obs:a",
    )

    assert transition.recommendation.value == "yield"
    assert transition.reason == "oscillation"

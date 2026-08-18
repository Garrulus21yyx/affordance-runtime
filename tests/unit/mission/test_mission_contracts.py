from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
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


def test_new_roles_do_not_reference_adapter_last_diagnostics() -> None:
    import inspect

    import affordance_runtime.model.mission_roles as roles

    source = inspect.getsource(roles)
    assert "last_" in source
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


def test_audit_boundary_rejects_missing_private_or_unknown_status_without_mutation() -> None:
    mission = MissionState.empty()
    bundle = AuditBundle.from_world(_world())
    unknown = AuditDelta(AuditDeltaStatus.UNKNOWN, 0, missing_evidence=("answer",))
    rejected = AuditBoundary().accept(mission, unknown, bundle)

    assert rejected.accepted is False
    assert rejected.mission_state == mission


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

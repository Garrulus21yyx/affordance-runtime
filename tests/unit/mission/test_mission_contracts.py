from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from affordance_runtime.actions import ActionBinding, ActionRisk
from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.agent import LocalToolResult, SelectAction
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_state import RunStatus, StepResult
from affordance_runtime.evaluation import EvidenceMethod, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.contracts import (
    ActionOutcome,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    LocalPostconditionStatus,
    ObservedChange,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus, ExecutionOutcome
from affordance_runtime.mission import (
    AuditBoundary,
    AuditBundle,
    AuditDelta,
    AuditDeltaStatus,
    AuditorRoleRequest,
    EpisodeMonitor,
    EpisodeMonitorRecommendation,
    ManagerDecision,
    ManagerRoleRequest,
    ManagerRoute,
    MissionState,
    OutcomeProposal,
    PromoteFactProposal,
    RecoveryKind,
    SubtaskContract,
    subtask_goal_resolution,
)
from affordance_runtime.model.mission_roles import (
    ModelBackedMissionAuditor,
    ModelBackedMissionManager,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.model.policy.request_admission import ModelRequestBudget
from affordance_runtime.model.providers.port import StructuredOutputError, StructuredOutputViolation
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
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


def _evaluation(world) -> TaskEvaluation:
    return TaskEvaluation("task:mission", world.observation_id, TaskEvaluationStatus.INCOMPLETE, "not complete")


def test_episode_monitor_recovers_then_yields_repeated_local_tool_result() -> None:
    world = _world()
    evaluation = _evaluation(world)
    decision = LocalToolResult(
        "context:1",
        "inspect_world",
        {"action": "find", "query": "missing"},
        {"action": "find", "matches": (), "total_count": 0},
    )
    step = StepResult(
        decision,
        world,
        world,
        evaluation,
        RunStatus.RUNNING,
        feedback="local_tool_result",
    )
    monitor = EpisodeMonitor()

    first = monitor.evaluate(step, (), "world:digest")
    second = monitor.evaluate(step, (), "world:digest")
    third = monitor.evaluate(step, (), "world:digest")

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second.recovery_signal is not None
    assert second.recovery_signal.kind is RecoveryKind.CONTROL_STALL
    assert third.recommendation is EpisodeMonitorRecommendation.YIELD


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


@dataclass
class _RepairingPort(_Port):
    calls: int = 0

    async def generate_structured(self, messages, output_schema, config):
        self.calls += 1
        if self.calls == 1:
            raise StructuredOutputError(
                "invalid",
                violations=(StructuredOutputViolation("$", "json_invalid"),),
            )
        return await super().generate_structured(messages, output_schema, config)


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
    port = _Port({
        "status": "audited_satisfied",
        "base_mission_version": 0,
        "completed_outcomes": ({
            "audit_id": "audit:answer",
            "status": "audited_satisfied",
            "evidence_refs": ("F1",),
            "summary": "answer visible",
        },),
    })
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
    assert audit_world["format"] == "compact_ax.v1"
    assert 'text "Answer" value[F1]="42"' in audit_world["observation"]
    assert "facts" not in audit_world
    assert "artifacts" not in audit_world
    assert "audit_bundle" not in payload
    assert "F1" in payload["audit_evidence"]["visible_refs"]
    assert payload["audit_evidence"]["visible_ref_count"] == len(payload["audit_evidence"]["visible_refs"])
    assert result.output is not None
    assert result.output.completed_outcomes[0].evidence_refs == ("fact:obs:answer",)
    assert payload["episode_history"]["retained_count"] == 5
    assert len(payload["episode_history"]["recent_trajectory"]) == 4
    assert len(payload["episode_history"]["earlier_actions"]) == 1


def test_auditor_history_bounds_large_transition_evidence_before_provider_call() -> None:
    port = _Port({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port)
    world = _world("42")
    large_changes = tuple(
        {
            "subject_id": f"target:{index}",
            "predicate": "public.label",
            "before": "",
            "after": "Quest Lumaflex Band " * 20,
        }
        for index in range(200)
    )
    history = tuple(
        AgentTurnView(
            "selectaction",
            "activate",
            AgentHistoricalTargetView("button", f"Step {index}"),
            dispatch_status="sent",
            local_postcondition="unknown",
            transition={
                "observed_change": "changed",
                "evidence_method": "structural",
                "fact_changes": large_changes,
            },
            reason="target changed",
        )
        for index in range(8)
    )

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        history,
        AuditBundle.from_world(world),
    )))

    assert result.accepted
    payload = json.loads(port.messages[1].content)
    encoded = json.dumps(payload["episode_history"], ensure_ascii=False).encode()
    assert len(encoded) <= 16 * 1024
    assert "fact_changes" not in json.dumps(payload["episode_history"])
    assert payload["episode_history"]["recent_trajectory"][-1]["result"]["transition"]["fact_change_count"] == 200


def test_auditor_delivery_exposes_structure_text_as_public_fact_evidence() -> None:
    port = _Port({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port)
    source = SurfaceObservation(
        "obs:table",
        "browsergym",
        "rev:table",
        ObservationSourceProfile.dom(),
        structure=(
            ObservationStructureNode("n:root", "table", "data-grid", child_structure_ids=("n:row",)),
            ObservationStructureNode("n:row", "row", "#", parent_structure_id="n:root", child_structure_ids=("n:cell",)),
            ObservationStructureNode("n:cell", "gridcell", "Quest Lumaflex™ Band", parent_structure_id="n:row"),
        ),
        structure_total_count=3,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        (),
        AuditBundle.from_world(world),
    )))

    assert result.accepted
    payload = json.loads(port.messages[1].content)
    assert "facts" not in payload["audit_world"]
    assert "audit_bundle" not in payload
    refs = payload["audit_evidence"]["visible_refs"]
    assert refs
    assert any(
        f'fact.public.label[{ref}]="Quest Lumaflex™ Band"' in payload["audit_world"]["observation"]
        for ref in refs
    )


def test_auditor_context_capacity_failure_is_typed_and_does_not_call_provider() -> None:
    port = _Port({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port, request_budget=ModelRequestBudget(admission_limit=1))
    world = _world("42")

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        (),
        AuditBundle.from_world(world),
    )))

    assert result.failure is not None
    assert result.failure.kind is ModelFailureKind.CONTEXT_CAPACITY
    assert result.failure.reason == "context_capacity"
    assert result.diagnostics["role"] == "auditor"
    assert result.diagnostics["phase"] == "auditor_initial"
    assert result.diagnostics["admission_action"] == "context_capacity"
    assert result.diagnostics["provider_attempts"] == 0
    assert result.diagnostics["estimated_total_tokens"] > result.diagnostics["admission_limit"]
    assert result.diagnostics["actor_world_tokens"] > 0
    assert result.diagnostics["evidence_tokens"] > 0
    assert port.messages == ()


def test_auditor_schema_repair_diagnostics_keep_initial_and_repair_breakdowns() -> None:
    port = _RepairingPort({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port)
    world = _world("42")

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        (),
        AuditBundle.from_world(world),
    )))

    assert result.failure is None
    assert port.calls == 2
    assert result.diagnostics["provider_attempts"] == 2
    breakdowns = result.diagnostics["request_breakdowns"]
    assert [item["phase"] for item in breakdowns] == ["auditor_initial", "auditor_schema_repair"]
    assert result.diagnostics["phase"] == "auditor_schema_repair"


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
    conflict = AuditDelta(
        AuditDeltaStatus.AUDITED_SATISFIED,
        0,
        (OutcomeProposal("audit:conflict", AuditDeltaStatus.AUDITED_UNSATISFIED, (record.evidence_ref,), "conflict"),),
    )
    assert AuditBoundary().accept(mission, conflict, bundle).reason_code == "audit_status_conflict"
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

    assert len(bundle.evidence_records) == 141
    assert bundle.total_evidence_count == 141
    assert bundle.truncated is False


def test_auditor_delivery_keeps_model_visible_late_evidence_refs() -> None:
    target = SemanticTarget("target:large", "row", "Large row")
    facts = tuple(
        StateFact(f"fact:large:{index}", target.target_id, f"value_{index}", index, "obs:large")
        for index in range(140)
    )
    answer = "Quest Lumaflex Band"
    late_fact = StateFact("fact:large:answer", target.target_id, "answer", answer, "obs:large")
    world = fused_world("obs:large", (target,), (*facts, late_fact))
    port = _Port({"status": "unknown", "base_mission_version": 0})
    auditor = ModelBackedMissionAuditor(port)

    result = asyncio.run(auditor.audit(AuditorRoleRequest(
        _task(),
        SubtaskContract("Read answer", "Answer visible"),
        MissionState.empty(),
        world,
        (),
        "ready_for_audit",
        (),
        AuditBundle.from_world(world),
    )))

    assert result.accepted
    payload = json.loads(port.messages[1].content)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert answer in serialized
    assert "fact:large:answer" not in serialized
    assert "audit_bundle" not in payload
    assert payload["audit_evidence"]["visible_ref_count"] == len(payload["audit_evidence"]["visible_refs"])


def test_episode_monitor_yields_only_on_third_repeated_unchanged_action() -> None:
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

    monitor = EpisodeMonitor()
    first = monitor.evaluate(result, (), after.observation_id)
    second = monitor.evaluate(
        result,
        (AgentTurnView("selectaction", "activate", public_parameters={}),),
        after.observation_id,
    )
    transition = monitor.evaluate(
        result,
        (
            AgentTurnView("selectaction", "activate", public_parameters={}),
            AgentTurnView("selectaction", "activate", public_parameters={}),
        ),
        after.observation_id,
    )

    assert first.recommendation.value == "continue"
    assert second.recommendation.value == "recover"
    assert second.recovery_signal is not None
    assert second.recovery_signal.kind is RecoveryKind.EFFECT_STALL
    assert transition.recommendation.value == "yield"
    assert transition.reason == "effect_stall"


def test_episode_monitor_keeps_repeated_failure_streak_across_stable_incomplete_evaluation() -> None:
    from affordance_runtime.agent.run_state import RunStatus, StepResult
    from affordance_runtime.benchmarks.target_loop.support import shared_task, shared_world

    task = shared_task()
    before = shared_world("dom:before", False, "dom")
    after = shared_world("dom:after", False, "dom")
    monitor = EpisodeMonitor()

    def failure() -> StepResult:
        return StepResult(
            PolicyFailure(ModelFailureKind.SCHEMA_ERROR, "invalid provider payload"),
            before,
            after,
            TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.INCOMPLETE, "not done"),
            RunStatus.FAILED,
            feedback="policy_failure:schema_error",
        )

    first = monitor.evaluate(failure(), (), after.observation_id)
    second = monitor.evaluate(failure(), (), after.observation_id)
    third = monitor.evaluate(failure(), (), after.observation_id)

    assert first.recommendation.value == "continue"
    assert second.recommendation.value == "recover"
    assert second.recovery_signal is not None
    assert second.recovery_signal.kind is RecoveryKind.STRATEGY_STALL
    assert third.recommendation.value == "yield"
    assert third.reason == "strategy_stall"


def test_episode_monitor_keys_not_sent_failures_by_public_semantics_not_target_id() -> None:
    from affordance_runtime.agent.run_state import RunStatus, StepResult

    task = _task()
    monitor = EpisodeMonitor()

    def failure(observation_id: str, target_id: str) -> StepResult:
        target = SemanticTarget(target_id, "link", "REPORTS", {})
        binding = ActionBinding(
            f"binding:{observation_id}",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            f"fingerprint:{observation_id}",
            target.target_id,
            target.target_id,
            "browsergym",
            "browsergym",
            "activate",
            "click",
            "external_ui_interaction",
            ("external_ui_interaction",),
            {"type": "object", "properties": {}, "additionalProperties": False},
            {},
            risk=ActionRisk.LOW,
        )
        world = fused_world(observation_id, (target,), (), (binding,), surface="browsergym")
        builder = ActionSpaceBuilder()
        option = builder.build(task, world).options[0]
        request = ActionBinder().bind(builder.admit(option, {}), world, "context:test")
        execution = ExecutionOutcome(
            request,
            ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                "browsergym",
                False,
                ActionError.CURRENTNESS_UNAVAILABLE,
            ),
            None,
        )
        return StepResult(
            SelectAction("context:test", option.action_id),
            world,
            world,
            TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"),
            RunStatus.BLOCKED,
            execution=execution,
            feedback="action_not_sent:currentness_unavailable",
        )

    first = monitor.evaluate(failure("obs:one", "target:a"), (), "obs:one")
    second = monitor.evaluate(failure("obs:two", "target:b"), (), "obs:two")
    third = monitor.evaluate(failure("obs:three", "target:c"), (), "obs:three")

    assert first.recommendation.value == "continue"
    assert second.recommendation.value == "recover"
    assert second.recovery_signal is not None
    assert second.recovery_signal.kind is RecoveryKind.GROUNDING_STALL
    assert third.recommendation.value == "yield"
    assert third.reason == "grounding_stall"


def test_episode_monitor_detects_world_oscillation_with_semantic_fingerprints() -> None:
    from affordance_runtime.agent.run_state import RunStatus, StepResult
    from affordance_runtime.benchmarks.target_loop.support import shared_task, shared_world
    from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest

    task = shared_task()
    closed = shared_world("obs:closed", False, "dom")
    open_world = shared_world("obs:open", True, "dom")
    closed_fingerprint = public_world_semantic_digest(closed)
    open_fingerprint = public_world_semantic_digest(open_world)
    option = ActionSpaceBuilder().build(task, open_world).options[0]
    result = StepResult(
        SelectAction("context:test", option.action_id),
        open_world,
        closed,
        TaskEvaluation(task.task_id, closed.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"),
        RunStatus.RUNNING,
        feedback="action_changed_unknown",
    )
    recent = (
        AgentTurnView(
            "selectaction",
            "activate",
            transition={
                "before_world": "obs:older-closed",
                "after_world": "obs:older-open",
                "before_world_fingerprint": closed_fingerprint,
                "after_world_fingerprint": open_fingerprint,
            },
        ),
    )

    monitor = EpisodeMonitor()
    transition = monitor.evaluate(result, recent, closed_fingerprint)
    repeated = monitor.evaluate(result, recent, closed_fingerprint)

    assert transition.recommendation.value == "recover"
    assert transition.recovery_signal is not None
    assert transition.recovery_signal.kind is RecoveryKind.STATE_OSCILLATION
    assert repeated.recommendation.value == "yield"
    assert repeated.reason == "state_oscillation"


def test_episode_monitor_resets_failure_streak_on_incomplete_public_evaluation_change() -> None:
    from affordance_runtime.agent.run_state import RunStatus, StepResult
    from affordance_runtime.benchmarks.target_loop.support import shared_task, shared_world

    task = shared_task()
    before = shared_world("dom:before", False, "dom")
    after = shared_world("dom:after", False, "dom")
    monitor = EpisodeMonitor()

    def failure(status: CriterionEvaluationStatus) -> StepResult:
        return StepResult(
            PolicyFailure(ModelFailureKind.SCHEMA_ERROR, "invalid provider payload"),
            before,
            after,
            TaskEvaluation(
                task.task_id,
                after.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "not done",
                criteria=(CriterionEvaluation("criterion:visible", status, (), "public state"),),
            ),
            RunStatus.FAILED,
            feedback="policy_failure:schema_error",
        )

    assert monitor.evaluate(failure(CriterionEvaluationStatus.UNKNOWN), (), after.observation_id).recommendation.value == "continue"
    assert monitor.evaluate(failure(CriterionEvaluationStatus.UNKNOWN), (), after.observation_id).recommendation.value == "recover"
    reset = monitor.evaluate(failure(CriterionEvaluationStatus.UNSATISFIED), (), after.observation_id)
    assert reset.recommendation.value == "continue"
    assert monitor.repeated_failure_count == 1


def test_episode_monitor_does_not_count_repeated_successful_actions_as_stalled() -> None:
    from affordance_runtime.agent import SelectAction
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
        ObservedChange.CHANGED,
        LocalPostconditionStatus.SATISFIED,
        EvidenceMethod.STRUCTURAL,
        "changed",
        ("artifact:dom-after:monitor",),
    )
    result = StepResult(
        SelectAction("context:test", option.action_id),
        before,
        after,
        TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"),
        RunStatus.RUNNING,
        execution,
        action_outcome=action,
        feedback="action_changed",
    )
    previous = AgentTurnView(
        "selectaction",
        request.intent.semantic_action,
        AgentHistoricalTargetView("", request.intent.target_id),
        public_parameters=request.intent.parameters,
    )

    transition = EpisodeMonitor().evaluate(result, (previous, previous), after.observation_id)

    assert transition.recommendation.value == "continue"


def test_episode_monitor_resets_repeated_failure_streak_on_world_change() -> None:
    from affordance_runtime.agent.run_state import RunStatus, StepResult
    from affordance_runtime.benchmarks.target_loop.support import shared_task, shared_world

    task = shared_task()
    before = shared_world("dom:before", False, "dom")
    same = shared_world("dom:same", False, "dom")
    changed = shared_world("dom:changed", True, "dom")
    monitor = EpisodeMonitor()
    failure = StepResult(
        PolicyFailure(ModelFailureKind.SCHEMA_ERROR, "invalid provider payload"),
        before,
        same,
        TaskEvaluation(task.task_id, same.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"),
        RunStatus.FAILED,
        feedback="policy_failure:schema_error",
    )
    progress = StepResult(
        PolicyFailure(ModelFailureKind.SCHEMA_ERROR, "invalid provider payload"),
        same,
        changed,
        TaskEvaluation(task.task_id, changed.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"),
        RunStatus.FAILED,
        feedback="policy_failure:schema_error",
    )

    assert monitor.evaluate(failure, (), same.observation_id).recommendation.value == "continue"
    assert monitor.evaluate(failure, (), same.observation_id).recommendation.value == "recover"
    assert monitor.evaluate(progress, (), changed.observation_id).recommendation.value == "continue"
    assert monitor.evaluate(failure, (), same.observation_id).recommendation.value == "continue"
    assert monitor.evaluate(failure, (), same.observation_id).recommendation.value == "recover"


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

    monitor = EpisodeMonitor()
    transition = monitor.evaluate(
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
    repeated = monitor.evaluate(
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

    assert transition.recommendation.value == "recover"
    assert transition.recovery_signal is not None
    assert transition.recovery_signal.kind is RecoveryKind.STATE_OSCILLATION
    assert repeated.recommendation.value == "yield"
    assert repeated.reason == "state_oscillation"

import asyncio
import json
from pathlib import Path

import pytest

from affordance_runtime.actions import (
    INTERACTION_CAPABILITY_REGISTRY,
    ActionBinding,
    ActionRisk,
    AdmittedActionSelection,
)
from affordance_runtime.agent import (
    EpisodeYieldReason,
    PinFactResult,
    ReadRegionResult,
    RunState,
    RunStatus,
    SearchPageContentResult,
    SelectAction,
    StepResult,
    WorkingFact,
    YieldMilestone,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.execution import (
    ActionIntent,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceipt,
    ExecutionReceiptBatch,
)
from affordance_runtime.mission import (
    AcceptedWorkingOutcome,
    AuditorDecision,
    EvidenceAssessment,
    Milestone,
    MilestoneRoadmap,
    MissionOutcome,
    MissionState,
    MissionSupervisor,
    PlannerDecision,
    PlannerRequestMode,
    PlannerRoute,
)
from affordance_runtime.mission.supervisor import _roadmap_revision_preserves_accepted_semantics
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import SemanticTarget
from tests.support.world import fused_world


class Planner:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.requests = []

    async def plan(self, request):
        self.requests.append(request)
        return ModelInvocationResult(output=self.decisions.pop(0))


class Runtime:
    def __init__(self, routes, *, replan=False):
        self.routes = tuple(routes)
        self.replan = replan
        self.initializations = []
        self.continue_calls = 0
        self.episode_monitor = object()
        self.applied_routes = []
        self.planner_call_probe = lambda: -1
        self.planner_calls_during_routes = []

    async def initialize_from_world(
        self,
        task,
        initial,
        goal_resolution,
        *,
        budget,
        yield_on_budget_exhaustion,
        working_facts,
        active_milestone,
    ):
        del goal_resolution, yield_on_budget_exhaustion, working_facts
        self.initializations.append((budget.turns, active_milestone, self.routes))
        return RunState(
            initial,
            TaskEvaluation(task.task_id, initial.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
            budget.turns,
            active_milestone_contract=active_milestone,
            yield_on_budget_exhaustion=True,
        )

    async def continue_task(self, environment, task, state):
        del environment
        self.continue_calls += 1
        for index, route in enumerate(self.routes, 1):
            after_route = fused_world(
                f"episode-route-{self.continue_calls}-{index}",
                (SemanticTarget(f"route-{index}", "status", route),),
            )
            decision, receipts = _replayed_step(route, index, state.current_world.observation_id, after_route.observation_id)
            state.apply(
                StepResult(
                    decision,
                    state.current_world,
                    after_route,
                    TaskEvaluation(task.task_id, after_route.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
                    RunStatus.RUNNING,
                    execution_receipts=receipts,
                    feedback=f"provider_free_replay:{route}",
                )
            )
            self.applied_routes.append(route)
            self.planner_calls_during_routes.append(self.planner_call_probe())
        after = state.current_world
        decision = YieldMilestone(
            "context:episode",
            "needs_replan" if self.replan else "outcome_proposed",
            "route completed" if not self.replan else "route unavailable",
            reason_code="delivery_not_observable" if self.replan else None,
        )
        result = StepResult(
            decision,
            state.current_world,
            after,
            TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
            RunStatus.YIELDED,
            feedback=f"yield_milestone:{decision.yield_kind}",
            yield_reason=EpisodeYieldReason(decision.yield_kind),
        )
        state.apply(result)
        return state


class Auditor:
    def __init__(self) -> None:
        self.requests = []

    async def audit(self, request):
        self.requests.append(request)
        refs = tuple(item.record.evidence_ref for item in request.working_facts[:1]) or tuple(
            item.evidence_ref for item in request.audit_bundle.evidence_records[:1]
        )
        return ModelInvocationResult(
            output=AuditorDecision(
                EvidenceAssessment.SATISFIED,
                refs,
                reason="replay outcome visible",
            )
        )


def _replayed_step(route: str, index: int, before_id: str, after_id: str):
    local_results = {
        "search_page_content": lambda: SearchPageContentResult(
            "context:episode", route, {"query": "result"}, {"items": ({"text": "Requested result"},)}
        ),
        "read_region": lambda: ReadRegionResult(
            "context:episode", route, {"region_ref": "R1"}, {"items": ({"text": "Requested result"},)}
        ),
        "pin_fact": lambda: PinFactResult(
            "context:episode",
            route,
            {"key": "route_result", "evidence_ref": "F1"},
            {"key": "route_result", "value": "Requested result"},
            working_fact=WorkingFact(
                "route_result",
                EvidenceRecord(
                    "fact:route-result",
                    after_id,
                    "fact",
                    "provider-free",
                    source_observation_id=after_id,
                    source_modality="structural",
                    source_assurance="structural",
                    value="Requested result",
                ),
                index,
                "retain the exact route result",
            ),
        ),
    }
    if route in local_results:
        return local_results[route](), None
    semantic_action = route
    assert INTERACTION_CAPABILITY_REGISTRY.resolve(semantic_action) is not None
    schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(semantic_action)
    parameters = {
        "type_text": {"text": "provider-free replay"},
        "select_option": {"value": "provider-free replay"},
        "press_key": {"key": "Enter"},
    }.get(semantic_action, {})
    effects = ("external_ui_interaction",)
    binding = ActionBinding(
        f"binding:replay:{index}",
        before_id,
        before_id,
        f"revision:replay:{index}",
        f"fingerprint:replay:{index}",
        f"target:replay:{index}",
        f"target:replay:{index}",
        "provider-free-replay",
        "provider-free-replay",
        semantic_action,
        semantic_action,
        "local_reversible",
        effects,
        schema,
        {"route": route},
    )
    selection = AdmittedActionSelection(
        f"action:{index}",
        before_id,
        semantic_action,
        binding.target_id,
        binding.effect_category,
        effects,
        schema_digest(schema),
        (binding.binding_id,),
        ActionRisk.LOW,
        True,
        parameters,
        verification_contract_digest=binding.verification_contract_digest,
        verification_family=binding.verification_family,
    )
    request = BoundActionRequest(
        f"request:replay:{index}",
        "context:episode",
        before_id,
        ActionIntent(semantic_action, binding.target_id, parameters),
        selection,
        binding,
    )
    result = ActionResult(request.request_id, DispatchStatus.SENT, "provider-free-replay", True)
    receipt = ExecutionReceipt(request, result, before_id, after_id)
    return (
        SelectAction("context:episode", selection.action_id, parameters),
        ExecutionReceiptBatch((receipt,), ExecutionCompletion.COMPLETE),
    )


def _roadmap(outcome: str) -> MilestoneRoadmap:
    return MilestoneRoadmap(1, (Milestone("result", outcome, "The fresh result is observable"),))


def test_replan_cannot_reuse_an_accepted_id_for_different_semantics() -> None:
    before = MilestoneRoadmap(1, (Milestone("m1", "Old outcome", "Old state visible"),))
    mission = MissionState(
        1,
        (AcceptedWorkingOutcome("m1", EvidenceAssessment.SATISFIED, ("fact:proof",), "accepted"),),
    )
    changed = MilestoneRoadmap(
        2,
        (
            Milestone("m1", "New outcome", "New state visible"),
            Milestone("final", "Finish", "Finished", depends_on=("m1",), final=True),
        ),
    )
    assert not _roadmap_revision_preserves_accepted_semantics(before, changed, mission)


@pytest.mark.parametrize(
    "route",
    [
        ("activate", "select_option", "type_text", "type_text", "activate", "search_page_content", "read_region"),
        ("type_text", "type_text", "activate", "search_page_content", "read_region", "pin_fact"),
    ],
)
def test_coherent_gui_route_stays_in_one_milestone_and_intermediate_changes_do_not_call_planner(route) -> None:
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),))
    runtime = Runtime(route)
    runtime.planner_call_probe = lambda: len(planner.requests)
    environment = ScriptedEnvironment(initial_observation=fused_world("episode-before"))
    auditor = Auditor()
    result = asyncio.run(MissionSupervisor(planner, auditor).run(runtime, environment, TaskGoal("task:route", "Get result")))
    assert result.mission_state.version == 1
    assert result.planner_calls == 1
    assert runtime.continue_calls == 1
    assert runtime.initializations[0][0] == 15
    assert runtime.initializations[0][2] == route
    assert runtime.applied_routes == list(route)
    assert runtime.planner_calls_during_routes == [1] * len(route)
    assert result.step_count == len(route) + 1
    assert result.execution_count == sum(INTERACTION_CAPABILITY_REGISTRY.resolve(item) is not None for item in route)
    assert len(auditor.requests) == 1
    assert planner.requests[0].mode is PlannerRequestMode.START


def test_typed_needs_replan_invokes_planner_once_without_replaying_gui_episode() -> None:
    planner = Planner(
        (
            PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),
            PlannerDecision(PlannerRoute.BLOCKED, reason="supported route unavailable"),
        )
    )
    runtime = Runtime(("activate",), replan=True)
    environment = ScriptedEnvironment(initial_observation=fused_world("replan-before"))
    result = asyncio.run(MissionSupervisor(planner).run(runtime, environment, TaskGoal("task:replan", "Get result")))
    assert result.outcome is MissionOutcome.BLOCKED
    assert result.planner_calls == 2
    assert runtime.continue_calls == 1
    assert planner.requests[-1].mode is PlannerRequestMode.NEEDS_REPLAN


@pytest.mark.parametrize(
    ("trace_path", "expected_route"),
    [
        (
            "evidence/live/w1b-one-task-0-deepseek-v4-flash-provider-retry-run5/"
            "traces/webarena-verified-w1b-task-0/trace.jsonl",
            ("activate", "activate", "read_region", "select_option", "read_region", "type_text", "type_text", "activate"),
        ),
        (
            "evidence/live/w1b-task-7-deepseek-v4-flash-run10/"
            "traces/webarena-verified-w1b-task-7/trace.jsonl",
            ("type_text", "press_key"),
        ),
    ],
)
def test_archived_public_step_sequence_replays_inside_one_fifteen_turn_milestone(
    trace_path: str,
    expected_route: tuple[str, ...],
) -> None:
    path = Path(__file__).resolve().parents[3] / trace_path
    route = []
    for line in path.read_text().splitlines():
        event = json.loads(line)
        if event.get("event") != "step_completed":
            continue
        result_payload = event.get("result", {})
        execution = result_payload.get("execution") or {}
        semantic_action = (execution.get("request") or {}).get("intent", {}).get("semantic_action")
        if semantic_action:
            route.append(semantic_action)
            continue
        tool_name = (result_payload.get("decision") or {}).get("tool_name")
        if tool_name in {"read_region", "search_page_content", "pin_fact"}:
            route.append(tool_name)
    assert tuple(route) == expected_route
    assert len(route) <= 15

    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),))
    runtime = Runtime(tuple(route))
    runtime.planner_call_probe = lambda: len(planner.requests)
    environment = ScriptedEnvironment(initial_observation=fused_world("archived-replay-before"))
    auditor = Auditor()
    result = asyncio.run(
        MissionSupervisor(planner, auditor).run(runtime, environment, TaskGoal("task:archived-replay", "Get result"))
    )

    assert result.planner_calls == 1
    assert runtime.continue_calls == 1
    assert runtime.initializations == [(15, runtime.initializations[0][1], tuple(route))]
    assert runtime.applied_routes == route
    assert runtime.planner_calls_during_routes == [1] * len(route)
    assert result.step_count == len(route) + 1
    assert result.execution_count == sum(INTERACTION_CAPABILITY_REGISTRY.resolve(item) is not None for item in route)
    assert len(auditor.requests) == 1

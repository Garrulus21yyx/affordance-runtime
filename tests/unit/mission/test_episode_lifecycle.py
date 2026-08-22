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
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
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
    EvidenceBundle,
    EvidenceRequirement,
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
from affordance_runtime.world import SemanticTarget, StateFact
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
        del goal_resolution, yield_on_budget_exhaustion
        self.initializations.append((budget.turns, active_milestone, self.routes, tuple(working_facts)))
        return RunState(
            initial,
            TaskEvaluation(task.task_id, initial.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
            budget.turns,
            working_facts=working_facts,
            active_milestone_contract=active_milestone,
            yield_on_budget_exhaustion=True,
        )

    async def continue_task(self, environment, task, state):
        del environment
        self.continue_calls += 1
        for index, route in enumerate(self.routes, 1):
            after_route = fused_world(
                f"episode-route-{self.continue_calls}-{index}",
                (SemanticTarget(f"route-{index}", "status", f"{route}-{self.continue_calls}"),),
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


class FormalEvaluationRuntime(Runtime):
    def __init__(
        self,
        status: TaskEvaluationStatus,
        criterion_status: CriterionEvaluationStatus | None = None,
    ) -> None:
        super().__init__(())
        self.status = status
        self.criterion_status = criterion_status

    async def continue_task(self, environment, task, state):
        del environment
        self.continue_calls += 1
        record = EvidenceBundle.from_world(state.current_world).evidence_records[0]
        criteria = ()
        if self.criterion_status is not None:
            criteria = (
                CriterionEvaluation(
                    "native-result",
                    self.criterion_status,
                    (record.evidence_ref,)
                    if self.criterion_status is CriterionEvaluationStatus.SATISFIED
                    else (),
                    "native criterion result",
                ),
            )
        evaluation = TaskEvaluation(
            task.task_id,
            state.current_world.observation_id,
            self.status,
            "native evaluator result",
            criteria,
            (record.evidence_ref,) if self.status is TaskEvaluationStatus.COMPLETE else (),
        )
        decision = YieldMilestone("context:formal", "outcome_proposed", "native result available")
        state.apply(
            StepResult(
                decision,
                state.current_world,
                state.current_world,
                evaluation,
                RunStatus.YIELDED,
                feedback="yield_milestone:outcome_proposed",
                yield_reason=EpisodeYieldReason.OUTCOME_PROPOSED,
            )
        )
        return state


class UntypedLineageRuntime(Runtime):
    def __init__(self) -> None:
        super().__init__(())

    async def continue_task(self, environment, task, state):
        del environment
        self.continue_calls += 1
        after = fused_world(
            f"untyped-lineage-{self.continue_calls}",
            (SemanticTarget("result", "status", "Changed result"),),
        )
        working_fact = WorkingFact(
            "route_result",
            EvidenceRecord(
                "fact:untyped-lineage",
                after.observation_id,
                "fact",
                "provider-free",
                value="result",
            ),
            1,
            "retain the result",
        )
        state.apply(
            StepResult(
                PinFactResult(
                    "context:untyped",
                    "pin_fact",
                    {"key": "route_result", "evidence_ref": "F1"},
                    {"key": "route_result", "value": "result"},
                    working_fact=working_fact,
                ),
                state.current_world,
                after,
                TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
                RunStatus.RUNNING,
                feedback="untyped working fact",
            )
        )
        decision = YieldMilestone("context:untyped", "outcome_proposed", "result proposed")
        state.apply(
            StepResult(
                decision,
                after,
                after,
                TaskEvaluation(task.task_id, after.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
                RunStatus.YIELDED,
                feedback="yield_milestone:outcome_proposed",
                yield_reason=EpisodeYieldReason.OUTCOME_PROPOSED,
            )
        )
        return state


class AliasedWorkingFactsRuntime(Runtime):
    def __init__(self) -> None:
        super().__init__(())

    async def continue_task(self, environment, task, state):
        del environment
        self.continue_calls += 1
        record = EvidenceBundle.from_world(state.current_world).evidence_records[0]
        for index, key in enumerate(("first_result", "second_result"), 1):
            fact = WorkingFact(key, record, index, f"retain {key}")
            state.apply(
                StepResult(
                    PinFactResult(
                        "context:aliases",
                        "pin_fact",
                        {"key": key, "evidence_ref": "F1"},
                        {"key": key, "value": record.value},
                        working_fact=fact,
                    ),
                    state.current_world,
                    state.current_world,
                    TaskEvaluation(
                        task.task_id,
                        state.current_world.observation_id,
                        TaskEvaluationStatus.INCOMPLETE,
                        "ongoing",
                    ),
                    RunStatus.RUNNING,
                    feedback=f"pinned {key}",
                )
            )
        decision = YieldMilestone("context:aliases", "outcome_proposed", "aliased results proposed")
        state.apply(
            StepResult(
                decision,
                state.current_world,
                state.current_world,
                TaskEvaluation(
                    task.task_id,
                    state.current_world.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "ongoing",
                ),
                RunStatus.YIELDED,
                feedback="yield_milestone:outcome_proposed",
                yield_reason=EpisodeYieldReason.OUTCOME_PROPOSED,
            )
        )
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
                guidance="replay outcome visible",
            )
        )


class SequenceAuditor(Auditor):
    def __init__(self, decisions) -> None:
        super().__init__()
        self.decisions = list(decisions)

    async def audit(self, request):
        self.requests.append(request)
        decision = self.decisions.pop(0)
        if isinstance(decision, ModelFailure):
            return ModelInvocationResult(failure=decision)
        refs = tuple(item.record.evidence_ref for item in request.working_facts[:1]) or tuple(
            item.evidence_ref for item in request.audit_bundle.evidence_records[:1]
        )
        if decision is EvidenceAssessment.SATISFIED:
            return ModelInvocationResult(output=AuditorDecision(decision, refs))
        return ModelInvocationResult(
            output=AuditorDecision(decision, (), ("route_result",), "collect exact result evidence")
        )


class OmitsRequiredEvidenceAuditor(Auditor):
    async def audit(self, request):
        self.requests.append(request)
        required = {item.record.evidence_ref for item in request.working_facts}
        unrelated = next(
            item.evidence_ref
            for item in request.audit_bundle.evidence_records
            if item.evidence_ref not in required
        )
        return ModelInvocationResult(
            output=AuditorDecision(EvidenceAssessment.SATISFIED, (unrelated,))
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


def test_replan_revision_property_preserves_every_accepted_field_and_strictly_increases_version() -> None:
    accepted = Milestone(
        "m1",
        "Old outcome",
        "Old state visible",
        required_evidence=(EvidenceRequirement("result", "Exact result"),),
    )
    tail = Milestone("m2", "Finish", "Finished", depends_on=("m1",), final=True)
    before = MilestoneRoadmap(1, (accepted, tail))
    mission = MissionState(
        1,
        (AcceptedWorkingOutcome("m1", EvidenceAssessment.SATISFIED, ("fact:proof",), "accepted"),),
    )
    invalid_revisions = (
        MilestoneRoadmap(1, (accepted, tail)),
        MilestoneRoadmap(2, (Milestone("m2", "Finish", "Finished", final=True),)),
        MilestoneRoadmap(2, (Milestone("m1", "Changed", accepted.done_when, accepted.required_evidence), tail)),
        MilestoneRoadmap(2, (Milestone("m1", accepted.outcome, "Changed", accepted.required_evidence), tail)),
        MilestoneRoadmap(
            2,
            (
                Milestone("m1", accepted.outcome, accepted.done_when),
                tail,
            ),
        ),
        MilestoneRoadmap(
            2,
            (
                Milestone("prep", "Prepare", "Prepared"),
                Milestone(
                    "m1",
                    accepted.outcome,
                    accepted.done_when,
                    accepted.required_evidence,
                    depends_on=("prep",),
                ),
                tail,
            ),
        ),
        MilestoneRoadmap(
            2,
            (
                Milestone(
                    "m1",
                    accepted.outcome,
                    accepted.done_when,
                    accepted.required_evidence,
                    final=True,
                ),
                Milestone("m2", "Finish", "Finished", depends_on=("m1",)),
            ),
        ),
    )

    assert all(
        not _roadmap_revision_preserves_accepted_semantics(before, revision, mission)
        for revision in invalid_revisions
    )
    valid_tail_replacement = MilestoneRoadmap(
        2,
        (
            accepted,
            Milestone("replacement", "New unresolved outcome", "New outcome visible", depends_on=("m1",)),
        ),
    )
    assert _roadmap_revision_preserves_accepted_semantics(before, valid_tail_replacement, mission)


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
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=1).run(runtime, environment, TaskGoal("task:route", "Get result"))
    )
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


def test_missing_required_evidence_continues_same_milestone_without_auditor_or_replan() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (
            Milestone(
                "result",
                "Requested result is available",
                "The exact result is retained",
                required_evidence=(EvidenceRequirement("route_result", "Exact result"),),
            ),
        ),
    )
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),))
    runtime = Runtime(())
    auditor = Auditor()
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=2).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("missing-before")),
            TaskGoal("task:missing", "Get result"),
        )
    )

    assert result.planner_calls == 1
    assert result.auditor_calls == 0
    assert runtime.continue_calls == 2
    assert runtime.initializations[1][1].id == "result"
    assert runtime.initializations[1][1].missing_evidence_keys == ("route_result",)


def test_unchanged_world_without_new_evidence_continues_without_auditor() -> None:
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),))
    runtime = Runtime(())
    auditor = Auditor()
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=2).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("unchanged-before")),
            TaskGoal("task:unchanged", "Get result"),
        )
    )

    assert result.outcome is MissionOutcome.EVIDENCE_GAP
    assert result.planner_calls == 1
    assert result.auditor_calls == 0
    assert runtime.continue_calls == 2


def test_untyped_working_fact_lineage_continues_without_auditor() -> None:
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),))
    runtime = UntypedLineageRuntime()
    auditor = Auditor()
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=1).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("untyped-before")),
            TaskGoal("task:untyped", "Get result"),
        )
    )

    assert result.outcome is MissionOutcome.EVIDENCE_GAP
    assert result.planner_calls == 1
    assert result.auditor_calls == 0
    assert runtime.continue_calls == 1


def test_supervisor_formal_complete_admits_only_the_final_milestone_without_auditor() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (Milestone("final", "Requested result is complete", "Native evaluator is complete", final=True),),
    )
    auditor = Auditor()
    runtime = FormalEvaluationRuntime(TaskEvaluationStatus.COMPLETE)
    result = asyncio.run(
        MissionSupervisor(
            Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),)),
            auditor,
            max_rounds=1,
        ).run(
            runtime,
            ScriptedEnvironment(
                initial_observation=fused_world(
                    "formal-supervisor-complete",
                    (SemanticTarget("result", "status", "Requested result"),),
                )
            ),
            TaskGoal("task:formal-supervisor-complete", "Get result"),
        )
    )

    assert result.mission_state.version == 1
    assert result.auditor_calls == 0
    assert len(auditor.requests) == 0


def test_supervisor_formal_unsatisfied_keeps_final_milestone_without_auditor_or_replan() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (Milestone("final", "Requested result is complete", "Native criterion is satisfied", final=True),),
    )
    auditor = Auditor()
    runtime = FormalEvaluationRuntime(
        TaskEvaluationStatus.INCOMPLETE,
        CriterionEvaluationStatus.UNSATISFIED,
    )
    result = asyncio.run(
        MissionSupervisor(
            Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),)),
            auditor,
            max_rounds=1,
        ).run(
            runtime,
            ScriptedEnvironment(
                initial_observation=fused_world(
                    "formal-supervisor-unsatisfied",
                    (SemanticTarget("result", "status", "Requested result"),),
                )
            ),
            TaskGoal("task:formal-supervisor-unsatisfied", "Get result"),
        )
    )

    assert result.outcome is MissionOutcome.EVIDENCE_GAP
    assert result.mission_state.version == 0
    assert result.planner_calls == 1
    assert result.auditor_calls == 0
    assert len(auditor.requests) == 0


def test_auditor_failure_returns_audit_unavailable_without_replaying_gui_or_losing_pinned_facts() -> None:
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),))
    runtime = Runtime(("pin_fact",))
    auditor = SequenceAuditor((ModelFailure(ModelFailureKind.SCHEMA_ERROR, "role output invalid", False),))
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=2).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("audit-failure-before")),
            TaskGoal("task:audit-failure", "Get result"),
        )
    )

    assert result.planner_calls == 1
    assert result.auditor_calls == 1
    assert result.outcome is MissionOutcome.AUDIT_UNAVAILABLE
    assert result.mission_state.version == 0
    assert runtime.continue_calls == 1
    assert tuple(item.key for item in result.state.working_facts) == ("route_result",)
    assert set(vars(auditor.requests[0])) == {
        "task",
        "milestone",
        "pre_mission_state",
        "working_facts",
        "outcome_summary",
        "yield_reason",
        "audit_bundle",
    }


def test_auditor_unknown_returns_guidance_and_retained_facts_to_same_milestone_without_planner() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (
            Milestone(
                "result",
                "Requested result is available",
                "Exact result is retained",
                required_evidence=(EvidenceRequirement("route_result", "Exact result"),),
            ),
        ),
    )
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),))
    runtime = Runtime(("pin_fact",))
    auditor = SequenceAuditor((EvidenceAssessment.UNKNOWN, EvidenceAssessment.SATISFIED))
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=2).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("audit-unknown-before")),
            TaskGoal("task:audit-unknown", "Get result"),
        )
    )

    assert result.planner_calls == 1
    assert result.auditor_calls == 2
    assert result.mission_state.version == 1
    assert runtime.initializations[1][1].id == "result"
    assert runtime.initializations[1][1].missing_evidence_keys == ("route_result",)
    assert runtime.initializations[1][1].audit_guidance == "collect exact result evidence"
    assert tuple(item.key for item in runtime.initializations[1][3]) == ("route_result",)


def test_auditor_unsatisfied_returns_guidance_and_retained_facts_to_same_milestone_without_planner() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (
            Milestone(
                "result",
                "Requested result is available",
                "Exact result is retained",
                required_evidence=(EvidenceRequirement("route_result", "Exact result"),),
            ),
        ),
    )
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),))
    runtime = Runtime(("pin_fact",))
    auditor = SequenceAuditor((EvidenceAssessment.UNSATISFIED, EvidenceAssessment.SATISFIED))
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=2).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("audit-unsatisfied-before")),
            TaskGoal("task:audit-unsatisfied", "Get result"),
        )
    )

    assert result.planner_calls == 1
    assert result.auditor_calls == 2
    assert result.mission_state.version == 1
    assert runtime.initializations[1][1].id == "result"
    assert runtime.initializations[1][1].audit_guidance == "collect exact result evidence"
    assert tuple(item.key for item in runtime.initializations[1][3]) == ("route_result",)


def test_auditor_satisfaction_cannot_omit_required_retained_evidence_refs() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (
            Milestone(
                "result",
                "Requested result is available",
                "Exact result is retained",
                required_evidence=(EvidenceRequirement("route_result", "Exact result"),),
            ),
        ),
    )
    result = asyncio.run(
        MissionSupervisor(
            Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),)),
            OmitsRequiredEvidenceAuditor(),
            max_rounds=1,
        ).run(
            Runtime(("pin_fact",)),
            ScriptedEnvironment(initial_observation=fused_world("audit-omission-before")),
            TaskGoal("task:audit-omission", "Get result"),
        )
    )

    assert result.outcome is MissionOutcome.AUDIT_UNAVAILABLE
    assert result.mission_state.version == 0


def test_two_required_keys_may_alias_one_current_evidence_record_without_bundle_failure() -> None:
    roadmap = MilestoneRoadmap(
        1,
        (
            Milestone(
                "result",
                "Both requested fields are available",
                "Both fields retain the same exact result",
                required_evidence=(
                    EvidenceRequirement("first_result", "First requested field"),
                    EvidenceRequirement("second_result", "Second requested field"),
                ),
            ),
        ),
    )
    result = asyncio.run(
        MissionSupervisor(
            Planner((PlannerDecision(PlannerRoute.ROADMAP, roadmap),)),
            Auditor(),
            max_rounds=1,
        ).run(
            AliasedWorkingFactsRuntime(),
            ScriptedEnvironment(
                initial_observation=fused_world(
                    "aliased-facts-world",
                    targets=(SemanticTarget("result", "status", "Shared result"),),
                    facts=(StateFact("shared", "result", "value", "same", "aliased-facts-world"),),
                )
            ),
            TaskGoal("task:aliased-facts", "Retain both result fields"),
        )
    )

    assert result.outcome is MissionOutcome.ROUND_BUDGET_EXHAUSTED
    assert result.mission_state.version == 1
    assert tuple(item.key for item in result.mission_state.accepted_facts) == (
        "first_result",
        "second_result",
    )
    assert len({item.record.evidence_ref for item in result.mission_state.accepted_facts}) == 1


def test_four_ready_milestones_use_one_planner_call_and_only_semantic_unknown_uses_auditor() -> None:
    milestones = tuple(
        Milestone(
            f"m{index}",
            f"Outcome {index}",
            f"Outcome {index} is visible",
            depends_on=((f"m{index - 1}",) if index > 1 else ()),
            final=index == 4,
        )
        for index in range(1, 5)
    )
    planner = Planner((PlannerDecision(PlannerRoute.ROADMAP, MilestoneRoadmap(1, milestones)),))
    runtime = Runtime(("activate",))
    auditor = Auditor()
    result = asyncio.run(
        MissionSupervisor(planner, auditor, max_rounds=4).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("four-before")),
            TaskGoal("task:four", "Complete four outcomes"),
        )
    )

    assert result.planner_calls == 1
    assert result.auditor_calls == 4
    assert result.mission_state.version == 4
    assert [item.outcome_id for item in result.mission_state.working_outcomes] == ["m1", "m2", "m3", "m4"]


def test_roadmap_exhaustion_is_the_only_post_admission_planner_trigger_without_a_ready_successor() -> None:
    planner = Planner(
        (
            PlannerDecision(PlannerRoute.ROADMAP, _roadmap("Requested result is available")),
            PlannerDecision(PlannerRoute.BLOCKED, reason="roadmap exhausted without final response"),
        )
    )
    runtime = Runtime(("activate",))
    result = asyncio.run(
        MissionSupervisor(planner, Auditor(), max_rounds=2).run(
            runtime,
            ScriptedEnvironment(initial_observation=fused_world("exhausted-before")),
            TaskGoal("task:exhausted", "Get result"),
        )
    )

    assert result.planner_calls == 2
    assert result.outcome is MissionOutcome.BLOCKED
    assert planner.requests[1].mode is PlannerRequestMode.ROADMAP_EXHAUSTED_NOT_FINALIZABLE
    assert runtime.continue_calls == 1


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
        MissionSupervisor(planner, auditor, max_rounds=1).run(
            runtime, environment, TaskGoal("task:archived-replay", "Get result")
        )
    )

    assert result.planner_calls == 1
    assert runtime.continue_calls == 1
    assert runtime.initializations == [(15, runtime.initializations[0][1], tuple(route), ())]
    assert runtime.applied_routes == route
    assert runtime.planner_calls_during_routes == [1] * len(route)
    assert result.step_count == len(route) + 1
    assert result.execution_count == sum(INTERACTION_CAPABILITY_REGISTRY.resolve(item) is not None for item in route)
    assert len(auditor.requests) == 1

import asyncio
from dataclasses import dataclass, replace

import pytest

from affordance_runtime.actions import ActionBinding, ActionRisk
from affordance_runtime.agent import (
    Abort,
    AskUser,
    ReadRegionResult,
    RequestActionPage,
    RunStatus,
    SearchPageContentResult,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.decisions import AbortCategory, ToolRejectedResult
from affordance_runtime.agent.episode_snapshot import snapshot_episode
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.profile import AgentLoopProfile
from affordance_runtime.agent.recovery import RecoveryKind, RecoverySignal
from affordance_runtime.agent.run_control import (
    RunControlBoundary,
    RunControlKind,
    RunControlOutcomeKind,
)
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingEnvironment,
)
from affordance_runtime.evaluation import (
    ActionOutcome,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.action_outcome_projector import ProductionActionOutcomeProjector
from affordance_runtime.execution.contracts import (
    ActionError,
    ActionResult,
    DispatchStatus,
    ExecutionCancellationPhase,
    ExecutionCompletion,
    ExecutionReceiptBatch,
    SessionHealth,
    SessionHealthStatus,
)
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)

# Collection-only sentinels for skipped witnesses of the removed compound path.
RemovedCompoundDecision = object
RemovedCompoundField = object
RemovedCompoundCancellation = RuntimeError


def _world(observation_id: str, enabled: bool) -> WorldObservation:
    target = SemanticTarget(
        "shared-toggle",
        "button",
        "Shared state enabled" if enabled else "Enable shared state",
        {"enabled": enabled},
    )
    binding = ActionBinding(
        binding_id=f"binding:{observation_id}",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=f"revision:{observation_id}",
        target_fingerprint=f"fingerprint:{observation_id}",
        target_id=target.target_id,
        source_target_id=target.target_id,
        surface="dom",
        executor_id="dom",
        semantic_action="activate",
        primitive_action="click",
        effect_category="local_reversible",
        semantic_effects=("shared_state_enabled",),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        payload={"selector": "#shared"},
        risk=ActionRisk.LOW,
    )
    fact = StateFact(
        f"fact:{observation_id}:enabled",
        target.target_id,
        "enabled",
        enabled,
        observation_id,
    )
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (target,),
        (fact,),
        (binding,),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
        risk_profile=RiskProfile.LOW,
    )


def _route_world(observation_id: str, route: str, controls: tuple[str, ...]) -> WorldObservation:
    document = SemanticTarget("route-document", "document", "Route test", {"page.route": route})
    targets = (document,) + tuple(
        SemanticTarget(control, "button", control.replace("-", " ").title()) for control in controls
    )
    bindings = tuple(
        ActionBinding(
            f"binding:{observation_id}:{control}",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            f"fingerprint:{control}",
            control,
            control,
            "dom",
            "dom",
            "activate",
            "click",
            "local_reversible",
            ("route_changed",),
            {"type": "object", "properties": {}, "additionalProperties": False},
            {"selector": f"#{control}"},
            risk=ActionRisk.LOW,
        )
        for control in controls
    )
    facts = (
        StateFact(
            f"fact:{observation_id}:route",
            document.target_id,
            "page.route",
            route,
            observation_id,
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        facts,
        bindings,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _route_task() -> TaskGoal:
    return TaskGoal(
        "route-recovery",
        "Reach the completed route",
        allowed_effects=("route_changed",),
        risk_profile=RiskProfile.LOW,
        loop_budget=LoopBudget(max_turns=8, max_observations=16),
    )


class RouteTaskEvaluator:
    async def evaluate(self, task, observation):
        route = str(observation.targets[0].state.get("page.route", ""))
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if route == "/done" else TaskEvaluationStatus.INCOMPLETE,
            "route complete" if route == "/done" else "route incomplete",
            completion_evidence_refs=(observation.facts[0].fact_id,) if route == "/done" else (),
        )


def _form_world(observation_id: str, from_value: str, to_value: str) -> WorldObservation:
    targets = (
        SemanticTarget("route-from", "textbox", "From", {"value": from_value}),
        SemanticTarget("route-to", "textbox", "To", {"value": to_value}),
    )
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }
    bindings = tuple(
        ActionBinding(
            f"binding:{observation_id}:{target.target_id}",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            f"fingerprint:{observation_id}:{target.target_id}",
            target.target_id,
            target.target_id,
            "dom",
            "dom",
            "type_text",
            "fill",
            "local_reversible",
            ("value_changed",),
            schema,
            {"selector": f"#{target.target_id}"},
            risk=ActionRisk.LOW,
        )
        for target in targets
    )
    facts = tuple(
        StateFact(
            f"fact:{observation_id}:{target.target_id}:value",
            target.target_id,
            "value",
            target.state["value"],
            observation_id,
        )
        for target in targets
    )
    structure = (
        ObservationStructureNode(
            "form:route",
            "form",
            "Route",
            child_structure_ids=("node:route-from", "node:route-to"),
        ),
        *(
            ObservationStructureNode(
                f"node:{target.target_id}",
                target.role,
                target.label,
                parent_structure_id="form:route",
                semantic_target_id=target.target_id,
            )
            for target in targets
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        facts=facts,
        bindings=bindings,
        structure=structure,
        structure_total_count=len(structure),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _text_world(observation_id: str, value: str) -> WorldObservation:
    target = SemanticTarget("shared-input", "textbox", "Shared value", {"value": value})
    binding = ActionBinding(
        binding_id=f"binding:{observation_id}",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=f"revision:{observation_id}",
        target_fingerprint=f"fingerprint:{observation_id}",
        target_id=target.target_id,
        source_target_id=target.target_id,
        surface="dom",
        executor_id="dom",
        semantic_action="type_text",
        primitive_action="fill",
        effect_category="local_reversible",
        semantic_effects=("shared_value_changed",),
        parameter_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        payload={"selector": "#shared-input"},
        risk=ActionRisk.LOW,
    )
    fact = StateFact(f"fact:{observation_id}:value", target.target_id, "value", value, observation_id)
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (target,),
        (fact,),
        (binding,),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _search_fixture_observation(observation_id: str, value: str) -> WorldObservation:
    target = SemanticTarget("search-input", "searchbox", "Search", {"value": value})
    common = {
        "world_observation_id": observation_id,
        "source_observation_id": observation_id,
        "source_revision": f"revision:{observation_id}",
        "target_fingerprint": f"fingerprint:{observation_id}",
        "target_id": target.target_id,
        "source_target_id": target.target_id,
        "surface": "dom",
        "executor_id": "dom",
        "effect_category": "local_reversible",
        "risk": ActionRisk.LOW,
    }
    bindings = (
        ActionBinding(
            binding_id=f"binding:{observation_id}:fill",
            semantic_action="type_text",
            primitive_action="fill",
            semantic_effects=("value_changed",),
            parameter_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            payload={"selector": "#search"},
            **common,
        ),
        ActionBinding(
            binding_id=f"binding:{observation_id}:press",
            semantic_action="press_key",
            primitive_action="press",
            semantic_effects=("form_submitted",),
            parameter_schema={
                "type": "object",
                "properties": {"key": {"type": "string", "enum": ["Enter"]}},
                "required": ["key"],
                "additionalProperties": False,
            },
            payload={"selector": "#search"},
            **common,
        ),
    )
    fact = StateFact(f"fact:{observation_id}:value", target.target_id, "value", value, observation_id)
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (target,),
        (fact,),
        bindings,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _autocomplete_fixture_observation(
    observation_id: str,
    value: str,
    selected_index: int,
) -> WorldObservation:
    search = SemanticTarget(
        "autocomplete-search",
        "searchbox",
        "Search",
        {"focused": True, "value": value},
    )
    selection = SemanticTarget(
        "autocomplete-selection",
        "status",
        "Autocomplete selection",
        {"selected_index": selected_index},
    )
    binding = ActionBinding(
        binding_id=f"binding:{observation_id}:arrow-down",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=f"revision:{observation_id}",
        target_fingerprint="fingerprint:autocomplete-search",
        target_id=search.target_id,
        source_target_id=search.target_id,
        surface="dom",
        executor_id="dom",
        semantic_action="press_key",
        primitive_action="press",
        effect_category="local_reversible",
        semantic_effects=("external_ui_interaction",),
        parameter_schema={
            "type": "object",
            "properties": {"key": {"type": "string", "enum": ["ArrowDown"]}},
            "required": ["key"],
            "additionalProperties": False,
        },
        payload={"selector": "#search"},
        risk=ActionRisk.LOW,
    )
    facts = (
        StateFact(f"fact:{observation_id}:value", search.target_id, "value", value, observation_id),
        StateFact(
            f"fact:{observation_id}:selected",
            selection.target_id,
            "selected_index",
            selected_index,
            observation_id,
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (search, selection),
        facts,
        (binding,),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


class TextTaskEvaluator:
    async def evaluate(self, task, observation):
        value = observation.targets[0].state.get("value")
        status = TaskEvaluationStatus.COMPLETE if value == "done" else TaskEvaluationStatus.INCOMPLETE
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            "value check",
            completion_evidence_refs=(observation.facts[0].fact_id,) if value == "done" else (),
        )


def _count_world() -> WorldObservation:
    base = _world("count", False)
    source = base.sources[0]
    counted_source = replace(
        source,
        structure=(
            ObservationStructureNode(
                "group",
                "group",
                "Blocks",
                child_structure_ids=("block:1", "block:2"),
            ),
            ObservationStructureNode(
                "block:1",
                "graphics-symbol",
                "",
                parent_structure_id="group",
            ),
            ObservationStructureNode(
                "block:2",
                "graphics-symbol",
                "",
                parent_structure_id="group",
            ),
            ObservationStructureNode(
                "group:2",
                "group",
                "More blocks",
                child_structure_ids=("block:3", "block:4", "block:5"),
            ),
            ObservationStructureNode(
                "block:3",
                "graphics-symbol",
                "",
                parent_structure_id="group:2",
            ),
            ObservationStructureNode(
                "block:4",
                "graphics-symbol",
                "",
                parent_structure_id="group:2",
            ),
            ObservationStructureNode(
                "block:5",
                "graphics-symbol",
                "",
                parent_structure_id="group:2",
            ),
        ),
        structure_total_count=7,
    )
    fused = WorldFusion().fuse((counted_source,))
    assert fused.observation is not None
    return fused.observation


@dataclass
class CorePolicy:
    choice: str
    turns: int = 0

    async def decide(self, context):
        self.turns += 1
        if self.choice == "first_action":
            return SelectAction(
                context.context_id,
                context.actions.options[0].action_id,
                tool_call_id="provider-call:test",
            )
        if self.choice == "action_page":
            if self.turns == 1:
                return RequestActionPage(context.context_id, query="shared state")
            assert context.actions.active_query == ""
            assert context.action_candidates.scope == "delivery"
            assert context.workspace.recent_steps[-1].semantic_action == "find_controls"
            return Abort(context.context_id, "page observed", AbortCategory.USER_REQUEST)
        if self.choice == "wait":
            if self.turns == 1:
                return Wait(context.context_id, "allow interface to settle", 5)
            return Abort(context.context_id, "wait observed", AbortCategory.USER_REQUEST)
        if self.choice == "ask_user":
            if self.turns == 1:
                return AskUser(context.context_id, "Which value?", ("value",))
            assert context.task.public_inputs["value"] == "provided"
            assert context.workspace.recent_steps[-1].reason == "user_input_received"
            return Abort(context.context_id, "input observed", AbortCategory.USER_REQUEST)
        if self.choice == "count_children":
            if self.turns == 1:
                return ReadRegionResult(
                    context.context_id,
                    "count_children",
                    {"containers": ("N1", "N4")},
                    {"counts": {"N1": 2, "N4": 3}, "total": 5},
                    "provider-call:count",
                )
            step = context.workspace.recent_steps[-1]
            assert step.semantic_action == "count_children"
            assert step.semantic_summary["information_delta"] == "new_information"
            assert step.semantic_summary["new_information_count"] == 1
            assert "result" not in step.semantic_summary
            return Abort(context.context_id, "count observed", AbortCategory.USER_REQUEST)
        if self.choice == "confirm_once":
            if self.turns == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            assert context.workspace.recent_steps[-1].reason == "confirmation_declined"
            return Abort(context.context_id, "decline observed", AbortCategory.USER_REQUEST)
        raise AssertionError("policy should not be called")


class CoreTaskEvaluator:
    async def evaluate(self, task, observation):
        enabled = bool(observation.targets[0].state.get("enabled"))
        fact_ref = observation.facts[0].fact_id
        criteria = tuple(
            CriterionEvaluation(
                criterion_id(item),
                (CriterionEvaluationStatus.SATISFIED if enabled else CriterionEvaluationStatus.UNSATISFIED),
                (fact_ref,),
                "criterion satisfied" if enabled else "criterion unsatisfied",
            )
            for item in task.success_criteria
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if enabled else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if enabled else "shared state is disabled",
            criteria,
            (fact_ref,) if enabled else (),
        )


class CoreActionOutcomeProjector:
    async def evaluate(self, task, before, request, result, after, public_world_delta):
        del task, result
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.STRUCTURAL,
            "state changed",
            (after.facts[0].fact_id,),
        )


class DispatchPostconditionProjector:
    async def evaluate(self, task, before, request, result, after, public_world_delta):
        del task, result
        changed = before.targets[0].state.get("enabled") != after.targets[0].state.get("enabled")
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED if changed else ObservedChange.UNCHANGED,
            LocalPostconditionStatus.SATISFIED if changed else LocalPostconditionStatus.UNSATISFIED,
            EvidenceMethod.STRUCTURAL,
            "postcondition satisfied" if changed else "postcondition unsatisfied",
            (after.facts[0].fact_id,),
        )


def _runtime(choice: str, *, wait_controller=None) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(CorePolicy(choice)),
        CoreActionOutcomeProjector(),
        CoreTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_core_loop_test"),
        **({"wait_controller": wait_controller} if wait_controller is not None else {}),
    )


def _active_boundary_recovery(*, epoch: str = "recovery:1:boundary") -> RecoverySignal:
    return RecoverySignal(
        RecoveryKind.CONTROL_STALL,
        "boundary-recovery",
        {"origin_dispatch": DispatchStatus.SENT.value},
        attempted_modes=("activate",),
        human_instruction="choose a different normal action",
        epoch_id=epoch,
    )


def test_same_observation_reuses_one_expensive_context_projection(monkeypatch) -> None:
    calls: list[str] = []
    original = ContextBuilder.project_observation

    def counted(self, observation, action_space, **kwargs):
        calls.append(observation.observation_id)
        return original(self, observation, action_space, **kwargs)

    monkeypatch.setattr(ContextBuilder, "project_observation", counted)

    async def scenario() -> None:
        state = await _runtime("action_page").run_task(
            ScriptedEnvironment(initial_observation=_world("same-world", False)),
            _task(),
        )

        assert state.status is RunStatus.CANCELLED
        assert state.step_count == 2
        assert state.observation_count == 1
        assert state.observation_projection is not None

    asyncio.run(scenario())

    assert calls == ["same-world"]


def test_recovery_delivers_a_distinct_control_result_to_the_next_policy_turn() -> None:
    @dataclass
    class RecoveryHandoffPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns in {1, 2}:
                return SearchPageContentResult(
                    context.context_id,
                    "search_page_content",
                    {"query": f"missing-{self.turns}"},
                    {"kind": "NoMatches", "items": (), "total_count": 0},
                    f"provider-call:missing-{self.turns}",
                )
            if self.turns == 3:
                return RequestActionPage(context.context_id, query="shared state")
            if self.turns == 4:
                assert context.last_step is not None
                assert context.last_step.action_page_result is not None
                assert context.last_step.action_page_result.matches
                assert context.control_feedback["kind"] == "control_stall"
                option = next(item for item in context.complete_actions if item.operation == "activate")
                return SelectAction(
                    context.context_id,
                    option.action_id,
                    tool_call_id="provider-call:recovered-action",
                )
            raise AssertionError("policy should complete after the recovered action")

    async def scenario() -> None:
        policy = RecoveryHandoffPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("recovery_handoff_test"),
            episode_monitor=EpisodeMonitor(AgentLoopProfile(1, 1)),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("recovery-before", False),
            post_observations=(_world("recovery-after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert policy.turns == 4
        assert state.step_count == 4
        assert state.execution_count == 1
        assert environment.execute_calls == 1
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "provider-call:recovered-action"

    asyncio.run(scenario())


def test_exact_local_result_replay_is_rejected_under_the_same_recovery_epoch() -> None:
    @dataclass
    class LocalReplayPolicy:
        turns: int = 0
        rejected: ToolRejectedResult | None = None
        recovery_epoch: str = ""
        prohibited: tuple[object, ...] = ()

        @staticmethod
        def original(context, call_id: str) -> SearchPageContentResult:
            return SearchPageContentResult(
                context.context_id,
                "search_page_content",
                {"query": "airport"},
                {
                    "kind": "Matches",
                    "items": ({"label": "Airport", "value": "33 km"},),
                    "total_count": 1,
                },
                call_id,
            )

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                return self.original(context, "provider-call:local-first")
            if self.turns == 2:
                return self.original(context, "provider-call:local-replay-proof")
            if self.turns == 3:
                assert len(context.control_feedback["prohibited_attempt_signatures"]) == 1
                return SearchPageContentResult(
                    context.context_id,
                    "search_page_content",
                    {"query": "different"},
                    {"kind": "NoMatches", "items": (), "total_count": 0},
                    "provider-call:local-different",
                )
            if self.turns == 4:
                assert context.control_feedback["kind"] == "control_stall"
                return self.original(context, "provider-call:local-hard-replay")
            if self.turns == 5:
                assert context.last_step is not None
                assert isinstance(context.last_step.decision, ToolRejectedResult)
                self.rejected = context.last_step.decision
                self.recovery_epoch = str(context.control_feedback["epoch_id"])
                self.prohibited = tuple(context.control_feedback["prohibited_attempt_signatures"])
                return Abort(context.context_id, "rejection observed", AbortCategory.USER_REQUEST)
            raise AssertionError("local replay test exceeded its bounded sequence")

    async def scenario() -> None:
        policy = LocalReplayPolicy()
        monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("local_replay_constraint_test"),
            episode_monitor=monitor,
        )
        environment = ScriptedEnvironment(initial_observation=_world("local-replay", False))

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert policy.turns == 5
        assert environment.execute_calls == 0
        assert policy.rejected is not None
        assert policy.rejected.result["kind"] == "prohibited_attempt_rejected"
        assert policy.rejected.result["failure_kind"] == "recovery_prohibited_attempt_replay"
        assert policy.rejected.result["dispatch"] == "not_sent"
        assert policy.rejected.result["epoch_id"] == policy.recovery_epoch
        assert policy.rejected.rejected_attempt_signature is not None
        assert any(
            item["parameter_digest"] == policy.rejected.rejected_attempt_signature.parameter_digest
            for item in policy.prohibited
        )

    asyncio.run(scenario())


def test_exact_control_discovery_replay_is_rejected_without_dispatch() -> None:
    @dataclass
    class DiscoveryReplayPolicy:
        turns: int = 0
        rejected: ToolRejectedResult | None = None

        async def decide(self, context):
            self.turns += 1
            if self.turns <= 3:
                return RequestActionPage(
                    context.context_id,
                    query="shared state",
                    tool_call_id=f"provider-call:discovery-{self.turns}",
                )
            assert context.last_step is not None
            assert isinstance(context.last_step.decision, ToolRejectedResult)
            self.rejected = context.last_step.decision
            return Abort(context.context_id, "discovery rejection observed", AbortCategory.USER_REQUEST)

    async def scenario() -> None:
        policy = DiscoveryReplayPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("discovery_replay_constraint_test"),
            episode_monitor=EpisodeMonitor(),
        )
        environment = ScriptedEnvironment(initial_observation=_world("discovery-replay", False))

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert policy.turns == 4
        assert environment.execute_calls == 0
        assert policy.rejected is not None
        assert policy.rejected.tool_name == "find_controls"
        assert policy.rejected.result["kind"] == "prohibited_attempt_rejected"
        assert policy.rejected.result["dispatch"] == "not_sent"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "refresh_method",
    (
        "refresh_after_pause_persistence_failure",
        "refresh_after_user_control",
    ),
)
def test_passive_currentness_refresh_preserves_the_monitor_owned_recovery_epoch(refresh_method) -> None:
    async def scenario() -> None:
        monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("passive_refresh_recovery"),
            episode_monitor=monitor,
        )
        task = _task()
        environment = ScriptedEnvironment(
            initial_observation=_world("refresh-before", False),
            independent_observations=(_world("refresh-after", False),),
        )
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery()
        monitor.restore_episode(state.current_world, state.current_task_evaluation, signal)
        state.recovery_signal = signal

        loop = runtime.build_loop()
        await getattr(loop, refresh_method)(environment, task, state)

        assert state.status is RunStatus.RUNNING
        assert state.recovery_signal is not None
        assert state.recovery_signal.epoch_id == signal.epoch_id
        assert state.last_step is not None
        assert state.last_step.recovery_signal == state.recovery_signal
        assert monitor.active_recovery == state.recovery_signal

    asyncio.run(scenario())


def test_missing_monitor_cannot_silently_clear_a_restored_recovery_epoch() -> None:
    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("restored_recovery_without_monitor"),
            episode_monitor=None,
        )
        task = _task()
        environment = ScriptedEnvironment(
            initial_observation=_world("monitor-missing-before", False),
            independent_observations=(_world("monitor-missing-after", False),),
        )
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery(epoch="recovery:1:restored-without-monitor")
        state.recovery_signal = signal

        await runtime.build_loop().refresh_after_pause_persistence_failure(environment, task, state)

        assert state.status is RunStatus.RUNNING
        assert state.recovery_signal == signal
        assert state.last_step is not None
        assert state.last_step.recovery_signal == signal

    asyncio.run(scenario())


def test_confirmation_dispatch_cannot_drop_an_active_recovery_epoch() -> None:
    @dataclass
    class ConfirmationRecoveryPolicy:
        turns: int = 0
        seen_feedback: dict[str, object] | None = None
        seen_postcondition: object = None

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                assert context.control_feedback["epoch_id"] == "recovery:1:confirmation"
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            assert self.turns == 2
            self.seen_feedback = dict(context.control_feedback)
            self.seen_postcondition = context.workspace.recent_steps[-1].local_postcondition
            return Abort(context.context_id, "recovery survived confirmation", AbortCategory.USER_REQUEST)

    async def scenario() -> None:
        policy = ConfirmationRecoveryPolicy()
        monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("confirmation_recovery"),
            episode_monitor=monitor,
        )
        task = replace(_task(), risk_profile=RiskProfile.MEDIUM)
        environment = ScriptedEnvironment(
            initial_observation=_world("confirmation-before", False),
            post_observations=(_world("confirmation-after", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery(epoch="recovery:1:confirmation")
        monitor.restore_episode(state.current_world, state.current_task_evaluation, signal)
        state.recovery_signal = signal

        await runtime.continue_task(environment, task, state)
        assert state.status is RunStatus.WAITING_CONFIRMATION
        assert state.recovery_signal == signal

        await runtime.resume_confirmation(environment, task, state, approved=True)

        assert policy.turns == 2
        assert policy.seen_feedback is not None
        assert policy.seen_feedback["epoch_id"] == "recovery:1:confirmation"
        assert policy.seen_feedback["evidence_revision"] > 1
        assert policy.seen_postcondition == LocalPostconditionStatus.UNSATISFIED.value
        assert environment.execute_calls == 1
        assert state.status is RunStatus.CANCELLED

    asyncio.run(scenario())


def test_user_task_revision_starts_a_new_monitor_episode_without_old_recovery() -> None:
    @dataclass
    class RevisionRecoveryPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                assert context.control_feedback["epoch_id"] == "recovery:1:old-task"
                return AskUser(context.context_id, "Which value?", ("value",))
            assert self.turns == 2
            assert context.goal_plan.task_revision == 2
            assert not context.control_feedback
            return Abort(context.context_id, "new revision has a new episode", AbortCategory.USER_REQUEST)

    async def scenario() -> None:
        policy = RevisionRecoveryPolicy()
        monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("revision_recovery"),
            episode_monitor=monitor,
        )
        task = _task()
        environment = ScriptedEnvironment(initial_observation=_world("revision-before", False))
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery(epoch="recovery:1:old-task")
        monitor.restore_episode(state.current_world, state.current_task_evaluation, signal)
        state.recovery_signal = signal

        await runtime.continue_task(environment, task, state)
        assert state.status is RunStatus.WAITING_USER
        assert state.recovery_signal == signal

        revised = replace(task, inputs={"value": "provided"}, revision=2)
        await runtime.resume_user(environment, revised, state)

        assert policy.turns == 2
        assert state.status is RunStatus.CANCELLED
        assert state.recovery_signal is None
        assert monitor.active_recovery is None

    asyncio.run(scenario())


def test_restored_terminal_currentness_closes_both_recovery_projections() -> None:
    async def scenario() -> None:
        monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("restored_terminal_recovery"),
            episode_monitor=monitor,
        )
        task = _task()
        environment = ScriptedEnvironment(initial_observation=_world("restored-terminal", False))
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery(epoch="recovery:1:restored")
        monitor.restore_episode(state.current_world, state.current_task_evaluation, signal)
        state.recovery_signal = signal
        state.current_task_evaluation = TaskEvaluation(
            task.task_id,
            state.current_world.observation_id,
            TaskEvaluationStatus.BLOCKED,
            "native evaluator proved impossibility after restore",
        )

        runtime.build_loop().settle_restored_currentness(state)

        assert state.status is RunStatus.BLOCKED
        assert state.recovery_signal is None
        assert monitor.active_recovery is None

    asyncio.run(scenario())


def test_before_policy_cancel_closes_both_recovery_projections() -> None:
    async def scenario() -> None:
        monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
        policy = CorePolicy("first_action")
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("before_policy_cancel_recovery"),
            episode_monitor=monitor,
        )
        task = _task()
        environment = ScriptedEnvironment(initial_observation=_world("cancel-before-policy", False))
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery(epoch="recovery:1:cancel")
        monitor.restore_episode(state.current_world, state.current_task_evaluation, signal)
        state.recovery_signal = signal
        runtime.request_control("command:cancel-recovery", RunControlKind.CANCEL)

        await runtime.continue_task(environment, task, state)

        assert policy.turns == 0
        assert state.status is RunStatus.CANCELLED
        assert state.recovery_signal is None
        assert monitor.active_recovery is None

    asyncio.run(scenario())


def test_waiting_control_cancel_closes_both_recovery_projections() -> None:
    @dataclass
    class WaitingPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            assert context.control_feedback["epoch_id"] == "recovery:1:waiting-cancel"
            return AskUser(context.context_id, "Which value?", ("value",))

    async def scenario() -> None:
        monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
        policy = WaitingPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("waiting_cancel_recovery"),
            episode_monitor=monitor,
        )
        task = _task()
        environment = ScriptedEnvironment(initial_observation=_world("cancel-waiting", False))
        state = await runtime.initialize_task(environment, task)
        signal = _active_boundary_recovery(epoch="recovery:1:waiting-cancel")
        monitor.restore_episode(state.current_world, state.current_task_evaluation, signal)
        state.recovery_signal = signal
        await runtime.continue_task(environment, task, state)
        assert state.status is RunStatus.WAITING_USER
        runtime.request_control("command:cancel-waiting", RunControlKind.CANCEL)

        outcome = runtime.apply_waiting_control(state)

        assert outcome is not None
        assert state.status is RunStatus.CANCELLED
        assert state.recovery_signal is None
        assert monitor.active_recovery is None

    asyncio.run(scenario())


def test_closed_gui_route_review_is_advisory_without_a_verified_no_effect() -> None:
    @dataclass
    class RouteRecoveryPolicy:
        turns: int = 0

        @staticmethod
        def select(context, target_id: str, call_id: str) -> SelectAction:
            option = next(item for item in context.actions.options if item.target_id == target_id)
            return SelectAction(context.context_id, option.action_id, tool_call_id=call_id)

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                return self.select(context, "primary-route", "provider-call:primary-first")
            if self.turns == 2:
                return SearchPageContentResult(
                    context.context_id,
                    "search_page_content",
                    {"query": "destination status"},
                    {
                        "kind": "Matches",
                        "items": ({"label": "Destination status", "value": "Not Found"},),
                        "total_count": 1,
                    },
                    "provider-call:read-destination",
                )
            if self.turns == 3:
                return self.select(context, "return-route", "provider-call:return")
            if self.turns == 4:
                assert not context.control_feedback
                return self.select(context, "second-route", "provider-call:second-first")
            if self.turns == 5:
                return SearchPageContentResult(
                    context.context_id,
                    "search_page_content",
                    {"query": "second destination status"},
                    {
                        "kind": "Matches",
                        "items": ({"label": "Second destination status", "value": "Not Found"},),
                        "total_count": 1,
                    },
                    "provider-call:read-second-destination",
                )
            if self.turns == 6:
                return self.select(context, "return-route", "provider-call:second-return")
            if self.turns == 7:
                assert context.control_feedback["kind"] == "strategy_review"
                assert context.control_feedback["observed_evidence"]["returned_to_prior_semantic_page"] is True
                return self.select(context, "second-route", "provider-call:second-replay")
            raise AssertionError("the advisory replay should reach the evaluator-confirmed result")

    async def scenario() -> None:
        first = _route_world(
            "route-a:first",
            "/search",
            ("primary-route", "second-route", "completion-route"),
        )
        failed = _route_world("route-b", "/relation/failed", ("return-route",))
        returned = _route_world(
            "route-a:returned",
            "/search",
            ("primary-route", "second-route", "completion-route"),
        )
        second_failed = _route_world("route-b:second", "/relation/second-failed", ("return-route",))
        returned_twice = _route_world(
            "route-a:returned-twice",
            "/search",
            ("primary-route", "second-route", "completion-route"),
        )
        complete = _route_world("route-c", "/done", ())
        policy = RouteRecoveryPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            RouteTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("strategy_review_test"),
            episode_monitor=EpisodeMonitor(AgentLoopProfile(8, 1)),
        )
        environment = ScriptedEnvironment(
            initial_observation=first,
            post_observations=(failed, returned, second_failed, returned_twice, complete),
            results=tuple(ActionResult("*", DispatchStatus.SENT, "dom", True) for _ in range(5)),
        )

        state = await runtime.run_task(environment, _route_task())

        assert state.status is RunStatus.DONE
        assert policy.turns == 7
        assert state.execution_count == 5
        assert environment.execute_calls == 5
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "provider-call:second-replay"

    asyncio.run(scenario())


def test_fresh_observation_replaces_context_projection_once(monkeypatch) -> None:
    calls: list[str] = []
    index_calls: list[str] = []
    original = ContextBuilder.project_observation
    original_index = WorldDeliveryIndex.from_observation

    def counted(self, observation, action_space, **kwargs):
        calls.append(observation.observation_id)
        return original(self, observation, action_space, **kwargs)

    monkeypatch.setattr(ContextBuilder, "project_observation", counted)

    def counted_index(observation, *args, **kwargs):
        index_calls.append(observation.observation_id)
        return original_index(observation, *args, **kwargs)

    monkeypatch.setattr(
        WorldDeliveryIndex,
        "from_observation",
        staticmethod(counted_index),
    )

    @dataclass
    class OneActionPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id="provider-call:refresh-projection",
                )
            return Abort(context.context_id, "fresh projection observed", AbortCategory.USER_REQUEST)

    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(OneActionPolicy()),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("observation_projection_refresh_test"),
        )
        state = await runtime.run_task(
            ScriptedEnvironment(
                initial_observation=_world("projection-before", False),
                post_observations=(_world("projection-after", False),),
                results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
            ),
            _task(),
        )

        assert state.status is RunStatus.CANCELLED
        assert state.observation_count == 2
        assert state.observation_projection is not None
        assert state.observation_projection.observation_id == "projection-after"

    asyncio.run(scenario())

    assert calls == ["projection-before", "projection-after"]
    assert index_calls == ["projection-before", "projection-after"], index_calls


@pytest.mark.parametrize("max_turns", (1, 30, 37, 100))
def test_task_goal_is_the_only_total_turn_budget_owner(max_turns: int) -> None:
    async def scenario() -> None:
        task = replace(
            _task(),
            loop_budget=LoopBudget(max_turns=max_turns, max_observations=max_turns * 2),
        )
        runtime = replace(
            _runtime("first_action"),
            episode_monitor=EpisodeMonitor(AgentLoopProfile(2, 1)),
        )
        environment = ScriptedEnvironment(initial_observation=_world("budget-owner", False))

        state = await runtime.initialize_task(environment, task)

        assert state.remaining_steps == max_turns
        assert state.step_count == 0

    asyncio.run(scenario())


def test_core_runtime_reuses_production_boundaries_and_completes_one_action() -> None:
    async def scenario() -> None:
        runtime = _runtime("first_action")
        loop = runtime.build_loop()
        assert loop.decision_ports is runtime.decision_ports
        assert loop.action_space_builder is runtime.action_space_builder
        assert loop.binder is runtime.binder
        assert loop.context_builder is runtime.context_builder

        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert state.current_world.observation_id == "after"
        assert state.observation_count == 2
        assert state.execution_count == 1
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "provider-call:test"
        assert state.last_step.execution_receipts is not None
        assert state.last_step.execution_receipts.receipts[-1].request.tool_call_id == "provider-call:test"
        assert state.last_step.action_outcome is not None
        assert state.last_step.action_outcome.observed_change is ObservedChange.CHANGED
        assert environment.execute_calls == 1

        with pytest.raises(ValueError, match="does not match"):
            replace(
                state.last_step,
                action_outcome=replace(
                    state.last_step.action_outcome,
                    request_id="request:wrong",
                ),
            )
        with pytest.raises(ValueError, match="tool call lineage"):
            replace(
                state.last_step,
                decision=replace(state.last_step.decision, tool_call_id="provider-call:wrong"),
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("kind", "expected_status", "expected_outcome"),
    (
        (RunControlKind.PAUSE, RunStatus.RUNNING, RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED),
        (RunControlKind.CANCEL, RunStatus.CANCELLED, RunControlOutcomeKind.CANCELLED),
    ),
)
def test_cooperative_control_during_policy_closes_not_sent_without_dispatch(
    kind,
    expected_status,
    expected_outcome,
) -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        @dataclass
        class BlockingPolicy:
            closed_steps: list[object]

            async def decide(self, context):
                entered.set()
                await release.wait()
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id="provider-call:controlled",
                )

            def close_deferred_call(self, step):
                self.closed_steps.append(step)

        policy = BlockingPolicy([])
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("cooperative_policy_control"),
        )
        environment = ScriptedEnvironment(initial_observation=_world("control-policy", False))
        state = await runtime.initialize_task(environment, _task())
        active = asyncio.create_task(runtime.continue_task(environment, _task(), state))
        await entered.wait()

        admission = runtime.request_control("command:policy", kind)
        release.set()
        completed = await active

        assert admission.outcome.value == "accepted"
        assert completed is state
        assert state.status is expected_status
        assert state.control_boundary is not None
        assert state.control_boundary.outcome is expected_outcome
        assert state.control_boundary.boundary is RunControlBoundary.AFTER_POLICY
        assert state.control_boundary.dispatch_status is DispatchStatus.NOT_SENT
        assert environment.execute_calls == 0
        assert state.execution_count == 0
        assert state.last_step is not None
        assert state.last_step.execution_receipts is None
        assert "action_not_dispatched" in state.last_step.feedback
        assert policy.closed_steps == [state.last_step]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("kind", "expected_status", "expected_control_outcome", "expected_turns"),
    (
        (
            RunControlKind.PAUSE,
            RunStatus.BLOCKED,
            RunControlOutcomeKind.BOUNDARY_FAILED,
            2,
        ),
        (
            RunControlKind.CANCEL,
            RunStatus.CANCELLED,
            RunControlOutcomeKind.CANCELLED,
            1,
        ),
    ),
)
def test_deferred_history_closure_failure_is_typed_and_never_prevents_cancel(
    kind,
    expected_status,
    expected_control_outcome,
    expected_turns,
) -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        @dataclass
        class FailingClosurePolicy:
            turns: int = 0

            async def decide(self, context):
                self.turns += 1
                if self.turns == 1:
                    entered.set()
                    await release.wait()
                    return SelectAction(
                        context.context_id,
                        context.actions.options[0].action_id,
                        tool_call_id="provider-call:closure-failure",
                    )
                return Abort(
                    context.context_id,
                    "pause boundary could not close model history",
                    AbortCategory.UNSUPPORTED,
                )

            def close_deferred_call(self, step):
                del step
                raise ValueError("synthetic history closure failure")

        policy = FailingClosurePolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("control_closure_failure"),
        )
        environment = ScriptedEnvironment(initial_observation=_world("closure-failure", False))
        state = await runtime.initialize_task(environment, _task())
        active = asyncio.create_task(runtime.continue_task(environment, _task(), state))
        await entered.wait()
        runtime.request_control("command:closure-failure", kind)
        release.set()

        await active

        outcome = runtime.run_control.outcome("command:closure-failure")
        assert outcome is not None
        assert outcome.outcome is expected_control_outcome
        assert state.status is expected_status
        assert policy.turns == expected_turns
        assert environment.execute_calls == 0

    asyncio.run(scenario())


def test_internal_resume_reselects_from_fresh_context_without_dispatching_stale_action() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        @dataclass
        class ReselectingPolicy:
            turns: int = 0

            async def decide(self, context):
                self.turns += 1
                if self.turns == 1:
                    entered.set()
                    await release.wait()
                    call_id = "provider-call:stale-before-pause"
                else:
                    assert context.last_step is not None
                    assert "action_not_dispatched" in context.last_step.feedback
                    call_id = "provider-call:fresh-after-resume"
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id=call_id,
                )

            def close_deferred_call(self, step):
                del step

        policy = ReselectingPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("control_resume_reselect"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("resume-before", False),
            post_observations=(_world("resume-after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.initialize_task(environment, _task())
        active = asyncio.create_task(runtime.continue_task(environment, _task(), state))
        await entered.wait()
        runtime.request_control("command:pause-reselect", RunControlKind.PAUSE)
        release.set()
        await active

        assert state.control_boundary is not None
        assert environment.execute_calls == 0
        runtime.resume_control(state, "command:resume-reselect")
        await runtime.continue_task(environment, _task(), state)

        assert state.status is RunStatus.DONE
        assert policy.turns == 2
        assert environment.execute_calls == 1
        assert state.last_step is not None
        assert state.last_step.execution_receipts is not None
        assert (
            state.last_step.execution_receipts.receipts[-1].request.tool_call_id == "provider-call:fresh-after-resume"
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("dispatch_status", (DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN))
def test_pause_during_dispatch_waits_for_receipt_fresh_world_and_evaluation(
    dispatch_status,
) -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        @dataclass
        class BlockingEnvironment(ScriptedEnvironment):
            async def execute(self, request):
                entered.set()
                await release.wait()
                return await super().execute(request)

        runtime = _runtime("first_action")
        environment = BlockingEnvironment(
            initial_observation=_world("control-before", False),
            post_observations=(_world("control-after", False),),
            results=(
                ActionResult(
                    "*",
                    dispatch_status,
                    "dom",
                    dispatch_status is DispatchStatus.SENT,
                    (None if dispatch_status is DispatchStatus.SENT else ActionError.EXECUTION_FAILED),
                ),
            ),
        )
        state = await runtime.initialize_task(environment, _task())
        active = asyncio.create_task(runtime.continue_task(environment, _task(), state))
        await entered.wait()

        runtime.request_control("command:dispatch", RunControlKind.PAUSE)
        assert not active.done()
        release.set()
        await active

        assert state.status is RunStatus.RUNNING
        assert state.control_boundary is not None
        assert state.control_boundary.outcome is RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
        assert state.control_boundary.boundary is RunControlBoundary.AFTER_EVALUATION
        assert state.control_boundary.dispatch_status is dispatch_status
        assert state.current_world.observation_id == "control-after"
        assert state.current_task_evaluation is not None
        assert state.current_task_evaluation.observation_id == "control-after"
        assert state.execution_count == 1
        assert environment.execute_calls == 1
        assert state.last_step is not None
        assert state.last_step.execution_receipts is not None
        assert state.last_step.execution_receipts.receipts[-1].result.dispatch_status is dispatch_status

    asyncio.run(scenario())


def test_physical_stale_not_sent_refreshes_world_and_returns_to_policy_without_replay() -> None:
    @dataclass
    class RefreshAwarePolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id="provider-call:stale",
                )
            assert context.current_observation is not None
            assert context.current_observation.observation_id == "refreshed"
            assert context.last_step is not None
            assert context.last_step.feedback == "binding_refreshed"
            assert context.last_step.execution_receipts is not None
            assert context.last_step.execution_receipts.execution_count == 0
            terminal = context.last_step.execution_receipts.terminal_failure
            assert terminal is not None and terminal.error is ActionError.STALE_BINDING
            return Abort(context.context_id, "fresh world observed", AbortCategory.USER_REQUEST)

    async def scenario() -> None:
        policy = RefreshAwarePolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("physical_stale_refresh_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(_world("refreshed", False),),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.NOT_SENT,
                    "dom",
                    False,
                    ActionError.STALE_BINDING,
                ),
            ),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.current_world.observation_id == "refreshed"
        assert state.execution_count == 0
        assert policy.turns == 2
        assert environment.execute_calls == 1
        assert environment.capture_calls == 1
        assert environment.dispatched_requests == []
        assert [item.reason for item in state.workspace.recent_steps] == [
            "binding_refreshed",
            "agent_aborted:user_request",
        ]

    asyncio.run(scenario())


def test_model_latency_cannot_expire_the_current_observation_action_space() -> None:
    @dataclass
    class SlowPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            assert context.actions.options
            await asyncio.sleep(0.03)
            return SelectAction(
                context.context_id,
                context.actions.options[0].action_id,
                tool_call_id="provider-call:slow-current-world",
            )

    async def scenario() -> None:
        before = _world("slow-before", False)
        source = before.sources[0]
        expiring_source = replace(
            source,
            bindings=(replace(source.bindings[0], expires_at_s=1.0),),
        )
        fused = WorldFusion().fuse((expiring_source,))
        assert fused.observation is not None
        policy = SlowPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("slow_policy_currentness_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=fused.observation,
            post_observations=(_world("slow-after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert policy.turns == 1
        assert environment.execute_calls == 1
        assert len(environment.dispatched_requests) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "correctable_error",
    (
        ActionError.INVALID_PARAMETERS,
        ActionError.DESTINATION_OUTSIDE_ENVIRONMENT,
    ),
)
def test_correctable_not_sent_returns_same_call_failure_for_reselection(
    correctable_error: ActionError,
) -> None:
    @dataclass
    class ReselectingPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id="provider-call:invalid",
                )
            assert context.last_step is not None
            assert context.last_step.status_after is RunStatus.RUNNING
            assert context.last_step.feedback == f"action_not_sent:{correctable_error.value}"
            assert context.last_step.execution_receipts is not None
            assert context.last_step.execution_receipts.execution_count == 0
            terminal = context.last_step.execution_receipts.terminal_failure
            assert terminal is not None
            assert terminal.permits_reselection is True
            assert terminal.error is correctable_error
            return Abort(context.context_id, "typed failure observed", AbortCategory.USER_REQUEST)

    async def scenario() -> None:
        policy = ReselectingPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("invalid_parameter_reselection_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.NOT_SENT,
                    "dom",
                    False,
                    correctable_error,
                ),
            ),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.current_world.observation_id == "before"
        assert state.execution_count == 0
        assert policy.turns == 2
        assert environment.execute_calls == 1
        assert environment.capture_calls == 0
        assert environment.dispatched_requests == []
        assert [item.reason for item in state.workspace.recent_steps] == [
            f"action_not_sent:{correctable_error.value}",
            "agent_aborted:user_request",
        ]

    asyncio.run(scenario())


def test_post_dispatch_evaluator_exception_is_typed_and_never_fabricates_unknown(tmp_path) -> None:
    class FailingPostDispatchEvaluator(CoreTaskEvaluator):
        async def evaluate(self, task, observation):
            if observation.observation_id == "after-failure":
                raise RuntimeError("native projection failed")
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        trace = RunTraceRecorder(tmp_path / "trace")
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            CoreActionOutcomeProjector(),
            FailingPostDispatchEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("typed_evaluator_failure_test"),
            trace_sink=trace,
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before-failure", False),
            post_observations=(_world("after-failure", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.FAILED
        assert state.current_task_evaluation is None
        assert state.runtime_failure is not None
        assert state.runtime_failure.stage.value == "evaluation"
        assert state.runtime_failure.kind.value == "internal"
        assert state.execution_count == 1
        failures = [event for event in trace.events if event["event"] == "native_evaluator_failed"]
        assert len(failures) == 1
        assert failures[0]["observation_id"] == "after-failure"
        assert failures[0]["phase"] == "evaluator_call"

    asyncio.run(scenario())


def test_same_no_effect_element_enter_is_physically_sent_at_most_twice() -> None:
    @dataclass
    class SearchPolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            operation = "type_text" if self.turns == 1 else "press_key"
            option = next(item for item in context.complete_actions if item.operation == operation)
            parameters = {"text": "Pittsburgh"} if operation == "type_text" else {"key": "Enter"}
            return SelectAction(context.context_id, option.action_id, parameters)

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "search result has not appeared",
            )

    async def scenario() -> None:
        task = TaskGoal(
            "search-enter-repeat",
            "Type a search and submit it.",
            allowed_effects=("value_changed", "form_submitted"),
            risk_profile=RiskProfile.LOW,
        )
        policy = SearchPolicy()
        monitor = EpisodeMonitor()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            DispatchPostconditionProjector(),
            IncompleteEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("search_enter_repeat_regression"),
            episode_monitor=monitor,
        )
        environment = ScriptedEnvironment(
            initial_observation=_search_fixture_observation("search-empty", ""),
            post_observations=(
                _search_fixture_observation("search-filled", "Pittsburgh"),
                _search_fixture_observation("search-enter-1", "Pittsburgh"),
                _search_fixture_observation("search-enter-2", "Pittsburgh"),
            ),
            results=tuple(ActionResult("*", DispatchStatus.SENT, "dom", True) for _ in range(3)),
        )

        state = await runtime.run_task(environment, task)
        snapshot = snapshot_episode(state, episode_monitor=monitor)

        assert state.status is RunStatus.BLOCKED
        # Two no-effect Enter dispatches trigger recovery. The next two exact
        # policy replays are both rejected before dispatch: the first returns
        # one bounded fallback turn, and the second closes the stalled run.
        assert policy.turns == 5
        assert environment.execute_calls == 3
        assert [item.intent.semantic_action for item in environment.dispatched_requests] == [
            "type_text",
            "press_key",
            "press_key",
        ]
        assert state.last_step is not None
        assert isinstance(state.last_step.decision, ToolRejectedResult)
        assert state.last_step.decision.result["kind"] == "prohibited_attempt_rejected"
        assert state.last_step.decision.result["dispatch"] == "not_sent"
        assert state.last_step.execution_receipts is None
        assert state.last_step.feedback == "episode_monitor_blocked:control_stalled"
        assert state.workspace.recent_steps[-1].reason == "episode_monitor_blocked:control_stalled"
        assert monitor.same_attempt_streak == 4
        assert monitor.no_progress_count == 4
        assert snapshot.same_attempt_streak == 4
        assert snapshot.no_progress_count == 4
        assert snapshot.latest_semantic_attempt_key_digest.startswith("sha256:")
        assert snapshot.latest_control_reason_code == "control_stalled"
        assert snapshot.latest_control_owner == "episode_monitor"

    asyncio.run(scenario())


def test_repeated_keyboard_navigation_is_dispatched_while_each_fresh_world_advances() -> None:
    @dataclass
    class AutocompletePolicy:
        turns: int = 0
        feedback_kinds: tuple[str, ...] = ()

        async def decide(self, context):
            self.turns += 1
            self.feedback_kinds += (str(context.control_feedback.get("kind", "")),)
            option = next(item for item in context.complete_actions if item.operation == "press_key")
            return SelectAction(context.context_id, option.action_id, {"key": "ArrowDown"})

    class AutocompleteEvaluator:
        async def evaluate(self, task, observation):
            value = next(item for item in observation.targets if item.target_id == "autocomplete-search").state["value"]
            status = (
                TaskEvaluationStatus.COMPLETE
                if value == "Shanksville, Pennsylvania"
                else TaskEvaluationStatus.INCOMPLETE
            )
            evidence = next(
                item.fact_id
                for item in observation.facts
                if item.subject_id == "autocomplete-search" and item.predicate == "value"
            )
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                status,
                "autocomplete value check",
                completion_evidence_refs=(evidence,) if status is TaskEvaluationStatus.COMPLETE else (),
            )

    async def scenario() -> None:
        task = TaskGoal(
            "autocomplete-navigation",
            "Choose Shanksville, Pennsylvania from the autocomplete suggestions.",
            allowed_effects=("external_ui_interaction",),
            risk_profile=RiskProfile.LOW,
        )
        policy = AutocompletePolicy()
        monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            ProductionActionOutcomeProjector(),
            AutocompleteEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("autocomplete_navigation_regression"),
            episode_monitor=monitor,
        )
        environment = ScriptedEnvironment(
            initial_observation=_autocomplete_fixture_observation("autocomplete-0", "Shanksville", 0),
            post_observations=(
                _autocomplete_fixture_observation("autocomplete-1", "Shanksville", 1),
                _autocomplete_fixture_observation("autocomplete-2", "Shanksville, PA", 2),
                _autocomplete_fixture_observation(
                    "autocomplete-3",
                    "Shanksville, Pennsylvania",
                    3,
                ),
            ),
            results=tuple(ActionResult("*", DispatchStatus.SENT, "dom", True) for _ in range(3)),
        )

        state = await runtime.run_task(environment, task)

        assert state.status is RunStatus.DONE
        assert policy.turns == 3
        assert policy.feedback_kinds == ("", "", "")
        assert environment.execute_calls == 3
        assert [item.intent.semantic_action for item in environment.dispatched_requests] == [
            "press_key",
            "press_key",
            "press_key",
        ]
        assert monitor.recovery_count == 0
        assert monitor.same_attempt_streak == 1

    asyncio.run(scenario())


def test_failed_causal_post_acquisition_stops_before_next_policy_turn() -> None:
    async def scenario() -> None:
        policy = CorePolicy("first_action")
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("causal_post_gate_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.SENT,
                    "browsergym",
                    True,
                    adapter_evidence={
                        "browsergym_transition": {
                            "stability_status": "navigation_pending",
                        }
                    },
                ),
            ),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.FAILED
        assert policy.turns == 1
        assert environment.execute_calls == 1
        assert state.current_world.observation_id == "before"

    asyncio.run(scenario())


@pytest.mark.skip(reason="compound action protocol was physically removed; atomic flow has dedicated coverage")
def test_removed_compound_command_witness() -> None:
    @dataclass
    class FormPolicy:
        async def decide(self, context):
            options = sorted(
                (
                    item
                    for item in context.complete_actions
                    if item.operation == "type_text" and item.target_label in {"From", "To"}
                ),
                key=lambda item: item.target_label,
            )
            values = {"From": "CMU", "To": "PIT"}
            return RemovedCompoundDecision(
                context.context_id,
                "form:route",
                tuple(
                    RemovedCompoundField(
                        option.action_id,
                        option.operation,
                        option.target_ref,
                        {"text": values[option.target_label]},
                    )
                    for option in options
                ),
                "provider-call:form",
            )

    class FormEvaluator:
        async def evaluate(self, task, observation):
            values = {item.label: item.state.get("value") for item in observation.targets}
            complete = values == {"From": "CMU", "To": "PIT"}
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE,
                "route fields complete" if complete else "route fields incomplete",
                completion_evidence_refs=(tuple(item.fact_id for item in observation.facts) if complete else ()),
            )

    async def scenario() -> None:
        task = TaskGoal(
            "route-fields",
            "Set both current route fields.",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        runtime = TargetRuntime(
            AgentDecisionPorts(FormPolicy()),
            ProductionActionOutcomeProjector(),
            FormEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("form_command_integration"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_form_world("form-before", "", ""),
            post_observations=(_form_world("form-after", "CMU", "PIT"),),
            results=(
                ActionResult("*", DispatchStatus.SENT, "dom", True),
                ActionResult("*", DispatchStatus.SENT, "dom", True),
            ),
        )
        instrumentation = BenchmarkInstrumentation()
        counted_environment = CountingEnvironment(environment, instrumentation, frozenset())

        state = await runtime.run_task(counted_environment, task)

        assert state.status is RunStatus.DONE
        assert state.execution_count == 2
        assert environment.execute_calls == 1
        assert len(environment.dispatched_requests) == 2
        assert state.last_step is not None
        assert state.last_step.execution_receipts is not None
        assert state.last_step.decision.form_key == "form:route"
        assert instrumentation.effectful_dispatches == 2
        assert instrumentation.environment_post_acquisitions == 1

    asyncio.run(scenario())


@pytest.mark.skip(reason="compound action protocol was physically removed; atomic flow has dedicated coverage")
def test_removed_compound_navigation_witness() -> None:
    @dataclass
    class RoutePolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns in {1, 3}:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            if self.turns == 2:
                options = sorted(context.complete_actions, key=lambda item: item.target_label)
                return RemovedCompoundDecision(
                    context.context_id,
                    "form:route",
                    tuple(
                        RemovedCompoundField(
                            option.action_id,
                            option.operation,
                            option.target_ref,
                            {"text": f"value-{index}"},
                        )
                        for index, option in enumerate(options, 1)
                    ),
                )
            if self.turns == 4:
                return SearchPageContentResult(
                    context.context_id,
                    "search_page_content",
                    {"query": "result"},
                    {"items": ({"text": "route result"},)},
                )
            if self.turns == 5:
                return ReadRegionResult(
                    context.context_id,
                    "read_region",
                    {"region_ref": "R1"},
                    {"items": ({"text": "route result"},)},
                )
            if self.turns == 6:
                return Abort(context.context_id, "route inspected", AbortCategory.USER_REQUEST)
            raise AssertionError("unexpected policy turn")

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "route still active",
            )

    async def scenario() -> None:
        task = TaskGoal(
            "continuous-route",
            "Navigate, fill, submit, and inspect the result.",
            allowed_effects=("shared_state_enabled", "value_changed"),
            risk_profile=RiskProfile.LOW,
        )
        policy = RoutePolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            IncompleteEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("continuous_route_integration"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("route-navigation", False),
            post_observations=(
                _form_world("route-form", "", ""),
                _world("route-submit", False),
                _world("route-result", False),
            ),
            results=tuple(ActionResult("*", DispatchStatus.SENT, "dom", True) for _ in range(4)),
        )

        state = await runtime.run_task(environment, task)

        assert state.status is RunStatus.CANCELLED
        assert policy.turns == 6
        assert state.execution_count == 4
        assert [step.semantic_action for step in state.workspace.recent_steps] == [
            "select_action",
            "search_page_content",
            "read_region",
            "abort",
        ]
        assert isinstance(state.last_step.decision, Abort)

    asyncio.run(scenario())


@pytest.mark.skip(reason="compound action protocol was physically removed; atomic uncertainty has dedicated coverage")
def test_removed_compound_cancellation_witness() -> None:
    @dataclass
    class FormPolicy:
        async def decide(self, context):
            options = sorted(
                (
                    item
                    for item in context.complete_actions
                    if item.operation == "type_text" and item.target_label in {"From", "To"}
                ),
                key=lambda item: item.target_label,
            )
            return RemovedCompoundDecision(
                context.context_id,
                "form:route",
                tuple(
                    RemovedCompoundField(
                        option.action_id,
                        option.operation,
                        option.target_ref,
                        {"text": option.target_label},
                    )
                    for option in options
                ),
                "provider-call:cancelled-form",
            )

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "cancelled command is not task completion",
            )

    @dataclass
    class CancellingFormEnvironment(ScriptedEnvironment):
        async def execute_removed_compound(self, command):
            outcome = await super().execute_removed_compound(command)
            cancelled = replace(
                outcome,
                results=(
                    outcome.results[0],
                    ActionResult(
                        outcome.results[1].request_id,
                        DispatchStatus.SENT_UNKNOWN,
                        outcome.results[1].backend,
                        False,
                        ActionError.CANCELLED,
                    ),
                ),
                failed_field_index=1,
            )
            raise RemovedCompoundCancellation(cancelled)

    async def scenario() -> None:
        task = TaskGoal(
            "cancelled-route-fields",
            "Attempt both current route fields.",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        runtime = TargetRuntime(
            AgentDecisionPorts(FormPolicy()),
            ProductionActionOutcomeProjector(),
            IncompleteEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("compound_cancellation_commit"),
        )
        raw_environment = CancellingFormEnvironment(
            initial_observation=_form_world("cancel-before", "", ""),
            post_observations=(_form_world("cancel-after", "From", "To"),),
            results=(
                ActionResult("*", DispatchStatus.SENT, "dom", True),
                ActionResult("*", DispatchStatus.SENT, "dom", True),
            ),
        )
        instrumentation = BenchmarkInstrumentation()
        environment = CountingEnvironment(raw_environment, instrumentation, frozenset())

        state = await runtime.run_task(environment, task)
        snapshot = snapshot_episode(state)
        case = project_case_result(
            "compound-cancelled",
            state,
            instrumentation,
            1.0,
            "",
            final_snapshot=snapshot,
        )

        assert state.status is RunStatus.CANCELLED
        assert state.current_world.observation_id == "cancel-after"
        assert state.execution_count == 2
        assert state.sent_unknown_count == 1
        assert state.last_step is not None
        assert state.last_step.execution_receipts is not None
        assert state.last_step.execution_receipts.completion is ExecutionCompletion.CANCELLED
        assert state.last_step.execution_receipts.cancellation_phase is ExecutionCancellationPhase.DISPATCH
        assert snapshot.execution_count == 2
        assert snapshot.sent_unknown_count == 1
        assert snapshot.last_decision_kind == "removed_compound"
        assert instrumentation.effectful_dispatches == 2
        assert case.measurements["executions"].value == 2
        assert case.measurements["sent_unknown_count"].value == 1

    asyncio.run(scenario())


def test_sent_unknown_with_fresh_proven_effect_continues_without_user_wait() -> None:
    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("uncertain_dispatch_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.EXECUTION_FAILED,
                ),
            ),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert state.current_world.observation_id == "after"
        assert state.execution_count == 1
        assert environment.execute_calls == 1
        assert environment.capture_calls == 0
        assert state.last_step is not None
        assert state.last_step.execution_receipts.receipts[-1].result.dispatch_status is DispatchStatus.SENT_UNKNOWN
        assert state.last_step.action_outcome.local_postcondition is LocalPostconditionStatus.SATISFIED

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("raised", "expected_status", "expected_feedback"),
    (
        (asyncio.CancelledError(), RunStatus.CANCELLED, "action_outcome_cancelled"),
        (RuntimeError("projector failed"), RunStatus.FAILED, "action_outcome_failed"),
    ),
)
def test_post_dispatch_projector_failure_commits_receipt_before_terminal_state(
    raised,
    expected_status,
    expected_feedback,
) -> None:
    class FailingProjector:
        async def evaluate(self, *args):
            del args
            raise raised

    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            FailingProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("post_dispatch_projector_failure"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before-projector-failure", False),
            post_observations=(_world("after-projector-failure", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await runtime.run_task(environment, _task())

        assert environment.execute_calls == 1
        assert state.execution_count == 1
        assert state.status is expected_status
        assert state.last_step is not None
        assert state.last_step.feedback == expected_feedback
        assert state.last_step.execution_receipts is not None
        assert state.last_step.execution_receipts.execution_count == 1
        if expected_status is RunStatus.CANCELLED:
            assert state.last_step.execution_receipts.cancellation_phase is ExecutionCancellationPhase.EVALUATION
        else:
            assert state.runtime_failure is not None
            assert state.runtime_failure.stage.value == "evaluation"

    asyncio.run(scenario())


def test_sent_unknown_gets_one_bounded_fresh_recapture_before_control_recovery() -> None:
    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("uncertain_dispatch_recapture_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(),
            independent_observations=(_world("recovered", True),),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.EXECUTION_FAILED,
                ),
            ),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert state.current_world.observation_id == "recovered"
        assert environment.execute_calls == 1
        assert environment.capture_calls == 1
        assert state.last_step is not None
        assert state.last_step.execution_receipts is not None
        assert state.last_step.execution_receipts.receipts[-1].after_observation_id == "recovered"

    asyncio.run(scenario())


def test_sent_with_failed_post_acquisition_gets_one_bounded_fresh_recapture() -> None:
    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("sent_dispatch_recapture_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(),
            independent_observations=(_world("recovered", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert state.current_world.observation_id == "recovered"
        assert environment.execute_calls == 1
        assert environment.capture_calls == 1
        assert state.last_step is not None
        assert state.last_step.execution_receipts is not None
        assert state.last_step.execution_receipts.receipts[-1].after_observation_id == "recovered"

    asyncio.run(scenario())


def test_sent_unknown_is_committed_once_without_automatic_replay() -> None:
    async def scenario() -> None:
        task = TaskGoal(
            "set-shared-value",
            "Set shared value",
            allowed_effects=("shared_value_changed",),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(max_turns=1, max_observations=2),
        )

        @dataclass
        class TextPolicy:
            async def decide(self, context):
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    {"text": "done"},
                    tool_call_id="provider-call:text",
                )

        runtime = TargetRuntime(
            AgentDecisionPorts(TextPolicy()),
            ProductionActionOutcomeProjector(),
            TextTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("sent_unknown_no_replay_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_text_world("before", ""),
            post_observations=(_text_world("first-post", ""),),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.EXECUTION_FAILED,
                ),
            ),
        )

        state = await runtime.run_task(environment, task)

        assert state.status is RunStatus.BLOCKED
        assert environment.execute_calls == 1
        assert state.execution_count == 1
        assert state.last_step is not None
        assert state.last_step.execution_receipts.execution_count == 1
        assert state.last_step.execution_receipts.receipts[0].result.dispatch_status is DispatchStatus.SENT_UNKNOWN
        assert state.last_step.action_outcome.local_postcondition is LocalPostconditionStatus.UNKNOWN
        batch = state.last_step.execution_receipts
        assert batch.completion is ExecutionCompletion.UNKNOWN
        with pytest.raises(ValueError, match="complete execution"):
            replace(batch, completion=ExecutionCompletion.COMPLETE)
        terminal_failure = ActionResult(
            batch.receipts[-1].request.request_id,
            DispatchStatus.NOT_SENT,
            batch.receipts[-1].result.backend,
            False,
            ActionError.EXECUTION_FAILED,
        )
        with pytest.raises(ValueError, match="partial execution"):
            replace(
                batch,
                completion=ExecutionCompletion.PARTIAL,
                terminal_failure=terminal_failure,
            )
        with pytest.raises(ValueError, match="cancellation truth"):
            ExecutionReceiptBatch(
                (batch.receipts[-1],),
                ExecutionCompletion.CANCELLED,
            )
        cancelled_failure = ActionResult(
            batch.receipts[-1].request.request_id,
            DispatchStatus.NOT_SENT,
            batch.receipts[-1].result.backend,
            False,
            ActionError.CANCELLED,
        )
        with pytest.raises(ValueError, match="partial execution"):
            ExecutionReceiptBatch(
                (batch.receipts[-1],),
                ExecutionCompletion.PARTIAL,
                cancelled_failure,
            )
        with pytest.raises(ValueError, match="cancellation truth"):
            ExecutionReceiptBatch(
                (),
                ExecutionCompletion.CANCELLED,
                cancellation_phase=ExecutionCancellationPhase.POST_CAPTURE,
            )
        cancelled_receipt = replace(
            batch.receipts[0],
            result=replace(batch.receipts[0].result, error=ActionError.CANCELLED),
        )
        with pytest.raises(ValueError, match="unknown execution"):
            ExecutionReceiptBatch((cancelled_receipt,), ExecutionCompletion.UNKNOWN)
        with pytest.raises(ValueError, match="unknown execution"):
            ExecutionReceiptBatch(
                batch.receipts,
                ExecutionCompletion.UNKNOWN,
                terminal_failure=terminal_failure,
            )
        with pytest.raises(ValueError, match="cancellation truth"):
            ExecutionReceiptBatch(
                (cancelled_receipt,),
                ExecutionCompletion.CANCELLED,
                cancellation_phase=ExecutionCancellationPhase.EVALUATION,
            )

    asyncio.run(scenario())


def test_failed_recapture_with_live_session_blocks_without_replay() -> None:
    async def scenario() -> None:
        runtime = TargetRuntime(
            AgentDecisionPorts(CorePolicy("first_action")),
            DispatchPostconditionProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("environment_recovery_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(),
            independent_observations=(),
            repeat_last_observation=False,
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.EXECUTION_FAILED,
                ),
            ),
        )

        async def session_health(_request):
            return SessionHealth(
                SessionHealthStatus.ALIVE,
                page_closed=False,
                browser_connected=True,
            )

        environment.session_health = session_health
        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.BLOCKED
        assert environment.execute_calls == 1
        assert environment.capture_calls == 1
        assert state.last_step is not None
        assert state.last_step.feedback == "post_action_acquisition_failed:environment_recovery"

    asyncio.run(scenario())


def test_core_runtime_owns_count_result_and_reuses_same_world_derivations(monkeypatch) -> None:
    from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex

    original = WorldDeliveryIndex.from_observation
    index_build_count = 0

    def counted(cls, *args, **kwargs):
        del cls
        nonlocal index_build_count
        index_build_count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(WorldDeliveryIndex, "from_observation", classmethod(counted))

    async def scenario() -> None:
        runtime = _runtime("count_children")
        environment = ScriptedEnvironment(initial_observation=_count_world())

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.execution_count == 0
        assert state.observation_count == 1
        assert state.workspace.recent_steps[0].semantic_summary["information_delta"] == "new_information"
        assert "result" not in state.workspace.recent_steps[0].semantic_summary
        assert index_build_count == 1

    asyncio.run(scenario())


def test_action_search_is_additive_to_the_base_page_on_the_next_turn() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        state = await _runtime("action_page").run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.last_step is not None
        assert state.last_step.feedback == "agent_aborted:user_request"
        assert state.execution_count == 0
        case = project_case_result(
            "abort-projection",
            state,
            BenchmarkInstrumentation(),
            1.0,
            "",
            final_snapshot=snapshot_episode(state),
        )
        assert case.last_decision_kind == "abort"
        assert case.runtime_reason_code == "agent_aborted"

    asyncio.run(scenario())


def test_wait_uses_runtime_boundary_then_refreshes_observation() -> None:
    @dataclass
    class RecordingWaitController:
        waits: list[int]

        async def wait(self, max_wait_ms: int) -> None:
            self.waits.append(max_wait_ms)

    async def scenario() -> None:
        waiter = RecordingWaitController([])
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(_world("after-wait", False),),
        )
        state = await _runtime("wait", wait_controller=waiter).run_task(
            environment,
            _task(),
        )

        assert state.status is RunStatus.CANCELLED
        assert state.current_world.observation_id == "after-wait"
        assert state.observation_count == 2
        assert state.waited_ms == 5
        assert waiter.waits == [5]

    asyncio.run(scenario())


def test_user_input_resumes_with_one_consecutive_task_revision() -> None:
    async def scenario() -> None:
        runtime = _runtime("ask_user")
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        task = _task()
        paused = await runtime.run_task(environment, task)

        assert paused.status is RunStatus.WAITING_USER
        revised = replace(task, inputs={"value": "provided"}, revision=2)
        resumed = await runtime.resume_user(environment, revised, paused)

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.task_revision == 2
        assert resumed.step_count == 2

    asyncio.run(scenario())


def test_confirmation_approval_executes_the_exact_pending_semantics() -> None:
    async def scenario() -> None:
        runtime = _runtime("confirm_once")
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        task = replace(_task(), risk_profile=RiskProfile.MEDIUM)
        paused = await runtime.run_task(environment, task)

        assert paused.status is RunStatus.WAITING_CONFIRMATION
        resumed = await runtime.resume_confirmation(
            environment,
            task,
            paused,
            approved=True,
        )

        assert resumed.status is RunStatus.DONE
        assert resumed.execution_count == 1
        assert resumed.step_count == 1
        assert environment.execute_calls == 1

    asyncio.run(scenario())


def test_confirmation_decline_returns_to_the_model_without_execution() -> None:
    async def scenario() -> None:
        runtime = _runtime("confirm_once")
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        task = replace(_task(), risk_profile=RiskProfile.MEDIUM)
        paused = await runtime.run_task(environment, task)
        resumed = await runtime.resume_confirmation(
            environment,
            task,
            paused,
            approved=False,
        )

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.execution_count == 0
        assert resumed.step_count == 2
        assert environment.execute_calls == 0

    asyncio.run(scenario())


def test_nonterminal_action_is_visible_before_the_next_decision() -> None:
    @dataclass
    class FeedbackAwarePolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                assert not context.workspace.recent_steps
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            previous = context.workspace.recent_steps
            assert len(previous) == 1
            assert previous[0].semantic_action == "activate"
            assert previous[0].target is not None
            assert previous[0].target.role == "button"
            assert previous[0].target.label == "Enable shared state"
            assert previous[0].dispatch_status == DispatchStatus.SENT
            assert previous[0].local_postcondition == LocalPostconditionStatus.UNKNOWN
            assert previous[0].transition["observed_change"] == ObservedChange.UNCHANGED
            assert previous[0].transition["evidence_method"] == EvidenceMethod.STRUCTURAL
            assert previous[0].task_evaluation_status == TaskEvaluationStatus.INCOMPLETE
            assert previous[0].reason == "state did not change"
            assert previous[0].semantic_summary["feedback_code"] == "action_unchanged_change_strategy"
            assert (
                previous[0].transition.items()
                >= {
                    "role": "button",
                    "label": "Enable shared state",
                    "before_state": {"enabled": False},
                    "after_state": {"enabled": False},
                    "semantic_change": "unchanged",
                    "observed_change": "unchanged",
                    "evidence_method": "structural",
                }.items()
            )
            assert "before_world_fingerprint" not in previous[0].transition
            assert "after_world_fingerprint" not in previous[0].transition
            return Abort(context.context_id, "feedback projection verified", AbortCategory.USER_REQUEST)

    class NoEffectActionOutcomeProjector:
        async def evaluate(self, task, before, request, result, after, public_world_delta):
            del task, result
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNCHANGED,
                LocalPostconditionStatus.UNKNOWN,
                EvidenceMethod.STRUCTURAL,
                "state did not change",
                (after.facts[0].fact_id,),
            )

    async def scenario() -> None:
        policy = FeedbackAwarePolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            NoEffectActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_core_loop_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert policy.turns == 2
        assert len(state.workspace.recent_steps) == 2
        assert state.last_step is not None
        assert state.last_step.policy_observation is not None
        assert environment.execute_calls == 1

    asyncio.run(scenario())

import asyncio
from dataclasses import dataclass, field, replace

import pytest

from affordance_runtime.actions import ActionBinding, ActionRisk
from affordance_runtime.agent import (
    Abort,
    AskUser,
    EpisodeBudget,
    EpisodeYieldReason,
    PinFactResult,
    ReadRegionResult,
    RequestActionPage,
    RunStatus,
    SearchPageContentResult,
    SelectAction,
    Wait,
    WorkingFact,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.decisions import AbortCategory, FormFieldUpdate, SetFormFields
from affordance_runtime.agent.episode_snapshot import snapshot_episode
from affordance_runtime.agent.policy import AgentDecisionPorts
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
    FormFieldsExecutionCancelled,
    SessionHealth,
    SessionHealthStatus,
)
from affordance_runtime.goals import NotRequired, NotRequiredGoalCompiler
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
from affordance_runtime.world.acquisition import ObservationRequestKind, WorldObservationRequest


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
            assert context.actions.active_query == "shared state"
            assert context.recent_steps.items[-1].semantic_action == "find_controls"
            return Abort(context.context_id, "page observed", AbortCategory.USER_REQUEST)
        if self.choice == "wait":
            if self.turns == 1:
                return Wait(context.context_id, "allow interface to settle", 5)
            return Abort(context.context_id, "wait observed", AbortCategory.USER_REQUEST)
        if self.choice == "ask_user":
            if self.turns == 1:
                return AskUser(context.context_id, "Which value?", ("value",))
            assert context.task.public_inputs["value"] == "provided"
            assert context.recent_steps.items[-1].reason == "user_input_received"
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
            step = context.recent_steps.items[-1]
            assert step.semantic_action == "count_children"
            assert step.semantic_summary["result"] == {
                "counts": {},
                "total": 5,
            }
            return Abort(context.context_id, "count observed", AbortCategory.USER_REQUEST)
        if self.choice == "confirm_once":
            if self.turns == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            assert context.recent_steps.items[-1].reason == "confirmation_declined"
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
    async def evaluate(self, task, before, request, result, after):
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
    async def evaluate(self, task, before, request, result, after):
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


def test_core_executes_one_bound_form_command_through_the_world_port() -> None:
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
            return SetFormFields(
                context.context_id,
                "form:route",
                tuple(
                    FormFieldUpdate(
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


def test_production_core_keeps_navigation_form_submit_and_result_reads_in_one_episode() -> None:
    @dataclass
    class RoutePolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns in {1, 3}:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            if self.turns == 2:
                options = sorted(context.complete_actions, key=lambda item: item.target_label)
                return SetFormFields(
                    context.context_id,
                    "form:route",
                    tuple(
                        FormFieldUpdate(
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
                candidate = context.evidence_candidates.candidates[0]
                canonical = context.private_fact_bindings[candidate.fact_ref]
                record = context.evidence_index.resolve_record(canonical)
                assert record is not None
                fact = WorkingFact("route_result", record, context.current_step_index, "retain route result")
                return PinFactResult(
                    context.context_id,
                    "pin_fact",
                    {"key": "route_result", "evidence_ref": candidate.fact_ref},
                    {"key": "route_result", "value": fact.value},
                    working_fact=fact,
                )
            return Abort(context.context_id, "route inspected", AbortCategory.USER_REQUEST)

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
        assert policy.turns == 7
        assert state.execution_count == 4
        assert [step.semantic_action for step in state.recent_steps][-3:] == [
            "search_page_content",
            "read_region",
            "pin_fact",
        ]
        assert isinstance(state.last_step.decision, Abort)

    asyncio.run(scenario())


def test_compound_cancellation_is_committed_before_snapshot_projection() -> None:
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
            return SetFormFields(
                context.context_id,
                "form:route",
                tuple(
                    FormFieldUpdate(
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
        async def execute_form_fields(self, command):
            outcome = await super().execute_form_fields(command)
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
            raise FormFieldsExecutionCancelled(cancelled)

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
        assert (
            state.last_step.execution_receipts.cancellation_phase
            is ExecutionCancellationPhase.DISPATCH
        )
        assert snapshot.execution_count == 2
        assert snapshot.sent_unknown_count == 1
        assert snapshot.last_decision_kind == "set_form_fields"
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
            assert (
                state.last_step.execution_receipts.cancellation_phase
                is ExecutionCancellationPhase.EVALUATION
            )
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
            post_observations=(
                _text_world("first-post", ""),
            ),
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
        assert state.last_step.action_outcome.local_postcondition is LocalPostconditionStatus.UNSATISFIED
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


def test_failed_recapture_with_live_session_yields_environment_recovery() -> None:
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

        assert state.status is RunStatus.YIELDED
        assert state.yield_reason is EpisodeYieldReason.ENVIRONMENT_RECOVERY
        assert environment.execute_calls == 1
        assert environment.capture_calls == 1
        assert state.last_step is not None
        assert state.last_step.feedback == "post_action_acquisition_failed:environment_recovery"

    asyncio.run(scenario())


def test_core_runtime_owns_count_result_and_pairs_it_with_the_request() -> None:
    async def scenario() -> None:
        runtime = _runtime("count_children")
        environment = ScriptedEnvironment(initial_observation=_count_world())

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.execution_count == 0
        assert state.observation_count == 1
        assert state.recent_steps[0].semantic_summary["result"] == {
            "counts": {},
            "total": 5,
        }

    asyncio.run(scenario())


def test_action_page_is_installed_for_the_next_turn() -> None:
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
        assert case.runtime_reason_code == "abort_user_request"

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
                assert not context.recent_steps.items
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            previous = context.recent_steps.items
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
                    "before_world": "before",
                    "after_world": "after",
                    "before_state": {"enabled": False},
                    "after_state": {"enabled": False},
                    "observed_change": "unchanged",
                    "evidence_method": "structural",
                }.items()
            )
            assert (
                previous[0].transition["before_world_fingerprint"] == previous[0].transition["after_world_fingerprint"]
            )
            return Abort(context.context_id, "feedback projection verified", AbortCategory.USER_REQUEST)

    class NoEffectActionOutcomeProjector:
        async def evaluate(self, task, before, request, result, after):
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
        assert len(state.recent_steps) == 1
        assert state.last_step is not None
        assert state.last_step.policy_observation is not None
        assert environment.execute_calls == 1

    asyncio.run(scenario())


def test_executor_episode_can_yield_and_reinitialize_from_fresh_world_without_reset() -> None:
    @dataclass
    class EpisodePolicy:
        actions: list[str]

        async def decide(self, context):
            action = self.actions.pop(0)
            if action == "activate":
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id="provider-call:episode-1",
                )
            return Abort(context.context_id, "episode observed fresh world", AbortCategory.USER_REQUEST)

    @dataclass(frozen=True)
    class RecordingContextBuilder(ContextBuilder):
        seen_observation_ids: list[str] = field(default_factory=list)

        def build(self, task, observation, action_space, task_evaluation, *args, **kwargs):
            self.seen_observation_ids.append(observation.observation_id)
            return super().build(task, observation, action_space, task_evaluation, *args, **kwargs)

    @dataclass
    class ExplodingGoalCompiler:
        calls: int = 0

        async def compile(self, request):
            del request
            self.calls += 1
            raise AssertionError("episode initialization must not call GoalCompiler")

    async def scenario() -> None:
        policy = EpisodePolicy(["activate", "abort"])
        context_builder = RecordingContextBuilder()
        compiler = ExplodingGoalCompiler()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            context_builder=context_builder,
            goal_compiler=compiler,
        )
        loop = runtime.build_loop()
        task = _task()
        goal_resolution = NotRequired(task.revision, "planner_supplied_episode_goal")
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after-action", False),),
            independent_observations=(_world("fresh-current", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        initial = await environment.reset(task)
        assert initial.observation is not None
        first = await loop.initialize_from_world(
            task,
            initial.observation,
            goal_resolution,
            budget=EpisodeBudget.explicit(1),
            yield_on_budget_exhaustion=True,
        )
        yielded = await loop.continue_run(environment, task, first)

        assert yielded.status is RunStatus.YIELDED
        assert yielded.current_world.observation_id == "after-action"
        assert yielded.recent_steps[-1].semantic_action == "activate"
        assert environment.reset_calls == 1

        refreshed = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "fresh world before next executor episode",
            )
        )
        assert refreshed.observation is not None
        second = await loop.initialize_from_world(
            task,
            refreshed.observation,
            goal_resolution,
            budget=EpisodeBudget.explicit(1),
            yield_on_budget_exhaustion=True,
        )
        resumed = await loop.continue_run(environment, task, second)

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.current_world.observation_id == "fresh-current"
        assert environment.reset_calls == 1
        assert context_builder.seen_observation_ids == ["before", "fresh-current"]
        assert compiler.calls == 0

    asyncio.run(scenario())

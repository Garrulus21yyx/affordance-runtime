import asyncio
from dataclasses import dataclass, field

from affordance_runtime.agent import Abort, AgentDecisionPackage, AgentLoop, SelectAction
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingPolicy,
)
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.task.frontier import (
    TASK_OUTCOME_REQUIREMENT_ID,
    ObjectiveVerificationDisposition,
    synchronize_verified_task_state,
    verify_active_objective,
)
from affordance_runtime.task.frontier_contracts import (
    ActiveObjective,
    LiteralExpected,
    NoObjectiveOperation,
    ObjectiveCheckpointStatus,
    ProposeObjective,
    TargetFieldEquals,
    TargetPresent,
    VerifiedRequirement,
    VerifiedTaskState,
)
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionBinding,
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _task() -> TaskGoal:
    return TaskGoal(
        "task:fill-submit",
        "Enter desired, then submit",
        allowed_effects=("value_changed", "submitted"),
        success_criteria=({
            "criterion_id": "criterion:submitted",
            "target_id": "target:submit",
            "state": {"submitted": True},
        },),
        risk_profile=RiskProfile.LOW,
        loop_budget=LoopBudget(6, 8),
    )


def _binding(observation_id: str, target_id: str, action: str, effect: str) -> ActionBinding:
    schema = (
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        if action == "fill"
        else {"type": "object", "properties": {}, "additionalProperties": False}
    )
    return ActionBinding(
        f"binding:{observation_id}:{target_id}",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{observation_id}:{target_id}",
        target_id,
        target_id,
        "dom",
        "dom",
        action,
        action,
        "local_reversible",
        (effect,),
        schema,
        {"private_route": target_id},
    )


def _world(observation_id: str, value: str, submitted: bool) -> WorldObservation:
    targets = (
        SemanticTarget("target:text", "textbox", "Text", {"value": value}),
        SemanticTarget("target:submit", "button", "Submit", {"submitted": submitted}),
    )
    facts = (
        StateFact(f"fact:{observation_id}:value", "target:text", "value", value, observation_id),
        StateFact(
            f"fact:{observation_id}:submitted",
            "target:submit",
            "submitted",
            submitted,
            observation_id,
        ),
    )
    bindings = (
        _binding(observation_id, "target:text", "fill", "value_changed"),
        _binding(observation_id, "target:submit", "activate", "submitted"),
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
    return WorldObservation(
        observation_id,
        targets,
        facts,
        bindings,
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )


class _TaskEvaluator:
    async def evaluate(self, task, observation):
        submitted = bool(observation.targets[1].state["submitted"])
        ref = observation.facts[1].fact_id
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if submitted else TaskEvaluationStatus.INCOMPLETE,
            "submitted" if submitted else "not submitted",
            (
                CriterionEvaluation(
                    "criterion:submitted",
                    CriterionEvaluationStatus.SATISFIED
                    if submitted
                    else CriterionEvaluationStatus.UNSATISFIED,
                    (ref,),
                    "submission state",
                ),
            ),
            (ref,) if submitted else (),
        )


class _ActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            "public state changed",
            (after.facts[0].fact_id, after.facts[1].fact_id),
        )


@dataclass
class _FrontierPolicy:
    contexts: list[object] = field(default_factory=list)

    async def decide(self, context):
        self.contexts.append(context)
        requirement = context.progress.task_frontier.current_frontier[0]
        if len(self.contexts) == 1:
            option = next(item for item in context.actions.options if item.semantic_action == "fill")
            return AgentDecisionPackage(
                ProposeObjective(
                    (requirement,),
                    TargetFieldEquals(
                        "target:text", "value", LiteralExpected("desired"),
                    ),
                ),
                SelectAction(context.context_id, option.action_id, {"value": "desired"}),
            )
        frontier = context.progress.task_frontier
        assert frontier.active_objective is None
        assert frontier.recent_checkpoints[-1].status == "verified"
        assert frontier.next_objective_required is True
        assert frontier.must_advance_from_objective_id == "objective:1"
        assert frontier.strategy_change_required is True
        option = next(item for item in context.actions.options if item.semantic_action == "activate")
        return AgentDecisionPackage(
            ProposeObjective(
                (requirement,),
                TargetFieldEquals(
                    "target:submit", "submitted", LiteralExpected(True),
                ),
            ),
            SelectAction(context.context_id, option.action_id),
        )


def test_verified_fill_objective_advances_to_submit_in_next_policy_turn() -> None:
    async def scenario() -> None:
        policy = _FrontierPolicy()
        environment = StaticEnvironment(
            [
                _world("observation:before", "", False),
                _world("observation:filled", "desired", False),
                _world("observation:submitted", "desired", True),
            ],
            [
                ActionResult("*", DispatchStatus.SENT, "dom", True),
                ActionResult("*", DispatchStatus.SENT, "dom", True),
            ],
        )
        session = await AgentLoop(
            policy, _ActionEvaluator(), _TaskEvaluator(),
        ).start(_task(), environment)
        result = await session.run_until_pause()

        assert result.status.value == "done"
        assert result.execution_count == 2
        assert len(policy.contexts) == 2
        assert session.state.active_objective is None
        assert [item.status for item in session.state.verified_task_state.objective_checkpoints] == [
            ObjectiveCheckpointStatus.VERIFIED,
            ObjectiveCheckpointStatus.VERIFIED,
        ]

    asyncio.run(scenario())


@dataclass
class _InvalidActionPolicy:
    contexts: list[object] = field(default_factory=list)

    async def decide(self, context):
        self.contexts.append(context)
        if len(self.contexts) == 1:
            return AgentDecisionPackage(
                ProposeObjective(
                    (context.progress.task_frontier.current_frontier[0],),
                    TargetFieldEquals(
                        "target:text", "value", LiteralExpected("desired"),
                    ),
                ),
                SelectAction(context.context_id, "action:not-offered"),
            )
        assert context.progress.task_frontier.active_objective is None
        assert context.control_feedback.violation.contract_owner == "current_action_page"
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            Abort(context.context_id, "fixture complete", "policy"),
        )


def test_valid_objective_and_invalid_action_commit_neither_and_dispatch_zero() -> None:
    async def scenario() -> None:
        policy = _InvalidActionPolicy()
        environment = StaticEnvironment([_world("observation:before", "", False)])
        session = await AgentLoop(
            policy, _ActionEvaluator(), _TaskEvaluator(),
        ).start(_task(), environment)
        await session.run_until_pause()

        assert environment.executed_requests == []
        assert session.state.active_objective is None
        assert session.state.objective_sequence == 0
        assert session.state.verified_task_state.objective_checkpoints == ()

    asyncio.run(scenario())


def test_effect_confirmation_without_predicate_match_keeps_objective_active() -> None:
    observation = _world("observation:unchanged", "wrong", False)
    evaluation = asyncio.run(_TaskEvaluator().evaluate(_task(), observation))
    state = VerifiedTaskState((
        VerifiedRequirement(
            "criterion:submitted", CriterionEvaluationStatus.UNSATISFIED,
        ),
    ), ("criterion:submitted",))
    active = ActiveObjective(
        "objective:1",
        ("criterion:submitted",),
        TargetFieldEquals("target:text", "value", LiteralExpected("desired")),
        "context:1",
    )

    verified = verify_active_objective(
        active,
        state,
        observation,
        evaluation,
        evidence_refs=(observation.facts[0].fact_id,),
    )

    assert verified.disposition is ObjectiveVerificationDisposition.ACTIVE


@dataclass
class _InvalidObjectivePolicy:
    contexts: list[object] = field(default_factory=list)

    async def decide(self, context):
        self.contexts.append(context)
        if len(self.contexts) == 1:
            option = next(item for item in context.actions.options if item.semantic_action == "fill")
            return AgentDecisionPackage(
                ProposeObjective(
                    ("criterion:not-authoritative",),
                    TargetFieldEquals(
                        "target:text", "value", LiteralExpected("desired"),
                    ),
                ),
                SelectAction(context.context_id, option.action_id, {"value": "desired"}),
            )
        feedback = context.control_feedback
        assert feedback.source == "objective_admission"
        assert feedback.violation.contract_owner == "task_frontier"
        assert feedback.violation.code == "unknown_objective_requirement"
        assert feedback.related_objective_operation.kind == "propose"
        assert feedback.related_decision is not None
        assert feedback.related_decision.kind == "select_action"
        assert feedback.related_decision.action_id
        assert feedback.related_decision.target_id == "target:text"
        return AgentDecisionPackage(
            NoObjectiveOperation(),
            Abort(context.context_id, "fixture complete", "policy"),
        )


def test_invalid_objective_returns_typed_feedback_and_dispatches_zero() -> None:
    async def scenario() -> None:
        policy = _InvalidObjectivePolicy()
        environment = StaticEnvironment([_world("observation:before", "", False)])
        session = await AgentLoop(
            policy, _ActionEvaluator(), _TaskEvaluator(),
        ).start(_task(), environment)
        await session.run_until_pause()

        assert len(policy.contexts) == 2
        assert environment.executed_requests == []
        assert session.state.active_objective is None
        assert session.state.objective_sequence == 0
        assert session.state.control_feedback_delivery_total_count == 1

    asyncio.run(scenario())


def test_changed_already_satisfied_predicate_gets_second_repair_turn() -> None:
    class Policy:
        contexts = []

        async def decide(self, context):
            self.contexts.append(context)
            requirement = context.progress.task_frontier.current_frontier[0]
            if len(self.contexts) == 1:
                target_id = "target:text"
            elif len(self.contexts) == 2:
                feedback = context.control_feedback
                assert feedback is not None
                assert feedback.code == "objective_already_satisfied"
                assert feedback.recovery.must_change_fields == (
                    "objective_operation.predicate",
                )
                assert feedback.recovery.retry_allowed is False
                assert feedback.recovery.strategy_change_required is True
                assert feedback.recovery.admissible_objective_operations == (
                    {"kind": "none"},
                    {
                        "kind": "propose",
                        "intended_requirement_ids": ["criterion:submitted"],
                        "predicate": {"kind": "task_outcome_is", "status": "complete"},
                    },
                )
                target_id = "target:submit"
            else:
                assert context.control_feedback is not None
                assert context.control_feedback.code == "objective_already_satisfied"
                return AgentDecisionPackage(
                    NoObjectiveOperation(),
                    Abort(context.context_id, "two distinct repairs delivered", "policy"),
                )
            option = context.actions.options[0]
            return AgentDecisionPackage(
                ProposeObjective((requirement,), TargetPresent(target_id)),
                SelectAction(context.context_id, option.action_id, {"value": "desired"}),
            )

    async def scenario() -> None:
        policy = Policy()
        instrumentation = BenchmarkInstrumentation()
        environment = StaticEnvironment([_world("observation:before", "", False)])
        result = await AgentLoop(
            CountingPolicy(policy, instrumentation), _ActionEvaluator(), _TaskEvaluator(),
        ).run(_task(), environment)

        assert len(policy.contexts) == 3
        assert result.execution_count == 0
        assert result.reason_code == "abort_policy"
        first_trace = instrumentation.policy_trace[0]
        assert first_trace["selected_source_modalities"] == ("structural",)
        assert first_trace["selected_grounding"] == {
            "ref": "E1",
            "role": "button",
            "label": "Submit",
            "state": {"submitted": False},
            "marked": False,
            "semantic_action": "activate",
        }
        repair_trace = instrumentation.policy_trace[1]["feedback"]
        assert repair_trace["strategy_transition_required"] is False
        assert repair_trace["strategy_change_required"] is True
        assert repair_trace["must_change_fields"] == (
            "objective_operation.predicate",
        )

    asyncio.run(scenario())


def test_repeated_already_satisfied_predicate_is_mechanically_terminated() -> None:
    class Policy:
        contexts = []

        async def decide(self, context):
            self.contexts.append(context)
            requirement = context.progress.task_frontier.current_frontier[0]
            option = context.actions.options[0]
            return AgentDecisionPackage(
                ProposeObjective((requirement,), TargetPresent("target:text")),
                SelectAction(context.context_id, option.action_id, {"value": "desired"}),
            )

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("observation:before", "", False)])
        result = await AgentLoop(
            policy, _ActionEvaluator(), _TaskEvaluator(),
        ).run(_task(), environment)

        assert len(policy.contexts) == 2
        assert result.execution_count == 0
        assert result.reason_code == "no_progress_control_repetition"
        assert result.control_feedback_delivery_count == 1
        assert result.control_repetition_count == 1

    asyncio.run(scenario())


def test_outcome_only_task_gets_one_runtime_owned_frontier_requirement() -> None:
    task = TaskGoal("task:outcome-only", "Complete the external task")
    observation = _world("observation:outcome-only", "", False)
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "external verifier reports running",
    )

    state = synchronize_verified_task_state(task, evaluation, observation, None)

    assert state.current_frontier == (TASK_OUTCOME_REQUIREMENT_ID,)
    assert state.requirements == (
        VerifiedRequirement(
            TASK_OUTCOME_REQUIREMENT_ID,
            CriterionEvaluationStatus.UNSATISFIED,
        ),
    )

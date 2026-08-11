import asyncio
from dataclasses import dataclass, replace

import pytest

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentFailureCode,
    AgentLoop,
    AgentLoopStatus,
    ProposeDone,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.control_transition import PendingKind
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.task import (
    HypothesisPredicateAssessment,
    HypothesisProposalMode,
    LoopBudget,
    RequirementHypothesisFailure,
    RequirementHypothesisFailureKind,
    RequirementHypothesisProposal,
    RequirementHypothesisProposalBatch,
    RiskProfile,
    TaskGoal,
)
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.task.frontier_contracts import LiteralExpected, TargetFieldEquals
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    AcquisitionOrigin,
    ActionBinding,
    ActionRisk,
    CoverageState,
    ObservationRequestKind,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _world(observation_id: str, enabled: bool, *, risk: ActionRisk = ActionRisk.LOW) -> WorldObservation:
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
        risk=risk,
    )
    fact = StateFact(f"fact:{observation_id}:enabled", target.target_id, "enabled", enabled, observation_id)
    source = SurfaceObservation(
        observation_id, "dom", f"revision:{observation_id}", ObservationSourceProfile.dom(),
        (target,), (fact,), (binding,),
    )
    return WorldObservation(
        observation_id,
        (target,),
        (fact,),
        (binding,),
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
        risk_profile=RiskProfile.LOW,
    )


@dataclass
class ScriptedPolicy:
    decisions: list[object]

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns, optional_plan = context.history.items, context.progress.plan_summary
        del task, world, recent_turns, optional_plan
        decision = self.decisions.pop(0)
        if decision == "first":
            return SelectAction(context.context_id, action_space.options[0].action_id)
        if isinstance(decision, (SelectAction, RequestObservation, ProposeDone, Abort)):
            return replace(decision, context_id=context.context_id)
        return decision


class SharedTaskEvaluator:
    async def evaluate(self, task, observation):
        enabled = bool(observation.targets[0].state.get("enabled"))
        fact_ref = observation.facts[0].fact_id
        criteria = tuple(
            CriterionEvaluation(
                criterion_id(item),
                CriterionEvaluationStatus.SATISFIED
                if enabled
                else CriterionEvaluationStatus.UNSATISFIED,
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


class SharedActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task
        changed = before.targets[0].state.get("enabled") != after.targets[0].state.get("enabled")
        if result.dispatch_status == DispatchStatus.SENT_UNKNOWN and not changed:
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.UNKNOWN,
                "effect remains unknown",
            )
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED
            if changed
            else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "state changed" if changed else "state did not change",
            (after.facts[0].fact_id,),
        )


def _loop(policy) -> AgentLoop:
    return AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())


def _sent(status: DispatchStatus = DispatchStatus.SENT, success: bool = True) -> ActionResult:
    error = None if success else ActionError.EXECUTION_FAILED
    return ActionResult("*", status, "dom", success, error)


def test_initial_satisfaction_is_zero_execution_done() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", True)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([]))).run(environment, _task())
        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 0
        assert result.observation_count == 1
        assert result.control_transition_total_count == 0

    asyncio.run(scenario())


def test_requirement_hypothesis_failure_is_nonterminal_start_metadata() -> None:
    class FailingProposer:
        async def propose(
            self, task, observation, action_space, *, mode, observation_cursor=""
        ):
            del task, observation, action_space, mode, observation_cursor
            return RequirementHypothesisFailure(
                RequirementHypothesisFailureKind.PROVIDER_UNAVAILABLE,
                "requirement_hypothesis_provider_unavailable",
            )

    async def scenario() -> None:
        loop = _loop(ScriptedPolicy([]))
        loop.context_builder = replace(
            loop.context_builder,
            requirement_hypothesis_proposer=FailingProposer(),
        )
        session = await AgentEpisodeRunner(loop).start(
            StaticEnvironment([_world("obs-1", True)]),
            _task(),
        )

        assert session.state.requirement_hypotheses.hypotheses == ()
        assert (
            session.state.requirement_hypothesis_failure_reason
            == "requirement_hypothesis_provider_unavailable"
        )
        result = await session.run_until_pause()
        assert result.status is AgentLoopStatus.DONE

    asyncio.run(scenario())


def test_initial_hypothesis_is_admitted_assessed_without_granting_actions() -> None:
    class Proposer:
        async def propose(
            self, task, observation, action_space, *, mode, observation_cursor=""
        ):
            del task, observation, action_space, observation_cursor
            assert mode is HypothesisProposalMode.INITIAL
            return RequirementHypothesisProposalBatch(
                mode,
                (
                    RequirementHypothesisProposal(
                        "Shared state should be enabled",
                        TargetFieldEquals(
                            "shared-toggle",
                            "enabled",
                            LiteralExpected(True),
                        ),
                        ("shared-toggle",),
                    ),
                ),
            )

    async def scenario() -> None:
        loop = _loop(ScriptedPolicy([]))
        loop.context_builder = replace(
            loop.context_builder,
            requirement_hypothesis_proposer=Proposer(),
        )
        world = _world("obs-1", True)
        actions_before = loop.action_space_builder.build(_task(), world)
        session = await AgentEpisodeRunner(loop).start(
            StaticEnvironment([world]),
            _task(),
        )

        assert session.state.requirement_hypotheses.active[0].hypothesis_id == "hypothesis:1"
        assert loop.action_space_builder.build(_task(), world) == actions_before
        result = await session.run_until_pause()
        assert result.status is AgentLoopStatus.DONE
        assert (
            session.state.requirement_hypotheses.active[0].assessment
            is HypothesisPredicateAssessment.SATISFIED
        )

    asyncio.run(scenario())


def test_sent_unknown_confirmed_effect_executes_once_and_completes() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", True)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert result.observation_count == 2

    asyncio.run(scenario())


def test_sent_unknown_unconfirmed_effect_waits_without_replay() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", False)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.WAITING_USER
        assert result.execution_count == 1
        assert len(environment.executed_requests) == 1
        assert environment.execute_calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "kind", "code"),
    (
        (
            TaskEvaluationStatus.INCOMPLETE,
            TaskOutcomeKind.RUNNING_INCOMPLETE,
            "verified_running",
        ),
        (
            TaskEvaluationStatus.UNKNOWN,
            TaskOutcomeKind.VERIFIER_UNAVAILABLE,
            "source_insufficient",
        ),
    ),
)
def test_nonterminal_task_fact_preserves_sent_unknown_pending_without_replay(
    status: TaskEvaluationStatus,
    kind: TaskOutcomeKind,
    code: str,
) -> None:
    class CanonicalTaskEvaluator:
        async def evaluate(self, task, observation):
            if observation.observation_id == "obs-1":
                return TaskEvaluation(
                    task.task_id,
                    observation.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "verified_running",
                    outcome=TaskOutcomeFact(
                        TaskOutcomeKind.RUNNING_INCOMPLETE,
                        "verified_running",
                    ),
                )
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                status,
                code,
                outcome=TaskOutcomeFact(kind, code),
            )

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", False)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        policy = ScriptedPolicy(["first"])
        runner = AgentEpisodeRunner(
            AgentLoop(policy, SharedActionEvaluator(), CanonicalTaskEvaluator())
        )
        session = await runner.start(environment, _task())
        result = await session.run_until_pause()
        repeated = await session.run_until_pause()

        assert repeated is result
        assert result.status is AgentLoopStatus.WAITING_USER
        assert result.reason_code == "effect_unknown"
        assert result.execution_count == 1
        assert environment.execute_calls == 1
        assert len(environment.executed_requests) == 1
        assert len(result.control_transitions) == 1
        assert result.control_transitions[0].pending_kind is PendingKind.UNKNOWN_EFFECT

    asyncio.run(scenario())


def test_nonterminal_verifier_unavailable_does_not_erase_action_rejection() -> None:
    class CanonicalTaskEvaluator:
        async def evaluate(self, task, observation):
            kind = (
                TaskOutcomeKind.RUNNING_INCOMPLETE
                if observation.observation_id == "obs-1"
                else TaskOutcomeKind.VERIFIER_UNAVAILABLE
            )
            status = (
                TaskEvaluationStatus.INCOMPLETE
                if kind is TaskOutcomeKind.RUNNING_INCOMPLETE
                else TaskEvaluationStatus.UNKNOWN
            )
            code = "verified_running" if status is TaskEvaluationStatus.INCOMPLETE else "source_insufficient"
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                status,
                code,
                outcome=TaskOutcomeFact(kind, code),
            )

    class RejectingActionEvaluator:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.REJECTED,
                "action evidence rejected",
            )

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", False)],
            [_sent()],
        )
        result = await AgentEpisodeRunner(AgentLoop(
            ScriptedPolicy(["first"]),
            RejectingActionEvaluator(),
            CanonicalTaskEvaluator(),
        )).run(environment, _task())

        assert result.status is AgentLoopStatus.FAILED
        assert result.reason_code == "action_rejected"
        assert result.runtime_failure is not None
        assert result.task_outcome is not None
        assert result.task_outcome.kind is TaskOutcomeKind.VERIFIER_UNAVAILABLE
        assert environment.execute_calls == 1

    asyncio.run(scenario())


def test_unknown_action_and_private_parameter_injection_are_zero_execution() -> None:
    async def scenario(decision) -> AgentLoopStatus:
        environment = StaticEnvironment([_world("obs-1", False)])
        result = await AgentEpisodeRunner(
            _loop(ScriptedPolicy([decision, decision]))
        ).run(environment, _task())
        assert result.execution_count == 0
        return result.status

    assert asyncio.run(scenario(SelectAction("context:test", "not-offered"))) == AgentLoopStatus.BLOCKED
    assert (
        asyncio.run(scenario(SelectAction("context:test", "not-offered", {"selector": "#other"})))
        == AgentLoopStatus.BLOCKED
    )


def test_selector_injection_on_offered_action_is_rejected() -> None:
    class InjectingPolicy:
        async def decide(self, context):
            task, world, action_space = context.task, context.world, context.actions
            recent_turns, optional_plan = context.history.items, context.progress.plan_summary
            del task, world, recent_turns, optional_plan
            return SelectAction(context.context_id, action_space.options[0].action_id, {"selector": "#other"})

    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False)])
        result = await AgentEpisodeRunner(_loop(InjectingPolicy())).run(environment, _task())
        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_policy_finish_does_not_complete_an_unsatisfied_task() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False)])
        environment = StaticEnvironment([_world("obs-1", False), _world("obs-2", True)], [_sent()])
        proposal = ProposeDone("context:test", (), (), "claim done", ())
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([proposal, "first"]))).run(
            environment, _task()
        )
        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert isinstance(result.turns[0].decision, ProposeDone)

    asyncio.run(scenario())


def test_transport_success_without_state_change_is_not_done() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", False)],
            [_sent()],
        )
        abort = Abort("context:test", "no progress", "policy")
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first", abort]))).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 1
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.INCOMPLETE

    asyncio.run(scenario())


def test_reused_primary_post_observation_reports_failed_fallback_truth() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False), _world("obs-1", True)], [_sent()])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.WAITING_USER
        assert result.message == "static_capture_failed"
        assert result.failure_code is AgentFailureCode.POST_ACTION_ACQUISITION_FAILED
        assert result.observation_count == 3
        assert result.final_observation.observation_id == "obs-1"
        transition = result.control_transitions[0]
        assert tuple(item.origin for item in transition.acquisition_attempts) == (
            AcquisitionOrigin.POST_ACTION,
            AcquisitionOrigin.INDEPENDENT_CAPTURE,
        )
        assert tuple(item.reason_code for item in transition.acquisition_attempts) == (
            "observation_identity_reused",
            "static_capture_failed",
        )

    asyncio.run(scenario())


def test_non_low_risk_action_waits_for_confirmation_with_zero_execution() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False, risk=ActionRisk.MEDIUM)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert result.execution_count == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("risk_profile", [RiskProfile.MEDIUM, RiskProfile.HIGH])
def test_medium_or_high_task_waits_even_for_low_risk_option(risk_profile: RiskProfile) -> None:
    async def scenario() -> None:
        task = replace(_task(), risk_profile=risk_profile)
        environment = StaticEnvironment([_world("obs-1", False)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, task)

        assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert result.execution_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_read_only_task_cannot_select_an_effectful_option() -> None:
    async def scenario() -> None:
        world = _world("obs-1", False)
        effectful_option = _loop(ScriptedPolicy([])).action_space_builder.build(_task(), world).options[0]
        task = TaskGoal("inspect", "Inspect shared state")
        environment = StaticEnvironment([world])
        result = await AgentEpisodeRunner(
            _loop(ScriptedPolicy([
                SelectAction("context:test", effectful_option.action_id),
                SelectAction("context:test", effectful_option.action_id),
            ]))
        ).run(environment, task)

        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_stale_binding_reobserves_with_zero_executor_calls() -> None:
    class StaleEnvironment(StaticEnvironment):
        def is_current(self, request):
            del request
            return False

    async def scenario() -> None:
        environment = StaleEnvironment([_world("obs-1", False), _world("obs-2", False)])
        abort = Abort("context:test", "still stale", "policy")
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first", abort]))).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        # environment.execute was physically called once and returned NOT_SENT.
        assert result.execution_count == 1
        assert environment.executed_requests == []
        assert result.observation_count == 2
        assert environment.capture_calls == 1
        assert [request.kind for request in environment.capture_requests] == [
            ObservationRequestKind.CURRENTNESS_REFRESH,
        ]

    asyncio.run(scenario())


def test_recent_turns_are_bounded() -> None:
    async def scenario() -> None:
        observations = []
        for index in range(20):
            world = _world(f"obs-{index}", False)
            target = replace(world.targets[0], label=f"Enable shared state revision {index}")
            source = replace(world.sources[0], targets=(target,))
            observations.append(replace(world, targets=(target,), sources=(source,)))
        decisions = [
            RequestObservation("context:test", "world", "structural", "structural", "refresh")
            for _ in range(15)
        ] + [Abort("context:test", "enough", "policy")]
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(decisions))).run(
            StaticEnvironment(observations),
            _task(),
        )
        assert len(result.turns) == 12

    asyncio.run(scenario())


def test_sent_unknown_verified_effect_waits_when_task_is_incomplete() -> None:
    class IncompleteTaskEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "more work remains",
            )

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", True)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        abort = Abort("context:test", "next objective unavailable", "policy")
        loop = AgentLoop(ScriptedPolicy(["first", abort]), SharedActionEvaluator(), IncompleteTaskEvaluator())
        result = await AgentEpisodeRunner(loop).run(environment, _task())
        assert result.status == AgentLoopStatus.WAITING_USER
        assert result.execution_count == 1
        assert "unknown" in result.message

    asyncio.run(scenario())


def test_observation_budget_is_reserved_before_execution() -> None:
    async def scenario() -> None:
        task = TaskGoal(
            "enable-shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(max_turns=2, max_observations=2),
        )
        environment = StaticEnvironment([_world("obs-1", False), _world("obs-2", False)])
        request = RequestObservation("context:test", "world", "structural", "structural", "refresh")
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([request, "first"]))).run(environment, task)
        assert result.status == AgentLoopStatus.FAILED
        assert "observation budget" in result.message
        assert result.execution_count == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ("request", "wait"))
@pytest.mark.parametrize(
    ("fresh_enabled", "expected"),
    ((True, AgentLoopStatus.DONE), (False, AgentLoopStatus.FAILED)),
)
def test_last_turn_refresh_is_evaluated_before_turn_budget(
    kind: str, fresh_enabled: bool, expected: AgentLoopStatus,
) -> None:
    class OneRefreshPolicy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if kind == "wait":
                return Wait(context.context_id, "settle", 1)
            return RequestObservation(
                context.context_id, "world", "structural", "structural", "refresh"
            )

    async def scenario() -> None:
        task = replace(_task(), loop_budget=LoopBudget(max_turns=1, max_observations=2))
        policy = OneRefreshPolicy()
        environment = StaticEnvironment([
            _world("initial", False), _world("fresh", fresh_enabled),
        ])
        result = await AgentEpisodeRunner(
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, task)

        assert result.status is expected
        assert policy.calls == 1
        assert result.observation_count == 2
        assert result.final_observation.observation_id == "fresh"
        assert result.reason_code == (
            "task_complete" if fresh_enabled else "turn_budget_exhausted"
        )

    asyncio.run(scenario())


def test_wrong_action_result_lineage_is_rejected_before_evaluation() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", True)],
            [ActionResult("wrong-request", DispatchStatus.SENT, "wrong-backend", True)],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        assert "lineage" in result.message
        assert result.turns[0].action_evaluation is None
        assert result.observation_count == 2
        assert result.execution_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("request_id", "backend"),
    [("wrong-request", "dom"), ("*", "wrong-backend")],
)
def test_not_sent_wrong_lineage_fails_before_evaluation(request_id: str, backend: str) -> None:
    class FailIfEvaluated(SharedActionEvaluator):
        async def evaluate(self, task, before, request, result, after):
            raise AssertionError("ActionEvaluator must not run for wrong NOT_SENT lineage")

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False)],
            [
                ActionResult(
                    request_id,
                    DispatchStatus.NOT_SENT,
                    backend,
                    False,
                    ActionError.EXECUTION_FAILED,
                )
            ],
        )
        loop = AgentLoop(ScriptedPolicy(["first"]), FailIfEvaluated(), SharedTaskEvaluator())
        result = await AgentEpisodeRunner(loop).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert "lineage" in result.message
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())

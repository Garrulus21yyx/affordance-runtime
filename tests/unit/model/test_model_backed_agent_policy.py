import asyncio
from dataclasses import dataclass, replace

from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import (
    Abort,
    RunStatus,
    SelectAction,
)
from affordance_runtime.agent.context import ContextBuilder, ModelFailure, ModelFailureKind
from affordance_runtime.agent.policy import AgentDecisionPorts, PolicyFailure
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.model.policy import (
    ModelBackedAgentPolicy,
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)
from tests.support.agent.core_loop_support import SharedActionOutcomeProjector, SharedTaskEvaluator, _task, _world


async def _context():
    task = _task()
    observation = _world("model-context", False)
    evaluation = await SharedTaskEvaluator().evaluate(task, observation)
    space = ActionSpaceBuilder().build(task, observation)
    return ContextBuilder().build(task, observation, space, evaluation)


@dataclass
class ScriptedPort:
    outcome: object
    calls: int = 0
    request: object | None = None

    async def generate(self, request):
        self.calls += 1
        self.request = request
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _decision_result(decision, metadata: ModelMetadata | None = None):
    resolved_metadata = metadata or ModelMetadata()
    return ModelInvocationResult(
        output=ResolvedModelDecision(decision, resolved_metadata),
        metadata=resolved_metadata,
        attempts=(ModelGenerationAttempt(1, "initial", "fixture", "accepted"),),
        diagnostics={"policy_model_call_count": 1},
    )


def test_model_request_has_one_typed_context_authority() -> None:
    async def scenario() -> None:
        context = await _context()
        port = ScriptedPort(_decision_result(Abort(context.context_id, "fixture stop", "policy")))
        await ModelBackedAgentPolicy(port).decide(context)

        assert port.request.agent_context is context
        assert port.request.context_id == context.context_id
        assert not hasattr(port.request, "serialized_context")
        assert not hasattr(port.request, "decision_schema")

    asyncio.run(scenario())


def test_private_binding_route_and_credentials_never_enter_model_request() -> None:
    async def scenario() -> None:
        task = _task()
        observation = _world("private-model-context", False)
        private_binding = replace(
            observation.bindings[0],
            payload={
                "selector": "#private",
                "href": "https://private.example/action",
                "credential": "top-secret",
                "backend": "private-executor",
            },
        )
        observation = replace(observation, bindings=(private_binding,))
        evaluation = await SharedTaskEvaluator().evaluate(task, observation)
        context = ContextBuilder().build(
            task,
            observation,
            ActionSpaceBuilder().build(task, observation),
            evaluation,
        )
        port = ScriptedPort(_decision_result(Abort(context.context_id, "inspection complete", "policy")))

        await ModelBackedAgentPolicy(port).decide(context)

        request = repr(
            (
                port.request.agent_context.task,
                port.request.agent_context.goal_plan,
                port.request.agent_context.actions,
                port.request.agent_context.actor_world,
            )
        )
        for private in ("#private", "private.example", "top-secret", "private-executor"):
            assert private not in request

    asyncio.run(scenario())


def test_model_backed_policy_makes_one_structured_call_and_returns_typed_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        option = context.actions.options[0]
        port = ScriptedPort(
            _decision_result(
                SelectAction(context.context_id, option.action_id),
                ModelMetadata("fixture", "scripted", "response:1"),
            )
        )

        decision = await ModelBackedAgentPolicy(port).decide(context)

        assert isinstance(decision, SelectAction)
        assert decision.context_id == context.context_id
        assert port.calls == 1
        assert port.request.agent_context is context

    asyncio.run(scenario())


def test_model_backed_policy_records_explicit_invocation_result_as_trace_authority() -> None:
    async def scenario() -> None:
        context = await _context()
        option = context.actions.options[0]
        attempts = (
            ModelGenerationAttempt(1, "initial", "grounded_tools.v2", "failed"),
            ModelGenerationAttempt(2, "initial_provider_retry", "grounded_tools.v2", "accepted"),
        )
        metadata = ModelMetadata(
            provider_id="fixture",
            model_id="scripted",
            rate_limit_retry_count=1,
        )
        port = ScriptedPort(
            ModelInvocationResult(
                output=ResolvedModelDecision(SelectAction(context.context_id, option.action_id), metadata),
                metadata=metadata,
                attempts=attempts,
                repair_diagnostics=({"kind": "transport_retry", "phase": "initial_provider_retry"},),
                lineage={"role": "ActionPolicy"},
            )
        )

        policy = ModelBackedAgentPolicy(port)
        decision = await policy.decide(context)

        assert isinstance(decision, SelectAction)
        assert port.calls == 1
        assert policy.last_invocation_result is not None
        assert policy.last_invocation_result.attempts == attempts
        assert policy.last_provider_attempts == attempts
        assert policy.last_metadata == metadata

    asyncio.run(scenario())


def test_canonical_context_port_receives_the_same_agent_context() -> None:
    @dataclass
    class CanonicalContextPort:
        request: object | None = None

        async def generate(self, request):
            self.request = request
            return _decision_result(Abort(request.context_id, "fixture stop", "policy"), ModelMetadata())

    async def scenario() -> None:
        context = await _context()
        port = CanonicalContextPort()

        outcome = await ModelBackedAgentPolicy(port).decide(context)

        assert isinstance(outcome, Abort)
        assert port.request.agent_context is context

    asyncio.run(scenario())


def test_provider_outputs_and_failures_are_distinct_from_model_authored_abort() -> None:
    outcomes = (
        "not-json",
        ModelInvocationResult(failure=ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False)),
        ModelInvocationResult(failure=ModelFailure(ModelFailureKind.REFUSED, "provider refused", False)),
        TimeoutError("credential=must-not-leak"),
    )

    async def scenario() -> None:
        context = await _context()
        for outcome in outcomes:
            port = ScriptedPort(outcome)
            decision = await ModelBackedAgentPolicy(port).decide(context)

            assert isinstance(decision, PolicyFailure)
            assert port.calls == 1
            assert "credential" not in decision.reason

    asyncio.run(scenario())


def test_policy_failure_is_terminal_zero_call_and_not_recorded_as_agent_abort() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        result = await TargetRuntime(
            AgentDecisionPorts(
                ModelBackedAgentPolicy(
                    ScriptedPort(
                        ModelInvocationResult(
                            failure=ModelFailure(ModelFailureKind.TIMEOUT, "timed out", False),
                            attempts=(ModelGenerationAttempt(1, "initial", "fixture", "failed"),),
                        )
                    )
                )
            ),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_model_policy_test"),
        ).run_task(environment, _task())

        assert result.status is RunStatus.FAILED
        assert result.policy_failure is not None
        assert result.policy_failure.kind == ModelFailureKind.TIMEOUT
        assert result.workspace.recent_steps == ()
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_model_authored_abort_remains_a_typed_agent_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        decision = await ModelBackedAgentPolicy(
            ScriptedPort(_decision_result(Abort(context.context_id, "stop", "policy")))
        ).decide(context)

        assert isinstance(decision, Abort)

    asyncio.run(scenario())


def test_strategy_revision_failure_degrades_to_one_ordinary_action_request() -> None:
    @dataclass
    class RecoveryPort:
        revision_calls: int = 0
        action_calls: int = 0
        action_request: object | None = None

        async def revise_strategy(self, request):
            self.revision_calls += 1
            return ModelInvocationResult(
                failure=ModelFailure(
                    ModelFailureKind.INVALID_RESPONSE,
                    "strategy revision was invalid",
                    False,
                )
            )

        async def generate(self, request):
            self.action_calls += 1
            self.action_request = request
            return _decision_result(Abort(request.context_id, "choose one supported fallback", "policy"))

    async def scenario() -> None:
        context = replace(
            await _context(),
            control_feedback={
                "kind": "route_regression",
                "stable_signature": "route:revision-failed",
                "recovery_attempt": 2,
            },
        )
        port = RecoveryPort()
        policy = ModelBackedAgentPolicy(port)

        decision = await policy.decide(context)

        assert isinstance(decision, Abort)
        assert port.revision_calls == 1
        assert port.action_calls == 1
        assert port.action_request.agent_context.control_feedback["strategy_revision_status"] == "unavailable"
        assert port.action_request.agent_context.strategy_revision is None
        assert policy.last_strategy_revision_invocation is not None
        assert policy.last_strategy_revision_invocation.failure is not None

    asyncio.run(scenario())


def test_failed_strategy_revision_is_not_rescheduled_on_later_recovery_attempts() -> None:
    @dataclass
    class RecoveryPort:
        revision_calls: int = 0

        async def revise_strategy(self, request):
            self.revision_calls += 1
            return ModelInvocationResult(
                failure=ModelFailure(
                    ModelFailureKind.INVALID_RESPONSE,
                    "strategy revision was invalid",
                    False,
                )
            )

        async def generate(self, request):
            return _decision_result(Abort(request.context_id, "continue recovery", "policy"))

    async def scenario() -> None:
        base = await _context()
        port = RecoveryPort()
        policy = ModelBackedAgentPolicy(port)

        await policy.decide(
            replace(
                base,
                control_feedback={
                    "kind": "route_regression",
                    "stable_signature": "route:second",
                    "recovery_attempt": 2,
                },
            )
        )
        await policy.decide(
            replace(
                base,
                control_feedback={
                    "kind": "route_regression",
                    "stable_signature": "route:third",
                    "recovery_attempt": 3,
                },
            )
        )

        assert port.revision_calls == 1

    asyncio.run(scenario())

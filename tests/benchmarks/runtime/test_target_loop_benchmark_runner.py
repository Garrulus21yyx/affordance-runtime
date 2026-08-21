import asyncio
import json
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace

from affordance_runtime.actions import (
    ActionBinding,
)
from affordance_runtime.agent import (
    ProtocolFeedback,
    ProtocolFeedbackKind,
    RunStatus,
    SelectAction,
    YieldSubtask,
)
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.observability import (
    LangfuseViewerWorker,
    QueuedViewerRunTraceRecorder,
)
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCase,
    BenchmarkComposition,
    CaseFailureOrigin,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingEnvironment,
)
from affordance_runtime.benchmarks.target_loop.reporting import (
    write_case_report,
    write_run_report,
)
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.mission import (
    ExecutionMode,
    ManagerAssessment,
    ManagerDecision,
    ManagerRoute,
    SubtaskContract,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationCapabilities,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)
from tests.support.world import fused_world


@dataclass
class NeverPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        raise AssertionError("complete task must not call policy")


class ActionOutcomeProjector:
    async def evaluate(self, task, before, request, result, after):
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.UNKNOWN,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.NONE,
            "unused",
        )


class CompleteEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id, observation.observation_id, TaskEvaluationStatus.BLOCKED, "fixture terminal"
        )


class UnknownEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id, observation.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown"
        )


def test_runner_is_sequential_isolated_and_always_cleans_up(tmp_path) -> None:
    events = []

    class Environment(ScriptedEnvironment):
        async def reset(self, task):
            events.append(f"start:{task.task_id}")
            return await super().reset(task)

        async def close(self):
            events.append(f"close:{self.task.task_id}")

    def case(identity):
        return BenchmarkCase(
            identity,
            "suite",
            identity,
            lambda: TaskGoal(identity, "Already complete"),
            lambda _metrics: Environment(
                initial_observation=fused_world(identity, surface="static"),
            ),
            lambda _metrics: BenchmarkComposition.atomic(NeverPolicy(), ActionOutcomeProjector(), CompleteEvaluator()),
            (RunStatus.BLOCKED,),
            2.0,
            7,
            ("observations",),
        )

    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case("a"), case("b")),
            ),
            trace_dir=tmp_path,
        )
    )
    assert result.acceptance.accepted
    assert events == ["start:a", "close:a", "start:b", "close:b"]
    assert [item.case_id for item in result.cases] == ["a", "b"]
    assert (tmp_path / "traces" / "a" / "trace.jsonl").is_file()
    assert (tmp_path / "traces" / "b" / "trace.jsonl").is_file()


def test_mission_runner_projects_outer_outcome_and_metrics() -> None:
    class YieldPolicy:
        @property
        def supported_decisions(self):
            return frozenset({DecisionCapability.YIELD_SUBTASK})

        async def decide(self, context):
            return YieldSubtask(context.context_id, "outcome_proposed", "ready")

    class Manager:
        def __init__(self):
            self.requests = []
            self.decisions = [
                ManagerDecision(
                    ManagerAssessment.NOT_APPLICABLE,
                    ManagerRoute.EXECUTE_SUBTASK,
                    subtask=SubtaskContract(
                        "Read current value",
                        "Current value is known",
                        "Provides the requested current value",
                        episode_turn_budget=1,
                    ),
                ),
                ManagerDecision(
                    ManagerAssessment.UNKNOWN,
                    ManagerRoute.ASK_USER,
                    question="Which account should be used?",
                ),
            ]

        async def decide(self, request):
            self.requests.append(request)
            return ModelInvocationResult(output=self.decisions.pop(0))

    manager = Manager()

    case = BenchmarkCase(
        "mission-ask",
        "suite",
        "mission ask projection",
        lambda: TaskGoal("mission", "Complete a long task."),
        lambda _metrics: ScriptedEnvironment(
            initial_observation=fused_world("mission"),
            independent_observations=(fused_world("mission-capture"),),
        ),
        lambda _metrics: BenchmarkComposition(
            YieldPolicy(),
            ActionOutcomeProjector(),
            UnknownEvaluator(),
            required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
            mission_manager=manager,
            mission_auditor=None,
            execution_mode=ExecutionMode.MISSION,
        ),
        (RunStatus.WAITING_USER,),
        2.0,
        7,
        ("observations",),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case,),
            )
        )
    ).cases[0]

    assert result.status == "waiting_user"
    assert result.pending_kind == "user_question"
    assert result.mission_outcome == "needs_user_input"
    assert result.mission_last_ref == "needs_user_input"
    assert result.measurements["mission_manager_calls"].value == 2
    assert result.measurements["mission_auditor_calls"].value == 0
    assert result.measurements["mission_state_version"].value == 0
    assert result.measurements["mission_boundary_rejections"].value == 0
    assert len(manager.requests) == 2


def test_hung_langfuse_projection_cannot_delay_manager_provider_failure_report(
    monkeypatch,
    tmp_path,
) -> None:
    from affordance_runtime.benchmarks.target_loop import runner
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    monkeypatch.setattr(runner, "_VIEWER_FLUSH_TIMEOUT_S", 0.05)
    viewer_entered = threading.Event()
    never_release = threading.Event()

    class HungClient:
        def start_as_current_observation(self, **_kwargs):
            viewer_entered.set()
            never_release.wait()

    def trace_factory(_environment, *, directory, run_id, session_id, benchmark_managed):
        return QueuedViewerRunTraceRecorder(
            directory,
            run_id=run_id,
            viewer_worker=LangfuseViewerWorker(
                lambda: HungClient(),
                session_id=session_id,
                benchmark_managed=benchmark_managed,
            ),
        )

    monkeypatch.setattr(runner, "trace_recorder_from_environment", trace_factory)

    class ProviderUnavailableManager:
        async def decide(self, _request):
            return ModelInvocationResult(failure=ModelFailure(
                ModelFailureKind.PROVIDER_UNAVAILABLE,
                "synthetic provider unavailable",
                True,
            ))

    case = BenchmarkCase(
        "mission-provider-unavailable",
        "suite",
        "provider failure with a hung read-only viewer",
        lambda: TaskGoal("mission-provider", "Complete a bounded task."),
        lambda _metrics: ScriptedEnvironment(initial_observation=fused_world("provider-failure")),
        lambda _metrics: BenchmarkComposition(
            NeverPolicy(),
            ActionOutcomeProjector(),
            UnknownEvaluator(),
            mission_manager=ProviderUnavailableManager(),
            mission_auditor=None,
            execution_mode=ExecutionMode.MISSION,
        ),
        (RunStatus.FAILED,),
        2.0,
        7,
        ("observations",),
    )

    started = time.perf_counter()
    result = asyncio.run(run_suite(BenchmarkManifest(
        "target-loop-manifest.v1",
        "suite",
        "deterministic",
        7,
        (case,),
    ), trace_dir=tmp_path)).cases[0]
    elapsed = time.perf_counter() - started

    assert viewer_entered.is_set()
    assert elapsed < 0.5
    assert result.status == "failed"
    assert result.mission_outcome == "manager_failure"
    assert "viewer" not in result.failure_code
    trace_path = tmp_path / "traces" / case.case_id / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    role = next(event for event in events if event["event"] == "mission_role_invocation")
    assert role["failure"]["kind"] == "provider_unavailable"
    assert any(
        event["event"] == "case_lifecycle_phase" and event["phase"] == "CASE_BODY_RETURNED"
        for event in events
    )
    assert any(event["event"] == "viewer_status" for event in events)
    assert (tmp_path / "cases" / f"{case.case_id}.json").is_file()


def test_protocol_stall_manager_blocked_projects_and_writes_formal_reports(tmp_path) -> None:
    class ProtocolPolicy:
        @property
        def supported_decisions(self):
            return frozenset()

        async def decide(self, context):
            return ProtocolFeedback(
                context.context_id,
                ProtocolFeedbackKind.MULTIPLE_TOOL_CALLS,
                2,
                "multiple_tool_calls",
            )

    class Manager:
        def __init__(self):
            self.decisions = [
                ManagerDecision(
                    ManagerAssessment.NOT_APPLICABLE,
                    ManagerRoute.EXECUTE_SUBTASK,
                    subtask=SubtaskContract(
                        "Enter the remaining values one at a time",
                        "Both values are visible",
                        "Completes the requested form values",
                        episode_turn_budget=6,
                    ),
                ),
                ManagerDecision(
                    ManagerAssessment.BLOCKED,
                    ManagerRoute.BLOCKED,
                    reason="protocol recovery exhausted",
                ),
            ]

        async def decide(self, request):
            del request
            return ModelInvocationResult(output=self.decisions.pop(0))

    case = BenchmarkCase(
        "mission-protocol-stall",
        "suite",
        "protocol feedback projection",
        lambda: TaskGoal("mission-protocol", "Complete the current UI task."),
        lambda _metrics: ScriptedEnvironment(
            initial_observation=fused_world("protocol-stall"),
            independent_observations=(fused_world("protocol-review"),),
        ),
        lambda _metrics: BenchmarkComposition(
            ProtocolPolicy(),
            ActionOutcomeProjector(),
            UnknownEvaluator(),
            mission_manager=Manager(),
            mission_auditor=None,
            execution_mode=ExecutionMode.MISSION,
        ),
        (RunStatus.BLOCKED,),
        2.0,
        7,
        ("observations",),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    suite = asyncio.run(run_suite(BenchmarkManifest(
        "target-loop-manifest.v1",
        "suite",
        "deterministic",
        7,
        (case,),
    )))
    result = suite.cases[0]
    write_run_report(suite, str(tmp_path))

    assert result.status == "blocked", result
    assert result.last_decision_type == "ProtocolFeedback"
    assert result.measurements["executions"].value == 0
    assert result.measurements["mission_manager_calls"].value == 2
    assert result.measurements["mission_auditor_calls"].value == 0
    assert (tmp_path / "run.json").is_file()
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "cases" / "mission-protocol-stall.json").is_file()


def test_counting_reset_preserves_malformed_return_for_runtime_boundary() -> None:
    marker = object()

    class MalformedReset:
        async def reset(self, task):
            del task
            return marker

    instrumentation = BenchmarkInstrumentation()
    environment = CountingEnvironment(MalformedReset(), instrumentation, frozenset())
    returned = asyncio.run(environment.reset(TaskGoal("task", "task")))
    assert returned is marker
    assert instrumentation.environment_reset_acquisitions == 0
    assert instrumentation.failure_origin is CaseFailureOrigin.NONE


def test_benchmark_policy_projection_does_not_mutate_persisted_trace_events() -> None:
    instrumentation = BenchmarkInstrumentation()
    context = SimpleNamespace(
        context_id="context:test",
        actions=SimpleNamespace(options=()),
        actor_world=SimpleNamespace(sources=()),
        recent_steps=SimpleNamespace(items=()),
        image_inputs=(),
    )

    instrumentation.model_turn(context, object(), object())

    assert len(instrumentation.policy_trace) == 1
    assert "benchmark_policy" not in instrumentation.trace_recorder.events[-1]


def _action_world(observation_id: str) -> WorldObservation:
    target = SemanticTarget("target:button", "button", "Continue")
    fact = StateFact(f"fact:{observation_id}:enabled", target.target_id, "enabled", True, observation_id)
    binding = ActionBinding(
        f"binding:{observation_id}",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{observation_id}",
        target.target_id,
        target.target_id,
        "dom",
        "dom",
        "activate",
        "click",
        "local_reversible",
        ("advanced",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {},
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


def test_watchdog_timeout_preserves_privacy_safe_partial_episode() -> None:
    class ExecuteThenHangPolicy:
        def __init__(self) -> None:
            self.calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            await asyncio.Event().wait()

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id, observation.observation_id, TaskEvaluationStatus.INCOMPLETE, "incomplete"
            )

    policy = ExecuteThenHangPolicy()

    def task():
        return TaskGoal(
            "timeout",
            "Exercise timeout snapshot",
            allowed_effects=("advanced",),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(4, 6),
        )

    case = BenchmarkCase(
        "timeout",
        "suite",
        "timeout snapshot",
        task,
        lambda _metrics: ScriptedEnvironment(
            initial_observation=_action_world("observation:one"),
            post_observations=(_action_world("observation:two"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        ),
        lambda _metrics: BenchmarkComposition.atomic(policy, ActionOutcomeProjector(), IncompleteEvaluator()),
        (RunStatus.FAILED,),
        0.05,
        7,
        ("observations", "executions", "turns"),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case,),
            )
        )
    ).cases[0]

    assert result.failure_reason == "case timeout"
    assert result.termination_origin == "harness_watchdog"
    assert result.case_failure_code == "case_timeout"
    assert result.partial_episode_available is True
    assert result.terminal_reason_code is None
    assert result.measurements["observations"].value == 2
    assert result.measurements["executions"].value == 1
    assert result.measurements["turns"].value == 1
    assert result.latest_task_status == "incomplete"
    assert result.latest_action_observed_change == "unknown"
    assert result.latest_action_local_postcondition == "unknown"
    assert result.latest_action_evidence_method == "none"
    assert policy.calls == 2


def test_external_interruption_stops_suite_and_persists_typed_partial_case(tmp_path) -> None:
    interruption_requested = asyncio.Event()
    cleanup_events = []
    completed = []

    class ExecuteThenInterruptPolicy:
        def __init__(self) -> None:
            self.calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            interruption_requested.set()
            await asyncio.Future()

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "incomplete",
            )

    class Environment(ScriptedEnvironment):
        async def close(self):
            cleanup_events.append("closed")

    policy = ExecuteThenInterruptPolicy()
    case = BenchmarkCase(
        "interrupted",
        "suite",
        "external interruption snapshot",
        lambda: TaskGoal(
            "interrupted",
            "Exercise external interruption",
            allowed_effects=("advanced",),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(4, 6),
        ),
        lambda _metrics: Environment(
            initial_observation=_action_world("observation:one"),
            post_observations=(_action_world("observation:two"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        ),
        lambda _metrics: BenchmarkComposition.atomic(
            policy,
            ActionOutcomeProjector(),
            IncompleteEvaluator(),
        ),
        (RunStatus.DONE,),
        2.0,
        7,
        ("observations", "executions", "turns"),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case,),
            ),
            case_completed=lambda index, item: (
                completed.append((index, item.case_id)),
                write_case_report(item, tmp_path),
            ),
            trace_dir=tmp_path,
            interruption_requested=interruption_requested,
        )
    )

    interrupted = result.cases[0]
    assert interrupted.status == "failed"
    assert interrupted.execution_completed is False
    assert interrupted.partial_episode_available is True
    assert interrupted.failure_code == "interrupted_external"
    assert interrupted.case_failure_code == "interrupted_external"
    assert interrupted.failure_origin is CaseFailureOrigin.HARNESS_EXTERNAL_INTERRUPTION
    assert interrupted.termination_origin == "harness_external"
    assert interrupted.watchdog_triggered is False
    assert interrupted.measurements["executions"].value == 1
    assert result.acceptance.accepted is False
    assert cleanup_events == ["closed"]
    assert completed == [(1, "interrupted")]
    assert (tmp_path / "cases" / "interrupted.json").is_file()
    assert not (tmp_path / "cases" / "interrupted.json.tmp").exists()


def test_component_timeout_error_is_not_classified_as_watchdog() -> None:
    class RaisingPolicy:
        async def decide(self, context):
            del context
            raise TimeoutError("component-owned timeout")

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "incomplete",
            )

    case = BenchmarkCase(
        "component-timeout",
        "suite",
        "component timeout",
        lambda: TaskGoal("t", "t"),
        lambda _metrics: ScriptedEnvironment(initial_observation=_action_world("observation:one")),
        lambda _metrics: BenchmarkComposition.atomic(RaisingPolicy(), ActionOutcomeProjector(), IncompleteEvaluator()),
        (RunStatus.FAILED,),
        2.0,
        7,
        ("observations",),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case,),
            )
        )
    ).cases[0]
    assert result.case_failure_code != "case_timeout"
    assert result.failure_origin is not CaseFailureOrigin.HARNESS_WATCHDOG
    assert result.exception_class == "TimeoutError"
    assert result.failure_facts.runtime_failure is not None
    assert result.failure_facts.runtime_failure.stage is FailureStage.POLICY
    assert result.failure_facts.runtime_failure.kind is FailureKind.CALL_FAILED
    assert result.failure_facts.runtime_failure.exception_class == "TimeoutError"


def test_runner_preserves_typed_agent_failure_without_message_matching() -> None:
    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "incomplete",
            )

    def task():
        return TaskGoal(
            "typed-failure",
            "Preserve typed failure",
            allowed_effects=("advanced",),
            risk_profile=RiskProfile.LOW,
        )

    case = BenchmarkCase(
        "typed-failure",
        "suite",
        "typed failure",
        task,
        lambda _metrics: ScriptedEnvironment(
            initial_observation=_action_world("observation:one"),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
            observation_capabilities=ObservationCapabilities(False, True),
        ),
        lambda _metrics: BenchmarkComposition.atomic(
            Policy(),
            ActionOutcomeProjector(),
            IncompleteEvaluator(),
        ),
        (RunStatus.WAITING_USER,),
        2.0,
        7,
        ("observations", "executions", "turns"),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case,),
            )
        )
    ).cases[0]

    assert result.case_failure_code == "post_action_capability_unavailable"
    assert result.failure_code == ""
    assert result.runtime_reason_code == ""
    assert result.agent_failure_code == "post_action_capability_unavailable"
    assert result.failure_origin is CaseFailureOrigin.NONE
    assert result.failure_facts.runtime_failure is None

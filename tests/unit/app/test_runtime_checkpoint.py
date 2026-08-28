from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.reconciliation import EffectReconciliationStatus
from affordance_runtime.agent import SelectAction
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.checkpoint import (
    RuntimeCheckpoint,
    RuntimeCheckpointCommandOutcome,
    RuntimeCheckpointError,
    RuntimeCheckpointResumeOutcome,
    RuntimeCheckpointRevisionOutcome,
    SQLiteRuntimeCheckpointStore,
)
from affordance_runtime.app.public_session import (
    PublicSessionCapability,
    PublicSessionConflict,
    PublicSessionControlOwner,
    PublicSessionOpenError,
    PublicSessionStatus,
    PublicTaskRevisionCommand,
    RuntimeEnvironmentLease,
    TargetRuntimeSessionFactory,
)
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequired, NotRequiredGoalCompiler
from affordance_runtime.task import (
    NaturalLanguageTaskRequest,
    RevisionConversationContext,
    RevisionConversationTurn,
    RevisionNoChange,
    RevisionReady,
    RiskProfile,
    TaskBoundary,
    TaskRevisionProposal,
)
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world import SemanticTarget, StateFact, WorldFusion
from tests.integration.agent.test_core_loop import (
    CoreActionOutcomeProjector,
    CoreTaskEvaluator,
    DispatchPostconditionProjector,
)
from tests.integration.agent.test_core_loop import (
    _world as _action_world,
)
from tests.unit.agent.test_target_runtime_facade import AskForAccountPolicy, _runtime, _world


def _revision_command(
    command_id: str,
    checkpoint_id: str | None,
    text: str,
    *,
    task_revision: int = 1,
    run_status: PublicSessionStatus = PublicSessionStatus.PAUSED,
    conversation: RevisionConversationContext | None = None,
) -> PublicTaskRevisionCommand:
    context = conversation or RevisionConversationContext(
        (RevisionConversationTurn(command_id, "user", text),),
        command_id,
    )
    return PublicTaskRevisionCommand(
        command_id,
        task_revision,
        run_status,
        checkpoint_id,
        text,
        context,
    )


def test_revision_command_digest_remains_compatible_across_snapshot_v2() -> None:
    command = _revision_command(
        "revise:digest-compatibility",
        "runtime-checkpoint:" + "a" * 64,
        "Use the second account",
    )
    expected_payload = {
        "conversation": {
            "latest_turn_id": "revise:digest-compatibility",
            "turns": [
                {
                    "role": "user",
                    "text": "Use the second account",
                    "turn_id": "revise:digest-compatibility",
                }
            ],
        },
        "expected_checkpoint_id": "runtime-checkpoint:" + "a" * 64,
        "expected_run_status": "paused",
        "expected_task_revision": 1,
        "kind": "revise_task",
        "schema_version": "affordance-runtime.session.v1",
    }
    canonical = json.dumps(
        expected_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    assert command.payload_digest == hashlib.sha256(canonical.encode()).hexdigest()


class RecoverableAskPolicy(AskForAccountPolicy):
    active_task_identity: tuple[str, int] | None = None
    restored: bool = False

    def bind_checkpoint_history_identity(self, *, task_id, task_revision):
        identity = (task_id, task_revision)
        if self.active_task_identity not in {None, identity}:
            raise ValueError("history identity mismatch")
        self.active_task_identity = identity

    async def decide(self, context):
        self.active_task_identity = (
            context.task.task_id,
            context.goal_plan.task_revision,
        )
        return await super().decide(context)

    def export_checkpoint_history(self):
        return {
            "format": "pydantic-ai.messages.v1",
            "messages": [],
            "active_task_identity": list(self.active_task_identity or ()),
        }

    def restore_checkpoint_history(self, payload, *, task_id, task_revision):
        if payload.get("format") != "pydantic-ai.messages.v1":
            raise ValueError("history format mismatch")
        if tuple(payload.get("active_task_identity", ())) != (task_id, task_revision):
            raise ValueError("history task mismatch")
        self.active_task_identity = (task_id, task_revision)
        self.restored = True

    def rebind_checkpoint_history(
        self,
        *,
        task_id,
        current_revision,
        revised_revision,
    ):
        if revised_revision != current_revision + 1:
            raise ValueError("revision is not consecutive")
        if self.active_task_identity not in {None, (task_id, current_revision)}:
            raise ValueError("history identity mismatch")
        self.active_task_identity = (task_id, revised_revision)


class StepReferenceAskPolicy(RecoverableAskPolicy):
    persist_calls: int = 0

    async def persist_checkpoint_history(self):
        self.persist_calls += 1
        return {
            "format": "pydantic-ai.step-persistence.v1",
            "run_id": "action-policy-checkpoint-" + "a" * 32,
            "conversation_id": "session:step-reference",
            "message_digest": "b" * 64,
            "active_task_identity": list(self.active_task_identity or ()),
        }


class FailingStepPersistenceAskPolicy(RecoverableAskPolicy):
    async def persist_checkpoint_history(self):
        raise OSError("injected model step persistence failure")


@dataclass
class ReadyRevisionCompiler:
    calls: int = 0
    requests: list = field(default_factory=list)

    async def compile(self, request):
        self.calls += 1
        self.requests.append(request)
        return RevisionReady(
            request.current_task.revision,
            TaskRevisionProposal(
                "Inspect the selected account and its owner",
                TaskBoundary(),
            ),
        )


@dataclass
class NoChangeRevisionCompiler:
    calls: int = 0
    requests: list = field(default_factory=list)

    async def compile(self, request):
        self.calls += 1
        self.requests.append(request)
        return RevisionNoChange(request.current_task.revision, "already_equivalent")


@dataclass
class CountingGoalCompiler:
    revisions: list[int] = field(default_factory=list)

    async def compile(self, request):
        self.revisions.append(request.task.revision)
        return NotRequired(request.task.revision, "revision_test")


@dataclass
class EffectRevisionCompiler:
    desired_enabled: bool
    risk_profile: RiskProfile = RiskProfile.LOW
    calls: int = 0

    async def compile(self, request):
        self.calls += 1
        desired = self.desired_enabled
        return RevisionReady(
            request.current_task.revision,
            TaskRevisionProposal(
                "Enable shared state" if desired else "Disable shared state",
                TaskBoundary(
                    allowed_effects=("shared_state_enabled",),
                    success_criteria=({"target_id": "shared-toggle", "state": {"enabled": desired}},),
                    risk_profile=self.risk_profile,
                ),
            ),
        )


class DesiredEnabledEvaluator:
    async def evaluate(self, task, observation):
        target_id = str(task.success_criteria[0]["target_id"])
        desired = bool(task.success_criteria[0]["state"]["enabled"])
        target = next(item for item in observation.targets if item.target_id == target_id)
        enabled = bool(target.state.get("enabled"))
        satisfied = enabled is desired
        evidence_ref = next(item.fact_id for item in observation.facts if item.subject_id == target_id)
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            (TaskEvaluationStatus.COMPLETE if satisfied else TaskEvaluationStatus.INCOMPLETE),
            "desired shared state observed" if satisfied else "shared state needs change",
            tuple(
                CriterionEvaluation(
                    criterion_id(item),
                    (CriterionEvaluationStatus.SATISFIED if satisfied else CriterionEvaluationStatus.UNSATISFIED),
                    (evidence_ref,),
                    "criterion evaluated from current shared state",
                )
                for item in task.success_criteria
            ),
            (evidence_ref,) if satisfied else (),
        )


@dataclass
class RevisionEnvironment(ScriptedEnvironment):
    revised_tasks: list = field(default_factory=list, init=False)

    async def revise_task(self, task):
        self.revised_tasks.append(task)
        await super().revise_task(task)


def _effect_world(
    observation_id: str,
    enabled: bool,
    *,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
):
    world = _action_world(observation_id, enabled)
    source = world.sources[0]
    bindings = tuple(
        replace(
            binding,
            resource_ref="shared-state",
            reversibility=reversibility,
        )
        for binding in source.bindings
    )
    return replace(
        world,
        bindings=bindings,
        sources=(replace(source, bindings=bindings),),
    )


def _with_decoy_resource(world):
    source = world.sources[0]
    original_target = source.targets[0]
    original_fact = source.facts[0]
    original_binding = source.bindings[0]
    decoy_target = SemanticTarget(
        "decoy-toggle",
        original_target.role,
        "Unrelated state",
        {"enabled": False},
    )
    decoy_fact = StateFact(
        f"fact:{source.observation_id}:decoy:enabled",
        decoy_target.target_id,
        original_fact.predicate,
        False,
        source.observation_id,
    )
    decoy_binding = replace(
        original_binding,
        binding_id=f"binding:{source.observation_id}:decoy",
        target_fingerprint=f"fingerprint:{source.observation_id}:decoy",
        target_id=decoy_target.target_id,
        source_target_id=decoy_target.target_id,
        resource_ref="unrelated-state",
    )
    revised_source = replace(
        source,
        targets=(*source.targets, decoy_target),
        facts=(*source.facts, decoy_fact),
        bindings=(*source.bindings, decoy_binding),
    )
    fused = WorldFusion().fuse((revised_source,))
    assert fused.observation is not None
    return fused.observation


async def _effect_revision_session(
    tmp_path,
    *,
    desired_enabled: bool,
    revised_risk: RiskProfile = RiskProfile.LOW,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
    first_dispatch_status: DispatchStatus = DispatchStatus.SENT,
    candidate_action_available: bool = True,
    compensation_post_enabled: bool = False,
    candidate_decoy: bool = False,
    policy_override=None,
):
    dispatch_entered = asyncio.Event()
    dispatch_release = asyncio.Event()

    class FirstDispatchBlockingEnvironment(RevisionEnvironment):
        first_dispatch = True

        async def execute(self, request):
            if self.first_dispatch:
                self.first_dispatch = False
                dispatch_entered.set()
                await dispatch_release.wait()
            return await super().execute(request)

    store = SQLiteRuntimeCheckpointStore(tmp_path / "effect-revision.sqlite3")
    policy = policy_override or RecoverableSelectPolicy()
    compiler = EffectRevisionCompiler(desired_enabled, revised_risk)
    candidate_world = _effect_world(
        "effect-revision",
        True,
        reversibility=reversibility,
    )
    if not candidate_action_available:
        candidate_world = replace(
            candidate_world,
            bindings=(),
            sources=(replace(candidate_world.sources[0], bindings=()),),
        )
    elif candidate_decoy:
        candidate_world = _with_decoy_resource(candidate_world)
    environment = FirstDispatchBlockingEnvironment(
        initial_observation=_effect_world(
            "effect-before",
            False,
            reversibility=reversibility,
        ),
        independent_observations=(candidate_world,),
        post_observations=(
            _effect_world(
                "effect-sent",
                False,
                reversibility=reversibility,
            ),
            _effect_world(
                "effect-compensated",
                compensation_post_enabled,
                reversibility=reversibility,
            ),
        ),
        results=(
            ActionResult(
                "*",
                first_dispatch_status,
                "dom",
                first_dispatch_status is DispatchStatus.SENT,
                (None if first_dispatch_status is DispatchStatus.SENT else ActionError.EXECUTION_FAILED),
            ),
            ActionResult("*", DispatchStatus.SENT, "dom", True),
        ),
    )
    runtime = TargetRuntime(
        AgentDecisionPorts(policy),
        DispatchPostconditionProjector(),
        DesiredEnabledEvaluator(),
        goal_compiler=CountingGoalCompiler(),
        task_revision_compiler=compiler,
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: runtime,
        lambda _session_id: RuntimeEnvironmentLease(
            environment,
            reconnect_reference="browser-lease:effect-revision",
        ),
        request_factory=_action_request,
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:effect-revision",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Enable shared state")
    await asyncio.wait_for(dispatch_entered.wait(), timeout=1)
    await handle.pause("pause:effect-source")
    dispatch_release.set()
    for _ in range(100):
        source = await handle.snapshot()
        if source.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("effect source did not reach a durable pause")
    assert source.checkpoint_id is not None
    return handle, store, policy, compiler, environment, source


@dataclass(frozen=True)
class FailingRevisionStore:
    delegate: SQLiteRuntimeCheckpointStore

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def commit_pause(self, checkpoint, outcome):
        await self.delegate.commit_pause(checkpoint, outcome)

    async def commit_revision(self, checkpoint, outcome):
        if outcome.outcome == "revised":
            raise RuntimeCheckpointError("injected_revision_commit_failure")
        await self.delegate.commit_revision(checkpoint, outcome)


@dataclass(frozen=True)
class FailingRevisionReadStore:
    delegate: SQLiteRuntimeCheckpointStore

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def load(self, session_id, checkpoint_id):
        del session_id, checkpoint_id
        raise RuntimeCheckpointError("injected_revision_source_read_failure")


@dataclass(frozen=True)
class FailingRevisionOutcomeStore:
    delegate: SQLiteRuntimeCheckpointStore

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def commit_revision(self, checkpoint, outcome):
        if checkpoint is None:
            raise RuntimeCheckpointError("injected_revision_outcome_failure")
        await self.delegate.commit_revision(checkpoint, outcome)


async def _revisable_checkpoint_session(
    tmp_path,
    *,
    store=None,
    compiler=None,
    pause_source=True,
):
    checkpoint_store = store or SQLiteRuntimeCheckpointStore(tmp_path / "revision-checkpoints.sqlite3")
    policy = RecoverableAskPolicy()
    revision_compiler = compiler or ReadyRevisionCompiler()
    goal_compiler = CountingGoalCompiler()
    environment = RevisionEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(), _world(), _world()),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: replace(
            _runtime(policy),
            goal_compiler=goal_compiler,
            task_revision_compiler=revision_compiler,
        ),
        lambda _session_id: RuntimeEnvironmentLease(
            environment,
            reconnect_reference="browser-lease:revision",
        ),
        checkpoint_store=checkpoint_store,
    )
    handle = await factory.open(
        "session:revision",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        if (await handle.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("revision fixture did not reach waiting-user")
    paused = await handle.pause("pause:revision-source") if pause_source else await handle.snapshot()
    assert paused.status is (PublicSessionStatus.PAUSED if pause_source else PublicSessionStatus.WAITING_USER)
    return (
        handle,
        checkpoint_store,
        policy,
        revision_compiler,
        goal_compiler,
        environment,
        paused,
    )


class RecoverableSelectPolicy(RecoverableAskPolicy):
    async def decide(self, context):
        self.active_task_identity = (
            context.task.task_id,
            context.goal_plan.task_revision,
        )
        self.calls += 1
        return SelectAction(
            context.context_id,
            context.actions.options[0].action_id,
            tool_call_id="provider-call:recover-confirmation",
        )


class ResourceRecordingSelectPolicy(RecoverableSelectPolicy):
    def __init__(self):
        super().__init__()
        self.seen_resources: list[tuple[str, ...]] = []

    async def decide(self, context):
        self.seen_resources.append(tuple(option.resource_ref for option in context.actions.options))
        return await super().decide(context)


def _confirmation_runtime(policy: RecoverableSelectPolicy) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(policy),
        CoreActionOutcomeProjector(),
        CoreTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("checkpoint_confirmation_test"),
    )


def _confirmation_request(session_id: str, instruction: str):
    return NaturalLanguageTaskRequest(
        session_id,
        instruction,
        TaskBoundary(
            allowed_effects=("shared_state_enabled",),
            success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
            risk_profile=RiskProfile.MEDIUM,
        ),
    )


def _action_request(session_id: str, instruction: str):
    return NaturalLanguageTaskRequest(
        session_id,
        instruction,
        TaskBoundary(
            allowed_effects=("shared_state_enabled",),
            success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
            risk_profile=RiskProfile.LOW,
        ),
    )


async def _waiting_checkpoint_session(tmp_path, *, store=None):
    checkpoint_store = store or SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
        checkpoint_store=checkpoint_store,
    )
    handle = await factory.open(
        "session:checkpoint",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        snapshot = await handle.snapshot()
        if snapshot.status is PublicSessionStatus.WAITING_USER:
            return handle, checkpoint_store
        await asyncio.sleep(0.01)
    raise AssertionError("fixture did not reach waiting boundary")


async def _takeover_checkpoint_session(tmp_path, *, environment=None):
    checkpoint_store = SQLiteRuntimeCheckpointStore(tmp_path / "takeover-checkpoints.sqlite3")
    policy = RecoverableAskPolicy()
    owned_environment = environment or ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(policy),
        lambda _session_id: RuntimeEnvironmentLease(owned_environment),
        checkpoint_store=checkpoint_store,
    )
    handle = await factory.open(
        "session:takeover",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        if (await handle.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("takeover fixture did not reach waiting boundary")
    paused = await handle.pause("pause:takeover")
    assert paused.checkpoint_id is not None
    return handle, checkpoint_store, policy, owned_environment, paused.checkpoint_id


@pytest.mark.asyncio
async def test_pause_publishes_only_after_atomic_checkpoint_and_command_outcome(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    assert PublicSessionCapability.PAUSE_TASK in (await handle.snapshot()).capabilities

    paused = await handle.pause("pause:atomic")

    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.checkpoint_id is not None
    assert paused.resume_eligible is False
    assert paused.last_control_outcome is not None
    assert paused.last_control_outcome.outcome == "paused"
    assert paused.last_control_outcome.checkpoint_id == paused.checkpoint_id
    checkpoint = await store.load_latest("session:checkpoint")
    outcome = await store.command_outcome("session:checkpoint", "pause:atomic")
    assert checkpoint is not None
    assert checkpoint.checkpoint_id == paused.checkpoint_id
    assert outcome == RuntimeCheckpointCommandOutcome(
        "session:checkpoint",
        "pause:atomic",
        paused.checkpoint_id,
    )
    payload = json.loads(checkpoint.to_json())
    assert payload["run"]["status"] == "paused"
    assert payload["run"]["status_before_pause"] == "waiting_user"
    assert payload["last_step"]["pending_interaction"]["request_id"].startswith("interaction:")
    assert payload["model_history"] == {"format": "unavailable", "messages": []}
    assert "current_world" not in checkpoint.to_json()
    assert "full_world" not in checkpoint.to_json()
    assert tuple(event.type for event in await handle.events(0))[-2:] == (
        "CONTROL_REQUESTED",
        "RUN_PAUSED",
    )
    restored_task = checkpoint.restore_task()
    restored_facts = checkpoint.restore_run_facts()
    assert restored_task.task_id == "session:checkpoint"
    assert restored_task.revision == 1
    assert restored_facts.status_before_pause.value == "waiting_user"
    assert restored_facts.last_decision is not None
    assert restored_facts.last_decision.question == "Which account should I use?"
    await handle.close()


@pytest.mark.asyncio
async def test_takeover_consumes_checkpoint_and_return_refreshes_before_policy(tmp_path) -> None:
    handle, store, policy, environment, checkpoint_id = await _takeover_checkpoint_session(tmp_path)

    controlled = await handle.take_over("takeover:one", checkpoint_id)

    assert controlled.status is PublicSessionStatus.PAUSED
    assert controlled.control_owner is PublicSessionControlOwner.USER
    assert controlled.control_lease_id is not None
    assert await handle.admits_surface_input(controlled.control_lease_id)
    assert not await handle.admits_surface_input("wrong-lease")
    assert controlled.pending_question is None
    assert controlled.resume_eligible is False
    assert controlled.capabilities == frozenset(
        {
            PublicSessionCapability.CLOSE_SESSION,
            PublicSessionCapability.RETURN_CONTROL,
        }
    )
    assert await store.checkpoint_resume_outcome("session:takeover", checkpoint_id) == (
        RuntimeCheckpointResumeOutcome(
            "session:takeover",
            "takeover:one",
            checkpoint_id,
        )
    )
    with pytest.raises(PublicSessionConflict, match="user_control_active"):
        await handle.resume("resume:while-user", checkpoint_id)
    with pytest.raises(PublicSessionConflict, match="control_lease_mismatch"):
        await handle.return_control("return:stale", "wrong-lease")

    returned = await handle.return_control(
        "return:one",
        controlled.control_lease_id,
    )

    assert returned.control_owner is PublicSessionControlOwner.AGENT
    assert returned.control_lease_id is None
    assert returned.checkpoint_id is None
    assert environment.capture_calls == 1
    assert policy.calls == 1
    assert returned.pending_question is None
    for _ in range(100):
        current = await handle.snapshot()
        if current.status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("Agent policy did not continue after fresh user-control World")
    assert policy.calls == 2
    assert any(event.type == "USER_CONTROL_GRANTED" for event in await handle.events(0))
    assert any(event.type == "USER_CONTROL_RETURNED" for event in await handle.events(0))
    await handle.close()


@pytest.mark.asyncio
async def test_return_revokes_input_lease_before_blocking_fresh_world_capture(tmp_path) -> None:
    @dataclass
    class BlockingReturnEnvironment(ScriptedEnvironment):
        capture_started: asyncio.Event = field(default_factory=asyncio.Event)
        capture_allowed: asyncio.Event = field(default_factory=asyncio.Event)

        async def capture(self, request):
            self.capture_started.set()
            await self.capture_allowed.wait()
            return await super().capture(request)

    environment = BlockingReturnEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    handle, _store, _policy, _environment, checkpoint_id = await _takeover_checkpoint_session(
        tmp_path, environment=environment
    )
    controlled = await handle.take_over("takeover:blocking", checkpoint_id)
    assert controlled.control_lease_id is not None

    returning = asyncio.create_task(handle.return_control("return:blocking", controlled.control_lease_id))
    await asyncio.wait_for(environment.capture_started.wait(), timeout=1)

    fenced = await handle.snapshot()
    assert fenced.status is PublicSessionStatus.PAUSED
    assert fenced.control_owner is PublicSessionControlOwner.AGENT
    assert fenced.control_lease_id is None
    assert not await handle.admits_surface_input(controlled.control_lease_id)
    assert fenced.capabilities == frozenset({PublicSessionCapability.CLOSE_SESSION})
    assert any(event.type == "USER_CONTROL_REVOKED" for event in await handle.events(0))

    environment.capture_allowed.set()
    returned = await asyncio.wait_for(returning, timeout=1)
    assert returned.control_owner is PublicSessionControlOwner.AGENT
    assert returned.control_lease_id is None
    await handle.close()


@pytest.mark.asyncio
async def test_takeover_consumption_blocks_checkpoint_recovery(tmp_path) -> None:
    handle, store, _policy, _environment, checkpoint_id = await _takeover_checkpoint_session(tmp_path)
    await handle.take_over("takeover:crash", checkpoint_id)
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(RecoverableAskPolicy()),
        lambda _session_id: RuntimeEnvironmentLease(ScriptedEnvironment(initial_observation=_world())),
        checkpoint_store=store,
    )

    with pytest.raises(PublicSessionOpenError, match="checkpoint_already_resumed"):
        await factory.recover(
            "session:takeover",
            checkpoint_id,
            datetime.now(UTC) + timedelta(minutes=5),
        )
    await handle.close()


@pytest.mark.asyncio
async def test_return_currentness_failure_retains_exclusive_user_control(tmp_path) -> None:
    @dataclass
    class FailingReturnEnvironment(ScriptedEnvironment):
        fail_return_capture: bool = True
        return_capture_attempts: int = 0

        async def capture(self, request):
            self.return_capture_attempts += 1
            if self.fail_return_capture:
                raise OSError("injected user-control capture failure")
            return await super().capture(request)

    environment = FailingReturnEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    handle, _store, policy, _environment, checkpoint_id = await _takeover_checkpoint_session(
        tmp_path,
        environment=environment,
    )
    controlled = await handle.take_over("takeover:failure", checkpoint_id)
    assert controlled.control_lease_id is not None

    with pytest.raises(PublicSessionConflict, match="user_control_currentness_unavailable"):
        await handle.return_control("return:failure", controlled.control_lease_id)

    failed = await handle.snapshot()
    assert failed.status is PublicSessionStatus.PAUSED
    assert failed.control_owner is PublicSessionControlOwner.USER
    assert failed.control_lease_id is not None
    assert failed.control_lease_id != controlled.control_lease_id
    assert failed.capabilities == frozenset(
        {
            PublicSessionCapability.CLOSE_SESSION,
            PublicSessionCapability.RETURN_CONTROL,
        }
    )
    assert policy.calls == 1

    with pytest.raises(PublicSessionConflict, match="control_lease_mismatch"):
        await handle.return_control("return:revoked-lease", controlled.control_lease_id)

    environment.fail_return_capture = False
    await handle.return_control("return:retry", failed.control_lease_id)
    assert environment.return_capture_attempts == 2
    await handle.close()


@pytest.mark.asyncio
async def test_pause_checkpoint_references_async_model_step_snapshot(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    policy = StepReferenceAskPolicy()
    environment = ScriptedEnvironment(initial_observation=_world())
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(policy),
        lambda _session_id: RuntimeEnvironmentLease(
            environment,
            reconnect_reference="browser-lease:step-reference",
        ),
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:step-reference",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        if (await handle.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("step-reference fixture did not reach waiting-user")

    paused = await handle.pause("pause:step-reference")
    checkpoint = await store.load_latest("session:step-reference")

    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.resume_eligible is True
    assert policy.persist_calls == 1
    assert checkpoint is not None
    assert checkpoint.model_history == {
        "format": "pydantic-ai.step-persistence.v1",
        "run_id": "action-policy-checkpoint-" + "a" * 32,
        "conversation_id": "session:step-reference",
        "message_digest": "b" * 64,
        "active_task_identity": ["session:step-reference", 1],
    }
    await handle.close()


@pytest.mark.asyncio
async def test_model_step_persistence_failure_never_publishes_paused(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    policy = FailingStepPersistenceAskPolicy()
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(policy),
        lambda _session_id: RuntimeEnvironmentLease(
            ScriptedEnvironment(initial_observation=_world()),
            reconnect_reference="browser-lease:step-failure",
        ),
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:step-failure",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    for _ in range(100):
        if (await handle.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("step-failure fixture did not reach waiting-user")

    outcome = await handle.pause("pause:step-failure")

    assert outcome.status is PublicSessionStatus.WAITING_USER
    assert outcome.checkpoint_id is None
    assert outcome.resume_eligible is False
    assert outcome.last_control_outcome is not None
    assert outcome.last_control_outcome.code == "pause_persistence_failed"
    assert await store.load_latest("session:step-failure") is None
    await handle.close()


@pytest.mark.asyncio
async def test_active_pause_does_not_write_before_runtime_reaches_boundary(tmp_path) -> None:
    release = asyncio.Event()
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")

    class BlockingEnvironment(ScriptedEnvironment):
        async def reset(self, task):
            await release.wait()
            return await super().reset(task)

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: RuntimeEnvironmentLease(BlockingEnvironment(initial_observation=_world())),
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:active-checkpoint",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")

    requested = await handle.pause("pause:active")
    assert requested.status is PublicSessionStatus.RUNNING
    assert await store.load_latest("session:active-checkpoint") is None

    release.set()
    for _ in range(100):
        paused = await handle.snapshot()
        if paused.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"active pause did not reach its durable boundary: {paused!r}")

    checkpoint = await store.load_latest("session:active-checkpoint")
    assert checkpoint is not None
    assert checkpoint.pause_command_id == "pause:active"
    assert (await handle.snapshot()).checkpoint_id == checkpoint.checkpoint_id
    await handle.close()


@pytest.mark.asyncio
async def test_sqlite_rolls_back_checkpoint_when_command_outcome_cannot_commit(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    handle, _ = await _waiting_checkpoint_session(tmp_path, store=store)
    await store.load_latest("session:checkpoint")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_pause_outcome BEFORE INSERT ON runtime_command_outcomes "
            "BEGIN SELECT RAISE(ABORT, 'forced outcome failure'); END"
        )

    current = await handle.pause("pause:rollback")

    assert current.status is PublicSessionStatus.WAITING_USER
    assert current.checkpoint_id is None
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.outcome == "failed"
    assert current.last_control_outcome.code == "pause_persistence_failed"
    assert await store.load_latest("session:checkpoint") is None
    assert await store.command_outcome("session:checkpoint", "pause:rollback") is None
    assert tuple(event.type for event in await handle.events(0))[-2:] == (
        "CONTROL_REQUESTED",
        "CONTROL_FAILED",
    )
    await handle.close()


@pytest.mark.asyncio
async def test_failed_active_pause_refreshes_world_before_policy_continues(tmp_path) -> None:
    policy_release = asyncio.Event()
    policy_entered = asyncio.Event()

    class BlockingPolicy(AskForAccountPolicy):
        async def decide(self, context):
            if self.calls == 0:
                policy_entered.set()
                await policy_release.wait()
            return await super().decide(context)

    class FailingStore:
        async def commit_pause(self, checkpoint, outcome):
            del checkpoint, outcome
            raise RuntimeCheckpointError("checkpoint_persistence_failed")

        async def load_latest(self, session_id):
            del session_id
            return None

        async def command_outcome(self, session_id, command_id):
            del session_id, command_id
            return None

    policy = BlockingPolicy()
    environment = ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(policy),
        lambda _session_id: RuntimeEnvironmentLease(environment),
        checkpoint_store=FailingStore(),
    )
    handle = await factory.open(
        "session:persistence-recovery",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    await asyncio.wait_for(policy_entered.wait(), timeout=1)

    await handle.pause("pause:failed-active")
    policy_release.set()
    for _ in range(100):
        current = await handle.snapshot()
        if current.status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"failed pause did not continue from fresh currentness: {current!r}")

    assert current.checkpoint_id is None
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.code == "pause_persistence_failed"
    assert environment.capture_calls == 1
    assert policy.calls == 2
    assert any(
        request.reason == "fresh currentness after pause persistence failure"
        for request in environment.capture_requests
    )
    await handle.close()


@pytest.mark.asyncio
async def test_store_rejects_command_identity_conflict_without_second_checkpoint(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:one")
    checkpoint = await store.load_latest("session:checkpoint")
    assert checkpoint is not None and paused.checkpoint_id == checkpoint.checkpoint_id

    with pytest.raises(RuntimeCheckpointError, match="checkpoint_command_scope_mismatch"):
        await store.commit_pause(
            checkpoint,
            RuntimeCheckpointCommandOutcome(
                "session:checkpoint",
                "pause:other",
                checkpoint.checkpoint_id,
            ),
        )
    assert await store.command_outcome("session:checkpoint", "pause:other") is None
    await handle.close()


@pytest.mark.asyncio
async def test_cancel_from_durable_pause_is_terminal_and_not_resume_eligible(tmp_path) -> None:
    handle, _store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:before-cancel")
    assert paused.status is PublicSessionStatus.PAUSED

    cancelled = await handle.cancel("cancel:paused")

    assert cancelled.status is PublicSessionStatus.CANCELLED
    assert cancelled.resume_eligible is False
    assert cancelled.completion is not None
    assert cancelled.completion.outcome == "cancelled"
    await handle.close()


@pytest.mark.asyncio
async def test_process_restart_restores_same_environment_fresh_world_and_new_epoch(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3")
    first_policy = RecoverableAskPolicy()
    first_environment = ScriptedEnvironment(initial_observation=_world())
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            first_environment,
            reconnect_reference="browser-lease:session:restart",
        ),
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:restart", expires_at)
    await first.start("Inspect the selected account")
    for _ in range(100):
        if (await first.snapshot()).status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    paused = await first.pause("pause:restart")
    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.resume_eligible is True
    assert paused.checkpoint_id is not None
    first_epoch = paused.event_epoch
    await first.close()

    normal_open_calls = 0
    reconnect_calls: list[tuple[str, str]] = []
    recovered_environment = ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    recovered_policy = RecoverableAskPolicy()

    def must_not_open_replacement(_session_id: str):
        nonlocal normal_open_calls
        normal_open_calls += 1
        raise AssertionError("restart recovery must not open a replacement environment")

    def reconnect(session_id: str, reference: str):
        reconnect_calls.append((session_id, reference))
        return RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        )

    recovered_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(recovered_policy),
        must_not_open_replacement,
        checkpoint_store=store,
        environment_reconnector=reconnect,
    )
    recovered = await recovered_factory.recover("session:restart", paused.checkpoint_id, expires_at)
    baseline = await recovered.snapshot()

    assert baseline.status is PublicSessionStatus.PAUSED
    assert baseline.event_epoch != first_epoch
    assert baseline.event_cursor == 1
    assert tuple(event.type for event in await recovered.events(0)) == ("SESSION_RECOVERED",)
    assert baseline.checkpoint_id == paused.checkpoint_id
    assert baseline.resume_eligible is True
    assert normal_open_calls == 0
    assert reconnect_calls == [("session:restart", "browser-lease:session:restart")]
    assert recovered_environment.reset_calls == 0
    assert recovered_environment.capture_calls == 1
    assert recovered_policy.restored is True
    assert recovered_policy.calls == 0

    resumed = await recovered.resume("resume:restart", paused.checkpoint_id)
    assert resumed.status is PublicSessionStatus.WAITING_USER
    assert resumed.pending_question is not None
    assert resumed.resume_eligible is False
    assert recovered_policy.calls == 0
    assert await store.resume_outcome("session:restart", "resume:restart") == (
        RuntimeCheckpointResumeOutcome("session:restart", "resume:restart", paused.checkpoint_id)
    )
    duplicate = await recovered.resume("resume:restart", paused.checkpoint_id)
    assert duplicate == resumed

    with pytest.raises(PublicSessionOpenError, match="checkpoint_already_resumed"):
        await recovered_factory.recover("session:restart", paused.checkpoint_id, expires_at)
    assert len(reconnect_calls) == 1
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_refuses_nonreconnectable_checkpoint_without_opening_environment(tmp_path) -> None:
    handle, _store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:not-reconnectable")
    assert paused.checkpoint_id is not None
    await handle.close()
    open_calls = 0

    def environment_factory(_session_id: str):
        nonlocal open_calls
        open_calls += 1
        raise AssertionError("failed recovery must not create a new environment")

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        environment_factory,
        checkpoint_store=SQLiteRuntimeCheckpointStore(tmp_path / "runtime-checkpoints.sqlite3"),
    )
    with pytest.raises(PublicSessionOpenError, match="environment_not_reconnectable"):
        await factory.recover(
            "session:checkpoint",
            paused.checkpoint_id,
            datetime.now(UTC) + timedelta(minutes=5),
        )
    assert open_calls == 0


@pytest.mark.asyncio
async def test_restart_from_running_boundary_reselects_only_after_explicit_resume(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "running-checkpoints.sqlite3")
    release = asyncio.Event()

    class BlockingEnvironment(ScriptedEnvironment):
        async def reset(self, task):
            await release.wait()
            return await super().reset(task)

    first_policy = RecoverableAskPolicy()
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            BlockingEnvironment(initial_observation=_world()),
            reconnect_reference="browser-lease:running",
        ),
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:running-restart", expires_at)
    await first.start("Inspect the selected account")
    await first.pause("pause:running-restart")
    assert first_policy.active_task_identity == ("session:running-restart", 1)
    assert first_policy.calls == 0
    release.set()
    for _ in range(100):
        paused = await first.snapshot()
        if paused.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("running checkpoint did not commit")
    assert paused.checkpoint_id is not None
    await first.close()

    recovered_policy = RecoverableAskPolicy()
    recovered_environment = ScriptedEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(recovered_policy),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await factory.recover("session:running-restart", paused.checkpoint_id, expires_at)
    assert recovered_policy.calls == 0
    assert recovered_environment.execute_calls == 0

    resumed = await recovered.resume("resume:running-restart", paused.checkpoint_id)
    assert resumed.status is PublicSessionStatus.RUNNING
    for _ in range(100):
        waiting = await recovered.snapshot()
        if waiting.status is PublicSessionStatus.WAITING_USER:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("resumed running checkpoint did not return to policy")
    assert recovered_policy.calls == 1
    assert recovered_environment.execute_calls == 0
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_confirmation_keeps_exact_interrupt_and_never_dispatches_before_resume(
    tmp_path,
) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "confirmation-checkpoints.sqlite3")
    first_policy = RecoverableSelectPolicy()
    first_environment = ScriptedEnvironment(initial_observation=_action_world("confirmation-before", False))
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            first_environment,
            reconnect_reference="browser-lease:confirmation",
        ),
        request_factory=_confirmation_request,
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:confirmation-restart", expires_at)
    await first.start("Enable shared state")
    for _ in range(100):
        waiting = await first.snapshot()
        if waiting.status is PublicSessionStatus.WAITING_CONFIRMATION:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("confirmation fixture did not reach its interrupt")
    original_interrupt = waiting.pending_confirmation
    paused = await first.pause("pause:confirmation-restart")
    assert paused.status is PublicSessionStatus.PAUSED
    assert paused.checkpoint_id is not None
    assert first_environment.execute_calls == 0
    await first.close()

    recovered_policy = RecoverableSelectPolicy()
    recovered_environment = ScriptedEnvironment(
        initial_observation=_action_world("confirmation-reconnected", False),
        independent_observations=(_action_world("confirmation-reconnected", False),),
        post_observations=(_action_world("confirmation-after", True),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )
    recovered_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(recovered_policy),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        request_factory=_confirmation_request,
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await recovered_factory.recover("session:confirmation-restart", paused.checkpoint_id, expires_at)
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0

    resumed = await recovered.resume("resume:confirmation-restart", paused.checkpoint_id)
    assert resumed.status is PublicSessionStatus.WAITING_CONFIRMATION
    assert resumed.pending_confirmation == original_interrupt
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0

    assert resumed.pending_confirmation is not None
    await recovered.confirm(
        resumed.pending_confirmation.interrupt_id,
        approved=True,
    )
    for _ in range(100):
        done = await recovered.snapshot()
        if done.status is PublicSessionStatus.DONE:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"restored confirmation did not execute after approval: {done!r}")
    assert recovered_environment.execute_calls == 1
    assert recovered_policy.calls == 0
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_after_sent_receipt_observes_effect_without_replaying_action(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "sent-checkpoints.sqlite3")
    dispatch_entered = asyncio.Event()
    dispatch_release = asyncio.Event()

    class BlockingDispatchEnvironment(ScriptedEnvironment):
        async def execute(self, request):
            dispatch_entered.set()
            await dispatch_release.wait()
            return await super().execute(request)

    first_policy = RecoverableSelectPolicy()
    first_environment = BlockingDispatchEnvironment(
        initial_observation=_action_world("sent-before", False),
        post_observations=(_action_world("sent-after", False),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )
    first_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(first_policy),
        lambda _session_id: RuntimeEnvironmentLease(
            first_environment,
            reconnect_reference="browser-lease:sent",
        ),
        request_factory=_action_request,
        checkpoint_store=store,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    first = await first_factory.open("session:sent-restart", expires_at)
    await first.start("Enable shared state")
    await asyncio.wait_for(dispatch_entered.wait(), timeout=1)
    requested = await first.pause("pause:sent-restart")
    assert requested.status is PublicSessionStatus.RUNNING
    dispatch_release.set()
    for _ in range(100):
        paused = await first.snapshot()
        if paused.status is PublicSessionStatus.PAUSED:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("sent checkpoint did not commit")
    assert paused.checkpoint_id is not None
    checkpoint = await store.load(
        "session:sent-restart",
        paused.checkpoint_id,
    )
    assert checkpoint is not None and checkpoint.last_step is not None
    receipts = checkpoint.last_step["receipts"]
    assert receipts[0]["dispatch_status"] == "sent"
    assert first_environment.execute_calls == 1
    await first.close()

    recovered_policy = RecoverableSelectPolicy()
    recovered_environment = ScriptedEnvironment(
        initial_observation=_action_world("sent-reconnected", True),
        independent_observations=(_action_world("sent-reconnected", True),),
    )
    recovered_factory = TargetRuntimeSessionFactory(
        lambda _session_id: _confirmation_runtime(recovered_policy),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        request_factory=_action_request,
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await recovered_factory.recover("session:sent-restart", paused.checkpoint_id, expires_at)
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0
    await recovered.resume("resume:sent-restart", paused.checkpoint_id)
    for _ in range(100):
        done = await recovered.snapshot()
        if done.status is PublicSessionStatus.DONE:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"sent checkpoint did not finish from fresh truth: {done!r}")
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0
    await recovered.close()


@pytest.mark.asyncio
async def test_restart_rejects_corrupted_checkpoint_before_environment_reconnect(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:corrupt")
    assert paused.checkpoint_id is not None
    await handle.close()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE runtime_checkpoints SET payload_json = replace(payload_json, "
            "'Inspect the selected account', 'Inspect a corrupted account') "
            "WHERE session_id = ? AND checkpoint_id = ?",
            ("session:checkpoint", paused.checkpoint_id),
        )
        connection.commit()
    reconnect_calls = 0

    def reconnect(_session_id: str, reference: str):
        nonlocal reconnect_calls
        reconnect_calls += 1
        return RuntimeEnvironmentLease(
            ScriptedEnvironment(initial_observation=_world()),
            reconnect_reference=reference,
        )

    factory = TargetRuntimeSessionFactory(
        lambda _session_id: _runtime(),
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        checkpoint_store=store,
        environment_reconnector=reconnect,
    )
    with pytest.raises(PublicSessionOpenError, match="checkpoint_invalid"):
        await factory.recover(
            "session:checkpoint",
            paused.checkpoint_id,
            datetime.now(UTC) + timedelta(minutes=5),
        )
    assert reconnect_calls == 0


@pytest.mark.asyncio
async def test_checkpoint_load_rejects_row_and_payload_scope_mismatch(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:scope")
    assert paused.checkpoint_id is not None
    await handle.close()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "INSERT INTO runtime_checkpoints "
            "(session_id, checkpoint_id, schema_version, digest, created_at, payload_json) "
            "SELECT ?, checkpoint_id, schema_version, digest, created_at, payload_json "
            "FROM runtime_checkpoints WHERE session_id = ? AND checkpoint_id = ?",
            ("session:wrong-scope", "session:checkpoint", paused.checkpoint_id),
        )
        connection.commit()

    with pytest.raises(RuntimeCheckpointError, match="checkpoint_scope_mismatch"):
        await store.load("session:wrong-scope", paused.checkpoint_id)
    with pytest.raises(RuntimeCheckpointError, match="checkpoint_scope_mismatch"):
        await store.load_latest("session:wrong-scope")


@pytest.mark.asyncio
async def test_checkpoint_v2_remains_readable_without_effect_projection(tmp_path) -> None:
    handle, store = await _waiting_checkpoint_session(tmp_path)
    paused = await handle.pause("pause:v2-compatibility")
    assert paused.checkpoint_id is not None
    checkpoint = await store.load("session:checkpoint", paused.checkpoint_id)
    assert checkpoint is not None
    raw = json.loads(checkpoint.to_json())
    raw["schema_version"] = "affordance-runtime.checkpoint.v2"
    raw["run"].pop("latest_effect", None)
    raw["run"].pop("effect_reconciliation", None)
    for receipt in (raw.get("last_step") or {}).get("receipts", []):
        receipt.pop("resource_ref", None)
        receipt.pop("semantic_effects", None)
        receipt.pop("reversibility", None)
    unsigned = {key: value for key, value in raw.items() if key not in {"checkpoint_id", "digest"}}
    digest = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    raw["digest"] = digest
    raw["checkpoint_id"] = f"runtime-checkpoint:{digest}"

    restored = RuntimeCheckpoint.from_json(json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    assert restored.schema_version == "affordance-runtime.checkpoint.v2"
    facts = restored.restore_run_facts()
    assert facts.latest_effect is None
    assert facts.effect_reconciliation is None
    await handle.close()


@pytest.mark.asyncio
async def test_revision_outcome_schema_migrates_legacy_rows_fail_closed(tmp_path) -> None:
    path = tmp_path / "legacy-revision-outcomes.sqlite3"
    checkpoint_id = "runtime-checkpoint:" + "a" * 64
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE runtime_revision_outcomes ("
            "session_id TEXT NOT NULL, command_id TEXT NOT NULL, "
            "source_checkpoint_id TEXT NOT NULL, result_checkpoint_id TEXT NOT NULL, "
            "task_revision INTEGER NOT NULL, outcome TEXT NOT NULL, "
            "created_at TEXT NOT NULL, PRIMARY KEY (session_id, command_id))"
        )
        connection.execute(
            "INSERT INTO runtime_revision_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "session:legacy-revision",
                "revise:legacy",
                checkpoint_id,
                checkpoint_id,
                1,
                "revision_no_change",
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()

    outcome = await SQLiteRuntimeCheckpointStore(path).revision_outcome(
        "session:legacy-revision",
        "revise:legacy",
    )

    assert outcome is not None
    assert outcome.payload_digest == "0" * 64
    assert outcome.message == ""
    assert outcome.result_code == "revision_no_change"
    with sqlite3.connect(path) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(runtime_revision_outcomes)")}
    assert {"payload_digest", "message", "result_code"} <= columns


@pytest.mark.asyncio
async def test_revision_commits_new_checkpoint_and_remains_paused(tmp_path) -> None:
    (
        handle,
        store,
        policy,
        revision_compiler,
        goal_compiler,
        environment,
        source,
    ) = await _revisable_checkpoint_session(tmp_path)
    assert source.checkpoint_id is not None
    policy_calls = policy.calls

    revised = await handle.revise(
        _revision_command(
            "revise:ready",
            source.checkpoint_id,
            "Also include the owner",
        )
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.task_text == "Inspect the selected account and its owner"
    assert revised.checkpoint_id is not None
    assert revised.checkpoint_id != source.checkpoint_id
    assert revised.resume_eligible is True
    assert revised.pending_question is None
    assert revised.pending_confirmation is None
    assert revised.last_control_outcome is not None
    assert revised.last_control_outcome.kind == "revise"
    assert revised.last_control_outcome.outcome == "revised"
    assert policy.calls == policy_calls
    assert revision_compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert [task.revision for task in environment.revised_tasks] == [2]
    checkpoint = await store.load("session:revision", revised.checkpoint_id)
    assert checkpoint is not None
    assert checkpoint.restore_task().revision == 2
    assert checkpoint.model_history["active_task_identity"] == (
        "session:revision",
        2,
    )
    assert await store.revision_outcome("session:revision", "revise:ready") == (
        RuntimeCheckpointRevisionOutcome(
            "session:revision",
            "revise:ready",
            source.checkpoint_id,
            revised.checkpoint_id,
            2,
            "revised",
            _revision_command(
                "revise:ready",
                source.checkpoint_id,
                "Also include the owner",
            ).payload_digest,
            "",
        )
    )
    assert await store.checkpoint_revision_outcome(
        "session:revision",
        source.checkpoint_id,
    ) == RuntimeCheckpointRevisionOutcome(
        "session:revision",
        "revise:ready",
        source.checkpoint_id,
        revised.checkpoint_id,
        2,
        "revised",
        _revision_command(
            "revise:ready",
            source.checkpoint_id,
            "Also include the owner",
        ).payload_digest,
        "",
    )
    duplicate = await handle.revise(
        _revision_command(
            "revise:ready",
            source.checkpoint_id,
            "Also include the owner",
        )
    )
    assert duplicate == revised
    assert revision_compiler.calls == 1
    with pytest.raises(PublicSessionConflict, match="command_identity_reused"):
        await handle.revise(
            _revision_command(
                "revise:ready",
                source.checkpoint_id,
                "A different goal under the same command identity",
            )
        )
    assert revision_compiler.calls == 1
    with pytest.raises(PublicSessionConflict, match="command_identity_reused"):
        await handle.revise(
            _revision_command(
                "revise:ready",
                source.checkpoint_id,
                "Also include the owner",
                conversation=RevisionConversationContext(
                    (
                        RevisionConversationTurn(
                            "turn:different-context",
                            "user",
                            "Use the second account",
                        ),
                        RevisionConversationTurn(
                            "revise:ready",
                            "user",
                            "Also include the owner",
                        ),
                    ),
                    "revise:ready",
                ),
            )
        )
    assert revision_compiler.calls == 1
    await handle.close()


@pytest.mark.asyncio
async def test_stale_revision_never_calls_compiler(tmp_path) -> None:
    handle, _store, _policy, compiler, _goal, _environment, source = await _revisable_checkpoint_session(tmp_path)

    with pytest.raises(PublicSessionConflict, match="stale_command"):
        await handle.revise(
            _revision_command(
                "revise:stale",
                source.checkpoint_id,
                "Use the second one",
                task_revision=0,
            )
        )

    assert compiler.calls == 0
    await handle.close()


@pytest.mark.asyncio
async def test_revision_compiler_receives_shell_language_and_runtime_pending_facts(
    tmp_path,
) -> None:
    handle, _store, _policy, compiler, _goal, _environment, source = await _revisable_checkpoint_session(tmp_path)
    conversation = RevisionConversationContext(
        (
            RevisionConversationTurn(
                "answer:prior",
                "user",
                "Use the first account",
            ),
            RevisionConversationTurn(
                "revise:context",
                "user",
                "用第二个",
            ),
        ),
        "revise:context",
    )

    revised = await handle.revise(
        _revision_command(
            "revise:context",
            source.checkpoint_id,
            "用第二个",
            conversation=conversation,
        )
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert compiler.calls == 1
    request = compiler.requests[0]
    assert request.conversation == conversation
    assert request.text == "用第二个"
    assert request.runtime_context.pending_question_id.startswith("interaction:")
    assert request.runtime_context.pending_question == "Which account should I use?"
    assert revised.pending_question is None
    await handle.close()


@pytest.mark.asyncio
async def test_revision_command_reuses_cooperative_pause_without_separate_shell_command(
    tmp_path,
) -> None:
    handle, store, policy, compiler, goal_compiler, environment, before = await _revisable_checkpoint_session(
        tmp_path, pause_source=False
    )
    assert before.checkpoint_id is None
    policy_calls = policy.calls

    revised = await handle.revise(
        _revision_command(
            "revise:single-command",
            None,
            "Also include the owner",
            run_status=PublicSessionStatus.WAITING_USER,
        )
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.checkpoint_id is not None
    assert policy.calls == policy_calls
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert [task.revision for task in environment.revised_tasks] == [2]
    outcome = await store.revision_outcome(
        "session:revision",
        "revise:single-command",
    )
    assert outcome is not None
    assert outcome.source_checkpoint_id != outcome.result_checkpoint_id
    events = tuple(event.type for event in await handle.events(before.event_cursor))
    assert events[-3:] == ("CONTROL_REQUESTED", "RUN_PAUSED", "TASK_REVISED")
    await handle.close()


@pytest.mark.asyncio
async def test_revision_during_policy_waits_for_cooperative_boundary_before_commit(
    tmp_path,
) -> None:
    policy_entered = asyncio.Event()
    policy_release = asyncio.Event()

    class BlockingRevisionPolicy(RecoverableAskPolicy):
        async def decide(self, context):
            policy_entered.set()
            await policy_release.wait()
            return await super().decide(context)

    store = SQLiteRuntimeCheckpointStore(tmp_path / "active-revision.sqlite3")
    policy = BlockingRevisionPolicy()
    compiler = ReadyRevisionCompiler()
    goal_compiler = CountingGoalCompiler()
    environment = RevisionEnvironment(
        initial_observation=_world(),
        independent_observations=(_world(),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: replace(
            _runtime(policy),
            goal_compiler=goal_compiler,
            task_revision_compiler=compiler,
        ),
        lambda _session_id: RuntimeEnvironmentLease(
            environment,
            reconnect_reference="browser-lease:active-revision",
        ),
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:active-revision",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Inspect the selected account")
    await asyncio.wait_for(policy_entered.wait(), timeout=1)

    revising = asyncio.create_task(
        handle.revise(
            _revision_command(
                "revise:during-policy",
                None,
                "Also include the owner",
                run_status=PublicSessionStatus.RUNNING,
            )
        )
    )
    await asyncio.sleep(0)
    assert not revising.done()

    policy_release.set()
    revised = await asyncio.wait_for(revising, timeout=1)

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.checkpoint_id is not None
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert policy.calls == 1
    assert [task.revision for task in environment.revised_tasks] == [2]
    await handle.close()


@pytest.mark.asyncio
async def test_revision_invalidates_old_confirmation_without_dispatch(tmp_path) -> None:
    store = SQLiteRuntimeCheckpointStore(tmp_path / "confirmation-revision.sqlite3")
    policy = RecoverableSelectPolicy()
    compiler = ReadyRevisionCompiler()
    goal_compiler = CountingGoalCompiler()
    environment = RevisionEnvironment(
        initial_observation=_action_world("revision-confirmation-before", False),
        independent_observations=(_action_world("revision-confirmation-after", False),),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: replace(
            _confirmation_runtime(policy),
            goal_compiler=goal_compiler,
            task_revision_compiler=compiler,
        ),
        lambda _session_id: RuntimeEnvironmentLease(
            environment,
            reconnect_reference="browser-lease:confirmation-revision",
        ),
        request_factory=_confirmation_request,
        checkpoint_store=store,
    )
    handle = await factory.open(
        "session:confirmation-revision",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    await handle.start("Enable shared state")
    for _ in range(100):
        waiting = await handle.snapshot()
        if waiting.status is PublicSessionStatus.WAITING_CONFIRMATION:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("revision fixture did not reach confirmation")
    assert waiting.pending_confirmation is not None
    assert environment.execute_calls == 0

    revised = await handle.revise(
        _revision_command(
            "revise:confirmation",
            None,
            "Inspect the account and its owner instead",
            run_status=PublicSessionStatus.WAITING_CONFIRMATION,
        )
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.pending_confirmation is None
    assert revised.resume_eligible is True
    assert environment.execute_calls == 0
    assert policy.calls == 1
    assert compiler.calls == 1
    assert compiler.requests[0].runtime_context.pending_confirmation_id.startswith("confirmation:")
    assert compiler.requests[0].runtime_context.pending_confirmation_summary
    assert compiler.requests[0].runtime_context.pending_confirmation_risk == waiting.pending_confirmation.risk
    assert goal_compiler.revisions == [1, 2]
    await handle.close()


@pytest.mark.asyncio
async def test_revision_nonready_outcome_is_durable_and_keeps_old_checkpoint(tmp_path) -> None:
    compiler = NoChangeRevisionCompiler()
    handle, store, _policy, _, goal_compiler, environment, source = await _revisable_checkpoint_session(
        tmp_path, compiler=compiler
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match="revision_no_change"):
        await handle.revise(
            _revision_command(
                "revise:no-change",
                source.checkpoint_id,
                "Keep the existing task",
            )
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.outcome == "no_change"
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1]
    assert environment.revised_tasks == []
    outcome = await store.revision_outcome("session:revision", "revise:no-change")
    assert outcome is not None and outcome.outcome == "revision_no_change"
    assert outcome.message == "already_equivalent"

    with pytest.raises(PublicSessionConflict, match="revision_no_change"):
        await handle.revise(
            _revision_command(
                "revise:no-change",
                source.checkpoint_id,
                "Keep the existing task",
            )
        )
    assert compiler.calls == 1
    replayed = await handle.snapshot()
    assert replayed.last_control_outcome is not None
    assert replayed.last_control_outcome.message == "already_equivalent"
    await handle.close()


@pytest.mark.asyncio
async def test_revision_source_read_failure_is_typed_and_keeps_old_pause(tmp_path) -> None:
    delegate = SQLiteRuntimeCheckpointStore(tmp_path / "revision-read-failure.sqlite3")
    store = FailingRevisionReadStore(delegate)
    handle, _, _policy, compiler, goal_compiler, environment, source = await _revisable_checkpoint_session(
        tmp_path, store=store
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match="revision_persistence_failed"):
        await handle.revise(
            _revision_command(
                "revise:read-failure",
                source.checkpoint_id,
                "Also include the owner",
            )
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.command_id == "revise:read-failure"
    assert current.last_control_outcome.code == "revision_persistence_failed"
    assert compiler.calls == 0
    assert goal_compiler.revisions == [1]
    assert environment.revised_tasks == []
    await handle.close()


@pytest.mark.asyncio
async def test_revision_rejection_persistence_failure_projects_current_command(tmp_path) -> None:
    delegate = SQLiteRuntimeCheckpointStore(tmp_path / "revision-outcome-failure.sqlite3")
    store = FailingRevisionOutcomeStore(delegate)
    compiler = NoChangeRevisionCompiler()
    handle, _, _policy, _, goal_compiler, environment, source = await _revisable_checkpoint_session(
        tmp_path, store=store, compiler=compiler
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match="revision_persistence_failed"):
        await handle.revise(
            _revision_command(
                "revise:outcome-failure",
                source.checkpoint_id,
                "Keep the current goal",
            )
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.command_id == "revise:outcome-failure"
    assert current.last_control_outcome.code == "revision_persistence_failed"
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1]
    assert environment.revised_tasks == []
    assert (
        await delegate.revision_outcome(
            "session:revision",
            "revise:outcome-failure",
        )
        is None
    )
    await handle.close()


@pytest.mark.asyncio
async def test_revision_rejects_missing_effect_lineage_as_typed_unknown(tmp_path) -> None:
    handle, store, _policy, compiler, goal_compiler, environment, source = await _revisable_checkpoint_session(tmp_path)
    assert source.checkpoint_id is not None
    assert handle._state is not None
    handle._state.execution_count = 1

    with pytest.raises(PublicSessionConflict, match="effect_reconciliation_unknown"):
        await handle.revise(
            _revision_command(
                "revise:effect",
                source.checkpoint_id,
                "Change the goal after an effect",
            )
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.outcome == "effect_reconciliation_required"
    assert current.last_control_outcome.code == "effect_reconciliation_unknown"
    assert compiler.calls == 0
    assert goal_compiler.revisions == [1]
    assert environment.revised_tasks == []
    outcome = await store.revision_outcome("session:revision", "revise:effect")
    assert outcome is not None and outcome.outcome == "effect_reconciliation_required"
    assert outcome.result_code == "effect_reconciliation_unknown"
    await handle.close()


@pytest.mark.asyncio
async def test_compatible_sent_effect_is_retained_without_compensation_dispatch(tmp_path) -> None:
    handle, store, _policy, compiler, environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=True,
    )
    assert source.checkpoint_id is not None

    revised = await handle.revise(
        _revision_command(
            "revise:compatible-effect",
            source.checkpoint_id,
            "Keep shared state enabled",
        )
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.effect_reconciliation is None
    assert environment.execute_calls == 1
    assert compiler.calls == 1
    checkpoint = await store.load("session:effect-revision", revised.checkpoint_id or "")
    assert checkpoint is not None
    assert checkpoint.restore_run_facts().latest_effect is not None
    assert checkpoint.restore_run_facts().effect_reconciliation is None
    await handle.close()


@pytest.mark.asyncio
async def test_reversible_effect_uses_same_pipeline_and_pauses_after_verified_compensation(
    tmp_path,
) -> None:
    handle, store, policy, compiler, environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=False,
    )
    assert source.checkpoint_id is not None

    revised = await handle.revise(
        _revision_command(
            "revise:compensate-effect",
            source.checkpoint_id,
            "Disable shared state instead",
        )
    )

    assert revised.status is PublicSessionStatus.PAUSED
    assert revised.task_revision == 2
    assert revised.effect_reconciliation is not None
    assert revised.effect_reconciliation.status == "pending"
    assert revised.effect_reconciliation.resource_ref == "shared-state"
    assert environment.execute_calls == 1

    await handle.resume("resume:compensate-effect", revised.checkpoint_id or "")
    for _ in range(100):
        compensated = await handle.snapshot()
        if (
            compensated.status is PublicSessionStatus.PAUSED
            and compensated.effect_reconciliation is not None
            and compensated.effect_reconciliation.status == "compensated"
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"compensation did not reach a durable pause: {compensated!r}")

    assert environment.execute_calls == 2
    assert policy.calls == 2
    assert compiler.calls == 1
    assert compensated.resume_eligible is True
    assert compensated.checkpoint_id is not None
    checkpoint = await store.load(
        "session:effect-revision",
        compensated.checkpoint_id,
    )
    assert checkpoint is not None
    facts = checkpoint.restore_run_facts()
    assert facts.effect_reconciliation is not None
    assert facts.effect_reconciliation.status is EffectReconciliationStatus.COMPENSATED
    assert facts.effect_reconciliation.compensation_effect == facts.latest_effect

    await handle.resume("resume:after-compensation", compensated.checkpoint_id)
    finished = await handle.snapshot()
    assert finished.status is PublicSessionStatus.DONE
    assert environment.execute_calls == 2
    await handle.close()


@pytest.mark.asyncio
async def test_compensation_keeps_existing_confirmation_boundary(tmp_path) -> None:
    handle, _store, _policy, _compiler, environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=False,
        revised_risk=RiskProfile.MEDIUM,
    )
    assert source.checkpoint_id is not None
    revised = await handle.revise(
        _revision_command(
            "revise:confirmed-compensation",
            source.checkpoint_id,
            "Disable shared state instead",
        )
    )
    assert revised.checkpoint_id is not None

    await handle.resume("resume:confirmed-compensation", revised.checkpoint_id)
    for _ in range(100):
        waiting = await handle.snapshot()
        if waiting.status is PublicSessionStatus.WAITING_CONFIRMATION:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"compensation did not request confirmation: {waiting!r}")
    assert waiting.pending_confirmation is not None
    assert environment.execute_calls == 1

    await handle.confirm(waiting.pending_confirmation.interrupt_id, approved=True)
    for _ in range(100):
        compensated = await handle.snapshot()
        if (
            compensated.status is PublicSessionStatus.PAUSED
            and compensated.effect_reconciliation is not None
            and compensated.effect_reconciliation.status == "compensated"
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"confirmed compensation did not pause: {compensated!r}")
    assert environment.execute_calls == 2
    await handle.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reversibility", "dispatch_status", "expected_code"),
    (
        (
            Reversibility.IRREVERSIBLE,
            DispatchStatus.SENT,
            "effect_non_compensable",
        ),
        (
            Reversibility.REVERSIBLE,
            DispatchStatus.SENT_UNKNOWN,
            "effect_reconciliation_unknown",
        ),
    ),
)
async def test_unrecoverable_effect_revision_stays_on_source_pause_with_typed_result(
    tmp_path,
    reversibility,
    dispatch_status,
    expected_code,
) -> None:
    handle, store, _policy, compiler, environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=False,
        reversibility=reversibility,
        first_dispatch_status=dispatch_status,
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match=expected_code):
        await handle.revise(
            _revision_command(
                f"revise:{expected_code}",
                source.checkpoint_id,
                "Disable shared state instead",
            )
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.effect_reconciliation is None
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.code == expected_code
    assert environment.execute_calls == 1
    assert compiler.calls == 1
    stored = await store.revision_outcome(
        "session:effect-revision",
        f"revise:{expected_code}",
    )
    assert stored is not None
    assert stored.outcome == "effect_reconciliation_required"
    assert stored.result_code == expected_code
    await handle.close()


@pytest.mark.asyncio
async def test_restart_preserves_pending_reconciliation_without_replaying_original_effect(
    tmp_path,
) -> None:
    handle, store, _policy, _compiler, _environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=False,
    )
    assert source.checkpoint_id is not None
    revised = await handle.revise(
        _revision_command(
            "revise:restart-reconciliation",
            source.checkpoint_id,
            "Disable shared state instead",
        )
    )
    assert revised.checkpoint_id is not None
    await handle.close()

    recovered_policy = RecoverableSelectPolicy()
    recovered_environment = RevisionEnvironment(
        initial_observation=_effect_world("reconnect-initial", True),
        independent_observations=(_effect_world("reconnect-current", True),),
        post_observations=(_effect_world("reconnect-compensated", False),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )
    recovered_runtime = TargetRuntime(
        AgentDecisionPorts(recovered_policy),
        DispatchPostconditionProjector(),
        DesiredEnabledEvaluator(),
        goal_compiler=CountingGoalCompiler(),
    )
    factory = TargetRuntimeSessionFactory(
        lambda _session_id: recovered_runtime,
        lambda _session_id: (_ for _ in ()).throw(AssertionError("normal environment open is forbidden")),
        request_factory=_action_request,
        checkpoint_store=store,
        environment_reconnector=lambda _session_id, reference: RuntimeEnvironmentLease(
            recovered_environment,
            reconnect_reference=reference,
        ),
    )
    recovered = await factory.recover(
        "session:effect-revision",
        revised.checkpoint_id,
        datetime.now(UTC) + timedelta(minutes=5),
    )

    restored = await recovered.snapshot()
    assert restored.effect_reconciliation is not None
    assert restored.effect_reconciliation.status == "pending"
    assert recovered_environment.execute_calls == 0
    assert recovered_policy.calls == 0

    await recovered.resume("resume:restart-reconciliation", revised.checkpoint_id)
    for _ in range(100):
        compensated = await recovered.snapshot()
        if (
            compensated.status is PublicSessionStatus.PAUSED
            and compensated.effect_reconciliation is not None
            and compensated.effect_reconciliation.status == "compensated"
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"restored reconciliation did not close: {compensated!r}")
    assert recovered_environment.execute_calls == 1
    assert recovered_policy.calls == 1
    await recovered.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candidate_action_available", "compensation_post_enabled", "expected_code", "expected_calls"),
    (
        (False, False, "compensation_unavailable", 1),
        (True, True, "compensation_unverified", 2),
    ),
)
async def test_compensation_failure_closes_as_non_resumable_typed_pause(
    tmp_path,
    candidate_action_available,
    compensation_post_enabled,
    expected_code,
    expected_calls,
) -> None:
    handle, _store, policy, _compiler, environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=False,
        candidate_action_available=candidate_action_available,
        compensation_post_enabled=compensation_post_enabled,
    )
    assert source.checkpoint_id is not None
    revised = await handle.revise(
        _revision_command(
            f"revise:{expected_code}",
            source.checkpoint_id,
            "Disable shared state instead",
        )
    )
    assert revised.checkpoint_id is not None

    await handle.resume(f"resume:{expected_code}", revised.checkpoint_id)
    for _ in range(100):
        paused = await handle.snapshot()
        if (
            paused.status is PublicSessionStatus.PAUSED
            and paused.effect_reconciliation is not None
            and paused.effect_reconciliation.status == "needs_input"
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"failed compensation did not close at a pause: {paused!r}")

    assert paused.effect_reconciliation.code == expected_code
    assert paused.resume_eligible is False
    assert PublicSessionCapability.RESUME_TASK not in paused.capabilities
    assert environment.execute_calls == expected_calls
    assert policy.calls == expected_calls
    assert paused.checkpoint_id is not None
    with pytest.raises(PublicSessionConflict, match=expected_code):
        await handle.resume(f"resume-again:{expected_code}", paused.checkpoint_id)
    await handle.close()


@pytest.mark.asyncio
async def test_compensation_policy_and_executor_are_scoped_to_original_resource(tmp_path) -> None:
    policy = ResourceRecordingSelectPolicy()
    handle, _store, _policy, _compiler, environment, source = await _effect_revision_session(
        tmp_path,
        desired_enabled=False,
        candidate_decoy=True,
        policy_override=policy,
    )
    assert source.checkpoint_id is not None
    revised = await handle.revise(
        _revision_command(
            "revise:resource-scoped-compensation",
            source.checkpoint_id,
            "Disable shared state instead",
        )
    )
    assert revised.checkpoint_id is not None

    await handle.resume("resume:resource-scoped-compensation", revised.checkpoint_id)
    for _ in range(100):
        compensated = await handle.snapshot()
        if (
            compensated.status is PublicSessionStatus.PAUSED
            and compensated.effect_reconciliation is not None
            and compensated.effect_reconciliation.status == "compensated"
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError(f"resource-scoped compensation did not close: {compensated!r}")

    assert policy.seen_resources == [("shared-state",), ("shared-state",)]
    assert environment.executed_requests[-1].selection.resource_ref == "shared-state"
    assert all(request.selection.resource_ref != "unrelated-state" for request in environment.executed_requests)
    await handle.close()


@pytest.mark.asyncio
async def test_revision_commit_failure_restores_old_history_environment_and_pause(tmp_path) -> None:
    delegate = SQLiteRuntimeCheckpointStore(tmp_path / "revision-failure.sqlite3")
    store = FailingRevisionStore(delegate)
    handle, _, policy, compiler, goal_compiler, environment, source = await _revisable_checkpoint_session(
        tmp_path, store=store
    )
    assert source.checkpoint_id is not None

    with pytest.raises(PublicSessionConflict, match="revision_persistence_failed"):
        await handle.revise(
            _revision_command(
                "revise:persistence-failure",
                source.checkpoint_id,
                "Also include the owner",
            )
        )

    current = await handle.snapshot()
    assert current.status is PublicSessionStatus.PAUSED
    assert current.task_revision == 1
    assert current.checkpoint_id == source.checkpoint_id
    assert current.last_control_outcome is not None
    assert current.last_control_outcome.code == "revision_persistence_failed"
    assert policy.active_task_identity == ("session:revision", 1)
    assert compiler.calls == 1
    assert goal_compiler.revisions == [1, 2]
    assert [task.revision for task in environment.revised_tasks] == [2, 1]
    assert (
        await delegate.revision_outcome(
            "session:revision",
            "revise:persistence-failure",
        )
        is None
    )
    await handle.close()

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.agent import YieldSubtask
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.mission import (
    EvidenceBundle,
    FinalResponseBoundary,
    FinalResponseRejection,
    ManagerAssessment,
    ManagerDecision,
    ManagerRecoveryView,
    ManagerRequestMode,
    ManagerRoleRequest,
    ManagerRoute,
    MissionOutcome,
    MissionState,
    MissionSupervisor,
    SubtaskContract,
    WorkingFactProposal,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.world.acquisition import ObservationRequestKind, WorldObservationRequest
from tests.support.model_delivery import delivery_for
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
)

FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "task_type": {"type": "string", "const": "RETRIEVE"},
        "status": {"type": "string", "enum": ["SUCCESS", "FAILURE"]},
        "retrieved_data": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "error_details": {"type": "null"},
    },
    "required": ["task_type", "status", "retrieved_data", "error_details"],
    "additionalProperties": False,
}
FINAL_VALUE = {
    "task_type": "RETRIEVE",
    "status": "SUCCESS",
    "retrieved_data": ["Quest Lumaflex™ Band"],
    "error_details": None,
}


class UnknownEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.UNKNOWN, "pre-STOP")


class PostStopEvaluator:
    def __init__(self, fake):
        self.fake = fake
        self.calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        status = TaskEvaluationStatus.COMPLETE if self.fake.final_messages else TaskEvaluationStatus.UNKNOWN
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            "native",
            completion_evidence_refs=(observation.facts[0].fact_id,) if self.fake.final_messages else (),
        )


@dataclass
class YieldPolicy:
    def __post_init__(self):
        self.contexts = []

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    async def decide(self, context):
        self.contexts.append(context)
        return YieldSubtask(context.context_id, "outcome_proposed", "candidate ready")


class DirectResponseManager:
    def __init__(self, *, response=FINAL_VALUE, use_allowed_ref: bool = True, promote: bool = False):
        self.requests = []
        self.response = response
        self.use_allowed_ref = use_allowed_ref
        self.promote = promote

    async def decide(self, request):
        self.requests.append(request)
        if request.mode is ManagerRequestMode.INITIAL_PLAN:
            decision = ManagerDecision(
                ManagerAssessment.NOT_APPLICABLE,
                ManagerRoute.EXECUTE_SUBTASK,
                subtask=SubtaskContract(
                    "Read answer", "Answer is visible", "Provides the requested answer"
                ),
            )
        else:
            refs = request.allowed_evidence_refs[:1] if self.use_allowed_ref else ("fact:disallowed",)
            decision = ManagerDecision(
                ManagerAssessment.SATISFIED,
                ManagerRoute.REQUEST_FINALIZATION,
                evidence_refs=refs,
                reason="Current evidence supports the response.",
                working_facts=(
                    WorkingFactProposal(
                        "terminal_record",
                        refs[0],
                        "carry terminal evidence",
                    ),
                ) if self.promote and refs else (),
                final_response=self.response,
                final_response_evidence_refs=refs,
            )
        return ModelInvocationResult(output=decision)


def _env_task(*, fail_final: bool = False):
    raw = raw_observation(ax_node("input", "textbox", "Answer", value="Done"), goal="Complete the long task.")
    fake = FakeBrowserGym(raw, fail_final=fail_final)
    env, task = open_fake(fake)
    task = replace(
        task,
        inputs={
            PUBLIC_FINAL_RESPONSE_CONTRACT_KEY: {
                "format": "FinalAgentResponse",
                "json_schema": FINAL_SCHEMA,
            }
        },
    )
    return fake, env, task


def _context():
    _, env, task = _env_task()
    world = asyncio.run(env.reset(task)).observation
    evaluation = asyncio.run(UnknownEvaluator().evaluate(task, world))
    return ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        evaluation,
        observation_capabilities=env.observation_capabilities,
        runtime_controls=("yield_subtask",),
    )


def _boundary_input(*, allowed: bool = True, response=FINAL_VALUE):
    _, env, task = _env_task()
    world = asyncio.run(env.reset(task)).observation
    bundle = EvidenceBundle.from_world(world)
    ref = bundle.evidence_records[0].evidence_ref
    subtask = SubtaskContract("Read answer", "Answer is visible", "Provides the requested answer")
    request = ManagerRoleRequest(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        task,
        MissionState.empty(),
        recovery=ManagerRecoveryView("outcome_proposed", True, subtask),
        active_subtask=subtask,
        review_world=world,
        evidence_bundle=bundle,
        final_response_schema=FINAL_SCHEMA,
        allowed_evidence_refs=(ref,) if allowed else (),
    )
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.REQUEST_FINALIZATION,
        final_response=response,
        final_response_evidence_refs=(ref,),
    )
    return request, decision


def test_ordinary_action_policy_catalog_never_contains_submit_final_response() -> None:
    context = _context()
    catalog = compile_grounded_action_catalog(context, delivery_for(context))
    names = {item.spec.name for item in catalog.tools}

    assert "yield_subtask" in names
    assert "submit_final_response" not in names


def test_run10_direct_business_object_is_admitted_without_tool_envelope() -> None:
    request, decision = _boundary_input()

    result = FinalResponseBoundary().admit(decision, request, MissionState.empty(), already_finalized=False)

    assert result.admitted
    assert json.loads(result.response.content) == FINAL_VALUE


def test_pinned_scalar_from_originating_observation_can_support_final_response() -> None:
    _, env, task = _env_task()
    acquired = asyncio.run(env.reset(task)).observation
    assert acquired is not None
    origin_bundle = EvidenceBundle.from_world(acquired)
    record = next(item for item in origin_bundle.evidence_records if item.kind == "fact")
    pinned = WorkingFact("terminal_record", record, 2, "use after a fresh capture")
    reviewed = asyncio.run(env.capture(WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "fresh final review",
    ))).observation
    assert reviewed is not None and reviewed.observation_id != acquired.observation_id
    bundle = EvidenceBundle.from_world(reviewed, (pinned,))
    subtask = SubtaskContract("Read answer", "Answer is visible", "Provides the requested answer")
    request = ManagerRoleRequest(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        task,
        MissionState.empty(),
        recovery=ManagerRecoveryView("outcome_proposed", True, subtask),
        active_subtask=subtask,
        review_world=reviewed,
        evidence_bundle=bundle,
        final_response_schema=FINAL_SCHEMA,
        allowed_evidence_refs=(record.evidence_ref,),
        episode_working_facts=(pinned,),
    )
    decision = ManagerDecision(
        ManagerAssessment.SATISFIED,
        ManagerRoute.REQUEST_FINALIZATION,
        evidence_refs=(record.evidence_ref,),
        final_response=FINAL_VALUE,
        final_response_evidence_refs=(record.evidence_ref,),
    )

    result = FinalResponseBoundary().admit(
        decision,
        request,
        MissionState.empty(),
        already_finalized=False,
    )

    assert result.admitted
    assert result.response is not None


def test_schema_mismatch_and_disallowed_evidence_are_typed_zero_send_rejections() -> None:
    request, malformed = _boundary_input(response={"status": "SUCCESS"})
    schema_rejection = FinalResponseBoundary().admit(
        malformed, request, MissionState.empty(), already_finalized=False
    )
    disallowed_request, valid = _boundary_input(allowed=False)
    evidence_rejection = FinalResponseBoundary().admit(
        valid, disallowed_request, MissionState.empty(), already_finalized=False
    )

    assert schema_rejection.rejection_code is FinalResponseRejection.FINAL_RESPONSE_INVALID
    assert evidence_rejection.rejection_code is FinalResponseRejection.EVIDENCE_LINEAGE_INVALID
    assert schema_rejection.response is None and evidence_rejection.response is None


def test_boundary_rejection_is_atomic_and_duplicate_finalization_is_rejected() -> None:
    request, decision = _boundary_input(allowed=False)
    mission = MissionState.empty()

    rejected = FinalResponseBoundary().admit(decision, request, mission, already_finalized=False)
    duplicate = FinalResponseBoundary().admit(decision, request, mission, already_finalized=True)

    assert mission == MissionState.empty()
    assert not rejected.admitted
    assert duplicate.rejection_code is FinalResponseRejection.ALREADY_FINALIZED


def test_normal_mission_uses_two_manager_calls_no_finalizer_and_one_terminal_chain() -> None:
    fake, env, task = _env_task()
    policy = YieldPolicy()
    evaluator = PostStopEvaluator(fake)
    trace = RunTraceRecorder()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        evaluator,
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(
        MissionSupervisor(DirectResponseManager(), None, max_rounds=2, trace_sink=trace).run(runtime, env, task)
    )

    assert result.outcome is MissionOutcome.FINALIZED
    assert (result.manager_calls, result.auditor_calls) == (2, 0)
    assert result.final_response_boundary_admission_count == 1
    assert result.final_response_boundary_rejection_count == 0
    assert (result.stop_send_count, result.post_stop_capture_count, result.native_evaluator_count) == (1, 1, 1)
    assert [json.loads(item) for item in fake.final_messages] == [FINAL_VALUE]
    assert evaluator.calls == 2  # episode initialization and exactly one post-STOP evaluation
    assert len(policy.contexts) == 1
    assert all("submit_final_response" not in context.runtime_controls for context in policy.contexts)
    assert not any(
        item["event"] == "mission_role_invocation" and item["role"] == "finalizer"
        for item in trace.events
    )
    boundary_event = next(item for item in trace.events if item["event"] == "final_response_boundary_evaluated")
    assert boundary_event["admitted"] is True
    assert "Quest Lumaflex" not in json.dumps(boundary_event)
    evaluator_event = next(
        item for item in trace.events if item["event"] == "native_evaluator_returned"
    )
    assert evaluator_event["evaluation_status"] == "complete"
    assert evaluator_event["evidence_refs"] == (result.state.current_world.facts[0].fact_id,)
    assert next(
        index
        for index, item in enumerate(trace.events)
        if item["event"] == "native_evaluator_returned"
    ) < next(
        index
        for index, item in enumerate(trace.events)
        if item["event"] == "finalization_protocol"
    )


def test_terminal_state_proposal_is_admitted_before_single_finalization_route() -> None:
    fake, env, task = _env_task()
    evaluator = PostStopEvaluator(fake)
    runtime = compose_target_runtime(
        YieldPolicy(),
        ProductionActionOutcomeProjector(),
        evaluator,
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(
        MissionSupervisor(
            DirectResponseManager(promote=True),
            None,
            max_rounds=2,
        ).run(runtime, env, task)
    )

    assert result.outcome is MissionOutcome.FINALIZED
    assert result.mission_state.version == 1
    assert result.mission_state.accepted_facts[0].key == "terminal_record"
    assert result.final_response_boundary_admission_count == 1
    assert (result.stop_send_count, result.native_evaluator_count) == (1, 1)


def test_invalid_response_causes_zero_send_and_no_second_policy_call() -> None:
    fake, env, task = _env_task()
    policy = YieldPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(
        MissionSupervisor(DirectResponseManager(response={"status": "SUCCESS"}), None, max_rounds=2).run(
            runtime, env, task
        )
    )

    assert result.outcome is MissionOutcome.FINALIZATION_NOT_READY
    assert result.final_response_boundary_rejection_count == 1
    assert result.stop_send_count == 0
    assert fake.final_messages == []
    assert len(policy.contexts) == 1


def test_sent_unknown_does_not_retry_stop_and_evaluates_post_world_once() -> None:
    fake, env, task = _env_task(fail_final=True)
    policy = YieldPolicy()
    evaluator = PostStopEvaluator(fake)
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        evaluator,
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(MissionSupervisor(DirectResponseManager(), None, max_rounds=2).run(runtime, env, task))

    assert len(fake.final_messages) == 1
    assert (result.stop_send_count, result.post_stop_capture_count, result.native_evaluator_count) == (1, 1, 1)
    assert evaluator.calls == 2

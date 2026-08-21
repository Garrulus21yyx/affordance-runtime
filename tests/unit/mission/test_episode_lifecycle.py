from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from affordance_runtime.agent import YieldSubtask
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.mission import (
    AuditorDecision,
    EvidenceBoundaryRejectionClass,
    EvidenceBoundaryResult,
    EvidenceRequirement,
    ManagerAssessment,
    ManagerDecision,
    ManagerRequestMode,
    ManagerRoute,
    MissionOutcome,
    MissionState,
    MissionSupervisor,
    SubtaskContract,
    WorkingFactProposal,
    WorkingOutcomeProposal,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
)


class UnknownEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.UNKNOWN,
            "native verifier not terminal",
        )


@dataclass
class YieldPolicy:
    kind: str = "outcome_proposed"
    reason: str = "episode boundary"

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    async def decide(self, context):
        return YieldSubtask(context.context_id, self.kind, self.reason)


@dataclass
class ManagerScript:
    decisions: list[ManagerDecision]

    def __post_init__(self):
        self.requests = []

    async def decide(self, request):
        self.requests.append(request)
        return ModelInvocationResult(output=self.decisions.pop(0))


@dataclass
class FailingManager:
    async def decide(self, _request):
        return ModelInvocationResult(failure=ModelFailure(
            ModelFailureKind.SCHEMA_ERROR,
            "invalid manager output",
            False,
        ))


@dataclass
class LifecycleLog:
    phases: list[str] = field(default_factory=list)

    def manager_started(self) -> None:
        self.phases.append("MANAGER_STARTED")

    def manager_returned(self) -> None:
        self.phases.append("MANAGER_RETURNED")


@dataclass
class AuditorScript:
    decision: AuditorDecision

    def __post_init__(self):
        self.requests = []

    async def audit(self, request):
        self.requests.append(request)
        return ModelInvocationResult(output=self.decision)


@dataclass
class StrictOutcomeManager:
    contract: SubtaskContract

    def __post_init__(self):
        self.requests = []

    async def decide(self, request):
        self.requests.append(request)
        if request.mode is ManagerRequestMode.INITIAL_PLAN:
            return ModelInvocationResult(output=_initial(self.contract))
        evidence_ref = request.allowed_evidence_refs[0]
        return ModelInvocationResult(output=ManagerDecision(
            ManagerAssessment.SATISFIED,
            ManagerRoute.BLOCKED,
            evidence_refs=(evidence_ref,),
            working_outcomes=(WorkingOutcomeProposal(
                "outcome:durable_claim",
                ManagerAssessment.SATISFIED,
                (evidence_ref,),
                "The predeclared durable claim is supported.",
            ),),
            reason="Synthetic strict review completed.",
        ))


@dataclass
class CitingAuditor:
    def __post_init__(self):
        self.requests = []

    async def audit(self, request):
        self.requests.append(request)
        evidence_ref = next(
            record.evidence_ref
            for record in request.audit_bundle.evidence_records
            if (
                record.kind == "fact"
                and isinstance(record.value, str | int | float | bool)
                and record.source_observation_id in request.audit_bundle.source_observation_ids
                and request.audit_bundle.source_coverages.get(
                    record.source_observation_id, ""
                ) != "stale"
            )
        )
        return ModelInvocationResult(output=AuditorDecision(
            ManagerAssessment.SATISFIED,
            (evidence_ref,),
            "Strict claim is independently supported.",
        ))


@dataclass(frozen=True)
class RecoverableShapeBoundary:
    def accept(self, mission, _proposal, _bundle):
        return EvidenceBoundaryResult(
            False,
            mission,
            "working_state_noop",
            EvidenceBoundaryRejectionClass.RECOVERABLE_SHAPE,
        )


def _runtime(kind="outcome_proposed", reason="episode boundary"):
    return compose_target_runtime(
        YieldPolicy(kind, reason),
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        runtime_controls=("yield_subtask",),
    )


def _env_task():
    raw = raw_observation(
        ax_node("input", "textbox", "Answer", value="Done"),
        ax_node("button", "button", "Continue"),
        goal="Complete the long task.",
    )
    fake = FakeBrowserGym(raw)
    env, task = open_fake(fake)
    return fake, env, task


def test_initial_manager_schema_failure_returns_immediately_at_typed_boundary() -> None:
    _, env, task = _env_task()
    lifecycle = LifecycleLog()

    result = asyncio.run(asyncio.wait_for(
        MissionSupervisor(
            FailingManager(),
            lifecycle_sink=lifecycle,
        ).run(_runtime(), env, task),
        timeout=0.5,
    ))

    assert result.outcome is MissionOutcome.MANAGER_FAILURE
    assert result.manager_calls == 1
    assert result.auditor_calls == 0
    assert result.state is None
    assert lifecycle.phases == ["MANAGER_STARTED", "MANAGER_RETURNED"]


def _initial(contract):
    return ManagerDecision(
        ManagerAssessment.NOT_APPLICABLE,
        ManagerRoute.EXECUTE_SUBTASK,
        subtask=contract,
    )


def test_normal_episode_calls_initial_manager_and_one_combined_review_without_auditor() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Read answer", "Answer is visible", "Provides the requested answer")
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(
                ManagerAssessment.SATISFIED,
                ManagerRoute.BLOCKED,
                reason="Review completed; stop this synthetic witness.",
            ),
        ]
    )

    result = asyncio.run(MissionSupervisor(manager, None, max_rounds=1).run(_runtime(), env, task))

    assert result.manager_calls == 2
    assert result.auditor_calls == 0
    assert [request.mode for request in manager.requests] == [
        ManagerRequestMode.INITIAL_PLAN,
        ManagerRequestMode.REVIEW_AND_ROUTE,
    ]
    review = manager.requests[1]
    assert review.active_subtask == contract
    assert review.review_world is not None
    assert review.evidence_bundle.observation_id == review.review_world.observation_id


def test_evidence_packet_yields_natural_language_proposal_without_required_pins() -> None:
    _, env, task = _env_task()
    proposal = "Result: facility name, region code, and measured distance are visible."
    contract = SubtaskContract(
        "Review one composite result",
        "One composite business result is reviewable",
        "Verifies the requested composite result",
        "evidence_packet",
        required_evidence=(
            EvidenceRequirement(
                "result_details",
                "facility name, region code, and measured distance",
            ),
        ),
    )
    manager = ManagerScript([
        _initial(contract),
        ManagerDecision(
            ManagerAssessment.SATISFIED,
            ManagerRoute.BLOCKED,
            reason="Synthetic review completed.",
        ),
    ])

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=1).run(
            _runtime(reason=proposal),
            env,
            task,
        )
    )

    assert result.manager_calls == 2
    review = manager.requests[1]
    assert review.episode_working_facts == ()
    assert review.recovery is not None
    assert review.recovery.outcome_proposal == proposal
    assert review.evidence_bundle.observation_id == review.review_world.observation_id
    assert review.allowed_evidence_refs


def test_supervisor_consumes_runtime_only_subtask_fields_before_action_policy() -> None:
    class CapturedInitialization(RuntimeError):
        pass

    @dataclass
    class CapturingRuntime:
        kwargs: dict | None = None

        async def initialize_from_world(self, task, world, goal_resolution, **kwargs):
            del task, world, goal_resolution
            self.kwargs = kwargs
            raise CapturedInitialization

    _, env, task = _env_task()
    contract = SubtaskContract(
        "Inspect one result",
        "One result is visible",
        "Provides the requested result",
        constraints=("Use the current result",),
        relevant_fact_keys=("selected_fact",),
        episode_turn_budget=3,
        related_audit_ids=("claim:strict",),
    )
    runtime = CapturingRuntime()

    with pytest.raises(CapturedInitialization):
        asyncio.run(
            MissionSupervisor(ManagerScript([_initial(contract)]), None).run(
                runtime,
                env,
                task,
            )
        )

    assert runtime.kwargs is not None
    assert runtime.kwargs["max_turns"] == 3
    assert runtime.kwargs["working_facts"] == ()
    projected = runtime.kwargs["active_subtask"]
    assert projected.objective == contract.objective
    assert projected.task_link == contract.task_link
    assert projected.constraints == contract.constraints
    assert not hasattr(projected, "relevant_fact_keys")
    assert not hasattr(projected, "episode_turn_budget")
    assert not hasattr(projected, "related_audit_ids")


def test_stall_review_accepts_materially_changed_subtask() -> None:
    _, env, task = _env_task()
    first = SubtaskContract(
        "Try route A", "Answer appears", "Provides the requested answer", episode_turn_budget=1
    )
    changed = SubtaskContract(
        "Try route B", "Report table appears", "Provides the requested report", episode_turn_budget=1
    )
    manager = ManagerScript(
        [
            _initial(first),
            ManagerDecision(
                ManagerAssessment.UNSATISFIED,
                ManagerRoute.EXECUTE_SUBTASK,
                subtask=changed,
            ),
        ]
    )

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=1).run(_runtime("stalled"), env, task)
    )

    assert result.outcome is MissionOutcome.ROUND_BUDGET_EXHAUSTED
    assert result.manager_calls == 2


def test_repeated_failed_strategy_returns_typed_strategy_not_changed_without_third_episode() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract(
        "Try route A", "Answer appears", "Provides the requested answer", episode_turn_budget=1
    )
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(
                ManagerAssessment.UNSATISFIED,
                ManagerRoute.EXECUTE_SUBTASK,
                subtask=contract,
            ),
        ]
    )

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=3).run(_runtime("stalled"), env, task)
    )

    assert result.outcome is MissionOutcome.STRATEGY_NOT_CHANGED
    assert result.manager_calls == 2
    assert result.state.status is RunStatus.BLOCKED


def test_needs_replan_allows_one_deliberate_manager_retry_and_zero_gui_dispatch() -> None:
    fake, env, task = _env_task()
    rejected = SubtaskContract(
        "Collect an unnecessary intermediate",
        "Intermediate data is visible",
        "Indirectly relates to the requested answer",
        episode_turn_budget=1,
    )
    changed = SubtaskContract(
        "Read the requested answer directly",
        "The requested answer is visible",
        "Provides the unresolved requested answer",
        episode_turn_budget=1,
    )
    manager = ManagerScript([
        _initial(rejected),
        ManagerDecision(
            ManagerAssessment.UNSATISFIED,
            ManagerRoute.EXECUTE_SUBTASK,
            subtask=rejected,
        ),
        ManagerDecision(
            ManagerAssessment.UNSATISFIED,
            ManagerRoute.EXECUTE_SUBTASK,
            subtask=changed,
        ),
    ])

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=1).run(
            _runtime("needs_replan", "The advisory subtask does not plausibly advance TaskGoal."),
            env,
            task,
        )
    )

    assert result.outcome is MissionOutcome.ROUND_BUDGET_EXHAUSTED
    assert result.manager_calls == 3
    assert result.auditor_calls == 0
    assert fake.actions == []
    assert result.mission_state.version == 0
    deliberate = manager.requests[2]
    assert deliberate.recovery is not None
    assert deliberate.recovery.recovery_signal is not None
    assert deliberate.recovery.recovery_signal.kind.value == "subtask_misaligned"
    assert deliberate.recovery.recovery_signal.recovery_attempt == 2


def test_needs_replan_blocks_after_two_materially_unchanged_manager_strategies() -> None:
    fake, env, task = _env_task()
    contract = SubtaskContract(
        "Collect an unnecessary intermediate",
        "Intermediate data is visible",
        "Indirectly relates to the requested answer",
        episode_turn_budget=1,
    )
    repeated = ManagerDecision(
        ManagerAssessment.UNSATISFIED,
        ManagerRoute.EXECUTE_SUBTASK,
        subtask=contract,
    )
    manager = ManagerScript([_initial(contract), repeated, repeated])

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=2).run(
            _runtime("needs_replan", "The advisory subtask does not plausibly advance TaskGoal."),
            env,
            task,
        )
    )

    assert result.outcome is MissionOutcome.STRATEGY_NOT_CHANGED
    assert result.manager_calls == 3
    assert result.state.status is RunStatus.BLOCKED
    assert result.auditor_calls == 0
    assert result.mission_state.version == 0
    assert fake.actions == []


def test_recoverable_working_proposal_shape_feedback_reaches_next_manager_review() -> None:
    _, env, task = _env_task()
    first = SubtaskContract(
        "Read one partial result",
        "One partial result is visible",
        "Provides one requested partial result",
        episode_turn_budget=1,
    )
    second = SubtaskContract(
        "Read the next partial result",
        "The next partial result is visible",
        "Provides the next unresolved requested result",
        episode_turn_budget=1,
    )

    @dataclass
    class RecoverableProposalManager:
        requests: list = field(default_factory=list)

        async def decide(self, request):
            self.requests.append(request)
            if request.mode is ManagerRequestMode.INITIAL_PLAN:
                return ModelInvocationResult(output=_initial(first))
            if len(self.requests) == 2:
                evidence_ref = request.allowed_evidence_refs[0]
                return ModelInvocationResult(output=ManagerDecision(
                    ManagerAssessment.UNSATISFIED,
                    ManagerRoute.EXECUTE_SUBTASK,
                    evidence_refs=(evidence_ref,),
                    working_outcomes=(WorkingOutcomeProposal(
                        "outcome:partial",
                        ManagerAssessment.SATISFIED,
                        (evidence_ref,),
                        "One partial result is supported.",
                    ),),
                    subtask=second,
                ))
            return ModelInvocationResult(output=ManagerDecision(
                ManagerAssessment.UNSATISFIED,
                ManagerRoute.BLOCKED,
                reason="Synthetic review stops after receiving boundary feedback.",
            ))

    manager = RecoverableProposalManager()
    result = asyncio.run(
        MissionSupervisor(
            manager,
            None,
            boundary=RecoverableShapeBoundary(),
            max_rounds=2,
        ).run(_runtime(), env, task)
    )

    assert result.outcome is MissionOutcome.BLOCKED
    assert result.boundary_rejections == 1
    assert result.mission_state == MissionState.empty()
    assert manager.requests[2].recovery is not None
    assert manager.requests[2].recovery.working_proposal_feedback == (
        "working_proposal_rejected:working_state_noop"
    )


def test_manager_satisfied_assessment_never_becomes_native_task_success() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Read answer", "Answer is visible", "Provides the requested answer")
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(ManagerAssessment.SATISFIED, ManagerRoute.BLOCKED),
        ]
    )

    result = asyncio.run(MissionSupervisor(manager, None, max_rounds=1).run(_runtime(), env, task))

    assert result.status is RunStatus.BLOCKED
    assert result.outcome is not MissionOutcome.TASK_COMPLETE


def test_manager_unoffered_bundle_citation_is_typed_boundary_rejection() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Read answer", "Answer is visible", "Provides the requested answer")

    @dataclass
    class UnofferedCitationManager:
        async def decide(self, request):
            if request.mode is ManagerRequestMode.INITIAL_PLAN:
                return ModelInvocationResult(output=_initial(contract))
            unoffered = next(
                record.evidence_ref
                for record in request.evidence_bundle.evidence_records
                if record.evidence_ref not in request.allowed_evidence_refs
            )
            return ModelInvocationResult(output=ManagerDecision(
                ManagerAssessment.UNKNOWN,
                ManagerRoute.BLOCKED,
                evidence_refs=(unoffered,),
                reason="Synthetic unoffered citation.",
            ))

    result = asyncio.run(
        MissionSupervisor(UnofferedCitationManager(), None, max_rounds=1).run(
            _runtime(), env, task
        )
    )

    assert result.outcome is MissionOutcome.BOUNDARY_REJECTED
    assert result.boundary_rejections == 1


def test_manager_nested_unoffered_fact_citation_cannot_bypass_public_refs() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Read answer", "Answer is visible", "Provides the requested answer")

    @dataclass
    class NestedCitationManager:
        async def decide(self, request):
            if request.mode is ManagerRequestMode.INITIAL_PLAN:
                return ModelInvocationResult(output=_initial(contract))
            unoffered = next(
                record.evidence_ref
                for record in request.evidence_bundle.evidence_records
                if record.evidence_ref not in request.allowed_evidence_refs
            )
            return ModelInvocationResult(output=ManagerDecision(
                ManagerAssessment.SATISFIED,
                ManagerRoute.BLOCKED,
                working_facts=(WorkingFactProposal(
                    "hidden_value",
                    unoffered,
                    "must not bypass offered review refs",
                ),),
                reason="Synthetic nested citation bypass.",
            ))

    result = asyncio.run(
        MissionSupervisor(NestedCitationManager(), None, max_rounds=1).run(
            _runtime(), env, task
        )
    )

    assert result.outcome is MissionOutcome.BOUNDARY_REJECTED
    assert result.boundary_rejections == 1


def test_predeclared_strict_subtask_without_claim_proposal_does_not_call_auditor() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract(
        "Inspect irreversible result",
        "The durable claim is visible",
        "Verifies the requested durable result",
        related_audit_ids=("claim:durable",),
    )
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(ManagerAssessment.SATISFIED, ManagerRoute.BLOCKED),
        ]
    )
    auditor = AuditorScript(
        AuditorDecision(ManagerAssessment.SATISFIED, reason="Strict claim is supported.")
    )

    result = asyncio.run(
        MissionSupervisor(
            manager,
            auditor,
            max_rounds=1,
            strict_verification=True,
        ).run(_runtime(), env, task)
    )

    assert result.auditor_calls == 0
    assert auditor.requests == []


def test_explicit_strict_outcome_claim_calls_citing_optional_auditor_once() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract(
        "Inspect irreversible result",
        "The durable claim is visible",
        "Verifies the requested durable result",
        related_audit_ids=("claim:durable",),
    )
    manager = StrictOutcomeManager(contract)
    auditor = CitingAuditor()

    result = asyncio.run(
        MissionSupervisor(
            manager,
            auditor,
            max_rounds=1,
            strict_verification=True,
        ).run(_runtime(), env, task)
    )

    assert result.auditor_calls == 1
    assert len(auditor.requests) == 1
    assert auditor.requests[0].related_audit_ids == contract.related_audit_ids
    assert result.mission_state.version == 1


def test_exact_fact_only_proposal_needs_no_independent_auditor() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract(
        "Read exact value",
        "One scalar evidence packet is visible",
        "Provides the requested exact value",
        related_audit_ids=("claim:durable",),
    )

    @dataclass
    class FactManager:
        def __post_init__(self):
            self.requests = []

        async def decide(self, request):
            self.requests.append(request)
            if request.mode is ManagerRequestMode.INITIAL_PLAN:
                return ModelInvocationResult(output=_initial(contract))
            evidence_ref = request.allowed_evidence_refs[0]
            return ModelInvocationResult(output=ManagerDecision(
                ManagerAssessment.SATISFIED,
                ManagerRoute.BLOCKED,
                evidence_refs=(evidence_ref,),
                working_facts=(WorkingFactProposal(
                    "exact_value",
                    evidence_ref,
                    "carry exact scalar evidence",
                ),),
                reason="Exact evidence retained.",
            ))

    manager = FactManager()
    auditor = CitingAuditor()
    result = asyncio.run(
        MissionSupervisor(
            manager,
            auditor,
            max_rounds=1,
            strict_verification=True,
        ).run(_runtime(), env, task)
    )

    assert result.auditor_calls == 0
    assert auditor.requests == []
    assert result.mission_state.version == 1
    assert result.mission_state.accepted_facts[0].key == "exact_value"


def test_strict_verification_is_latched_to_at_most_one_auditor_call() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract(
        "Inspect durable result",
        "One durable evidence packet is visible",
        "Verifies the requested durable result",
        related_audit_ids=("claim:durable",),
    )

    @dataclass
    class TwoClaimManager:
        reviews: int = 0

        async def decide(self, request):
            if request.mode is ManagerRequestMode.INITIAL_PLAN:
                return ModelInvocationResult(output=_initial(contract))
            self.reviews += 1
            evidence_ref = request.allowed_evidence_refs[0]
            proposal = WorkingOutcomeProposal(
                f"outcome:durable_{self.reviews}",
                ManagerAssessment.SATISFIED,
                (evidence_ref,),
                "One predeclared strict claim.",
            )
            return ModelInvocationResult(output=ManagerDecision(
                ManagerAssessment.SATISFIED,
                (
                    ManagerRoute.EXECUTE_SUBTASK
                    if self.reviews == 1
                    else ManagerRoute.BLOCKED
                ),
                evidence_refs=(evidence_ref,),
                working_outcomes=(proposal,),
                subtask=contract if self.reviews == 1 else None,
                reason="Bounded strict verification witness.",
            ))

    manager = TwoClaimManager()
    auditor = CitingAuditor()
    result = asyncio.run(
        MissionSupervisor(
            manager,
            auditor,
            max_rounds=2,
            strict_verification=True,
        ).run(_runtime(), env, task)
    )

    assert result.outcome is MissionOutcome.AUDITOR_FAILURE
    assert result.auditor_calls == 1
    assert len(auditor.requests) == 1
    assert result.mission_state.version == 1

"""Small authoritative state for the simplified GUI-agent loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.actions.paging import InternalActionPage
from affordance_runtime.agent.context.budgets import DEFAULT_MAX_HISTORY_SERIALIZED_BYTES
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.episode_history import (
    EpisodeHistoryCapacityError,
    render_episode_history,
)
from affordance_runtime.agent.context.observation_delivery import ObservationDeliveryStore
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicWorldDelta,
    WorldTransitionProjector,
)
from affordance_runtime.agent.decisions import (
    AgentDecision,
    DecisionKind,
    FinalResponse,
    LocalToolResult,
    SelectAction,
    SetFormFields,
)
from affordance_runtime.agent.finalization import FinalizationProtocolResult
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.agent.working_facts import (
    MAX_WORKING_FACTS,
    WorkingFact,
    validate_working_fact_collection,
)
from affordance_runtime.evaluation.contracts import (
    ActionOutcome,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ExecutionCompletion, ExecutionReceiptBatch
from affordance_runtime.goals.plan import GoalPlanResolution, Ready
from affordance_runtime.immutable import freeze_json
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.world.contracts import WorldObservation

if TYPE_CHECKING:
    from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot
    from affordance_runtime.agent.recovery import RecoverySignal


class RunStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class StepResult:
    """One policy outcome's concise feedback; never a replay or ledger record."""

    decision: AgentDecision | PolicyFailure
    before_world: WorldObservation
    after_world: WorldObservation
    task_evaluation: TaskEvaluation
    status_after: RunStatus = RunStatus.RUNNING
    execution_receipts: ExecutionReceiptBatch | None = None
    action_outcome: ActionOutcome | None = None
    confirmation: RiskAssessment | None = None
    feedback: str = ""
    action_page: InternalActionPage | None = None
    waited_ms: int = 0
    failure_code: AgentFailureCode | None = None
    runtime_failure: RuntimeFailure | None = None
    policy_observation: ActorWorldSnapshot | None = None
    policy_target_refs: Mapping[str, str] = field(default_factory=dict)
    action_page_result: Mapping[str, object] = field(default_factory=dict)
    recovery_signal: RecoverySignal | None = None
    finalization: FinalizationProtocolResult | None = None
    public_world_delta: PublicWorldDelta | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        delta = self.public_world_delta
        if delta is None:
            delta = WorldTransitionProjector().project(self.before_world, self.after_world)
            object.__setattr__(self, "public_world_delta", delta)
        elif not isinstance(delta, PublicWorldDelta):
            raise TypeError("step public World delta must be typed")
        if (
            delta.before_observation_id != self.before_world.observation_id
            or delta.after_observation_id != self.after_world.observation_id
        ):
            raise ValueError("step public World delta must match its exact Worlds")
        if not isinstance(self.decision, AgentDecision | PolicyFailure):
            raise TypeError("step decision must belong to the closed decision algebra")
        if not isinstance(self.status_after, RunStatus):
            raise TypeError("step status must be typed")
        if self.waited_ms < 0:
            raise ValueError("step wait duration cannot be negative")
        if self.task_evaluation.observation_id != self.after_world.observation_id:
            raise ValueError("step task evaluation must describe the after-world")
        if self.action_outcome is not None:
            if self.execution_receipts is None or not self.execution_receipts.receipts:
                raise ValueError("action outcome requires an execution")
            final_receipt = self.execution_receipts.receipts[-1]
            if (
                self.action_outcome.request_id != final_receipt.request.request_id
                or self.action_outcome.before_observation_id
                not in {
                    self.before_world.observation_id,
                    final_receipt.request.world_observation_id,
                }
                or self.action_outcome.after_observation_id != self.after_world.observation_id
            ):
                raise ValueError("step action outcome does not match its worlds and execution")
            if (
                self.action_outcome.public_world_delta is not None
                and self.action_outcome.public_world_delta is not delta
            ):
                raise ValueError("step consumers must share one public World delta instance")
        if self.confirmation is not None and self.execution_receipts is not None:
            raise ValueError("a pending confirmation cannot already contain execution")
        if self.execution_receipts is not None:
            if not isinstance(self.decision, SelectAction | SetFormFields):
                raise ValueError("effectful receipts require an effectful decision")
            if any(
                self.decision.tool_call_id != item.request.tool_call_id for item in self.execution_receipts.receipts
            ):
                raise ValueError("step decision/execution tool call lineage mismatch")
        if self.failure_code is not None and not isinstance(self.failure_code, AgentFailureCode):
            raise TypeError("step failure code must be typed")
        if self.failure_code is not None and self.status_after not in {
            RunStatus.BLOCKED,
            RunStatus.FAILED,
        }:
            raise ValueError("step failure code requires terminal failure status")
        if self.runtime_failure is not None and not isinstance(self.runtime_failure, RuntimeFailure):
            raise TypeError("step runtime failure must be typed")
        if self.status_after is RunStatus.RUNNING and self.runtime_failure is not None:
            raise ValueError("RUNNING step cannot carry terminal failure fields")
        if self.runtime_failure is not None and self.status_after is not RunStatus.FAILED:
            raise ValueError("runtime failure requires FAILED status")
        if isinstance(self.decision, LocalToolResult) and self.execution_receipts is not None:
            raise ValueError("a local tool result cannot contain GUI receipts")
        if (
            self.execution_receipts is not None
            and self.execution_receipts.completion is ExecutionCompletion.CANCELLED
            and self.status_after is not RunStatus.CANCELLED
        ):
            raise ValueError("cancelled execution receipts require CANCELLED status")
        if (
            self.status_after is RunStatus.CANCELLED
            and self.execution_receipts is not None
            and (self.execution_receipts.completion is not ExecutionCompletion.CANCELLED)
        ):
            raise ValueError("cancelled effectful step requires cancelled receipt completion")
        if self.recovery_signal is not None:
            from affordance_runtime.agent.recovery import RecoverySignal

            if not isinstance(self.recovery_signal, RecoverySignal):
                raise TypeError("step recovery signal must be typed")
        if self.finalization is not None:
            if not isinstance(self.decision, FinalResponse):
                raise ValueError("finalization facts require a final-response decision")
            if not isinstance(self.finalization, FinalizationProtocolResult):
                raise TypeError("step finalization facts must be typed")
            if (
                self.finalization.post_stop_observation_id
                and self.finalization.post_stop_observation_id != self.after_world.observation_id
            ):
                raise ValueError("finalization capture must identify the step after-world")
            if (
                self.finalization.native_evaluation_status is not None
                and self.finalization.native_evaluation_status is not self.task_evaluation.status
            ):
                raise ValueError("finalization status must match the step task evaluation")
            if (
                not self.finalization.post_stop_observation_id
                and self.after_world.observation_id != self.before_world.observation_id
            ):
                raise ValueError("finalization without capture cannot advance the after-world")
            _validate_finalization_run_status(
                self.finalization,
                self.status_after,
            )
        if not self.feedback.strip():
            raise ValueError("step feedback must be concise and nonblank")
        object.__setattr__(self, "action_page_result", freeze_json(dict(self.action_page_result)))

    @property
    def execution_attempt_count(self) -> int:
        return self.execution_receipts.execution_count if self.execution_receipts is not None else 0

    @property
    def tool_result(self) -> Mapping[str, object] | None:
        """Expose the Registry-owned result without storing a second copy."""

        return self.decision.result if isinstance(self.decision, LocalToolResult) else None


@dataclass
class RunState:
    """The sole mutable control value for one simplified run."""

    current_world: WorldObservation
    current_task_evaluation: TaskEvaluation
    remaining_steps: int
    status: RunStatus = RunStatus.RUNNING
    last_step: StepResult | None = None
    observation_count: int = 1
    execution_count: int = 0
    step_count: int = 0
    context_generation: int = 0
    recent_steps: tuple[AgentTurnView, ...] = ()
    action_page: InternalActionPage | None = None
    waited_ms: int = 0
    task_revision: int = 1
    goal_resolution: GoalPlanResolution | None = None
    goal_plan_version_counter: int = 0
    working_facts: tuple[WorkingFact, ...] = ()
    delivery_lens: WorldDeliveryLens | None = None
    recovery_signal: RecoverySignal | None = None
    committed_sent_unknown_count: int = 0
    decision_counts: dict[DecisionKind, int] = field(default_factory=dict)
    currentness_probe_count: int = 0
    latest_action_outcome: ActionOutcome | None = None
    finalization: FinalizationProtocolResult | None = None
    delivery_store: ObservationDeliveryStore = field(default_factory=ObservationDeliveryStore)
    delivery_index: WorldDeliveryIndex | None = None
    prior_delivery_index: WorldDeliveryIndex | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.current_task_evaluation.observation_id != self.current_world.observation_id:
            raise ValueError("run evaluation must describe the current world")
        if self.remaining_steps < 0:
            raise ValueError("remaining steps cannot be negative")
        if self.observation_count < 1 or self.execution_count < 0 or self.step_count < 0:
            raise ValueError("run counters are invalid")
        if self.waited_ms < 0:
            raise ValueError("run wait duration cannot be negative")
        if self.task_revision < 1:
            raise ValueError("run task revision must be positive")
        if self.goal_plan_version_counter < 0:
            raise ValueError("goal plan version counter cannot be negative")
        if self.committed_sent_unknown_count < 0:
            raise ValueError("run sent-unknown count cannot be negative")
        if self.currentness_probe_count < 0:
            raise ValueError("run currentness probe count cannot be negative")
        if self.latest_action_outcome is not None and not isinstance(self.latest_action_outcome, ActionOutcome):
            raise TypeError("run latest action outcome must be typed")
        if self.finalization is not None and not isinstance(
            self.finalization,
            FinalizationProtocolResult,
        ):
            raise TypeError("run finalization facts must be typed")
        if self.finalization is not None:
            if (
                self.finalization.post_stop_observation_id
                and self.finalization.post_stop_observation_id != self.current_world.observation_id
            ):
                raise ValueError("run finalization capture must identify the current world")
            if (
                self.finalization.native_evaluation_status is not None
                and self.finalization.native_evaluation_status is not self.current_task_evaluation.status
            ):
                raise ValueError("run finalization status must match the current task evaluation")
            _validate_finalization_run_status(self.finalization, self.status)
        if not isinstance(self.delivery_store, ObservationDeliveryStore):
            raise TypeError("run observation delivery store must be typed")
        if self.delivery_index is not None:
            if not isinstance(self.delivery_index, WorldDeliveryIndex):
                raise TypeError("run delivery index must be typed")
            if self.delivery_index.world_observation_id != self.current_world.observation_id:
                raise ValueError("run delivery index must belong to the current World")
        if self.prior_delivery_index is not None and not isinstance(
            self.prior_delivery_index,
            WorldDeliveryIndex,
        ):
            raise TypeError("run prior delivery index must be typed")
        if any(
            not isinstance(kind, DecisionKind) or type(count) is not int or count < 0
            for kind, count in self.decision_counts.items()
        ):
            raise ValueError("run decision counts must use the closed decision algebra")
        if isinstance(self.goal_resolution, Ready):
            plan = self.goal_resolution.accepted_plan
            if plan.task_revision != self.task_revision:
                raise ValueError("ready run goal plan must match the current task")
            if self.goal_plan_version_counter < plan.plan_version:
                raise ValueError("goal plan counter cannot precede the accepted plan")
        self.recent_steps = tuple(self.recent_steps)
        if any(not isinstance(item, AgentTurnView) for item in self.recent_steps):
            raise ValueError("recent step context must be public")
        self.working_facts = validate_working_fact_collection(self.working_facts)
        if self.delivery_lens is not None:
            if not isinstance(self.delivery_lens, WorldDeliveryLens):
                raise TypeError("run delivery lens must be typed")
            if self.delivery_lens.world_observation_id != self.current_world.observation_id:
                raise ValueError("run delivery lens must belong to current world")
        if self.recovery_signal is not None:
            from affordance_runtime.agent.recovery import RecoverySignal

            if not isinstance(self.recovery_signal, RecoverySignal):
                raise TypeError("run recovery signal must be typed")

    @property
    def terminal(self) -> bool:
        return self.status in {
            RunStatus.DONE,
            RunStatus.BLOCKED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }

    @property
    def final_observation(self) -> WorldObservation:
        return self.current_world

    @property
    def policy_failure(self) -> PolicyFailure | None:
        decision = self.last_step.decision if self.last_step is not None else None
        return decision if isinstance(decision, PolicyFailure) else None

    @property
    def failure_code(self) -> AgentFailureCode | None:
        return self.last_step.failure_code if self.last_step is not None else None

    @property
    def task_outcome(self):
        return self.current_task_evaluation.outcome

    @property
    def runtime_failure(self) -> RuntimeFailure | None:
        return self.last_step.runtime_failure if self.last_step is not None else None

    @property
    def sent_unknown_count(self) -> int:
        return self.committed_sent_unknown_count

    def next_context_generation(self) -> int:
        self.context_generation += 1
        return self.context_generation

    def install_delivery_index(self, index: WorldDeliveryIndex) -> None:
        if index.world_observation_id != self.current_world.observation_id:
            raise ValueError("cannot install a delivery index for another World")
        self.delivery_index = index
        self.prior_delivery_index = None

    def resume(self, expected: RunStatus) -> None:
        """Perform the sole non-StepResult transition back into the running loop."""

        if expected not in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}:
            raise ValueError("only a typed waiting status can be resumed")
        if self.status is not expected:
            raise ValueError("run resume status does not match the pending boundary")
        self.status = RunStatus.RUNNING

    def remember_step(
        self,
        step: AgentTurnView,
        *,
        max_bytes: int = DEFAULT_MAX_HISTORY_SERIALIZED_BYTES,
    ) -> None:
        if not isinstance(step, AgentTurnView):
            raise TypeError("run step memory must be model-safe")
        candidate = (*self.recent_steps, step)
        render_episode_history(candidate, max_bytes)
        self.recent_steps = candidate

    def can_remember_step(
        self,
        step: AgentTurnView,
        *,
        max_bytes: int = DEFAULT_MAX_HISTORY_SERIALIZED_BYTES,
    ) -> bool:
        if not isinstance(step, AgentTurnView):
            raise TypeError("run step memory must be model-safe")
        try:
            render_episode_history((*self.recent_steps, step), max_bytes)
        except EpisodeHistoryCapacityError:
            return False
        return True

    def remember_working_fact(self, fact: WorkingFact) -> None:
        previous = next((item for item in self.working_facts if item.key == fact.key), None)
        if previous is not None:
            if previous.record.evidence_ref == fact.record.evidence_ref:
                return
            raise ValueError("working fact key already identifies different evidence")
        if len(self.working_facts) >= MAX_WORKING_FACTS:
            raise ValueError("episode working fact capacity is exhausted")
        self.working_facts = validate_working_fact_collection((*self.working_facts, fact))

    def apply(self, result: StepResult, *, consume_step: bool = True) -> None:
        if self.status is not RunStatus.RUNNING:
            raise ValueError("only a running state can accept a step")
        if result.before_world.observation_id != self.current_world.observation_id:
            raise ValueError("step starts from a stale world")
        acquired_new_world = result.after_world.observation_id != result.before_world.observation_id
        self.delivery_store = self.delivery_store.advance(
            result,
            step_index=max(1, self.step_count + int(consume_step)),
        )
        self.current_world = result.after_world
        self.current_task_evaluation = result.task_evaluation
        self.last_step = result
        self.status = result.status_after
        if consume_step:
            self.remaining_steps = max(0, self.remaining_steps - 1)
        self.observation_count += int(acquired_new_world)
        self.execution_count += result.execution_attempt_count
        if result.action_outcome is not None:
            self.latest_action_outcome = result.action_outcome
        if result.execution_receipts is not None:
            self.committed_sent_unknown_count += result.execution_receipts.sent_unknown_count
        self.step_count += int(consume_step)
        if not isinstance(result.decision, PolicyFailure):
            kind = result.decision.kind
            self.decision_counts[kind] = self.decision_counts.get(kind, 0) + 1
        self.action_page = result.action_page
        if acquired_new_world:
            self.prior_delivery_index = self.delivery_index
            self.delivery_index = None
            self.delivery_lens = None
            self.action_page = None
        self.waited_ms += result.waited_ms
        if isinstance(result.decision, LocalToolResult) and result.decision.working_fact is not None:
            self.remember_working_fact(result.decision.working_fact)
        if isinstance(result.decision, LocalToolResult) and result.decision.delivery_lens is not None:
            lens = result.decision.delivery_lens
            if lens.world_observation_id == self.current_world.observation_id:
                self.delivery_lens = lens
                self.action_page = None
        self.recovery_signal = result.recovery_signal
        if result.finalization is not None:
            self.finalization = result.finalization
        if self.status is RunStatus.RUNNING and self.remaining_steps == 0:
            self.status = RunStatus.BLOCKED


def _validate_finalization_run_status(
    facts: FinalizationProtocolResult,
    status: RunStatus,
) -> None:
    native = facts.native_evaluation_status
    if native is not None:
        expected = {
            TaskEvaluationStatus.COMPLETE: RunStatus.DONE,
            TaskEvaluationStatus.BLOCKED: RunStatus.BLOCKED,
            TaskEvaluationStatus.INCOMPLETE: RunStatus.FAILED,
            TaskEvaluationStatus.UNKNOWN: RunStatus.FAILED,
        }[native]
        if status is not expected:
            raise ValueError("finalization native evaluation contradicts run status")
        return
    if status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
        raise ValueError("finalization without native outcome requires failure or cancellation")

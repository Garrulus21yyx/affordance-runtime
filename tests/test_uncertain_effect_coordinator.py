from dataclasses import dataclass, replace

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RiskLevel,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


@dataclass
class TimeoutWorld:
    saved: bool = False


class TimeoutObserver:
    def __init__(self, world: TimeoutWorld) -> None:
        self.world = world
        self.sequence = 0

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        revision = f"saved:{self.world.saved}"
        snapshot_id = f"timeout-snapshot-{self.sequence}"
        model = DomAdapter().transduce(
            '<button id="save">Save</button>',
            environment_revision=revision,
            snapshot_id=snapshot_id,
            page_revision="timeout-page-v1",
            ttl_ms=60_000,
        )
        observation = Observation(
            revision,
            snapshot_id=snapshot_id,
            page_revision="timeout-page-v1",
            target_fingerprints={
                item.id: item.target_fingerprint for item in model.affordances
            },
            metadata={"saved": self.world.saved},
        )
        return BrowserSnapshot(observation, model)


@dataclass
class ApplyThenTimeoutExecutor:
    world: TimeoutWorld
    calls: int = 0
    backend: str = "dom"

    def execute(
        self,
        contract: ActionContract,
        observation: Observation,
    ) -> ExecutionReceipt:
        self.calls += 1
        self.world.saved = True
        return ExecutionReceipt(
            contract.id,
            self.backend,
            False,
            observation.environment_revision,
            "saved:True",
            1.0,
            evidence={"dispatched": True},
            error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
            message="transport timed out after dispatch",
        )


@dataclass
class TimeoutPlanner:
    calls: int = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        self.calls += 1
        if snapshot.observation.metadata["saved"] is True:
            return PlannerDecision(done=True, result={"saved": True})
        contract = ActionContract.from_affordance(
            snapshot.affordance_model.affordances[0],
            intent="Save exactly once",
            backend="dom",
            verifier_plan=[VerifierSpec("observation_metadata", "saved", True)],
            required_capabilities=["settings.write"],
        )
        return PlannerDecision(
            contract=replace(
                contract,
                risk=RiskLevel.MEDIUM,
                idempotency_key="save:exactly-once:v1",
                contract_hash="",
            )
        )


def test_timeout_after_dispatch_inspects_state_and_never_blindly_duplicates_effect() -> None:
    world = TimeoutWorld()
    observer = TimeoutObserver(world)
    executor = ApplyThenTimeoutExecutor(world)
    planner = TimeoutPlanner()

    result = RunCoordinator(observer, planner, executor).run_sync(
        TaskEnvelope(
            "uncertain-effect",
            "Save exactly once",
            capabilities=["settings.write"],
        )
    )

    assert result.status == RuntimeStep.DONE
    assert world.saved is True
    assert executor.calls == 1
    assert planner.calls == 2
    assert len(result.state.receipts) == 1
    assert result.verification is not None and result.verification.passed
    assert result.state.current_failure is not None
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == "inspect_post_state"
    assert result.state.recovery_receipts
    assert result.state.recovery_receipts[-1].command_id.startswith("recovery-command-")
    assert result.state.recovery_history
    assert ":inspect_post_state:" in result.state.recovery_history[-1].strategy_id
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryStateInspected" in events
    assert events.index("RecoveryStateInspected") < events.index("TaskCompleted")

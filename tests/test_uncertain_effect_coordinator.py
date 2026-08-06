from dataclasses import dataclass

from affordance_runtime.action_contract_builder import ActionContractMaterializer as ContractBuilder
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RiskLevel,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerDoneResponse,
    PlannerProposalResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression


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
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            metadata={
                "saved": self.world.saved,
                "criterion_evaluations": ({"criterion:saved": "satisfied"} if self.world.saved else {}),
            },
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
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        self.calls += 1
        if any(outcome.verification_status == "passed" for outcome in request.recent_outcomes):
            return PlannerDoneResponse(result={"saved": True})
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id="save-exactly-once",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="Save exactly once",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=request.observation.affordances[0].target_id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="uncertain-effect-test",
            ),
        )


def test_timeout_after_dispatch_inspects_state_and_never_blindly_duplicates_effect() -> None:
    world = TimeoutWorld()
    observer = TimeoutObserver(world)
    executor = ApplyThenTimeoutExecutor(world)
    planner = TimeoutPlanner()

    result = compose_run_coordinator(
        observer,
        executor,
        contract_builder=ContractBuilder(
            requirements={
                "dom_button_1": ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "observation_metadata",
                            "saved",
                            True,
                            criterion_ids=("criterion:saved",),
                        ),
                    ),
                    required_capabilities=("settings.write",),
                    risk=RiskLevel.MEDIUM,
                    idempotency_key="save:exactly-once:v1",
                )
            }
        ),
    ).run_sync(
        RunRequest(
            task_spec=TaskSpec(
                task_id="uncertain-effect",
                revision=1,
                objective="Save exactly once",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                requirements=canonical_effect_requirements(
                    ("Save",), OperationClass.REVERSIBLE_WRITE, "uncertain-effect-test", ("settings.write",)
                ),
                allowed_effect_refs=canonical_effect_requirement_refs(("Save",)),
                success=SuccessExpression(
                    expression_id="success:saved",
                    operator="criterion",
                    criterion_id="criterion:saved",
                    requirement_refs=("requirement:effect:1",),
                ),
                capability_ceiling=("settings.write",),
                source_request_ref="uncertain-effect-test",
            ),
            capabilities=["settings.write"],
        )
    )

    assert result.status == RuntimeStep.DONE
    assert world.saved is True
    assert executor.calls == 1
    assert planner.calls == 0
    assert result.state.step_count == 1
    assert result.verification is not None and result.verification.passed
    assert result.state.current_failure is not None
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == "inspect_post_state"
    recovery_outcomes = [
        node.payload["outcome"] for node in result.trace.nodes if node.kind == "RecoveryOutcomeRecorded"
    ]
    assert recovery_outcomes
    assert recovery_outcomes[-1]["success"]
    assert any(
        node.kind == "RecoveryStrategySelected" and node.payload["decision"]["kind"] == "inspect_post_state"
        for node in result.trace.nodes
    )
    events = [node.kind for node in result.trace.nodes]
    assert "RecoveryStateInspected" in events
    assert events.index("RecoveryStateInspected") < events.index("TaskCompleted")

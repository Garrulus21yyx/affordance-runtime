from dataclasses import dataclass

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.approval_contracts import ConfiguredApprovalProvider
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
from affordance_runtime.effect_authority_contracts import (
    EffectAuthorizationScope,
    EffectClass,
    Externality,
    ResourceScopeRef,
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
from affordance_runtime.runtime import RuntimeStep, legacy_run_request
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    canonical_effect_requirement_refs,
)
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer as ContractBuilder
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    EvidenceSourceKind,
    PredicateEvidence,
    SuccessExpression,
)


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
            '<button id="save" data-runtime-operation="resource.update@v1" '
            'data-runtime-effect-class="update" data-runtime-externality="external_system" '
            'data-runtime-reversibility="reversible" data-runtime-source-assurance="structural" '
            'data-runtime-risk="medium">Save</button>',
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
                "criterion_evaluations": (
                    {
                        "criterion:saved": {
                            "status": "satisfied",
                            "evidence_refs": [f"observation:{snapshot_id}:saved"],
                        }
                    }
                    if self.world.saved
                    else {}
                ),
            },
        )
        return BrowserSnapshot(
            observation,
            model,
            predicate_evidence=(
                (
                    PredicateEvidence(
                        evidence_ref=f"observation:{snapshot_id}:saved",
                        subject_ref="dom_button_1",
                        observed_value="satisfied",
                        source_kind=EvidenceSourceKind.DOM_STATE,
                        assurance=AssuranceLevel.STRUCTURAL,
                        observation_ref=snapshot_id,
                        effect_criterion_ids=("criterion:saved",),
                    ),
                )
                if self.world.saved
                else ()
            ),
        )


@dataclass
class ApplyThenTimeoutExecutor:
    supported_actions = ("activate", "click")
    provider_capabilities = ("settings.write",)
    adapter_capabilities = provider_capabilities
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
        approval_provider=ConfiguredApprovalProvider("test-user", {"settings.write"}),
    ).run_sync(
        legacy_run_request(
            task_spec=TaskSpec(
                task_id="uncertain-effect",
                revision=1,
                objective="Save exactly once",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                requirements=(
                    TaskRequirement(
                        requirement_id="requirement:effect:1",
                        payload=TaskSemanticPayload(
                            kind="effect",
                            subject="Save",
                            target_identity="dom_button_1",
                            operation_class=OperationClass.REVERSIBLE_WRITE,
                            capability="settings.write",
                            effect_authorization_scope=EffectAuthorizationScope(
                                requirement_ref="requirement:effect:1",
                                operation_constraint="resource.update@v1",
                                resource_scope=ResourceScopeRef("dom_button_1"),
                                effect_class=EffectClass.UPDATE,
                                externality=Externality.EXTERNAL_SYSTEM,
                                required_capabilities=frozenset({"settings.write"}),
                            ),
                        ),
                        source_anchor_refs=("uncertain-effect-test",),
                    ),
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

    assert result.status == RuntimeStep.ABORTED
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
    assert not recovery_outcomes[-1]["success"]
    assert any(
        node.kind == "RecoveryStrategySelected"
        and node.payload["decision"]["kind"] == "inspect_post_state"
        for node in result.trace.nodes
    )
    events = [node.kind for node in result.trace.nodes]
    assert events.index("ExecutionAttemptIssued") < events.index("FailureDetected")
    assert "UncertainExternalEffectRecorded" in events
    assert result.state.current_execution_attempt is not None
    assert result.state.uncertain_external_effects
    assert "RecoveryStateInspected" in events
    assert "TaskCompleted" not in events

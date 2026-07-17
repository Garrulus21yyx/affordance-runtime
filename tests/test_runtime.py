from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, VerifierSpec
from affordance_runtime.runtime import AffordanceRuntime, RuntimeStep, TaskEnvelope


class FakeExecutor:
    backend = "fake"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract_id=contract.id,
            backend=self.backend,
            success=True,
            started_revision=observation.environment_revision,
            ended_revision=observation.environment_revision,
            latency_ms=1.0,
            evidence={"saved": True},
        )


def test_runtime_executes_and_verifies_contract() -> None:
    observation = Observation(environment_revision="rev-1")
    contract = ActionContract(
        id="contract_1",
        intent="save",
        affordance_id="dom_button_1",
        action="click",
        backend="fake",
        environment_revision="rev-1",
        locator={"selector": "#save"},
        verifier_plan=[VerifierSpec(kind="evidence", target="saved", expected=True)],
    )

    result = AffordanceRuntime(FakeExecutor()).run_contract(
        TaskEnvelope(task_id="task_1", goal="save settings"),
        contract,
        observation,
    )

    assert result.status == RuntimeStep.DONE
    assert result.receipt is not None
    assert len(result.trace.nodes) == 4


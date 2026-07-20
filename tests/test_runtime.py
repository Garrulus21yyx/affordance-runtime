from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode, VerifierSpec
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


class FailingExecutor:
    backend = "fake"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract_id=contract.id,
            backend=self.backend,
            success=False,
            started_revision=observation.environment_revision,
            ended_revision=observation.environment_revision,
            latency_ms=1.0,
            error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
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


def test_runtime_uses_task_capabilities_without_mutating_shared_gate() -> None:
    observation = Observation(environment_revision="rev-1")
    contract = ActionContract(
        id="contract_1",
        intent="save",
        affordance_id="dom_button_1",
        action="click",
        backend="fake",
        environment_revision="rev-1",
        locator={"selector": "#save"},
        required_capabilities=["settings.write"],
    )
    runtime = AffordanceRuntime(FakeExecutor())

    result = runtime.run_contract(
        TaskEnvelope(task_id="task_1", goal="save settings", capabilities=["settings.write"]),
        contract,
        observation,
    )

    assert result.status == RuntimeStep.DONE
    assert runtime.gate.granted_capabilities == set()


def test_runtime_preserves_executor_error_code() -> None:
    observation = Observation(environment_revision="rev-1")
    contract = ActionContract(
        id="contract_1",
        intent="save",
        affordance_id="dom_button_1",
        action="click",
        backend="fake",
        environment_revision="rev-1",
        locator={"selector": "#save"},
    )

    result = AffordanceRuntime(FailingExecutor()).run_contract(
        TaskEnvelope(task_id="task_1", goal="save settings"),
        contract,
        observation,
    )

    assert result.status == RuntimeStep.FAILED
    assert result.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT


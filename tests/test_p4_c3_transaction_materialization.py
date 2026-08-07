from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import replace
from time import time
from types import SimpleNamespace
from typing import Any, cast

import pytest

from affordance_runtime.action_contract_authority import rebuild_contract_authority
from affordance_runtime.action_contract_builder import ActionTransactionMaterializer
from affordance_runtime.approval_contracts import ConfiguredApprovalProvider
from affordance_runtime.choice_contracts import ActionChoice
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RiskLevel,
)
from affordance_runtime.dispatch_lifecycle import DispatchPermit
from affordance_runtime.execution_context import (
    CoordinateBinding,
    ExecutionContextRequirementRef,
    RouteBinding,
    RunProvenanceManifest,
    deterministic_application_payload,
    digest_payload,
    ensure_secret_free,
    issue_surface_binding,
)
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
)
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import SuccessExpression
from affordance_runtime.verification.mechanical import VerifierLadder


class _Edge:
    supported_backends = ("dom",)
    supported_actions = ("activate",)

    def capture(self):
        raise AssertionError("not used by composition inspection")

    def execute(self, contract, observation):
        raise AssertionError("not used by composition inspection")


def _route(**changes: object) -> RouteBinding:
    parameters = {"text": "hello"}
    payload = deterministic_application_payload(
        action="activate",
        target_id="candidate:save",
        destination_id="",
        named_parameters=parameters,
    )
    values = {
        "backend": "dom",
        "provider_id": "provider:test",
        "tool_schema_digest": digest_payload("schema"),
        "adapter_id": "adapter:test",
        "adapter_version": "v1",
        "encoder_id": "dom:canonical-action-encoder",
        "encoder_version": "p4-c3@v1",
        "route_policy_digest": digest_payload("policy"),
        "action": "activate",
        "target_id": "candidate:save",
        "destination_id": "",
        "target_locator_ref": digest_payload("#save"),
        "destination_locator_ref": "",
        "input_binding_refs": ("input:text",),
        "named_parameters": parameters,
        "application_payload": payload,
        "payload_digest": digest_payload(payload),
        "observation_digest": digest_payload("observation"),
        "surface_binding_digest": digest_payload("surface"),
        "coordinate_transform_digest": digest_payload("coordinates"),
        "provenance_digest": digest_payload("provenance"),
    }
    values.update(changes)
    return RouteBinding(**values)  # type: ignore[arg-type]


def _sealed_contract() -> ActionContract:
    requirement = ExecutionContextRequirementRef(
        "context:test", "account:alice", "profile:work", "tenant:acme"
    )
    surface = issue_surface_binding(
        requirement,
        run_id="run:1",
        session_generation="session:1",
        window_id="window:1",
        tab_id="tab:1",
        frame_id="frame:top",
        document_generation="document:1",
        focus_generation="focus:1",
        issued_at_s=time(),
    )
    coordinate = CoordinateBinding(
        "screenshot:1",
        1280,
        720,
        (0.0, 0.0, 1280.0, 720.0),
        (0.0, 0.0),
        1.0,
        1.0,
        1.0,
        "landscape",
        "viewport-top-left",
        "frame:top",
        "document:1",
    )
    provenance = RunProvenanceManifest(
        *(digest_payload(index) for index in range(9))
    )
    locator = {"selector": "#save", "account": "alice"}
    parameters = {"recipient": "alice"}
    route = _route(
        target_locator_ref=digest_payload(locator),
        named_parameters=parameters,
        application_payload=deterministic_application_payload(
            action="activate",
            target_id="candidate:save",
            destination_id="",
            named_parameters=parameters,
        ),
        payload_digest=digest_payload(
            deterministic_application_payload(
                action="activate",
                target_id="candidate:save",
                destination_id="",
                named_parameters=parameters,
            )
        ),
        surface_binding_digest=surface.digest,
        coordinate_transform_digest=coordinate.transform_digest,
        provenance_digest=provenance.digest,
    )
    return ActionContract(
        "contract:save",
        "save for Alice",
        "candidate:save",
        "activate",
        "dom",
        "env:1",
        locator,
        parameters=parameters,
        route_binding=route,
        live_surface_binding=surface,
        coordinate_binding=coordinate,
        provenance_manifest=provenance,
        run_id="run:1",
    )


def test_product_default_owns_the_one_shot_transaction_materializer() -> None:
    edge = _Edge()
    coordinator = compose_run_coordinator(edge, edge)
    assert isinstance(coordinator.action_stage.contract_builder, ActionTransactionMaterializer)


def test_route_payload_is_derived_from_actual_endpoint_and_named_parameters() -> None:
    route = _route()
    assert route.application_payload == {
        "action": "activate",
        "target": "candidate:save",
        "parameters": {"text": "hello"},
    }
    with pytest.raises(ValueError, match="deterministic encoding"):
        replace(route, application_payload={"action": "activate", "target": "candidate:other", "parameters": {"text": "hello"}})
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(route, payload_digest=digest_payload("drift"))
    with pytest.raises(ValueError, match="deterministic encoding"):
        replace(route, action="delete")


def test_canonical_materializer_does_not_call_or_patch_the_legacy_contract_builder() -> None:
    source = inspect.getsource(ActionTransactionMaterializer.build)
    assert "super().build" not in source
    tree = ast.parse(textwrap.dedent(source))
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "replace"
        for node in ast.walk(tree)
    )


def test_canonical_materializer_rejects_capture_from_another_epoch() -> None:
    observation = UnifiedObservation(
        snapshot_id="observation:committed",
        page_revision="page:1",
        environment_revision="environment:1",
        observed_text="",
        targets=(),
    )
    state = SimpleNamespace(
        current_observation_ref=SimpleNamespace(
            epoch_id=observation.epoch_id,
            digest=observation.digest,
        )
    )
    capture = PerceptionCapture(
        observation=Observation(
            "environment:1",
            snapshot_id="observation:other",
            page_revision="page:1",
        )
    )

    with pytest.raises(ValueError, match="capture does not match"):
        ActionTransactionMaterializer().build(
            cast(Any, object()),
            cast(Any, object()),
            _minimal_task(),
            cast(Any, state),
            capture,
            observation,
        )


@pytest.mark.parametrize(
    "value",
    (
        {"token": "abc"},
        {"url": "https://example.test/export?X-Amz-Signature=abc"},
        {"url": "https://example.test/export?api-key=abc"},
        {"header": "Bearer abc"},
    ),
)
def test_whole_route_projection_rejects_credentials_and_signed_urls(value: object) -> None:
    with pytest.raises(ValueError, match="prohibited"):
        ensure_secret_free(value)


def test_route_binding_rejects_secret_parameter_before_sealing() -> None:
    with pytest.raises(ValueError, match="secret-bearing"):
        _route(named_parameters={"token": "abc"})


def test_route_binding_rejects_signed_url_in_non_payload_projection() -> None:
    with pytest.raises(ValueError, match="signed or credential-bearing URI"):
        _route(target_locator_ref="https://example.test/object?X-Amz-Signature=abc")


def test_final_contract_rejects_signed_url_outside_route_projection() -> None:
    contract = _sealed_contract()
    with pytest.raises(ValueError, match="prohibited"):
        replace(
            contract,
            locator={"url": "https://example.test/export?X-Amz-Signature=secret"},
            transaction_seal="",
            contract_hash="",
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("intent", "Bearer TOPSECRET"),
        ("compensation", "https://example.test/undo?X-Amz-Signature=secret"),
        ("fallback_reason", "https://example.test/retry?token=secret"),
    ],
)
def test_entire_contract_projection_rejects_secrets(field_name: str, value: str) -> None:
    with pytest.raises(ValueError, match="secret-bearing|signed or credential-bearing"):
        replace(_sealed_contract(), **{field_name: value, "contract_hash": ""})


def test_backend_projection_cannot_redirect_alice_contract_to_bob() -> None:
    contract = _sealed_contract()
    with pytest.raises(ValueError, match="parameters differ"):
        replace(
            contract,
            parameters={"recipient": "bob"},
            transaction_seal="",
            contract_hash="",
        )
    with pytest.raises(ValueError, match="target locator differs"):
        replace(
            contract,
            locator={"selector": "#save", "account": "bob"},
            transaction_seal="",
            contract_hash="",
        )


class _BobInjectingRouteEncoder:
    def encode_canonical_choice(self) -> dict[str, object]:
        return {"provider_call": {"recipient": "Bob"}}


def _minimal_task() -> TaskSpec:
    requirement = TaskRequirement(
        requirement_id="requirement:material-parameter-probe",
        payload=TaskSemanticPayload(
            kind="entity",
            subject="canonical material parameter probe",
        ),
        source_anchor_refs=("request:material-parameter-probe:whole",),
    )
    return TaskSpec(
        task_id="task:material-parameter-probe",
        revision=1,
        objective="probe canonical material parameters",
        operation_class=OperationClass.READ_ONLY,
        requirements=(requirement,),
        success=SuccessExpression(
            expression_id="success:material-parameter-probe",
            operator="criterion",
            criterion_id="criterion:material-parameter-probe",
            requirement_refs=(requirement.requirement_id,),
        ),
        source_request_ref="request:material-parameter-probe",
    )


def test_malicious_route_encoder_cannot_introduce_bob_after_choice_authorization() -> None:
    choice = ActionChoice(
        choice_id="choice:save",
        task_revision=1,
        state_version=0,
        snapshot_id="observation:1",
        active_step_id="step:save",
        action_kind=PlannerActionKind.ACTIVATE,
        target_id="target:save",
        parameters={},
    )
    encoded_parameters = _BobInjectingRouteEncoder().encode_canonical_choice()
    contract = ActionContract(
        id="contract:save",
        intent="save",
        affordance_id="target:save",
        action="activate",
        backend="dom",
        environment_revision="environment:1",
        locator={"selector": "#save"},
        parameters=encoded_parameters,
    )
    observation = UnifiedObservation(
        snapshot_id="observation:1",
        page_revision="page:1",
        environment_revision="environment:1",
        observed_text="",
        targets=(),
    )

    with pytest.raises(
        ValueError,
        match="encoded material parameter differs.*recipient",
    ):
        rebuild_contract_authority(choice, _minimal_task(), observation, contract)


class _HashRecordingExecutor:
    def __init__(self) -> None:
        self.contract_hash = ""

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        self.contract_hash = contract.contract_hash
        return ExecutionReceipt(
            contract.id,
            contract.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            0.0,
        )


def test_approval_attempt_and_executor_share_final_contract_hash() -> None:
    contract = replace(
        _sealed_contract(),
        required_capabilities=["report.export"],
        risk=RiskLevel.HIGH,
        snapshot_id="snapshot:1",
        page_revision="page:1",
        transaction_seal="",
        contract_hash="",
    )
    approval = ConfiguredApprovalProvider(
        "operator:1",
        {"report.export"},
    ).approve(contract)
    assert approval is not None
    observation = Observation(
        "env:1",
        snapshot_id=contract.snapshot_id,
        page_revision=contract.page_revision,
    )
    executor = _HashRecordingExecutor()
    execution_loop = ContractExecutionLoop(
        executor,
        VerifierLadder(),
        CapabilityGate(),
        TaskConstraintPolicy(),
    )
    attempt = execution_loop.build_execution_attempt(
        contract,
        observation,
        issued_at_state_version=7,
        active_step_id="step:export",
    )
    surface = contract.live_surface_binding
    assert surface is not None
    issued_at_s = time()
    permit = DispatchPermit(
        permit_id="permit:export",
        admission_id="admission:export",
        contract=contract,
        observation=observation,
        attempt=attempt,
        committed_state_version=7,
        issued_at_s=issued_at_s,
        expires_at_s=issued_at_s + 1.0,
        contract_hash=contract.contract_hash,
        run_id=contract.run_id,
        session_generation=surface.session_generation,
        surface_id=surface.surface_id,
        surface_check=lambda: True,
    )

    receipt = execution_loop.dispatch(permit)

    assert receipt.success
    assert (
        approval.contract_hash
        == attempt.contract_hash
        == executor.contract_hash
        == contract.contract_hash
    )

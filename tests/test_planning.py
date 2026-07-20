import time

import pytest
from pydantic import ValidationError

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation, RiskLevel, VerifierSpec
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    ProposalRejected,
    ProposalRejectionCode,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


def _fixture() -> tuple[TaskSpec, StateKernel, BrowserSnapshot]:
    model = DomAdapter().transduce(
        '<input id="theme" aria-label="Theme">',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Set theme")
    state.remember_observation(observation)
    spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Set theme to dark",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme is dark",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-1",
        created_at_s=time.time(),
    )
    return spec, state, BrowserSnapshot(observation, model)


def _proposal(state: StateKernel, **changes: object) -> PlannerProposal:
    values = {
        "proposal_id": "proposal-1",
        "based_on_task_revision": 2,
        "based_on_state_version": state.version,
        "snapshot_id": "snapshot-1",
        "subgoal": "Set theme to dark",
        "action_kind": PlannerActionKind.TYPE_TEXT,
        "target_affordance_id": "dom_input_1",
        "parameters": {"text": "dark"},
        "expected_effects": ("theme is dark",),
        "evidence_requirements": ("saved theme evidence",),
    }
    values.update(changes)
    return PlannerProposal(**values)


def test_contract_builder_binds_current_target_authority_and_verifier() -> None:
    spec, state, snapshot = _fixture()
    builder = ContractBuilder(
        requirements={
            "dom_input_1": ContractRequirements(
                verifier_plan=(VerifierSpec("evidence", "saved_theme", "dark"),),
                compensation="restore previous theme",
            )
        }
    )

    contract = builder.build(_proposal(state), spec, state, snapshot)

    assert contract.locator == {"selector": "#theme", "strategy": "css"}
    assert contract.backend == "dom"
    assert contract.parameters == {"value": "dark"}
    assert contract.required_capabilities == ["settings.write"]
    assert contract.risk == RiskLevel.MEDIUM
    assert contract.verifier_plan == [VerifierSpec("evidence", "saved_theme", "dark")]
    assert contract.compensation == "restore previous theme"
    assert contract.idempotency_key


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"based_on_task_revision": 1}, ProposalRejectionCode.STALE_TASK_REVISION),
        ({"based_on_state_version": 99}, ProposalRejectionCode.STALE_STATE_VERSION),
        ({"snapshot_id": "old"}, ProposalRejectionCode.STALE_SNAPSHOT),
        ({"target_affordance_id": "missing"}, ProposalRejectionCode.MISSING_TARGET),
        ({"action_kind": PlannerActionKind.ACTIVATE, "parameters": {}}, ProposalRejectionCode.UNSUPPORTED_ACTION),
    ],
)
def test_contract_builder_rejects_stale_missing_or_incompatible_proposal(
    changes: dict[str, object],
    code: ProposalRejectionCode,
) -> None:
    spec, state, snapshot = _fixture()
    with pytest.raises(ProposalRejected) as caught:
        ContractBuilder().build(_proposal(state, **changes), spec, state, snapshot)
    assert caught.value.code == code


def test_proposal_schema_rejects_surface_and_authority_fields() -> None:
    _, state, _ = _fixture()
    with pytest.raises(ValidationError, match="surface or authority"):
        _proposal(state, parameters={"text": "dark", "selector": "#theme"})
    with pytest.raises(ValidationError, match="surface or authority"):
        _proposal(state, parameters={"text": "dark", "capability": "settings.write"})
    with pytest.raises(ValidationError, match="unsupported semantic parameters"):
        _proposal(state, parameters={"text": "dark", "wait_for_seconds": 3})
    with pytest.raises(ValidationError, match="at least 1 character"):
        _proposal(state, snapshot_id="")


def test_finish_and_ask_flags_are_deterministically_derived_from_action_kind() -> None:
    _, state, _ = _fixture()
    finish = _proposal(
        state,
        action_kind=PlannerActionKind.FINISH,
        target_affordance_id="",
        parameters={},
        done=False,
    )
    ask = _proposal(
        state,
        action_kind=PlannerActionKind.ASK_USER,
        target_affordance_id="",
        parameters={},
        requires_clarification=False,
    )

    assert finish.done is True
    assert ask.requires_clarification is True

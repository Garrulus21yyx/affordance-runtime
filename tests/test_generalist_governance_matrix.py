from __future__ import annotations

from dataclasses import dataclass

import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.planning import (
    ContractBuilder,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
    PlannerProposalValidator,
    ProposalRejectionCode,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec

MARKUP = (
    "<main>"
    "<button>Save profile</button>"
    "<button>Save invoice</button>"
    "<button>Delete profile</button>"
    "<button>Submit</button>"
    "<label>Name<input></label>"
    "<label>Email<input></label>"
    "<button>Weather</button>"
    "<button>Open admin</button>"
    "<button>Enable notifications</button>"
    "</main>"
)
MODEL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.MODEL,
    producer_id="adversarial-governance-fixture",
    profile_id="strict-generalist",
    version="governance-matrix-v1",
)


@dataclass
class GovernanceObserver:
    captures: int = 0

    def capture(self) -> BrowserSnapshot:
        self.captures += 1
        snapshot_id = f"governance-snapshot-{self.captures}"
        model = DomAdapter().transduce(
            MARKUP,
            environment_revision="governance-rev",
            snapshot_id=snapshot_id,
            page_revision="governance-page",
        )
        observation = Observation(
            "governance-rev",
            snapshot_id=snapshot_id,
            page_revision="governance-page",
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        )
        return BrowserSnapshot(observation, model)


@dataclass
class AdversarialSemanticPlanner:
    target_label: str = ""
    ask_user: bool = False

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        if self.ask_user:
            proposal = PlannerProposal(
                proposal_id="matrix-clarification",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                action_kind=PlannerActionKind.ASK_USER,
                reason="current task scope is ambiguous",
            )
        else:
            target = next(item for item in snapshot.affordance_model.affordances if item.label == self.target_label)
            action_kind = (
                PlannerActionKind.TYPE_TEXT
                if target.action in {"fill", "type", "type_text"}
                else PlannerActionKind.ACTIVATE
            )
            proposal = PlannerProposal(
                proposal_id=f"matrix-{target.id}",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal=f"act on {self.target_label}",
                action_kind=action_kind,
                target_affordance_id=target.id,
                parameters={"text": "unrequested"} if action_kind == PlannerActionKind.TYPE_TEXT else {},
            )
        return PlannerDecision(
            proposal=proposal,
            proposal_provenance=MODEL_PROVENANCE,
        )


@dataclass
class CountingExecutor:
    calls: int = 0

    def execute(self, contract, observation) -> ExecutionReceipt:  # type: ignore[no-untyped-def]
        self.calls += 1
        return ExecutionReceipt(
            contract.id,
            "governance-fixture",
            True,
            observation.environment_revision,
            observation.environment_revision,
            0.0,
        )


def _task(objective: str, targets: tuple[str, ...]) -> TaskSpec:
    return TaskSpec(
        task_id="governance-matrix",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=targets,
        success_criteria=("only the requested effect occurs",),
        evidence_requirements=("post-action state",),
        source_request_ref="governance-matrix",
    )


@pytest.mark.parametrize(
    ("case", "objective", "targets", "target_label", "rejection"),
    [
        (
            "distractor",
            "Save the profile changes",
            ("profile",),
            "Save invoice",
            ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
        ),
        (
            "extra_control",
            "Update Name",
            ("Name",),
            "Email",
            ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
        ),
        (
            "unrelated_interface",
            "Review the profile details",
            ("profile",),
            "Weather",
            ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
        ),
        (
            "unrequested_terminal",
            "Enter Q1 into Name",
            ("Name",),
            "Submit",
            ProposalRejectionCode.UNREQUESTED_EFFECT,
        ),
        (
            "scope_expansion",
            "Open the profile",
            ("profile",),
            "Open admin",
            ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
        ),
        (
            "unrequested_destructive_effect",
            "Review the profile",
            ("profile",),
            "Delete profile",
            ProposalRejectionCode.UNREQUESTED_EFFECT,
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_negative_behavior_matrix_stops_before_contract_or_effect(
    case: str,
    objective: str,
    targets: tuple[str, ...],
    target_label: str,
    rejection: ProposalRejectionCode,
) -> None:
    del case
    executor = CountingExecutor()
    result = RunCoordinator(
        GovernanceObserver(),
        AdversarialSemanticPlanner(target_label),
        executor,
        contract_builder=ContractBuilder(),
    ).run_sync(TaskEnvelope(task_spec=_task(objective, targets)))

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
    rejected = next(node for node in result.trace.nodes if node.kind == "PlannerProposalRejected")
    assert rejected.payload["rejection_code"] == rejection.value
    assert executor.calls == 0
    assert result.state.receipts == []
    assert "ContractBuilt" not in [node.kind for node in result.trace.nodes]


def test_ambiguity_control_requests_clarification_without_effect() -> None:
    executor = CountingExecutor()
    result = RunCoordinator(
        GovernanceObserver(),
        AdversarialSemanticPlanner(ask_user=True),
        executor,
        contract_builder=ContractBuilder(),
    ).run_sync(TaskEnvelope(task_spec=_task("Update the profile", ("profile",))))

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert executor.calls == 0
    validated = next(node for node in result.trace.nodes if node.kind == "PlannerProposalValidated")
    assert validated.payload["source"] == "model"


def test_paraphrase_control_authorizes_the_same_semantic_target() -> None:
    snapshot = GovernanceObserver().capture()
    task = _task("Turn notifications on", ("notifications",))
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(snapshot.observation)
    target = next(item for item in snapshot.affordance_model.affordances if item.label == "Enable notifications")
    proposal = PlannerProposal(
        proposal_id="matrix-paraphrase",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=target.id,
    )

    PlannerProposalValidator().validate(proposal, MODEL_PROVENANCE, task, state, snapshot)

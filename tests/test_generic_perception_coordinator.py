from pathlib import Path
from typing import Any

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.coordinator import RunBudget
from affordance_runtime.executors import ExecutorRouter, VisualExecutor
from affordance_runtime.grounding import EvidenceKind, GroundingSource, PerceptionRequirements
from affordance_runtime.perception import GenericPerceptionOrchestrator
from affordance_runtime.planning import (
    ContractBuilder,
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
from affordance_runtime.route_calibration import RouteOutcomeStatus
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.visual_grounding import VisualRegion

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="generic-perception-test-planner",
)


class CanvasPage:
    url = "http://fixture/canvas"

    def __init__(self) -> None:
        self.activated = False

    def content(self) -> str:
        status = "activated" if self.activated else "pending"
        return f"<main><canvas></canvas><p>{status}</p></main>"

    def evaluate(self, expression: str, arg: Any = None) -> object:
        del arg
        if "querySelectorAll('[bid]')" in expression:
            return {}
        if "document.activeElement" in expression:
            return ""
        if "document.body?.innerText" in expression:
            return "activated" if self.activated else "pending"
        if "document.querySelectorAll('svg')" in expression:
            return {"viewport": [800, 600], "elements": []}
        if "innerWidth" in expression:
            return [800, 600]
        return {}

    def screenshot(self, **kwargs: Any) -> bytes:
        payload = b"canvas-after" if self.activated else b"canvas-before"
        path = kwargs.get("path")
        if path:
            Path(path).write_bytes(payload)
        return payload


class RecordingRegionProposer:
    provider = "fixture"
    model = "deterministic-regions"
    prompt_version = "test-v1"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def propose(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        return [VisualRegion((0.4, 0.4, 0.2, 0.2), "Blue canvas control", 0.95)]


class RecordingBrowserSession(BrowserSession):
    def __init__(self, page: CanvasPage, proposer: RecordingRegionProposer) -> None:
        super().__init__(
            page,
            perception_orchestrator=GenericPerceptionOrchestrator(proposer),
        )
        self.capture_arguments: list[dict[str, object]] = []
        self.snapshots: list[BrowserSnapshot] = []

    def capture(self, **kwargs: Any) -> BrowserSnapshot:
        self.capture_arguments.append(dict(kwargs))
        snapshot = super().capture(**kwargs)
        self.snapshots.append(snapshot)
        return snapshot


class VisualSemanticPlanner:
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if any(
            outcome.verification_status == "passed"
            for outcome in request.recent_outcomes
        ):
            return PlannerDoneResponse(result={"activated": True})
        target = next(
            item
            for item in request.observation.affordances
            if "point_activate" in item.supported_actions
        )
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=PlannerProposal(
                proposal_id=f"activate-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                action_kind=PlannerActionKind.POINT_ACTIVATE,
                target_affordance_id=target.target_id,
            ),
        )


class VerifiedVisualContractBuilder:
    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ):
        requirements = ContractRequirements(
            verifier_plan=(
                VerifierSpec(
                    "dom_contains",
                    "page",
                    "activated",
                    progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                ),
            )
        )
        return ContractBuilder(requirements={proposal.target_affordance_id: requirements}).build(
            proposal, task_spec, state, snapshot
        )


class CanvasPointer:
    def __init__(self, page: CanvasPage) -> None:
        self.page = page
        self.clicks: list[tuple[int, int]] = []

    def click_xy(self, x: int, y: int) -> None:
        self.clicks.append((x, y))
        self.page.activated = True

    def type_text(self, text: str) -> None:
        raise AssertionError(f"unexpected text input: {text}")


def test_coordinator_runs_task_derived_visual_primary_path_without_benchmark_adapter(
    tmp_path: Path,
) -> None:
    page = CanvasPage()
    proposer = RecordingRegionProposer()
    observer = RecordingBrowserSession(page, proposer)
    pointer = CanvasPointer(page)
    task = TaskSpec(
        task_id="generic-visual-run",
        revision=1,
        objective="Activate the blue visual canvas control",
        operation_class=OperationClass.READ_ONLY,
        targets=("blue canvas control",),
        success_criteria=("the page reports activated",),
        evidence_requirements=("visual appearance and post-action page state",),
        source_request_ref="test-request",
    )

    coordinator = compose_run_coordinator(
        observer=observer,
        planner=VisualSemanticPlanner(),
        executor=VisualExecutor(pointer),
        contract_builder=VerifiedVisualContractBuilder(),  # type: ignore[arg-type]
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        task_planner=None,
    )
    result = coordinator.run_sync(RunRequest(task_spec=task))

    assert result.status == RuntimeStep.DONE, [(node.kind, node.payload) for node in result.trace.nodes]
    assert result.result == {"activated": True}
    assert pointer.clicks == [(400, 300)]
    assert len(proposer.requests) >= 2
    assert all(request.instruction == "Activate the blue visual canvas control" for request in proposer.requests)
    assert all(
        isinstance(arguments["perception_requirements"], PerceptionRequirements)
        and EvidenceKind.VISUAL_APPEARANCE in arguments["perception_requirements"].required_properties
        for arguments in observer.capture_arguments
    )
    assert all(
        {source.observation_epoch_id for source in snapshot.source_observations} == {snapshot.observation.snapshot_id}
        for snapshot in observer.snapshots
    )
    assert all(
        any(candidate.source == GroundingSource.VISUAL for candidate in snapshot.grounding_candidates)
        for snapshot in observer.snapshots
    )
    assert "ContractBuilt" in [node.kind for node in result.trace.nodes]
    assert "PostActionEvaluated" in [node.kind for node in result.trace.nodes]
    outcomes = [node for node in result.trace.nodes if node.kind == "RouteOutcomeRecorded"]
    assert len(outcomes) == 1
    assert outcomes[0].payload["status"] == RouteOutcomeStatus.VERIFIED_SUCCESS.value
    assert outcomes[0].payload["trainable"] is True
    assert outcomes[0].payload["evidence_ids"]
    assert len(coordinator.progress_stage.route_calibrator.outcomes) == 1


class DomFallbackPage(CanvasPage):
    url = "http://fixture/settings"

    def content(self) -> str:
        status = "saved" if self.activated else "pending"
        return f"<main><button bid='save'>Save changes</button><p>{status}</p></main>"

    def evaluate(self, expression: str, arg: Any = None) -> object:
        del arg
        if "querySelectorAll('[bid]')" in expression:
            return {
                "save": {
                    "value": "",
                    "selected_options": [],
                    "checked": None,
                    "visible": True,
                }
            }
        if "document.activeElement" in expression:
            return ""
        if "document.body?.innerText" in expression:
            return "Save changes\nsaved" if self.activated else "Save changes\npending"
        if "document.querySelectorAll('svg')" in expression:
            return {"viewport": [800, 600], "elements": []}
        if "innerWidth" in expression:
            return [800, 600]
        return {}


class SaveRegionProposer(RecordingRegionProposer):
    def propose(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        return [VisualRegion((0.4, 0.4, 0.2, 0.2), "Save changes", 0.95)]


class ActivateSemanticPlanner:
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if any(
            outcome.verification_status == "passed"
            for outcome in request.recent_outcomes
        ):
            return PlannerDoneResponse(result={"saved": True})
        target = next(
            item
            for item in request.observation.affordances
            if "activate" in item.supported_actions
        )
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=PlannerProposal(
                proposal_id=f"save-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=target.target_id,
            ),
        )


class FailBeforeDispatchDomExecutor:
    backend = "dom"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, contract: object, observation: Observation) -> ExecutionReceipt:
        self.calls += 1
        return ExecutionReceipt(
            str(getattr(contract, "id")),
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": False},
            error_code=RuntimeErrorCode.EXECUTION_FAILED,
            message="structured grounding failed before dispatch",
        )


class VerifiedSaveContractBuilder:
    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ):
        requirements = ContractRequirements(
            verifier_plan=(
                VerifierSpec(
                    "dom_contains",
                    "page",
                    "saved",
                    progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                ),
            ),
            idempotency_key="generic-settings-save-v1",
        )
        return ContractBuilder(requirements={proposal.target_affordance_id: requirements}).build(
            proposal, task_spec, state, snapshot
        )


def test_dom_failure_widens_generic_perception_and_uses_fresh_visual_route(
    tmp_path: Path,
) -> None:
    page = DomFallbackPage()
    proposer = SaveRegionProposer()
    observer = RecordingBrowserSession(page, proposer)
    pointer = CanvasPointer(page)
    dom = FailBeforeDispatchDomExecutor()
    executors = ExecutorRouter()
    executors.register(dom)
    executors.register(VisualExecutor(pointer))
    task = TaskSpec(
        task_id="generic-dom-visual-fallback",
        revision=1,
        objective="Save changes",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Save changes",),
        success_criteria=("the page reports saved",),
        evidence_requirements=("current page state",),
        requested_capabilities=("settings.write",),
        source_request_ref="test-request",
    )

    result = compose_run_coordinator(
        observer=observer,
        planner=ActivateSemanticPlanner(),
        executor=executors,
        contract_builder=VerifiedSaveContractBuilder(),  # type: ignore[arg-type]
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        task_planner=None,
    ).run_sync(RunRequest(task_spec=task, capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE, [(node.kind, node.payload) for node in result.trace.nodes]
    assert result.result == {"saved": True}
    assert dom.calls == 1
    assert pointer.clicks == [(400, 300)]
    assert proposer.requests
    route_sources = [node.payload["source"] for node in result.trace.nodes if node.kind == "RouteSelected"]
    assert route_sources == ["dom", "visual"]
    widened = [
        snapshot.perception_requirements
        for snapshot in observer.snapshots
        if snapshot.perception_requirements is not None
        and EvidenceKind.VISUAL_APPEARANCE in snapshot.perception_requirements.required_properties
    ]
    assert widened
    assert all(
        candidate.observation_epoch_id == snapshot.observation.snapshot_id
        for snapshot in observer.snapshots
        for candidate in snapshot.grounding_candidates
    )


def test_source_conflict_uses_bounded_targeted_epoch_then_returns_inconclusive(
    tmp_path: Path,
) -> None:
    class ConflictPage(CanvasPage):
        def content(self) -> str:
            return "<main><svg><circle id='target'/></svg></main>"

        def evaluate(self, expression: str, arg: Any = None) -> object:
            del arg
            if "getScreenCTM" in expression:
                return {
                    "viewport": [800, 600],
                    "elements": [
                        {
                            "element_id": "target",
                            "tag": "circle",
                            "label": "Target",
                            "role": "button",
                            "action": "point_activate",
                            "bid": "",
                            "view_box": [0, 0, 100, 100],
                            "geometry_bbox": [10, 10, 10, 10],
                            "viewport_bbox": [100, 100, 20, 20],
                            "transform": [2, 0, 0, 2, 80, 80],
                        }
                    ],
                }
            if "innerWidth" in expression:
                return [800, 600]
            if "document.activeElement" in expression or "innerText" in expression:
                return ""
            return {}

    class ConflictingProposer(RecordingRegionProposer):
        def propose(self, request):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            return [VisualRegion((0.6, 0.6, 0.1, 0.1), "Target", 0.9)]

    class InconclusivePlanner:
            def propose(
                self,
                request: PlanningRequest,
            ) -> PlannerDoneResponse:
                assert request.observation.affordances
                return PlannerDoneResponse(
                result={"status": "inconclusive", "reason": "source conflict"},
            )

    proposer = ConflictingProposer()
    page = ConflictPage()
    observer = RecordingBrowserSession(page, proposer)
    task = TaskSpec(
        task_id="generic-source-conflict",
        revision=1,
        objective="Activate the visual point target",
        operation_class=OperationClass.READ_ONLY,
        targets=("Target",),
        success_criteria=("the current target is activated",),
        evidence_requirements=("visual appearance and spatial position",),
        source_request_ref="test-request",
    )

    result = compose_run_coordinator(
        observer=observer,
        planner=InconclusivePlanner(),
        executor=VisualExecutor(CanvasPointer(page)),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        budget=RunBudget(max_active_perception_observations=1),
        task_planner=None,
    ).run_sync(RunRequest(task_spec=task))

    assert result.status == RuntimeStep.DONE
    assert result.result["status"] == "inconclusive"
    events = [node.kind for node in result.trace.nodes]
    assert events.count("TargetedPerceptionCaptured") == 1
    assert "TargetedPerceptionBudgetExhausted" in events
    assert "EvidenceGapDetected" in events
    assert "ActivePerceptionPlanned" in events
    assert "ProbeCompleted" in events
    assert "EvidenceGapUnresolved" in events
    assert "ActionStarted" not in events
    assert all(
        {source.observation_epoch_id for source in snapshot.source_observations}
        == {snapshot.observation.snapshot_id}
        for snapshot in observer.snapshots
    )

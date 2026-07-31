from dataclasses import dataclass, replace

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    Affordance,
    AffordanceLease,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    RuntimeErrorCode,
    Surface,
    VerifierSpec,
)
from affordance_runtime.executors import ExecutorRouter, VisualExecutor
from affordance_runtime.grounding import GroundingCandidate, GroundingSource, SourceObservation
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
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="unified-fallback-test-planner",
)


@dataclass
class FallbackWorld:
    saved: bool = False
    visual_clicks: int = 0


class FallbackPointer:
    def __init__(self, world: FallbackWorld) -> None:
        self.world = world

    def click_xy(self, x: int, y: int) -> None:
        assert (x, y) == (120, 90)
        self.world.visual_clicks += 1
        self.world.saved = True

    def type_text(self, text: str) -> None:
        raise AssertionError(f"unexpected text input: {text}")


@dataclass
class FailBeforeDispatchDomExecutor:
    calls: int = 0
    backend: str = "dom"

    def execute(self, contract: object, observation: Observation) -> ExecutionReceipt:
        self.calls += 1
        contract_id = str(getattr(contract, "id"))
        return ExecutionReceipt(
            contract_id,
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": False},
            error_code=RuntimeErrorCode.EXECUTION_FAILED,
            message="deterministic DOM locator dispatch failure",
        )


class CrossSurfaceObserver:
    def __init__(self, world: FallbackWorld) -> None:
        self.world = world
        self.sequence = 0
        probe = self._snapshot(0)
        self.semantic_target_id = probe.unified_affordances[0].semantic_target_id

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        return self._snapshot(self.sequence)

    def _snapshot(self, sequence: int) -> BrowserSnapshot:
        snapshot_id = f"snapshot-{sequence}"
        model = DomAdapter().transduce(
            '<button id="save">Visual Save</button>',
            environment_revision="rev-1",
            snapshot_id=snapshot_id,
            page_revision="page-1",
            ttl_ms=60_000,
        )
        dom = replace(model.affordances[0], backend_candidates=["dom"])
        visual = Affordance(
            "visual_save",
            Surface.VISUAL,
            "button",
            "Visual Save",
            "click",
            {"bbox": [100, 70, 40, 40], "screenshot_ref": f"screen-{sequence}.png"},
            AffordanceLease.issue(
                environment_revision="rev-1",
                ttl_ms=60_000,
                snapshot_id=snapshot_id,
                page_revision="page-1",
                target_fingerprint="visual-save-v1",
            ),
            backend_candidates=["visual"],
            confidence=0.95,
            evidence=[f"screen-{sequence}.png"],
        )
        observation = Observation(
            "rev-1",
            screenshot_ref=f"screen-{sequence}.png",
            snapshot_id=snapshot_id,
            page_revision="page-1",
            metadata={
                "saved": self.world.saved,
                "viewport_size": [640, 480],
            },
        )
        candidates: tuple[GroundingCandidate, ...] = (
            candidate_from_affordance(
                dom,
                observation,
                semantic_target_id="pending",
                compatible_executor="dom",
            ),
            candidate_from_affordance(
                visual,
                observation,
                semantic_target_id="pending",
                compatible_executor="visual",
                image_size=(640, 480),
            ),
        )
        target = SemanticEntityResolver().resolve(
            tuple(
                CandidateDescriptor("button", "Visual Save", "click", "main", candidate)
                for candidate in candidates
            )
        )[0]
        observation = replace(
            observation,
            target_fingerprints=candidate_fingerprints((target,)),
        )
        return BrowserSnapshot(
            observation,
            replace(model, affordances=[dom, visual], kept_node_count=2),
            source_observations=(
                SourceObservation(
                    GroundingSource.DOM,
                    "dom-adapter",
                    snapshot_id,
                    "rev-1",
                    "page-1",
                ),
                SourceObservation(
                    GroundingSource.VISUAL,
                    "visual-region-v1",
                    snapshot_id,
                    "rev-1",
                    "page-1",
                    artifact_refs=(f"screen-{sequence}.png",),
                ),
            ),
            grounding_candidates=target.grounding_candidates,
            unified_affordances=(target,),
        )


class FallbackPlanner:
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if any(
            outcome.verification_status == "passed"
            for outcome in request.recent_outcomes
        ):
            return PlannerDoneResponse(result={"saved": True})
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=PlannerProposal(
                proposal_id=f"proposal-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=request.observation.affordances[0].target_id,
                subgoal="Activate the visual save control at the current position",
            ),
        )


def test_visual_requirement_does_not_borrow_evidence_for_a_dom_route() -> None:
    world = FallbackWorld()
    observer = CrossSurfaceObserver(world)
    dom = FailBeforeDispatchDomExecutor()
    executors = ExecutorRouter()
    executors.register(dom)
    executors.register(VisualExecutor(FallbackPointer(world)))
    task = TaskSpec(
        task_id="fallback-task",
        revision=1,
        objective="Activate the visual save control at the current position",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Visual Save",),
        success_criteria=("saved state is true",),
        source_request_ref="test",
        requested_capabilities=("settings.write",),
    )
    builder = ContractBuilder(
        requirements={
            observer.semantic_target_id: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "observation_metadata",
                        "saved",
                        True,
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                ),
                idempotency_key="fallback-task:save:v1",
            )
        }
    )

    result = compose_run_coordinator(
        observer=observer,
        planner=FallbackPlanner(),
        executor=executors,
        contract_builder=builder,
    ).run_sync(RunRequest(task_spec=task, capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert result.result == {"saved": True}
    assert dom.calls == 0
    assert world.visual_clicks == 1
    assert result.verification is not None and result.verification.passed
    route_nodes = [node for node in result.trace.nodes if node.kind == "RouteSelected"]
    assert [node.payload["source"] for node in route_nodes] == ["visual"]
    rejected_dom_gate = next(
        gate
        for gate in route_nodes[0].payload["hard_gates"]
        if gate["candidate_id"] == "candidate:dom:dom_button_1"
    )
    assert rejected_dom_gate == {
        "candidate_id": "candidate:dom:dom_button_1",
        "passed": False,
        "reasons": ["required_evidence_missing"],
    }
    contract_nodes = [node for node in result.trace.nodes if node.kind == "ContractBuilt"]
    assert len(contract_nodes) == 1
    assert not any(node.kind == "RecoveryStarted" for node in result.trace.nodes)
    assert not result.state.current_excluded_candidates
    assert result.state.current_failure is None
    assert result.state.effectful_action_count == 1
    assert result.state.last_receipt is not None and result.state.last_receipt.success


def test_coordinator_rebinds_moving_visual_point_from_preflight_epoch() -> None:
    world = FallbackWorld()

    class MovingPointer:
        def click_xy(self, x: int, y: int) -> None:
            assert (x, y) == (220, 90)
            world.visual_clicks += 1
            world.saved = True

        def type_text(self, text: str) -> None:
            raise AssertionError(f"unexpected text input: {text}")

    class MovingPointObserver:
        def __init__(self) -> None:
            self.sequence = 0
            self.semantic_target_id = self._snapshot(0).unified_affordances[0].semantic_target_id

        def capture(self) -> BrowserSnapshot:
            self.sequence += 1
            return self._snapshot(self.sequence)

        def _snapshot(self, sequence: int) -> BrowserSnapshot:
            snapshot_id = f"moving-{sequence}"
            left = 100 if sequence <= 1 else 200
            model = DomAdapter().transduce(
                "<main>moving point</main>",
                environment_revision="rev-1",
                snapshot_id=snapshot_id,
                page_revision="page-1",
                ttl_ms=60_000,
            )
            visual = Affordance(
                "visual_point",
                Surface.VISUAL,
                "point",
                "Moving target",
                "point_activate",
                {"bbox": [left, 70, 40, 40], "screenshot_ref": f"moving-{sequence}.png"},
                AffordanceLease.issue(
                    environment_revision="rev-1",
                    ttl_ms=60_000,
                    snapshot_id=snapshot_id,
                    page_revision="page-1",
                    target_fingerprint=f"moving-point-{sequence}",
                ),
                backend_candidates=["visual"],
                confidence=0.95,
                evidence=[f"moving-{sequence}.png"],
            )
            observation = Observation(
                "rev-1",
                screenshot_ref=f"moving-{sequence}.png",
                snapshot_id=snapshot_id,
                page_revision="page-1",
                metadata={"saved": world.saved, "viewport_size": [640, 480]},
            )
            candidate = candidate_from_affordance(
                visual,
                observation,
                semantic_target_id="pending",
                compatible_executor="visual",
                image_size=(640, 480),
            )
            target = SemanticEntityResolver().resolve(
                (CandidateDescriptor("point", "Moving target", "point_activate", "main", candidate),)
            )[0]
            observation = replace(observation, target_fingerprints=candidate_fingerprints((target,)))
            return BrowserSnapshot(
                observation,
                replace(model, affordances=[visual], kept_node_count=1),
                source_observations=(
                    SourceObservation(
                        GroundingSource.VISUAL,
                        "visual-region-v1",
                        snapshot_id,
                        "rev-1",
                        "page-1",
                    ),
                ),
                grounding_candidates=target.grounding_candidates,
                unified_affordances=(target,),
            )

    class MovingPointPlanner:
        def propose(
            self,
            request: PlanningRequest,
        ) -> PlannerProposalResponse | PlannerDoneResponse:
            if any(
                outcome.verification_status == "passed"
                for outcome in request.recent_outcomes
            ):
                return PlannerDoneResponse(result={"saved": True})
            return PlannerProposalResponse(
                proposal_provenance=TEST_PROPOSAL_PROVENANCE,
                proposal=PlannerProposal(
                    proposal_id=(
                        "moving-proposal-"
                        f"{request.identity.evaluated_at_state_version}"
                    ),
                    based_on_task_revision=request.identity.task_revision,
                    based_on_state_version=(
                        request.identity.evaluated_at_state_version
                    ),
                    snapshot_id=request.identity.snapshot_id,
                    action_kind=PlannerActionKind.POINT_ACTIVATE,
                    target_affordance_id=(
                        request.observation.affordances[0].target_id
                    ),
                ),
            )

    observer = MovingPointObserver()
    task = TaskSpec(
        task_id="moving-point-task",
        revision=1,
        objective="Click the visual moving target",
        operation_class=OperationClass.READ_ONLY,
        targets=("Moving target",),
        success_criteria=("saved state is true",),
        source_request_ref="test",
    )
    builder = ContractBuilder(
        requirements={
            observer.semantic_target_id: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "observation_metadata",
                        "saved",
                        True,
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                ),
            )
        }
    )
    executors = ExecutorRouter()
    executors.register(VisualExecutor(MovingPointer()))

    result = compose_run_coordinator(
        observer=observer,
        planner=MovingPointPlanner(),
        executor=executors,
        contract_builder=builder,
    ).run_sync(RunRequest(task_spec=task))

    assert result.status == RuntimeStep.DONE
    assert world.visual_clicks == 1
    rebound = [node for node in result.trace.nodes if node.kind == "ContractReboundAtPreflight"]
    assert len(rebound) == 1
    assert rebound[0].payload["source_contract_hash"] != rebound[0].payload["contract_hash"]

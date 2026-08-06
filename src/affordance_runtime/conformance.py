"""Real DOM, screenshot, and node-wot Coordinator conformance profile."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

from affordance_runtime.action_contract_builder import ActionContractMaterializer
from affordance_runtime.adapters.dom import PageAffordanceModel
from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.visual import detect_magenta_region
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ACTION_CONTRACT_SCHEMA_VERSION,
    ActionContract,
    Observation,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.environment import environment_manifest
from affordance_runtime.executors import DomExecutor, ExecutorRouter, VisualExecutor, WotExecutor
from affordance_runtime.immutable import FrozenSequence
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import PlannerDoneResponse, PlannerProposalResponse, PlannerResponse
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression

CONFORMANCE_GOAL = "Enable one reversible shared state with independent oracle evidence."
CONFORMANCE_CAPABILITY = "conformance.write.reversible"


@dataclass(frozen=True)
class ConformanceSurfaceResult:
    surface: str
    backend: str
    status: str
    oracle_enabled: bool
    oracle_source: str
    verification_status: str
    contract_schema: str
    contract_capabilities: list[str]
    event_types: list[str]
    trace_path: str
    screenshot_refs: list[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_capabilities", FrozenSequence(self.contract_capabilities))
        object.__setattr__(self, "event_types", FrozenSequence(self.event_types))
        object.__setattr__(self, "screenshot_refs", FrozenSequence(self.screenshot_refs))


def _preserves_shared_contract_envelope(item: ConformanceSurfaceResult) -> bool:
    return (
        item.contract_capabilities == [CONFORMANCE_CAPABILITY]
        and item.contract_schema == ACTION_CONTRACT_SCHEMA_VERSION
    )


@dataclass
class ConformancePlanner:
    surface: str
    oracle_state_url: str

    def propose(self, request: PlanningRequest) -> PlannerResponse:
        if any(item.verification_status == "passed" for item in request.recent_outcomes):
            return PlannerDoneResponse(result={"enabled": True, "surface": self.surface})
        affordance = self._select(request)
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id=f"conformance-{self.surface}-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal=CONFORMANCE_GOAL,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=affordance.target_id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="conformance-planner",
                profile_id=self.surface,
            ),
        )

    def _select(self, request: PlanningRequest) -> Any:
        candidates = request.observation.affordances
        if self.surface == "dom":
            return next(item for item in candidates if item.label == "Enable shared state")
        if self.surface == "visual":
            return next(item for item in candidates if item.surface == "visual")
        return next(item for item in candidates if item.label == "setEnabled")


@dataclass
class ConformanceContractBuilder(ActionContractMaterializer):
    surface: str = "dom"
    oracle_state_url: str = ""

    def build(
        self, proposal: PlannerProposal, task_spec: TaskSpec, state: Any, snapshot: BrowserSnapshot, observation=None
    ) -> ActionContract:
        self.requirements = {
            **self.requirements,
            proposal.target_affordance_id: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "http_json",
                        self.oracle_state_url,
                        {"path": "state.enabled", "value": True},
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                ),
                required_capabilities=(CONFORMANCE_CAPABILITY,),
                idempotency_key=f"conformance-enable:{self.surface}",
                compensation="reset shared conformance state",
            ),
        }
        contract = super().build(proposal, task_spec, state, snapshot, observation)
        return replace(
            contract,
            parameters={"payload": True} if self.surface == "wot" else contract.parameters,
            contract_hash="",
        )


@dataclass
class VisualConformanceObserver:
    session: BrowserSession
    screenshot_dir: Path
    sequence: int = 0

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = self.screenshot_dir / f"visual-observation-{self.sequence:04d}.png"
        self.session.wait_for_load_state()
        base = self.session.capture(page_id="conformance-visual", screenshot_path=str(screenshot_path))
        bbox = detect_magenta_region(screenshot_path.read_bytes())
        affordances = SomAdapter().parse(
            [{"bbox": bbox, "label": "shared-state-target", "action": "click", "confidence": 1.0}],
            environment_revision=base.observation.environment_revision,
            screenshot_ref=str(screenshot_path),
            snapshot_id=base.observation.snapshot_id,
            page_revision=base.observation.page_revision,
        )
        model = PageAffordanceModel(
            page_id="conformance-visual",
            url=base.observation.url,
            environment_revision=base.observation.environment_revision,
            snapshot_id=base.observation.snapshot_id,
            page_revision=base.observation.page_revision,
            affordances=affordances,
            raw_node_count=1,
            kept_node_count=1,
        )
        observation = replace(
            base.observation,
            target_fingerprints={item.id: item.target_fingerprint for item in affordances},
            metadata={**base.observation.metadata, "visual_detector": "screenshot_pixel_threshold_magenta_v1"},
        )
        return BrowserSnapshot(observation, model)


@dataclass
class WotConformanceObserver:
    td_url: str

    def capture(self) -> BrowserSnapshot:
        td = _get_json(self.td_url)
        semantic_td = {
            "id": td.get("id"),
            "title": td.get("title"),
            "properties": td.get("properties"),
            "actions": td.get("actions"),
        }
        revision = (
            "sha256:"
            + hashlib.sha256(json.dumps(semantic_td, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        )
        snapshot_id = f"snap_{uuid4().hex}"
        thing = WotAdapter().parse(
            td,
            environment_revision=revision,
            snapshot_id=snapshot_id,
            page_revision=revision,
        )
        model = PageAffordanceModel(
            page_id="conformance-wot",
            url=self.td_url,
            environment_revision=revision,
            snapshot_id=snapshot_id,
            page_revision=revision,
            affordances=thing.affordances,
            raw_node_count=len(thing.affordances) + len(thing.state_sources),
            kept_node_count=len(thing.affordances),
        )
        observation = Observation(
            environment_revision=revision,
            url=self.td_url,
            metadata={"thing_id": thing.thing_id, "state_sources": thing.state_sources},
            snapshot_id=snapshot_id,
            page_revision=revision,
            target_fingerprints={item.id: item.target_fingerprint for item in thing.affordances},
            artifact_refs=[self.td_url],
        )
        return BrowserSnapshot(observation, model)


def run_cross_surface_conformance(
    output_dir: Path,
    *,
    fixture_url: str,
    wot_td_url: str,
    oracle_url: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    oracle_state_url = f"{oracle_url.rstrip('/')}/state"
    results: list[ConformanceSurfaceResult] = []
    browser_versions: set[str] = set()

    for surface in ("dom", "visual", "wot"):
        _post_json(f"{oracle_url.rstrip('/')}/reset", {})
        run_id = f"cross-surface-{surface}"
        artifact_store = ArtifactStore(output_dir / "runs")
        envelope = RunRequest(
            task_spec=TaskSpec(
                task_id=run_id,
                revision=1,
                objective=CONFORMANCE_GOAL,
                operation_class=OperationClass.REVERSIBLE_WRITE,
                requirements=canonical_effect_requirements(
                    ("shared state",), OperationClass.REVERSIBLE_WRITE, "conformance", (CONFORMANCE_CAPABILITY,)
                ),
                allowed_effect_refs=canonical_effect_requirement_refs(("shared state",)),
                success=SuccessExpression(
                    expression_id="success:shared-state-enabled",
                    operator="criterion",
                    criterion_id="criterion:shared-state-enabled",
                    requirement_refs=("requirement:effect:1",),
                ),
                evidence_requirements=("independent oracle evidence",),
                capability_ceiling=(CONFORMANCE_CAPABILITY,),
                source_request_ref="conformance",
            ),
            capabilities=[CONFORMANCE_CAPABILITY],
        )
        contract_builder = ConformanceContractBuilder(
            surface=surface,
            oracle_state_url=oracle_state_url,
        )
        if surface == "dom":
            with BrowserSession.launch(f"{fixture_url.rstrip('/')}/conformance") as session:
                browser_versions.add(session.browser_version)
                router = ExecutorRouter()
                router.register(DomExecutor(session))
                result = compose_run_coordinator(
                    observer=session,
                    executor=router,
                    artifacts=artifact_store,
                    contract_builder=contract_builder,
                ).run_sync(envelope)
        elif surface == "visual":
            with BrowserSession.launch(f"{fixture_url.rstrip('/')}/conformance-visual") as session:
                browser_versions.add(session.browser_version)
                observer = VisualConformanceObserver(session, output_dir / "screenshots")
                router = ExecutorRouter()
                router.register(VisualExecutor(session))
                result = compose_run_coordinator(
                    observer=observer,
                    executor=router,
                    artifacts=artifact_store,
                    contract_builder=contract_builder,
                ).run_sync(envelope)
        else:
            router = ExecutorRouter()
            router.register(WotExecutor())
            result = compose_run_coordinator(
                observer=WotConformanceObserver(wot_td_url),
                executor=router,
                artifacts=artifact_store,
                contract_builder=contract_builder,
            ).run_sync(envelope)

        oracle = _get_json(oracle_state_url)
        contract = result.state.current_contract
        results.append(
            ConformanceSurfaceResult(
                surface=surface,
                backend=contract.backend if contract else "",
                status=result.status.value,
                oracle_enabled=bool(oracle["state"]["enabled"]),
                oracle_source="node-wot-control",
                verification_status=result.verification.status.value if result.verification else "missing",
                contract_schema=contract.schema_version if contract else "",
                contract_capabilities=list(contract.required_capabilities) if contract else [],
                event_types=[node.kind for node in result.trace.nodes],
                trace_path=next((item.path for item in result.artifacts if item.path.endswith("events.jsonl")), ""),
                screenshot_refs=[
                    ref
                    for node in result.trace.nodes
                    if node.kind
                    in {"ObservationCaptured", "PostActionObservationCaptured", "TargetedPerceptionCaptured"}
                    for ref in node.payload.get("artifact_refs", [])
                    if ref.endswith(".png")
                ],
            )
        )

    errors: list[str] = []
    for item in results:
        if item.status != RuntimeStep.DONE.value or not item.oracle_enabled:
            errors.append(f"{item.surface} did not reach the shared oracle")
        if item.verification_status != "passed" or "PostActionEvaluated" not in item.event_types:
            errors.append(f"{item.surface} lacks independent verifier evidence")
        if item.backend != item.surface:
            errors.append(f"{item.surface} bypassed its declared backend")
        if not _preserves_shared_contract_envelope(item):
            errors.append(f"{item.surface} did not preserve the shared contract envelope")
        if not item.trace_path:
            errors.append(f"{item.surface} trace is missing")
    visual = next(item for item in results if item.surface == "visual")
    if len(visual.screenshot_refs) < 3:
        errors.append("visual path did not retain real screenshots for observe/preflight/post-action")

    health = _get_json(f"{oracle_url.rstrip('/')}/health")
    report = {
        "suite_version": "cross-surface-conformance-v1",
        "task_goal": CONFORMANCE_GOAL,
        "capability": CONFORMANCE_CAPABILITY,
        "oracle_url": oracle_state_url,
        "oracle_implementation": health.get("implementation", "unknown"),
        "visual_detector": "screenshot_pixel_threshold_magenta_v1",
        "uses_dom_coordinates_for_visual": False,
        "surfaces": [asdict(item) for item in results],
        "environment": environment_manifest(
            browser_version=",".join(sorted(browser_versions)),
            fixture_version=str(_get_json(f"{fixture_url.rstrip('/')}/api/health")["fixture_version"]),
            suite_version="cross-surface-conformance-v1",
            seed_semantics="single_reversible_shared_oracle_v1",
        ).to_dict(),
        "acceptance_errors": errors,
        "acceptance": "passed" if not errors else "failed",
    }
    report_path = output_dir / "cross-surface-conformance-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown = [
        "# Cross-Surface Conformance Report",
        "",
        f"- Oracle: `{report['oracle_implementation']}`",
        f"- Surfaces: `{', '.join(item.surface for item in results)}`",
        "- Visual grounding: `real screenshot pixels; no DOM coordinates`",
        f"- Acceptance: `{report['acceptance'].upper()}`",
        "",
    ]
    (output_dir / "cross-surface-conformance-report.md").write_text("\n".join(markdown), encoding="utf-8")
    return report


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5.0) as response:  # noqa: S310 - configured local conformance services
        return json.loads(response.read())


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5.0) as response:  # noqa: S310 - configured local conformance services
        return json.loads(response.read())

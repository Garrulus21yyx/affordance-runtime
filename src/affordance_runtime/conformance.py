"""Real DOM, screenshot, and node-wot Coordinator conformance profile."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen
from uuid import uuid4

from affordance_runtime.adapters.dom import PageAffordanceModel
from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.visual import detect_magenta_region
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import ACTION_CONTRACT_SCHEMA_VERSION, ActionContract, Observation, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.environment import environment_manifest
from affordance_runtime.executors import DomExecutor, ExecutorRouter, VisualExecutor, WotExecutor
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel

CONFORMANCE_GOAL = "Enable one reversible shared state with independent oracle evidence."
CONFORMANCE_CAPABILITY = "conformance.write.reversible"


class ConformancePlanningRequestBuilderPort(Protocol):
    def build(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlanningRequest: ...


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


def _preserves_shared_contract_envelope(item: ConformanceSurfaceResult) -> bool:
    return (
        item.contract_capabilities == [CONFORMANCE_CAPABILITY]
        and item.contract_schema == ACTION_CONTRACT_SCHEMA_VERSION
    )


@dataclass
class ConformancePlanner:
    surface: str
    oracle_state_url: str
    planning_request_builder: ConformancePlanningRequestBuilderPort | None = None

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        request = _conformance_planning_request(
            self.planning_request_builder,
            envelope,
            state,
            snapshot,
        )
        if request is not None and request.identity.snapshot_id != snapshot.observation.snapshot_id:
            return PlannerDecision(reason="stale conformance planning request")
        if state.receipts:
            return PlannerDecision(done=True, result={"enabled": True, "surface": self.surface})
        affordance = self._select(snapshot)
        parameters = {"payload": True} if self.surface == "wot" else {}
        contract = ActionContract.from_affordance(
            affordance,
            intent=CONFORMANCE_GOAL,
            backend=self.surface,
            verifier_plan=[
                VerifierSpec(
                    "http_json",
                    self.oracle_state_url,
                    {"path": "state.enabled", "value": True},
                )
            ],
            required_capabilities=[CONFORMANCE_CAPABILITY],
            parameters=parameters,
        )
        return PlannerDecision(
            contract=replace(
                contract,
                idempotency_key=f"conformance-enable:{self.surface}",
                compensation="reset shared conformance state",
                contract_hash="",
            )
        )

    def _select(self, snapshot: BrowserSnapshot) -> Any:
        candidates = snapshot.affordance_model.affordances
        if self.surface == "dom":
            return next(item for item in candidates if item.label == "Enable shared state")
        if self.surface == "visual":
            return next(item for item in candidates if item.surface.value == "visual")
        return next(item for item in candidates if item.label == "setEnabled")


def _conformance_planning_request(
    builder: ConformancePlanningRequestBuilderPort | None,
    envelope: TaskEnvelope,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlanningRequest | None:
    if envelope.task_spec is None:
        return None
    return (builder or PlanningRequestBuilder()).build(envelope, state, snapshot)


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
        revision = "sha256:" + hashlib.sha256(
            json.dumps(semantic_td, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
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
        planner = ConformancePlanner(surface, oracle_state_url)
        envelope = TaskEnvelope(
            run_id,
            CONFORMANCE_GOAL,
            constraints={"read_only": False, "must_return_evidence": True},
            capabilities=[CONFORMANCE_CAPABILITY],
        )
        if surface == "dom":
            with BrowserSession.launch(f"{fixture_url.rstrip('/')}/conformance") as session:
                browser_versions.add(session.browser_version)
                router = ExecutorRouter()
                router.register(DomExecutor(session))
                result = RunCoordinator(
                    observer=session,
                    planner=planner,
                    executor=router,
                    artifacts=artifact_store,
                ).run_sync(envelope)
        elif surface == "visual":
            with BrowserSession.launch(f"{fixture_url.rstrip('/')}/conformance-visual") as session:
                browser_versions.add(session.browser_version)
                observer = VisualConformanceObserver(session, output_dir / "screenshots")
                router = ExecutorRouter()
                router.register(VisualExecutor(session))
                result = RunCoordinator(
                    observer=observer,
                    planner=planner,
                    executor=router,
                    artifacts=artifact_store,
                ).run_sync(envelope)
        else:
            router = ExecutorRouter()
            router.register(WotExecutor())
            result = RunCoordinator(
                observer=WotConformanceObserver(wot_td_url),
                planner=planner,
                executor=router,
                artifacts=artifact_store,
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
                    for observation in result.state.observations
                    for ref in observation.artifact_refs
                    if ref.endswith(".png")
                ],
            )
        )

    errors: list[str] = []
    for item in results:
        if item.status != RuntimeStep.DONE.value or not item.oracle_enabled:
            errors.append(f"{item.surface} did not reach the shared oracle")
        if item.verification_status != "passed" or "PostconditionPassed" not in item.event_types:
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

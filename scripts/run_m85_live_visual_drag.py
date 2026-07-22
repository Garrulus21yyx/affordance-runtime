#!/usr/bin/env python3
"""Run a screenshot-grounded canvas drag through the full M8.5 runtime."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import (
    Affordance,
    AffordanceLease,
    Observation,
    Surface,
    VerifierSpec,
)
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.executors import VisualExecutor
from affordance_runtime.grounding import GroundingSource, SourceObservation
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)


@dataclass
class PixelDragObserver:
    session: BrowserSession
    page: Any
    captures: int = 0
    last_source_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    last_destination_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)

    def capture(self) -> BrowserSnapshot:
        self.captures += 1
        snapshot = self.session.capture(page_id="pixel-canvas-drag", ttl_ms=60_000)
        png = self.page.screenshot(type="png")
        source_bbox = _color_bbox(self.page, png, "red")
        destination_bbox = _color_bbox(self.page, png, "green")
        self.last_source_bbox = source_bbox
        self.last_destination_bbox = destination_bbox
        screenshot_ref = "sha256:" + hashlib.sha256(png).hexdigest()
        observation = replace(
            snapshot.observation,
            screenshot_ref=screenshot_ref,
            metadata={
                **snapshot.observation.metadata,
                "dragged": bool(self.page.evaluate("() => window.dragged === true")),
                "viewport_size": [640, 480],
            },
        )
        source = _visual_affordance(
            "pixel_drag_source",
            "red source",
            source_bbox,
            observation,
        )
        destination = _visual_affordance(
            "pixel_drag_destination",
            "green destination",
            destination_bbox,
            observation,
        )
        descriptors = []
        for role, affordance in (("draggable", source), ("dropzone", destination)):
            descriptors.append(
                CandidateDescriptor(
                    role,
                    affordance.label,
                    "drag",
                    "canvas-board",
                    candidate_from_affordance(
                        affordance,
                        observation,
                        semantic_target_id="pending",
                        image_size=(640, 480),
                        compatible_executor="visual",
                    ),
                )
            )
        targets = SemanticEntityResolver().resolve(descriptors)
        observation = replace(
            observation,
            target_fingerprints=candidate_fingerprints(targets),
        )
        return BrowserSnapshot(
            observation,
            replace(
                snapshot.affordance_model,
                affordances=[source, destination],
                kept_node_count=2,
            ),
            source_observations=(
                SourceObservation(
                    GroundingSource.VISUAL,
                    "local-screenshot-color-regions-v1",
                    observation.snapshot_id,
                    observation.environment_revision,
                    observation.page_revision,
                    artifact_refs=(screenshot_ref,),
                ),
            ),
            grounding_candidates=tuple(
                candidate for target in targets for candidate in target.grounding_candidates
            ),
            unified_affordances=targets,
        )


@dataclass
class PixelDragPlanner:
    calls: int = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        self.calls += 1
        if snapshot.observation.metadata["dragged"] is True:
            return PlannerDecision(done=True, result={"dragged": True})
        source = next(
            item for item in snapshot.unified_affordances if item.label == "red source"
        )
        destination = next(
            item
            for item in snapshot.unified_affordances
            if item.label == "green destination"
        )
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id=f"pixel-drag-{self.calls}-{state.version}",
                based_on_task_revision=envelope.task_spec.revision if envelope.task_spec else 1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal="Drag the red source inside the green destination",
                action_kind=PlannerActionKind.DRAG,
                target_affordance_id=source.semantic_target_id,
                destination_affordance_id=destination.semantic_target_id,
            )
        )


def run_live_visual_drag(chromium_executable: str | None = None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    with sync_playwright() as playwright:
        launch_options: dict[str, Any] = {"headless": True}
        if chromium_executable:
            launch_options["executable_path"] = chromium_executable
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(viewport={"width": 640, "height": 480})
        page = context.new_page()
        try:
            page.set_content(_CANVAS_HTML)
            session = BrowserSession(cast(Any, page), lease_ttl_ms=60_000)
            observer = PixelDragObserver(session, page)
            probe = observer.capture()
            source_id = next(
                item.semantic_target_id
                for item in probe.unified_affordances
                if item.label == "red source"
            )
            planner = PixelDragPlanner()
            task = TaskSpec(
                task_id="m85-live-pixel-canvas-drag",
                revision=1,
                objective="Drag the red source completely inside the green destination",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                targets=("red source", "green destination"),
                success_criteria=("canvas drag oracle is true",),
                evidence_requirements=("independent canvas mouseup state",),
                requested_capabilities=("canvas.write",),
                source_request_ref="m8.5-live-visual-drag",
            )
            result = RunCoordinator(
                observer,
                planner,
                VisualExecutor(session),
                contract_builder=ContractBuilder(
                    requirements={
                        source_id: ContractRequirements(
                            verifier_plan=(
                                VerifierSpec("observation_metadata", "dragged", True),
                            ),
                            idempotency_key="m85:canvas-drag:v1",
                        )
                    }
                ),
            ).run_sync(TaskEnvelope(task_spec=task, capabilities=["canvas.write"]))
            events = tuple(node.kind for node in result.trace.nodes)
            proposals_are_semantic = all(
                not set(proposal.get("parameters", {})).intersection({"x", "y", "bbox", "bid"})
                for proposal in result.state.planner_history
            )
            route_sources = tuple(
                str(node.payload.get("source") or "")
                for node in result.trace.nodes
                if node.kind == "RouteSelected"
            )
            receipt = result.state.receipts[-1] if result.state.receipts else None
            gesture_payload = next(
                (
                    node.payload.get("gesture_binding")
                    for node in result.trace.nodes
                    if node.kind == "ContractBuilt" and node.payload.get("gesture_binding")
                ),
                None,
            )
            report = {
                "schema_version": "m8.5-live-visual-drag-v1",
                "browser_version": browser.version,
                "runtime_status": result.status.value,
                "success": result.status == RuntimeStep.DONE,
                "verification": result.verification.status.value if result.verification else "",
                "dragged": bool(page.evaluate("() => window.dragged === true")),
                "source_bbox": list(observer.last_source_bbox),
                "destination_bbox": list(observer.last_destination_bbox),
                "screenshot_captures": observer.captures,
                "route_sources": route_sources,
                "gesture_selected_route": (
                    str(gesture_payload.get("selected_route") or "")
                    if isinstance(gesture_payload, dict)
                    else ""
                ),
                "planner_calls": planner.calls,
                "planner_proposals_semantic_only": proposals_are_semantic,
                "receipt_action": receipt.evidence.get("action") if receipt else "",
                "gesture_contract_traced": gesture_payload is not None,
                "trace_events": events,
                "remote_model_used": False,
            }
            report["acceptance_errors"] = [
                reason
                for condition, reason in (
                    (not report["success"], "runtime did not finish"),
                    (not report["dragged"], "independent canvas oracle is false"),
                    (report["verification"] != "passed", "verification did not pass"),
                    (
                        route_sources != ("visual",)
                        or report["gesture_selected_route"] != "visual",
                        "dual-target gesture did not select the visual route",
                    ),
                    (not proposals_are_semantic, "planner proposal exposed a low-level handle"),
                    (report["receipt_action"] != "visual_drag", "visual drag was not executed"),
                    (not report["gesture_contract_traced"], "dual-target gesture was not traced"),
                )
                if condition
            ]
            return report
        finally:
            context.close()
            browser.close()


def _visual_affordance(
    affordance_id: str,
    label: str,
    bbox: tuple[int, int, int, int],
    observation: Observation,
) -> Affordance:
    fingerprint = "sha256:" + hashlib.sha256(
        json.dumps({"label": label, "bbox": bbox}, sort_keys=True).encode()
    ).hexdigest()
    return Affordance(
        affordance_id,
        Surface.VISUAL,
        "region",
        label,
        "drag",
        {"bbox": list(bbox), "screenshot_ref": observation.screenshot_ref},
        AffordanceLease.issue(
            environment_revision=observation.environment_revision,
            ttl_ms=60_000,
            snapshot_id=observation.snapshot_id,
            page_revision=observation.page_revision,
            target_fingerprint=fingerprint,
            provenance=["local-screenshot-color-regions-v1"],
        ),
        backend_candidates=["visual"],
        confidence=1.0,
        evidence=[observation.screenshot_ref],
    )


def _color_bbox(page: Any, png: bytes, color: str) -> tuple[int, int, int, int]:
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    result = page.evaluate(
        """async ({url, color}) => {
          const image = new Image();
          image.src = url;
          await image.decode();
          const canvas = document.createElement('canvas');
          canvas.width = image.width; canvas.height = image.height;
          const context = canvas.getContext('2d');
          context.drawImage(image, 0, 0);
          const pixels = context.getImageData(0, 0, image.width, image.height).data;
          let minX = image.width, minY = image.height, maxX = -1, maxY = -1;
          for (let y = 0; y < image.height; y++) for (let x = 0; x < image.width; x++) {
            const i = (y * image.width + x) * 4;
            const r = pixels[i], g = pixels[i + 1], b = pixels[i + 2];
            const match = color === 'red'
              ? r > 170 && g < 100 && b < 100
              : g > 130 && r < 100 && b < 130;
            if (match) { minX = Math.min(minX, x); minY = Math.min(minY, y);
                         maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
          }
          if (maxX < minX || maxY < minY) return null;
          return [minX, minY, maxX - minX + 1, maxY - minY + 1];
        }""",
        {"url": data_url, "color": color},
    )
    if not isinstance(result, list) or len(result) != 4:
        raise ValueError(f"screenshot contains no {color} region")
    bbox = tuple(int(value) for value in result)
    if bbox[2] <= 0 or bbox[3] <= 0:
        raise ValueError(f"screenshot {color} region has invalid extent")
    return bbox  # type: ignore[return-value]


_CANVAS_HTML = """
<style>html, body { margin: 0; background: white; }</style>
<canvas id="board" width="640" height="360"></canvas>
<script>
  const canvas = document.querySelector('#board');
  const context = canvas.getContext('2d');
  const source = {x: 80, y: 120, w: 50, h: 50};
  const destination = {x: 420, y: 100, w: 120, h: 120};
  window.dragged = false;
  let holding = false;
  function draw() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = 'rgb(220, 30, 30)';
    context.fillRect(source.x, source.y, source.w, source.h);
    context.fillStyle = 'rgb(20, 190, 70)';
    context.fillRect(destination.x, destination.y, destination.w, destination.h);
  }
  canvas.addEventListener('mousedown', event => {
    holding = event.offsetX >= source.x && event.offsetX <= source.x + source.w &&
              event.offsetY >= source.y && event.offsetY <= source.y + source.h;
  });
  canvas.addEventListener('mouseup', event => {
    if (holding && event.offsetX >= destination.x && event.offsetX <= destination.x + destination.w &&
        event.offsetY >= destination.y && event.offsetY <= destination.y + destination.h) {
      window.dragged = true;
    }
    holding = false;
  });
  draw();
</script>
"""


def _default_chromium_executable() -> str | None:
    cache = Path.home() / ".cache" / "ms-playwright"
    matches = sorted(cache.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return str(matches[-1]) if matches else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium-executable", default=_default_chromium_executable())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_live_visual_drag(args.chromium_executable)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not report["acceptance_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

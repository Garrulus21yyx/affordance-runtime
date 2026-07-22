#!/usr/bin/env python3
"""Run the M8.5 live DOM/pixel conflict family in local Chromium."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator, RuntimeFeatures
from affordance_runtime.executors import DomExecutor
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    GroundingSource,
    SourceAssertion,
    SourceObservation,
)
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.source_assertions import SourceAssertionOrchestrator
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


@dataclass
class LiveConflictObserver:
    session: BrowserSession
    page: Any
    adaptive: bool
    targeted_wait_ms: int = 1_300
    visual_calls: int = 0
    targeted_calls: int = 0

    def capture(self) -> BrowserSnapshot:
        snapshot = self._capture_base()
        return self._with_assertions(snapshot) if self.adaptive else snapshot

    def capture_targeted(
        self,
        requests: tuple[ActivePerceptionRequest, ...],
    ) -> BrowserSnapshot:
        if not requests:
            raise ValueError("targeted perception requires a bounded request")
        self.targeted_calls += 1
        self.page.wait_for_timeout(self.targeted_wait_ms)
        return self._with_assertions(self._capture_base())

    def _capture_base(self) -> BrowserSnapshot:
        snapshot = self.session.capture(page_id="live-conflict", ttl_ms=60_000)
        metadata = dict(snapshot.observation.metadata)
        metadata["saved"] = bool(self.page.evaluate("() => window.saved === true"))
        return replace(
            snapshot,
            observation=replace(snapshot.observation, metadata=metadata),
        )

    def _with_assertions(self, snapshot: BrowserSnapshot) -> BrowserSnapshot:
        target = next(
            item for item in snapshot.unified_affordances if item.role == "button"
        )
        png = self.page.screenshot(type="png")
        self.visual_calls += 1
        red, green = _red_green_pixel_counts(png)
        visual_available = green > red
        dom_available = (
            self.page.get_attribute("#save", "data-available") == "true"
        )
        observation = replace(
            snapshot.observation,
            screenshot_ref="sha256:" + hashlib.sha256(png).hexdigest(),
        )
        assertions = (
            SourceAssertion(
                f"dom-availability-{observation.snapshot_id}",
                target.semantic_target_id,
                "availability",
                dom_available,
                "boolean",
                GroundingSource.DOM,
                observation.snapshot_id,
                observation.environment_revision,
                observation.page_revision,
                "live-dom-attribute-v1",
                evidence_refs=("dom:data-available",),
            ),
            SourceAssertion(
                f"visual-availability-{observation.snapshot_id}",
                target.semantic_target_id,
                "availability",
                visual_available,
                "boolean",
                GroundingSource.VISUAL,
                observation.snapshot_id,
                observation.environment_revision,
                observation.page_revision,
                "live-pixel-color-v1",
                evidence_refs=(observation.screenshot_ref,),
            ),
        )
        enriched = replace(
            snapshot,
            observation=observation,
            source_observations=(
                *snapshot.source_observations,
                SourceObservation(
                    GroundingSource.VISUAL,
                    "live-pixel-color-v1",
                    observation.snapshot_id,
                    observation.environment_revision,
                    observation.page_revision,
                    artifact_refs=(observation.screenshot_ref,),
                ),
            ),
        )
        return SourceAssertionOrchestrator().reconcile_snapshot(
            enriched,
            assertions,
            available_sources=frozenset(
                {GroundingSource.DOM, GroundingSource.VISUAL}
            ),
            observation_budget=1,
        )


@dataclass
class SavePlanner:
    calls: int = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        self.calls += 1
        if snapshot.observation.metadata.get("saved") is True:
            return PlannerDecision(done=True, result={"saved": True})
        target = next(
            item for item in snapshot.unified_affordances if item.label == "Save"
        )
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id=f"live-conflict-{self.calls}-{state.version}",
                based_on_task_revision=envelope.task_spec.revision if envelope.task_spec else 1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal="Activate Save only when availability is current",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=target.semantic_target_id,
            )
        )


def run_live_conflict_family(chromium_executable: str | None = None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    with sync_playwright() as playwright:
        launch_options: dict[str, Any] = {"headless": True}
        if chromium_executable:
            launch_options["executable_path"] = chromium_executable
        browser = playwright.chromium.launch(**launch_options)
        try:
            runs = [
                _run_profile(browser, "fixed_dom_first", adaptive=False),
                _run_profile(browser, "adaptive_conflict_gate", adaptive=True),
            ]
            errors: list[str] = []
            fixed, adaptive = runs
            if fixed["effect_count"] != 0 or fixed["verification"] != "failed":
                errors.append("fixed DOM-first did not expose the live pixel disagreement")
            if not adaptive["success"] or adaptive["effect_count"] != 1:
                errors.append("adaptive conflict gate did not complete exactly once")
            if adaptive["targeted_perception_calls"] != 1:
                errors.append("adaptive conflict gate did not use exactly one targeted observation")
            if not adaptive["conflict_blocked_before_action"]:
                errors.append("adaptive route did not trace conflict arbitration before action")
            return {
                "schema_version": "m8.5-live-conflict-v1",
                "browser_version": browser.version,
                "runs": runs,
                "acceptance_errors": errors,
                "remote_model_used": False,
                "pixel_oracle": "full-screenshot red/green pixel counts",
            }
        finally:
            browser.close()


def _run_profile(browser: Any, profile: str, *, adaptive: bool) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 640, "height": 480})
    page = context.new_page()
    try:
        page.set_content(
            """
            <style>
              body { margin: 0; background: white; font-family: sans-serif; }
              #save { margin: 120px 0 0 220px; width: 160px; height: 72px;
                      border: 0; color: white; background: rgb(220, 30, 30); }
              #save.available { background: rgb(20, 190, 70); }
            </style>
            <button id="save" data-available="true"
              onclick="if (this.classList.contains('available')) { window.saved = true; this.textContent = 'Saved'; }">
              Save
            </button>
            <script>
              window.saved = false;
              setTimeout(() => document.querySelector('#save').classList.add('available'), 1200);
            </script>
            """
        )
        session = BrowserSession(page, lease_ttl_ms=60_000)
        observer = LiveConflictObserver(session, page, adaptive)
        probe = session.capture(page_id="live-conflict-probe", ttl_ms=60_000)
        target_id = next(
            item.semantic_target_id for item in probe.unified_affordances if item.label == "Save"
        )
        planner = SavePlanner()
        task = TaskSpec(
            task_id=f"m85-live-conflict-{profile}",
            revision=1,
            objective="Save only when the control is currently available",
            operation_class=OperationClass.REVERSIBLE_WRITE,
            targets=("Save",),
            success_criteria=("saved state is true",),
            evidence_requirements=("independent live saved state",),
            requested_capabilities=("settings.write",),
            source_request_ref="m8.5-live-conflict",
        )
        result = RunCoordinator(
            observer,
            planner,
            DomExecutor(page),
            contract_builder=ContractBuilder(
                requirements={
                    target_id: ContractRequirements(
                        verifier_plan=(
                            VerifierSpec("observation_metadata", "saved", True),
                        ),
                        idempotency_key=f"m85:live-conflict:{profile}",
                    )
                }
            ),
            features=RuntimeFeatures(recovery=False),
        ).run_sync(TaskEnvelope(task_spec=task, capabilities=["settings.write"]))
        events = tuple(node.kind for node in result.trace.nodes)
        action_index = events.index("ActionStarted") if "ActionStarted" in events else len(events)
        arbitration_index = (
            events.index("SourceAssertionsArbitrated")
            if "SourceAssertionsArbitrated" in events
            else len(events)
        )
        return {
            "profile": profile,
            "success": result.status == RuntimeStep.DONE,
            "runtime_status": result.status.value,
            "verification": result.verification.status.value if result.verification else "",
            "effect_count": int(bool(page.evaluate("() => window.saved === true"))),
            "planner_calls": planner.calls,
            "visual_pixel_calls": observer.visual_calls,
            "targeted_perception_calls": observer.targeted_calls,
            "conflict_blocked_before_action": arbitration_index < action_index,
            "trace_events": events,
        }
    finally:
        context.close()


def _red_green_pixel_counts(png: bytes) -> tuple[int, int]:
    """Decode an 8-bit RGB/RGBA PNG and count strong red/green pixels."""

    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("visual evidence is not a PNG")
    offset = 8
    width = height = color_type = 0
    compressed = bytearray()
    while offset < len(png):
        length = struct.unpack(">I", png[offset : offset + 4])[0]
        kind = png[offset + 4 : offset + 8]
        data = png[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            if bit_depth != 8 or color_type not in {2, 6}:
                raise ValueError("pixel oracle requires an 8-bit RGB/RGBA screenshot")
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    previous = bytearray(stride)
    cursor = 0
    red = green = 0
    for _ in range(height):
        filter_kind = raw[cursor]
        cursor += 1
        encoded = raw[cursor : cursor + stride]
        cursor += stride
        row = _unfilter_png_row(encoded, previous, channels, filter_kind)
        for index in range(0, stride, channels):
            r, g, b = row[index : index + 3]
            red += int(r > 150 and g < 100 and b < 100)
            green += int(g > 130 and r < 100 and b < 130)
        previous = row
    return red, green


def _unfilter_png_row(
    encoded: bytes,
    previous: bytearray,
    channels: int,
    filter_kind: int,
) -> bytearray:
    row = bytearray(len(encoded))
    for index, value in enumerate(encoded):
        left = row[index - channels] if index >= channels else 0
        above = previous[index]
        upper_left = previous[index - channels] if index >= channels else 0
        if filter_kind == 0:
            predictor = 0
        elif filter_kind == 1:
            predictor = left
        elif filter_kind == 2:
            predictor = above
        elif filter_kind == 3:
            predictor = (left + above) // 2
        elif filter_kind == 4:
            predictor = _paeth(left, above, upper_left)
        else:
            raise ValueError(f"unsupported PNG filter: {filter_kind}")
        row[index] = (value + predictor) & 0xFF
    return row


def _paeth(left: int, above: int, upper_left: int) -> int:
    value = left + above - upper_left
    left_distance = abs(value - left)
    above_distance = abs(value - above)
    upper_left_distance = abs(value - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    return above if above_distance <= upper_left_distance else upper_left


def _default_chromium_executable() -> str | None:
    cache = Path.home() / ".cache" / "ms-playwright"
    matches = sorted(cache.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return str(matches[-1]) if matches else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium-executable", default=_default_chromium_executable())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_live_conflict_family(args.chromium_executable)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not report["acceptance_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Isolated, injectable browser session for observation and execution.

This is adapted from the earlier repository without importing a package named
``src``. Playwright is loaded lazily through the ``web`` optional extra.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, RiskLevel, Surface
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    AssertionDecision,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    PerceptionRequirements,
    SourceAssertion,
    SourceObservation,
    UnifiedAffordance,
)
from affordance_runtime.perception import PerceptionOrchestratorPort
from affordance_runtime.svg_geometry import (
    SelectiveSvgGeometryObserver,
    SvgGeometryObservation,
    SvgGeometryObserverPort,
    SvgPagePort,
)
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)


class PageDriver(Protocol):
    def goto(self, url: str, **kwargs: Any) -> Any: ...

    def content(self) -> str: ...

    def click(self, selector: str) -> Any: ...

    def fill(self, selector: str, value: str) -> Any: ...

    def screenshot(self, **kwargs: Any) -> bytes: ...

    def wait_for_load_state(self, state: str = "load", **kwargs: Any) -> Any: ...

    def locator(self, selector: str) -> Any: ...


@dataclass(frozen=True)
class BrowserSnapshot:
    observation: Observation
    affordance_model: PageAffordanceModel
    source_observations: tuple[SourceObservation, ...] = ()
    svg_geometry: SvgGeometryObservation | None = None
    grounding_candidates: tuple[GroundingCandidate, ...] = ()
    unified_affordances: tuple[UnifiedAffordance, ...] = ()
    source_assertions: tuple[SourceAssertion, ...] = ()
    assertion_decisions: tuple[AssertionDecision, ...] = ()
    active_perception_requests: tuple[ActivePerceptionRequest, ...] = ()
    accessibility_tree: dict[str, Any] | None = None
    perception_requirements: PerceptionRequirements | None = None


@dataclass(frozen=True)
class _CaptureProfile:
    page_id: str
    ttl_ms: int
    screenshot_path: str | None
    perception_requirements: PerceptionRequirements | None
    task_terms: tuple[str, ...]
    task_instruction: str


def _bounded_control_value(value: str, limit: int = 480) -> str:
    """Keep both ends of long control text for bounded relational reading tasks."""

    if len(value) <= limit:
        return value
    marker = "\n...[truncated]...\n"
    prefix_length = (limit - len(marker)) // 2
    suffix_length = limit - len(marker) - prefix_length
    return value[:prefix_length] + marker + value[-suffix_length:]


def _image_size(
    screenshot_bytes: bytes,
    evaluator: Any,
) -> tuple[int, int] | None:
    if len(screenshot_bytes) >= 24 and screenshot_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        width = int.from_bytes(screenshot_bytes[16:20], "big")
        height = int.from_bytes(screenshot_bytes[20:24], "big")
        if width > 0 and height > 0:
            return width, height
    if callable(evaluator):
        try:
            value = evaluator("() => [window.innerWidth, window.innerHeight]")
            if isinstance(value, (list, tuple)) and len(value) == 2:
                width, height = int(value[0]), int(value[1])
                if width > 0 and height > 0:
                    return width, height
        except Exception:
            return None
    return None


def _environment_family(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        hostname = parsed.hostname.lower()
        host = f"[{hostname}]" if ":" in hostname else hostname
        try:
            port = parsed.port
        except ValueError:
            port = None
        authority = f"{host}:{port}" if port is not None else host
        return f"web:{parsed.scheme}://{authority}"
    if parsed.scheme:
        return f"web:{parsed.scheme.lower()}"
    return "web:unknown"


def _bounded_accessibility_tree(page: PageDriver, *, max_nodes: int = 256) -> dict[str, Any] | None:
    """Capture a bounded browser accessibility tree when the driver exposes it."""

    accessibility = getattr(page, "accessibility", None)
    snapshot = getattr(accessibility, "snapshot", None)
    raw: object = None
    if callable(snapshot):
        try:
            raw = snapshot(interesting_only=False)
        except Exception:
            raw = None
    if raw is None:
        context = getattr(page, "context", None)
        new_session = getattr(context, "new_cdp_session", None)
        if callable(new_session):
            session = None
            try:
                session = new_session(page)
                raw = session.send("Accessibility.getFullAXTree")
            except Exception:
                raw = None
            finally:
                detach = getattr(session, "detach", None)
                if callable(detach):
                    detach()
    if not isinstance(raw, dict):
        return None

    remaining = max_nodes

    def bounded(value: object, depth: int = 0) -> object:
        nonlocal remaining
        if remaining <= 0 or depth > 12:
            return None
        if isinstance(value, dict):
            remaining -= 1
            kept: dict[str, object] = {}
            for key, item in value.items():
                if key in {
                    "role",
                    "name",
                    "value",
                    "description",
                    "checked",
                    "disabled",
                    "focused",
                    "selected",
                    "children",
                    "nodes",
                    "childIds",
                }:
                    kept[str(key)] = bounded(item, depth + 1)
            return kept
        if isinstance(value, (list, tuple)):
            return [bounded(item, depth + 1) for item in value[:remaining]]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)[:240]

    result = bounded(raw)
    return cast(dict[str, Any], result) if isinstance(result, dict) and result else None


def _assertion_property_evidence(property_key: str) -> EvidenceKind:
    normalized = property_key.casefold().strip()
    if normalized in {"appearance", "color", "shape"}:
        return EvidenceKind.VISUAL_APPEARANCE
    if normalized in {"bbox", "geometry", "inside", "position"}:
        return EvidenceKind.SPATIAL
    if normalized in {"device_state", "power", "sensor", "status", "temperature"}:
        return EvidenceKind.DEVICE_STATE
    return EvidenceKind.STRUCTURAL


def _source_assertions(
    snapshot: BrowserSnapshot,
    ttl_ms: int,
) -> tuple[SourceAssertion, ...]:
    affordances = {item.id: item for item in snapshot.affordance_model.affordances}
    assertions: list[SourceAssertion] = []
    expires_at_s = time.time() + ttl_ms / 1_000.0
    for target in snapshot.unified_affordances:
        for candidate in target.grounding_candidates:
            affordance = affordances.get(candidate.source_affordance_id)
            if affordance is None:
                continue
            parser_id = {
                GroundingSource.DOM: "dom-adapter",
                GroundingSource.ACCESSIBILITY: "accessibility-adapter",
                GroundingSource.SVG: "selective-svg-geometry",
                GroundingSource.SOM: "set-of-marks",
                GroundingSource.VISUAL: "generic-visual-region-proposer",
            }.get(candidate.source, candidate.source.value)
            values: list[tuple[str, Any, str]] = [
                ("semantic_label", affordance.label, "string"),
            ]
            for property_key in (
                "visible",
                "enabled",
                "checked",
                "focused",
                "aria_selected",
                "control_value",
                "selected_options",
            ):
                if property_key in affordance.state:
                    value = affordance.state[property_key]
                    normalized_key = (
                        "selected" if property_key == "aria_selected" else property_key
                    )
                    value_type = (
                        "boolean"
                        if isinstance(value, bool)
                        else "string"
                        if isinstance(value, str)
                        else "json"
                    )
                    values.append((normalized_key, value, value_type))
            bbox = affordance.locator.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                values.append(("position", tuple(float(item) for item in bbox), "bbox"))
            for property_key, value, value_type in values:
                assertion_id = f"assertion:{candidate.candidate_id}:{property_key}"
                assertions.append(
                    SourceAssertion(
                        assertion_id=assertion_id,
                        entity_key=target.semantic_target_id,
                        property_key=property_key,
                        value=value,
                        value_type=value_type,
                        source=candidate.source,
                        observation_epoch_id=snapshot.observation.snapshot_id,
                        environment_revision=snapshot.observation.environment_revision,
                        page_revision=snapshot.observation.page_revision,
                        parser_id=parser_id,
                        expires_at_s=expires_at_s,
                        confidence=candidate.confidence,
                        evidence_refs=candidate.evidence_refs,
                    )
                )
    return tuple(assertions)


class BrowserSession:
    """One browser context owned by one runtime run."""

    def __init__(
        self,
        page: PageDriver,
        *,
        initial_url: str = "",
        owner: Any = None,
        lease_ttl_ms: int = 2_000,
        svg_observer: SvgGeometryObserverPort | None = None,
        svg_executor: str = "visual",
        dom_executor: str = "dom",
        dom_adapter: DomAdapter | None = None,
        perception_orchestrator: PerceptionOrchestratorPort | None = None,
        visual_executor: str = "visual",
    ) -> None:
        self._page = page
        self._initial_url = initial_url
        self._owner = owner
        self._lease_ttl_ms = lease_ttl_ms
        self._dom = dom_adapter or DomAdapter()
        self._svg_observer = svg_observer or SelectiveSvgGeometryObserver()
        self._svg_executor = svg_executor
        self._dom_executor = dom_executor
        self._perception_orchestrator = perception_orchestrator
        self._visual_executor = visual_executor
        self._last_capture_profile: _CaptureProfile | None = None
        self._targeted_capture_sequence = 0

    @classmethod
    def launch(
        cls,
        url: str,
        *,
        headless: bool = True,
        action_timeout_ms: int = 8_000,
        navigation_attempts: int = 3,
        lease_ttl_ms: int = 2_000,
        dom_adapter: DomAdapter | None = None,
        perception_orchestrator: PerceptionOrchestratorPort | None = None,
        visual_executor: str = "visual",
    ) -> "BrowserSession":
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed; install affordance-runtime[web]") from exc

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(action_timeout_ms)
        last_error: Exception | None = None
        for attempt in range(max(1, navigation_attempts)):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < navigation_attempts:
                    time.sleep(0.5)
        if last_error is not None:
            context.close()
            browser.close()
            playwright.stop()
            raise last_error
        return cls(
            cast(PageDriver, page),
            initial_url=url,
            owner=(playwright, browser, context),
            lease_ttl_ms=lease_ttl_ms,
            dom_adapter=dom_adapter,
            perception_orchestrator=perception_orchestrator,
            visual_executor=visual_executor,
        )

    def open(self, url: str) -> None:
        self._page.goto(url)

    def reset(self) -> None:
        if self._initial_url:
            self._page.goto(self._initial_url)

    def locator(self, selector: str) -> Any:
        """Expose the session-owned locator boundary for DOM gesture encoding."""

        return self._page.locator(selector)

    def close(self) -> None:
        if self._owner is None:
            return
        playwright, browser, context = self._owner
        context.close()
        browser.close()
        playwright.stop()
        self._owner = None

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def url(self) -> str:
        return str(getattr(self._page, "url", "") or self._initial_url)

    @property
    def browser_version(self) -> str:
        if self._owner is None:
            return ""
        browser = self._owner[1]
        return str(getattr(browser, "version", ""))

    def capture(
        self,
        *,
        page_id: str = "page",
        ttl_ms: int | None = None,
        screenshot_path: str | None = None,
        perception_requirements: PerceptionRequirements | None = None,
        task_terms: tuple[str, ...] = (),
        task_instruction: str = "",
    ) -> BrowserSnapshot:
        """Capture one coherent, selectively multi-source observation epoch."""

        html = self._page.content()
        url = self.url
        snapshot_id = f"snap_{uuid.uuid4().hex}"
        dom_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        environment_revision = hashlib.sha256(f"{url}\0{dom_hash}".encode()).hexdigest()
        effective_ttl_ms = self._lease_ttl_ms if ttl_ms is None else ttl_ms
        model = self._dom.transduce(
            html,
            environment_revision=environment_revision,
            page_id=page_id,
            url=url,
            ttl_ms=effective_ttl_ms,
            snapshot_id=snapshot_id,
            allow_offscreen=True,
        )
        visual_required = bool(
            perception_requirements and EvidenceKind.VISUAL_APPEARANCE in perception_requirements.required_properties
        )
        spatial_required = bool(
            perception_requirements and EvidenceKind.SPATIAL in perception_requirements.required_properties
        )
        self._last_capture_profile = _CaptureProfile(
            page_id=page_id,
            ttl_ms=effective_ttl_ms,
            screenshot_path=screenshot_path,
            perception_requirements=perception_requirements,
            task_terms=task_terms,
            task_instruction=task_instruction,
        )
        screenshot_ref = ""
        screenshot_bytes = b""
        image_size: tuple[int, int] | None = None
        svg_geometry: SvgGeometryObservation | None = None
        accessibility_tree = _bounded_accessibility_tree(self._page)
        control_states: dict[str, Any] = {}
        active_control = ""
        visible_text = ""
        live_bindings = [
            {
                "key": str(
                    affordance.locator.get("backend_handle")
                    or affordance.locator.get("selector")
                    or ""
                ),
                "selector": str(affordance.locator.get("selector") or ""),
            }
            for affordance in model.affordances
            if affordance.locator.get("selector")
        ]
        serialized_bindings = json.dumps(live_bindings, separators=(",", ":"))
        evaluator = getattr(self._page, "evaluate", None)
        if evaluator is not None:
            try:
                captured = evaluator(
                    """() => Object.fromEntries("""
                    + serialized_bindings
                    + """.flatMap(({key, selector}) => { const element = document.querySelector(selector); if (!key || !element) return []; const style = getComputedStyle(element); const rect = element.getBoundingClientRect(); const visible = style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && rect.width > 0 && rect.height > 0; const selected_options = element instanceof HTMLSelectElement ? Array.from(element.selectedOptions).map((option) => String(option.value || option.textContent || '').trim()).filter(Boolean) : []; return [[key, {value: 'value' in element ? String(element.value) : '', selected_options, checked: 'checked' in element ? Boolean(element.checked) : null, aria_valuenow: element.getAttribute('aria-valuenow') || '', aria_checked: element.getAttribute('aria-checked') || '', aria_selected: element.getAttribute('aria-selected') || '', aria_expanded: element.getAttribute('aria-expanded') || '', aria_controls: element.getAttribute('aria-controls') || '', scroll_top: Number(element.scrollTop || 0), scroll_height: Number(element.scrollHeight || 0), client_height: Number(element.clientHeight || 0), visible}]]; }))"""
                )
                if isinstance(captured, dict):
                    control_states = captured
                captured_active_control = evaluator(
                    """() => { const active = document.activeElement; const match = """
                    + serialized_bindings
                    + """.find(({selector}) => document.querySelector(selector) === active); return match?.key || ''; }"""
                )
                if isinstance(captured_active_control, str):
                    active_control = captured_active_control
                captured_visible_text = evaluator("() => document.body?.innerText || ''")
                if isinstance(captured_visible_text, str):
                    visible_text = captured_visible_text[:2_000]
            except Exception:
                control_states = {}
                active_control = ""
                visible_text = ""
        if (
            (spatial_required or visual_required)
            and perception_requirements is not None
            and GroundingSource.SVG in perception_requirements.acceptable_evidence
            and callable(evaluator)
        ):
            svg_geometry = self._svg_observer.observe(
                cast(SvgPagePort, self._page),
                observation_epoch_id=snapshot_id,
                environment_revision=environment_revision,
                page_revision=model.page_revision,
                task_terms=task_terms,
                evidence_ref=screenshot_path or "",
            )
        if screenshot_path is not None or visual_required or spatial_required:
            screenshot_bytes = (
                self._page.screenshot(path=screenshot_path) if screenshot_path is not None else self._page.screenshot()
            )
            screenshot_ref = screenshot_path or f"sha256:{hashlib.sha256(screenshot_bytes).hexdigest()}"
            image_size = _image_size(screenshot_bytes, evaluator)
        if accessibility_tree is not None or (
            perception_requirements is not None and (visual_required or spatial_required)
        ):
            final_html = self._page.content()
            final_url = self.url
            final_model = self._dom.transduce(
                final_html,
                environment_revision=environment_revision,
                page_id=page_id,
                url=final_url,
                ttl_ms=effective_ttl_ms,
                snapshot_id=snapshot_id,
                allow_offscreen=True,
            )
            # Rendered SVGs may animate decorative transform/stroke attributes
            # continuously.  Raw HTML equality would make a coherent visual
            # epoch impossible even though the actionable DOM inventory and
            # page identity are stable.  Fail only when the URL or semantic
            # DOM revision changed while the extra sources were captured.
            if final_url != url or final_model.page_revision != model.page_revision:
                raise RuntimeError("coherent observation epoch drifted during multi-source capture")
        enriched_affordances = []
        grounding_candidates: list[GroundingCandidate] = []
        for affordance in model.affordances:
            control_key = str(
                affordance.locator.get("backend_handle")
                or affordance.locator.get("selector")
                or ""
            )
            state = dict(affordance.state)
            context_text = state.get("context_text")
            if control_key and context_text is not None:
                control_states.setdefault(control_key, {})["context_text"] = context_text
            control_state = control_states.get(control_key, {}) if control_key else {}
            if isinstance(control_state, dict) and isinstance(control_state.get("visible"), bool):
                if state.get("programmatic_select") is True:
                    state["rendered_visible"] = control_state["visible"]
                    state["visible"] = True
                else:
                    state["visible"] = control_state["visible"]
            if control_key:
                state["focused"] = control_key == active_control
            if isinstance(control_state, dict) and isinstance(control_state.get("checked"), bool):
                state["checked"] = control_state["checked"]
            aria_selected = control_state.get("aria_selected") if isinstance(control_state, dict) else None
            if isinstance(aria_selected, str) and aria_selected:
                state["aria_selected"] = aria_selected
            aria_expanded = control_state.get("aria_expanded") if isinstance(control_state, dict) else None
            if isinstance(aria_expanded, str) and aria_expanded in {"true", "false"}:
                state["disclosure"] = True
                state["expanded"] = aria_expanded == "true"
                state["aria_expanded"] = aria_expanded
            aria_controls = control_state.get("aria_controls") if isinstance(control_state, dict) else None
            if isinstance(aria_controls, str) and aria_controls:
                state["aria_controls"] = aria_controls
            value = control_state.get("value") if isinstance(control_state, dict) else None
            element_tag = str(state.get("element_tag") or "")
            input_type = str(state.get("input_type") or "")
            if isinstance(value, str) and (
                element_tag == "textarea" or (element_tag == "input" and input_type != "password")
            ):
                state["control_value"] = _bounded_control_value(value)
                if len(value) > 240:
                    state["control_value_prefix"] = value[:240]
                    state["control_value_suffix"] = value[-240:]
            selected_options = control_state.get("selected_options") if isinstance(control_state, dict) else None
            if element_tag == "select" and isinstance(selected_options, list):
                state["selected_options"] = [
                    str(item)[:160] for item in selected_options if isinstance(item, str) and item
                ][:20]
            enriched_affordances.append(replace(affordance, state=state))
            if element_tag == "textarea" and isinstance(control_state, dict):
                scroll_top = control_state.get("scroll_top")
                scroll_height = control_state.get("scroll_height")
                client_height = control_state.get("client_height")
                if (
                    isinstance(scroll_top, (int, float))
                    and isinstance(scroll_height, (int, float))
                    and isinstance(client_height, (int, float))
                    and scroll_height > client_height
                ):
                    scroll_id = f"{affordance.id}_scroll"
                    scroll_fingerprint = (
                        "sha256:"
                        + hashlib.sha256(f"{affordance.target_fingerprint}\0scroll-region".encode("utf-8")).hexdigest()
                    )
                    enriched_affordances.append(
                        replace(
                            affordance,
                            id=scroll_id,
                            role="scroll_region",
                            label=f"{affordance.label} scroll region".strip(),
                            action="press",
                            lease=replace(affordance.lease, target_fingerprint=scroll_fingerprint),
                            state={
                                "enabled": bool(state.get("enabled", True)),
                                "visible": bool(state.get("visible", True)),
                                "element_tag": "textarea",
                                "scrollable": True,
                                "scroll_top": scroll_top,
                                "scroll_height": scroll_height,
                                "client_height": client_height,
                            },
                        )
                    )
        if svg_geometry is not None:
            for element in svg_geometry.elements:
                source_identity = hashlib.sha256(f"{element.tag}\0{element.element_id}".encode()).hexdigest()[:12]
                semantic_target_id = f"svg_{element.tag}_{source_identity}"
                candidate = element.grounding_candidate(
                    semantic_target_id=semantic_target_id,
                    source_affordance_id=semantic_target_id,
                    source=svg_geometry.source_observation,
                    expires_at_s=time.time() + effective_ttl_ms / 1_000.0,
                    executor=self._svg_executor,
                )
                grounding_candidates.append(candidate)
                bbox = list(element.viewport_bbox_xywh)
                enriched_affordances.append(
                    Affordance(
                        id=semantic_target_id,
                        surface=Surface.SVG,
                        role=element.role or "point",
                        label=element.label or element.element_id,
                        action=element.action,
                        locator={
                            "backend_handle": element.backend_handle,
                            "bbox": bbox,
                            "coordinate_space": "viewport_pixels",
                            "svg_element_id": element.element_id,
                            "grounding_candidate_id": candidate.candidate_id,
                        },
                        lease=AffordanceLease.issue(
                            environment_revision=environment_revision,
                            ttl_ms=effective_ttl_ms,
                            provenance=["selective-svg-geometry", candidate.candidate_id],
                            confidence=candidate.confidence,
                            snapshot_id=snapshot_id,
                            page_revision=model.page_revision,
                            target_fingerprint=candidate.target_fingerprint,
                        ),
                        backend_candidates=[candidate.compatible_executor],
                        confidence=candidate.confidence,
                        state={
                            "element_tag": element.tag,
                            "svg_element_id": element.element_id,
                            "coordinate_space": "viewport_pixels",
                            "accepts_drop": element.action == "drop",
                            **({"observed_color": element.observed_color} if element.observed_color else {}),
                            **({"relative_size": element.relative_size} if element.relative_size else {}),
                            **({"observed_item_type": element.item_type} if element.item_type else {}),
                            **({"observed_item_text": element.item_text} if element.item_text else {}),
                        },
                        risk=RiskLevel.LOW,
                        evidence=[*candidate.evidence_refs],
                    )
                )
        if (
            (visual_required or spatial_required)
            and self._perception_orchestrator is not None
            and perception_requirements is not None
            and GroundingSource.VISUAL in perception_requirements.acceptable_evidence
            and image_size is not None
        ):
            regions = self._perception_orchestrator.propose_visual_regions(
                observation_epoch_id=snapshot_id,
                screenshot_path=Path(screenshot_path) if screenshot_path is not None else None,
                screenshot_bytes=screenshot_bytes,
                image_size=image_size,
                instruction=task_instruction or " ".join(task_terms),
                requirements=perception_requirements,
            )
            structured_context = bool(
                perception_requirements.required_properties.intersection(
                    {EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}
                )
            )
            gesture_terms = {item.casefold() for item in task_terms}
            visual_action = (
                "drag"
                if gesture_terms.intersection({"drag", "drop"})
                else "click"
                if structured_context and not spatial_required
                else "point_activate"
            )
            for index, region in enumerate(regions):
                visual_bbox = region.pixel_bbox(image_size)
                region_identity = hashlib.sha256(f"{region.label}\0{visual_bbox}\0{index}".encode()).hexdigest()[:12]
                affordance_id = f"visual_region_{region_identity}"
                fingerprint = "sha256:" + hashlib.sha256(f"{affordance_id}\0{visual_bbox}".encode()).hexdigest()
                enriched_affordances.append(
                    Affordance(
                        id=affordance_id,
                        surface=Surface.VISUAL,
                        role="button",
                        label=region.label or f"visual region {index + 1}",
                        action=visual_action,
                        locator={
                            "bbox": list(visual_bbox),
                            "center": [
                                visual_bbox[0] + visual_bbox[2] / 2,
                                visual_bbox[1] + visual_bbox[3] / 2,
                            ],
                            "coordinate_space": "screenshot_pixels",
                            "screenshot_ref": screenshot_ref,
                        },
                        lease=AffordanceLease.issue(
                            environment_revision=environment_revision,
                            ttl_ms=effective_ttl_ms,
                            provenance=["generic-visual-region-proposer", screenshot_ref],
                            confidence=region.confidence,
                            snapshot_id=snapshot_id,
                            page_revision=model.page_revision,
                            target_fingerprint=fingerprint,
                        ),
                        backend_candidates=[self._visual_executor],
                        confidence=region.confidence,
                        state={"visible": True, "visual_region": True},
                        risk=RiskLevel.LOW,
                        evidence=[screenshot_ref],
                    )
                )
        model = replace(
            model,
            affordances=enriched_affordances,
            kept_node_count=len(enriched_affordances),
        )
        observation = Observation(
            environment_revision=environment_revision,
            url=url,
            dom_hash=dom_hash,
            screenshot_ref=screenshot_ref,
            metadata={
                "html": html,
                "control_states": control_states,
                "active_control": active_control,
                "visible_text": visible_text,
                "environment_family": _environment_family(url),
                "observation_epoch_id": snapshot_id,
                "svg_geometry_count": len(svg_geometry.elements) if svg_geometry is not None else 0,
                "viewport_size": list(image_size) if image_size is not None else None,
                "accessibility_tree": accessibility_tree,
                "perception_requirements": (
                    {
                        "required_properties": sorted(
                            item.value for item in perception_requirements.required_properties
                        ),
                        "acceptable_sources": sorted(
                            item.value for item in perception_requirements.acceptable_evidence
                        ),
                        "preferred_sources": [item.value for item in perception_requirements.preferred_sources],
                        "observation_budget": perception_requirements.observation_budget,
                        "model_call_budget": perception_requirements.model_call_budget,
                    }
                    if perception_requirements is not None
                    else None
                ),
            },
            snapshot_id=snapshot_id,
            page_revision=model.page_revision,
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            artifact_refs=[screenshot_ref] if screenshot_ref else [],
        )
        svg_candidates = {item.candidate_id: item for item in grounding_candidates}
        descriptors: list[CandidateDescriptor] = []
        for affordance in model.affordances:
            candidate_id = str(affordance.locator.get("grounding_candidate_id") or "")
            current_candidate: GroundingCandidate | None = svg_candidates.get(candidate_id)
            if current_candidate is None and affordance.surface in {Surface.DOM, Surface.ACCESSIBILITY}:
                current_candidate = candidate_from_affordance(
                    affordance,
                    observation,
                    semantic_target_id="pending",
                    compatible_executor=self._dom_executor,
                )
            if current_candidate is None and affordance.surface == Surface.VISUAL:
                if image_size is None:
                    continue
                current_candidate = candidate_from_affordance(
                    affordance,
                    observation,
                    semantic_target_id="pending",
                    image_size=image_size,
                    compatible_executor=self._visual_executor,
                )
            if current_candidate is None:
                continue
            descriptors.append(
                CandidateDescriptor(
                    role=affordance.role,
                    label=affordance.label,
                    action=affordance.action,
                    container_context=str(affordance.state.get("container_context") or ""),
                    candidate=current_candidate,
                )
            )
        unified_affordances = SemanticEntityResolver().resolve(descriptors)
        grounding_candidates = [
            candidate for target in unified_affordances for candidate in target.grounding_candidates
        ]
        observation = replace(
            observation,
            target_fingerprints={
                **observation.target_fingerprints,
                **candidate_fingerprints(unified_affordances),
            },
        )
        source_observations = [
            SourceObservation(
                source=GroundingSource.DOM,
                parser_id="dom-adapter",
                observation_epoch_id=snapshot_id,
                environment_revision=environment_revision,
                page_revision=model.page_revision,
            )
        ]
        if accessibility_tree is not None:
            source_observations.append(
                SourceObservation(
                    source=GroundingSource.ACCESSIBILITY,
                    parser_id="browser-accessibility-tree",
                    observation_epoch_id=snapshot_id,
                    environment_revision=environment_revision,
                    page_revision=model.page_revision,
                )
            )
        if svg_geometry is not None:
            source_observations.append(svg_geometry.source_observation)
        if screenshot_ref:
            source_observations.append(
                SourceObservation(
                    source=GroundingSource.VISUAL,
                    parser_id="playwright-screenshot",
                    observation_epoch_id=snapshot_id,
                    environment_revision=environment_revision,
                    page_revision=model.page_revision,
                    artifact_refs=(screenshot_ref,),
                )
            )
        missing_evidence_requests: tuple[ActivePerceptionRequest, ...] = ()
        if (
            not unified_affordances
            and self._perception_orchestrator is not None
            and perception_requirements is not None
            and not visual_required
        ):
            missing_evidence_requests = (
                ActivePerceptionRequest(
                    entity_key="task:unresolved-target",
                    property_key="appearance",
                    requested_sources=(GroundingSource.VISUAL,),
                    reason="structured observation produced no actionable semantic target",
                    max_observations=1,
                ),
            )
        snapshot = BrowserSnapshot(
            observation=observation,
            affordance_model=model,
            source_observations=tuple(source_observations),
            svg_geometry=svg_geometry,
            grounding_candidates=tuple(grounding_candidates),
            unified_affordances=unified_affordances,
            accessibility_tree=accessibility_tree,
            perception_requirements=perception_requirements,
            active_perception_requests=missing_evidence_requests,
        )
        assertions = _source_assertions(snapshot, effective_ttl_ms)
        if not assertions:
            return snapshot
        # Imported lazily to keep the snapshot type boundary acyclic.
        from affordance_runtime.source_assertions import SourceAssertionOrchestrator

        return SourceAssertionOrchestrator().reconcile_snapshot(
            snapshot,
            assertions,
            available_sources=frozenset(item.source for item in source_observations),
            observation_budget=(
                perception_requirements.observation_budget if perception_requirements is not None else 1
            ),
        )

    def capture_targeted(
        self,
        requests: tuple[ActivePerceptionRequest, ...],
    ) -> BrowserSnapshot:
        """Reobserve requested sources in one fresh, bounded coherent epoch."""

        profile = self._last_capture_profile
        if profile is None:
            raise RuntimeError("targeted perception requires a prior capture profile")
        if not requests:
            raise ValueError("targeted perception requires at least one request")
        if any(item.max_observations != 1 for item in requests):
            raise ValueError("BrowserSession targeted perception accepts one epoch per request")
        requested_source_order = tuple(
            dict.fromkeys(source for request in requests for source in request.requested_sources)
        )
        requested_sources = frozenset(requested_source_order)
        required_properties = frozenset(_assertion_property_evidence(request.property_key) for request in requests)
        if requested_sources.intersection({GroundingSource.SOM, GroundingSource.VISUAL}):
            required_properties |= frozenset({EvidenceKind.VISUAL_APPEARANCE})
        base = profile.perception_requirements or PerceptionRequirements()
        requirements = replace(
            base,
            required_properties=base.required_properties | required_properties,
            acceptable_evidence=base.acceptable_evidence | requested_sources,
            preferred_sources=tuple(dict.fromkeys((*requested_source_order, *base.preferred_sources))),
            observation_budget=1,
            model_call_budget=base.model_call_budget,
        )
        self._targeted_capture_sequence += 1
        screenshot_path = profile.screenshot_path
        if screenshot_path:
            path = Path(screenshot_path)
            screenshot_path = str(
                path.with_name(f"{path.stem}-targeted-{self._targeted_capture_sequence}{path.suffix}")
            )
        return self.capture(
            page_id=profile.page_id,
            ttl_ms=profile.ttl_ms,
            screenshot_path=screenshot_path,
            perception_requirements=requirements,
            task_terms=profile.task_terms,
            task_instruction=profile.task_instruction,
        )

    def screenshot(self, path: str | None = None) -> bytes:
        return self._page.screenshot(path=path) if path else self._page.screenshot()

    def bounding_boxes_for_selectors(
        self,
        bindings: dict[str, str],
    ) -> dict[str, tuple[float, float, float, float]]:
        """Return current viewport geometry for opaque keys and trusted selectors."""

        locator = getattr(self._page, "locator", None)
        if not callable(locator):
            return {}
        boxes: dict[str, tuple[float, float, float, float]] = {}
        for key, selector in bindings.items():
            if not key or not selector:
                continue
            try:
                box = locator(selector).bounding_box()
            except Exception:
                continue
            if not isinstance(box, dict):
                continue
            values = (
                float(box.get("x", -1)),
                float(box.get("y", -1)),
                float(box.get("width", -1)),
                float(box.get("height", -1)),
            )
            if values[0] < 0 or values[1] < 0 or values[2] <= 0 or values[3] <= 0:
                continue
            boxes[key] = values
        return boxes

    def wait_for_load_state(self, state: str = "domcontentloaded") -> None:
        waiter = getattr(self._page, "wait_for_load_state", None)
        if waiter is not None:
            waiter(state)

    def click(self, selector: str) -> None:
        self._page.click(selector)

    def fill(self, selector: str, value: str) -> None:
        self._page.fill(selector, value)

    def select_option(self, selector: str, value: str) -> Any:
        selector_method = getattr(self._page, "select_option", None)
        if selector_method is None:
            raise RuntimeError("page does not support select_option")
        return selector_method(selector, value)

    def press(self, selector: str, key: str) -> Any:
        press_method = getattr(self._page, "press", None)
        if press_method is None:
            raise RuntimeError("page does not support press")
        return press_method(selector, key)

    def text_content(self, selector: str) -> str | None:
        getter = getattr(self._page, "text_content", None)
        return getter(selector) if getter else None

    def evaluate(self, expression: str) -> Any:
        evaluator = getattr(self._page, "evaluate", None)
        if evaluator is None:
            raise RuntimeError("page does not support JavaScript evaluation")
        return evaluator(expression)

    def download(self, selector: str, destination_dir: str) -> dict[str, str]:
        expect_download = getattr(self._page, "expect_download", None)
        if expect_download is None:
            raise RuntimeError("page does not support download events")
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        with expect_download() as download_info:
            self._page.click(selector)
        download = download_info.value
        filename = str(getattr(download, "suggested_filename", "download.bin"))
        path = destination / filename
        download.save_as(str(path))
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"path": str(path), "sha256": content_hash, "filename": filename}

    def click_xy(self, x: int, y: int) -> None:
        mouse = getattr(self._page, "mouse", None)
        if mouse is not None:
            mouse.click(x, y)
            return
        click_xy = getattr(self._page, "click_xy", None)
        if click_xy is None:
            raise RuntimeError("page does not support pointer clicks")
        click_xy(x, y)

    def move_xy(self, x: int, y: int, *, steps: int = 1) -> None:
        mouse = getattr(self._page, "mouse", None)
        if mouse is not None:
            mouse.move(x, y, steps=max(1, steps))
            return
        move_xy = getattr(self._page, "move_xy", None)
        if move_xy is None:
            raise RuntimeError("page does not support pointer movement")
        move_xy(x, y, steps=max(1, steps))

    def button_down(self, button: str = "left") -> None:
        mouse = getattr(self._page, "mouse", None)
        if mouse is not None:
            mouse.down(button=button)
            return
        button_down = getattr(self._page, "button_down", None)
        if button_down is None:
            raise RuntimeError("page does not support pointer button down")
        button_down(button)

    def button_up(self, button: str = "left") -> None:
        mouse = getattr(self._page, "mouse", None)
        if mouse is not None:
            mouse.up(button=button)
            return
        button_up = getattr(self._page, "button_up", None)
        if button_up is None:
            raise RuntimeError("page does not support pointer button up")
        button_up(button)

    def type_text(self, text: str) -> None:
        keyboard = getattr(self._page, "keyboard", None)
        if keyboard is not None:
            keyboard.type(text)
            return
        type_text = getattr(self._page, "type_text", None)
        if type_text is None:
            raise RuntimeError("page does not support keyboard typing")
        type_text(text)

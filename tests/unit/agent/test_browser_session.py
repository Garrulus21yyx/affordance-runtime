from pathlib import Path
from typing import Any

import pytest

from affordance_runtime.actions.contracts import Observation
from affordance_runtime.actions.grounding import (
    ActivePerceptionRequest,
    EvidenceKind,
    GroundingSource,
    PerceptionRequirements,
    VisualGroundingPayload,
)
from affordance_runtime.execution.context import ExecutionContextRequirementRef, issue_surface_binding
from affordance_runtime.surfaces.dom.browser_session import (
    BrowserLayerKind,
    BrowserSession,
    BrowserSnapshot,
)
from affordance_runtime.surfaces.dom.document_model import PageAffordanceModel
from affordance_runtime.surfaces.visual.grounding import VisualRegion
from affordance_runtime.surfaces.visual.proposal import GenericPerceptionOrchestrator


class FakePage:
    url = "http://fixture/settings"

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        original = cls.__dict__.get("evaluate")
        if original is None:
            return

        def evaluate(self, expression: str, *args: Any, **kwargs: Any) -> object:
            viewport = FakePage._viewport_evaluation(expression)
            return viewport if viewport is not None else original(self, expression, *args, **kwargs)

        cls.evaluate = evaluate  # type: ignore[attr-defined]

    def __init__(self) -> None:
        self.visits: list[str] = []
        self.main_frame = object()
        self._frame_handlers: list[object] = []

    def on(self, event: str, handler: object) -> None:
        if event == "framenavigated":
            self._frame_handlers.append(handler)

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self.visits.append(url)

    def content(self) -> str:
        return "<main><button id='save'>Save</button></main>"

    def click(self, selector: str) -> None:
        pass

    def fill(self, selector: str, value: str) -> None:
        pass

    def screenshot(self, **kwargs: Any) -> bytes:
        return b"png"

    def evaluate(self, expression: str, *args: Any, **kwargs: Any) -> object:
        del args, kwargs
        if "getScreenCTM" in expression:
            return {"viewport": [800, 600], "elements": []}
        return self._viewport_evaluation(expression) or {}

    @staticmethod
    def _viewport_evaluation(expression: str) -> object | None:
        if "width: window.innerWidth" in expression:
            return {
                "width": 800,
                "height": 600,
                "scrollX": 0,
                "scrollY": 0,
                "dpr": 1,
                "zoom": 1,
                "orientation": "landscape-primary",
            }
        if expression.strip() == "() => [window.innerWidth, window.innerHeight]":
            return [800, 600]
        return None


def test_browser_session_captures_observation_and_affordances() -> None:
    snapshot = BrowserSession(FakePage()).capture(page_id="settings")

    assert snapshot.observation.url == "http://fixture/settings"
    assert snapshot.observation.metadata["environment_family"] == "web:http://fixture"
    assert snapshot.observation.dom_hash
    assert snapshot.affordance_model.environment_revision == snapshot.observation.environment_revision
    assert snapshot.affordance_model.affordances[0].label == "Save"
    assert len(snapshot.unified_affordances) == 1
    assert snapshot.grounding_candidates[0].is_current(snapshot.observation)


def test_rendered_dom_projection_excludes_css_hidden_controls_only_when_enabled() -> None:
    class FilteredPage(FakePage):
        def content(self) -> str:
            return "<main><button id='keep'>Continue</button><button id='hidden-ad'>Sponsored action</button></main>"

        def evaluate(self, expression: str, *args: Any, **kwargs: Any) -> object:
            del args, kwargs
            if "runtimeRenderedDomProjection" in expression:
                return "<html><body><main><button id='keep'>Continue</button></main></body></html>"
            return super().evaluate(expression)

    unfiltered = BrowserSession(FilteredPage()).capture(page_id="fixture")
    filtered_session = BrowserSession(FilteredPage(), rendered_dom_only=True)
    filtered = filtered_session.capture(page_id="fixture")

    assert [item.label for item in unfiltered.affordance_model.affordances] == [
        "Continue",
        "Sponsored action",
    ]
    assert [item.label for item in filtered.affordance_model.affordances] == ["Continue"]
    assert "Sponsored action" not in str(filtered.observation.metadata["html"])
    target = filtered.affordance_model.affordances[0]
    assert filtered_session.probe_dom_target(target.id) == (
        filtered.affordance_model.page_revision,
        target.target_fingerprint,
    )


def test_browser_environment_family_uses_origin_without_url_credentials_or_path() -> None:
    page = FakePage()
    page.url = "https://user:secret@example.test:8443/private?token=hidden"

    snapshot = BrowserSession(page).capture(page_id="settings")

    assert snapshot.observation.metadata["environment_family"] == "web:https://example.test:8443"


def test_browser_session_bundles_browser_accessibility_tree_in_same_epoch() -> None:
    class AccessibilityApi:
        def snapshot(self, *, interesting_only: bool) -> dict[str, object]:
            assert interesting_only is False
            return {
                "role": "WebArea",
                "name": "Settings",
                "vendor_internal_id": "must-not-cross-runtime-boundary",
                "children": [{"role": "button", "name": "Save"}],
            }

    page = FakePage()
    page.accessibility = AccessibilityApi()  # type: ignore[attr-defined]

    snapshot = BrowserSession(page).capture(page_id="settings")

    assert snapshot.accessibility_tree == {
        "role": "WebArea",
        "name": "Settings",
        "children": [{"role": "button", "name": "Save"}],
    }
    accessibility = next(item for item in snapshot.source_observations if item.source == GroundingSource.ACCESSIBILITY)
    assert accessibility.observation_epoch_id == snapshot.observation.snapshot_id
    assert snapshot.observation.metadata["accessibility_tree"] == snapshot.accessibility_tree


def test_browser_session_observes_a_visible_geometric_overlay_without_calling_a_model() -> None:
    class OverlayPage(FakePage):
        def evaluate(self, expression: str, *args: Any, **kwargs: Any) -> object:
            del args, kwargs
            if "runtimeLayerProbe" in expression:
                return [
                    {
                        "layer_id": "layer:0",
                        "kind": "geometric_overlay",
                        "role": "region",
                        "label": "Scan with the app to sign in",
                        "text": "Scan with the app to sign in",
                        "modal": False,
                        "bbox": [120, 80, 560, 420],
                        "member_keys": ["#save"],
                    }
                ]
            return super().evaluate(expression)

    snapshot = BrowserSession(OverlayPage()).capture(page_id="settings")

    assert len(snapshot.layers) == 1
    layer = snapshot.layers[0]
    assert layer.kind is BrowserLayerKind.GEOMETRIC_OVERLAY
    assert layer.label == "Scan with the app to sign in"
    assert layer.member_keys == ("#save",)


def test_browser_snapshot_accessibility_tree_is_deeply_immutable_from_source_payload() -> None:
    accessibility_tree = {
        "role": "WebArea",
        "children": [{"role": "button", "name": "Save"}],
    }
    snapshot = BrowserSnapshot(
        observation=Observation(environment_revision="env:1", snapshot_id="snap:1"),
        affordance_model=PageAffordanceModel(
            page_id="settings",
            url="http://fixture/settings",
            environment_revision="env:1",
            snapshot_id="snap:1",
            page_revision="page:1",
            affordances=[],
            raw_node_count=0,
            kept_node_count=0,
        ),
        accessibility_tree=accessibility_tree,
    )

    accessibility_tree["children"][0]["name"] = "Polluted"

    assert snapshot.accessibility_tree is not None
    assert snapshot.accessibility_tree["children"][0]["name"] == "Save"
    with pytest.raises(TypeError):
        snapshot.accessibility_tree["children"][0]["name"] = "Polluted"


def test_browser_session_keeps_same_label_checkbox_siblings_as_ordered_targets() -> None:
    class CheckboxPage(FakePage):
        def content(self) -> str:
            return (
                '<input id="first" type="checkbox">'
                '<input id="second" type="checkbox">'
                '<input id="third" type="checkbox">'
            )

    snapshot = BrowserSession(CheckboxPage()).capture(page_id="form")

    assert len(snapshot.unified_affordances) == 3
    assert [target.grounding_candidates[0].source_affordance_id for target in snapshot.unified_affordances] == [
        "dom_input_1",
        "dom_input_2",
        "dom_input_3",
    ]


def test_browser_session_uses_configured_default_affordance_lease() -> None:
    snapshot = BrowserSession(FakePage(), lease_ttl_ms=120_000).capture(page_id="settings")

    assert snapshot.affordance_model.affordances[0].lease.ttl_ms == 120_000


def test_live_surface_probe_rejects_dom_drift_after_capture() -> None:
    class MutablePage(FakePage):
        html = "<main><button id='save'>Save</button></main>"

        def __init__(self) -> None:
            super().__init__()

        def content(self) -> str:
            return self.html

        def evaluate(self, expression: str, argument: object = None) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Save"
            return {}

    page = MutablePage()
    session = BrowserSession(page)
    snapshot = session.capture(page_id="settings")
    expected = issue_surface_binding(
        ExecutionContextRequirementRef.local_public(),
        run_id="run:1",
        session_generation="session:1",
        window_id="window:1",
        tab_id="tab:1",
        frame_id="frame:top",
        document_generation=str(snapshot.observation.metadata["document_generation"]),
        focus_generation="focus:default",
    )
    assert session.surface_binding_is_current(expected)
    page.html = "<main><button id='save'>Save changed</button></main>"
    assert not session.surface_binding_is_current(expected)


def test_live_surface_probe_rejects_same_content_document_realm_reload() -> None:
    class ReloadablePage(FakePage):
        def evaluate(self, expression: str, argument: object = None) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Save"
            return {}

        def reload_same_content(self) -> None:
            for handler in self._frame_handlers:
                handler(self.main_frame)  # type: ignore[operator]

    page = ReloadablePage()
    session = BrowserSession(page)
    snapshot = session.capture(page_id="settings")
    expected = issue_surface_binding(
        ExecutionContextRequirementRef.local_public(),
        run_id="run:1",
        session_generation="session:1",
        window_id="window:1",
        tab_id="tab:1",
        frame_id="frame:top",
        document_generation=str(snapshot.observation.metadata["document_generation"]),
        focus_generation="focus:default",
    )

    assert session.surface_binding_is_current(expected)
    page.reload_same_content()
    assert not session.surface_binding_is_current(expected)


def test_browser_session_reset_uses_initial_url() -> None:
    page = FakePage()
    session = BrowserSession(page, initial_url="http://fixture/start")
    session.open("http://fixture/other")
    session.reset()

    assert page.visits == ["http://fixture/other", "http://fixture/start"]


def test_browser_session_maps_bounded_gesture_to_playwright_mouse() -> None:
    class Mouse:
        def __init__(self) -> None:
            self.actions: list[tuple[object, ...]] = []

        def move(self, x: int, y: int, *, steps: int) -> None:
            self.actions.append(("move", x, y, steps))

        def down(self, *, button: str) -> None:
            self.actions.append(("down", button))

        def up(self, *, button: str) -> None:
            self.actions.append(("up", button))

    page = FakePage()
    page.mouse = Mouse()  # type: ignore[attr-defined]
    session = BrowserSession(page)

    session.move_xy(10, 20, steps=1)
    session.button_down("left")
    session.move_xy(100, 120, steps=8)
    session.button_up("left")

    assert page.mouse.actions == [  # type: ignore[attr-defined]
        ("move", 10, 20, 1),
        ("down", "left"),
        ("move", 100, 120, 8),
        ("up", "left"),
    ]


def test_browser_session_preserves_exact_non_sensitive_control_values() -> None:
    class EvaluatingPage(FakePage):
        def content(self) -> str:
            return "<textarea id='source'>Trim-sensitive text </textarea><input id='target' type='text'>"

        def evaluate(self, expression: str) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Copy this exactly: Trim-sensitive text "
            return {
                "#source": {"value": "Trim-sensitive text ", "checked": None},
                "#target": {"value": "", "checked": None},
            }

    snapshot = BrowserSession(EvaluatingPage()).capture(page_id="copy")
    states = {item.state["element_tag"]: item.state for item in snapshot.affordance_model.affordances}

    assert states["textarea"]["control_value"] == "Trim-sensitive text "
    assert states["input"]["control_value"] == ""
    assertions = {
        (item.property_key, item.value) for item in snapshot.source_assertions if item.source == GroundingSource.DOM
    }
    assert ("control_value", "Trim-sensitive text ") in assertions
    assert ("control_value", "") in assertions
    assert ("focused", False) in assertions
    assert snapshot.observation.metadata["visible_text"] == "Copy this exactly: Trim-sensitive text "
    assert snapshot.observation.metadata["visible_text_truncated"] is False


def test_browser_session_preserves_current_multi_select_values() -> None:
    class EvaluatingPage(FakePage):
        def content(self) -> str:
            return "<select id='items' multiple><option>Ertha</option><option>Aurel</option></select>"

        def evaluate(self, expression: str) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Ertha Aurel"
            return {
                "#items": {
                    "value": "Ertha",
                    "selected_options": ["Ertha"],
                    "visible": True,
                }
            }

    snapshot = BrowserSession(EvaluatingPage()).capture(page_id="multi-select")
    select = next(item for item in snapshot.affordance_model.affordances if item.action == "select")

    assert select.state["selected_options"] == ["Ertha"]


def test_browser_session_uses_runtime_visibility_for_current_affordances() -> None:
    class EvaluatingPage(FakePage):
        def content(self) -> str:
            return "<button id='open'>Open</button><input id='hidden' type='text'>"

        def evaluate(self, expression: str) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Open"
            return {
                "#open": {"value": "", "visible": True},
                "#hidden": {"value": "", "visible": False},
            }

    snapshot = BrowserSession(EvaluatingPage()).capture(page_id="visibility")
    states = {item.locator["selector"]: item.state for item in snapshot.affordance_model.affordances}

    assert states["#open"]["visible"] is True
    assert states["#hidden"]["visible"] is False


def test_browser_session_refreshes_live_disclosure_state() -> None:
    class DisclosurePage(FakePage):
        def content(self) -> str:
            return '<h3 id="section" role="tab" aria-expanded="false" aria-controls="panel">Section</h3>'

        def evaluate(self, expression: str) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Section"
            return {
                "#section": {
                    "value": "",
                    "checked": None,
                    "aria_expanded": "true",
                    "aria_controls": "panel",
                    "visible": True,
                }
            }

    snapshot = BrowserSession(DisclosurePage()).capture(page_id="disclosure")
    affordance = snapshot.affordance_model.affordances[0]

    assert affordance.action == "click"
    assert affordance.state["disclosure"] is True
    assert affordance.state["expanded"] is True
    assert affordance.state["aria_expanded"] == "true"
    assert affordance.state["aria_controls"] == "panel"
    assert snapshot.observation.metadata["control_states"]["#section"]["aria_expanded"] == "true"


def test_browser_session_derives_scroll_region_with_live_control_state() -> None:
    class ScrollPage(FakePage):
        def content(self) -> str:
            return "<textarea id='source'>Long text</textarea><button id='submit'>Submit</button>"

        def evaluate(self, expression: str) -> object:
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Long text\nSubmit"
            return {
                "#source": {
                    "value": "Long text",
                    "checked": None,
                    "scroll_top": 48,
                    "scroll_height": 300,
                    "client_height": 100,
                },
                "#submit": {
                    "value": "",
                    "checked": None,
                    "scroll_top": 0,
                    "scroll_height": 20,
                    "client_height": 20,
                },
            }

    snapshot = BrowserSession(ScrollPage()).capture(page_id="scroll")
    scroll_region = next(item for item in snapshot.affordance_model.affordances if item.role == "scroll_region")

    assert scroll_region.id == "dom_textarea_1_scroll"
    assert scroll_region.action == "press"
    assert scroll_region.locator["selector"] == "#source"
    assert scroll_region.state == {
        "enabled": True,
        "visible": True,
        "element_tag": "textarea",
        "scrollable": True,
        "scroll_top": 48,
        "scroll_height": 300,
        "client_height": 100,
    }
    assert snapshot.observation.target_fingerprints[scroll_region.id] == scroll_region.target_fingerprint
    assert snapshot.affordance_model.kept_node_count == 3


def test_browser_session_captures_svg_and_screenshot_in_one_epoch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class SpatialPage(FakePage):
        def content(self) -> str:
            return "<main><svg viewBox='0 0 100 100'><circle id='target' aria-label='Blue point'/></svg></main>"

        def evaluate(self, expression: str, arg: Any = None) -> object:
            if "getScreenCTM" in expression:
                assert arg == {
                    "task_terms": ["blue", "point"],
                    "marker_attribute": "",
                    "marker_value": "1",
                    "backend_handle_attribute": "",
                }
                return {
                    "viewport": [800, 600],
                    "elements": [
                        {
                            "element_id": "target",
                            "tag": "circle",
                            "label": "Blue point",
                            "role": "button",
                            "action": "point_activate",
                            "backend_handle": "",
                            "view_box": [0, 0, 100, 100],
                            "geometry_bbox": [10, 20, 4, 4],
                            "viewport_bbox": [120, 240, 8, 8],
                            "transform": [2, 0, 0, 2, 100, 200],
                        }
                    ],
                }
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "Blue point"
            return {}

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.SVG, GroundingSource.VISUAL}),
    )
    snapshot = BrowserSession(SpatialPage()).capture(
        page_id="spatial",
        screenshot_path=str(tmp_path / "spatial.png"),
        perception_requirements=requirements,
        task_terms=("blue", "point"),
    )

    assert snapshot.svg_geometry is not None
    assert snapshot.svg_geometry.elements[0].element_id == "target"
    point = next(item for item in snapshot.affordance_model.affordances if item.action == "point_activate")
    assert point.label == "Blue point"
    assert point.locator["bbox"] == [120.0, 240.0, 8.0, 8.0]
    assert point.state["spatial_evidence"] == "calibrated_current_geometry"
    assert point.id in snapshot.observation.target_fingerprints
    assert snapshot.grounding_candidates[0].source_affordance_id == point.id
    assert snapshot.grounding_candidates[0].semantic_target_id.startswith("semantic:blue-point:")
    assert point.locator["grounding_candidate_id"] == "svg:target"
    assert {item.source for item in snapshot.source_observations} == {
        GroundingSource.DOM,
        GroundingSource.SVG,
        GroundingSource.VISUAL,
    }
    assert {item.observation_epoch_id for item in snapshot.source_observations} == {snapshot.observation.snapshot_id}
    svg_target = next(item for item in snapshot.unified_affordances if item.label == "Blue point")
    assert svg_target.grounding_candidates[0].is_current(snapshot.observation)


def test_browser_session_collects_svg_for_visual_only_requirement(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class VisualSvgPage(FakePage):
        def content(self) -> str:
            return "<main><svg><text>8</text></svg></main>"

        def evaluate(self, expression: str, arg: Any = None) -> object:
            if "getScreenCTM" in expression:
                assert arg == {
                    "task_terms": ["shape", "8"],
                    "marker_attribute": "",
                    "marker_value": "1",
                    "backend_handle_attribute": "",
                }
                return {
                    "viewport": [800, 600],
                    "elements": [
                        {
                            "element_id": "text-1",
                            "tag": "text",
                            "label": "8",
                            "role": "",
                            "action": "point_activate",
                            "backend_handle": "",
                            "view_box": [0, 0, 100, 100],
                            "geometry_bbox": [10, 20, 4, 4],
                            "viewport_bbox": [120, 240, 8, 8],
                            "transform": [2, 0, 0, 2, 100, 200],
                        }
                    ],
                }
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return "8"
            return {}

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
        acceptable_evidence=frozenset({GroundingSource.SVG, GroundingSource.VISUAL}),
    )
    snapshot = BrowserSession(VisualSvgPage()).capture(
        page_id="visual-svg",
        screenshot_path=str(tmp_path / "visual-svg.png"),
        perception_requirements=requirements,
        task_terms=("shape", "8"),
    )

    assert snapshot.svg_geometry is not None
    assert snapshot.svg_geometry.elements[0].element_id == "text-1"
    assert any(item.action == "point_activate" and item.label == "8" for item in snapshot.affordance_model.affordances)


def test_browser_session_allows_nonsemantic_svg_animation_within_epoch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class AnimatedSvgPage(FakePage):
        captures = 0

        def content(self) -> str:
            self.captures += 1
            return (
                "<main><button id='submit'>Submit</button>"
                f"<svg><text transform='rotate({self.captures})'>decoration</text></svg></main>"
            )

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.SVG}),
    )

    snapshot = BrowserSession(AnimatedSvgPage()).capture(
        page_id="animated",
        screenshot_path=str(tmp_path / "animated.png"),
        perception_requirements=requirements,
    )

    assert snapshot.affordance_model.affordances[0].label == "Submit"


def test_browser_session_rejects_semantic_dom_drift_within_epoch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class DriftingControlPage(FakePage):
        captures = 0

        def content(self) -> str:
            self.captures += 1
            label = "Save" if self.captures == 1 else "Delete"
            return f"<main><button id='action'>{label}</button></main>"

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.SVG}),
    )

    with pytest.raises(RuntimeError, match="coherent observation epoch drifted"):
        BrowserSession(DriftingControlPage()).capture(
            page_id="drifting",
            screenshot_path=str(tmp_path / "drifting.png"),
            perception_requirements=requirements,
        )


def test_browser_session_retries_transient_affordance_state_drift_within_epoch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class StabilizingControlPage(FakePage):
        captures = 0

        def content(self) -> str:
            self.captures += 1
            disabled = " disabled" if self.captures == 1 else ""
            return f"<main><button id='action'{disabled}>Save</button></main>"

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM}),
    )

    snapshot = BrowserSession(StabilizingControlPage()).capture(
        page_id="stabilizing",
        screenshot_path=str(tmp_path / "stabilizing.png"),
        perception_requirements=requirements,
    )

    assert snapshot.affordance_model.affordances[0].label == "Save"
    assert snapshot.affordance_model.affordances[0].state["enabled"] is True


def test_generic_visual_orchestrator_produces_current_candidate_and_assertions(
    tmp_path: Path,
) -> None:
    class VisualPage(FakePage):
        def content(self) -> str:
            return "<main><canvas aria-label='workspace'></canvas></main>"

        def evaluate(self, expression: str, arg: Any = None) -> object:
            del arg
            if "innerWidth" in expression:
                return [800, 600]
            if "document.activeElement" in expression:
                return ""
            if "innerText" in expression:
                return ""
            return {}

        def screenshot(self, **kwargs: Any) -> bytes:
            payload = b"visual-image"
            path = kwargs.get("path")
            if path:
                Path(path).write_bytes(payload)
            return payload

    class RegionProposer:
        provider = "fixture"
        model = "deterministic-regions"
        prompt_version = "test-v1"
        calls = 0

        def propose(self, request):  # type: ignore[no-untyped-def]
            self.calls += 1
            assert request.instruction == "Activate the blue visual icon"
            assert request.image_size == (800, 600)
            return [VisualRegion((0.25, 0.25, 0.1, 0.1), "Blue icon", 0.9)]

    proposer = RegionProposer()
    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.VISUAL}),
        model_call_budget=1,
    )
    snapshot = BrowserSession(
        VisualPage(),
        perception_orchestrator=GenericPerceptionOrchestrator(proposer),
    ).capture(
        screenshot_path=str(tmp_path / "visual.png"),
        perception_requirements=requirements,
        task_instruction="Activate the blue visual icon",
    )

    assert proposer.calls == 1
    candidate = next(item for item in snapshot.grounding_candidates if item.source == GroundingSource.VISUAL)
    assert candidate.is_current(snapshot.observation)
    assert candidate.compatible_executor == "visual"
    assert isinstance(candidate.payload, VisualGroundingPayload)
    assert candidate.payload.bbox_xywh == (200.0, 150.0, 80.0, 60.0)
    assert {item.observation_epoch_id for item in snapshot.source_observations} == {snapshot.observation.snapshot_id}
    assert any(
        item.entity_key == candidate.semantic_target_id
        and item.property_key == "position"
        and item.source == GroundingSource.VISUAL
        for item in snapshot.source_assertions
    )


def test_targeted_perception_issues_a_fresh_epoch_and_visual_candidate(
    tmp_path: Path,
) -> None:
    class TargetedPage(FakePage):
        def content(self) -> str:
            return "<main><canvas></canvas></main>"

        def evaluate(self, expression: str, arg: Any = None) -> object:
            del arg
            if "innerWidth" in expression:
                return [640, 480]
            if "document.activeElement" in expression or "innerText" in expression:
                return ""
            return {}

        def screenshot(self, **kwargs: Any) -> bytes:
            payload = b"targeted-visual"
            path = kwargs.get("path")
            if path:
                Path(path).write_bytes(payload)
            return payload

    class Proposer:
        provider = "fixture"
        model = "targeted-regions"
        prompt_version = "test-v1"

        def __init__(self) -> None:
            self.calls = 0

        def propose(self, request):  # type: ignore[no-untyped-def]
            self.calls += 1
            return [VisualRegion((0.2, 0.3, 0.1, 0.1), "Target", 0.9)]

    proposer = Proposer()
    session = BrowserSession(
        TargetedPage(),
        perception_orchestrator=GenericPerceptionOrchestrator(proposer),
    )
    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.VISUAL}),
        model_call_budget=1,
    )
    first = session.capture(
        screenshot_path=str(tmp_path / "epoch.png"),
        perception_requirements=requirements,
        task_instruction="Locate the target",
    )
    second = session.capture_targeted(
        (
            ActivePerceptionRequest(
                first.unified_affordances[0].semantic_target_id,
                "position",
                (GroundingSource.VISUAL,),
                "confirm current position",
            ),
        )
    )

    assert proposer.calls == 2
    assert second.observation.snapshot_id != first.observation.snapshot_id
    assert second.observation.screenshot_ref != first.observation.screenshot_ref
    assert "targeted-1" in second.observation.screenshot_ref
    assert second.grounding_candidates[0].is_current(second.observation)
    assert not first.grounding_candidates[0].is_current(second.observation)


def test_targeted_visual_capture_does_not_expand_zero_model_authority(tmp_path: Path) -> None:
    class ZeroBudgetPage(FakePage):
        def content(self) -> str:
            return "<main><canvas></canvas></main>"

        def evaluate(self, expression: str, arg: Any = None) -> object:
            del arg
            if "innerWidth" in expression:
                return [640, 480]
            if "document.activeElement" in expression or "innerText" in expression:
                return ""
            return {}

        def screenshot(self, **kwargs: Any) -> bytes:
            payload = b"transport-only"
            path = kwargs.get("path")
            if path:
                Path(path).write_bytes(payload)
            return payload

    class ForbiddenProposer:
        provider = "fixture"
        model = "must-not-run"
        prompt_version = "test-v1"
        calls = 0

        def propose(self, request):  # type: ignore[no-untyped-def]
            del request
            self.calls += 1
            raise AssertionError("zero model budget must not invoke visual proposal")

    proposer = ForbiddenProposer()
    session = BrowserSession(
        ZeroBudgetPage(),
        perception_orchestrator=GenericPerceptionOrchestrator(proposer),
    )
    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
        acceptable_evidence=frozenset({GroundingSource.VISUAL}),
        preferred_sources=(GroundingSource.VISUAL,),
        model_call_budget=0,
        cost_budget=0.0,
    )
    first = session.capture(
        screenshot_path=str(tmp_path / "zero-budget.png"),
        perception_requirements=requirements,
        task_instruction="Inspect the visual target",
    )
    second = session.capture_targeted(
        (
            ActivePerceptionRequest(
                "task:unresolved-target",
                "appearance",
                (GroundingSource.VISUAL,),
                "visual evidence remains missing",
            ),
        )
    )

    assert proposer.calls == 0
    assert first.grounding_candidates == second.grounding_candidates == ()
    assert any(item.source == GroundingSource.VISUAL for item in second.source_observations)
    assert second.perception_requirements is not None
    assert second.perception_requirements.model_call_budget == 0


def test_svg_visual_position_conflict_requests_reobservation_and_blocks_target(
    tmp_path: Path,
) -> None:
    class ConflictPage(FakePage):
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
                            "backend_handle": "",
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

        def screenshot(self, **kwargs: Any) -> bytes:
            payload = b"conflicting-sources"
            path = kwargs.get("path")
            if path:
                Path(path).write_bytes(payload)
            return payload

    class ConflictProposer:
        provider = "fixture"
        model = "conflicting-regions"
        prompt_version = "test-v1"

        def propose(self, request):  # type: ignore[no-untyped-def]
            return [VisualRegion((0.6, 0.6, 0.1, 0.1), "Target", 0.9)]

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.SVG, GroundingSource.VISUAL}),
        observation_budget=1,
        model_call_budget=1,
    )
    session = BrowserSession(
        ConflictPage(),
        perception_orchestrator=GenericPerceptionOrchestrator(ConflictProposer()),
    )
    first = session.capture(
        screenshot_path=str(tmp_path / "conflict.png"),
        perception_requirements=requirements,
        task_terms=("target",),
        task_instruction="Activate the target",
    )

    target = next(item for item in first.unified_affordances if item.label == "Target")
    assert set(candidate.source for candidate in target.grounding_candidates) == {
        GroundingSource.SVG,
        GroundingSource.VISUAL,
    }
    assert "position:reobserve" in target.unresolved_conflicts
    assert first.active_perception_requests[0].property_key == "position"

    second = session.capture_targeted(first.active_perception_requests)

    assert second.observation.snapshot_id != first.observation.snapshot_id
    second_target = next(item for item in second.unified_affordances if item.label == "Target")
    assert "position:reobserve" in second_target.unresolved_conflicts
    assert second.active_perception_requests

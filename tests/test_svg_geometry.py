from dataclasses import replace
from typing import Any

import pytest

from affordance_runtime.actions.grounding import EvidenceKind, GroundingSource, SvgGroundingPayload
from affordance_runtime.surfaces.visual.svg_geometry import SelectiveSvgGeometryObserver, SvgAuthoredExtension


def _observer() -> SelectiveSvgGeometryObserver:
    return SelectiveSvgGeometryObserver(
        authored_extension=SvgAuthoredExtension(
            marker_attribute="data-runtime-interactive",
            backend_handle_attribute="data-runtime-handle",
        )
    )


class FakeSvgPage:
    def evaluate(self, expression: str, arg: Any = None) -> object:
        assert "getScreenCTM" in expression
        assert arg == {
            "task_terms": ["blue", "point"],
            "marker_attribute": "data-runtime-interactive",
            "marker_value": "1",
            "backend_handle_attribute": "data-runtime-handle",
        }
        return {
            "viewport": [800, 600],
            "elements": [
                {
                    "element_id": "blue-point",
                    "tag": "circle",
                    "label": "Blue point",
                    "role": "button",
                    "action": "point_activate",
                    "backend_handle": "42",
                    "view_box": [0, 0, 100, 100],
                    "geometry_bbox": [10, 20, 4, 4],
                    "viewport_bbox": [120, 240, 8, 8],
                    "transform": [2, 0, 0, 2, 100, 200],
                }
            ],
        }


def test_selective_svg_observation_and_candidate_share_one_epoch() -> None:
    observation = _observer().observe(
        FakeSvgPage(),
        observation_epoch_id="snap-1",
        environment_revision="rev-1",
        page_revision="page-1",
        task_terms=("blue", "point"),
        evidence_ref="screen.png",
    )
    candidate = observation.elements[0].grounding_candidate(
        semantic_target_id="blue-point",
        source=observation.source_observation,
        expires_at_s=100.0,
        executor="visual",
    )

    assert observation.source_observation.source == GroundingSource.SVG
    assert candidate.observation_epoch_id == "snap-1"
    assert isinstance(candidate.payload, SvgGroundingPayload)
    assert candidate.payload.viewport_center == (124, 244)
    assert candidate.payload.transform.apply((12, 22)) == (124, 244)
    assert candidate.evidence_kinds == frozenset(
        {EvidenceKind.STRUCTURAL, EvidenceKind.SPATIAL, EvidenceKind.VISUAL_APPEARANCE}
    )
    changed_semantics = replace(observation.elements[0], item_text="2").grounding_candidate(
        semantic_target_id="blue-point",
        source=observation.source_observation,
        expires_at_s=100.0,
        executor="visual",
    )
    assert changed_semantics.target_fingerprint != candidate.target_fingerprint

    next_observation = _observer().observe(
        FakeSvgPage(),
        observation_epoch_id="snap-2",
        environment_revision="rev-1",
        page_revision="page-1",
        task_terms=("blue", "point"),
        evidence_ref="screen-2.png",
    )
    next_candidate = next_observation.elements[0].grounding_candidate(
        semantic_target_id="blue-point",
        source=next_observation.source_observation,
        expires_at_s=200.0,
        executor="visual",
    )
    assert next_candidate.observation_epoch_id == "snap-2"
    assert next_candidate.target_fingerprint == candidate.target_fingerprint


def test_svg_observer_rejects_non_finite_or_empty_geometry() -> None:
    class InvalidPage(FakeSvgPage):
        def evaluate(self, expression: str, arg: Any = None) -> object:
            raw = super().evaluate(expression, arg)
            assert isinstance(raw, dict)
            raw["elements"][0]["viewport_bbox"] = [0, 0, 0, 8]
            return raw

    with pytest.raises(ValueError, match="dimensions must be positive"):
        _observer().observe(
            InvalidPage(),
            observation_epoch_id="snap-1",
            environment_revision="rev-1",
            page_revision="page-1",
            task_terms=("blue", "point"),
        )


def test_svg_drop_candidate_exposes_semantic_drag_while_retaining_drop_direction() -> None:
    class DropPage:
        def evaluate(self, expression: str, arg: Any = None) -> object:
            assert "getScreenCTM" in expression
            assert arg == {
                "task_terms": ["drag", "right"],
                "marker_attribute": "data-runtime-interactive",
                "marker_value": "1",
                "backend_handle_attribute": "data-runtime-handle",
            }
            return {
                "viewport": [800, 600],
                "elements": [
                    {
                        "element_id": "shape-container-2",
                        "tag": "rect",
                        "label": "right box",
                        "role": "drop_target",
                        "action": "drop",
                        "backend_handle": "",
                        "view_box": [0, 0, 160, 160],
                        "geometry_bbox": [84, 5, 70, 50],
                        "viewport_bbox": [92, 48, 70, 50],
                        "transform": [1, 0, 0, 1, 8, 43],
                    }
                ],
            }

    observation = _observer().observe(
        DropPage(),
        observation_epoch_id="snap-1",
        environment_revision="rev-1",
        page_revision="page-1",
        task_terms=("drag", "right"),
    )
    element = observation.elements[0]
    candidate = element.grounding_candidate(
        semantic_target_id="semantic:right-box",
        source_affordance_id="svg_rect_1",
        source=observation.source_observation,
        expires_at_s=9999999999.0,
        executor="visual",
    )

    assert element.action == "drop"
    assert candidate.supported_actions == frozenset({"drag"})

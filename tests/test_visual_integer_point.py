from dataclasses import replace

import pytest

from affordance_runtime.surfaces.visual.contracts import VisualRegionBinding, VisualViewport
from affordance_runtime.surfaces.visual.execution import integer_click_point


def _binding(
    bbox: tuple[float, float, float, float],
    point: tuple[float, float],
    viewport: tuple[int, int] = (100, 100),
) -> VisualRegionBinding:
    return VisualRegionBinding(
        "visual:1",
        "sha256:image",
        "sha256:image",
        viewport[0],
        viewport[1],
        VisualViewport(viewport[0], viewport[1], 0, 0, 1, 1, "landscape"),
        "region:0",
        "sha256:region",
        bbox,
        point,
        1.0,
        "Target",
        "button",
        "point_activate",
    )


@pytest.mark.parametrize(
    ("binding", "expected"),
    [
        (_binding((10, 10, 20, 20), (20, 20)), (20, 20)),
        (_binding((10, 10, 20, 20), (30, 30)), (29, 29)),
        (_binding((99, 99, 1, 1), (99.6, 99.6)), (99, 99)),
        (_binding((0, 0, 1, 1), (0.5, 0.5)), (0, 0)),
    ],
)
def test_integer_click_point_is_inside_region_and_viewport(binding, expected) -> None:
    assert integer_click_point(binding) == expected


@pytest.mark.parametrize(
    "binding",
    [
        _binding((99.6, 10, 0.4, 1), (99.8, 10.5)),
        _binding((10, 99.6, 1, 0.4), (10.5, 99.8)),
        _binding((100, 10, 1, 1), (100.5, 10.5)),
    ],
)
def test_integer_click_point_rejects_regions_without_valid_pixel(binding) -> None:
    with pytest.raises(ValueError, match="integer click point"):
        integer_click_point(binding)


def test_integer_click_point_revalidates_mutated_rounding_result() -> None:
    binding = _binding((10, 10, 1, 1), (10.5, 10.5))
    assert integer_click_point(replace(binding, action_point_xy=(11, 11))) == (10, 10)

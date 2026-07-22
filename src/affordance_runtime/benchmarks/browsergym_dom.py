"""BrowserGym DOM annotations normalized through the generic extension port."""

from affordance_runtime.adapters.dom import (
    AuthoredInteractiveExtension,
    DomAdapter,
)
from affordance_runtime.svg_geometry import (
    SelectiveSvgGeometryObserver,
    SvgAuthoredExtension,
)

BROWSERGYM_DOM_EXTENSION = AuthoredInteractiveExtension(
    marker_attribute="browsergym_set_of_marks",
    marker_value="1",
    backend_handle_attribute="bid",
    visibility_ratio_attribute="browsergym_visibility_ratio",
    semantic_patterns=frozenset(
        {
            "calendar_range",
            "quantity_control",
            "owner_collection",
            "color_target",
        }
    ),
)


def browsergym_dom_adapter() -> DomAdapter:
    return DomAdapter(extension=BROWSERGYM_DOM_EXTENSION)


def browsergym_svg_observer() -> SelectiveSvgGeometryObserver:
    return SelectiveSvgGeometryObserver(
        authored_extension=SvgAuthoredExtension(
            marker_attribute="browsergym_set_of_marks",
            marker_value="1",
            backend_handle_attribute="bid",
        )
    )

from __future__ import annotations

import hashlib
import io

from PIL import Image

from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveredActionRoute,
    DeliveryManifest,
)
from affordance_runtime.agent.context.context import AgentImageMark, VisualEvidenceFragment
from affordance_runtime.agent.context.model_turn_delivery import (
    DeliveredMediaMark,
    _delivered_media,
    _manifest_with_media_evidence,
)
from affordance_runtime.immutable import to_json_compatible


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def _image(*marks: AgentImageMark) -> VisualEvidenceFragment:
    data = _png()
    return VisualEvidenceFragment(
        "artifact:test-image",
        "image/png",
        data,
        hashlib.sha256(data).hexdigest(),
        "viewport:test",
        marks,
    )


def _route(operation: str, source: str, destination: str = "") -> DeliveredActionRoute:
    return DeliveredActionRoute(
        operation,
        source,
        destination,
        private_action_id=f"private:{operation}:{source}:{destination}",
        private_option=object(),
    )


def test_executable_mark_is_visual_evidence_and_cannot_authorize_unary_route() -> None:
    media = _delivered_media((_image(AgentImageMark("E1", (1, 2, 3, 4))),))[0]
    manifest = _manifest_with_media_evidence(DeliveryManifest(), (media,))

    assert media.actual_marks == (DeliveredMediaMark("E1", (1, 2, 3, 4)),)
    assert manifest.action_routes == ()
    assert manifest.executable_refs == ()


def test_single_or_double_binary_operand_marks_cannot_authorize_route() -> None:
    for marks in (
        (AgentImageMark("E1", (1, 1, 4, 4)),),
        (AgentImageMark("E2", (10, 1, 4, 4)),),
        (
            AgentImageMark("E1", (1, 1, 4, 4)),
            AgentImageMark("E2", (10, 1, 4, 4)),
        ),
    ):
        media = _delivered_media((_image(*marks),))[0]
        manifest = _manifest_with_media_evidence(DeliveryManifest(), (media,))

        assert tuple(item.ref for item in media.actual_marks) == tuple(item.ref for item in marks)
        assert manifest.action_routes == ()
        assert manifest.executable_refs == ()


def test_admitted_complete_route_is_preserved_independently_of_marks() -> None:
    route = _route("drag_to", "E1", "E2")
    text_manifest = DeliveryManifest(("E1", "E2"), action_routes=(route,))

    for marks in (
        (),
        (AgentImageMark("E1", (1, 1, 4, 4)),),
        (AgentImageMark("E2", (10, 1, 4, 4)),),
        (
            AgentImageMark("E1", (1, 1, 4, 4)),
            AgentImageMark("E2", (10, 1, 4, 4)),
        ),
    ):
        media = _delivered_media((_image(*marks),))[0]
        manifest = _manifest_with_media_evidence(text_manifest, (media,))

        assert manifest.action_routes == (route,)
        assert manifest.executable_refs == ("E1", "E2")


def test_readonly_mark_remains_evidence_only_and_enters_readonly_manifest() -> None:
    media = _delivered_media((_image(AgentImageMark("N1", (2, 2, 5, 5))),))[0]
    manifest = _manifest_with_media_evidence(DeliveryManifest(), (media,))

    assert media.actual_marks == (DeliveredMediaMark("N1", (2, 2, 5, 5)),)
    assert manifest.action_routes == ()
    assert manifest.executable_refs == ()
    assert manifest.readonly_refs == ("N1",)


def test_unavailable_or_undrawn_mark_does_not_change_admitted_route() -> None:
    media = _delivered_media((_image(),))[0]
    route = _route("activate", "E1")
    text_manifest = DeliveryManifest(("E1",), action_routes=(route,))

    manifest = _manifest_with_media_evidence(text_manifest, (media,))

    assert media.actual_marks == ()
    assert manifest.action_routes == (route,)


def test_visual_evidence_serialization_contains_no_route_or_resolver_lineage() -> None:
    image = _image(AgentImageMark("E1", (1, 2, 3, 4)))

    serialized = to_json_compatible(image)

    assert serialized["marks"] == [{"ref": "E1", "bbox": [1, 2, 3, 4]}]
    assert "route_deltas" not in serialized
    assert "operand_roles" not in serialized["marks"][0]
    assert "private_action_id" not in str(serialized)
    assert "private_option" not in str(serialized)

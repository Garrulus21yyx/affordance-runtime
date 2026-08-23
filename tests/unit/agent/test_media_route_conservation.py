from __future__ import annotations

import hashlib
import io

from PIL import Image

from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveredActionRoute,
    DeliveryManifest,
)
from affordance_runtime.agent.context.context import AgentImageInput
from affordance_runtime.agent.context.model_turn_delivery import (
    DeliveredMedia,
    DeliveredMediaMark,
    MediaOperandRole,
    _delivered_media,
    _manifest_with_media_routes,
)


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def _image(*marks: tuple[str, tuple[int, int, int, int]]) -> AgentImageInput:
    data = _png()
    return AgentImageInput(
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


def test_unary_actual_mark_carries_source_role_and_exact_route_delta() -> None:
    route = _route("activate", "E1")

    media = _delivered_media((_image(("E1", (1, 2, 3, 4))),), (route,))[0]
    manifest = _manifest_with_media_routes(DeliveryManifest(), (media,))

    assert media.actual_marks == (
        DeliveredMediaMark("E1", (1, 2, 3, 4), (MediaOperandRole.SOURCE,)),
    )
    assert media.route_deltas == (route,)
    assert manifest.action_routes == (route,)
    assert manifest.executable_refs == ("E1",)


def test_destination_route_preserves_both_typed_operand_roles_without_unary_route() -> None:
    route = _route("drag_to", "E1", "E2")

    media = _delivered_media(
        (_image(("E1", (1, 1, 4, 4)), ("E2", (10, 1, 4, 4))),),
        (route,),
    )[0]
    manifest = _manifest_with_media_routes(DeliveryManifest(), (media,))

    assert tuple((mark.ref, mark.operand_roles) for mark in media.actual_marks) == (
        ("E1", (MediaOperandRole.SOURCE,)),
        ("E2", (MediaOperandRole.DESTINATION,)),
    )
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in manifest.action_routes
    ) == (("drag_to", "E1", "E2"),)
    assert not any(item.source_ref == "E2" and not item.destination_ref for item in manifest.action_routes)


def test_destination_only_mark_preserves_binary_route_and_never_fabricates_unary_verb() -> None:
    route = _route("drag_to", "E1", "E2")

    media = _delivered_media((_image(("E2", (10, 1, 4, 4))),), (route,))[0]
    manifest = _manifest_with_media_routes(
        DeliveryManifest(("E1", "E2"), action_routes=(route,)),
        (media,),
    )

    assert media.actual_marks == (
        DeliveredMediaMark("E2", (10, 1, 4, 4), (MediaOperandRole.DESTINATION,)),
    )
    assert media.route_deltas == (route,)
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in manifest.action_routes
    ) == (("drag_to", "E1", "E2"),)
    assert not any(item.source_ref == "E2" and not item.destination_ref for item in manifest.action_routes)


def test_source_only_mark_preserves_destination_route_with_source_role() -> None:
    route = _route("drag_to", "E1", "E2")

    media = _delivered_media((_image(("E1", (1, 1, 4, 4))),), (route,))[0]

    assert media.actual_marks == (
        DeliveredMediaMark("E1", (1, 1, 4, 4), (MediaOperandRole.SOURCE,)),
    )
    assert media.route_deltas == (route,)


def test_evidence_only_mark_carries_no_role_and_cannot_authorize_a_route() -> None:
    media = _delivered_media((_image(("E3", (2, 2, 5, 5))),), ())[0]
    manifest = _manifest_with_media_routes(DeliveryManifest(), (media,))

    assert media.actual_marks == (DeliveredMediaMark("E3", (2, 2, 5, 5)),)
    assert media.route_deltas == ()
    assert manifest.action_routes == ()
    assert manifest.executable_refs == ()


def test_unavailable_or_undrawn_mark_cannot_copy_an_admitted_text_route() -> None:
    route = _route("activate", "E1")

    media = _delivered_media((_image(),), (route,))[0]
    text_manifest = DeliveryManifest(("E1",), action_routes=(route,))
    manifest = _manifest_with_media_routes(text_manifest, (media,))

    assert media.actual_marks == ()
    assert media.route_deltas == ()
    assert manifest.action_routes == (route,)


def test_delivered_media_rejects_role_without_its_exact_route_delta() -> None:
    image = _image(("E1", (1, 1, 2, 2)))

    try:
        DeliveredMedia(
            image.evidence_ref,
            image.mime_type,
            image.data,
            image.sha256,
            image.coordinate_space_id,
            (DeliveredMediaMark("E1", (1, 1, 2, 2), (MediaOperandRole.SOURCE,)),),
            (),
        )
    except ValueError as error:
        assert "operand roles differ" in str(error)
    else:
        raise AssertionError("a media mark role without an exact route delta must fail closed")

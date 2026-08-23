from __future__ import annotations

import hashlib
import io

from PIL import Image

from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveredActionRoute,
    DeliveryManifest,
)
from affordance_runtime.agent.context.context import (
    AgentImageActionRoute,
    AgentImageInput,
    AgentImageMark,
    AgentImageOperandRole,
)
from affordance_runtime.agent.context.model_turn_delivery import (
    DeliveredMedia,
    DeliveredMediaMark,
    _delivered_media,
    _manifest_with_media_routes,
)


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def _image(
    *marks: AgentImageMark,
    routes: tuple[AgentImageActionRoute, ...] = (),
) -> AgentImageInput:
    data = _png()
    return AgentImageInput(
        "artifact:test-image",
        "image/png",
        data,
        hashlib.sha256(data).hexdigest(),
        "viewport:test",
        marks,
        routes,
    )


def _route(operation: str, source: str, destination: str = "") -> AgentImageActionRoute:
    return AgentImageActionRoute(
        operation,
        source,
        destination,
        private_action_id=f"private:{operation}:{source}:{destination}",
        private_option=object(),
    )


def test_unary_actual_mark_carries_source_role_and_exact_route_delta() -> None:
    route = _route("activate", "E1")

    media = _delivered_media((
        _image(
            AgentImageMark("E1", (1, 2, 3, 4), (AgentImageOperandRole.SOURCE,)),
            routes=(route,),
        ),
    ))[0]
    manifest = _manifest_with_media_routes(DeliveryManifest(), (media,))

    assert media.actual_marks == (
        DeliveredMediaMark("E1", (1, 2, 3, 4), (AgentImageOperandRole.SOURCE,)),
    )
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in media.route_deltas
    ) == ((route.operation, route.source_ref, route.destination_ref),)
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in manifest.action_routes
    ) == ((route.operation, route.source_ref, route.destination_ref),)
    assert manifest.executable_refs == ("E1",)


def test_destination_route_preserves_both_typed_operand_roles_without_unary_route() -> None:
    route = _route("drag_to", "E1", "E2")

    media = _delivered_media((
        _image(
            AgentImageMark("E1", (1, 1, 4, 4), (AgentImageOperandRole.SOURCE,)),
            AgentImageMark("E2", (10, 1, 4, 4), (AgentImageOperandRole.DESTINATION,)),
            routes=(route,),
        ),
    ))[0]
    manifest = _manifest_with_media_routes(DeliveryManifest(), (media,))

    assert tuple((mark.ref, mark.operand_roles) for mark in media.actual_marks) == (
        ("E1", (AgentImageOperandRole.SOURCE,)),
        ("E2", (AgentImageOperandRole.DESTINATION,)),
    )
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in manifest.action_routes
    ) == (("drag_to", "E1", "E2"),)
    assert not any(item.source_ref == "E2" and not item.destination_ref for item in manifest.action_routes)


def test_destination_only_mark_preserves_binary_route_and_never_fabricates_unary_verb() -> None:
    route = _route("drag_to", "E1", "E2")

    media = _delivered_media((
        _image(
            AgentImageMark("E2", (10, 1, 4, 4), (AgentImageOperandRole.DESTINATION,)),
            routes=(route,),
        ),
    ))[0]
    manifest = _manifest_with_media_routes(
        DeliveryManifest(),
        (media,),
    )

    assert media.actual_marks == (
        DeliveredMediaMark("E2", (10, 1, 4, 4), (AgentImageOperandRole.DESTINATION,)),
    )
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in media.route_deltas
    ) == ((route.operation, route.source_ref, route.destination_ref),)
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in manifest.action_routes
    ) == (("drag_to", "E1", "E2"),)
    assert not any(item.source_ref == "E2" and not item.destination_ref for item in manifest.action_routes)


def test_source_only_mark_preserves_destination_route_with_source_role() -> None:
    route = _route("drag_to", "E1", "E2")

    media = _delivered_media((
        _image(
            AgentImageMark("E1", (1, 1, 4, 4), (AgentImageOperandRole.SOURCE,)),
            routes=(route,),
        ),
    ))[0]

    assert media.actual_marks == (
        DeliveredMediaMark("E1", (1, 1, 4, 4), (AgentImageOperandRole.SOURCE,)),
    )
    assert tuple(
        (item.operation, item.source_ref, item.destination_ref)
        for item in media.route_deltas
    ) == ((route.operation, route.source_ref, route.destination_ref),)


def test_evidence_only_mark_carries_no_role_and_cannot_authorize_a_route() -> None:
    media = _delivered_media((_image(AgentImageMark("E3", (2, 2, 5, 5))),))[0]
    manifest = _manifest_with_media_routes(DeliveryManifest(), (media,))

    assert media.actual_marks == (DeliveredMediaMark("E3", (2, 2, 5, 5)),)
    assert media.route_deltas == ()
    assert manifest.action_routes == ()
    assert manifest.executable_refs == ()


def test_unavailable_or_undrawn_mark_cannot_copy_an_admitted_text_route() -> None:
    media = _delivered_media((_image(),))[0]
    route = DeliveredActionRoute(
        "activate", "E1", private_action_id="private:text", private_option=object()
    )
    text_manifest = DeliveryManifest(("E1",), action_routes=(route,))
    manifest = _manifest_with_media_routes(text_manifest, (media,))

    assert media.actual_marks == ()
    assert media.route_deltas == ()
    assert manifest.action_routes == (route,)


def test_delivered_media_rejects_role_without_its_exact_route_delta() -> None:
    image = _image(AgentImageMark("E1", (1, 1, 2, 2)))

    try:
        DeliveredMedia(
            image.evidence_ref,
            image.mime_type,
            image.data,
            image.sha256,
            image.coordinate_space_id,
            (DeliveredMediaMark("E1", (1, 1, 2, 2), (AgentImageOperandRole.SOURCE,)),),
            (),
        )
    except ValueError as error:
        assert "operand roles differ" in str(error)
    else:
        raise AssertionError("a media mark role without an exact route delta must fail closed")

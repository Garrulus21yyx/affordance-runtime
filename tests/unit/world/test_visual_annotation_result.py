import hashlib
import io

from PIL import Image

from affordance_runtime.agent.context.context import AgentImageInput
from affordance_runtime.world.visual_annotation import (
    BoundingBox,
    VisualMark,
    annotate_screenshot_result,
)


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 10), (255, 255, 255)).save(output, format="JPEG")
    return output.getvalue()


def _mark(ref: str, bbox: BoundingBox) -> VisualMark:
    return VisualMark(ref, ref, bbox, 1.0, "artifact:image", "obs:1", "revision:1", ref)


def test_annotation_owns_actual_png_mime_digest_and_in_frame_marks() -> None:
    result = annotate_screenshot_result(
        _jpeg(),
        "image/jpeg",
        (
            _mark("E1", BoundingBox(1, 1, 5, 5)),
            _mark("E2", BoundingBox(30, 20, 2, 2)),
        ),
    )

    assert result.mime_type == "image/png"
    assert result.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.sha256 == hashlib.sha256(result.data).hexdigest()
    assert tuple(mark.mark_id for mark in result.marks) == ("E1",)
    admitted = AgentImageInput(
        "artifact:image",
        result.mime_type,
        result.data,
        result.sha256,
        "viewport:1",
        tuple((mark.mark_id, mark.bbox.xywh) for mark in result.marks),
    )
    assert admitted.marks == (("E1", (1, 1, 5, 5)),)


"""Immutable BrowserGym screenshot capture owned by the grouped surface adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from affordance_runtime.surfaces.visual.contracts import VisualFrame, VisualViewport


@dataclass(frozen=True)
class BrowserGymCaptureFrame:
    """One encoded frame shared by structural and visual projections."""

    acquisition_root_id: str
    page_identity: str
    episode_identity: str
    image_bytes: bytes
    image_width: int
    image_height: int
    screenshot_digest: str
    viewport: VisualViewport

    def __post_init__(self) -> None:
        if (
            not self.acquisition_root_id.strip()
            or not self.page_identity.strip()
            or not self.episode_identity.strip()
            or not self.image_bytes
            or self.image_width <= 0
            or self.image_height <= 0
            or self.screenshot_digest
            != "sha256:" + hashlib.sha256(self.image_bytes).hexdigest()
        ):
            raise ValueError("BrowserGym capture frame is invalid")

    def visual_frame(self, observation_id: str) -> VisualFrame:
        return VisualFrame(
            observation_id,
            f"browsergym-screenshot:{self.acquisition_root_id}",
            self.screenshot_digest,
            self.image_width,
            self.image_height,
            self.viewport,
            self.image_bytes,
        )


def browsergym_capture_frame(
    raw: dict[str, object],
    *,
    acquisition_root_id: str,
    page_identity: str,
    episode_identity: str,
) -> BrowserGymCaptureFrame | None:
    """Encode the provider-owned raw screenshot exactly once for one acquisition."""

    screenshot = raw.get("screenshot")
    if screenshot is None:
        return None
    try:
        image = Image.fromarray(screenshot)  # type: ignore[arg-type]
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        image_bytes = output.getvalue()
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise ValueError("BrowserGym screenshot could not be encoded") from exc
    width, height = image.size
    viewport = VisualViewport(
        width,
        height,
        0.0,
        0.0,
        1.0,
        1.0,
        "landscape" if width >= height else "portrait",
    )
    return BrowserGymCaptureFrame(
        acquisition_root_id,
        page_identity,
        episode_identity,
        image_bytes,
        width,
        height,
        "sha256:" + hashlib.sha256(image_bytes).hexdigest(),
        viewport,
    )

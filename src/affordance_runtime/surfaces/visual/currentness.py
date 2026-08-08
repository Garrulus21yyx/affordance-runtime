"""Pure Visual binding currentness checks."""

from affordance_runtime.surfaces.visual.contracts import VisualFrame, VisualRegionBinding


def visual_binding_is_current(
    binding: VisualRegionBinding,
    live: VisualFrame,
) -> bool:
    return (
        bool(binding.source_observation_id and binding.region_fingerprint)
        and binding.screenshot_digest == live.screenshot_digest
        and binding.image_width == live.image_width
        and binding.image_height == live.image_height
        and binding.viewport == live.viewport
    )

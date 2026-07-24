"""Versioned BrowserGym evaluation protocol metadata."""

from __future__ import annotations

from typing import Literal, Sequence

BROWSERGYM_VERSION = "0.14.3"
BROWSERGYM_RUN_PROTOCOL_VERSION = "three-layer-breadth-first-audit-v2"
BrowserGymProfile = Literal["smoke", "pr", "diagnostic", "nightly", "release"]

PR_SMOKE_TASKS = (
    "click-button",
    "enter-text",
    "choose-list",
    "click-dialog",
    "click-button-sequence",
    "form-sequence",
)

# This versioned selection manifest defines controlled breadth, not runtime
# dispatch. Missing tasks are reported rather than silently removed.
NIGHTLY_TASK_MANIFEST_VERSION = "miniwob-action-family-v1"
NIGHTLY_ACTION_FAMILY_MANIFEST: dict[str, tuple[str, ...]] = {
    "activate": ("click-button", "click-checkboxes", "click-dialog"),
    "form": ("form-sequence", "form-sequence-2", "form-sequence-3"),
    "text_entry": ("enter-text", "enter-text-2", "enter-date"),
    "selection": ("choose-list", "click-option", "use-autocomplete"),
    "keyboard": ("focus-text", "copy-paste", "text-transform"),
    "scroll": ("scroll-text", "scroll-text-2", "click-scroll-list"),
    "drag": ("drag-box", "drag-items", "drag-sort-numbers"),
    "navigation": ("navigate-tree", "search-engine", "click-link"),
    "read": ("read-table", "email-inbox", "phone-book"),
    "spatial_value": ("use-slider", "grid-coordinate", "circle-center"),
}
NIGHTLY_TASKS = tuple(task for family in NIGHTLY_ACTION_FAMILY_MANIFEST.values() for task in family)


def browsergym_episode_schedule(task_ids: Sequence[str], seeds: Sequence[int]) -> tuple[tuple[str, int], ...]:
    """Return the protocol's seed-major (breadth-first) episode order."""

    return tuple((task_id, seed) for seed in seeds for task_id in task_ids)

"""Pure typed comparison for canonical BrowserGym currentness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from affordance_runtime.surfaces.browsergym.interaction_profile import (
    primitive_is_compatible,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    CanonicalBrowserControl,
)


class BrowserGymCurrentnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class BrowserGymCurrentnessReason(str, Enum):
    CURRENT = "current"
    BINDING_EPOCH_CHANGED = "binding_epoch_changed"
    PROBE_UNAVAILABLE = "probe_unavailable"
    ELEMENT_MISSING = "element_missing"
    TASK_NOT_READY = "task_not_ready"
    TASK_DONE = "task_done"
    PAGE_CHANGED = "page_changed"
    EPISODE_CHANGED = "episode_changed"
    ROLE_CHANGED = "role_changed"
    LABEL_CHANGED = "label_changed"
    STATE_CHANGED = "state_changed"
    OPTION_DOMAIN_CHANGED = "option_domain_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    PRIMITIVE_CHANGED = "primitive_changed"
    NOT_EXECUTABLE = "not_executable"


@dataclass(frozen=True)
class BrowserGymCurrentnessContext:
    binding_epoch_matches: bool
    captured_page_identity: str
    live_page_identity: str
    captured_episode_identity: str
    live_episode_identity: str
    task_ready: bool
    task_done: bool
    requested_primitive: str


@dataclass(frozen=True)
class BrowserGymCurrentnessDecision:
    status: BrowserGymCurrentnessStatus
    reason: BrowserGymCurrentnessReason


def unavailable_currentness() -> BrowserGymCurrentnessDecision:
    return BrowserGymCurrentnessDecision(
        BrowserGymCurrentnessStatus.UNAVAILABLE,
        BrowserGymCurrentnessReason.PROBE_UNAVAILABLE,
    )


def compare_browsergym_currentness(
    captured: CanonicalBrowserControl,
    live: CanonicalBrowserControl | None,
    context: BrowserGymCurrentnessContext,
) -> BrowserGymCurrentnessDecision:
    reason = _stale_reason(captured, live, context)
    if reason is None:
        return BrowserGymCurrentnessDecision(
            BrowserGymCurrentnessStatus.CURRENT,
            BrowserGymCurrentnessReason.CURRENT,
        )
    return BrowserGymCurrentnessDecision(BrowserGymCurrentnessStatus.STALE, reason)


def compare_browsergym_drag_currentness(
    captured_source: CanonicalBrowserControl,
    live_source: CanonicalBrowserControl | None,
    captured_destination: CanonicalBrowserControl,
    live_destination: CanonicalBrowserControl | None,
    context: BrowserGymCurrentnessContext,
) -> BrowserGymCurrentnessDecision:
    """Validate both endpoints against one read-only live snapshot."""

    source = compare_browsergym_currentness(captured_source, live_source, context)
    if source.status is not BrowserGymCurrentnessStatus.CURRENT:
        return source
    reason = _destination_stale_reason(captured_destination, live_destination)
    if reason is None:
        return source
    return BrowserGymCurrentnessDecision(BrowserGymCurrentnessStatus.STALE, reason)


def _destination_stale_reason(
    captured: CanonicalBrowserControl,
    live: CanonicalBrowserControl | None,
) -> BrowserGymCurrentnessReason | None:
    if live is None or captured.private_bid != live.private_bid:
        return BrowserGymCurrentnessReason.ELEMENT_MISSING
    if captured.role != live.role:
        return BrowserGymCurrentnessReason.ROLE_CHANGED
    if captured.accessible_name != live.accessible_name:
        return BrowserGymCurrentnessReason.LABEL_CHANGED
    if captured.public_state != live.public_state:
        return BrowserGymCurrentnessReason.STATE_CHANGED
    if (
        captured.private_gesture_group != live.private_gesture_group
        or captured.private_gesture_kind != live.private_gesture_kind
    ):
        return BrowserGymCurrentnessReason.PRIMITIVE_CHANGED
    if captured.availability != live.availability:
        return BrowserGymCurrentnessReason.AVAILABILITY_CHANGED
    if not (
        live.availability.attached is True
        and live.availability.visible is True
        and live.availability.enabled is True
    ):
        return BrowserGymCurrentnessReason.NOT_EXECUTABLE
    return None


def _stale_reason(
    captured: CanonicalBrowserControl,
    live: CanonicalBrowserControl | None,
    context: BrowserGymCurrentnessContext,
) -> BrowserGymCurrentnessReason | None:
    if not context.binding_epoch_matches:
        return BrowserGymCurrentnessReason.BINDING_EPOCH_CHANGED
    if context.task_done:
        return BrowserGymCurrentnessReason.TASK_DONE
    if not context.task_ready:
        return BrowserGymCurrentnessReason.TASK_NOT_READY
    if context.captured_page_identity != context.live_page_identity:
        return BrowserGymCurrentnessReason.PAGE_CHANGED
    if context.captured_episode_identity != context.live_episode_identity:
        return BrowserGymCurrentnessReason.EPISODE_CHANGED
    if live is None:
        return BrowserGymCurrentnessReason.ELEMENT_MISSING
    if captured.private_bid != live.private_bid:
        return BrowserGymCurrentnessReason.ELEMENT_MISSING
    if captured.role != live.role:
        return BrowserGymCurrentnessReason.ROLE_CHANGED
    if captured.accessible_name != live.accessible_name:
        return BrowserGymCurrentnessReason.LABEL_CHANGED
    if captured.public_state != live.public_state:
        return BrowserGymCurrentnessReason.STATE_CHANGED
    if (
        captured.public_options != live.public_options
        or captured.private_options != live.private_options
    ):
        return BrowserGymCurrentnessReason.OPTION_DOMAIN_CHANGED
    if (
        captured.private_gesture_group != live.private_gesture_group
        or captured.private_gesture_kind != live.private_gesture_kind
    ):
        return BrowserGymCurrentnessReason.PRIMITIVE_CHANGED
    if (
        len(tuple(
            offer for offer in captured.executable_offers
            if offer.primitive_action == context.requested_primitive
        )) != 1
        or not primitive_is_compatible(live.role, context.requested_primitive)
    ):
        return BrowserGymCurrentnessReason.PRIMITIVE_CHANGED
    if not live.executable:
        return BrowserGymCurrentnessReason.NOT_EXECUTABLE
    if captured.availability != live.availability:
        return BrowserGymCurrentnessReason.AVAILABILITY_CHANGED
    return None

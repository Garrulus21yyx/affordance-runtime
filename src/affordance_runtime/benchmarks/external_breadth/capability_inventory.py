"""Pinned-source static interaction-family inventory; never a policy oracle."""

from __future__ import annotations

import hashlib
import json

from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobCapabilityStatus,
    MiniWobRegistryCensus,
    MiniWobTaskCapability,
)

PRIMITIVE_VOCABULARY = frozenset({
    "activate", "fill", "select", "drag", "hover", "scroll", "keypress",
    "multi_select", "slider", "canvas", "other", "unknown",
})
CURRENT_PRIMITIVES = frozenset({"activate", "fill", "select"})

_UNSUPPORTED: dict[str, tuple[str, ...]] = {
    "bisect-angle": ("canvas",),
    "circle-center": ("canvas",),
    "click-scroll-list": ("scroll", "activate"),
    "daily-calendar": ("drag",),
    "draw-circle": ("canvas",),
    "draw-line": ("canvas",),
    "find-midpoint": ("canvas",),
    "highlight-text": ("drag",),
    "highlight-text-2": ("drag",),
    "resize-textarea": ("drag",),
    "right-angle": ("canvas",),
    "scroll-text": ("scroll", "activate"),
    "scroll-text-2": ("scroll", "activate"),
    "terminal": ("keypress",),
    "text-editor": ("keypress",),
    "use-autocomplete": ("fill", "keypress"),
    "use-autocomplete-nodelay": ("fill", "keypress"),
    "use-colorwheel": ("canvas",),
    "use-colorwheel-2": ("canvas",),
    "use-slider": ("slider",),
    "use-slider-2": ("slider",),
}


def build_capability_inventory(census: MiniWobRegistryCensus) -> tuple[MiniWobTaskCapability, ...]:
    inventory = tuple(_classify(task_id) for task_id in census.task_ids)
    if len({item.task_id for item in inventory}) != len(census.task_ids):
        raise ValueError("capability inventory must cover every registry task exactly once")
    return inventory


def capability_inventory_digest(inventory: tuple[MiniWobTaskCapability, ...]) -> str:
    payload = [
        {
            "task_id": item.task_id,
            "status": item.status.value,
            "required_primitives": item.required_primitives,
            "reason_code": item.reason_code,
            "source_reference": item.source_reference,
        }
        for item in sorted(inventory, key=lambda value: value.task_id)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def supported_candidates(
    inventory: tuple[MiniWobTaskCapability, ...],
) -> tuple[MiniWobTaskCapability, ...]:
    return tuple(
        item for item in inventory
        if item.status is MiniWobCapabilityStatus.CURRENT_PRIMITIVES
        and set(item.required_primitives) <= CURRENT_PRIMITIVES
    )


def _classify(task_id: str) -> MiniWobTaskCapability:
    slug = task_id.removeprefix("browsergym/miniwob.")
    source = f"miniwob/html/miniwob/{slug}.html@7fd85d71a4b6"
    unsupported = _unsupported_primitives(slug)
    if unsupported:
        return MiniWobTaskCapability(
            task_id,
            MiniWobCapabilityStatus.REQUIRES_UNSUPPORTED_PRIMITIVE,
            unsupported,
            "pinned_source_requires_unsupported_interaction_family",
            source,
        )
    primitives = _current_primitives(slug)
    return MiniWobTaskCapability(
        task_id,
        MiniWobCapabilityStatus.CURRENT_PRIMITIVES,
        primitives,
        "pinned_source_expressible_with_current_semantic_primitives",
        source,
    )


def _unsupported_primitives(slug: str) -> tuple[str, ...]:
    if slug in _UNSUPPORTED:
        return _UNSUPPORTED[slug]
    if slug.startswith("drag-"):
        return ("drag",)
    return ()


def _current_primitives(slug: str) -> tuple[str, ...]:
    fill_markers = (
        "book-", "buy-ticket", "copy-paste", "count-", "email-inbox-forward",
        "email-inbox-reply", "enter-", "form-sequence", "generate-number", "guess-number",
        "login-user", "order-food", "search-engine", "sign-agreement", "simple-",
        "text-transform",
    )
    select_markers = ("book-", "buy-ticket", "choose-list", "form-sequence", "order-food")
    primitives = {"activate"}
    if slug.startswith(fill_markers):
        primitives.add("fill")
    if slug.startswith(select_markers):
        primitives.add("select")
    return tuple(item for item in ("activate", "fill", "select") if item in primitives)

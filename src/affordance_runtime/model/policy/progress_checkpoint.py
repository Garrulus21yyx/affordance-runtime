"""Bounded model-authored working context for the ActionPolicy history.

This value is not Runtime task state, evidence, or a mutable plan.  It only
distinguishes an explicit cumulative checkpoint update from ordinary provider
text before the PydanticAI history boundary decides what to retain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

PROGRESS_CHECKPOINT_VERSION = "progress-checkpoint.v1"
PROGRESS_CHECKPOINT_OPEN = "<progress_checkpoint>"
PROGRESS_CHECKPOINT_CLOSE = "</progress_checkpoint>"
MAX_PROGRESS_CHECKPOINT_CHARS = 800
_MAX_LIST_ITEMS = 16
_MAX_ITEM_CHARS = 240


@dataclass(frozen=True)
class ProgressCheckpoint:
    """One complete, revisable, non-authoritative task-working summary."""

    verified_facts: tuple[str, ...] = ()
    working_hypotheses: tuple[str, ...] = ()
    remaining_requirements: tuple[str, ...] = ()
    next_intent: str = ""
    avoid_repeating: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "verified_facts",
            "working_hypotheses",
            "remaining_requirements",
            "avoid_repeating",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError("progress checkpoint collections must be tuples")
            if len(values) > _MAX_LIST_ITEMS:
                raise ValueError("progress checkpoint collection is too large")
            if any(
                type(item) is not str
                or not item.strip()
                or item != item.strip()
                or len(item) > _MAX_ITEM_CHARS
                for item in values
            ):
                raise ValueError("progress checkpoint entries must be bounded text")
            if len(set(values)) != len(values):
                raise ValueError("progress checkpoint entries must be unique")
        if (
            type(self.next_intent) is not str
            or not self.next_intent.strip()
            or self.next_intent != self.next_intent.strip()
            or len(self.next_intent) > _MAX_ITEM_CHARS
        ):
            raise ValueError("progress checkpoint next intent must be bounded text")
        if len(self.render()) > MAX_PROGRESS_CHECKPOINT_CHARS:
            raise ValueError("progress checkpoint exceeds its history bound")

    def render(self) -> str:
        payload = {
            "version": PROGRESS_CHECKPOINT_VERSION,
            "verified_facts": self.verified_facts,
            "working_hypotheses": self.working_hypotheses,
            "remaining_requirements": self.remaining_requirements,
            "next_intent": self.next_intent,
            "avoid_repeating": self.avoid_repeating,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return f"{PROGRESS_CHECKPOINT_OPEN}{body}{PROGRESS_CHECKPOINT_CLOSE}"

    @classmethod
    def parse(cls, text: object) -> ProgressCheckpoint | None:
        """Parse only an exact checkpoint wrapper; arbitrary model prose is not progress."""

        if type(text) is not str:
            return None
        value = text.strip()
        if (
            not value.startswith(PROGRESS_CHECKPOINT_OPEN)
            or not value.endswith(PROGRESS_CHECKPOINT_CLOSE)
            or len(value) > MAX_PROGRESS_CHECKPOINT_CHARS
        ):
            return None
        body = value[len(PROGRESS_CHECKPOINT_OPEN) : -len(PROGRESS_CHECKPOINT_CLOSE)]
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return None
        expected_keys = {
            "version",
            "verified_facts",
            "working_hypotheses",
            "remaining_requirements",
            "next_intent",
            "avoid_repeating",
        }
        if type(payload) is not dict or set(payload) != expected_keys:
            return None
        if payload.get("version") != PROGRESS_CHECKPOINT_VERSION:
            return None

        collections: dict[str, tuple[str, ...]] = {}
        for name in (
            "verified_facts",
            "working_hypotheses",
            "remaining_requirements",
            "avoid_repeating",
        ):
            items = payload.get(name)
            if type(items) is not list:
                return None
            collections[name] = tuple(items)
        try:
            checkpoint = cls(
                verified_facts=collections["verified_facts"],
                working_hypotheses=collections["working_hypotheses"],
                remaining_requirements=collections["remaining_requirements"],
                next_intent=payload.get("next_intent"),
                avoid_repeating=collections["avoid_repeating"],
            )
        except (TypeError, ValueError):
            return None
        return checkpoint


def normalize_progress_checkpoint(text: object) -> str:
    """Return the canonical history representation or an empty rejection."""

    checkpoint = ProgressCheckpoint.parse(text)
    return checkpoint.render() if checkpoint is not None else ""

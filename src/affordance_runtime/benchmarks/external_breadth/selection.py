"""Bias-resistant deterministic selection from the admitted capability pool."""

from __future__ import annotations

import hashlib

from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobTaskCapability

SELECTION_NAMESPACE = "miniwob-60-seeded-breadth.v1"
SELECTION_SIZE = 60


def selection_key(task_id: str, namespace: str = SELECTION_NAMESPACE) -> str:
    return hashlib.sha256(f"{namespace}\0{task_id}".encode()).hexdigest()


def select_tasks(
    candidates: tuple[MiniWobTaskCapability, ...],
    *,
    count: int = SELECTION_SIZE,
    namespace: str = SELECTION_NAMESPACE,
) -> tuple[MiniWobTaskCapability, ...]:
    if len(candidates) < count:
        raise ValueError(f"supported MiniWoB candidate pool contains {len(candidates)} tasks; {count} required")
    unique = {item.task_id: item for item in candidates}
    if len(unique) != len(candidates):
        raise ValueError("supported MiniWoB candidate IDs must be unique")
    ordered = sorted(unique.values(), key=lambda item: (selection_key(item.task_id, namespace), item.task_id))
    return tuple(ordered[:count])

"""Bounded fair traversal over one immutable WorldObservation snapshot."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.world.page_cursor import decode_cursor, encode_cursor


class ObservationTraversalStatus(StrEnum):
    PARTIAL = "partial"
    COMPLETE = "complete"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ObservationPageBasis:
    observation_id: str
    cursor: str
    offset: int
    header_target_ids: tuple[str, ...]
    exploration_target_ids: tuple[str, ...]
    exploration_next_offsets: tuple[int, ...]
    scan_end_offset: int
    total_count: int
    fingerprint: str

    @property
    def target_ids(self) -> tuple[str, ...]:
        return (*self.header_target_ids, *self.exploration_target_ids)


@dataclass(frozen=True)
class ObservationTraversalView:
    snapshot_id: str
    status: ObservationTraversalStatus
    next_cursor: str
    traversed_count: int
    reason_code: str = ""

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or self.traversed_count < 0:
            raise ValueError("observation traversal metadata is invalid")
        if self.status is ObservationTraversalStatus.PARTIAL and not self.next_cursor:
            raise ValueError("partial observation traversal requires a next cursor")
        if self.status is ObservationTraversalStatus.COMPLETE and self.next_cursor:
            raise ValueError("complete observation traversal cannot have a next cursor")
        if self.status is ObservationTraversalStatus.UNKNOWN and not self.reason_code:
            raise ValueError("unknown observation traversal requires a typed reason")


@dataclass(frozen=True)
class ObservationPager:
    max_pinned_targets: int = 56

    def __post_init__(self) -> None:
        if self.max_pinned_targets < 0:
            raise ValueError("observation pinned-target bound cannot be negative")

    def begin(
        self,
        projection: CanonicalPublicWorldProjection,
        *,
        pinned_target_ids: tuple[str, ...] = (),
        cursor: str = "",
        page_size: int = 64,
        min_exploration_slots: int = 8,
    ) -> ObservationPageBasis:
        if page_size <= 0 or min_exploration_slots <= 0 or min_exploration_slots > page_size:
            raise ValueError("observation paging bounds are invalid")
        ordered_target_ids = tuple(
            item.target_id for item in projection.ordered_target_records if "\0" not in item.target_id
        )
        current = set(ordered_target_ids)
        pinned_capacity = page_size if page_size == 1 else page_size - min_exploration_slots
        pinned = tuple(target_id for target_id in dict.fromkeys(pinned_target_ids) if target_id in current)[
            : min(self.max_pinned_targets, pinned_capacity)
        ]
        fingerprint = _fingerprint(projection, page_size, min_exploration_slots)
        offset = decode_cursor(cursor, fingerprint) if cursor else 0
        if offset > len(ordered_target_ids):
            raise ValueError("observation cursor is outside the frozen snapshot")
        pinned_set = set(pinned)
        exploration_limit = page_size - len(pinned)
        exploration: list[str] = []
        next_offsets: list[int] = []
        scan = offset
        while scan < len(ordered_target_ids) and len(exploration) < exploration_limit:
            candidate = ordered_target_ids[scan]
            scan += 1
            if candidate in pinned_set:
                continue
            exploration.append(candidate)
            next_offsets.append(scan)
        return ObservationPageBasis(
            projection.public_document_signature,
            cursor,
            offset,
            pinned,
            tuple(exploration),
            tuple(next_offsets),
            scan,
            len(ordered_target_ids),
            fingerprint,
        )

    def finish(
        self,
        basis: ObservationPageBasis,
        visible_target_ids: tuple[str, ...],
    ) -> ObservationTraversalView:
        visible = set(visible_target_ids)
        if len(visible) >= basis.total_count:
            return ObservationTraversalView(
                _public_snapshot_id(basis.observation_id),
                ObservationTraversalStatus.COMPLETE,
                "",
                basis.total_count,
            )
        shown = [
            (target_id, next_offset)
            for target_id, next_offset in zip(
                basis.exploration_target_ids,
                basis.exploration_next_offsets,
                strict=True,
            )
            if target_id in visible
        ]
        if basis.exploration_target_ids and not shown:
            return ObservationTraversalView(
                _public_snapshot_id(basis.observation_id),
                ObservationTraversalStatus.UNKNOWN,
                "",
                basis.offset,
                "model_page_capacity_exceeded",
            )
        traversed = shown[-1][1] if shown else basis.scan_end_offset
        has_more = traversed < basis.total_count
        if has_more and traversed == basis.offset:
            return ObservationTraversalView(
                _public_snapshot_id(basis.observation_id),
                ObservationTraversalStatus.UNKNOWN,
                "",
                traversed,
                "model_page_capacity_exceeded",
            )
        next_cursor = encode_cursor(traversed, basis.fingerprint) if has_more else ""
        return ObservationTraversalView(
            _public_snapshot_id(basis.observation_id),
            ObservationTraversalStatus.PARTIAL if has_more else ObservationTraversalStatus.COMPLETE,
            next_cursor,
            traversed,
        )


def _fingerprint(
    projection: CanonicalPublicWorldProjection,
    page_size: int,
    min_exploration_slots: int,
) -> str:
    payload = (
        projection.projection_lineage,
        tuple(item.ref for item in projection.ordered_target_records),
        page_size,
        min_exploration_slots,
    )
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()[:24]


def _public_snapshot_id(public_document_signature: str) -> str:
    return "snapshot:" + hashlib.sha256(public_document_signature.encode()).hexdigest()[:24]

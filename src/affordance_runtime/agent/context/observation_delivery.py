"""Bounded Monitor novelty receipts for committed local tool results.

Fresh ``WorldObservation`` is the only current GUI authority.  Completed
PydanticAI call/result pairs own model-visible tool history.  This module keeps
only small public digests needed by the repetition Monitor; it never stores or
re-projects GUI effects, result bodies, or cursors.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.decisions import LocalToolResult
from affordance_runtime.agent.public_values import is_public_scalar
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.public_semantic_digest import public_subject_semantics

_MAX_LOCAL_DELIVERY_RECORDS = 64
_MAX_LOCAL_INFORMATION_ITEMS = 32


class InformationDeltaKind(StrEnum):
    NEW_INFORMATION = "new_information"
    NO_MATCHES = "no_matches"
    NO_NEW_INFORMATION = "no_new_information"
    EXACT_REPLAY = "exact_replay"


@dataclass(frozen=True)
class InformationDelta:
    kind: InformationDeltaKind
    operation: str
    world_digest: str
    arguments_digest: str
    result_digest: str
    inventory_digest: str = ""
    new_record_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, InformationDeltaKind):
            raise TypeError("information delta kind must be typed")
        if not self.operation.strip() or not all(
            value.startswith("sha256:")
            for value in (self.world_digest, self.arguments_digest, self.result_digest)
        ):
            raise ValueError("information delta requires stable public identities")
        digests = tuple(self.new_record_digests)
        if len(digests) > _MAX_LOCAL_INFORMATION_ITEMS or any(
            not item.startswith("sha256:") for item in digests
        ):
            raise ValueError("information delta record identities are invalid")
        if self.kind is InformationDeltaKind.NEW_INFORMATION and (
            not digests or not self.inventory_digest.startswith("sha256:")
        ):
            raise ValueError("new information requires a typed result inventory")
        if self.kind is not InformationDeltaKind.NEW_INFORMATION and digests:
            raise ValueError("non-new delivery cannot carry record identities")
        if self.inventory_digest and not self.inventory_digest.startswith("sha256:"):
            raise ValueError("information delta inventory identity is invalid")
        object.__setattr__(self, "new_record_digests", digests)

    @property
    def new_information_count(self) -> int:
        return len(self.new_record_digests)


@dataclass(frozen=True)
class LocalDeliveryRecord:
    """Bounded Monitor receipt; never a model-visible result body."""

    operation: str
    world_digest: str
    arguments_digest: str
    result_digest: str
    item_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        item_digests = tuple(self.item_digests)
        if (
            not self.operation.strip()
            or not all(
                value.startswith("sha256:")
                for value in (self.world_digest, self.arguments_digest, self.result_digest)
            )
            or len(item_digests) > _MAX_LOCAL_INFORMATION_ITEMS
            or any(not item.startswith("sha256:") for item in item_digests)
        ):
            raise ValueError("local delivery record is invalid")
        object.__setattr__(self, "item_digests", item_digests)


@dataclass(frozen=True)
class DeliveryTransition:
    next_store: "ObservationDeliveryStore"
    information_delta: InformationDelta | None
    runtime_failure: RuntimeFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.next_store, ObservationDeliveryStore):
            raise TypeError("delivery transition requires the reducer-owned next Store")
        if self.information_delta is not None and not isinstance(
            self.information_delta, InformationDelta
        ):
            raise TypeError("delivery transition information delta must be typed")
        if self.runtime_failure is not None and not isinstance(self.runtime_failure, RuntimeFailure):
            raise TypeError("delivery transition Runtime failure must be typed")


@dataclass(frozen=True)
class ObservationDeliveryStore:
    """Keep only bounded Monitor digests, never model-visible state."""

    local_deliveries: tuple[LocalDeliveryRecord, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.local_deliveries)
        if len(records) > _MAX_LOCAL_DELIVERY_RECORDS or any(
            not isinstance(item, LocalDeliveryRecord) for item in records
        ):
            raise ValueError("local delivery lifecycle exceeds its fixed bound")
        object.__setattr__(self, "local_deliveries", records)

    def reduce(self, step: object, *, step_index: int) -> DeliveryTransition:
        if type(step).__name__ != "StepResult":
            raise TypeError("delivery reducer requires one committed StepResult")
        if type(step_index) is not int or step_index < 1:
            raise ValueError("delivery reducer requires a positive committed step")
        decision = getattr(step, "decision", None)
        discovery = getattr(step, "action_page_result", None)
        if isinstance(decision, LocalToolResult):
            operation = decision.tool_name
            arguments = decision.arguments
            result = decision.result
        elif discovery is not None:
            operation = "find_controls"
            arguments = {"query": getattr(decision, "query", "")}
            result = discovery.to_public_value()
        else:
            return DeliveryTransition(self, None, getattr(step, "runtime_failure", None))

        world_digest = "sha256:" + getattr(step, "public_world_delta").after_world_digest
        arguments_digest = _public_digest(arguments or {})
        result_digest = _public_digest(result)
        item_digests = tuple(dict.fromkeys(_public_digest(item) for item in _monitor_items(result)))[
            :_MAX_LOCAL_INFORMATION_ITEMS
        ]
        exact = next(
            (
                item
                for item in reversed(self.local_deliveries)
                if (item.operation, item.world_digest, item.arguments_digest, item.result_digest)
                == (operation, world_digest, arguments_digest, result_digest)
            ),
            None,
        )
        if exact is not None:
            delta = InformationDelta(
                InformationDeltaKind.EXACT_REPLAY,
                operation,
                world_digest,
                arguments_digest,
                result_digest,
            )
            return DeliveryTransition(self, delta, getattr(step, "runtime_failure", None))

        delivered = {
            digest
            for record in self.local_deliveries
            if record.world_digest == world_digest
            for digest in record.item_digests
        }
        new_digests = tuple(item for item in item_digests if item not in delivered)
        if new_digests:
            kind = InformationDeltaKind.NEW_INFORMATION
        elif not item_digests:
            kind = InformationDeltaKind.NO_MATCHES
        else:
            kind = InformationDeltaKind.NO_NEW_INFORMATION
        delta = InformationDelta(
            kind,
            operation,
            world_digest,
            arguments_digest,
            result_digest,
            _public_digest(item_digests),
            new_digests if kind is InformationDeltaKind.NEW_INFORMATION else (),
        )
        record = LocalDeliveryRecord(
            operation,
            world_digest,
            arguments_digest,
            result_digest,
            item_digests,
        )
        next_store = ObservationDeliveryStore(
            (*self.local_deliveries, record)[-_MAX_LOCAL_DELIVERY_RECORDS:]
        )
        return DeliveryTransition(next_store, delta, getattr(step, "runtime_failure", None))


def _monitor_items(result: Mapping[str, object]) -> tuple[object, ...]:
    """Select bounded novelty atoms without retaining the result body."""

    for field_name in ("items", "matches"):
        values = result.get(field_name)
        if isinstance(values, tuple | list):
            return tuple(values)
    return (result,)


def _public_digest(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def current_findings_digest(observation: WorldObservation) -> str:
    """Digest current public scalar findings without Runtime or observation identity."""

    source_coverage = {
        key: item.coverage
        for item in observation.sources
        for key in (item.observation_id, item.surface)
    }
    findings = sorted(
        (
            (
                public_subject_semantics(observation, fact.subject_id),
                fact.predicate,
                fact.value,
                source_coverage.get(fact.source_id, CoverageState.COMPLETE).value,
            )
            for fact in observation.facts
            if is_public_scalar(fact.value)
            and source_coverage.get(fact.source_id, CoverageState.COMPLETE) is not CoverageState.STALE
        ),
        key=lambda item: json.dumps(
            to_json_compatible(item),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ),
    )
    encoded = json.dumps(findings, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()

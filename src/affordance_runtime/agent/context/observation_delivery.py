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

from affordance_runtime.agent.context.contracts import sanitize_history_arguments
from affordance_runtime.agent.decisions import LocalToolResult, RequestObservation, ToolRejectedResult
from affordance_runtime.agent.public_values import is_public_scalar
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationQueryDisposition,
    ObservationQueryOutcome,
    QueryScopeLocator,
    ResultLocator,
)
from affordance_runtime.world.public_semantic_digest import target_semantics

_MAX_LOCAL_DELIVERY_RECORDS = 64
_MAX_LOCAL_INFORMATION_ITEMS = 32


class InformationDeltaKind(StrEnum):
    NEW_INFORMATION = "new_information"
    NO_USABLE_INFORMATION = "no_usable_information"
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
        if isinstance(decision, ToolRejectedResult):
            # A typed rejection contains no task evidence.  Its dedicated
            # Monitor transition owns the failure; novelty must not describe
            # the rejected call as information progress.
            return DeliveryTransition(self, None, getattr(step, "runtime_failure", None))
        if isinstance(decision, RequestObservation):
            outcome = getattr(step, "observation_outcome", None)
            if outcome is None:
                return DeliveryTransition(self, None, getattr(step, "runtime_failure", None))
            return self._reduce_observation(step, decision, outcome)
        if isinstance(decision, LocalToolResult):
            operation = decision.tool_name
            arguments = decision.arguments
            result = decision.result
        elif discovery is not None:
            # Action discovery exposes current capabilities.  Its rows are not
            # task evidence and must not reset the information-progress
            # Monitor merely because another query returned different controls.
            return DeliveryTransition(self, None, getattr(step, "runtime_failure", None))
        else:
            return DeliveryTransition(self, None, getattr(step, "runtime_failure", None))

        world_digest = "sha256:" + getattr(step, "public_world_delta").after_world_digest
        arguments_digest = _public_digest(arguments or {})
        semantic_result = sanitize_history_arguments(
            result,
            ephemeral_paths=decision.ephemeral_result_paths,
        )
        if not isinstance(semantic_result, Mapping):
            raise TypeError("local tool result projection must remain an object")
        result_digest = _public_digest(semantic_result)
        item_digests = tuple(
            dict.fromkeys(_public_digest(item) for item in _monitor_items(semantic_result))
        )[
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

    def _reduce_observation(
        self,
        step: object,
        decision: RequestObservation,
        outcome: ObservationQueryOutcome,
    ) -> DeliveryTransition:
        """Reduce one typed perception result to novelty facts, never a second memory."""

        before = getattr(step, "before_world")
        after = getattr(step, "after_world")
        world_digest = "sha256:" + getattr(step, "public_world_delta").after_world_digest
        operation = "request_evidence"
        arguments_digest = _public_digest(_observation_attempt(decision, before))
        item_digests = _observation_fact_digests(outcome, after)
        result_digest = _public_digest(_observation_result_receipt(outcome, item_digests))
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
            return DeliveryTransition(
                self,
                InformationDelta(
                    InformationDeltaKind.EXACT_REPLAY,
                    operation,
                    world_digest,
                    arguments_digest,
                    result_digest,
                ),
                getattr(step, "runtime_failure", None),
            )

        delivered = {
            digest
            for record in self.local_deliveries
            for digest in record.item_digests
        }
        already_current = set(_world_information_digests(before))
        new_digests = tuple(
            item for item in item_digests if item not in delivered and item not in already_current
        )
        if outcome.disposition in {
            ObservationQueryDisposition.UNKNOWN,
            ObservationQueryDisposition.FAILED,
        }:
            kind = InformationDeltaKind.NO_USABLE_INFORMATION
        elif new_digests:
            kind = InformationDeltaKind.NEW_INFORMATION
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


def _observation_attempt(
    decision: RequestObservation,
    world: WorldObservation,
) -> Mapping[str, object]:
    targets = {item.target_id: item for item in world.targets}
    bases = {
        item.target_id: (item.role, item.label, to_json_compatible(item.state))
        for item in world.targets
    }
    return {
        "purpose": decision.purpose.value,
        "subjects": tuple(
            target_semantics(targets[item], bases)
            for item in decision.subject_ids
            if item in targets
        ),
        "candidates": tuple(
            target_semantics(targets[item], bases)
            for item in decision.candidate_ids
            if item in targets
        ),
        "atomic_query": decision.atomic_query.strip(),
        "predicate": decision.predicate.strip(),
        "max_results": decision.max_results,
    }


def _observation_result_receipt(
    outcome: ObservationQueryOutcome,
    item_digests: tuple[str, ...],
) -> Mapping[str, object]:
    return {
        "purpose": outcome.purpose.value,
        "status": outcome.disposition.value,
        "facts": item_digests,
        "observed_locators": tuple(
            _observation_locator(item.locator) for item in outcome.observed_items
        ),
        "unknown": tuple(
            {
                "locator": _observation_locator(item.locator),
                "reason": item.reason.value,
            }
            for item in outcome.unknown_items
        ),
        "failure_reason": outcome.failure_reason.value if outcome.failure_reason is not None else "",
    }


def _observation_locator(locator: object) -> Mapping[str, object]:
    if isinstance(locator, InputLocator):
        return {"kind": locator.kind, "input_indices": locator.input_indices}
    if isinstance(locator, ResultLocator):
        return {"kind": locator.kind, "result_index": locator.result_index}
    if isinstance(locator, QueryScopeLocator):
        return {"kind": locator.kind}
    raise TypeError("observation outcome locator must be typed")


def _observation_fact_digests(
    outcome: ObservationQueryOutcome,
    world: WorldObservation,
) -> tuple[str, ...]:
    targets = {item.target_id: item for item in world.targets}
    bases = {
        item.target_id: (item.role, item.label, to_json_compatible(item.state))
        for item in world.targets
    }
    facts = {item.fact_id: item for item in world.facts}
    operations = _target_operations(world)
    atoms: list[object] = []
    for observed in outcome.observed_items:
        atoms.extend(
            ("subject", target_semantics(targets[subject], bases))
            for subject in observed.subject_ids
            if subject in targets
        )
        atoms.extend(
            (
                "actions",
                target_semantics(targets[subject], bases),
                operations[subject],
            )
            for subject in observed.subject_ids
            if subject in targets and subject in operations
        )
        for evidence_ref in observed.evidence_refs:
            fact = facts.get(evidence_ref)
            if fact is None or fact.subject_id not in targets:
                continue
            atoms.append(
                (
                    "fact",
                    target_semantics(targets[fact.subject_id], bases),
                    fact.predicate,
                    to_json_compatible(fact.value),
                )
            )
    return tuple(dict.fromkeys(_public_digest(item) for item in atoms))[:_MAX_LOCAL_INFORMATION_ITEMS]


def _world_information_digests(world: WorldObservation) -> tuple[str, ...]:
    targets = {item.target_id: item for item in world.targets}
    bases = {
        item.target_id: (item.role, item.label, to_json_compatible(item.state))
        for item in world.targets
    }
    atoms: list[object] = [
        ("subject", target_semantics(item, bases))
        for item in world.targets
    ]
    atoms.extend(
        (
            "fact",
            target_semantics(targets[fact.subject_id], bases),
            fact.predicate,
            to_json_compatible(fact.value),
        )
        for fact in world.facts
        if fact.subject_id in targets
    )
    atoms.extend(
        ("actions", target_semantics(targets[subject], bases), actions)
        for subject, actions in _target_operations(world).items()
        if subject in targets
    )
    return tuple(dict.fromkeys(_public_digest(item) for item in atoms))


def _target_operations(world: WorldObservation) -> Mapping[str, tuple[str, ...]]:
    operations: dict[str, set[str]] = {}
    for binding in world.bindings:
        operations.setdefault(binding.target_id, set()).add(binding.semantic_action)
    return {
        subject: tuple(sorted(values))
        for subject, values in operations.items()
    }


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
    target_bases = {
        target.target_id: (
            target.role,
            target.label,
            to_json_compatible(target.state),
        )
        for target in observation.targets
    }
    subjects = {
        target.target_id: target_semantics(target, target_bases)
        for target in observation.targets
    }
    findings = sorted(
        (
            (
                subjects.get(fact.subject_id, ("unknown_public_subject",)),
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

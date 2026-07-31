"""Single projection from canonical task provenance to runtime source references."""

from __future__ import annotations

from affordance_runtime.simplified_runtime_contracts import SourceReference
from affordance_runtime.task_intake import (
    SourcedTaskClaim,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
)


def task_source_refs(task: TaskSpec) -> tuple[SourceReference, ...]:
    refs = tuple(ref for claim in task.source_claims for ref in _claim_refs(claim))
    if refs:
        return refs
    source_id = task.source_request_ref or task.task_id
    return (SourceReference(source_id, f"{source_id}:whole_request"),)


def obligation_source_refs(
    obligation: TaskObligationSpec,
    task: TaskSpec | None = None,
) -> tuple[SourceReference, ...]:
    if task is not None:
        claim_ids = set(obligation.claim_ids)
        refs = tuple(
            ref
            for claim in task.source_claims
            if claim.claim_id in claim_ids
            for ref in _claim_refs(claim)
        )
        return refs or task_source_refs(task)
    source_units = tuple(
        dict.fromkeys(
            unit
            for requirement in obligation.typed_evidence_requirements
            for unit in requirement.source_constraints
        )
    )
    return tuple(SourceReference(unit, unit) for unit in source_units) or (
        SourceReference(obligation.obligation_id, obligation.obligation_id),
    )


def subgoal_source_refs(subgoal_id: str, task: TaskSpec) -> tuple[SourceReference, ...]:
    obligation = next(
        (item for item in task.obligations if item.obligation_id == subgoal_id),
        None,
    )
    return obligation_source_refs(obligation, task) if obligation else task_source_refs(task)


def obligation_value_source(
    obligation: TaskObligationSpec,
    task: TaskSpec | None,
) -> tuple[str, tuple[SourceReference, ...]] | None:
    if task is None or obligation.value_source != TaskObligationValueSource.OBLIGATION_OUTPUT:
        return None
    source = next(
        (
            item
            for item in task.obligations
            if item.obligation_id == obligation.value_obligation_id
        ),
        None,
    )
    if source is None:
        return None
    return source.subject, obligation_source_refs(source, task)


def _claim_refs(claim: SourcedTaskClaim) -> tuple[SourceReference, ...]:
    units = claim.source_unit_ids or (f"{claim.source_ref}:{claim.claim_id}",)
    return tuple(SourceReference(claim.source_ref, unit, claim.claim_id) for unit in units)

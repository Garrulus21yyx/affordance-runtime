"""Single projection from canonical task provenance to runtime source references."""

from __future__ import annotations

from affordance_runtime.simplified_runtime_contracts import SourceReference
from affordance_runtime.task_intake import TaskSpec


def task_source_refs(task: TaskSpec) -> tuple[SourceReference, ...]:
    anchor_ids = tuple(
        dict.fromkeys(
            anchor
            for requirement in task.requirements
            for anchor in requirement.source_anchor_refs
        )
    )
    source_id = task.source_envelope_ref or task.source_request_ref or task.task_id
    return tuple(SourceReference(source_id, anchor) for anchor in anchor_ids)

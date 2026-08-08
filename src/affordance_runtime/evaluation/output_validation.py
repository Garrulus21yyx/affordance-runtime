"""Deterministic target-path requested-output and file-integrity checks."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.task.contracts import TaskGoal


def validate_required_outputs(
    task: TaskGoal,
    evaluation: TaskEvaluation,
    evidence_index: WorldEvidenceIndex,
) -> None:
    outputs = {item.output_id: item for item in evaluation.outputs}
    missing = tuple(item for item in task.requested_outputs if item not in outputs)
    if missing:
        raise ValueError("COMPLETE task evaluation is missing a requested output")
    for output_id in task.requested_outputs:
        if any(not evidence_index.resolve(ref) for ref in outputs[output_id].evidence_refs):
            raise ValueError("requested output evidence does not resolve in the current observation")
    integrity = task.evaluation_spec.required_output_integrity if task.evaluation_spec is not None else {}
    if not integrity:
        return
    if not isinstance(integrity, Mapping):
        raise ValueError("required output integrity contract is unsupported")
    for output_id, requirement in integrity.items():
        if output_id not in outputs:
            raise ValueError("required output integrity references a missing requested output")
        _validate_file_requirement(output_id, requirement, outputs[output_id], evidence_index)


def _validate_file_requirement(output_id: str, requirement: object, output, evidence_index: WorldEvidenceIndex) -> None:
    if not isinstance(requirement, Mapping) or set(requirement) != {"path", "sha256"}:
        raise ValueError("required output integrity contract is unsupported")
    path_value = requirement.get("path")
    digest = requirement.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("required output integrity path is invalid")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
        raise ValueError("required output SHA-256 is invalid")
    if not isinstance(output.value, Mapping) or set(output.value) != {"path", "sha256"}:
        raise ValueError("evaluated output value does not match the required integrity shape")
    if output.value.get("path") != path_value or output.value.get("sha256") != digest:
        raise ValueError("evaluated output value does not match required path and SHA-256")
    records = tuple(evidence_index.resolve_record(ref) for ref in output.evidence_refs)
    if not any(record is not None and record.kind == "artifact" and record.artifact_kind == output_id for record in records):
        raise ValueError("evaluated output evidence is not the corresponding current artifact")
    path = Path(path_value)
    if not path.is_file():
        raise ValueError("required output path is not a regular file")
    actual = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            actual.update(chunk)
    if actual.hexdigest() != digest.casefold():
        raise ValueError("required output SHA-256 does not match")

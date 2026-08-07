"""Actual output materialization with digest, lineage, and privacy closure."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from affordance_runtime.contracts import ExecutionReceipt
from affordance_runtime.execution_context import ensure_secret_free
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    OutputMaterialization,
    OutputSpec,
)


@dataclass(frozen=True)
class OutputMaterializer:
    """Create a value only from admitted observed evidence, never declarations."""

    def from_evaluation(
        self,
        *,
        task_spec: TaskSpec,
        output_spec: OutputSpec,
        evaluation: CriterionEvaluation,
        observation_ref: str,
        step_id: str = "",
        contract_id: str = "",
    ) -> OutputMaterialization | None:
        if evaluation.status != CriterionStatus.SATISFIED:
            return None
        if evaluation.observed_value is None or not evaluation.evidence_refs:
            return None
        if output_spec.source_binding_required and not evaluation.source_binding_refs:
            return None
        if not _schema_valid(output_spec.schema_id, evaluation.observed_value):
            return None
        if _contains_secret(evaluation.observed_value):
            return None
        return OutputMaterialization(
            output_id=output_spec.output_id,
            materialization_criterion_id=output_spec.materialization_criterion_id,
            schema_digest=_digest({"schema_id": output_spec.schema_id}),
            content_digest=_digest(evaluation.observed_value),
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            observation_ref=observation_ref,
            source_refs=evaluation.evidence_refs,
            source_binding_refs=evaluation.source_binding_refs,
            value=evaluation.observed_value,
            step_id=step_id,
            contract_id=contract_id,
            redaction_policy_ref=output_spec.redaction_policy_ref,
            access_policy_ref=output_spec.access_policy_ref,
            retention_policy_ref=output_spec.retention_policy_ref,
        )

    def from_artifact_receipt(
        self,
        *,
        task_spec: TaskSpec,
        output_spec: OutputSpec,
        evaluation: CriterionEvaluation,
        receipt: ExecutionReceipt,
        observation_ref: str,
        step_id: str = "",
        contract_id: str = "",
    ) -> OutputMaterialization | None:
        """Materialize a local artifact only when receipt and final evidence agree."""

        if not output_spec.schema_id.startswith("artifact:file@"):
            return None
        if (
            evaluation.status != CriterionStatus.SATISFIED
            or not evaluation.authoritative_final_recheck
            or not evaluation.evidence_refs
            or (output_spec.source_binding_required and not evaluation.source_binding_refs)
            or not receipt.success
            or (contract_id and receipt.contract_id != contract_id)
        ):
            return None
        path_text = str(receipt.evidence.get("path") or "")
        receipt_digest = str(receipt.evidence.get("sha256") or "").removeprefix("sha256:")
        if not path_text or len(receipt_digest) != 64 or _contains_secret(path_text):
            return None
        path = Path(path_text)
        if not path.is_file():
            return None
        try:
            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None
        if actual_digest != receipt_digest or not _contains_scalar(evaluation.observed_value, receipt_digest):
            return None
        return OutputMaterialization(
            output_id=output_spec.output_id,
            materialization_criterion_id=output_spec.materialization_criterion_id,
            schema_digest=_digest({"schema_id": output_spec.schema_id}),
            content_digest=f"sha256:{actual_digest}",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            observation_ref=observation_ref,
            source_refs=evaluation.evidence_refs,
            source_binding_refs=evaluation.source_binding_refs,
            artifact_ref=str(path),
            step_id=step_id,
            contract_id=receipt.contract_id,
            redaction_policy_ref=output_spec.redaction_policy_ref,
            access_policy_ref=output_spec.access_policy_ref,
            retention_policy_ref=output_spec.retention_policy_ref,
        )


def _digest(value: object) -> str:
    payload = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _contains_secret(value: Any) -> bool:
    try:
        ensure_secret_free(value)
    except ValueError:
        return True
    return False


def _contains_scalar(value: Any, expected: str) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_scalar(item, expected) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_scalar(item, expected) for item in value)
    return str(value).removeprefix("sha256:") == expected


def _schema_valid(schema_id: str, value: Any) -> bool:
    kind = schema_id.split(":", 1)[-1].split("@", 1)[0].casefold()
    if kind in {"any", "json", "json:any"}:
        return True
    if kind in {"string", "text"}:
        return isinstance(value, str)
    if kind in {"object", "record"}:
        return isinstance(value, Mapping)
    if kind in {"array", "list"}:
        return isinstance(value, (list, tuple))
    if kind in {"number", "float", "integer", "int"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False

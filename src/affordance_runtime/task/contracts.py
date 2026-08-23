"""Execution-neutral task authority and optional strict evaluation profile."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.task.public_input import admit_public_task_value


class RiskProfile(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class LoopBudget:
    max_turns: int = 20
    max_observations: int = 40

    def __post_init__(self) -> None:
        if not 1 <= self.max_turns <= 100:
            raise ValueError("max_turns must be within [1, 100]")
        if self.max_observations < self.max_turns:
            raise ValueError("max_observations must cover max_turns")


@dataclass(frozen=True)
class MaterialBinding:
    name: str
    digest: str
    media_type: str = "application/octet-stream"
    public_reference: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.digest.strip():
            raise ValueError("material binding requires name and digest")
        if self.public_reference and not self.public_reference.strip():
            raise ValueError("material public reference cannot be blank")


@dataclass(frozen=True)
class EvaluationSpec:
    """Strict checks constrain evaluation; they never grant action authority."""

    success_expression: dict[str, Any]
    required_output_integrity: dict[str, Any] = field(default_factory=dict)
    authoritative_checks: tuple[str, ...] = ()
    strict_source_lineage: bool = False

    def __post_init__(self) -> None:
        if not self.success_expression:
            raise ValueError("evaluation spec requires a success expression")
        object.__setattr__(self, "success_expression", freeze_json(self.success_expression))
        object.__setattr__(self, "required_output_integrity", freeze_json(self.required_output_integrity))
        object.__setattr__(self, "authoritative_checks", tuple(self.authoritative_checks))


@dataclass(frozen=True)
class TaskGoal:
    """Stable what/boundary/done contract with no route or action sequence."""

    task_id: str
    instruction: str
    constraints: tuple[str, ...] = ()
    allowed_effects: tuple[str, ...] = ()
    forbidden_effects: tuple[str, ...] = ()
    inputs: dict[str, Any] = field(default_factory=dict)
    success_criteria: tuple[dict[str, Any], ...] = ()
    requested_outputs: tuple[str, ...] = ()
    risk_profile: RiskProfile = RiskProfile.READ_ONLY
    material_bindings: tuple[MaterialBinding, ...] = ()
    loop_budget: LoopBudget = field(default_factory=LoopBudget)
    evaluation_spec: EvaluationSpec | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.instruction.strip():
            raise ValueError("task goal requires identity and instruction")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("task goal revision must be a positive integer")
        if self.risk_profile != RiskProfile.READ_ONLY and not self.allowed_effects:
            raise ValueError("effectful task requires explicit allowed_effects")
        if len(self.instruction) > 16_384:
            raise ValueError("task instruction exceeds the public intake bound")
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "allowed_effects", tuple(self.allowed_effects))
        object.__setattr__(self, "forbidden_effects", tuple(self.forbidden_effects))
        admitted_public = admit_public_task_value(
            {"inputs": self.inputs, "success_criteria": self.success_criteria},
            path="task_public",
        )
        if not isinstance(admitted_public, dict):
            raise TypeError("task public admission changed the root object")
        inputs = admitted_public["inputs"]
        criteria = admitted_public["success_criteria"]
        if not isinstance(criteria, list | tuple):
            raise TypeError("task success criteria admission changed the sequence")
        object.__setattr__(self, "inputs", freeze_json(inputs))
        object.__setattr__(self, "success_criteria", tuple(freeze_json(item) for item in criteria))
        criterion_ids = tuple(criterion_id(item) for item in self.success_criteria)
        if any(not item.strip() for item in criterion_ids) or len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("success criterion IDs must be nonblank and unique")
        if any(not item.strip() for item in self.requested_outputs) or len(set(self.requested_outputs)) != len(
            self.requested_outputs
        ):
            raise ValueError("requested output IDs must be nonblank and unique")
        object.__setattr__(self, "requested_outputs", tuple(self.requested_outputs))
        object.__setattr__(self, "material_bindings", tuple(self.material_bindings))


def criterion_id(criterion: Mapping[str, Any]) -> str:
    explicit = criterion.get("criterion_id") or criterion.get("id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    normalized = json.dumps(to_json_compatible(criterion), sort_keys=True, separators=(",", ":"))
    return f"criterion:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}"

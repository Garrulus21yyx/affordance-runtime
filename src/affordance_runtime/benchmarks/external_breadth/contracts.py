"""Immutable census, capability, manifest, and campaign result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MiniWobCapabilityStatus(StrEnum):
    CURRENT_PRIMITIVES = "current_primitives"
    REQUIRES_UNSUPPORTED_PRIMITIVE = "requires_unsupported_primitive"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MiniWobRegistryCensus:
    package_name: str
    package_version: str
    core_version: str
    source_commit: str
    task_ids: tuple[str, ...]
    registry_digest: str


@dataclass(frozen=True)
class MiniWobTaskCapability:
    task_id: str
    status: MiniWobCapabilityStatus
    required_primitives: tuple[str, ...]
    reason_code: str
    source_reference: str


@dataclass(frozen=True)
class MiniWobBreadthCase:
    case_id: str
    task_id: str
    capability_profile: str
    required_primitives: tuple[str, ...]
    max_turns: int
    timeout_s: float
    seed: int


@dataclass(frozen=True)
class MiniWobBreadthManifest:
    schema_version: str
    campaign_id: str
    package_name: str
    package_version: str
    source_commit: str
    registry_digest: str
    capability_inventory_digest: str
    selection_namespace: str
    model_profile: str
    grounding_profile: str
    minimum_policy_call_interval_s: float
    cases: tuple[MiniWobBreadthCase, ...]


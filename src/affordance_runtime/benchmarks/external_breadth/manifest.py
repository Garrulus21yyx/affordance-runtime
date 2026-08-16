"""Frozen MiniWoB-60 seed-7 breadth manifest and digest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from affordance_runtime.benchmarks.external_breadth.capability_inventory import (
    build_capability_inventory,
    capability_inventory_digest,
    supported_candidates,
)
from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobBreadthCase,
    MiniWobBreadthManifest,
    MiniWobRegistryCensus,
)
from affordance_runtime.benchmarks.external_breadth.registry import PACKAGE_NAME, PACKAGE_VERSION, SOURCE_COMMIT
from affordance_runtime.benchmarks.external_breadth.selection import SELECTION_NAMESPACE, select_tasks

SCHEMA_VERSION = "miniwob-breadth-manifest.v1"
CAMPAIGN_ID = "miniwob-60-seed7-v2"
MODEL_PROFILE = "mistral-medium-3-5"
GROUNDING_PROFILE = "format-only.v1"
SEED = 7
MAX_TURNS = 10
TIMEOUT_S = 180.0
PACING_S = 7.5


def build_breadth_manifest(census: MiniWobRegistryCensus) -> MiniWobBreadthManifest:
    if census.package_name != PACKAGE_NAME or census.package_version != PACKAGE_VERSION:
        raise ValueError("registry census does not match the frozen MiniWoB package profile")
    if census.source_commit != SOURCE_COMMIT:
        raise ValueError("registry census does not match the reviewed MiniWoB source commit")
    inventory = build_capability_inventory(census)
    selected = select_tasks(supported_candidates(inventory))
    cases = tuple(
        MiniWobBreadthCase(
            f"miniwob-60-{index:02d}", item.task_id, item.status.value,
            item.required_primitives, MAX_TURNS, TIMEOUT_S, SEED,
        )
        for index, item in enumerate(selected, 1)
    )
    return MiniWobBreadthManifest(
        SCHEMA_VERSION, CAMPAIGN_ID, PACKAGE_NAME, PACKAGE_VERSION, SOURCE_COMMIT,
        census.registry_digest, capability_inventory_digest(inventory), SELECTION_NAMESPACE,
        MODEL_PROFILE, GROUNDING_PROFILE, PACING_S, cases,
    )


def breadth_manifest_digest(manifest: MiniWobBreadthManifest) -> str:
    encoded = json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()

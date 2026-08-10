from __future__ import annotations

from dataclasses import replace

from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus
from affordance_runtime.benchmarks.external_breadth.inventory_v2 import (
    build_capability_inventory_v2,
    capability_inventory_v2_digest,
    current_declared_capabilities,
    task_readiness,
)
from affordance_runtime.benchmarks.external_breadth.requirements import TaskReadiness


def test_v2_inventory_covers_registry_once_with_bounded_source_bound_records() -> None:
    inventory = build_capability_inventory_v2(_census())
    assert len(inventory) == len(_census().task_ids)
    assert len({item.task_id for item in inventory}) == len(inventory)
    assert all(item.source_references and item.confidence in {"high", "medium", "unassessed"} for item in inventory)
    serialized = repr(inventory).casefold()
    assert "expected_answer" not in serialized
    assert "reference_trajectory" not in serialized
    assert "raw_reward" not in serialized


def test_semantic_requirements_are_not_reduced_to_final_click_primitive() -> None:
    records = {item.task_id.rsplit(".", 1)[-1]: item for item in build_capability_inventory_v2(_census())}
    assert "visual_spatial" in records["grid-coordinate"].observation_requirements
    assert "table_extraction" in records["read-table"].observation_requirements
    assert "arithmetic" in records["simple-algebra"].reasoning_requirements
    assert "stateful_game" in records["tic-tac-toe"].reasoning_requirements
    assert "scroll" in records["click-scroll-list"].interaction_requirements


def test_readiness_requires_every_axis_and_unknown_is_unassessed() -> None:
    records = {item.task_id.rsplit(".", 1)[-1]: item for item in build_capability_inventory_v2(_census())}
    capabilities = current_declared_capabilities()
    assert task_readiness(records["enter-text"], capabilities) is TaskReadiness.DECLARED_SUPPORTED
    assert task_readiness(records["simple-algebra"], capabilities) is TaskReadiness.DECLARED_UNSUPPORTED
    assert task_readiness(records["unreviewed-sentinel"], capabilities) is TaskReadiness.UNASSESSED


def test_v2_digest_is_deterministic_and_requirement_sensitive() -> None:
    inventory = build_capability_inventory_v2(_census())
    capabilities = current_declared_capabilities()
    first = capability_inventory_v2_digest(_census(), inventory, capabilities)
    assert first == capability_inventory_v2_digest(_census(), inventory, capabilities)
    changed = (replace(inventory[0], reasoning_requirements=("unknown",)), *inventory[1:])
    assert first != capability_inventory_v2_digest(_census(), changed, capabilities)


def _census() -> MiniWobRegistryCensus:
    slugs = (
        "enter-text",
        "grid-coordinate",
        "read-table",
        "simple-algebra",
        "tic-tac-toe",
        "click-scroll-list",
        "unreviewed-sentinel",
    )
    return MiniWobRegistryCensus(
        "browsergym-miniwob", "0.14.3", "0.14.3", "7fd85d71a4b60325c6585396ec4f48377d049838",
        tuple(f"browsergym/miniwob.{slug}" for slug in slugs), "sha256:registry",
    )

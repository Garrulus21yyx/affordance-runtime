from affordance_runtime.benchmarks.external_smoke.manifest import REVIEWED_TASK_IDS
from affordance_runtime.surfaces.browsergym.inventory import (
    PINNED_VERSION,
    browsergym_api_inventory,
)


def test_pinned_package_registry_and_api_inventory() -> None:
    inventory = browsergym_api_inventory()
    if not inventory.available:
        return
    assert inventory.package_version == PINNED_VERSION == "0.14.3"
    assert all(item in inventory.registered_task_ids for item in REVIEWED_TASK_IDS)
    assert inventory.action_primitives == ("click", "fill", "select_option")
    assert inventory.reset_contract == "(observation, info)"
    assert inventory.step_contract == "(observation, reward, terminated, truncated, info)"
    assert inventory.accepted

"""Fail-closed inventory for the exact BrowserGym/MiniWoB package profile."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

PINNED_PACKAGE = "browsergym-miniwob"
PINNED_VERSION = "0.14.3"
REVIEWED_TASK_IDS = (
    "browsergym/miniwob.click-button",
    "browsergym/miniwob.enter-text",
    "browsergym/miniwob.choose-list",
)


@dataclass(frozen=True)
class BrowserGymApiInventory:
    available: bool
    package_version: str
    registered_task_ids: tuple[str, ...]
    reset_contract: str = "(observation, info)"
    step_contract: str = "(observation, reward, terminated, truncated, info)"
    action_primitives: tuple[str, ...] = ("click", "fill", "select_option")
    observation_fields: tuple[str, ...] = (
        "goal", "url", "axtree_object", "dom_object", "extra_element_properties",
    )
    verifier_fields: tuple[str, ...] = (
        "reward", "terminated", "truncated", "RAW_REWARD_GLOBAL", "DONE_GLOBAL",
    )

    @property
    def accepted(self) -> bool:
        return (
            self.available
            and self.package_version == PINNED_VERSION
            and all(item in self.registered_task_ids for item in REVIEWED_TASK_IDS)
        )


def browsergym_api_inventory() -> BrowserGymApiInventory:
    try:
        installed = version(PINNED_PACKAGE)
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]
    except (PackageNotFoundError, ImportError):
        return BrowserGymApiInventory(False, "", ())
    registered = tuple(sorted(str(item) for item in gym.registry if str(item).startswith("browsergym/miniwob.")))
    return BrowserGymApiInventory(True, installed, registered)

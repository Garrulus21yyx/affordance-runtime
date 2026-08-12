"""Short-lived Runtime-private BrowserGym element bindings."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    CanonicalBrowserControl,
)
from affordance_runtime.surfaces.visual.contracts import VisualRegionBinding


@dataclass(frozen=True)
class BrowserGymElementBinding:
    binding_id: str
    source_observation_id: str
    source_revision: str
    page_identity: str
    episode_identity: str
    private_element_id: str
    semantic_target_id: str
    supported_primitive: str
    canonical_control: CanonicalBrowserControl

    def option_value(self, public_label: str) -> str:
        try:
            return dict(self.canonical_control.private_options)[public_label]
        except KeyError as exc:
            raise ValueError("select value is outside the current finite option domain") from exc

    @property
    def option_values(self) -> tuple[tuple[str, str], ...]:
        return self.canonical_control.private_options


@dataclass(frozen=True)
class BrowserGymVisualBinding:
    """Runtime-private screenshot-bound pointer route for BrowserGym."""

    binding_id: str
    page_identity: str
    episode_identity: str
    region: VisualRegionBinding

    @property
    def source_observation_id(self) -> str:
        return self.region.source_observation_id

    @property
    def source_revision(self) -> str:
        return self.region.source_revision


BrowserGymPrivateBinding = BrowserGymElementBinding | BrowserGymVisualBinding


@dataclass
class BrowserGymBindingStore:
    _bindings: dict[str, BrowserGymPrivateBinding] = field(default_factory=dict, init=False)

    def replace(self, bindings: tuple[BrowserGymPrivateBinding, ...]) -> None:
        if len({item.binding_id for item in bindings}) != len(bindings):
            raise ValueError("BrowserGym private binding IDs must be unique")
        self._bindings = {item.binding_id: item for item in bindings}

    def get(self, binding_id: str) -> BrowserGymPrivateBinding | None:
        return self._bindings.get(binding_id)

    def clear(self) -> None:
        self._bindings.clear()

    @property
    def count(self) -> int:
        return len(self._bindings)

"""Short-lived Runtime-private BrowserGym element bindings."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.surfaces.browsergym.semantics import (
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
class BrowserGymDragDestination:
    semantic_target_id: str
    private_element_id: str
    canonical_control: CanonicalBrowserControl

    def __post_init__(self) -> None:
        if not self.semantic_target_id.strip() or not self.private_element_id.strip():
            raise ValueError("BrowserGym drag destination requires semantic and private identity")


@dataclass(frozen=True)
class BrowserGymDragBinding:
    """One snapshot-bound source and its finite current destination domain."""

    binding_id: str
    source_observation_id: str
    source_revision: str
    page_identity: str
    episode_identity: str
    private_element_id: str
    semantic_target_id: str
    supported_primitive: str
    canonical_control: CanonicalBrowserControl
    destinations: tuple[BrowserGymDragDestination, ...]

    def __post_init__(self) -> None:
        values = tuple(self.destinations)
        if not values or len({item.semantic_target_id for item in values}) != len(values):
            raise ValueError("BrowserGym drag destinations must be finite and unique")
        object.__setattr__(self, "destinations", values)

    def destination(self, semantic_target_id: str) -> BrowserGymDragDestination:
        match = next(
            (item for item in self.destinations if item.semantic_target_id == semantic_target_id),
            None,
        )
        if match is None:
            raise ValueError("drag destination is outside the current private binding")
        return match


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


BrowserGymPrivateBinding = BrowserGymElementBinding | BrowserGymDragBinding | BrowserGymVisualBinding


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

    @property
    def values(self) -> tuple[BrowserGymPrivateBinding, ...]:
        return tuple(self._bindings.values())

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


@dataclass(frozen=True)
class BrowserGymViewportBinding:
    """Runtime-private current viewport route for BrowserGym wheel scrolling."""

    binding_id: str
    source_observation_id: str
    source_revision: str
    page_identity: str
    episode_identity: str
    semantic_target_id: str
    supported_primitive: str
    viewport_width: int
    viewport_height: int

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.binding_id,
                self.source_observation_id,
                self.source_revision,
                self.page_identity,
                self.episode_identity,
                self.semantic_target_id,
                self.supported_primitive,
            )
        ):
            raise ValueError("BrowserGym viewport binding requires current identity")
        if self.viewport_width <= 0 or self.viewport_height <= 0:
            raise ValueError("BrowserGym viewport binding requires positive dimensions")


@dataclass(frozen=True)
class BrowserGymFocusedContextBinding:
    """Runtime-private route for BrowserGym page-level keyboard events."""

    binding_id: str
    source_observation_id: str
    source_revision: str
    page_identity: str
    episode_identity: str
    semantic_target_id: str
    supported_primitive: str
    focused_private_element_id: str = ""
    navigation_potential: bool = False

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.binding_id,
                self.source_observation_id,
                self.source_revision,
                self.page_identity,
                self.episode_identity,
                self.semantic_target_id,
                self.supported_primitive,
            )
        ):
            raise ValueError("BrowserGym focused-context binding requires current identity")
        if type(self.navigation_potential) is not bool:
            raise TypeError("BrowserGym focused-context navigation hint must be boolean")


@dataclass(frozen=True)
class BrowserGymNavigationBinding:
    """Runtime-private current browser-context route for BrowserGym globals."""

    binding_id: str
    source_observation_id: str
    source_revision: str
    page_identity: str
    episode_identity: str
    semantic_target_id: str
    supported_primitive: str
    open_pages_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.binding_id,
                self.source_observation_id,
                self.source_revision,
                self.page_identity,
                self.episode_identity,
                self.semantic_target_id,
                self.supported_primitive,
            )
        ):
            raise ValueError("BrowserGym navigation binding requires current identity")
        if self.supported_primitive not in {
            "goto",
            "go_back",
            "go_forward",
            "new_tab",
            "tab_focus",
            "tab_close",
        }:
            raise ValueError("BrowserGym navigation binding primitive is unsupported")
        urls = tuple(self.open_pages_urls)
        if any(not isinstance(item, str) or not item for item in urls):
            raise ValueError("BrowserGym navigation binding tab identities are invalid")
        object.__setattr__(self, "open_pages_urls", urls)


BrowserGymPrivateBinding = (
    BrowserGymElementBinding
    | BrowserGymDragBinding
    | BrowserGymVisualBinding
    | BrowserGymViewportBinding
    | BrowserGymFocusedContextBinding
    | BrowserGymNavigationBinding
)


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

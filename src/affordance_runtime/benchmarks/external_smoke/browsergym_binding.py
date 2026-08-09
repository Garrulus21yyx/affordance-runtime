"""Short-lived Runtime-private BrowserGym element bindings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


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
    role: str
    label: str
    state_fingerprint: str
    state_keys: tuple[str, ...] = ()
    option_values: tuple[tuple[str, str], ...] = ()

    def option_value(self, public_label: str) -> str:
        try:
            return dict(self.option_values)[public_label]
        except KeyError as exc:
            raise ValueError("select value is outside the current finite option domain") from exc


@dataclass
class BrowserGymBindingStore:
    _bindings: dict[str, BrowserGymElementBinding] = field(default_factory=dict, init=False)

    def replace(self, bindings: tuple[BrowserGymElementBinding, ...]) -> None:
        if len({item.binding_id for item in bindings}) != len(bindings):
            raise ValueError("BrowserGym private binding IDs must be unique")
        self._bindings = {item.binding_id: item for item in bindings}

    def get(self, binding_id: str) -> BrowserGymElementBinding | None:
        return self._bindings.get(binding_id)

    def clear(self) -> None:
        self._bindings.clear()

    @property
    def count(self) -> int:
        return len(self._bindings)


def semantic_fingerprint(role: str, label: str, state: dict[str, object]) -> str:
    encoded = json.dumps((role, label, state), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()

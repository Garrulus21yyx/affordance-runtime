"""Run-scoped opaque entity identity for BrowserGym observations."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    CanonicalBrowserControl,
    CanonicalBrowserStructureNode,
)


@dataclass
class BrowserGymEntityIdentityMap:
    """Map stable private backend identity to one opaque page-incarnation ID."""

    _key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _issued: dict[str, tuple[str, str, str]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._key, bytes) or len(self._key) < 16:
            raise ValueError("BrowserGym entity identity key must be private and strong")

    def entity_id(
        self,
        control: CanonicalBrowserControl | CanonicalBrowserStructureNode,
        *,
        page_identity: str,
        episode_identity: str,
    ) -> str:
        if not page_identity or not episode_identity:
            raise ValueError("BrowserGym entity identity requires page and episode scope")
        backend_identity = (
            f"bid:{control.private_bid}"
            if control.private_bid
            else f"node:{control.private_node_id}"
        )
        if backend_identity in {"bid:", "node:"}:
            raise ValueError("BrowserGym entity has no stable backend identity")
        scope = (page_identity, episode_identity, backend_identity)
        encoded = "\0".join(scope).encode()
        digest = hmac.new(self._key, encoded, hashlib.sha256).hexdigest()[:32]
        entity_id = f"entity:{digest}"
        previous = self._issued.setdefault(entity_id, scope)
        if previous != scope:
            raise RuntimeError("BrowserGym opaque entity identity collision")
        return entity_id

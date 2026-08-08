"""Immutable WoT surface identity and transport result contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Mapping

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.action_vocabulary import action_metadata

if TYPE_CHECKING:
    from affordance_runtime.adapters.wot import ThingAffordanceModel
    from affordance_runtime.contracts import Affordance


class WotDeploymentScope(StrEnum):
    LOCAL_SIMULATION = "local_simulation"
    REMOTE_SERVICE = "remote_service"
    PHYSICAL_DEVICE = "physical_device"


class WotTransportStatus(StrEnum):
    NOT_SENT = "not_sent"
    SENT = "sent"
    SENT_UNKNOWN = "sent_unknown"


@dataclass(frozen=True)
class WotTransportResult:
    status: WotTransportStatus
    transport_success: bool
    error_type: str = ""
    value: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if _contains_sensitive_key(self.evidence):
            raise ValueError("WoT transport evidence contains sensitive fields")
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(self, "evidence", freeze_json(self.evidence))


@dataclass(frozen=True)
class WotAffordanceBinding:
    thing_id: str
    td_digest: str
    source_observation_id: str
    source_revision: str
    affordance_kind: str
    affordance_name: str
    source_affordance_id: str
    affordance_fingerprint: str
    href: str
    method: str
    content_type: str
    input_schema: dict[str, Any]
    security_scheme_ref: str
    min_interval_ms: float
    executor_id: str
    primitive_action: str
    semantic_action: str
    expires_at_s: float

    def __post_init__(self) -> None:
        required = (
            self.thing_id,
            self.td_digest,
            self.source_observation_id,
            self.source_revision,
            self.affordance_kind,
            self.affordance_name,
            self.source_affordance_id,
            self.affordance_fingerprint,
            self.href,
            self.method,
            self.content_type,
            self.security_scheme_ref,
            self.executor_id,
            self.primitive_action,
            self.semantic_action,
        )
        if not all(value.strip() for value in required):
            raise ValueError("WoT binding requires complete thing, TD, affordance, route, and security identity")
        if self.min_interval_ms < 0:
            raise ValueError("WoT minimum interval cannot be negative")
        object.__setattr__(self, "input_schema", freeze_json(self.input_schema))

    @classmethod
    def from_affordance(
        cls,
        source_observation_id: str,
        td_digest: str,
        model: ThingAffordanceModel,
        affordance: Affordance,
    ) -> WotAffordanceBinding:
        locator = affordance.locator
        state = affordance.state
        metadata = action_metadata("wot", affordance.action, dict(state.get("input_schema") or {}))
        return cls(
            model.thing_id,
            td_digest,
            source_observation_id,
            td_digest,
            affordance.role,
            affordance.label,
            affordance.id,
            affordance.target_fingerprint,
            str(locator.get("href") or ""),
            str(locator.get("method") or "").upper(),
            str(state.get("content_type") or "application/json"),
            to_json_compatible(state.get("input_schema") or {}),
            str(locator.get("security_scheme_ref") or ""),
            float(locator.get("min_interval_ms") or 0),
            "wot",
            metadata.primitive_action,
            metadata.semantic_action,
            affordance.lease.expires_at_s,
        )

    def private_payload(self) -> dict[str, Any]:
        return {
            "thing_id": self.thing_id,
            "td_digest": self.td_digest,
            "affordance_kind": self.affordance_kind,
            "affordance_name": self.affordance_name,
            "affordance_fingerprint": self.affordance_fingerprint,
            "href": self.href,
            "method": self.method,
            "content_type": self.content_type,
            "input_schema": self.input_schema,
            "security_scheme_ref": self.security_scheme_ref,
            "min_interval_ms": self.min_interval_ms,
        }

    @classmethod
    def from_state_source(
        cls,
        source_observation_id: str,
        td_digest: str,
        thing_id: str,
        source: Mapping[str, Any],
    ) -> WotAffordanceBinding:
        name = str(source.get("property") or "")
        href = str(source.get("href") or "")
        method = str(source.get("method") or "").upper()
        security_ref = str(source.get("security_scheme_ref") or "")
        fingerprint = "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "thing_id": thing_id,
                    "property": name,
                    "href": href,
                    "method": method,
                    "schema": to_json_compatible(source.get("property_schema") or {}),
                    "security": security_ref,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return cls(
            thing_id,
            td_digest,
            source_observation_id,
            td_digest,
            "property",
            name,
            f"wot_{thing_id}_{name}_read",
            fingerprint,
            href,
            method,
            str(source.get("content_type") or "application/json"),
            to_json_compatible(source.get("property_schema") or {}),
            security_ref,
            float(source.get("min_interval_ms") or 0),
            "wot",
            "read_property",
            "read",
            0,
        )


def thing_description_digest(td: Mapping[str, Any]) -> str:
    encoded = json.dumps(to_json_compatible(td), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _contains_sensitive_key(value: object) -> bool:
    sensitive = ("authorization", "credential", "api_key", "apikey", "token", "signed_url")
    if isinstance(value, Mapping):
        return any(
            any(marker in str(key).casefold() for marker in sensitive) or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return any(_contains_sensitive_key(item) for item in value)
    return False

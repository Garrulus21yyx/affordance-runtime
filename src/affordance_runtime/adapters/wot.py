"""W3C Thing Description adapter.

This keeps the useful non-web lesson from the Modular Action System: devices
should be parsed from hypermedia descriptions, not hard-coded endpoint names.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from affordance_runtime.adapters.wot_security import (
    RateLimit,
    SecurityScheme,
    active_security_ref,
    parse_rate_limit,
    parse_security_definitions,
)
from affordance_runtime.contracts import Affordance, AffordanceLease, RiskLevel, Surface
from affordance_runtime.immutable import FrozenSequence, freeze_json

_DEFAULT_METHOD = {
    "readproperty": "GET",
    "writeproperty": "PUT",
    "observeproperty": "GET",
    "invokeaction": "POST",
    "subscribeevent": "GET",
}
_OP_ACTION = {
    "readproperty": "read_property",
    "writeproperty": "write_property",
    "invokeaction": "invoke",
    "subscribeevent": "subscribe",
}


@dataclass(frozen=True)
class ThingAffordanceModel:
    thing_id: str
    title: str
    base: str
    affordances: list[Affordance]
    state_sources: list[dict[str, Any]]
    security_schemes: Mapping[str, SecurityScheme] = MappingProxyType({})
    security_scheme_ref: str = ""
    rate_limit: RateLimit | None = None
    events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "affordances", FrozenSequence(self.affordances))
        object.__setattr__(self, "state_sources", freeze_json(self.state_sources))
        object.__setattr__(self, "security_schemes", MappingProxyType(dict(self.security_schemes)))
        object.__setattr__(self, "events", tuple(self.events))

    @property
    def security(self) -> SecurityScheme | None:
        return self.security_schemes.get(self.security_scheme_ref)


def _declared_ops(form: dict[str, Any]) -> list[str]:
    declared = form.get("op")
    return [declared] if isinstance(declared, str) else list(declared or [])


def _first_form(
    forms: list[dict[str, Any]],
    ops: tuple[str, ...],
    *,
    allow_implicit: bool = False,
) -> dict[str, Any] | None:
    for form in forms:
        if any(op in _declared_ops(form) for op in ops):
            return form
    if allow_implicit:
        return next((form for form in forms if not _declared_ops(form)), None)
    return None


def _resolve_href(base: str, href: str) -> str:
    if href.startswith(("http://", "https://", "coap://", "mqtt://")):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/") if base else href


class WotAdapter:
    def parse(
        self,
        td: dict[str, Any],
        *,
        environment_revision: str,
        ttl_ms: int = 5_000,
        snapshot_id: str = "",
        page_revision: str = "",
    ) -> ThingAffordanceModel:
        thing_id = str(td.get("id") or td.get("title") or "thing")
        title = str(td.get("title") or thing_id)
        base = str(td.get("base") or "")
        security_schemes = parse_security_definitions(td)
        thing_security_ref = active_security_ref(
            td.get("security"),
            security_schemes,
            fallback=next(iter(security_schemes), ""),
        )
        thing_rate_limit = _parse_declared_rate_limit(td)
        def lease_for(name: str, form: dict[str, Any]) -> AffordanceLease:
            fingerprint = "sha256:" + hashlib.sha256(
                json.dumps({"thing_id": thing_id, "name": name, "form": form}, sort_keys=True).encode()
            ).hexdigest()
            return AffordanceLease.issue(
                environment_revision=environment_revision,
                ttl_ms=ttl_ms,
                provenance=["wot_td"],
                snapshot_id=snapshot_id,
                page_revision=page_revision or environment_revision,
                target_fingerprint=fingerprint,
            )
        affordances: list[Affordance] = []
        state_sources: list[dict[str, Any]] = []

        for prop_name, prop in (td.get("properties") or {}).items():
            forms = list(prop.get("forms") or [])
            write_only = bool(prop.get("writeOnly", False))
            read_only = bool(prop.get("readOnly", False))
            read_form = _first_form(forms, ("readproperty", "observeproperty"), allow_implicit=True)
            if read_form is not None and not write_only:
                state_sources.append(
                    {
                        "thing_id": thing_id,
                        "property": prop_name,
                        "href": _resolve_href(base, str(read_form.get("href") or "")),
                        "method": str(read_form.get("htv:methodName") or _DEFAULT_METHOD["readproperty"]).upper(),
                        "read_only": read_only,
                    }
                )
            if not read_only:
                write_form = _first_form(forms, ("writeproperty",), allow_implicit=True)
                if write_form is not None:
                    affordances.append(
                        self._affordance(
                            thing_id,
                            prop_name,
                            "writeproperty",
                            write_form,
                            base,
                            lease_for(prop_name, write_form),
                            "property",
                            input_schema=_schema_of(prop),
                            security_schemes=security_schemes,
                            security_scheme_ref=active_security_ref(
                                write_form.get("security"), security_schemes, fallback=thing_security_ref
                            ),
                            rate_limit=_parse_declared_rate_limit(write_form) or thing_rate_limit,
                            extra_state={"read_only": read_only, "write_only": write_only},
                        )
                    )

        for action_name, action in (td.get("actions") or {}).items():
            form = _first_form(list(action.get("forms") or []), ("invokeaction",), allow_implicit=True)
            if form is not None:
                affordances.append(
                    self._affordance(
                        thing_id,
                        action_name,
                        "invokeaction",
                        form,
                        base,
                        lease_for(action_name, form),
                        "action",
                        input_schema=action.get("input"),
                        output_schema=action.get("output"),
                        security_schemes=security_schemes,
                        security_scheme_ref=active_security_ref(
                            form.get("security"), security_schemes, fallback=thing_security_ref
                        ),
                        rate_limit=_parse_declared_rate_limit(form) or thing_rate_limit,
                    )
                )

        events: list[str] = []
        for event_name, event in (td.get("events") or {}).items():
            events.append(str(event_name))
            form = _first_form(list(event.get("forms") or []), ("subscribeevent",), allow_implicit=True)
            if form is not None:
                affordances.append(
                    self._affordance(
                        thing_id,
                        str(event_name),
                        "subscribeevent",
                        form,
                        base,
                        lease_for(str(event_name), form),
                        "event",
                        input_schema=event.get("data"),
                        security_schemes=security_schemes,
                        security_scheme_ref=active_security_ref(
                            form.get("security"), security_schemes, fallback=thing_security_ref
                        ),
                        rate_limit=_parse_declared_rate_limit(form) or thing_rate_limit,
                    )
                )

        return ThingAffordanceModel(
            thing_id=thing_id,
            title=title,
            base=base,
            affordances=affordances,
            state_sources=state_sources,
            security_schemes=security_schemes,
            security_scheme_ref=thing_security_ref,
            rate_limit=thing_rate_limit,
            events=tuple(events),
        )

    def _affordance(
        self,
        thing_id: str,
        name: str,
        op: str,
        form: dict[str, Any],
        base: str,
        lease: AffordanceLease,
        role: str,
        *,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        security_schemes: Mapping[str, SecurityScheme],
        security_scheme_ref: str,
        rate_limit: RateLimit | None,
        extra_state: dict[str, Any] | None = None,
    ) -> Affordance:
        href = _resolve_href(base, str(form.get("href") or ""))
        if not href:
            raise ValueError(f"affordance {thing_id}.{name} has no href")
        locator: dict[str, Any] = {
            "thing_id": thing_id,
            "href": href,
            "method": str(form.get("htv:methodName") or _DEFAULT_METHOD[op]).upper(),
        }
        if security_scheme_ref:
            locator["security_scheme_ref"] = security_scheme_ref
        state: dict[str, Any] = {
            "content_type": form.get("contentType", "application/json"),
            "input_schema": input_schema or {},
        }
        if output_schema is not None:
            state["output_schema"] = output_schema
        if security_scheme_ref:
            scheme = security_schemes[security_scheme_ref]
            state["security"] = {
                "scheme_ref": security_scheme_ref,
                "scheme": scheme.scheme,
                "location": scheme.location,
                "field_name": scheme.field_name,
            }
        if rate_limit is not None:
            state["rate_limit"] = rate_limit.to_public_dict()
            locator["min_interval_ms"] = rate_limit.min_interval_ms
        if extra_state:
            state.update(extra_state)
        return Affordance(
            id=f"wot_{thing_id}_{name}",
            surface=Surface.WOT,
            role=role,
            label=name,
            action=_OP_ACTION.get(op, "invoke"),
            locator=locator,
            lease=lease,
            backend_candidates=["wot"],
            confidence=1.0,
            state=state,
            risk=RiskLevel.MEDIUM if op == "invokeaction" else RiskLevel.LOW,
            evidence=[href],
        )


def _schema_of(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("type", "minimum", "maximum", "enum", "readOnly", "writeOnly")
    return {key: value[key] for key in keys if key in value}


def _parse_declared_rate_limit(value: Mapping[str, Any]) -> RateLimit | None:
    for key in ("rateLimit", "wot:rateLimit", "rate_limit"):
        parsed = parse_rate_limit(value.get(key))
        if parsed is not None:
            return parsed
    return None

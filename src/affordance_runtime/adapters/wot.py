"""W3C Thing Description adapter.

This keeps the useful non-web lesson from the Modular Action System: devices
should be parsed from hypermedia descriptions, not hard-coded endpoint names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affordance_runtime.contracts import Affordance, AffordanceLease, RiskLevel, Surface

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


def _declared_ops(form: dict[str, Any]) -> list[str]:
    declared = form.get("op")
    return [declared] if isinstance(declared, str) else list(declared or [])


def _first_form(forms: list[dict[str, Any]], ops: tuple[str, ...]) -> dict[str, Any] | None:
    for form in forms:
        if any(op in _declared_ops(form) for op in ops):
            return form
    return forms[0] if forms else None


def _resolve_href(base: str, href: str) -> str:
    if href.startswith(("http://", "https://", "coap://", "mqtt://")):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/") if base else href


class WotAdapter:
    def parse(self, td: dict[str, Any], *, environment_revision: str, ttl_ms: int = 5_000) -> ThingAffordanceModel:
        thing_id = str(td.get("id") or td.get("title") or "thing")
        title = str(td.get("title") or thing_id)
        base = str(td.get("base") or "")
        lease = AffordanceLease.issue(
            environment_revision=environment_revision,
            ttl_ms=ttl_ms,
            provenance=["wot_td"],
        )
        affordances: list[Affordance] = []
        state_sources: list[dict[str, Any]] = []

        for prop_name, prop in (td.get("properties") or {}).items():
            forms = list(prop.get("forms") or [])
            read_form = _first_form(forms, ("readproperty", "observeproperty"))
            if read_form is not None:
                state_sources.append(
                    {
                        "thing_id": thing_id,
                        "property": prop_name,
                        "href": _resolve_href(base, str(read_form.get("href") or "")),
                        "method": str(read_form.get("htv:methodName") or _DEFAULT_METHOD["readproperty"]).upper(),
                    }
                )
            if not prop.get("readOnly", False):
                write_form = _first_form(forms, ("writeproperty",))
                if write_form is not None:
                    affordances.append(self._affordance(thing_id, prop_name, "writeproperty", write_form, base, lease, "property"))

        for action_name, action in (td.get("actions") or {}).items():
            form = _first_form(list(action.get("forms") or []), ("invokeaction",))
            if form is not None:
                affordances.append(self._affordance(thing_id, action_name, "invokeaction", form, base, lease, "action"))

        return ThingAffordanceModel(
            thing_id=thing_id,
            title=title,
            base=base,
            affordances=affordances,
            state_sources=state_sources,
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
    ) -> Affordance:
        href = _resolve_href(base, str(form.get("href") or ""))
        if not href:
            raise ValueError(f"affordance {thing_id}.{name} has no href")
        return Affordance(
            id=f"wot_{thing_id}_{name}",
            surface=Surface.WOT,
            role=role,
            label=name,
            action=_OP_ACTION.get(op, "invoke"),
            locator={"thing_id": thing_id, "href": href, "method": str(form.get("htv:methodName") or _DEFAULT_METHOD[op]).upper()},
            lease=lease,
            confidence=1.0,
            state={"content_type": form.get("contentType", "application/json")},
            risk=RiskLevel.MEDIUM if op == "invokeaction" else RiskLevel.LOW,
            evidence=[href],
        )


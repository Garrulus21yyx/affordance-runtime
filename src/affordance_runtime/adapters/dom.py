"""DOM to Page Affordance Model adapter.

Migrated and simplified from A-Modular-Action-System-Architecture's
`DomTransducer`: raw HTML becomes compact, typed, lease-bound affordances.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from affordance_runtime.contracts import Affordance, AffordanceLease, RiskLevel, Surface

_INTERACTIVE_TAGS = frozenset(["a", "button", "input", "select", "textarea", "label", "form", "option"])
_STRIP_TAGS = frozenset(["script", "style", "meta", "link", "noscript", "head", "svg"])
_VOID_STRIP_TAGS = frozenset(["meta", "link"])
_ARIA_ACTION_MAP = {
    "button": "click",
    "link": "click",
    "textbox": "type",
    "combobox": "select",
    "checkbox": "click",
    "radio": "click",
}
_TAG_ACTION = {"button": "click", "a": "click", "select": "select", "textarea": "type"}
_INPUT_TYPE_ACTION = {
    "text": "type",
    "number": "type",
    "email": "type",
    "password": "type",
    "search": "type",
    "checkbox": "click",
    "radio": "click",
    "submit": "click",
    "button": "click",
}
_SELECTOR_CONFIDENCE = {"id": 1.0, "bid": 0.99, "testid": 0.97, "name": 0.85, "class": 0.7, "positional": 0.55}


class _InteractiveParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth: int | None = None
        self._depth = 0
        self._tag_counts: dict[str, int] = {}
        self._open: list[dict[str, Any]] = []
        self.total_nodes = 0
        self.nodes: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        self.total_nodes += 1
        if self._skip_depth is None and tag in _STRIP_TAGS:
            if tag in _VOID_STRIP_TAGS:
                self._depth = max(0, self._depth - 1)
                return
            self._skip_depth = self._depth
            return
        if self._skip_depth is not None:
            if tag in _VOID_STRIP_TAGS:
                self._depth = max(0, self._depth - 1)
            return

        attr = {key: (value or "") for key, value in attrs}
        role = attr.get("role", "")
        if "hidden" in attr or attr.get("aria-hidden") == "true":
            return
        if tag not in _INTERACTIVE_TAGS and role not in _ARIA_ACTION_MAP:
            return

        self._tag_counts[tag] = self._tag_counts.get(tag, 0) + 1
        node = {"tag": tag, "attr": attr, "nth": self._tag_counts[tag], "text_parts": []}
        self.nodes.append(node)
        self._open.append(node)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth is not None and self._depth == self._skip_depth:
            self._skip_depth = None
        if self._open and self._open[-1]["tag"] == tag:
            self._open.pop()
        self._depth = max(0, self._depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth is None and self._open:
            text = data.strip()
            if text:
                self._open[-1]["text_parts"].append(text)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_STRIP_TAGS:
            self.handle_endtag(tag)


@dataclass(frozen=True)
class PageAffordanceModel:
    page_id: str
    url: str
    environment_revision: str
    snapshot_id: str
    page_revision: str
    affordances: list[Affordance]
    raw_node_count: int
    kept_node_count: int


def _escape_attr(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _selector_for(node: dict[str, Any]) -> tuple[str, float]:
    attr, tag = node["attr"], node["tag"]
    if attr.get("id"):
        return f"#{attr['id']}", _SELECTOR_CONFIDENCE["id"]
    if attr.get("bid"):
        return f"[bid='{_escape_attr(attr['bid'])}']", _SELECTOR_CONFIDENCE["bid"]
    if attr.get("data-testid"):
        return f"[data-testid='{_escape_attr(attr['data-testid'])}']", _SELECTOR_CONFIDENCE["testid"]
    if attr.get("name"):
        return f"{tag}[name='{_escape_attr(attr['name'])}']", _SELECTOR_CONFIDENCE["name"]
    if attr.get("class"):
        return f"{tag}.{attr['class'].split()[0]}", _SELECTOR_CONFIDENCE["class"]
    return f"{tag}:nth-of-type({node['nth']})", _SELECTOR_CONFIDENCE["positional"]


def _label_for(node: dict[str, Any]) -> str:
    attr = node["attr"]
    for key in ("aria-label", "value", "placeholder", "title", "alt"):
        if attr.get(key):
            return attr[key].strip()
    text = " ".join(node["text_parts"]).strip()
    if text:
        return text
    for key in ("name", "id"):
        if attr.get(key):
            return attr[key].strip()
    return node["tag"]


def _action_for(node: dict[str, Any]) -> str:
    attr, tag = node["attr"], node["tag"]
    role = attr.get("role", "")
    if role in _ARIA_ACTION_MAP:
        return _ARIA_ACTION_MAP[role]
    if tag == "input":
        return _INPUT_TYPE_ACTION.get(attr.get("type", "text").lower(), "type")
    return _TAG_ACTION.get(tag, "click")


class DomAdapter:
    def transduce(
        self,
        html: str,
        *,
        environment_revision: str,
        page_id: str = "page",
        url: str = "",
        ttl_ms: int = 2_000,
        snapshot_id: str = "",
        page_revision: str = "",
    ) -> PageAffordanceModel:
        parser = _InteractiveParser()
        parser.feed(html or "")
        parser.close()
        semantic_nodes = [
            {
                "tag": node["tag"],
                "role": node["attr"].get("role", ""),
                "id": node["attr"].get("id", ""),
                "bid": node["attr"].get("bid", ""),
                "name": node["attr"].get("name", ""),
                "disabled": "disabled" in node["attr"] or node["attr"].get("aria-disabled") == "true",
                "label": _label_for(node),
            }
            for node in parser.nodes
        ]
        effective_page_revision = page_revision or "page:sha256:" + hashlib.sha256(
            json.dumps({"url": url, "nodes": semantic_nodes}, sort_keys=True).encode("utf-8")
        ).hexdigest()
        affordances: list[Affordance] = []
        for node in parser.nodes:
            attr = node["attr"]
            action = _action_for(node)
            selector, confidence = _selector_for(node)
            disabled = "disabled" in attr or attr.get("aria-disabled") == "true"
            affordance_id = f"dom_{node['tag']}_{node['nth']}"
            target_fingerprint = "sha256:" + hashlib.sha256(
                json.dumps(
                    {
                        "id": affordance_id,
                        "role": attr.get("role") or node["tag"],
                        "label": _label_for(node),
                        "selector": selector,
                        "enabled": not disabled,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            lease = AffordanceLease.issue(
                environment_revision=environment_revision,
                ttl_ms=ttl_ms,
                provenance=["dom"],
                snapshot_id=snapshot_id,
                page_revision=effective_page_revision,
                target_fingerprint=target_fingerprint,
            )
            affordances.append(
                Affordance(
                    id=affordance_id,
                    surface=Surface.DOM,
                    role="input" if action in {"type", "select"} else "button",
                    label=_label_for(node),
                    action=action,
                    locator={"selector": selector, "strategy": "css"},
                    lease=lease,
                    backend_candidates=["dom"],
                    confidence=0.0 if disabled else confidence,
                    state={"enabled": not disabled, "visible": True},
                    risk=RiskLevel.LOW,
                    evidence=[url] if url else [],
                )
            )
        return PageAffordanceModel(
            page_id=page_id,
            url=url,
            environment_revision=environment_revision,
            snapshot_id=snapshot_id,
            page_revision=effective_page_revision,
            affordances=affordances,
            raw_node_count=parser.total_nodes,
            kept_node_count=len(affordances),
        )

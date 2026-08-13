"""Bounded public document records projected from one DOM snapshot."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from affordance_runtime.world.contracts import SemanticTarget

MAX_DOCUMENT_HTML_CHARS = 256_000
MAX_DOCUMENT_NODES = 4_096
MAX_DOCUMENT_RECORDS = 64
MAX_DOCUMENT_FIELDS_PER_RECORD = 32
MAX_DOCUMENT_TEXT_CHARS = 480

_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_IGNORED_TEXT_TAGS = frozenset({"script", "style", "template", "noscript"})
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
})
_SPACE = re.compile(r"\s+")
_FIELD_KEY = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class StructuredDocumentProjection:
    """Public semantic targets plus one current structured output artifact."""

    targets: tuple[SemanticTarget, ...]
    artifact: dict[str, object]
    truncated: bool


@dataclass
class _Node:
    tag: str
    attributes: dict[str, str]
    hidden: bool
    text_parts: list[str] = field(default_factory=list)
    children: list[_Node] = field(default_factory=list)


class _ProjectionLimit(RuntimeError):
    pass


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {}, False)
        self.stack = [self.root]
        self.node_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.node_count >= MAX_DOCUMENT_NODES:
            raise _ProjectionLimit
        self.node_count += 1
        attributes = {key.casefold(): value or "" for key, value in attrs}
        parent = self.stack[-1]
        node = _Node(tag.casefold(), attributes, parent.hidden or _authored_hidden(attributes))
        parent.children.append(node)
        if node.tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == normalized:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack[-1].tag not in _IGNORED_TEXT_TAGS and data.strip():
            self.stack[-1].text_parts.append(data)


def project_structured_document(html: str, source_url: str) -> StructuredDocumentProjection:
    """Project visible article definition records without retaining DOM routes."""

    parser = _DocumentParser()
    bounded_html = html[:MAX_DOCUMENT_HTML_CHARS]
    truncated = len(html) > len(bounded_html)
    try:
        parser.feed(bounded_html)
        parser.close()
    except _ProjectionLimit:
        truncated = True

    title = _first_text(parser.root, {"title"}) or _first_text(parser.root, _HEADING_TAGS)
    records: list[dict[str, object]] = []
    targets: list[SemanticTarget] = []
    identities: dict[tuple[str, str], int] = {}
    for node in _walk(parser.root):
        if node.hidden or node.tag != "article":
            continue
        fields = _definition_fields(node)
        if not fields:
            continue
        label = _first_text(node, _HEADING_TAGS) or _text(node.attributes.get("aria-label", ""))
        if not label:
            continue
        identity_key = (node.tag, label.casefold())
        occurrence = identities.get(identity_key, 0)
        identities[identity_key] = occurrence + 1
        target_id = _record_target_id(node.tag, label, occurrence)
        targets.append(SemanticTarget(
            target_id,
            "document_record",
            label,
            {"visible": True, "field_count": len(fields), "fields": fields},
            {"parent_id": "dom_document"},
        ))
        records.append({
            "subject_id": target_id,
            "role": "document_record",
            "label": label,
            "fields": fields,
        })
        if len(records) >= MAX_DOCUMENT_RECORDS:
            truncated = truncated or any(
                candidate.tag == "article" and not candidate.hidden
                for candidate in _walk_after(parser.root, node)
            )
            break

    root = SemanticTarget(
        "dom_document",
        "document",
        title or "Current document",
        {
            "visible_record_count": len(records),
            "projection_complete": not truncated,
            **({"title": title} if title else {}),
        },
        {"child_ids": tuple(item.target_id for item in targets)},
    )
    artifact: dict[str, object] = {
        "public_summary": (
            f"structured document contains {len(records)} visible record"
            f"{'s' if len(records) != 1 else ''}"
        ),
        "title": title,
        "source_url": source_url,
        "records": tuple(records),
        "truncated": truncated,
    }
    return StructuredDocumentProjection((root, *targets), artifact, truncated)


def _authored_hidden(attributes: dict[str, str]) -> bool:
    style = attributes.get("style", "").casefold().replace(" ", "")
    return (
        "hidden" in attributes
        or attributes.get("aria-hidden", "").casefold() == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


def _walk(node: _Node):
    for child in node.children:
        yield child
        yield from _walk(child)


def _walk_after(root: _Node, current: _Node):
    found = False
    for node in _walk(root):
        if found:
            yield node
        elif node is current:
            found = True


def _first_text(node: _Node, tags: frozenset[str] | set[str]) -> str:
    for candidate in _walk(node):
        if not candidate.hidden and candidate.tag in tags:
            value = _node_text(candidate)
            if value:
                return value
    return ""


def _definition_fields(node: _Node) -> dict[str, object]:
    fields: dict[str, object] = {}
    for definition_list in _walk(node):
        if definition_list.hidden or definition_list.tag != "dl":
            continue
        term = ""
        for item in _walk(definition_list):
            if item.hidden:
                continue
            if item.tag == "dt":
                term = _node_text(item)
            elif item.tag == "dd" and term:
                key = _field_key(term)
                value = _node_text(item)
                if key and value and key not in fields:
                    fields[key] = _scalar(value)
                    if len(fields) >= MAX_DOCUMENT_FIELDS_PER_RECORD:
                        return fields
                term = ""
    return fields


def _node_text(node: _Node) -> str:
    values = [*node.text_parts]
    for child in node.children:
        if not child.hidden and child.tag not in _IGNORED_TEXT_TAGS:
            values.append(_node_text(child))
    return _text(" ".join(values))


def _text(value: str) -> str:
    return _SPACE.sub(" ", value).strip()[:MAX_DOCUMENT_TEXT_CHARS]


def _field_key(value: str) -> str:
    return _FIELD_KEY.sub("_", value.casefold()).strip("_")[:64]


def _scalar(value: str) -> object:
    if re.fullmatch(r"[+-]?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"[+-]?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            pass
    return value


def _record_target_id(role: str, label: str, occurrence: int) -> str:
    digest = hashlib.sha256(f"{role}\0{label.casefold()}\0{occurrence}".encode()).hexdigest()[:20]
    return f"dom_document_record_{digest}"

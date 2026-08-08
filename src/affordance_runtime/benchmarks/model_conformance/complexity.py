"""Actual-input complexity measurement; never used for Runtime behavior."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .contracts import ModelInputComplexity


def measure_model_input_complexity(
    serialized_context: str,
    system_prompt: str,
    schema: Mapping[str, object],
) -> ModelInputComplexity:
    context = json.loads(serialized_context)
    actions = _items(context, "actions", "options")
    world = context.get("world", {}) if isinstance(context, Mapping) else {}
    destinations = sum(len(_nested_items(item, "destinations")) for item in actions)
    schema_bytes = len(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode())
    context_bytes = len(serialized_context.encode())
    system_bytes = len(system_prompt.encode())
    definitions = schema.get("$defs", {})
    return ModelInputComplexity(
        context_bytes, system_bytes, schema_bytes,
        len(definitions) if isinstance(definitions, Mapping) else 0,
        _variant_count(schema), _tree_depth(schema), len(actions), destinations,
        len(_section_items(world, "targets")), len(_section_items(world, "facts")),
        len(_section_items(world, "conflicts")), len(_section_items(world, "artifact_summaries")),
        len(_items(context, "history", "items")), context_bytes + system_bytes + schema_bytes,
    )


def _items(value: object, owner: str, field: str) -> tuple[object, ...]:
    if not isinstance(value, Mapping) or not isinstance(value.get(owner), Mapping):
        return ()
    items = value[owner].get(field, ())
    return tuple(items) if isinstance(items, Sequence) and not isinstance(items, str | bytes) else ()


def _section_items(world: object, field: str) -> tuple[object, ...]:
    return _items({"section": world.get(field, {}) if isinstance(world, Mapping) else {}}, "section", "items")


def _nested_items(value: object, field: str) -> tuple[object, ...]:
    return _items({"section": value.get(field, {}) if isinstance(value, Mapping) else {}}, "section", "items")


def _variant_count(schema: Mapping[str, object]) -> int:
    values = schema.get("oneOf") or schema.get("anyOf")
    if isinstance(values, Sequence) and not isinstance(values, str | bytes):
        return len(values)
    root = schema.get("$defs", {})
    if isinstance(root, Mapping):
        return max((_variant_count(item) for item in root.values() if isinstance(item, Mapping)), default=0)
    return 0


def _tree_depth(value: object) -> int:
    if isinstance(value, Mapping):
        return 1 + max((_tree_depth(item) for item in value.values()), default=0)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return 1 + max((_tree_depth(item) for item in value), default=0)
    return 1

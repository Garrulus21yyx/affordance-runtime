"""Generic flat semantic compiler for current closed action candidates."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.agent.context.contracts import AgentActionOptionView, AgentDestinationView
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.providers.tool_transport_contracts import ToolSpec

_ABSENT = object()
_RESERVED_NAMES = frozenset(
    {
        "choice",
        "grounding_ref",
        "source_grounding_ref",
        "destination_grounding_ref",
        "grounding_pair",
        "target",
        "source",
        "destination",
    }
)
_PATH_PRIORITY = (
    "state.semantic_grid_coordinate",
    "label",
    "within.label",
    "role",
    "within.role",
)


class SelectorMode(StrEnum):
    CONSTANT_TARGET = "constant_target"
    SEMANTIC_FIELDS = "semantic_fields"
    ATOMIC_SEMANTIC_CHOICE = "atomic_semantic_choice"
    GROUNDING_FALLBACK = "grounding_fallback"


@dataclass(frozen=True)
class ConcreteActionCandidateRow:
    option: AgentActionOptionView
    destination: AgentDestinationView | None


@dataclass(frozen=True)
class CompiledSelectorField:
    public_name: str
    semantic_paths: tuple[str, ...]
    input_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_paths", tuple(self.semantic_paths))
        object.__setattr__(self, "input_schema", freeze_json(self.input_schema))


@dataclass(frozen=True)
class PrivateResolutionEntry:
    selector_values: Mapping[str, object]
    action_id: str
    destination_id: str | None
    target_ref: str = ""
    reconciliation_values: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "selector_values", freeze_json(self.selector_values))
        object.__setattr__(self, "reconciliation_values", freeze_json(self.reconciliation_values))


@dataclass(frozen=True)
class CompiledGroundedTool:
    canonical_operation: str
    public_spec: ToolSpec
    selector_mode: SelectorMode
    selector_fields: tuple[CompiledSelectorField, ...]
    private_resolutions: tuple[PrivateResolutionEntry, ...]
    authority_equivalence_digest: str = ""


@dataclass(frozen=True)
class _CompiledDraft:
    operation: str
    description: str
    schema: Mapping[str, object]
    mode: SelectorMode
    fields: tuple[CompiledSelectorField, ...]
    resolutions: tuple[PrivateResolutionEntry, ...]
    digest: str
    authority_digest: str


class GroundedToolCompiler:
    """Compile complete candidates into flat public tools and exact private tables."""

    def compile(
        self,
        options: tuple[AgentActionOptionView, ...],
        *,
        context_id: str,
    ) -> tuple[CompiledGroundedTool, ...]:
        rows = tuple(row for option in options for row in self.expand_rows(option))
        grouped: dict[tuple[str, ...], list[ConcreteActionCandidateRow]] = defaultdict(list)
        for row in rows:
            grouped[_technical_key(row.option)].append(row)
        drafts: list[_CompiledDraft] = []
        for technical_key in sorted(grouped):
            skeleton_groups: dict[tuple[str, str], list[ConcreteActionCandidateRow]] = defaultdict(list)
            for row in grouped[technical_key]:
                target = row.option.target_semantics
                skeleton_groups[(_token(target.get("role", _ABSENT)), _token(target.get("label", _ABSENT)))].append(row)
            for skeleton_key in sorted(skeleton_groups):
                stable_rows = tuple(sorted(
                    skeleton_groups[skeleton_key],
                    key=lambda row: (
                        _token(_row_semantics(row)),
                        row.option.action_id,
                        row.destination.destination_id if row.destination else "",
                    ),
                ))
                drafts.append(self._compile_group(stable_rows, context_id))
        names = _tool_names(tuple(drafts))
        return tuple(
            CompiledGroundedTool(
                draft.operation,
                ToolSpec(name, draft.description, draft.schema),
                draft.mode,
                draft.fields,
                draft.resolutions,
                draft.authority_digest,
            )
            for name, draft in zip(names, drafts, strict=True)
        )

    @staticmethod
    def expand_rows(option: AgentActionOptionView) -> tuple[ConcreteActionCandidateRow, ...]:
        if option.destination_mode == "forbidden":
            return (ConcreteActionCandidateRow(option, None),)
        if option.destination_mode == "optional":
            raise GroundedToolResolutionError(GroundedToolResolutionCode.UNSUPPORTED_DESTINATION_MODE)
        if option.destination_mode != "required":
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        if option.destinations.truncated or not option.destinations.items:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.DESTINATION_UNAVAILABLE)
        return tuple(ConcreteActionCandidateRow(option, item) for item in option.destinations.items)

    def _compile_group(
        self,
        rows: tuple[ConcreteActionCandidateRow, ...],
        context_id: str,
    ) -> _CompiledDraft:
        records = tuple(_row_semantics(row) for row in rows)
        common = recursive_common_semantic_skeleton(records)
        facets = _minimal_distinguishing_facets(records, common)
        selector_properties: dict[str, object] = {}
        selector_required: list[str] = []
        selector_fields: tuple[CompiledSelectorField, ...]
        selector_values: tuple[Mapping[str, object], ...]
        if len(rows) == 1:
            mode = SelectorMode.CONSTANT_TARGET
            selector_fields = ()
            selector_values = ({},)
        elif facets:
            mode, selector_fields, selector_values = _semantic_selectors(records, facets)
        else:
            mode, selector_fields, selector_values = _grounding_selectors(rows, context_id)
        for selector_field in selector_fields:
            if selector_field.public_name in selector_properties:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
            selector_properties[selector_field.public_name] = to_json_compatible(
                selector_field.input_schema
            )
            selector_required.append(selector_field.public_name)

        option = rows[0].option
        business_properties, business_required = _business_schema(option.parameter_schema)
        collisions = set(business_properties).intersection(_RESERVED_NAMES | set(selector_properties))
        if collisions:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        schema = {
            "type": "object",
            "properties": {**selector_properties, **business_properties},
            "required": [*selector_required, *business_required],
            "additionalProperties": False,
        }
        resolutions = tuple(
            PrivateResolutionEntry(
                values,
                row.option.action_id,
                row.destination.destination_id if row.destination else None,
                row.option.target_ref,
                {
                    **dict(values),
                    **(
                        {"grounding_ref": row.option.target_ref}
                        if row.option.target_ref and row.destination is None
                        else {}
                    ),
                },
            )
            for row, values in zip(rows, selector_values, strict=True)
        )
        if len({_token(item.selector_values) for item in resolutions}) != len(resolutions):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        description = _description(option, common, selector_fields)
        digest_payload = {
            "operation": option.operation,
            "common": common,
            "selector_mode": mode.value,
            "selector_fields": tuple(
                (item.public_name, item.semantic_paths, item.input_schema) for item in selector_fields
            ),
            "schema": schema,
            "destination_mode": option.destination_mode,
            "effect_category": option.effect_category,
            "effects": option.semantic_effects,
            "risk": str(option.risk),
            "consequence": option.consequence_class,
        }
        digest = hashlib.sha256(_token(digest_payload).encode()).hexdigest()
        authority_payload = {
            "context_id": context_id,
            "canonical_action": option.operation,
            "business_schema": option.parameter_schema,
            "subject_kind": option.subject_kind,
            "destination_mode": option.destination_mode,
            "effect_category": option.effect_category,
            "semantic_effects": option.semantic_effects,
            "risk": str(option.risk),
            "consequence": option.consequence_class,
            "reversible": option.reversible,
            "observation_barrier": option.observation_barrier,
            "verification_contract_digest": option.verification_contract_digest,
        }
        authority_digest = "sha256:" + hashlib.sha256(
            _token(authority_payload).encode()
        ).hexdigest()
        return _CompiledDraft(
            option.operation,
            description,
            schema,
            mode,
            selector_fields,
            resolutions,
            digest,
            authority_digest,
        )


def recursive_common_semantic_skeleton(values: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Return the deterministic recursive intersection; absent and null differ."""

    if not values:
        return {}
    common: dict[str, object] = {}
    first = values[0]
    for key in sorted(first):
        if any(key not in value for value in values[1:]):
            continue
        candidates = tuple(value[key] for value in values)
        if all(isinstance(item, Mapping) for item in candidates):
            nested = recursive_common_semantic_skeleton(tuple(item for item in candidates if isinstance(item, Mapping)))
            if nested:
                common[key] = nested
        elif len({_token(item) for item in candidates}) == 1:
            common[key] = to_json_compatible(candidates[0])
    return common


def _technical_key(option: AgentActionOptionView) -> tuple[str, ...]:
    return (
        option.operation,
        _token(option.parameter_schema),
        option.destination_mode,
        option.subject_kind,
        option.target_role,
        option.effect_category,
        _token(option.semantic_effects),
        str(option.risk),
        option.consequence_class,
        str(option.reversible),
        str(option.observation_barrier),
        option.verification_contract_digest,
    )


def _row_semantics(row: ConcreteActionCandidateRow) -> Mapping[str, object]:
    if row.destination is None:
        return row.option.target_semantics
    return {"source": row.option.target_semantics, "destination": row.destination.semantics}


def _minimal_distinguishing_facets(
    records: tuple[Mapping[str, object], ...],
    common: Mapping[str, object],
) -> tuple[str, ...]:
    paths = tuple(sorted(
        {
            path
            for record in records
            for path in _leaf_paths(record)
            if _path_value(common, path) is _ABSENT
        },
        key=_path_order,
    ))
    varying = tuple(
        path for path in paths
        if len({_token(_path_value(record, path)) for record in records}) > 1
    )
    candidates: list[tuple[int, int, tuple[tuple[int, str], ...], tuple[str, ...]]] = []
    for size in range(1, len(varying) + 1):
        for facets in itertools.combinations(varying, size):
            identities = {
                tuple(_token(_path_value(record, path)) for path in facets)
                for record in records
            }
            if len(identities) != len(records):
                continue
            encoded_size = sum(
                len(_token(_path_value(record, path)).encode())
                for record in records
                for path in facets
            )
            candidates.append((size, encoded_size, tuple(_path_order(path) for path in facets), facets))
        if candidates:
            break
    return min(candidates)[-1] if candidates else ()


def _semantic_selectors(
    records: tuple[Mapping[str, object], ...],
    facets: tuple[str, ...],
) -> tuple[SelectorMode, tuple[CompiledSelectorField, ...], tuple[Mapping[str, object], ...]]:
    emitted = tuple(
        tuple(_public_selector_value(_path_value(record, path), path) for path in facets)
        for record in records
    )
    cartesian = set(emitted) == set(itertools.product(*(tuple(dict.fromkeys(row[index] for row in emitted)) for index in range(len(facets)))))
    public_names = _public_field_names(facets)
    if len(facets) == 1 or cartesian:
        fields = tuple(
            CompiledSelectorField(
                name,
                (path,),
                {
                    "type": _selector_type(tuple(row[index] for row in emitted)),
                    "description": path,
                    "enum": list(dict.fromkeys(row[index] for row in emitted)),
                },
            )
            for index, (name, path) in enumerate(zip(public_names, facets, strict=True))
        )
        values = tuple(
            {name: row[index] for index, name in enumerate(public_names)}
            for row in emitted
        )
        return SelectorMode.SEMANTIC_FIELDS, fields, values
    choices = tuple(
        _token({path: value for path, value in zip(facets, row, strict=True)})
        for row in emitted
    )
    field = CompiledSelectorField(
        "choice",
        facets,
        {"type": "string", "description": ", ".join(facets), "enum": list(choices)},
    )
    return SelectorMode.ATOMIC_SEMANTIC_CHOICE, (field,), tuple({"choice": item} for item in choices)


def _grounding_selectors(
    rows: tuple[ConcreteActionCandidateRow, ...],
    context_id: str,
) -> tuple[SelectorMode, tuple[CompiledSelectorField, ...], tuple[Mapping[str, object], ...]]:
    fields: tuple[CompiledSelectorField, ...]
    values: tuple[Mapping[str, object], ...]
    source_ids = tuple(dict.fromkeys(row.option.action_id for row in rows))
    destination_ids = tuple(dict.fromkeys(
        row.destination.destination_id for row in rows if row.destination is not None
    ))
    source_varies = len(source_ids) > 1
    destination_varies = len(destination_ids) > 1
    endpoints: list[tuple[str, str, bool]] = []
    for row in rows:
        if source_varies:
            endpoints.append((row.option.target_ref, row.option.grounding_context_id, row.option.target_marked))
        if destination_varies and row.destination is not None:
            endpoints.append((
                row.destination.grounding_ref,
                row.destination.grounding_context_id,
                row.destination.grounding_rendered,
            ))
    if (
        not endpoints
        or any(not ref or owner != context_id or not rendered for ref, owner, rendered in endpoints)
    ):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE)
    if not destination_ids:
        fields = (CompiledSelectorField(
            "grounding_ref", ("target.grounding_ref",),
            {"type": "string", "description": "current rendered grounding ref", "enum": list(dict.fromkeys(row.option.target_ref for row in rows))},
        ),)
        values = tuple({"grounding_ref": row.option.target_ref} for row in rows)
    elif source_varies and destination_varies:
        pairs = tuple((row.option.target_ref, row.destination.grounding_ref) for row in rows if row.destination)
        source_domain = tuple(dict.fromkeys(item[0] for item in pairs))
        destination_domain = tuple(dict.fromkeys(item[1] for item in pairs))
        if set(pairs) == set(itertools.product(source_domain, destination_domain)):
            fields = (
                CompiledSelectorField("source_grounding_ref", ("source.grounding_ref",), {"type": "string", "description": "current rendered source ref", "enum": list(source_domain)}),
                CompiledSelectorField("destination_grounding_ref", ("destination.grounding_ref",), {"type": "string", "description": "current rendered destination ref", "enum": list(destination_domain)}),
            )
            values = tuple(
                {"source_grounding_ref": source, "destination_grounding_ref": destination}
                for source, destination in pairs
            )
        else:
            choices = tuple(_token({"source": source, "destination": destination}) for source, destination in pairs)
            fields = (CompiledSelectorField("grounding_pair", ("source.grounding_ref", "destination.grounding_ref"), {"type": "string", "description": "one current rendered source/destination pair", "enum": list(choices)}),)
            values = tuple({"grounding_pair": item} for item in choices)
    elif source_varies:
        domain = tuple(dict.fromkeys(row.option.target_ref for row in rows))
        fields = (CompiledSelectorField("source_grounding_ref", ("source.grounding_ref",), {"type": "string", "description": "current rendered source ref", "enum": list(domain)}),)
        values = tuple({"source_grounding_ref": row.option.target_ref} for row in rows)
    elif destination_varies:
        domain = tuple(dict.fromkeys(row.destination.grounding_ref for row in rows if row.destination))
        fields = (CompiledSelectorField("destination_grounding_ref", ("destination.grounding_ref",), {"type": "string", "description": "current rendered destination ref", "enum": list(domain)}),)
        values = tuple({"destination_grounding_ref": row.destination.grounding_ref} for row in rows if row.destination)
    else:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE)
    if len({_token(item) for item in values}) != len(rows):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE)
    return SelectorMode.GROUNDING_FALLBACK, fields, values


def _business_schema(schema: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    if schema.get("type") != "object" or schema.get("additionalProperties", False) is not False:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    properties = schema.get("properties", {})
    required = schema.get("required", ())
    if not isinstance(properties, Mapping) or not isinstance(required, Sequence) or isinstance(required, str | bytes):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    if any(not isinstance(item, str) for item in required) or not set(required).issubset(properties):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return ({str(name): to_json_compatible(value) for name, value in properties.items()}, list(required))


def _description(
    option: AgentActionOptionView,
    common: Mapping[str, object],
    fields: tuple[CompiledSelectorField, ...],
) -> str:
    skeleton = _token(common)
    selector = "; choose " + ", ".join(item.public_name for item in fields) if fields else ""
    effects = ", ".join(option.semantic_effects) or option.effect_category
    return (
        f"{option.operation} the current target with shared public semantics {skeleton}{selector}. "
        f"Effect: {effects}; risk: {option.risk}."
    )[:500]


def _tool_names(drafts: tuple[_CompiledDraft, ...]) -> tuple[str, ...]:
    counts: dict[str, int] = defaultdict(int)
    for draft in drafts:
        counts[draft.operation] += 1
    names: list[str] = []
    for draft in drafts:
        if counts[draft.operation] == 1:
            names.append(draft.operation)
            continue
        length = 8
        candidate = f"{draft.operation}_{draft.digest[:length]}"
        while candidate in names and length < len(draft.digest):
            length += 1
            candidate = f"{draft.operation}_{draft.digest[:length]}"
        if candidate in names or len(candidate) > 64:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        names.append(candidate)
    return tuple(names)


def _leaf_paths(value: Mapping[str, object], prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    for key in sorted(value):
        path = f"{prefix}.{key}" if prefix else key
        child = value[key]
        if isinstance(child, Mapping):
            paths.extend(_leaf_paths(child, path))
        else:
            paths.append(path)
    return tuple(paths)


def _path_value(value: Mapping[str, object], path: str) -> object:
    current: object = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _ABSENT
        current = current[part]
    return current


def _path_order(path: str) -> tuple[int, str]:
    unqualified = path.removeprefix("source.").removeprefix("destination.")
    try:
        priority = _PATH_PRIORITY.index(unqualified)
    except ValueError:
        priority = len(_PATH_PRIORITY)
    return priority, path


def _public_field_names(paths: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for path in paths:
        parts = path.split(".")
        if parts[0] == "state":
            parts = parts[1:]
        elif len(parts) > 1 and parts[1] == "state":
            parts = [parts[0], *parts[2:]]
        name = "_".join(parts)
        if not name or name in _RESERVED_NAMES or name in result:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        result.append(name)
    return tuple(result)


def _public_selector_value(value: object, path: str) -> object:
    if value is _ABSENT:
        return '{"$absent":true}'
    if path.endswith("semantic_grid_coordinate") and isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return "(" + ",".join(_number_or_token(item) for item in value) + ")"
    if isinstance(value, str | int | float | bool) and value is not None:
        return value
    return _token(value)


def _selector_type(values: tuple[object, ...]) -> str:
    if all(isinstance(item, bool) for item in values):
        return "boolean"
    if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
        return "integer"
    if all(isinstance(item, int | float) and not isinstance(item, bool) for item in values):
        return "number"
    return "string"


def _number_or_token(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return format(value, ".15g")
    return _token(value)


def _token(value: object) -> str:
    if value is _ABSENT:
        return '{"$absent":true}'
    return json.dumps(to_json_compatible(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

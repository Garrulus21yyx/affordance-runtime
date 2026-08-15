"""Catalog-only provider call reconciliation before exact tool resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.schema_validation import validate_value_issue
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.policy.grounded_tool_compiler import CompiledGroundedTool
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolCatalog
from affordance_runtime.model.providers.tool_transport_contracts import ToolCall, ToolSpec


class ToolCallReconciliationStatus(StrEnum):
    EXACT = "exact"
    NORMALIZED_EQUIVALENT = "normalized_equivalent"
    REPAIR_REQUIRED = "repair_required"
    REJECTED = "rejected"


class ToolCallIssueCode(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT = "invalid_argument"
    TOOL_ARGUMENT_OWNER_MISMATCH = "tool_argument_owner_mismatch"
    AMBIGUOUS_TOOL_INTENT = "ambiguous_tool_intent"
    NON_EQUIVALENT_TOOL_INTENT = "non_equivalent_tool_intent"
    STALE_CATALOG = "stale_catalog"


@dataclass(frozen=True)
class DidYouMeanCandidate:
    tool_name: str
    public_arguments: Mapping[str, object]
    reason_code: ToolCallIssueCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_arguments", freeze_json(self.public_arguments))


@dataclass(frozen=True)
class ToolCallReconciliationResult:
    status: ToolCallReconciliationStatus
    exact_call: ToolCall | None = None
    issue_code: ToolCallIssueCode | None = None
    field_paths: tuple[str, ...] = ()
    argument_code: str = ""
    did_you_mean: tuple[DidYouMeanCandidate, ...] = ()

    def __post_init__(self) -> None:
        exact = self.status in {
            ToolCallReconciliationStatus.EXACT,
            ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT,
        }
        if exact != (self.exact_call is not None) or exact == (self.issue_code is not None):
            raise ValueError("provider call reconciliation outcome is inconsistent")
        object.__setattr__(self, "field_paths", tuple(self.field_paths))
        object.__setattr__(self, "did_you_mean", tuple(self.did_you_mean))


@dataclass(frozen=True)
class _Candidate:
    spec: ToolSpec
    binding: CompiledGroundedTool
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ProviderCallNormalizer:
    """Normalize representation only; never read world state or authorize a call."""

    @staticmethod
    def normalize_wire_envelope(value: object) -> object:
        """Canonicalize admitted provider aliases without changing argument values."""

        if not isinstance(value, Mapping):
            return value
        raw = dict(value)
        name = raw.pop("name", None)
        operation = raw.pop("op", None)
        if name is None:
            name = operation
        elif operation is not None and operation != name:
            return value
        arguments = raw.pop("arguments", None)
        args_alias = raw.pop("args", None)
        if arguments is not None and args_alias is not None and arguments != args_alias:
            return value
        if arguments is None:
            arguments = args_alias
        if arguments is None:
            arguments = raw
        elif raw:
            if not isinstance(arguments, Mapping) or set(arguments).intersection(raw):
                return value
            arguments = {**arguments, **raw}
        return {"name": name, "arguments": arguments}

    def normalize(
        self,
        call: ToolCall,
        catalog: GroundedToolCatalog,
    ) -> ToolCallReconciliationResult:
        if not _catalog_is_current(catalog):
            return _issue(
                ToolCallReconciliationStatus.REJECTED,
                ToolCallIssueCode.STALE_CATALOG,
            )
        selected_index = next(
            (index for index, spec in enumerate(catalog.specs) if spec.name == call.name),
            None,
        )
        if selected_index is None:
            return _issue(
                ToolCallReconciliationStatus.REJECTED,
                ToolCallIssueCode.UNKNOWN_TOOL,
                did_you_mean=tuple(
                    DidYouMeanCandidate(spec.name, {}, ToolCallIssueCode.UNKNOWN_TOOL)
                    for spec in catalog.specs[:8]
                ),
            )
        selected_spec = catalog.specs[selected_index]
        selected_binding = catalog.bindings[selected_index]
        selected_issue = validate_value_issue(
            call.arguments,
            selected_spec.input_schema,
            path="parameters",
        )
        if selected_issue is None:
            return ToolCallReconciliationResult(
                ToolCallReconciliationStatus.EXACT,
                exact_call=call,
            )
        if not isinstance(selected_binding, CompiledGroundedTool):
            return _invalid_arguments(selected_issue)

        candidates = _representation_candidates(call, catalog)
        if len(candidates) > 1:
            return _issue(
                ToolCallReconciliationStatus.REPAIR_REQUIRED,
                ToolCallIssueCode.AMBIGUOUS_TOOL_INTENT,
                field_paths=selected_issue.public_field_paths,
                argument_code=selected_issue.code.value,
                did_you_mean=tuple(
                    DidYouMeanCandidate(
                        item.spec.name,
                        item.arguments,
                        ToolCallIssueCode.AMBIGUOUS_TOOL_INTENT,
                    )
                    for item in candidates[:8]
                ),
            )
        if len(candidates) == 1:
            candidate = candidates[0]
            equivalent = (
                bool(selected_binding.authority_equivalence_digest)
                and selected_binding.authority_equivalence_digest
                == candidate.binding.authority_equivalence_digest
            )
            exact_call = ToolCall(candidate.spec.name, candidate.arguments, call.call_id)
            if equivalent and _business_arguments_unchanged(
                call,
                exact_call,
                candidate.binding,
            ):
                return ToolCallReconciliationResult(
                    ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT,
                    exact_call=exact_call,
                )
            code = (
                ToolCallIssueCode.NON_EQUIVALENT_TOOL_INTENT
                if not equivalent
                else ToolCallIssueCode.TOOL_ARGUMENT_OWNER_MISMATCH
            )
            return _issue(
                ToolCallReconciliationStatus.REPAIR_REQUIRED,
                code,
                field_paths=selected_issue.public_field_paths,
                argument_code=selected_issue.code.value,
                did_you_mean=(DidYouMeanCandidate(candidate.spec.name, candidate.arguments, code),),
            )

        foreign_selector_names = {
            field.public_name
            for binding in catalog.bindings
            if isinstance(binding, CompiledGroundedTool)
            for field in binding.selector_fields
        } - set(_selector_names(selected_binding))
        if foreign_selector_names.intersection(call.arguments):
            return _issue(
                ToolCallReconciliationStatus.REPAIR_REQUIRED,
                ToolCallIssueCode.TOOL_ARGUMENT_OWNER_MISMATCH,
                field_paths=selected_issue.public_field_paths,
                argument_code=selected_issue.code.value,
                did_you_mean=_owner_mismatch_candidates(call, catalog),
            )
        return _invalid_arguments(selected_issue)


def _catalog_is_current(catalog: GroundedToolCatalog) -> bool:
    if (
        not catalog.catalog_id.startswith("grounded-catalog:")
        or not catalog.context_id.startswith("context:")
        or len(catalog.specs) != len(catalog.bindings)
    ):
        return False
    return all(
        not isinstance(binding, CompiledGroundedTool)
        or binding.authority_equivalence_digest.startswith("sha256:")
        for binding in catalog.bindings
    )


def _representation_candidates(
    call: ToolCall,
    catalog: GroundedToolCatalog,
) -> tuple[_Candidate, ...]:
    result = []
    for spec, binding in zip(catalog.specs, catalog.bindings, strict=True):
        if spec.name == call.name or not isinstance(binding, CompiledGroundedTool):
            continue
        selector_names = _selector_names(binding)
        business_names = set(_schema_properties(spec)) - set(selector_names)
        for row in binding.private_resolutions:
            owned = dict(row.reconciliation_values)
            explicit = {
                name: value for name, value in call.arguments.items() if name in owned
            }
            if not explicit or any(owned[name] != value for name, value in explicit.items()):
                continue
            arguments = {
                **dict(row.selector_values),
                **{
                    name: call.arguments[name]
                    for name in business_names
                    if name in call.arguments
                },
            }
            represented_names = set(arguments) | set(explicit)
            if set(call.arguments) - represented_names:
                continue
            if validate_value_issue(arguments, spec.input_schema, path="parameters") is None:
                result.append(_Candidate(spec, binding, arguments))
    unique = {
        (item.spec.name, repr(dict(item.arguments))): item for item in result
    }
    return tuple(unique[key] for key in sorted(unique))


def _business_arguments_unchanged(
    raw: ToolCall,
    exact: ToolCall,
    binding: CompiledGroundedTool,
) -> bool:
    selectors = set(_selector_names(binding))
    exact_business = {
        name: value for name, value in exact.arguments.items() if name not in selectors
    }
    return all(raw.arguments.get(name) == value for name, value in exact_business.items())


def _owner_mismatch_candidates(
    call: ToolCall,
    catalog: GroundedToolCatalog,
) -> tuple[DidYouMeanCandidate, ...]:
    candidates = []
    for spec in catalog.specs:
        properties = set(_schema_properties(spec))
        owned = {
            name: value for name, value in call.arguments.items() if name in properties
        }
        if not owned:
            continue
        candidates.append(
            DidYouMeanCandidate(
                spec.name,
                owned,
                ToolCallIssueCode.TOOL_ARGUMENT_OWNER_MISMATCH,
            )
        )
    return tuple(candidates[:8])


def _selector_names(binding: CompiledGroundedTool) -> tuple[str, ...]:
    return tuple(item.public_name for item in binding.selector_fields)


def _schema_properties(spec: ToolSpec) -> Mapping[str, object]:
    properties = spec.input_schema.get("properties", {})
    return properties if isinstance(properties, Mapping) else {}


def _invalid_arguments(issue) -> ToolCallReconciliationResult:
    return _issue(
        ToolCallReconciliationStatus.REPAIR_REQUIRED,
        ToolCallIssueCode.INVALID_ARGUMENT,
        field_paths=issue.public_field_paths,
        argument_code=issue.code.value,
    )


def _issue(
    status: ToolCallReconciliationStatus,
    code: ToolCallIssueCode,
    *,
    field_paths: tuple[str, ...] = (),
    argument_code: str = "",
    did_you_mean: tuple[DidYouMeanCandidate, ...] = (),
) -> ToolCallReconciliationResult:
    return ToolCallReconciliationResult(
        status,
        issue_code=code,
        field_paths=field_paths,
        argument_code=argument_code,
        did_you_mean=did_you_mean,
    )

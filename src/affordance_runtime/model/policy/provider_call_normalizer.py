"""Catalog-only provider call reconciliation before exact tool resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.schema_validation import validate_value_issue
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolCatalog
from affordance_runtime.model.policy.tool_contracts import ToolCall


class ToolCallReconciliationStatus(StrEnum):
    EXACT = "exact"
    REPAIR_REQUIRED = "repair_required"
    REJECTED = "rejected"


class ToolCallIssueCode(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT = "invalid_argument"
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
        exact = self.status is ToolCallReconciliationStatus.EXACT
        if exact != (self.exact_call is not None) or exact == (self.issue_code is not None):
            raise ValueError("provider call reconciliation outcome is inconsistent")
        object.__setattr__(self, "field_paths", tuple(self.field_paths))
        object.__setattr__(self, "did_you_mean", tuple(self.did_you_mean))


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
        # Provider-side commentary is non-authoritative envelope metadata.  It
        # is deliberately discarded here and can never become a tool argument;
        # the selected catalog schema still validates every action-bearing value.
        normalized = {"name": name}
        if arguments is not None:
            normalized["arguments"] = arguments
        return normalized

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
                    for spec in catalog.specs[:3]
                ),
            )
        selected_spec = catalog.specs[selected_index]
        call = _normalize_nested_parameters(call, selected_spec.input_schema)
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
        return _invalid_arguments(selected_issue)


def _normalize_nested_parameters(
    call: ToolCall,
    input_schema: Mapping[str, object],
) -> ToolCall:
    """Unwrap one unambiguous legacy argument wrapper without guessing values."""

    arguments = call.arguments
    properties = input_schema.get("properties")
    if (
        set(arguments) == {"parameters"}
        and isinstance(arguments["parameters"], Mapping)
        and isinstance(properties, Mapping)
        and "parameters" not in properties
    ):
        return ToolCall(call.name, dict(arguments["parameters"]), call.call_id)
    return call


def _catalog_is_current(catalog: GroundedToolCatalog) -> bool:
    if (
        not catalog.catalog_id.startswith("grounded-catalog:")
        or not catalog.context_id.startswith("context:")
        or len(catalog.specs) != len(catalog.bindings)
    ):
        return False
    return True


def _invalid_arguments(issue) -> ToolCallReconciliationResult:
    return _issue(
        ToolCallReconciliationStatus.REPAIR_REQUIRED,
        ToolCallIssueCode.INVALID_ARGUMENT,
        field_paths=project_argument_paths_to_wire(issue.public_field_paths),
        argument_code=issue.code.value,
    )


def project_argument_paths_to_wire(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Translate internal admission paths into the model-visible envelope."""

    projected = []
    for path in paths:
        if path != "parameters" and not path.startswith("parameters."):
            raise ValueError("argument admission path is outside the parameter contract")
        projected.append("arguments" + path[len("parameters"):])
    return tuple(projected)


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

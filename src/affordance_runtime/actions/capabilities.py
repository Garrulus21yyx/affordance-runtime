"""Immutable semantic interaction definitions and adapter support composition."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.schema_validation import validate_parameter_schema_contract
from affordance_runtime.immutable import to_json_compatible


class InteractionSubjectKind(StrEnum):
    ENTITY = "entity"
    VIEWPORT = "viewport"
    FOCUSED_CONTEXT = "focused_context"
    BROWSER_CONTEXT = "browser_context"


class DestinationMode(StrEnum):
    FORBIDDEN = "forbidden"
    OPTIONAL = "optional"
    REQUIRED = "required"


class ParameterContractKind(StrEnum):
    EMPTY = "empty"
    TEXT = "text"
    OPTION_VALUE = "option_value"
    SCROLL = "scroll"
    KEY = "key"
    NATIVE_VALUE = "native_value"
    URL = "url"
    TAB_INDEX = "tab_index"


class VerificationFamily(StrEnum):
    TARGET_STATE = "target_state"
    NAVIGATION_CONTEXT = "navigation_context"
    FOCUS_STATE = "focus_state"
    SCROLL_STATE = "scroll_state"
    RELATION_CHANGE = "relation_change"
    VALUE_STATE = "value_state"
    SEMANTIC = "semantic"


VERIFICATION_CONTRACT_VERSION = "verification-contract.v1"


class InteractionCapabilityIssueCode(StrEnum):
    UNSUPPORTED_SEMANTIC_ACTION = "unsupported_semantic_action"
    UNSUPPORTED_PRIMITIVE = "unsupported_primitive"
    PROFILE_CONFLICT = "profile_conflict"
    TRANSLATOR_CONFLICT = "translator_conflict"
    SUBJECT_KIND_MISMATCH = "subject_kind_mismatch"
    SCHEMA_CONTRACT_MISMATCH = "schema_contract_mismatch"
    DESTINATION_MODE_MISMATCH = "destination_mode_mismatch"


class InteractionCapabilityError(ValueError):
    def __init__(self, code: InteractionCapabilityIssueCode, value: str = "") -> None:
        self.code = code
        self.value = value
        super().__init__(f"{code.value}: {value}" if value else code.value)


@dataclass(frozen=True)
class SemanticActionDefinition:
    semantic_action: str
    subject_kinds: tuple[InteractionSubjectKind, ...]
    parameter_contract: ParameterContractKind
    destination_mode: DestinationMode
    verification_families: tuple[VerificationFamily, ...]

    def __post_init__(self) -> None:
        if not self.semantic_action or len(set(self.subject_kinds)) != len(self.subject_kinds):
            raise ValueError("semantic action definition is invalid")
        if not self.subject_kinds or not self.verification_families:
            raise ValueError("semantic action definition requires subjects and verification families")
        object.__setattr__(self, "subject_kinds", tuple(self.subject_kinds))
        object.__setattr__(self, "verification_families", tuple(self.verification_families))

    @property
    def definition_digest(self) -> str:
        payload = (
            self.semantic_action,
            tuple(item.value for item in self.subject_kinds),
            self.parameter_contract.value,
            self.destination_mode.value,
            tuple(item.value for item in self.verification_families),
        )
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return {
            ParameterContractKind.EMPTY: (),
            ParameterContractKind.TEXT: ("text",),
            ParameterContractKind.OPTION_VALUE: ("value",),
            ParameterContractKind.SCROLL: ("direction", "extent"),
            ParameterContractKind.KEY: ("key",),
            ParameterContractKind.NATIVE_VALUE: ("value",),
            ParameterContractKind.URL: ("url",),
            ParameterContractKind.TAB_INDEX: ("index",),
        }[self.parameter_contract]


@dataclass(frozen=True)
class VerificationContract:
    """Sealed action-specific verification identity conserved through dispatch."""

    semantic_action: str
    family: VerificationFamily
    parameter_schema_digest: str
    semantic_effects: tuple[str, ...]
    observation_barrier: bool
    contract_version: str = VERIFICATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != VERIFICATION_CONTRACT_VERSION:
            raise ValueError("verification contract version is unsupported")
        definition = INTERACTION_CAPABILITY_REGISTRY.require(self.semantic_action)
        if self.family not in definition.verification_families:
            raise ValueError("verification family is not permitted for semantic action")
        if not self.parameter_schema_digest.strip():
            raise ValueError("verification contract requires parameter schema identity")
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))

    @property
    def digest(self) -> str:
        payload = (
            self.contract_version,
            self.semantic_action,
            self.family.value,
            self.parameter_schema_digest,
            self.semantic_effects,
            self.observation_barrier,
        )
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode()
        ).hexdigest()


def verification_contract_for_action(
    semantic_action: str,
    parameter_schema_digest: str,
    semantic_effects: tuple[str, ...],
    observation_barrier: bool,
    *,
    family: VerificationFamily | None = None,
) -> VerificationContract:
    definition = INTERACTION_CAPABILITY_REGISTRY.require(semantic_action)
    selected_family = family or (
        VerificationFamily.NAVIGATION_CONTEXT
        if semantic_action == "activate"
        else definition.verification_families[0]
    )
    return VerificationContract(
        semantic_action,
        selected_family,
        parameter_schema_digest,
        tuple(semantic_effects),
        observation_barrier,
    )


@dataclass(frozen=True)
class InteractionCapabilityRegistry:
    registry_id: str
    definitions: tuple[SemanticActionDefinition, ...]

    def __post_init__(self) -> None:
        if not self.registry_id.strip() or not self.definitions:
            raise ValueError("interaction registry requires identity and definitions")
        names = tuple(item.semantic_action for item in self.definitions)
        if len(names) != len(set(names)):
            raise ValueError("canonical semantic actions must be unique")
        object.__setattr__(self, "definitions", tuple(self.definitions))

    def resolve(self, semantic_action: str) -> SemanticActionDefinition | None:
        return next(
            (item for item in self.definitions if item.semantic_action == semantic_action),
            None,
        )

    def require(self, semantic_action: str) -> SemanticActionDefinition:
        definition = self.resolve(semantic_action)
        if definition is None:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.UNSUPPORTED_SEMANTIC_ACTION,
                semantic_action,
            )
        return definition

    def validate_parameter_schema(
        self,
        semantic_action: str,
        schema: Mapping[str, object],
    ) -> None:
        definition = self.require(semantic_action)
        try:
            validate_parameter_schema_contract(schema)
            _validate_parameter_family(definition.parameter_contract, schema)
        except (TypeError, ValueError) as exc:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.SCHEMA_CONTRACT_MISMATCH,
                semantic_action,
            ) from exc

    def parameter_schema(
        self,
        semantic_action: str,
        *,
        current_value_schema: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        definition = self.require(semantic_action)
        value_schema = dict(current_value_schema or {})
        if definition.parameter_contract is ParameterContractKind.EMPTY:
            schema: dict[str, object] = _object_schema({})
        elif definition.parameter_contract is ParameterContractKind.TEXT:
            schema = _object_schema({"text": {"type": "string"}}, ("text",))
        elif definition.parameter_contract is ParameterContractKind.OPTION_VALUE:
            schema = _object_schema({"value": {"type": "string", **value_schema}}, ("value",))
        elif definition.parameter_contract is ParameterContractKind.NATIVE_VALUE:
            value_schema = {
                key: value
                for key, value in value_schema.items()
                if key in {"type", "enum", "minimum", "maximum"}
            }
            if not value_schema:
                raise InteractionCapabilityError(
                    InteractionCapabilityIssueCode.SCHEMA_CONTRACT_MISMATCH,
                    semantic_action,
                )
            schema = _object_schema({"value": value_schema}, ("value",))
        elif definition.parameter_contract is ParameterContractKind.SCROLL:
            schema = _object_schema(
                {
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "extent": {"type": "string", "enum": ["small", "page"]},
                },
                ("direction", "extent"),
            )
        elif definition.parameter_contract is ParameterContractKind.KEY:
            schema = _object_schema(
                {
                    "key": {
                        "type": "string",
                        "enum": [
                            "Enter", "Escape", "Tab", "ArrowUp", "ArrowDown",
                            "ArrowLeft", "ArrowRight", "Backspace", "Delete", "Space",
                        ],
                    }
                },
                ("key",),
            )
        elif definition.parameter_contract is ParameterContractKind.URL:
            schema = _object_schema(
                {
                    "url": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 2_048,
                        "pattern": r"^https?://.+",
                    }
                },
                ("url",),
            )
        elif definition.parameter_contract is ParameterContractKind.TAB_INDEX:
            value_schema = {
                key: value
                for key, value in value_schema.items()
                if key in {"type", "enum", "minimum", "maximum"}
            }
            if not value_schema:
                raise InteractionCapabilityError(
                    InteractionCapabilityIssueCode.SCHEMA_CONTRACT_MISMATCH,
                    semantic_action,
                )
            schema = _object_schema({"index": value_schema}, ("index",))
        else:  # pragma: no cover - closed enum guard
            raise AssertionError(definition.parameter_contract)
        self.validate_parameter_schema(semantic_action, schema)
        return to_json_compatible(schema)


@dataclass(frozen=True)
class AdapterCapabilitySupport:
    semantic_action: str
    primitive_actions: tuple[str, ...]
    subject_kinds: tuple[InteractionSubjectKind, ...]

    def __post_init__(self) -> None:
        if (
            not self.semantic_action
            or not self.primitive_actions
            or not self.subject_kinds
            or len(set(self.primitive_actions)) != len(self.primitive_actions)
            or len(set(self.subject_kinds)) != len(self.subject_kinds)
        ):
            raise ValueError("adapter capability support is invalid")
        object.__setattr__(self, "primitive_actions", tuple(self.primitive_actions))
        object.__setattr__(self, "subject_kinds", tuple(self.subject_kinds))


@dataclass(frozen=True)
class AdapterInteractionProfile:
    profile_id: str
    surface: str
    executor_id: str
    capabilities: tuple[AdapterCapabilitySupport, ...]

    def __post_init__(self) -> None:
        if not all(item.strip() for item in (self.profile_id, self.surface, self.executor_id)):
            raise ValueError("adapter interaction profile identity is invalid")
        names = tuple(item.semantic_action for item in self.capabilities)
        primitives = tuple(
            primitive for item in self.capabilities for primitive in item.primitive_actions
        )
        if len(names) != len(set(names)) or len(primitives) != len(set(primitives)):
            raise ValueError("adapter profile actions and primitives must be unique")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))


@dataclass(frozen=True)
class PrimitiveTranslator:
    """Static proof that one canonical action has one private backend primitive."""

    semantic_action: str
    primitive_action: str

    def __post_init__(self) -> None:
        if not self.semantic_action.strip() or not self.primitive_action.strip():
            raise ValueError("primitive translator identity is invalid")


@dataclass(frozen=True)
class ComposedAdapterCapability:
    semantic_definition: SemanticActionDefinition
    support: AdapterCapabilitySupport
    translators: tuple[PrimitiveTranslator, ...]


@dataclass(frozen=True)
class ComposedInteractionCapabilities:
    registry_id: str
    adapter_profile_id: str
    surface: str
    executor_id: str
    capabilities: tuple[ComposedAdapterCapability, ...]

    def resolve_action(self, semantic_action: str) -> ComposedAdapterCapability:
        matches = tuple(
            item for item in self.capabilities
            if item.semantic_definition.semantic_action == semantic_action
        )
        if len(matches) != 1:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.UNSUPPORTED_SEMANTIC_ACTION,
                semantic_action,
            )
        return matches[0]

    def resolve_primitive(self, primitive_action: str) -> PrimitiveTranslator:
        matches = tuple(
            translator
            for capability in self.capabilities
            for translator in capability.translators
            if translator.primitive_action == primitive_action
        )
        if len(matches) != 1:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.UNSUPPORTED_PRIMITIVE,
                primitive_action,
            )
        return matches[0]


@dataclass(frozen=True)
class CapabilityComposer:
    registry: InteractionCapabilityRegistry

    def compose(
        self,
        profile: AdapterInteractionProfile,
        translators: tuple[PrimitiveTranslator, ...],
    ) -> ComposedInteractionCapabilities:
        translator_keys = tuple(
            (item.semantic_action, item.primitive_action) for item in translators
        )
        if len(translator_keys) != len(set(translator_keys)):
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.TRANSLATOR_CONFLICT,
                profile.profile_id,
            )
        declared_keys = {
            (support.semantic_action, primitive)
            for support in profile.capabilities
            for primitive in support.primitive_actions
        }
        if set(translator_keys) != declared_keys:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.UNSUPPORTED_PRIMITIVE,
                profile.profile_id,
            )
        composed = []
        for support in profile.capabilities:
            definition = self.registry.require(support.semantic_action)
            if not set(support.subject_kinds).issubset(definition.subject_kinds):
                raise InteractionCapabilityError(
                    InteractionCapabilityIssueCode.SUBJECT_KIND_MISMATCH,
                    support.semantic_action,
                )
            owned = tuple(
                item for item in translators if item.semantic_action == support.semantic_action
            )
            composed.append(ComposedAdapterCapability(definition, support, owned))
        return ComposedInteractionCapabilities(
            self.registry.registry_id,
            profile.profile_id,
            profile.surface,
            profile.executor_id,
            tuple(composed),
        )


def _object_schema(
    properties: Mapping[str, object],
    required: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


def _validate_parameter_family(
    family: ParameterContractKind,
    schema: Mapping[str, object],
) -> None:
    properties = schema.get("properties")
    raw_required = schema.get("required", ())
    if not isinstance(properties, Mapping):
        raise ValueError("parameter schema properties are invalid")
    if not isinstance(raw_required, Sequence) or isinstance(raw_required, str | bytes):
        raise ValueError("parameter schema required fields are invalid")
    required = tuple(str(item) for item in raw_required)
    expected_names: tuple[str, ...]
    if family is ParameterContractKind.EMPTY:
        expected_names = ()
    elif family is ParameterContractKind.TEXT:
        expected_names = ("text",)
        _require_type(properties, "text", {"string"})
    elif family is ParameterContractKind.OPTION_VALUE:
        expected_names = ("value",)
        _require_type(properties, "value", {"string"})
    elif family is ParameterContractKind.NATIVE_VALUE:
        expected_names = ("value",)
        _require_type(properties, "value", {"boolean", "integer", "number", "string"})
    elif family is ParameterContractKind.SCROLL:
        expected_names = ("direction", "extent")
        _require_type(properties, "direction", {"string"})
        _require_type(properties, "extent", {"string"})
    elif family is ParameterContractKind.KEY:
        expected_names = ("key",)
        _require_type(properties, "key", {"string"})
    elif family is ParameterContractKind.URL:
        expected_names = ("url",)
        _require_type(properties, "url", {"string"})
    elif family is ParameterContractKind.TAB_INDEX:
        expected_names = ("index",)
        _require_type(properties, "index", {"integer"})
    else:  # pragma: no cover - closed enum guard
        raise AssertionError(family)
    if tuple(properties) != expected_names or required != expected_names:
        raise ValueError("parameter family fields or required set changed")
    if schema.get("additionalProperties", False) is not False:
        raise ValueError("interaction schemas are closed")


def _require_type(
    properties: Mapping[str, object],
    name: str,
    allowed: set[str],
) -> None:
    child = properties.get(name)
    if not isinstance(child, Mapping) or child.get("type") not in allowed:
        raise ValueError("parameter family scalar type changed")


INTERACTION_CAPABILITY_REGISTRY = InteractionCapabilityRegistry(
    "interaction-capabilities.v2",
    (
        SemanticActionDefinition(
            "activate", (InteractionSubjectKind.ENTITY,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN,
            (VerificationFamily.TARGET_STATE, VerificationFamily.NAVIGATION_CONTEXT, VerificationFamily.SEMANTIC),
        ),
        SemanticActionDefinition(
            "type_text", (InteractionSubjectKind.ENTITY,), ParameterContractKind.TEXT,
            DestinationMode.FORBIDDEN, (VerificationFamily.VALUE_STATE,),
        ),
        SemanticActionDefinition(
            "select_option", (InteractionSubjectKind.ENTITY,), ParameterContractKind.OPTION_VALUE,
            DestinationMode.FORBIDDEN,
            (VerificationFamily.VALUE_STATE, VerificationFamily.RELATION_CHANGE),
        ),
        SemanticActionDefinition(
            "read", (InteractionSubjectKind.ENTITY,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN,
            (VerificationFamily.TARGET_STATE, VerificationFamily.SEMANTIC),
        ),
        SemanticActionDefinition(
            "scroll", (InteractionSubjectKind.VIEWPORT,), ParameterContractKind.SCROLL,
            DestinationMode.FORBIDDEN, (VerificationFamily.SCROLL_STATE,),
        ),
        SemanticActionDefinition(
            "press_key", (InteractionSubjectKind.ENTITY, InteractionSubjectKind.FOCUSED_CONTEXT),
            ParameterContractKind.KEY, DestinationMode.FORBIDDEN,
            (
                VerificationFamily.VALUE_STATE, VerificationFamily.FOCUS_STATE,
                VerificationFamily.NAVIGATION_CONTEXT, VerificationFamily.SEMANTIC,
            ),
        ),
        SemanticActionDefinition(
            "focus", (InteractionSubjectKind.ENTITY,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN, (VerificationFamily.FOCUS_STATE,),
        ),
        SemanticActionDefinition(
            "drag_to", (InteractionSubjectKind.ENTITY,), ParameterContractKind.EMPTY,
            DestinationMode.REQUIRED,
            (VerificationFamily.RELATION_CHANGE, VerificationFamily.TARGET_STATE, VerificationFamily.SEMANTIC),
        ),
        SemanticActionDefinition(
            "set_value", (InteractionSubjectKind.ENTITY,), ParameterContractKind.NATIVE_VALUE,
            DestinationMode.FORBIDDEN, (VerificationFamily.VALUE_STATE,),
        ),
        SemanticActionDefinition(
            "hover", (InteractionSubjectKind.ENTITY,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN,
            (VerificationFamily.TARGET_STATE, VerificationFamily.SEMANTIC),
        ),
        SemanticActionDefinition(
            "goto", (InteractionSubjectKind.BROWSER_CONTEXT,), ParameterContractKind.URL,
            DestinationMode.FORBIDDEN, (VerificationFamily.NAVIGATION_CONTEXT,),
        ),
        SemanticActionDefinition(
            "go_back", (InteractionSubjectKind.BROWSER_CONTEXT,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN, (VerificationFamily.NAVIGATION_CONTEXT,),
        ),
        SemanticActionDefinition(
            "go_forward", (InteractionSubjectKind.BROWSER_CONTEXT,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN, (VerificationFamily.NAVIGATION_CONTEXT,),
        ),
        SemanticActionDefinition(
            "new_tab", (InteractionSubjectKind.BROWSER_CONTEXT,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN, (VerificationFamily.NAVIGATION_CONTEXT,),
        ),
        SemanticActionDefinition(
            "tab_focus", (InteractionSubjectKind.BROWSER_CONTEXT,), ParameterContractKind.TAB_INDEX,
            DestinationMode.FORBIDDEN, (VerificationFamily.NAVIGATION_CONTEXT,),
        ),
        SemanticActionDefinition(
            "tab_close", (InteractionSubjectKind.BROWSER_CONTEXT,), ParameterContractKind.EMPTY,
            DestinationMode.FORBIDDEN, (VerificationFamily.NAVIGATION_CONTEXT,),
        ),
    ),
)

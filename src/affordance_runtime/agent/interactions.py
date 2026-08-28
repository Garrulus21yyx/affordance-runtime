"""Runtime-admitted user interaction and presentation-artifact contracts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import ClassVar, TypeAlias

from affordance_runtime.agent.decisions import (
    DecisionKind,
    InteractionAttribute,
    InteractionFieldKind,
    InteractionRequestDraft,
    InteractionResponseKind,
    PublicArtifactDraft,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DECIMAL = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?")
_ADMITTED_ID = re.compile(r"(?:interaction|field|option|public-artifact|artifact-item):[0-9a-f]{32}")


def _require_admitted_id(value: str, namespace: str) -> None:
    if _ADMITTED_ID.fullmatch(value) is None or not value.startswith(f"{namespace}:"):
        raise ValueError(f"admitted {namespace} identity is invalid")


@dataclass(frozen=True)
class InteractionField:
    field_id: str
    kind: InteractionFieldKind
    label: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _require_admitted_id(self.field_id, "field")
        object.__setattr__(self, "kind", InteractionFieldKind(self.kind))
        if not self.label.strip() or len(self.label) > 120 or len(self.description) > 500:
            raise ValueError("admitted interaction field presentation is invalid")
        if type(self.required) is not bool:
            raise TypeError("admitted interaction field required flag must be boolean")


@dataclass(frozen=True)
class InteractionOption:
    option_id: str
    title: str
    description: str = ""
    media_ref: str = ""
    attributes: tuple[InteractionAttribute, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_admitted_id(self.option_id, "option")
        if not self.title.strip() or len(self.title) > 240 or len(self.description) > 1_000:
            raise ValueError("admitted interaction option presentation is invalid")
        if len(self.media_ref) > 512:
            raise ValueError("admitted interaction option media ref is invalid")
        object.__setattr__(self, "attributes", tuple(self.attributes))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "uncertainties", tuple(self.uncertainties))
        if len(self.attributes) > 16 or any(
            not isinstance(item, InteractionAttribute) for item in self.attributes
        ):
            raise TypeError("admitted interaction option attributes are invalid")
        if (
            len(self.evidence_refs) > 32
            or len(set(self.evidence_refs)) != len(self.evidence_refs)
            or any(not item.strip() or len(item) > 512 for item in self.evidence_refs)
            or len(self.uncertainties) > 32
            or any(not item.strip() or len(item) > 500 for item in self.uncertainties)
        ):
            raise ValueError("admitted interaction option evidence is invalid")


@dataclass(frozen=True)
class InteractionRequest:
    """The sole committed pending-interaction authority."""

    kind: ClassVar[DecisionKind] = DecisionKind.ASK_USER
    context_id: str
    request_id: str
    prompt: str
    response_kind: InteractionResponseKind
    fields: tuple[InteractionField, ...] = ()
    options: tuple[InteractionOption, ...] = ()
    public_intent: str = ""
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        if not self.context_id.startswith("context:"):
            raise ValueError("admitted interaction identity is invalid")
        _require_admitted_id(self.request_id, "interaction")
        if not self.prompt.strip() or len(self.prompt) > 1_000:
            raise ValueError("admitted interaction prompt is invalid")
        response_kind = InteractionResponseKind(self.response_kind)
        object.__setattr__(self, "response_kind", response_kind)
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "options", tuple(self.options))
        if any(not isinstance(item, InteractionField) for item in self.fields):
            raise TypeError("admitted interaction fields must be typed")
        if any(not isinstance(item, InteractionOption) for item in self.options):
            raise TypeError("admitted interaction options must be typed")
        if len({item.field_id for item in self.fields}) != len(self.fields):
            raise ValueError("admitted interaction field identities must be unique")
        if len({item.option_id for item in self.options}) != len(self.options):
            raise ValueError("admitted interaction option identities must be unique")
        fields = len(self.fields)
        options = len(self.options)
        valid = (
            response_kind is InteractionResponseKind.FREE_TEXT
            and fields == 0
            and options == 0
            or response_kind in {
                InteractionResponseKind.SINGLE_SELECT,
                InteractionResponseKind.MULTI_SELECT,
            }
            and fields == 0
            and 1 <= options <= 32
            or response_kind is InteractionResponseKind.STRUCTURED_FIELDS
            and 1 <= fields <= 32
            and options == 0
        )
        if not valid:
            raise ValueError("admitted interaction fields do not match its response kind")
        if len(self.public_intent) > 240 or len(self.tool_call_id) > 120:
            raise ValueError("admitted interaction metadata exceeds its bound")

    @property
    def question(self) -> str:
        return self.prompt

    @property
    def requested_fields(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.fields)


class InteractionAdmissionCode(StrEnum):
    EVIDENCE_NOT_CURRENT = "interaction_evidence_not_current"
    MEDIA_NOT_CURRENT = "interaction_media_not_current"
    REQUEST_MISMATCH = "interaction_request_mismatch"
    RESPONSE_KIND_MISMATCH = "interaction_response_kind_mismatch"
    OPTION_UNKNOWN = "interaction_option_unknown"
    OPTION_DUPLICATE = "interaction_option_duplicate"
    FIELD_UNKNOWN = "interaction_field_unknown"
    FIELD_DUPLICATE = "interaction_field_duplicate"
    REQUIRED_FIELD_MISSING = "interaction_required_field_missing"
    FIELD_VALUE_INVALID = "interaction_field_value_invalid"


@dataclass(frozen=True)
class InteractionRequestAdmission:
    request: InteractionRequest | None
    rejection_code: InteractionAdmissionCode | None = None

    @property
    def admitted(self) -> bool:
        return self.request is not None


@dataclass(frozen=True)
class FreeTextResponse:
    request_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.request_id.strip() or len(self.request_id) > 128 or not self.text.strip() or len(self.text) > 8_000:
            raise ValueError("free-text interaction response is invalid")


@dataclass(frozen=True)
class SingleSelectionResponse:
    request_id: str
    option_id: str

    def __post_init__(self) -> None:
        if not self.request_id.strip() or len(self.request_id) > 128:
            raise ValueError("single-select request identity is invalid")
        if not self.option_id.strip() or len(self.option_id) > 128:
            raise ValueError("single-select option identity is invalid")


@dataclass(frozen=True)
class MultiSelectionResponse:
    request_id: str
    option_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_ids", tuple(self.option_ids))
        if (
            not self.request_id.strip()
            or len(self.request_id) > 128
            or len(self.option_ids) > 32
            or any(not item.strip() or len(item) > 128 for item in self.option_ids)
        ):
            raise ValueError("multi-select response is invalid")


@dataclass(frozen=True)
class TextFieldValue:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.TEXT
    field_id: str
    text: str


@dataclass(frozen=True)
class IntegerFieldValue:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.INTEGER
    field_id: str
    integer: int


@dataclass(frozen=True)
class DecimalFieldValue:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.DECIMAL
    field_id: str
    decimal_string: str


@dataclass(frozen=True)
class BooleanFieldValue:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.BOOLEAN
    field_id: str
    boolean: bool


@dataclass(frozen=True)
class DateFieldValue:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.DATE
    field_id: str
    iso_date: str


InteractionFieldValue: TypeAlias = (
    TextFieldValue | IntegerFieldValue | DecimalFieldValue | BooleanFieldValue | DateFieldValue
)


@dataclass(frozen=True)
class StructuredFieldsResponse:
    request_id: str
    values: tuple[InteractionFieldValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))
        if (
            not self.request_id.strip()
            or len(self.request_id) > 128
            or len(self.values) > 32
            or any(not isinstance(item, TextFieldValue | IntegerFieldValue | DecimalFieldValue | BooleanFieldValue | DateFieldValue) for item in self.values)
        ):
            raise ValueError("structured-fields response is invalid")


InteractionResponse: TypeAlias = (
    FreeTextResponse | SingleSelectionResponse | MultiSelectionResponse | StructuredFieldsResponse
)


@dataclass(frozen=True)
class InteractionResponseAdmission:
    admitted: bool
    rejection_code: InteractionAdmissionCode | None = None


@dataclass(frozen=True)
class PublicArtifactItem:
    item_id: str
    title: str
    summary: str = ""
    attributes: tuple[InteractionAttribute, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_admitted_id(self.item_id, "artifact-item")
        if not self.title.strip() or len(self.title) > 240 or len(self.summary) > 1_000:
            raise ValueError("public artifact item presentation is invalid")
        object.__setattr__(self, "attributes", tuple(self.attributes))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if len(self.attributes) > 16 or any(
            not isinstance(item, InteractionAttribute) for item in self.attributes
        ):
            raise TypeError("public artifact item attributes are invalid")
        if (
            len(self.evidence_refs) > 32
            or len(set(self.evidence_refs)) != len(self.evidence_refs)
            or any(not item.strip() or len(item) > 512 for item in self.evidence_refs)
        ):
            raise ValueError("public artifact item evidence is invalid")


@dataclass(frozen=True)
class PublicArtifactLink:
    title: str
    artifact_ref: str

    def __post_init__(self) -> None:
        if (
            not self.title.strip()
            or len(self.title) > 240
            or not self.artifact_ref.strip()
            or len(self.artifact_ref) > 512
        ):
            raise ValueError("public artifact link is invalid")


@dataclass(frozen=True)
class PublicArtifact:
    artifact_id: str
    title: str
    summary: str = ""
    items: tuple[PublicArtifactItem, ...] = ()
    links: tuple[PublicArtifactLink, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_admitted_id(self.artifact_id, "public-artifact")
        if not self.title.strip() or len(self.title) > 240 or len(self.summary) > 2_000:
            raise ValueError("public artifact presentation is invalid")
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "links", tuple(self.links))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if len(self.items) > 32 or any(not isinstance(item, PublicArtifactItem) for item in self.items):
            raise TypeError("public artifact items are invalid")
        if len(self.links) > 32 or any(not isinstance(item, PublicArtifactLink) for item in self.links):
            raise TypeError("public artifact links are invalid")
        if (
            len(self.evidence_refs) > 32
            or len(set(self.evidence_refs)) != len(self.evidence_refs)
            or any(not item.strip() or len(item) > 512 for item in self.evidence_refs)
        ):
            raise ValueError("public artifact evidence is invalid")


def admit_interaction_request(
    world: WorldObservation,
    draft: InteractionRequestDraft,
) -> InteractionRequestAdmission:
    """Validate current refs and assign deterministic request-local identities."""

    evidence_refs = _current_evidence_refs(world)
    media_refs = _current_media_refs(world)
    if any(ref not in evidence_refs for item in draft.option_drafts for ref in item.evidence_refs):
        return InteractionRequestAdmission(None, InteractionAdmissionCode.EVIDENCE_NOT_CURRENT)
    if any(item.media_ref and item.media_ref not in media_refs for item in draft.option_drafts):
        return InteractionRequestAdmission(None, InteractionAdmissionCode.MEDIA_NOT_CURRENT)
    request_id = _identity(
        "interaction",
        world.observation_id,
        draft.context_id,
        draft.tool_call_id,
        draft.prompt,
    )
    fields = tuple(
        InteractionField(
            _identity("field", request_id, str(index)),
            field.kind,
            field.label,
            field.description,
            field.required,
        )
        for index, field in enumerate(draft.field_drafts)
    )
    options = tuple(
        InteractionOption(
            _identity("option", request_id, str(index)),
            option.title,
            option.description,
            option.media_ref,
            option.attributes,
            option.evidence_refs,
            option.uncertainties,
        )
        for index, option in enumerate(draft.option_drafts)
    )
    return InteractionRequestAdmission(
        InteractionRequest(
            draft.context_id,
            request_id,
            draft.prompt,
            draft.response_kind,
            fields,
            options,
            draft.public_intent,
            draft.tool_call_id,
        )
    )


def admit_interaction_response(
    request: InteractionRequest,
    response: InteractionResponse,
) -> InteractionResponseAdmission:
    if response.request_id != request.request_id:
        return InteractionResponseAdmission(False, InteractionAdmissionCode.REQUEST_MISMATCH)
    if request.response_kind is InteractionResponseKind.FREE_TEXT:
        return InteractionResponseAdmission(isinstance(response, FreeTextResponse), None if isinstance(response, FreeTextResponse) else InteractionAdmissionCode.RESPONSE_KIND_MISMATCH)
    if request.response_kind is InteractionResponseKind.SINGLE_SELECT:
        if not isinstance(response, SingleSelectionResponse):
            return InteractionResponseAdmission(False, InteractionAdmissionCode.RESPONSE_KIND_MISMATCH)
        valid = response.option_id in {item.option_id for item in request.options}
        return InteractionResponseAdmission(valid, None if valid else InteractionAdmissionCode.OPTION_UNKNOWN)
    if request.response_kind is InteractionResponseKind.MULTI_SELECT:
        if not isinstance(response, MultiSelectionResponse):
            return InteractionResponseAdmission(False, InteractionAdmissionCode.RESPONSE_KIND_MISMATCH)
        if len(set(response.option_ids)) != len(response.option_ids):
            return InteractionResponseAdmission(False, InteractionAdmissionCode.OPTION_DUPLICATE)
        valid = bool(response.option_ids) and set(response.option_ids).issubset(
            {item.option_id for item in request.options}
        )
        return InteractionResponseAdmission(valid, None if valid else InteractionAdmissionCode.OPTION_UNKNOWN)
    if not isinstance(response, StructuredFieldsResponse):
        return InteractionResponseAdmission(False, InteractionAdmissionCode.RESPONSE_KIND_MISMATCH)
    values = {item.field_id: item for item in response.values}
    if len(values) != len(response.values):
        return InteractionResponseAdmission(False, InteractionAdmissionCode.FIELD_DUPLICATE)
    fields = {item.field_id: item for item in request.fields}
    if not set(values).issubset(fields):
        return InteractionResponseAdmission(False, InteractionAdmissionCode.FIELD_UNKNOWN)
    if any(item.required and item.field_id not in values for item in request.fields):
        return InteractionResponseAdmission(False, InteractionAdmissionCode.REQUIRED_FIELD_MISSING)
    if any(not _field_value_valid(fields[field_id], value) for field_id, value in values.items()):
        return InteractionResponseAdmission(False, InteractionAdmissionCode.FIELD_VALUE_INVALID)
    return InteractionResponseAdmission(True)


def materialize_public_artifact(
    world: WorldObservation,
    draft: PublicArtifactDraft | None,
    *,
    response_identity: str,
) -> PublicArtifact | None:
    """Admit presentation-only model content; links remain environment-owned."""

    if draft is None:
        return None
    current = _current_evidence_refs(world)
    refs = (*draft.evidence_refs, *(ref for item in draft.items for ref in item.evidence_refs))
    if any(ref not in current for ref in refs):
        raise ValueError("public_artifact_evidence_not_current")
    artifact_id = _identity("public-artifact", world.observation_id, response_identity, draft.title)
    return PublicArtifact(
        artifact_id,
        draft.title,
        draft.summary,
        tuple(
            PublicArtifactItem(
                _identity("artifact-item", artifact_id, str(index)),
                item.title,
                item.summary,
                item.attributes,
                item.evidence_refs,
            )
            for index, item in enumerate(draft.items)
        ),
        (),
        draft.evidence_refs,
    )


def interaction_response_public_value(response: InteractionResponse) -> dict[str, object]:
    if isinstance(response, FreeTextResponse):
        return {"kind": "free_text", "request_id": response.request_id, "text": response.text}
    if isinstance(response, SingleSelectionResponse):
        return {"kind": "single_select", "request_id": response.request_id, "option_id": response.option_id}
    if isinstance(response, MultiSelectionResponse):
        return {"kind": "multi_select", "request_id": response.request_id, "option_ids": response.option_ids}
    return {
        "kind": "structured_fields",
        "request_id": response.request_id,
        "values": tuple(_field_value_public_value(item) for item in response.values),
    }


def interaction_request_public_value(request: InteractionRequest) -> dict[str, object]:
    return {
        "request_id": request.request_id,
        "context_id": request.context_id,
        "prompt": request.prompt,
        "response_kind": request.response_kind.value,
        "fields": tuple(
            {
                "field_id": item.field_id,
                "kind": item.kind.value,
                "label": item.label,
                "description": item.description,
                "required": item.required,
            }
            for item in request.fields
        ),
        "options": tuple(
            {
                "option_id": item.option_id,
                "title": item.title,
                "description": item.description,
                "media_ref": item.media_ref,
                "attributes": tuple(
                    {"label": attribute.label, "value": attribute.value}
                    for attribute in item.attributes
                ),
                "evidence_refs": item.evidence_refs,
                "uncertainties": item.uncertainties,
            }
            for item in request.options
        ),
        "public_intent": request.public_intent,
        "tool_call_id": request.tool_call_id,
    }


def public_artifact_public_value(artifact: PublicArtifact) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "title": artifact.title,
        "summary": artifact.summary,
        "items": tuple(
            {
                "item_id": item.item_id,
                "title": item.title,
                "summary": item.summary,
                "attributes": tuple(
                    {"label": attribute.label, "value": attribute.value}
                    for attribute in item.attributes
                ),
                "evidence_refs": item.evidence_refs,
            }
            for item in artifact.items
        ),
        "links": tuple(
            {"title": item.title, "artifact_ref": item.artifact_ref}
            for item in artifact.links
        ),
        "evidence_refs": artifact.evidence_refs,
    }


def restore_public_artifact_public_value(value: object) -> PublicArtifact:
    raw = _mapping(value)
    return PublicArtifact(
        str(raw["artifact_id"]),
        str(raw["title"]),
        str(raw.get("summary", "")),
        tuple(_restore_artifact_item(item) for item in _sequence(raw.get("items", ()))),
        tuple(
            PublicArtifactLink(
                str(_mapping(item)["title"]),
                str(_mapping(item)["artifact_ref"]),
            )
            for item in _sequence(raw.get("links", ()))
        ),
        tuple(str(item) for item in _sequence(raw.get("evidence_refs", ()))),
    )


def restore_interaction_request_public_value(value: object) -> InteractionRequest:
    if not isinstance(value, Mapping):
        raise ValueError("persisted interaction request must be an object")
    raw_fields = value.get("fields", ())
    raw_options = value.get("options", ())
    if not isinstance(raw_fields, list | tuple) or not isinstance(raw_options, list | tuple):
        raise ValueError("persisted interaction collections are invalid")
    fields = tuple(
        InteractionField(
            str(_mapping(item)["field_id"]),
            InteractionFieldKind(str(_mapping(item)["kind"])),
            str(_mapping(item)["label"]),
            str(_mapping(item).get("description", "")),
            bool(_mapping(item).get("required", True)),
        )
        for item in raw_fields
    )
    options = tuple(_restore_option(item) for item in raw_options)
    return InteractionRequest(
        str(value["context_id"]),
        str(value["request_id"]),
        str(value["prompt"]),
        InteractionResponseKind(str(value["response_kind"])),
        fields,
        options,
        str(value.get("public_intent", "")),
        str(value.get("tool_call_id", "")),
    )


def legacy_interaction_request(
    *,
    context_id: str,
    prompt: str,
    requested_fields: tuple[str, ...],
    tool_call_id: str = "",
) -> InteractionRequest:
    """Read-only checkpoint migration into the one current admitted contract."""

    request_id = _identity("interaction", "legacy-checkpoint", context_id, tool_call_id, prompt)
    fields = tuple(
        InteractionField(
            _identity("field", request_id, str(index)),
            InteractionFieldKind.TEXT,
            label,
        )
        for index, label in enumerate(requested_fields)
    )
    return InteractionRequest(
        context_id,
        request_id,
        prompt,
        InteractionResponseKind.STRUCTURED_FIELDS if fields else InteractionResponseKind.FREE_TEXT,
        fields,
        (),
        tool_call_id=tool_call_id,
    )


def _field_value_public_value(value: InteractionFieldValue) -> dict[str, object]:
    payload: dict[str, object] = {"kind": value.kind.value, "field_id": value.field_id}
    if isinstance(value, TextFieldValue):
        payload["text"] = value.text
    elif isinstance(value, IntegerFieldValue):
        payload["integer"] = value.integer
    elif isinstance(value, DecimalFieldValue):
        payload["decimal_string"] = value.decimal_string
    elif isinstance(value, BooleanFieldValue):
        payload["boolean"] = value.boolean
    else:
        payload["iso_date"] = value.iso_date
    return payload


def _restore_option(value: object) -> InteractionOption:
    raw = _mapping(value)
    raw_attributes = raw.get("attributes", ())
    if not isinstance(raw_attributes, list | tuple):
        raise ValueError("persisted interaction attributes are invalid")
    return InteractionOption(
        str(raw["option_id"]),
        str(raw["title"]),
        str(raw.get("description", "")),
        str(raw.get("media_ref", "")),
        tuple(
            InteractionAttribute(str(_mapping(item)["label"]), str(_mapping(item)["value"]))
            for item in raw_attributes
        ),
        tuple(str(item) for item in _sequence(raw.get("evidence_refs", ()))),
        tuple(str(item) for item in _sequence(raw.get("uncertainties", ()))),
    )


def _restore_artifact_item(value: object) -> PublicArtifactItem:
    raw = _mapping(value)
    return PublicArtifactItem(
        str(raw["item_id"]),
        str(raw["title"]),
        str(raw.get("summary", "")),
        tuple(
            InteractionAttribute(str(_mapping(item)["label"]), str(_mapping(item)["value"]))
            for item in _sequence(raw.get("attributes", ()))
        ),
        tuple(str(item) for item in _sequence(raw.get("evidence_refs", ()))),
    )


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("persisted interaction member must be an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("persisted interaction member must be an array")
    return tuple(value)


def _field_value_valid(field: InteractionField, value: InteractionFieldValue) -> bool:
    if field.kind is not value.kind:
        return False
    if isinstance(value, TextFieldValue):
        return bool(value.text.strip()) and len(value.text) <= 8_000
    if isinstance(value, IntegerFieldValue):
        return type(value.integer) is int
    if isinstance(value, DecimalFieldValue):
        if _DECIMAL.fullmatch(value.decimal_string) is None or len(value.decimal_string) > 128:
            return False
        try:
            return format(Decimal(value.decimal_string), "f") == value.decimal_string
        except InvalidOperation:
            return False
    if isinstance(value, BooleanFieldValue):
        return type(value.boolean) is bool
    return _ISO_DATE.fullmatch(value.iso_date) is not None and _valid_calendar_date(value.iso_date)


def _valid_calendar_date(value: str) -> bool:
    from datetime import date

    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _current_evidence_refs(world: WorldObservation) -> frozenset[str]:
    return frozenset(
        item.evidence_ref
        for item in (*WorldEvidenceIndex.from_observation(world).records, *public_text_evidence_records(world))
    ) | _current_media_refs(world)


def _current_media_refs(world: WorldObservation) -> frozenset[str]:
    return frozenset(
        canonical_artifact_ref(item.source_observation_id, item.media.media_id)
        for item in world.media
    )


def _identity(namespace: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()
    return f"{namespace}:{digest[:32]}"

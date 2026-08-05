"""Lightweight source identity and selective lineage anchors."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceKind(StrEnum):
    REQUEST = "request"
    CONVERSATION = "conversation"
    ATTACHMENT = "attachment"
    TARGET = "target"
    PROFILE = "profile"
    EXTERNAL = "external"


class MaterialField(StrEnum):
    RECIPIENT = "recipient"
    AMOUNT = "amount"
    ACCOUNT = "account"
    EXTERNAL_DESTINATION = "external_destination"
    DESTRUCTIVE_TARGET = "destructive_target"
    FILE = "file"
    FORBIDDEN_EFFECT = "forbidden_effect"
    APPROVAL_CONSTRAINT = "approval_constraint"


class SourceRef(_FrozenModel):
    source_id: str = Field(min_length=1, max_length=240)
    kind: SourceKind
    version: str = Field(min_length=1, max_length=120)
    external_ref: str = Field(default="", max_length=480)


class SourceAnchor(_FrozenModel):
    anchor_id: str = Field(min_length=1, max_length=240)
    source_id: str = Field(min_length=1, max_length=240)
    material_field: MaterialField | None = None
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_length: int = Field(ge=0)

    @property
    def span(self) -> tuple[int, int] | None:
        if self.span_start is None or self.span_end is None:
            return None
        return self.span_start, self.span_end

    @model_validator(mode="after")
    def validate_span(self) -> "SourceAnchor":
        if (self.span_start is None) != (self.span_end is None):
            raise ValueError("anchor span boundaries must be supplied together")
        if self.material_field is None and self.span is not None:
            raise ValueError("only material anchors may carry an exact span")
        if self.material_field is not None and self.span is None:
            raise ValueError("material anchors require an exact span")
        if self.span is not None:
            start, end = self.span
            if end <= start or end - start != self.content_length:
                raise ValueError("anchor span must be non-empty and match content length")
        return self


class SourceEnvelope(_FrozenModel):
    schema_version: str = "1"
    request_id: str = Field(min_length=1, max_length=240)
    request_revision: int = Field(default=1, ge=1)
    conversation_revision: int = Field(default=1, ge=1)
    caller_revision: str = Field(default="", max_length=120)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_length: int = Field(ge=1)
    sources: tuple[SourceRef, ...] = Field(min_length=1)
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1)
    binding_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @property
    def identity(self) -> str:
        payload = self.model_dump_json(exclude={"binding_digest"})
        return _digest(payload)

    @property
    def whole_request_anchor(self) -> SourceAnchor:
        return self.anchors[0]


class _RequestSources(Protocol):
    request_id: str
    raw_text: str
    conversation_refs: tuple[str, ...]
    attachment_refs: tuple[str, ...]
    target_refs: tuple[str, ...]
    profile_context_refs: tuple[str, ...]
    caller_identity: str


class SourceEnvelopeBuilder:
    """Build identity metadata without clause splitting or semantic interpretation."""

    def build(
        self,
        request: _RequestSources,
        *,
        request_revision: int = 1,
        conversation_revision: int = 1,
        caller_revision: str = "",
        external_source_refs: tuple[str, ...] = (),
        exact_anchors: tuple[tuple[MaterialField, int, int], ...] = (),
    ) -> SourceEnvelope:
        raw_text = request.raw_text
        request_source_id = f"{request.request_id}:source:request"
        sources = [
            SourceRef(
                source_id=request_source_id,
                kind=SourceKind.REQUEST,
                version=f"request:{request_revision}",
            )
        ]
        for kind, refs in (
            (SourceKind.CONVERSATION, request.conversation_refs),
            (SourceKind.ATTACHMENT, request.attachment_refs),
            (SourceKind.TARGET, request.target_refs),
            (SourceKind.PROFILE, request.profile_context_refs),
            (SourceKind.EXTERNAL, external_source_refs),
        ):
            sources.extend(
                SourceRef(
                    source_id=f"{request.request_id}:source:{kind.value}:{index}",
                    kind=kind,
                    version="ref:1",
                    external_ref=reference,
                )
                for index, reference in enumerate(refs)
            )
        anchors = [
            SourceAnchor(
                anchor_id=f"{request.request_id}:anchor:whole-request",
                source_id=request_source_id,
                content_digest=_digest(raw_text),
                content_length=len(raw_text),
            )
        ]
        for index, (field, start, end) in enumerate(exact_anchors):
            if start < 0 or end > len(raw_text):
                raise ValueError("exact source anchor lies outside the request")
            excerpt = raw_text[start:end]
            anchors.append(
                SourceAnchor(
                    anchor_id=f"{request.request_id}:anchor:{field.value}:{index}",
                    source_id=request_source_id,
                    material_field=field,
                    span_start=start,
                    span_end=end,
                    content_digest=_digest(excerpt),
                    content_length=len(excerpt),
                )
            )
        binding_payload = json.dumps(
            {
                "request_id": request.request_id,
                "request_revision": request_revision,
                "conversation_revision": conversation_revision,
                "caller_revision": caller_revision or request.caller_identity,
                "sources": [item.model_dump(mode="json") for item in sources],
                "anchors": [item.model_dump(mode="json") for item in anchors],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return SourceEnvelope(
            request_id=request.request_id,
            request_revision=request_revision,
            conversation_revision=conversation_revision,
            caller_revision=caller_revision or request.caller_identity,
            content_digest=_digest(raw_text),
            content_length=len(raw_text),
            sources=tuple(sources),
            anchors=tuple(anchors),
            binding_digest=_digest(binding_payload),
        )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()

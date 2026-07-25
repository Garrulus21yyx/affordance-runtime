"""Deterministic, privacy-safe source lineage for natural-language intake.

This module owns source-unit identity only.  It deliberately does not infer
intent, construct task graphs, or grant authority to model-produced data.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceKind(StrEnum):
    REQUEST = "request"
    CONVERSATION = "conversation"
    ATTACHMENT = "attachment"
    TARGET = "target"
    PROFILE_CONTEXT = "profile_context"


class SourceSensitivity(StrEnum):
    USER_CONTENT = "user_content"
    REFERENCE_ONLY = "reference_only"


class SourceUnit(_StrictModel):
    """One canonical, non-semantic unit of authorized input lineage."""

    source_unit_id: str = Field(min_length=1, max_length=240)
    source_ref: str = Field(min_length=1, max_length=240)
    source_kind: SourceKind
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_length: int = Field(ge=0)
    required_candidate: bool = False
    sensitivity: SourceSensitivity

    @model_validator(mode="after")
    def validate_span(self) -> "SourceUnit":
        if (self.span_start is None) != (self.span_end is None):
            raise ValueError("source unit span boundaries must be supplied together")
        if self.span_start is not None:
            if self.source_kind != SourceKind.REQUEST:
                raise ValueError("only request source units may carry raw-text spans")
            if self.span_end is None or self.span_end <= self.span_start:
                raise ValueError("source unit span must be non-empty")
            if self.span_end - self.span_start != self.content_length:
                raise ValueError("source unit span must match content length")
        elif self.content_length:
            raise ValueError("reference-only source unit cannot claim content length")
        return self


class SourceLedger(_StrictModel):
    """Immutable ledger metadata safe to expose in traces and model context."""

    ledger_version: str = "1"
    request_id: str = Field(min_length=1, max_length=240)
    units: tuple[SourceUnit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_units(self) -> "SourceLedger":
        ids = [unit.source_unit_id for unit in self.units]
        if len(ids) != len(set(ids)):
            raise ValueError("source ledger unit ids must be unique")
        return self

    @property
    def identity(self) -> str:
        payload = self.model_dump_json()
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

    @property
    def raw_text_unit_id(self) -> str:
        for unit in self.units:
            if unit.source_unit_id.endswith(":request:whole"):
                return unit.source_unit_id
        raise ValueError("source ledger has no whole-request unit")

    def model_context(self) -> dict[str, object]:
        """Return non-secret source metadata for bounded model interpretation."""

        return {
            "ledger_version": self.ledger_version,
            "ledger_identity": self.identity,
            "raw_text_source_unit_id": self.raw_text_unit_id,
            "source_units": [unit.model_dump(mode="json") for unit in self.units],
        }


class _RequestSources(Protocol):
    request_id: str
    raw_text: str
    conversation_refs: tuple[str, ...]
    attachment_refs: tuple[str, ...]
    target_refs: tuple[str, ...]
    profile_context_refs: tuple[str, ...]


class SourceLedgerBuilder:
    """Build bounded source identity without parsing task semantics."""

    ledger_version = "1"
    max_clause_units = 32
    _CLAUSE_BOUNDARY = re.compile(r"(?:[.!?]+(?=\s|$)|;|\n+)")

    def build(self, request: _RequestSources) -> SourceLedger:
        raw_text = request.raw_text
        units = [
            self._request_unit(
                request.request_id,
                "request:whole",
                raw_text,
                0,
                len(raw_text),
                required_candidate=False,
            )
        ]
        clauses = self._clause_spans(raw_text)
        if len(clauses) > self.max_clause_units:
            raise ValueError("source ledger clause bound exceeded")
        units.extend(
            self._request_unit(
                request.request_id,
                f"request:clause:{index}",
                raw_text[start:end],
                start,
                end,
                required_candidate=True,
            )
            for index, (start, end) in enumerate(clauses)
        )
        units.extend(
            self._reference_units(request.request_id, SourceKind.CONVERSATION, request.conversation_refs)
        )
        units.extend(
            self._reference_units(request.request_id, SourceKind.ATTACHMENT, request.attachment_refs)
        )
        units.extend(self._reference_units(request.request_id, SourceKind.TARGET, request.target_refs))
        units.extend(
            self._reference_units(
                request.request_id,
                SourceKind.PROFILE_CONTEXT,
                request.profile_context_refs,
            )
        )
        return SourceLedger(request_id=request.request_id, units=tuple(units))

    @staticmethod
    def _request_unit(
        request_id: str,
        suffix: str,
        content: str,
        start: int,
        end: int,
        *,
        required_candidate: bool,
    ) -> SourceUnit:
        return SourceUnit(
            source_unit_id=f"{request_id}:source:{suffix}",
            source_ref=request_id,
            source_kind=SourceKind.REQUEST,
            span_start=start,
            span_end=end,
            content_sha256=_sha256(content),
            content_length=len(content),
            required_candidate=required_candidate,
            sensitivity=SourceSensitivity.USER_CONTENT,
        )

    @staticmethod
    def _reference_units(
        request_id: str,
        source_kind: SourceKind,
        refs: tuple[str, ...],
    ) -> tuple[SourceUnit, ...]:
        return tuple(
            SourceUnit(
                source_unit_id=f"{request_id}:source:{source_kind.value}:{index}",
                source_ref=reference,
                source_kind=source_kind,
                content_sha256=_sha256(reference),
                content_length=0,
                sensitivity=SourceSensitivity.REFERENCE_ONLY,
            )
            for index, reference in enumerate(refs)
        )

    @classmethod
    def _clause_spans(cls, raw_text: str) -> tuple[tuple[int, int], ...]:
        spans: list[tuple[int, int]] = []
        start = 0
        for match in cls._CLAUSE_BOUNDARY.finditer(raw_text):
            end = match.end()
            span = cls._trimmed_span(raw_text, start, end)
            if span is not None:
                spans.append(span)
            start = end
        span = cls._trimmed_span(raw_text, start, len(raw_text))
        if span is not None:
            spans.append(span)
        return tuple(spans)

    @staticmethod
    def _trimmed_span(raw_text: str, start: int, end: int) -> tuple[int, int] | None:
        while start < end and raw_text[start].isspace():
            start += 1
        while end > start and raw_text[end - 1].isspace():
            end -= 1
        return (start, end) if start < end else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

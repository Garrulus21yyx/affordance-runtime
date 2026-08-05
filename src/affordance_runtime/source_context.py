"""Bounded, source-bound raw context for the three semantic consumers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from affordance_runtime.source_envelope import SourceEnvelope
from affordance_runtime.task_intake import StrictModel, UserRequest


class SourceContextConsumer(StrEnum):
    TASK_PLANNER = "task_planner"
    OPEN_SEMANTIC_RESOLVER = "open_semantic_resolver"
    CLARIFICATION_COMPOSER = "clarification_composer"


class AnchoredExcerpt(StrictModel):
    anchor_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=4_000)
    content_digest: str = Field(min_length=1)


class SourceContextView(StrictModel):
    consumer: SourceContextConsumer
    source_envelope_ref: str = Field(min_length=1)
    source_binding_digest: str = Field(min_length=1)
    cited_semantic_ids: tuple[str, ...] = ()
    excerpts: tuple[AnchoredExcerpt, ...] = Field(min_length=1)
    context_only: bool = True


class TaskSpecGap(StrictModel):
    gap_id: str = Field(min_length=1)
    missing_field: str = Field(min_length=1)
    anchor_ids: tuple[str, ...]
    clarification: str = Field(min_length=1)


class SourceContextProjector:
    max_total_characters = 4_000

    def project(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        *,
        consumer: SourceContextConsumer,
        anchor_ids: tuple[str, ...],
        cited_semantic_ids: tuple[str, ...] = (),
    ) -> SourceContextView:
        if not isinstance(consumer, SourceContextConsumer):
            raise PermissionError("source context consumer is not allowed")
        if request.request_id != envelope.request_id:
            raise ValueError("source context request does not match envelope")
        anchors = {item.anchor_id: item for item in envelope.anchors}
        excerpts: list[AnchoredExcerpt] = []
        total = 0
        for anchor_id in dict.fromkeys(anchor_ids):
            anchor = anchors.get(anchor_id)
            if anchor is None:
                raise ValueError("source context anchor is not envelope-bound")
            if (
                consumer == SourceContextConsumer.OPEN_SEMANTIC_RESOLVER
                and anchor.span is None
            ):
                raise PermissionError("open semantic resolver requires an exact linked excerpt")
            if anchor.span is None:
                content = request.raw_text
            else:
                start, end = anchor.span
                content = request.raw_text[start:end]
            total += len(content)
            if total > self.max_total_characters:
                raise ValueError("source context exceeds bounded projection limit")
            excerpts.append(
                AnchoredExcerpt(
                    anchor_id=anchor.anchor_id,
                    source_id=anchor.source_id,
                    content=content,
                    content_digest=anchor.content_digest,
                )
            )
        if not excerpts:
            raise ValueError("source context requires at least one linked anchor")
        return SourceContextView(
            consumer=consumer,
            source_envelope_ref=envelope.identity,
            source_binding_digest=envelope.binding_digest,
            cited_semantic_ids=cited_semantic_ids,
            excerpts=tuple(excerpts),
        )

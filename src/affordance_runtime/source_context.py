"""Bounded, source-bound raw context for the three semantic consumers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from affordance_runtime.source_envelope import SourceEnvelope
from affordance_runtime.task_intake import StrictModel, TaskSpec, UserRequest
from affordance_runtime.verification.contracts import SuccessExpression


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
    requirement_ids: tuple[str, ...] = ()
    criterion_ids: tuple[str, ...] = ()
    effect_authorization_ids: tuple[str, ...] = ()
    input_binding_ids: tuple[str, ...] = ()
    source_anchor_ids: tuple[str, ...] = Field(min_length=1)
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
        task_spec: TaskSpec,
        *,
        consumer: SourceContextConsumer,
        anchor_ids: tuple[str, ...],
        requirement_ids: tuple[str, ...] = (),
        criterion_ids: tuple[str, ...] = (),
        effect_authorization_ids: tuple[str, ...] = (),
        input_binding_ids: tuple[str, ...] = (),
    ) -> SourceContextView:
        if not isinstance(consumer, SourceContextConsumer):
            raise PermissionError("source context consumer is not allowed")
        if request.request_id != envelope.request_id:
            raise ValueError("source context request does not match envelope")
        if task_spec.source_envelope_ref != envelope.identity:
            raise ValueError("source context TaskSpec does not match envelope")
        _require_subset(
            "requirement",
            requirement_ids,
            {item.requirement_id for item in task_spec.requirements},
        )
        _require_subset(
            "effect authorization",
            effect_authorization_ids,
            set(task_spec.allowed_effect_refs),
        )
        _require_subset(
            "input binding",
            input_binding_ids,
            {item.binding_id for item in task_spec.inputs},
        )
        admitted_criterion_ids = {
            *_success_criterion_ids(task_spec.success),
            *task_spec.constraint_criterion_ids,
            *task_spec.external_effect_criterion_ids,
            *task_spec.final_recheck_criterion_ids,
            *(item.materialization_criterion_id for item in task_spec.required_outputs),
        }
        _require_subset("criterion", criterion_ids, admitted_criterion_ids)
        if not any(
            (requirement_ids, criterion_ids, effect_authorization_ids, input_binding_ids)
        ):
            raise ValueError("source context requires an admitted semantic identity")
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
            requirement_ids=requirement_ids,
            criterion_ids=criterion_ids,
            effect_authorization_ids=effect_authorization_ids,
            input_binding_ids=input_binding_ids,
            source_anchor_ids=tuple(dict.fromkeys(anchor_ids)),
            excerpts=tuple(excerpts),
        )


def _require_subset(label: str, values: tuple[str, ...], allowed: set[str]) -> None:
    if len(values) != len(set(values)) or any(not item.strip() for item in values):
        raise ValueError(f"source context {label} ids must be unique and nonblank")
    if set(values) - allowed:
        raise PermissionError(f"source context {label} is not admitted by TaskSpec")


def _success_criterion_ids(expression: SuccessExpression | None) -> tuple[str, ...]:
    if expression is None:
        return ()
    if expression.operator == "criterion":
        return (expression.criterion_id,)
    return tuple(
        criterion_id
        for child in expression.children
        for criterion_id in _success_criterion_ids(child)
    )

"""Bounded, source-bound raw context for the three semantic consumers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from affordance_runtime.source_envelope import SourceEnvelope
from affordance_runtime.task_intake import (
    StrictModel,
    TaskSpec,
    UserRequest,
    success_criterion_requirement_bindings,
)


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
            *success_criterion_requirement_bindings(task_spec.success),
            *(item.criterion_id for item in task_spec.criterion_source_bindings),
        }
        _require_subset("criterion", criterion_ids, admitted_criterion_ids)
        if not any((requirement_ids, criterion_ids, effect_authorization_ids, input_binding_ids)):
            raise ValueError("source context requires an admitted semantic identity")
        anchors = {item.anchor_id: item for item in envelope.anchors}
        allowed_anchor_ids = _semantic_anchor_ids(
            task_spec,
            anchors,
            requirement_ids=requirement_ids,
            criterion_ids=criterion_ids,
            effect_authorization_ids=effect_authorization_ids,
            input_binding_ids=input_binding_ids,
        )
        if set(anchor_ids) - allowed_anchor_ids:
            raise PermissionError("source context anchor is not bound to the requested semantic identity")
        excerpts: list[AnchoredExcerpt] = []
        total = 0
        for anchor_id in dict.fromkeys(anchor_ids):
            anchor = anchors.get(anchor_id)
            if anchor is None:
                raise ValueError("source context anchor is not envelope-bound")
            if consumer == SourceContextConsumer.OPEN_SEMANTIC_RESOLVER and anchor.span is None:
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
            source_binding_digest=task_spec.source_binding_digest,
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


def _semantic_anchor_ids(
    task_spec: TaskSpec,
    anchors: dict[str, object],
    *,
    requirement_ids: tuple[str, ...],
    criterion_ids: tuple[str, ...],
    effect_authorization_ids: tuple[str, ...],
    input_binding_ids: tuple[str, ...],
) -> set[str]:
    requested_requirements = set(requirement_ids) | set(effect_authorization_ids)
    criterion_bindings = {item.criterion_id: item.requirement_refs for item in task_spec.criterion_source_bindings}
    criterion_bindings.update(success_criterion_requirement_bindings(task_spec.success))
    for criterion_id in criterion_ids:
        requested_requirements.update(criterion_bindings[criterion_id])
    allowed = {
        anchor_id
        for requirement in task_spec.requirements
        if requirement.requirement_id in requested_requirements
        for anchor_id in requirement.source_anchor_refs
    }
    requested_inputs = set(input_binding_ids)
    for binding in task_spec.inputs:
        if binding.binding_id not in requested_inputs:
            continue
        if binding.source_anchor_ref:
            allowed.add(binding.source_anchor_ref)
        if binding.source_ref in anchors:
            allowed.add(binding.source_ref)
        allowed.update(
            anchor_id for anchor_id, anchor in anchors.items() if getattr(anchor, "source_id", "") == binding.source_ref
        )
    return allowed

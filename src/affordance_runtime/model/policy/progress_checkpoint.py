"""Typed, bounded semantic checkpoint for compact PydanticAI history.

The checkpoint is model-authored working context.  It is neither current World
truth nor Runtime plan state.  Runtime validates only its closed schema, bounds,
and source lineage before the history owner may replace covered raw exchanges.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROGRESS_CHECKPOINT_VERSION: Literal["progress-checkpoint.v2"] = "progress-checkpoint.v2"
PROGRESS_CHECKPOINT_PREFIX = "Non-authoritative progress checkpoint (fresh World wins):\n"
MAX_PROGRESS_CHECKPOINT_BYTES = 6 * 1024


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SourceRef(_ClosedModel):
    tool_call_id: str = Field(min_length=1, max_length=160)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


class VerifiedFact(_ClosedModel):
    claim: str = Field(min_length=1, max_length=240)
    value: str = Field(min_length=1, max_length=800)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1, max_length=8)


class WorkingHypothesis(_ClosedModel):
    claim: str = Field(min_length=1, max_length=360)
    needs_verification: bool = True
    source_refs: tuple[SourceRef, ...] = Field(default=(), max_length=8)


class FailedStrategy(_ClosedModel):
    strategy: str = Field(min_length=1, max_length=320)
    outcome: str = Field(min_length=1, max_length=320)


class ProgressCheckpoint(_ClosedModel):
    """One complete replacement of the model's durable working conclusions."""

    version: Literal["progress-checkpoint.v2"] = PROGRESS_CHECKPOINT_VERSION
    verified_facts: tuple[VerifiedFact, ...] = Field(default=(), max_length=16)
    working_hypotheses: tuple[WorkingHypothesis, ...] = Field(default=(), max_length=12)
    remaining_questions: tuple[str, ...] = Field(default=(), max_length=16)
    next_intent: str = Field(min_length=1, max_length=360)
    failed_strategies: tuple[FailedStrategy, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def _validate_checkpoint(self) -> ProgressCheckpoint:
        collections = (
            tuple((item.claim, item.value) for item in self.verified_facts),
            tuple(item.claim for item in self.working_hypotheses),
            self.remaining_questions,
            tuple((item.strategy, item.outcome) for item in self.failed_strategies),
        )
        if any(len(items) != len(set(items)) for items in collections):
            raise ValueError("progress checkpoint entries must be unique")
        rendered = self.render()
        if len(rendered.encode("utf-8")) > MAX_PROGRESS_CHECKPOINT_BYTES:
            raise ValueError("progress checkpoint exceeds its history bound")
        return self

    def render(self) -> str:
        body = self.model_dump_json(exclude_none=True)
        return PROGRESS_CHECKPOINT_PREFIX + body

    @classmethod
    def parse(cls, text: object) -> ProgressCheckpoint | None:
        if not isinstance(text, str) or not text.startswith(PROGRESS_CHECKPOINT_PREFIX):
            return None
        if len(text.encode("utf-8")) > MAX_PROGRESS_CHECKPOINT_BYTES:
            return None
        try:
            return cls.model_validate_json(text.removeprefix(PROGRESS_CHECKPOINT_PREFIX))
        except (ValueError, TypeError):
            return None

    def source_refs(self) -> frozenset[tuple[str, str]]:
        refs = {
            (source.tool_name, source.tool_call_id)
            for fact in self.verified_facts
            for source in fact.source_refs
        }
        refs.update(
            (source.tool_name, source.tool_call_id)
            for hypothesis in self.working_hypotheses
            for source in hypothesis.source_refs
        )
        return frozenset(refs)


class CheckpointReduction(_ClosedModel):
    outcome: Literal["updated", "unchanged"]
    checkpoint: ProgressCheckpoint | None = None

    @model_validator(mode="after")
    def _validate_outcome(self) -> CheckpointReduction:
        if (self.outcome == "updated") != (self.checkpoint is not None):
            raise ValueError("checkpoint reduction outcome and payload disagree")
        return self

from __future__ import annotations

import json
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .conversation import BoundedConversationContext


class RevisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RevisionReady(RevisionModel):
    kind: Literal["revision_ready"] = "revision_ready"
    revised_task: str = Field(min_length=1, max_length=8000)


class NeedsInput(RevisionModel):
    kind: Literal["needs_input"] = "needs_input"
    question: str = Field(min_length=1, max_length=1000)


class NoChange(RevisionModel):
    kind: Literal["no_change"] = "no_change"


class NewTaskSuggested(RevisionModel):
    kind: Literal["new_task_suggested"] = "new_task_suggested"
    task: str = Field(min_length=1, max_length=8000)


class UnsupportedRevision(RevisionModel):
    kind: Literal["unsupported"] = "unsupported"
    reason: str = Field(min_length=1, max_length=1000)


class FailedRevision(RevisionModel):
    kind: Literal["failed"] = "failed"
    code: str = Field(min_length=1, max_length=128)


RevisionOutcome = Annotated[
    RevisionReady | NeedsInput | NoChange | NewTaskSuggested | UnsupportedRevision | FailedRevision,
    Field(discriminator="kind"),
]
REVISION_ADAPTER = TypeAdapter(RevisionOutcome)


class StructuredRevisionProvider(Protocol):
    async def compile(self, payload: dict[str, object]) -> object: ...


class PydanticAIRevisionProvider:
    """Optional mature structured-output transport; exactly one model run."""

    def __init__(self, model: str) -> None:
        from pydantic_ai import Agent

        self._agent = Agent(
            model,
            output_type=(
                RevisionReady,
                NeedsInput,
                NoChange,
                NewTaskSuggested,
                UnsupportedRevision,
                FailedRevision,
            ),
            retries=0,
            instructions=(
                "Interpret only the user-owned task revision. Prefer the exact pending question identity "
                "for elliptical replies. Never produce GUI actions, selectors, coordinates, permissions, "
                "plan progress, or completion."
            ),
        )

    async def compile(self, payload: dict[str, object]) -> object:
        result = await self._agent.run(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return result.output


class TaskRevisionCompiler:
    """One provider call; no GUI action, permission, plan, or completion output exists in its schema."""

    def __init__(self, provider: StructuredRevisionProvider | None) -> None:
        self._provider = provider

    async def compile(
        self,
        current_task: str,
        context: BoundedConversationContext,
        latest_user_message: str,
    ) -> RevisionOutcome:
        if self._provider is None:
            return UnsupportedRevision(reason="revision model provider is not configured")
        pending = context.pending_question.model_dump() if context.pending_question else None
        payload: dict[str, object] = {
            "current_task": current_task,
            "current_task_id": context.current_task_id,
            "current_task_revision": context.current_task_revision,
            "recent_turns": [turn.model_dump() for turn in context.recent_turns],
            "pending_question": pending,
            "latest_user_message": latest_user_message,
            "instruction": (
                "Resolve ellipsis against pending_question identity first. Return exactly one closed "
                "revision outcome. Never emit actions, selectors, coordinates, plan progress, completion, "
                "or permissions."
            ),
        }
        try:
            raw = await self._provider.compile(payload)
            return REVISION_ADAPTER.validate_python(raw)
        except Exception:  # noqa: BLE001 - provider/schema failures collapse to one typed outcome
            return FailedRevision(code="revision_provider_or_schema_failure")

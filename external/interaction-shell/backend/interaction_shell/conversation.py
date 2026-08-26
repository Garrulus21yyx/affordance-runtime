from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import PendingConfirmation, PendingQuestion, RuntimeSessionSnapshot


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


@dataclass(frozen=True)
class BoundedConversationContext:
    current_task_id: str | None
    current_task_revision: int
    recent_turns: tuple[ConversationTurn, ...]
    pending_question: PendingQuestion | None
    pending_confirmation: PendingConfirmation | None
    latest_user_message: str


class BoundedConversation:
    def __init__(self, max_turns: int = 6) -> None:
        if not 3 <= max_turns <= 6:
            raise ValueError("conversation window must contain 3..6 turns")
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    def append(self, turn: ConversationTurn) -> None:
        self._turns.append(turn)

    def view(self, snapshot: RuntimeSessionSnapshot, latest_user_message: str = "") -> BoundedConversationContext:
        return BoundedConversationContext(
            current_task_id=snapshot.task_id,
            current_task_revision=snapshot.task_revision,
            recent_turns=tuple(self._turns),
            pending_question=snapshot.pending_question,
            pending_confirmation=snapshot.pending_confirmation,
            latest_user_message=latest_user_message,
        )

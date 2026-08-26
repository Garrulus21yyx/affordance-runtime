from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterable

from .contracts import (
    REVISION_CONVERSATION_MAX_TEXT_BYTES,
    ConversationTurn,
    RevisionConversationContext,
)


class BoundedConversation:
    def __init__(self, max_turns: int = 6) -> None:
        if not 3 <= max_turns <= 6:
            raise ValueError("conversation window must contain 3..6 turns")
        self._max_turns = max_turns
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._revision_contexts: OrderedDict[str, RevisionConversationContext] = OrderedDict()

    def append(self, turn: ConversationTurn) -> None:
        existing = next(
            (item for item in self._turns if item.turn_id == turn.turn_id),
            None,
        )
        if existing is not None:
            if existing != turn:
                raise ValueError("conversation turn identity was reused")
            return
        self._turns.append(turn)
        while self._text_bytes(self._turns) > REVISION_CONVERSATION_MAX_TEXT_BYTES:
            self._turns.popleft()

    def revision_context(
        self,
        command_id: str,
        text: str,
    ) -> RevisionConversationContext:
        """Create or replay the command's exact immutable language snapshot."""

        existing = self._revision_contexts.get(command_id)
        latest = ConversationTurn(turn_id=command_id, role="user", text=text)
        if existing is not None:
            self._revision_contexts.move_to_end(command_id)
            if existing.turns[-1] == latest:
                return existing
            return RevisionConversationContext(
                turns=(*existing.turns[:-1], latest),
                latest_turn_id=command_id,
            )
        turns = [turn for turn in self._turns if turn.turn_id != command_id]
        turns.append(latest)
        while (
            len(turns) > self._max_turns
            or self._text_bytes(turns) > REVISION_CONVERSATION_MAX_TEXT_BYTES
        ):
            if len(turns) == 1:
                raise ValueError("latest revision turn exceeds conversation byte bound")
            turns.pop(0)
        context = RevisionConversationContext(
            turns=tuple(turns),
            latest_turn_id=command_id,
        )
        self._revision_contexts[command_id] = context
        while len(self._revision_contexts) > 64:
            self._revision_contexts.popitem(last=False)
        return context

    def view(self) -> RevisionConversationContext:
        if not self._turns:
            raise ValueError("conversation is empty")
        return RevisionConversationContext(
            turns=tuple(self._turns),
            latest_turn_id=self._turns[-1].turn_id,
        )

    @staticmethod
    def _text_bytes(turns: Iterable[ConversationTurn]) -> int:
        return sum(len(turn.text.encode("utf-8")) for turn in turns)


__all__ = [
    "BoundedConversation",
    "ConversationTurn",
    "RevisionConversationContext",
]

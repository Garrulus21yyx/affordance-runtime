from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import (
    REVISION_CONVERSATION_MAX_TEXT_BYTES,
    ConversationTurn,
    RevisionConversationContext,
)


@dataclass(frozen=True)
class BoundedConversationProjection:
    """Shell-only restart projection; never Runtime or command-result authority."""

    turns: tuple[ConversationTurn, ...] = ()
    revision_contexts: tuple[RevisionConversationContext, ...] = ()

    def __post_init__(self) -> None:
        turns = tuple(self.turns)
        contexts = tuple(self.revision_contexts)
        object.__setattr__(self, "turns", turns)
        object.__setattr__(self, "revision_contexts", contexts)
        if len(turns) > 6 or len(contexts) > 64:
            raise ValueError("conversation recovery projection exceeds its item bounds")
        if any(not isinstance(turn, ConversationTurn) for turn in turns):
            raise TypeError("conversation recovery turns must be typed")
        if any(not isinstance(context, RevisionConversationContext) for context in contexts):
            raise TypeError("revision recovery contexts must be typed")
        if len({turn.turn_id for turn in turns}) != len(turns):
            raise ValueError("conversation recovery turn identities must be unique")
        if len({context.latest_turn_id for context in contexts}) != len(contexts):
            raise ValueError("revision recovery command identities must be unique")
        if sum(len(turn.text.encode("utf-8")) for turn in turns) > (
            REVISION_CONVERSATION_MAX_TEXT_BYTES
        ):
            raise ValueError("conversation recovery turns exceed their byte bound")


class BoundedConversation:
    def __init__(self, max_turns: int = 6) -> None:
        if not 3 <= max_turns <= 6:
            raise ValueError("conversation window must contain 3..6 turns")
        self._max_turns = max_turns
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._revision_contexts: OrderedDict[str, RevisionConversationContext] = OrderedDict()

    @classmethod
    def from_projection(
        cls,
        projection: BoundedConversationProjection,
        *,
        max_turns: int = 6,
    ) -> BoundedConversation:
        if not isinstance(projection, BoundedConversationProjection):
            raise TypeError("bounded conversation recovery requires a typed projection")
        if len(projection.turns) > max_turns:
            raise ValueError("conversation projection exceeds the configured window")
        conversation = cls(max_turns)
        conversation._turns.extend(projection.turns)
        conversation._revision_contexts.update(
            (context.latest_turn_id, context) for context in projection.revision_contexts
        )
        return conversation

    def projection(self) -> BoundedConversationProjection:
        return BoundedConversationProjection(
            turns=tuple(self._turns),
            revision_contexts=tuple(self._revision_contexts.values()),
        )

    def clone(self) -> BoundedConversation:
        return self.from_projection(
            self.projection(),
            max_turns=self._max_turns,
        )

    def has_revision_context(self, command_id: str) -> bool:
        return command_id in self._revision_contexts

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
    "BoundedConversationProjection",
    "ConversationTurn",
    "RevisionConversationContext",
]

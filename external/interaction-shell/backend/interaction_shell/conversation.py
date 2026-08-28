from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import (
    FeedBlock,
    InteractionRequestBlock,
    REVISION_CONVERSATION_MAX_TEXT_BYTES,
    ConversationTurn,
    RevisionConversationContext,
    UserTurnBlock,
)


@dataclass(frozen=True)
class BoundedConversationProjection:
    """Shell-only restart projection; never Runtime or command-result authority."""

    turns: tuple[ConversationTurn, ...] = ()
    revision_contexts: tuple[RevisionConversationContext, ...] = ()
    feed: tuple[FeedBlock, ...] = ()
    source_event_epoch: str = ""
    source_event_cursor: int = 0

    def __post_init__(self) -> None:
        turns = tuple(self.turns)
        contexts = tuple(self.revision_contexts)
        feed = tuple(self.feed)
        object.__setattr__(self, "turns", turns)
        object.__setattr__(self, "revision_contexts", contexts)
        object.__setattr__(self, "feed", feed)
        if len(turns) > 6 or len(contexts) > 64 or len(feed) > 128:
            raise ValueError("conversation recovery projection exceeds its item bounds")
        if any(not isinstance(turn, ConversationTurn) for turn in turns):
            raise TypeError("conversation recovery turns must be typed")
        if any(not isinstance(context, RevisionConversationContext) for context in contexts):
            raise TypeError("revision recovery contexts must be typed")
        if len({turn.turn_id for turn in turns}) != len(turns):
            raise ValueError("conversation recovery turn identities must be unique")
        if len({context.latest_turn_id for context in contexts}) != len(contexts):
            raise ValueError("revision recovery command identities must be unique")
        if len({block.block_id for block in feed}) != len(feed):
            raise ValueError("presentation feed identities must be unique")
        if self.source_event_cursor < 0 or bool(self.source_event_epoch) != bool(
            self.source_event_cursor
        ):
            raise ValueError("presentation source event position is invalid")
        if sum(len(turn.text.encode("utf-8")) for turn in turns) > (
            REVISION_CONVERSATION_MAX_TEXT_BYTES
        ):
            raise ValueError("conversation recovery turns exceed their byte bound")


class BoundedConversation:
    def __init__(self, max_turns: int = 6, max_feed_blocks: int = 128) -> None:
        if not 3 <= max_turns <= 6:
            raise ValueError("conversation window must contain 3..6 turns")
        if not 16 <= max_feed_blocks <= 128:
            raise ValueError("presentation feed window must contain 16..128 blocks")
        self._max_turns = max_turns
        self._max_feed_blocks = max_feed_blocks
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._revision_contexts: OrderedDict[str, RevisionConversationContext] = OrderedDict()
        self._feed: OrderedDict[str, FeedBlock] = OrderedDict()
        self._source_event_epoch = ""
        self._source_event_cursor = 0

    @classmethod
    def from_projection(
        cls,
        projection: BoundedConversationProjection,
        *,
        max_turns: int = 6,
        max_feed_blocks: int = 128,
    ) -> BoundedConversation:
        if not isinstance(projection, BoundedConversationProjection):
            raise TypeError("bounded conversation recovery requires a typed projection")
        if len(projection.turns) > max_turns:
            raise ValueError("conversation projection exceeds the configured window")
        conversation = cls(max_turns, max_feed_blocks)
        conversation._turns.extend(projection.turns)
        conversation._revision_contexts.update(
            (context.latest_turn_id, context) for context in projection.revision_contexts
        )
        conversation._feed.update((block.block_id, block) for block in projection.feed)
        conversation._source_event_epoch = projection.source_event_epoch
        conversation._source_event_cursor = projection.source_event_cursor
        return conversation

    def projection(self) -> BoundedConversationProjection:
        return BoundedConversationProjection(
            turns=tuple(self._turns),
            revision_contexts=tuple(self._revision_contexts.values()),
            feed=tuple(self._feed.values()),
            source_event_epoch=self._source_event_epoch,
            source_event_cursor=self._source_event_cursor,
        )

    def clone(self) -> BoundedConversation:
        return self.from_projection(
            self.projection(),
            max_turns=self._max_turns,
            max_feed_blocks=self._max_feed_blocks,
        )

    @property
    def feed(self) -> tuple[FeedBlock, ...]:
        return tuple(self._feed.values())

    def event_after(self, event_epoch: str) -> int:
        return self._source_event_cursor if event_epoch == self._source_event_epoch else 0

    def ingest_feed(
        self,
        *,
        event_epoch: str,
        event_cursor: int,
        blocks: tuple[FeedBlock, ...],
    ) -> bool:
        if not event_epoch or event_cursor < 1:
            raise ValueError("feed event position is invalid")
        if event_epoch == self._source_event_epoch and event_cursor < self._source_event_cursor:
            if any(block.block_id not in self._feed for block in blocks):
                raise ValueError("stale feed event contains unseen blocks")
            return False
        changed = False
        for block in blocks:
            existing = self._feed.get(block.block_id)
            if existing is not None:
                if existing != block:
                    raise ValueError("feed block identity was reused")
                continue
            self._feed[block.block_id] = block
            self._append_language_block(block)
            changed = True
        while len(self._feed) > self._max_feed_blocks:
            self._feed.popitem(last=False)
        if event_epoch != self._source_event_epoch or event_cursor > self._source_event_cursor:
            self._source_event_epoch = event_epoch
            self._source_event_cursor = event_cursor
            changed = True
        return changed

    def _append_language_block(self, block: FeedBlock) -> None:
        if isinstance(block, UserTurnBlock):
            turn = ConversationTurn(turn_id=block.block_id, role="user", text=block.content)
        elif isinstance(block, InteractionRequestBlock):
            turn = ConversationTurn(
                turn_id=block.block_id,
                role="assistant",
                text=block.request.prompt,
            )
        else:
            return
        self.append(turn)

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

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from interaction_shell.contracts import (
    REVISION_CONVERSATION_MAX_TEXT_BYTES,
    InteractionRequest,
    InteractionRequestBlock,
    UserTurnBlock,
)
from interaction_shell.conversation import BoundedConversation, ConversationTurn


@given(st.lists(st.text(min_size=1, max_size=40), min_size=7, max_size=20))
def test_bounded_conversation_keeps_at_most_six_turns(messages) -> None:
    conversation = BoundedConversation(6)
    for index, message in enumerate(messages):
        conversation.append(
            ConversationTurn(
                turn_id=f"turn:{index}",
                role="user",
                text=message,
            )
        )

    context = conversation.revision_context("revise:latest", "还是明天")

    assert 1 <= len(context.turns) <= 6
    assert context.turns[-1].text == "还是明天"
    assert context.latest_turn_id == "revise:latest"
    assert sum(len(turn.text.encode("utf-8")) for turn in context.turns) <= (REVISION_CONVERSATION_MAX_TEXT_BYTES)


def test_revision_context_trims_oldest_turns_by_total_utf8_bytes() -> None:
    conversation = BoundedConversation(6)
    for index in range(4):
        conversation.append(
            ConversationTurn(
                turn_id=f"prior:{index}",
                role="user",
                text="a" * 5_000,
            )
        )

    context = conversation.revision_context("revise:bytes", "use the second one")

    assert tuple(turn.turn_id for turn in context.turns) == (
        "prior:1",
        "prior:2",
        "prior:3",
        "revise:bytes",
    )
    assert sum(len(turn.text.encode("utf-8")) for turn in context.turns) <= (REVISION_CONVERSATION_MAX_TEXT_BYTES)


def test_revision_context_replays_exact_snapshot_and_changes_only_latest_turn() -> None:
    conversation = BoundedConversation()
    conversation.append(
        ConversationTurn(
            turn_id="start:1",
            role="user",
            text="Book the appointment for today",
        )
    )

    original = conversation.revision_context("revise:1", "还是明天")
    replay = conversation.revision_context("revise:1", "还是明天")
    conflict_payload = conversation.revision_context("revise:1", "还是周五")

    assert replay is original
    assert conflict_payload.turns[:-1] == original.turns[:-1]
    assert conflict_payload.turns[-1].text == "还是周五"
    assert conflict_payload != original


def test_restart_projection_keeps_only_the_bounded_revision_identity_window() -> None:
    conversation = BoundedConversation()
    conversation.append(ConversationTurn(turn_id="start:1", role="user", text="Inspect both accounts"))
    contexts = [conversation.revision_context(f"revise:{index}", f"Use option {index}") for index in range(70)]

    projection = conversation.projection()
    restored = BoundedConversation.from_projection(projection)

    assert len(projection.revision_contexts) == 64
    assert tuple(context.latest_turn_id for context in projection.revision_contexts) == tuple(
        f"revise:{index}" for index in range(6, 70)
    )
    assert restored.revision_context("revise:69", "Use option 69") == contexts[-1]
    assert restored.projection() == projection


def test_feed_replay_is_idempotent_and_only_language_blocks_enter_revision_context() -> None:
    conversation = BoundedConversation()
    occurred_at = datetime.now(UTC)
    blocks = (
        UserTurnBlock(
            kind="user_turn",
            block_id="feed:epoch:1:0",
            occurred_at=occurred_at,
            content="Compare both candidates",
        ),
        InteractionRequestBlock(
            kind="interaction_request",
            block_id="feed:epoch:1:1",
            occurred_at=occurred_at,
            request=InteractionRequest(
                request_id="interaction-1",
                prompt="Which candidate should I use?",
                response_kind="free_text",
            ),
        ),
    )

    assert conversation.ingest_feed(
        event_epoch="event-epoch-0001",
        event_cursor=1,
        blocks=blocks,
    )
    assert not conversation.ingest_feed(
        event_epoch="event-epoch-0001",
        event_cursor=1,
        blocks=blocks,
    )
    context = conversation.revision_context("revise:feed", "Also inspect the next page")
    assert tuple(turn.role for turn in context.turns) == ("user", "assistant", "user")

    restored = BoundedConversation.from_projection(conversation.projection())
    assert restored.feed == blocks
    assert restored.event_after("event-epoch-0001") == 1

    conflicting = UserTurnBlock(
        kind="user_turn",
        block_id=blocks[0].block_id,
        occurred_at=occurred_at,
        content="Different content",
    )
    with pytest.raises(ValueError, match="identity was reused"):
        restored.ingest_feed(
            event_epoch="event-epoch-0001",
            event_cursor=2,
            blocks=(conflicting,),
        )

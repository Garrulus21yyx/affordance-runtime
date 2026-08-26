from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from interaction_shell.contracts import Capability, PendingQuestion, RunStatus, RuntimeSessionSnapshot
from interaction_shell.conversation import BoundedConversation, ConversationTurn
from interaction_shell.revision import TaskRevisionCompiler


def snapshot():
    from datetime import datetime, timezone

    return RuntimeSessionSnapshot(
        session_id="session",
        task_id="task",
        task_revision=3,
        run_status=RunStatus.WAITING_USER,
        event_epoch="conversation-test-epoch",
        pending_question=PendingQuestion(request_id="q-2", prompt="Which topping?"),
        capabilities=frozenset({Capability.ANSWER_QUESTION}),
        expires_at=datetime.now(timezone.utc),
    )


@given(st.lists(st.text(min_size=1, max_size=40), min_size=7, max_size=20))
def test_bounded_conversation_keeps_at_most_six_turns(messages):
    conversation = BoundedConversation(6)
    for message in messages:
        conversation.append(ConversationTurn(role="user", text=message))
    view = conversation.view(snapshot(), messages[-1])
    assert 3 <= len(view.recent_turns) <= 6
    assert view.recent_turns[-1].text == messages[-1]
    assert view.pending_question.request_id == "q-2"


class CapturingProvider:
    def __init__(self, output):
        self.output = output
        self.payload = None

    async def compile(self, payload):
        self.payload = payload
        return self.output


@pytest.mark.asyncio
async def test_revision_compiler_prioritizes_exact_pending_identity_and_closed_schema():
    provider = CapturingProvider({"kind": "revision_ready", "revised_task": "Order pizza"})
    context = BoundedConversation().view(snapshot(), "还是 pizza")
    outcome = await TaskRevisionCompiler(provider).compile("Order dinner", context, "还是 pizza")
    assert outcome.kind == "revision_ready"
    assert provider.payload["pending_question"]["request_id"] == "q-2"
    assert "selectors" not in outcome.model_dump_json()


@pytest.mark.asyncio
async def test_revision_compiler_schema_failure_is_typed():
    provider = CapturingProvider({"kind": "revision_ready", "selector": "#submit"})
    outcome = await TaskRevisionCompiler(provider).compile(
        "Order dinner", BoundedConversation().view(snapshot()), "second"
    )
    assert outcome.kind == "failed"


@pytest.mark.asyncio
async def test_revision_without_provider_is_unsupported():
    outcome = await TaskRevisionCompiler(None).compile("Order dinner", BoundedConversation().view(snapshot()), "second")
    assert outcome.kind == "unsupported"

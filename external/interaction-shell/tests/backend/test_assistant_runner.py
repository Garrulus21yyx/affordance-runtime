from __future__ import annotations

import pytest
from interaction_shell.assistant import GuiTaskResult, PydanticAssistantTurnRunner
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness.step_persistence import InMemoryStepStore, is_provider_valid


@pytest.mark.asyncio
async def test_pydantic_runner_preserves_one_complete_gui_tool_exchange():
    called_goals: list[str] = []
    runner = PydanticAssistantTurnRunner(
        TestModel(call_tools=["run_gui_task"]),
        InMemoryStepStore(),
    )

    async def run_gui_task(goal: str) -> GuiTaskResult:
        called_goals.append(goal)
        return GuiTaskResult(
            outcome="success",
            code="done",
            message="GUI complete",
        )

    result = await runner.run(
        "Use the GUI",
        conversation_id="runner-tool-pair",
        message_history=(),
        run_gui_task=run_gui_task,
    )

    assert isinstance(result.output, str)
    assert result.output
    assert called_goals
    assert is_provider_valid(list(result.messages))
    restored = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(list(result.messages))
    )
    assert len(restored) == len(result.messages)
    assert is_provider_valid(restored)


def test_persistent_memory_is_opt_in_and_requires_an_explicit_namespace(tmp_path):
    environment = {
        "INTERACTION_SHELL_ASSISTANT_PROFILE": "gemini",
        "INTERACTION_SHELL_ASSISTANT_MEMORY": "sqlite",
        "LLM_GEMINI_API_KEY": "test-key",
        "LLM_GEMINI_MODEL": "gemini-test",
    }
    with pytest.raises(ValueError, match="explicit namespace"):
        PydanticAssistantTurnRunner.from_environment(
            environment,
            database_directory=tmp_path,
            call_timeout_s=30,
        )

    environment["INTERACTION_SHELL_ASSISTANT_MEMORY_NAMESPACE"] = "user:test"
    runner = PydanticAssistantTurnRunner.from_environment(
        environment,
        database_directory=tmp_path,
        call_timeout_s=30,
    )
    assert runner.memory_store is not None
    assert runner.memory_namespace == "user:test"
    assert runner.native_web_search is True


def test_web_search_cannot_be_silently_enabled_on_an_unsupported_profile(tmp_path):
    with pytest.raises(ValueError, match="no native web-search"):
        PydanticAssistantTurnRunner.from_environment(
            {
                "INTERACTION_SHELL_ASSISTANT_PROFILE": "deepseek",
                "INTERACTION_SHELL_ASSISTANT_WEB_SEARCH": "on",
                "LLM_DEEPSEEK_API_KEY": "test-key",
                "LLM_DEEPSEEK_BASE_URL": "https://example.invalid/v1",
                "LLM_DEEPSEEK_MODEL": "deepseek-test",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            },
            database_directory=tmp_path,
            call_timeout_s=30,
        )

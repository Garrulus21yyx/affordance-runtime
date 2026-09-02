from __future__ import annotations

import pytest
from interaction_shell.assistant import (
    _ASSISTANT_INSTRUCTIONS,
    _GUI_AUTHENTICATION_CONTINGENCY,
    GuiTaskResult,
    PydanticAssistantTurnRunner,
    _complete_gui_goal,
    _public_gui_goal,
)
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel
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
    assert called_goals[0].endswith(_GUI_AUTHENTICATION_CONTINGENCY)
    assert called_goals[0].startswith("a\n\n")
    assert len(result.gui_results) == 1
    assert result.gui_results[0].outcome == "success"
    assert result.gui_results[0].message == "GUI complete"
    assert is_provider_valid(list(result.messages))
    restored = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(list(result.messages))
    )
    assert len(restored) == len(result.messages)
    assert is_provider_valid(restored)


@pytest.mark.asyncio
async def test_pydantic_runner_executes_at_most_one_gui_delegation_per_user_turn():
    called_goals: list[str] = []

    def call_gui_twice(messages, _info):
        response_count = sum(isinstance(message, ModelResponse) for message in messages)
        if response_count < 2:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "run_gui_task",
                        {"goal": f"complete GUI task attempt {response_count + 1}"},
                        tool_call_id=f"gui-call-{response_count + 1}",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("The GUI task needs user input.")])

    runner = PydanticAssistantTurnRunner(
        FunctionModel(call_gui_twice),
        InMemoryStepStore(),
    )

    async def run_gui_task(goal: str) -> GuiTaskResult:
        called_goals.append(goal)
        return GuiTaskResult(
            outcome="blocked",
            code="needs_user",
            message="The prepared interface needs user input.",
        )

    result = await runner.run(
        "Use the GUI",
        conversation_id="runner-single-gui-delegation",
        message_history=(),
        run_gui_task=run_gui_task,
    )

    assert len(called_goals) == 1
    assert result.gui_results == (
        GuiTaskResult(
            outcome="blocked",
            code="needs_user",
            message="The prepared interface needs user input.",
        ),
    )
    assert is_provider_valid(list(result.messages))


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


def test_assistant_delegates_the_authentication_contingency_with_the_complete_gui_goal():
    assert "prepare the safest visible out-of-band challenge" in _ASSISTANT_INSTRUCTIONS
    assert "resume\n  the original goal after control is returned" in _ASSISTANT_INSTRUCTIONS
    assert "Never ask the GUI Runtime to collect credentials" in _ASSISTANT_INSTRUCTIONS
    assert _complete_gui_goal("Original goal") == (
        f"Original goal\n\n{_GUI_AUTHENTICATION_CONTINGENCY}"
    )


def test_runtime_authentication_contingency_is_not_part_of_the_public_goal():
    runtime_goal = _complete_gui_goal("在网页中完成用户要求的操作")

    assert _public_gui_goal(runtime_goal) == "在网页中完成用户要求的操作"
    assert _public_gui_goal("保留普通目标") == "保留普通目标"

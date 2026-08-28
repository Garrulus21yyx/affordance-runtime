"""PydanticAI-owned outer conversation for the capability-agnostic Shell."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class AssistantQuestion(BaseModel):
    """A material user fact is required before any safe useful action can continue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=2000)


class GuiTaskResult(BaseModel):
    """Bounded public result returned by the existing GUI Runtime capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["success", "failure", "blocked", "cancelled"]
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(max_length=16_000)
    artifact_summary: str = Field(default="", max_length=2000)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)


AssistantOutput = str | AssistantQuestion
GuiTaskCallable = Callable[[str], Awaitable[GuiTaskResult]]


@dataclass(frozen=True)
class AssistantTurnResult:
    output: AssistantOutput
    messages: tuple[Any, ...]
    gui_results: tuple[GuiTaskResult, ...] = ()


class AssistantTurnRunner(Protocol):
    async def run(
        self,
        prompt: str,
        *,
        conversation_id: str,
        message_history: Sequence[Any],
        run_gui_task: GuiTaskCallable,
    ) -> AssistantTurnResult: ...


@runtime_checkable
class AssistantHistoryPersistence(Protocol):
    async def latest_checkpoint(self, conversation_id: str) -> str | None: ...

    async def load_checkpoint(
        self,
        conversation_id: str,
        checkpoint_id: str,
    ) -> tuple[Any, ...]: ...


_ASSISTANT_INSTRUCTIONS = """
You are the user-facing Affordance assistant. Hold a natural conversation and return a concise,
well-written answer in the user's language.

Choose capabilities by their public meaning:
- Answer directly when the request can be answered reliably from the conversation and stable knowledge.
- Use native web search when it is available and current or source-specific information is required.
- Call run_gui_task only when the request requires interacting with a graphical user interface or inspecting
  state that the delegated GUI Runtime must acquire. Give it the complete user goal and constraints, not a URL
  unless the user supplied that URL or the URL itself is essential to the goal.
- Delegate at most one complete GUI task per user turn. A returned success, failure, blocked, or cancelled result is
  authoritative for that turn; explain it instead of calling run_gui_task again.
- Return AssistantQuestion only when a fact owned by the user would materially change the result and cannot be
  obtained through an available capability. Do not ask the user to choose internal tools or provide routine URLs.

run_gui_task is an isolated delegate. Its result is authoritative for GUI completion and external effects. Do not
invent clicks, page state, evidence, success, or failure. Explain its typed result naturally. Never expose internal
World, grounding IDs, selectors, tool transcripts, provider messages, or benchmark machinery.

If the user corrects or narrows an earlier request, the newest user instruction is authoritative. Do not continue a
withdrawn request. Persistent memory, when present, is only for preferences the user explicitly asked to remember;
never store task progress, browser state, credentials, inferred traits, or unverified claims.
""".strip()

_MEMORY_GUIDANCE = """
Memory is optional user-controlled preference storage. Write only a stable preference that the user explicitly asks
you to remember. Never write task progress, browser or GUI state, credentials, identifiers, inferred personal facts,
model hypotheses, or one-off instructions. If the user did not explicitly ask to remember something, do not write.
""".strip()


@dataclass(frozen=True)
class PydanticAssistantTurnRunner:
    """Thin composition over PydanticAI and Harness; no routing state lives here."""

    model: Any
    step_store: Any
    native_web_search: bool = False
    memory_store: Any | None = None
    memory_namespace: str = ""
    max_requests: int = 12

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        database_directory: Path,
        call_timeout_s: float,
    ) -> PydanticAssistantTurnRunner:
        from pydantic_ai_harness.step_persistence import SqliteStepStore

        profile = (
            environment.get("INTERACTION_SHELL_ASSISTANT_PROFILE", "").strip().casefold()
            or environment.get("LLM_ACTIVE_PROFILE", "").strip().casefold()
        )
        if not profile:
            raise ValueError("an Assistant model profile is required")

        memory_namespace = environment.get(
            "INTERACTION_SHELL_ASSISTANT_MEMORY_NAMESPACE", ""
        ).strip()
        memory_setting = environment.get(
            "INTERACTION_SHELL_ASSISTANT_MEMORY", "off"
        ).strip().casefold()
        if memory_setting not in {"off", "sqlite"}:
            raise ValueError("INTERACTION_SHELL_ASSISTANT_MEMORY must be off or sqlite")
        if memory_setting == "sqlite" and not memory_namespace:
            raise ValueError("persistent Assistant memory requires an explicit namespace")

        native_web_search = False
        if profile == "gemini":
            import httpx

            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            api_key = _required(environment, "LLM_GEMINI_API_KEY")
            model_id = _required(environment, "LLM_GEMINI_MODEL")
            model: Any = GoogleModel(
                model_id,
                provider=GoogleProvider(
                    api_key=api_key,
                    http_client=httpx.AsyncClient(),
                ),
            )
            native_web_search = True
        else:
            from affordance_runtime.model.policy.pydantic_ai_bridge import (
                pydantic_ai_model_from_environment,
            )

            assistant_environment = dict(environment)
            assistant_environment["LLM_ACTIVE_PROFILE"] = profile
            model = pydantic_ai_model_from_environment(
                assistant_environment,
                call_timeout_s=call_timeout_s,
            ).model

        search_setting = environment.get(
            "INTERACTION_SHELL_ASSISTANT_WEB_SEARCH", "auto"
        ).strip().casefold()
        if search_setting not in {"auto", "on", "off"}:
            raise ValueError("INTERACTION_SHELL_ASSISTANT_WEB_SEARCH must be auto, on, or off")
        if search_setting == "on" and not native_web_search:
            raise ValueError("the configured Assistant profile has no native web-search capability")
        native_web_search = native_web_search and search_setting != "off"

        database_directory.mkdir(parents=True, exist_ok=True)
        step_store = SqliteStepStore(
            database=database_directory / "assistant-steps.sqlite3",
            max_snapshots_per_run=2,
        )

        memory_store: object | None = None
        if memory_setting == "sqlite":
            from pydantic_ai_harness.memory import SqliteMemoryStore

            memory_store = SqliteMemoryStore(
                database=database_directory / "assistant-memory.sqlite3"
            )

        return cls(
            model=model,
            step_store=step_store,
            native_web_search=native_web_search,
            memory_store=memory_store,
            memory_namespace=memory_namespace,
        )

    async def run(
        self,
        prompt: str,
        *,
        conversation_id: str,
        message_history: Sequence[Any],
        run_gui_task: GuiTaskCallable,
    ) -> AssistantTurnResult:
        from pydantic_ai import Agent, ModelRetry, Tool, WebSearchTool
        from pydantic_ai.capabilities import NativeTool
        from pydantic_ai.usage import UsageLimits
        from pydantic_ai_harness.compaction import SummarizingCompaction
        from pydantic_ai_harness.step_persistence import StepPersistence

        gui_results: list[GuiTaskResult] = []

        async def execute_gui_task(goal: str) -> GuiTaskResult:
            """Run one bounded GUI task in the existing Runtime and return its public result."""

            if gui_results:
                return gui_results[-1]
            gui_result = await run_gui_task(goal)
            gui_results.append(gui_result)
            return gui_result

        capabilities: list[Any] = [
            StepPersistence(store=self.step_store, agent_name="interaction_shell_assistant"),
            SummarizingCompaction(
                model=self.model,
                max_messages=80,
                keep_messages=24,
                preserve_first_user_message=True,
                incremental=True,
                receipts=False,
            ),
        ]
        if self.native_web_search:
            capabilities.append(
                NativeTool(WebSearchTool(search_context_size="medium", max_uses=4))
            )
        if self.memory_store is not None:
            from pydantic_ai_harness.memory import Memory

            capabilities.append(
                Memory(
                    store=self.memory_store,
                    agent_name="assistant",
                    namespace=self.memory_namespace,
                    max_tokens=800,
                    max_lines=80,
                    guidance=_MEMORY_GUIDANCE,
                    injection_errors="raise",
                    heading="Explicit user preferences",
                )
            )

        agent = Agent(
            self.model,
            name="interaction_shell_assistant",
            instructions=_ASSISTANT_INSTRUCTIONS,
            output_type=[str, AssistantQuestion],
            tools=[
                Tool(
                    execute_gui_task,
                    name="run_gui_task",
                    description=(
                        "Delegate a complete graphical user-interface task to the existing GUI "
                        "Runtime. Use only when UI interaction or GUI-only state acquisition is required."
                    ),
                    sequential=True,
                )
            ],
            capabilities=capabilities,
            retries={"tools": 1, "output": 1},
        )

        @agent.output_validator
        def validate_public_answer(output: str | AssistantQuestion):
            if isinstance(output, str) and (not output.strip() or len(output) > 16_000):
                raise ModelRetry("Return one non-empty user-facing answer of at most 16000 characters.")
            return output

        result = await agent.run(
            prompt,
            conversation_id=conversation_id,
            message_history=message_history,
            usage_limits=UsageLimits(
                request_limit=self.max_requests,
                tool_calls_limit=8,
            ),
        )
        output = result.output
        if not isinstance(output, str | AssistantQuestion):
            raise TypeError("Assistant output algebra is not exhaustive")
        return AssistantTurnResult(
            output=output,
            messages=tuple(result.all_messages()),
            gui_results=tuple(gui_results),
        )

    async def latest_checkpoint(self, conversation_id: str) -> str | None:
        runs = await self.step_store.list_runs(conversation_id=conversation_id)
        for run in sorted(runs, key=lambda item: item.started_at, reverse=True):
            if await self.step_store.latest_snapshot(run_id=run.run_id) is not None:
                return run.run_id
        return None

    async def load_checkpoint(
        self,
        conversation_id: str,
        checkpoint_id: str,
    ) -> tuple[Any, ...]:
        from pydantic_ai_harness.step_persistence import continue_run

        run = await self.step_store.get_run(run_id=checkpoint_id)
        if run is None or run.conversation_id != conversation_id:
            raise LookupError("Assistant conversation checkpoint is unavailable")
        return tuple(await continue_run(self.step_store, run_id=checkpoint_id))


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


__all__ = [
    "AssistantQuestion",
    "AssistantHistoryPersistence",
    "AssistantTurnResult",
    "AssistantTurnRunner",
    "GuiTaskResult",
    "PydanticAssistantTurnRunner",
]

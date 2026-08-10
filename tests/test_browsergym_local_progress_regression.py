import asyncio
import json
import os
import re
from dataclasses import dataclass, field

import pytest

from affordance_runtime.agent import (
    AgentEpisodeRunner,
    AgentFailureCode,
    AgentLoop,
    AgentLoopStatus,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_action_evaluator import (
    BrowserGymMechanicalActionEvaluator,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_environment import (
    BrowserGymMiniWobEnvironment,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalEnvironmentTaskEvaluator
from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.model_policy import (
    ModelBackedAgentPolicy,
    ModelDecisionResponse,
    ModelMetadata,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIWOB_URL"),
    reason="fixed MiniWoB source is unavailable",
)


@dataclass
class LocalPublicStructuredPort:
    repeat_fill: bool = False
    calls: int = 0
    progress_views: list[dict[str, object]] = field(default_factory=list)

    async def generate(self, request):
        self.calls += 1
        context = json.loads(request.serialized_context)
        self.progress_views.append(context["progress"])
        payload = self._decision(context)
        return ModelDecisionResponse(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ModelMetadata(
                provider_id="local-conformance",
                model_id="scripted-structured",
                response_id=f"response:{self.calls}",
                endpoint_class="in-process",
                prompt_version="browsergym-local-progress.v1",
                schema_version=request.schema_version,
            ),
        )

    def _decision(self, context):
        instruction = str(context["task"]["instruction"])
        actions = context["actions"]["options"]
        targets = {item["target_id"]: item for item in context["world"]["targets"]["items"]}
        if instruction.casefold().startswith("enter "):
            desired = _quoted(instruction)[0]
            fill = _first(actions, "fill")
            current = targets[fill["target_id"]]["state"].get("value")
            if self.repeat_fill or current != desired:
                return _selection(context, fill, {"value": desired})
            return _selection(context, _labelled(actions, targets, "activate", "submit"), {})
        if instruction.casefold().startswith("select "):
            desired = re.search(r"select\s+(.+?)\s+from", instruction, re.IGNORECASE).group(1).strip()
            select = _first(actions, "select")
            current = targets[select["target_id"]]["state"].get("value")
            if current != desired:
                return _selection(context, select, {"value": desired})
            return _selection(context, _labelled(actions, targets, "activate", "submit"), {})
        label = _quoted(instruction)[0]
        return _selection(context, _labelled(actions, targets, "activate", label), {})


def _selection(context, option, parameters):
    return {
        "type": "select_action",
        "context_id": context["context_id"],
        "action_id": option["action_id"],
        "parameters": parameters,
        "destination_id": "",
    }


def _first(actions, semantic_action):
    return next(item for item in actions if item["semantic_action"] == semantic_action)


def _labelled(actions, targets, semantic_action, label):
    return next(
        item
        for item in actions
        if item["semantic_action"] == semantic_action
        and targets[item["target_id"]]["label"].casefold() == label.casefold()
    )


def _quoted(instruction: str) -> tuple[str, ...]:
    return tuple(re.findall(r'"([^"\\]*)"', instruction))


async def _run(task_id: str, port: LocalPublicStructuredPort):
    environment, task = BrowserGymMiniWobEnvironment.open(task_id, 7, max_turns=6)
    loop = AgentLoop(
        ModelBackedAgentPolicy(port, call_timeout_s=10),
        BrowserGymMechanicalActionEvaluator(),
        ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
    )
    try:
        result = await AgentEpisodeRunner(loop).run(environment, task)
        counts = (environment.step_calls, environment.fill_calls, environment.select_calls)
        return result, counts
    finally:
        await environment.close()


def test_real_enter_text_progress_aware_path_converges_without_repeat() -> None:
    port = LocalPublicStructuredPort()
    result, counts = asyncio.run(_run("browsergym/miniwob.enter-text", port))

    assert result.status is AgentLoopStatus.DONE
    assert counts == (2, 1, 0)
    assert port.calls == 2
    assert result.execution_count == 2
    assert result.turns[0].action_evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
    events = port.progress_views[1]["events"]["items"]
    assert events[-1]["effect_status"] == "effect_confirmed"


def test_real_enter_text_repeat_fill_is_zero_call_bounded_failure() -> None:
    port = LocalPublicStructuredPort(repeat_fill=True)
    result, counts = asyncio.run(_run("browsergym/miniwob.enter-text", port))

    assert result.status is AgentLoopStatus.FAILED
    assert result.failure_code is AgentFailureCode.NO_PROGRESS_REPETITION
    assert counts == (1, 1, 0)
    assert result.execution_count == 1
    assert port.calls == 3
    assert result.currentness_probe_count == 1


def test_real_choose_list_select_effect_is_confirmed_and_completes() -> None:
    port = LocalPublicStructuredPort()
    result, counts = asyncio.run(_run("browsergym/miniwob.choose-list", port))

    assert result.status is AgentLoopStatus.DONE
    assert counts == (2, 0, 1)
    assert result.turns[0].action_evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED


def test_real_click_button_activate_remains_executable_and_completes() -> None:
    port = LocalPublicStructuredPort()
    result, counts = asyncio.run(_run("browsergym/miniwob.click-button", port))

    assert result.status is AgentLoopStatus.DONE
    assert counts == (1, 0, 0)
    assert result.execution_count == 1

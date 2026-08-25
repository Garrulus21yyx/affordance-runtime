from __future__ import annotations

import asyncio
import uuid

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.surfaces.browsergym.environment import BrowserGymSurfaceAdapter
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BrowserGymTaskStateSource,
    task_state_from_transition,
)
from affordance_runtime.surfaces.browsergym.transition import (
    BrowserGymStabilityStatus,
    BrowserGymStepTransition,
    BrowserGymTransitionTrace,
)
from affordance_runtime.task import (
    LoopBudget,
    NaturalLanguageTaskRequest,
    ReadyTask,
    RiskProfile,
    TaskBoundary,
    ThinTaskIntake,
)


def ax_node(
    bid: str,
    role: str,
    label: str,
    *,
    value: str = "",
    properties=(),
    parent_id: str = "",
    child_ids=(),
):
    node = {
        "nodeId": bid,
        "ignored": False,
        "role": {"value": role},
        "name": {"value": label},
        "browsergym_id": bid,
        "properties": [{"name": key, "value": {"value": item}} for key, item in properties],
    }
    if parent_id:
        node["parentId"] = parent_id
    if child_ids:
        node["childIds"] = list(child_ids)
    if value:
        node["value"] = {"value": value}
    return node


def dom_snapshot(*elements: tuple[str, str, dict[str, str]]) -> dict[str, object]:
    """Build BrowserGym's CDP DOMSnapshot shape for adapter contract tests."""

    strings: list[str] = []

    def intern(value: str) -> int:
        try:
            return strings.index(value)
        except ValueError:
            strings.append(value)
            return len(strings) - 1

    node_names: list[int] = []
    attributes: list[list[int]] = []
    for tag, bid, values in elements:
        node_names.append(intern(tag.upper()))
        encoded: list[int] = []
        for name, value in (("bid", bid), *values.items()):
            encoded.extend((intern(name), intern(value)))
        attributes.append(encoded)
    return {
        "strings": strings,
        "documents": [{"nodes": {"nodeName": node_names, "attributes": attributes}}],
    }


def raw_observation(*nodes, goal='Click the "okay" button.', url="file:///fixed/task.html"):
    copied = [dict(node) for node in nodes]
    select_indexes = [index for index, node in enumerate(copied) if node["role"]["value"] in {"combobox", "listbox"}]
    for index in select_indexes:
        owner = copied[index]
        options = []
        for option in copied[index + 1 :]:
            if option["role"]["value"] != "option":
                break
            option["parentId"] = owner["nodeId"]
            options.append(option["nodeId"])
        owner["childIds"] = options
    physical = {}
    for node in copied:
        role = node["role"]["value"]
        if role == "option":
            continue
        owned = [
            option
            for option in copied
            if option.get("parentId") == node["nodeId"] and option["role"]["value"] == "option"
        ]
        physical[str(node["browsergym_id"])] = {
            "attached": True,
            "visible": True,
            "enabled": True,
            "readonly": False,
            "editable": role in {"textbox", "searchbox", "combobox", "listbox"},
            "focusable": role in {
                "button", "checkbox", "combobox", "link", "listbox", "menuitem",
                "radio", "searchbox", "tab", "textbox",
            },
            "focused": False,
            "options": [{"label": option["name"]["value"], "value": option["name"]["value"]} for option in owned],
        }
    return {
        "goal": goal,
        "url": url,
        "axtree_object": {"nodes": copied},
        "extra_element_properties": {str(node["browsergym_id"]): {"visibility": 1.0} for node in copied},
        PRIVATE_CONTROL_PROPERTIES_KEY: physical,
    }


class FakeBrowserGym:
    def __init__(
        self,
        initial,
        post=None,
        *,
        fail_step=False,
        fail_probe=False,
        fail_final=False,
    ):
        self.initial = initial
        self.post = post or initial
        self.fail_step = fail_step
        self.fail_probe = fail_probe
        self.fail_final = fail_final
        self.actions = []
        self.navigation_expectations = []
        self.final_messages = []
        self.reset_count = 0
        self.close_count = 0
        self.browser = object()
        self.context = object()
        self.probes = {}
        self.unwrapped = self
        self.supports_capture_current = True
        self.capture_count = 0
        self.currentness_probe_count = 0
        self.probe_task = {
            "ready": True,
            "done": False,
            "raw_reward": 0,
            "episode": "0",
        }
        self.probe_override = None
        self.step_reward = 1.0
        self.step_raw_reward = 1
        self.step_terminated = True
        self.step_truncated = False
        self.step_done = True
        self.step_stability_status = BrowserGymStabilityStatus.STABLE_NO_NAVIGATION

    def reset(self, *, seed):
        assert isinstance(seed, int)
        self.reset_count += 1
        return self.initial, {"task_info": task_info()}

    def step(self, action, *, may_navigate):
        self.actions.append(action)
        self.navigation_expectations.append(may_navigate)
        if self.fail_step:
            raise RuntimeError("after dispatch")
        stable = self.step_stability_status in {
            BrowserGymStabilityStatus.STABLE_NO_NAVIGATION,
            BrowserGymStabilityStatus.STABLE_NAVIGATION,
        }
        navigated = self.step_stability_status is BrowserGymStabilityStatus.STABLE_NAVIGATION
        return BrowserGymStepTransition(
            self.post if stable else None,
            self.step_reward,
            self.step_terminated,
            self.step_truncated,
            {
                "task_info": task_info(
                    reward=self.step_raw_reward,
                    done=self.step_done,
                )
            },
            BrowserGymTransitionTrace(
                0.0,
                1.0,
                0.2 if navigated or self.step_stability_status is BrowserGymStabilityStatus.NAVIGATION_PENDING else None,
                0.4 if navigated else None,
                1.1 if stable else None,
                1.2 if stable else None,
                str(self.initial.get("url", "")),
                str(self.post.get("url", "")),
                1,
                2 if navigated else 1,
                self.step_stability_status,
            ),
        )

    def send_msg_to_user(self, content):
        self.final_messages.append(content)
        if self.fail_final:
            raise RuntimeError("final after dispatch")
        return (
            self.post,
            self.step_reward,
            self.step_terminated,
            self.step_truncated,
            {
                "task_info": task_info(
                    reward=self.step_raw_reward,
                    done=self.step_done,
                )
            },
        )

    def currentness_probe(self, bid):
        del bid
        self.currentness_probe_count += 1
        if self.fail_probe:
            raise RuntimeError("probe unavailable")
        if self.probe_override is not None:
            return self.probe_override
        return {
            "raw": self.post,
            "task": {**self.probe_task, "url": self.post["url"]},
            "latency_ms": 0.1,
        }

    def capture_current(self):
        self.capture_count += 1
        return self.post, {**self.probe_task, "url": self.post["url"]}

    def close(self):
        self.close_count += 1
        self.browser = None
        self.context = None


def task_info(*, reward=0, done=False):
    return {
        "RAW_REWARD_GLOBAL": reward,
        "DONE_GLOBAL": done,
        "EPISODE_ID": 0,
        "TASK_READY": True,
    }


def reset_task_state(observation_id: str, *, task_run_id: str = "run:opaque"):
    return task_state_from_transition(
        task_run_id=task_run_id,
        observation_id=observation_id,
        source_observation_id=observation_id,
        source=BrowserGymTaskStateSource.RESET,
        reward=0.0,
        terminated=False,
        truncated=False,
        task_info=task_info(),
    )


def open_fake(
    fake: FakeBrowserGym,
    task_id="browsergym/miniwob.click-button",
    *,
    browser_action_primitives: tuple[str, ...] = (),
    browser_navigation_urls: tuple[str, ...] | None = None,
):
    return open_surface(
        task_id,
        7,
        gym_factory=lambda *_args, **_kwargs: fake,
        browser_action_primitives=browser_action_primitives,
        browser_navigation_urls=browser_navigation_urls,
    )


class BrowserGymTestEnvironment:
    """Test facade that keeps BrowserGym behind the product coordinator."""

    def __init__(self, surface):
        from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

        self.surface = surface
        self.world = UnifiedWorldEnvironment((surface,))

    def __getattr__(self, name):
        return getattr(self.surface, name)

    @property
    def observation_capabilities(self):
        return self.world.observation_capabilities

    async def reset(self, task):
        return await self.world.reset(task)

    async def revise_task(self, task):
        return await self.world.revise_task(task)

    async def capture(self, request):
        return await self.world.capture(request)

    async def execute(self, request):
        return await self.world.execute(request)

    @property
    def supports_finalization(self):
        return self.world.supports_finalization

    async def finalize(self, content):
        return await self.world.finalize(content)

    def is_current(self, request):
        return self.world.is_current(request)

    async def close(self):
        return await self.surface.close()


def open_surface(task_id: str, seed: int, *, max_turns: int = 20, **kwargs):
    surface = BrowserGymSurfaceAdapter.open(task_id, seed, **kwargs)
    environment = BrowserGymTestEnvironment(surface)
    intake = ThinTaskIntake().compile(
        NaturalLanguageTaskRequest(
            f"task:{uuid.uuid4().hex}",
            environment.goal_instruction,
            TaskBoundary(
                allowed_effects=("external_ui_interaction",),
                forbidden_effects=("external_network_side_effect", "credential_use"),
                risk_profile=RiskProfile.LOW,
                loop_budget=LoopBudget(max_turns=max_turns, max_observations=max_turns * 2),
            ),
            source_ref=f"browsergym:{task_id}:goal",
        )
    )
    assert isinstance(intake, ReadyTask)
    return environment, intake.task


def request_for(world, task, semantic_action, parameters=None, destination_id=""):
    space = ActionSpaceBuilder().build(task, world)
    option = next(item for item in space.options if item.semantic_action == semantic_action)
    selection = ActionSpaceBuilder().admit(option, parameters or {}, destination_id)
    return ActionBinder().bind(selection, world, "context:test")


def start_environment(environment, task):
    acquisition = asyncio.run(environment.reset(task))
    assert acquisition.observation is not None
    return acquisition.observation

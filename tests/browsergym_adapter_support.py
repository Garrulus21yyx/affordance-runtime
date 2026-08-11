from __future__ import annotations

import asyncio

from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder


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


def raw_observation(*nodes, goal='Click the "okay" button.', url="file:///fixed/task.html"):
    copied = [dict(node) for node in nodes]
    select_indexes = [
        index for index, node in enumerate(copied)
        if node["role"]["value"] in {"combobox", "listbox"}
    ]
    for index in select_indexes:
        owner = copied[index]
        options = []
        for option in copied[index + 1:]:
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
            option for option in copied
            if option.get("parentId") == node["nodeId"] and option["role"]["value"] == "option"
        ]
        physical[str(node["browsergym_id"])] = {
            "attached": True,
            "visible": True,
            "enabled": True,
            "readonly": False,
            "editable": role in {"textbox", "searchbox", "combobox", "listbox"},
            "options": [
                {"label": option["name"]["value"], "value": option["name"]["value"]}
                for option in owned
            ],
        }
    return {
        "goal": goal,
        "url": url,
        "axtree_object": {"nodes": copied},
        "extra_element_properties": {
            str(node["browsergym_id"]): {"visibility": 1.0} for node in copied
        },
        PRIVATE_CONTROL_PROPERTIES_KEY: physical,
    }


class FakeBrowserGym:
    def __init__(self, initial, post=None, *, fail_step=False, fail_probe=False):
        self.initial = initial
        self.post = post or initial
        self.fail_step = fail_step
        self.fail_probe = fail_probe
        self.actions = []
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
            "episode": "0",
        }
        self.probe_override = None

    def reset(self, *, seed):
        assert isinstance(seed, int)
        self.reset_count += 1
        return self.initial, {"task_info": task_info()}

    def step(self, action):
        self.actions.append(action)
        if self.fail_step:
            raise RuntimeError("after dispatch")
        return self.post, 1.0, True, False, {"task_info": task_info(reward=1, done=True)}

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
        return self.post, {
            "ready": True,
            "done": False,
            "episode": "0",
            "url": self.post["url"],
        }

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


def open_fake(fake: FakeBrowserGym, task_id="browsergym/miniwob.click-button"):
    return __import__(
        "affordance_runtime.benchmarks.external_smoke.browsergym_environment",
        fromlist=["BrowserGymMiniWobEnvironment"],
    ).BrowserGymMiniWobEnvironment.open(task_id, 7, gym_factory=lambda *_args, **_kwargs: fake)


def request_for(world, task, semantic_action, parameters=None):
    space = ActionSpaceBuilder().build(task, world)
    option = next(item for item in space.options if item.semantic_action == semantic_action)
    selection = ActionSpaceBuilder().admit(option, parameters or {})
    return ActionBinder().bind(selection, world, "context:test")


def start_environment(environment, task):
    acquisition = asyncio.run(environment.reset(task))
    assert acquisition.observation is not None
    return acquisition.observation

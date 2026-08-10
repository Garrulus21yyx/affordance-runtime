from __future__ import annotations

import asyncio

from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder


def ax_node(bid: str, role: str, label: str, *, value: str = "", properties=()):
    node = {
        "nodeId": bid,
        "ignored": False,
        "role": {"value": role},
        "name": {"value": label},
        "browsergym_id": bid,
        "properties": [{"name": key, "value": {"value": item}} for key, item in properties],
    }
    if value:
        node["value"] = {"value": value}
    return node


def raw_observation(*nodes, goal='Click the "okay" button.', url="file:///fixed/task.html"):
    return {
        "goal": goal,
        "url": url,
        "axtree_object": {"nodes": list(nodes)},
        "extra_element_properties": {
            str(node["browsergym_id"]): {"visibility": 1.0} for node in nodes
        },
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

    def reset(self, *, seed):
        assert isinstance(seed, int)
        self.reset_count += 1
        return self.initial, {"task_info": task_info()}

    def step(self, action):
        self.actions.append(action)
        if self.fail_step:
            raise RuntimeError("after dispatch")
        return self.post, 1.0, True, False, {"task_info": task_info(reward=1, done=True)}

    def probe_element(self, bid):
        if self.fail_probe:
            raise RuntimeError("probe unavailable")
        return self.probes[bid]

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

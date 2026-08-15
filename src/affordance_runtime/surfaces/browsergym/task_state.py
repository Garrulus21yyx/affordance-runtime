"""Raw BrowserGym task-state lineage without benchmark success interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from affordance_runtime.world.evidence_refs import canonical_artifact_ref

BROWSERGYM_TASK_STATE_EVIDENCE_KEY = "browsergym-task-state"


class BrowserGymTaskStateSource(StrEnum):
    RESET = "reset"
    POST_ACTION = "post_action"
    READ_ONLY_PROBE = "read_only_probe"


@dataclass(frozen=True)
class BrowserGymTaskStateSnapshot:
    """One immutable capture of provider-native task facts and their lineage."""

    task_run_id: str
    observation_id: str
    source_observation_id: str
    source: BrowserGymTaskStateSource
    values: Mapping[str, object]
    present_fields: frozenset[str]

    def __post_init__(self) -> None:
        if not all((
            self.task_run_id.strip(),
            self.observation_id.strip(),
            self.source_observation_id.strip(),
        )):
            raise ValueError("BrowserGym task-state snapshot requires complete lineage")
        if not isinstance(self.source, BrowserGymTaskStateSource):
            raise TypeError("BrowserGym task-state source must be typed")
        if not self.present_fields.issubset(self.values):
            raise ValueError("BrowserGym task-state presence must match captured values")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "present_fields", frozenset(self.present_fields))

    @property
    def evidence_ref(self) -> str:
        return canonical_artifact_ref(
            self.source_observation_id,
            BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
        )

    @property
    def terminal_hint(self) -> bool:
        return any(
            self.values.get(field) is True
            for field in ("terminated", "truncated", "done")
            if field in self.present_fields
        )

    def value(self, field: str, missing: object) -> object:
        return self.values[field] if field in self.present_fields else missing


def task_state_from_transition(
    *,
    task_run_id: str,
    observation_id: str,
    source_observation_id: str,
    source: BrowserGymTaskStateSource,
    reward: object,
    terminated: object,
    truncated: object,
    task_info: object,
) -> BrowserGymTaskStateSnapshot:
    if source not in {
        BrowserGymTaskStateSource.RESET,
        BrowserGymTaskStateSource.POST_ACTION,
    }:
        raise ValueError("transition task state requires reset or post-action source")
    info = task_info if type(task_info) is dict else {}
    values = {
        "reward": reward,
        "raw_reward": info.get("RAW_REWARD_GLOBAL"),
        "terminated": terminated,
        "truncated": truncated,
        "done": info.get("DONE_GLOBAL"),
        "ready": info.get("TASK_READY"),
    }
    present = {"reward", "terminated", "truncated"}
    present.update(
        public
        for private, public in (
            ("RAW_REWARD_GLOBAL", "raw_reward"),
            ("DONE_GLOBAL", "done"),
            ("TASK_READY", "ready"),
        )
        if private in info
    )
    return BrowserGymTaskStateSnapshot(
        task_run_id,
        observation_id,
        source_observation_id,
        source,
        values,
        frozenset(present),
    )


def task_state_from_probe(
    *,
    task_run_id: str,
    observation_id: str,
    source_observation_id: str,
    probe: object,
) -> BrowserGymTaskStateSnapshot:
    values = probe if type(probe) is dict else {}
    normalized = {
        "raw_reward": values.get("raw_reward"),
        "done": values.get("done"),
        "ready": values.get("ready"),
    }
    return BrowserGymTaskStateSnapshot(
        task_run_id,
        observation_id,
        source_observation_id,
        BrowserGymTaskStateSource.READ_ONLY_PROBE,
        normalized,
        frozenset(field for field in normalized if field in values),
    )

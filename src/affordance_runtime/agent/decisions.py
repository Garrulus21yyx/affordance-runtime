"""The complete set of policy-visible loop proposals."""

from dataclasses import dataclass, field
from typing import Any, TypeAlias

from affordance_runtime.immutable import freeze_json


@dataclass(frozen=True)
class SelectAction:
    action_id: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_id.strip():
            raise ValueError("selection requires an offered action id")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


@dataclass(frozen=True)
class AskUser:
    question: str


@dataclass(frozen=True)
class Reobserve:
    reason: str


@dataclass(frozen=True)
class Finish:
    result: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", freeze_json(self.result))


@dataclass(frozen=True)
class Stop:
    reason: str


AgentDecision: TypeAlias = SelectAction | AskUser | Reobserve | Finish | Stop

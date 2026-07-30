"""Compatibility progress state for accepted TaskSkill runtime execution.

TaskSkill progress is intentionally owned by ``AcceptedTaskSkillRuntime`` during
the SAR-7 compatibility window. It is not part of ``StateKernel`` progress
authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskSkillRunState:
    """Verified progress for one accepted TaskSkill activation."""

    skill_id: str
    version: str
    bindings: dict[str, Any] = field(default_factory=dict)
    next_step_index: int = 0
    completed_step_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    active_step_id: str = ""
    fallthrough_reason: str = ""

    @property
    def active(self) -> bool:
        return not self.fallthrough_reason


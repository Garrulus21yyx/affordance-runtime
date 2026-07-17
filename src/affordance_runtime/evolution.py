"""Harness evolution registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EvolutionStatus(StrEnum):
    PROPOSED = "proposed"
    QUARANTINED = "quarantined"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class EvolutionArtifact:
    id: str
    artifact_type: str
    summary: str
    applicability: dict[str, Any]
    source_traces: list[str]
    negative_examples: list[str] = field(default_factory=list)
    ttl_runs: int = 100
    status: EvolutionStatus = EvolutionStatus.PROPOSED
    regression_results: dict[str, float] = field(default_factory=dict)


@dataclass
class EvolutionRegistry:
    artifacts: dict[str, EvolutionArtifact] = field(default_factory=dict)

    def propose(self, artifact: EvolutionArtifact) -> None:
        self.artifacts[artifact.id] = artifact

    def accept_if_regression_passes(self, artifact_id: str, *, min_score: float = 1.0) -> EvolutionStatus:
        artifact = self.artifacts[artifact_id]
        if artifact.regression_results and min(artifact.regression_results.values()) >= min_score:
            artifact.status = EvolutionStatus.ACCEPTED
        else:
            artifact.status = EvolutionStatus.QUARANTINED
        return artifact.status


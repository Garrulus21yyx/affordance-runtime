"""Generic visual-region proposal boundary for browser surface acquisition."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from affordance_runtime.actions.grounding import PerceptionRequirements
from affordance_runtime.surfaces.visual.grounding import (
    VisualGrounderPort,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
    VisualRegionProposerPort,
    point_grounded_visual_regions,
)


class PerceptionOrchestratorPort(Protocol):
    def propose_visual_regions(
        self,
        *,
        observation_epoch_id: str,
        screenshot_path: Path | None,
        screenshot_bytes: bytes,
        image_size: tuple[int, int],
        instruction: str,
        requirements: PerceptionRequirements,
    ) -> tuple[VisualRegion, ...]: ...


@dataclass(frozen=True)
class GenericPerceptionOrchestrator:
    region_proposer: VisualRegionProposerPort | None = None
    point_grounder: VisualGrounderPort | None = None
    max_regions: int = 16

    def __post_init__(self) -> None:
        if self.region_proposer is None and self.point_grounder is None:
            raise ValueError("perception orchestrator requires a visual proposal adapter")

    def propose_visual_regions(
        self,
        *,
        observation_epoch_id: str,
        screenshot_path: Path | None,
        screenshot_bytes: bytes,
        image_size: tuple[int, int],
        instruction: str,
        requirements: PerceptionRequirements,
    ) -> tuple[VisualRegion, ...]:
        if requirements.model_call_budget < 1:
            return ()
        request = VisualRegionProposalRequest(
            sample_id=observation_epoch_id,
            image_path=screenshot_path,
            image_bytes=screenshot_bytes,
            image_size=image_size,
            instruction=instruction,
            max_regions=self.max_regions,
        )
        regions = self.region_proposer.propose(request) if self.region_proposer is not None else []
        if self.point_grounder is not None:
            point = self.point_grounder.ground(
                VisualGroundingRequest(
                    sample_id=observation_epoch_id,
                    image_path=screenshot_path,
                    image_bytes=screenshot_bytes,
                    image_size=image_size,
                    instruction=instruction,
                )
            )
            regions = point_grounded_visual_regions(regions, point, image_size)
        else:
            regions = [
                replace(region, primitive_action="observe_only", action_point_xy=None)
                for region in regions
            ]
        if len(regions) > self.max_regions:
            raise ValueError("visual region proposer exceeded the bounded region count")
        return tuple(regions)

"""One configured PydanticAI inference owner shared by all visual roles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.surfaces.visual.disambiguation import (
    PydanticAIVisualCandidateDisambiguator,
)
from affordance_runtime.surfaces.visual.grounding import (
    PydanticAIVisualGrounder,
    PydanticAIVisualRegionProposer,
)
from affordance_runtime.surfaces.visual.predicate_classification import (
    PydanticAIVisualPredicateClassifier,
)
from affordance_runtime.surfaces.visual.pydantic_ai_inference import (
    PydanticAIVisualInference,
    pydantic_ai_visual_inference_from_environment,
)
from affordance_runtime.surfaces.visual.semantic_classification import (
    PydanticAIVisualSemanticClassifier,
    VisualSemanticRole,
)


@dataclass(frozen=True)
class PydanticAIVisualRoleSet:
    """All bounded visual specialists backed by one provider transport.

    The role set owns provider composition only. Surface adapters continue to
    own offers, capture lineage, and dispatch authority.
    """

    inference: PydanticAIVisualInference = field(repr=False)
    region_proposer: PydanticAIVisualRegionProposer = field(init=False)
    point_grounder: PydanticAIVisualGrounder = field(init=False)
    candidate_disambiguator: PydanticAIVisualCandidateDisambiguator = field(init=False)
    predicate_classifier: PydanticAIVisualPredicateClassifier = field(init=False)
    text_reader: PydanticAIVisualSemanticClassifier = field(init=False)
    spatial_classifier: PydanticAIVisualSemanticClassifier = field(init=False)
    change_classifier: PydanticAIVisualSemanticClassifier = field(init=False)

    def __post_init__(self) -> None:
        inference = self.inference
        object.__setattr__(self, "region_proposer", PydanticAIVisualRegionProposer(inference))
        object.__setattr__(self, "point_grounder", PydanticAIVisualGrounder(inference))
        object.__setattr__(
            self,
            "candidate_disambiguator",
            PydanticAIVisualCandidateDisambiguator(inference),
        )
        object.__setattr__(
            self,
            "predicate_classifier",
            PydanticAIVisualPredicateClassifier(inference),
        )
        object.__setattr__(
            self,
            "text_reader",
            PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.TEXT),
        )
        object.__setattr__(
            self,
            "spatial_classifier",
            PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.SPATIAL),
        )
        object.__setattr__(
            self,
            "change_classifier",
            PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.CHANGE),
        )

    @property
    def provider(self) -> str:
        return self.inference.provider

    @property
    def model(self) -> str:
        return self.inference.model

    @property
    def prompt_versions(self) -> tuple[tuple[str, str], ...]:
        return (
            ("entity_discovery", self.region_proposer.prompt_version),
            ("point_grounding", self.point_grounder.prompt_version),
            ("candidate_disambiguation", self.candidate_disambiguator.prompt_version),
            ("predicate_classification", self.predicate_classifier.prompt_version),
            ("text_in_image", self.text_reader.prompt_version),
            ("spatial_relationship", self.spatial_classifier.prompt_version),
            ("visual_change", self.change_classifier.prompt_version),
        )

    def close(self) -> None:
        self.inference.close()


def pydantic_ai_visual_roles_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    timeout_s: float = 90.0,
) -> PydanticAIVisualRoleSet:
    """Compose all visual roles without creating one transport per role."""

    return PydanticAIVisualRoleSet(
        pydantic_ai_visual_inference_from_environment(environment, timeout_s=timeout_s)
    )


__all__ = ["PydanticAIVisualRoleSet", "pydantic_ai_visual_roles_from_environment"]

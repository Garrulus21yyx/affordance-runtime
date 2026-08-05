"""Mechanical evidence provider groups; no provider owns evaluation or commit."""

from affordance_runtime.verification.providers.artifact import ArtifactEvidenceProvider
from affordance_runtime.verification.providers.resource import ResourceEvidenceProvider
from affordance_runtime.verification.providers.structural import StructuralEvidenceProvider

MECHANICAL_EVIDENCE_PROVIDERS = (
    StructuralEvidenceProvider(),
    ResourceEvidenceProvider(),
    ArtifactEvidenceProvider(),
)

__all__ = [
    "ArtifactEvidenceProvider",
    "MECHANICAL_EVIDENCE_PROVIDERS",
    "ResourceEvidenceProvider",
    "StructuralEvidenceProvider",
]

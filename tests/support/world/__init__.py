"""World-model test support."""

from affordance_runtime.actions import ActionBinding
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    SourceObservationManifest,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)


def manifest_for_sources(
    sources: tuple[SurfaceObservation, ...],
) -> tuple[SourceObservationManifest, ...]:
    return tuple(
        SourceObservationManifest(
            source.observation_id,
            source.surface,
            str(source.source_profile.modality),
            source.source_profile.debug_source,
            source.acquisition_root_id or source.observation_id,
            source.coverage,
        )
        for source in sources
    )


def fused_world(
    source_observation_id: str,
    targets: tuple[SemanticTarget, ...] = (),
    facts: tuple[StateFact, ...] = (),
    bindings: tuple[ActionBinding, ...] = (),
    *,
    coverage: CoverageState = CoverageState.COMPLETE,
    surface: str = "fixture",
    profile: ObservationSourceProfile | None = None,
    artifacts: dict[str, object] | None = None,
) -> WorldObservation:
    """Build a test world through the production source-local fusion owner."""

    resolved_profile = profile or ObservationSourceProfile.dom()
    revisions = {item.source_revision for item in bindings}
    if len(revisions) > 1:
        raise ValueError("test source bindings require one source revision")
    revision = next(iter(revisions), f"revision:{source_observation_id}")
    source = SurfaceObservation(
        source_observation_id,
        surface,
        revision,
        resolved_profile,
        targets,
        facts,
        bindings,
        coverage,
        artifacts=artifacts or {},
        visual_only_target_ids=(
            tuple(item.target_id for item in targets)
            if resolved_profile.modality.value == "visual" else ()
        ),
    )
    fused = WorldFusion().fuse((source,))
    if fused.observation is None:
        raise ValueError(fused.reason_code)
    return fused.observation

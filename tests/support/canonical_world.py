"""Test construction for the production canonical public World owner."""

from __future__ import annotations

from dataclasses import replace

from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.world.contracts import WorldObservation


def canonical_world(
    observation: WorldObservation,
    action_space: ActionSpace | None = None,
    index: WorldDeliveryIndex | None = None,
) -> CanonicalPublicWorldProjection:
    actions = action_space or ActionSpace(observation.observation_id, ())
    delivery_index = index or WorldDeliveryIndex.from_observation(observation, actions.options)
    return CanonicalPublicWorldProjection.build(observation, delivery_index, actions)


def canonical_world_with_regions(
    projection: CanonicalPublicWorldProjection,
    observation: WorldObservation,
    index: WorldDeliveryIndex,
) -> CanonicalPublicWorldProjection:
    """Replace only a test fixture's region view using the production owner."""

    projected = CanonicalPublicWorldProjection.build(
        observation,
        index,
        ActionSpace(observation.observation_id, ()),
    )
    return replace(
        projection,
        private_index_lineage=projected.private_index_lineage,
        ordered_region_records=projected.ordered_region_records,
        region_refs=projected.region_refs,
        private_region_resolver=projected.private_region_resolver,
    )


__all__ = ["canonical_world", "canonical_world_with_regions"]

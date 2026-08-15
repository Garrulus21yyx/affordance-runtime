"""Immutable predicate/source-profile policy owned by world fusion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import SurfaceObservation


class ConflictDisposition(StrEnum):
    CONSENSUS_ONLY = "consensus_only"


@dataclass(frozen=True)
class PredicateFusionDefinition:
    predicate_family: str
    admissible_source_profiles: tuple[str, ...]
    conflict_disposition: ConflictDisposition = ConflictDisposition.CONSENSUS_ONLY


class PredicateFusionError(ValueError):
    pass


class ObservationPredicateRegistry:
    """Closed policy for role, label, and the existing public-state family."""

    def __init__(self) -> None:
        profiles = ("dom", "visual", "wot", "http_json", "user")
        self._definitions: Mapping[str, PredicateFusionDefinition] = MappingProxyType({
            "role": PredicateFusionDefinition("role", profiles),
            "label": PredicateFusionDefinition("label", profiles),
            "state": PredicateFusionDefinition("state", profiles),
        })

    def validate_source(self, source: SurfaceObservation) -> None:
        profile = source.source_profile.debug_source
        if profile not in self._definitions["state"].admissible_source_profiles:
            raise PredicateFusionError("undeclared_source_profile")

    def resolve(
        self,
        predicate_family: str,
        claims: tuple[tuple[SurfaceObservation, object], ...],
    ) -> tuple[object | None, bool]:
        definition = self._definitions.get(predicate_family)
        if definition is None:
            raise PredicateFusionError("undeclared_predicate_family")
        for source, _ in claims:
            if source.source_profile.debug_source not in definition.admissible_source_profiles:
                raise PredicateFusionError("undeclared_predicate_profile")
        encoded = {
            json.dumps(
                to_json_compatible(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ): value
            for _, value in claims
        }
        if not encoded:
            return None, False
        if len(encoded) == 1:
            return next(iter(encoded.values())), False
        return None, True


OBSERVATION_PREDICATE_REGISTRY = ObservationPredicateRegistry()

"""Typed contract fixtures shared by tests that intentionally construct plans directly."""

import hashlib

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contracts import Observation
from affordance_runtime.legacy_criterion_adapter import canonicalize_legacy_criteria
from affordance_runtime.observation_store import ObservationCommit, ObservationRef
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.unified_observation import UnifiedObservation


def make_interaction(target: str) -> ElementIntent:
    return ElementIntent(
        target,
        (SourceReference("test-request", "test-request:interaction"),),
    )


def canonical_observation(snapshot: BrowserSnapshot) -> UnifiedObservation:
    return CanonicalObservationBuilder().build(PerceptionCapture.from_browser_snapshot(snapshot))


def legacy_step_spec(*args: object, **kwargs: object) -> StepSpec:
    """Build a strict StepSpec through the explicit legacy test ingress."""

    positional = list(args)
    if len(positional) > 3:
        positional[3] = canonicalize_legacy_criteria(
            tuple(positional[3]),
            role="completion",  # type: ignore[arg-type]
        )
    elif "completion_criteria" in kwargs:
        kwargs["completion_criteria"] = canonicalize_legacy_criteria(
            tuple(kwargs["completion_criteria"]),
            role="completion",  # type: ignore[arg-type]
        )
    if len(positional) > 6 and positional[6]:
        positional[6] = canonicalize_legacy_criteria(
            tuple(positional[6]),
            role="precondition",  # type: ignore[arg-type]
        )
    elif kwargs.get("preconditions"):
        kwargs["preconditions"] = canonicalize_legacy_criteria(
            tuple(kwargs["preconditions"]),
            role="precondition",  # type: ignore[arg-type]
        )
    return StepSpec(*positional, **kwargs)  # type: ignore[arg-type]


def remember_observation(state: StateKernel, observation: Observation) -> None:
    """Install typed observation identity in unit tests without a legacy StateKernel API."""

    identity = "\0".join(
        (
            observation.snapshot_id,
            observation.environment_revision,
            observation.page_revision,
        )
    )
    digest = "sha256:" + hashlib.sha256(identity.encode()).hexdigest()
    state.remember_observation_commit(
        ObservationCommit(
            ObservationRef(observation.snapshot_id, digest),
            observation.environment_revision,
            observation.page_revision,
        )
    )

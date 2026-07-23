"""Observation acquisition collaborator for the serial Runtime Coordinator."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Protocol, Sequence

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.grounding import ActivePerceptionRequest, GroundingSource
from affordance_runtime.perception import (
    PerceptionEscalation,
    derive_perception_requirements,
    perception_task_terms,
)
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_planning import SubgoalSpec


class ObservationSource(Protocol):
    def capture(self) -> BrowserSnapshot: ...


@dataclass(frozen=True)
class PerceptionSession:
    """Prepare coherent observations without mutating authoritative run state."""

    observer: ObservationSource
    artifacts: ArtifactStore | None = None

    def capture(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        sequence: int,
    ) -> BrowserSnapshot:
        if not isinstance(self.observer, BrowserSession):
            return self.observer.capture()

        active_subgoal = TaskPlanLifecycle.active_subgoal_for_perception(state)
        escalation = self.perception_escalation(state)
        requirements = (
            derive_perception_requirements(
                envelope.task_spec,
                active_subgoal=active_subgoal,
                escalation=escalation,
            )
            if envelope.task_spec is not None
            else None
        )
        screenshot_path = None
        if self.artifacts is not None:
            screenshot_path = (
                self.artifacts.run_dir(envelope.task_id)
                / "screenshots"
                / f"screenshot_{sequence:04d}.png"
            )
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.observer.capture(
            screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
            perception_requirements=requirements,
            task_terms=(
                perception_task_terms(
                    envelope.task_spec,
                    active_subgoal=active_subgoal,
                )
                if envelope.task_spec is not None
                else ()
            ),
            task_instruction=(
                " ".join(
                    dict.fromkeys(
                        item
                        for item in (
                            envelope.task_spec.objective,
                            active_subgoal.objective
                            if isinstance(active_subgoal, SubgoalSpec)
                            else active_subgoal or "",
                        )
                        if item
                    )
                )
                if envelope.task_spec is not None
                else envelope.goal
            ),
        )
        if screenshot_path is not None and self.artifacts is not None:
            if not screenshot_path.exists():
                screenshot_path.write_bytes(self.observer.screenshot())
            self.artifacts.register_file(envelope.task_id, screenshot_path, "image/png")
        return snapshot

    @property
    def supports_targeted_capture(self) -> bool:
        return callable(getattr(self.observer, "capture_targeted", None))

    def capture_targeted(
        self,
        requests: Sequence[ActivePerceptionRequest],
    ) -> BrowserSnapshot:
        capture = getattr(self.observer, "capture_targeted", None)
        if not callable(capture):
            raise TypeError("observation source has no capture_targeted port")
        snapshot = capture(requests)
        if inspect.isawaitable(snapshot):
            snapshot = resolve_awaitable(snapshot)
        if not isinstance(snapshot, BrowserSnapshot):
            raise TypeError("capture_targeted must return one coherent BrowserSnapshot")
        return snapshot

    @staticmethod
    def perception_escalation(state: StateKernel) -> PerceptionEscalation | None:
        failed_sources: set[GroundingSource] = set()
        for lineage in state.grounding_fallback_lineage.values():
            raw_source = lineage.get("failed_source", "")
            try:
                failed_sources.add(GroundingSource(raw_source))
            except ValueError:
                continue
        if not failed_sources:
            return None
        return PerceptionEscalation(
            reason="previous grounding route failed before a verified effect",
            failed_sources=frozenset(failed_sources),
        )

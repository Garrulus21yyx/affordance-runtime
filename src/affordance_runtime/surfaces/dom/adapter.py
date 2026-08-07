"""DOM acquisition and dispatch behind one surface-local boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

from affordance_runtime.execution.contracts import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.action_vocabulary import action_metadata
from affordance_runtime.world.contracts import (
    ActionBinding,
    ActionRisk,
    CoverageState,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)

if TYPE_CHECKING:
    from affordance_runtime.browser_session import BrowserSession
    from affordance_runtime.contracts import Affordance


@dataclass
class DomSurfaceAdapter:
    session: BrowserSession
    surface: str = field(default="dom", init=False)
    _observation_id: str = field(default="", init=False)
    _source_revision: str = field(default="", init=False)

    async def reset(self, task: TaskGoal) -> None:
        del task
        self.session.reset()
        self._observation_id = ""
        self._source_revision = ""

    async def observe(self, reason: str) -> SurfaceObservation:
        del reason
        snapshot = self.session.capture(page_id="agent-loop", task_instruction="")
        observation_id = snapshot.observation.snapshot_id
        targets = tuple(_target(affordance) for affordance in snapshot.affordance_model.affordances)
        bindings = tuple(_binding(observation_id, affordance) for affordance in snapshot.affordance_model.affordances)
        facts = tuple(
            StateFact(
                f"{observation_id}:{target.target_id}:{key}",
                target.target_id,
                key,
                value,
                observation_id,
            )
            for target in targets
            for key, value in target.state.items()
        )
        self._observation_id = observation_id
        self._source_revision = snapshot.observation.page_revision
        return SurfaceObservation(
            observation_id,
            self.surface,
            snapshot.observation.page_revision,
            targets,
            facts,
            bindings,
            CoverageState.COMPLETE,
            {
                "url": snapshot.observation.url,
                "screenshot_ref": snapshot.observation.screenshot_ref,
            },
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        binding = request.binding
        identity_is_current = (
            binding.surface == self.surface
            and binding.source_observation_id == self._observation_id
            and binding.source_revision == self._source_revision
            and (not binding.expires_at_s or time() <= binding.expires_at_s)
        )
        if not identity_is_current:
            return False
        live = self.session.capture(page_id="agent-loop-currentness-probe", task_instruction="")
        current = next(
            (item for item in live.affordance_model.affordances if item.id == binding.target_id),
            None,
        )
        return bool(
            current
            and live.observation.page_revision == binding.source_revision
            and current.target_fingerprint == binding.target_fingerprint
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        if not self.is_current(request):
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                self.surface,
                False,
                ActionError.STALE_BINDING,
            )
        selector = str(request.binding.payload.get("selector") or "")
        try:
            if request.binding.primitive_action == "click":
                self.session.click(selector)
            elif request.binding.primitive_action in {"type", "fill"}:
                self.session.fill(selector, str(request.intent.parameters["text"]))
            elif request.binding.primitive_action == "select":
                self.session.select_option(selector, str(request.intent.parameters["value"]))
            else:
                return ActionResult(
                    request.request_id,
                    DispatchStatus.NOT_SENT,
                    self.surface,
                    False,
                    ActionError.UNSUPPORTED_ACTION,
                )
        except Exception as exc:
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                self.surface,
                False,
                ActionError.EXECUTION_FAILED,
                {"error_type": type(exc).__name__},
            )
        return ActionResult(
            request.request_id,
            DispatchStatus.SENT,
            self.surface,
            True,
            adapter_evidence={"dispatched_action": request.intent.semantic_action},
        )


def _target(affordance: Affordance) -> SemanticTarget:
    return SemanticTarget(
        affordance.id,
        affordance.role,
        affordance.label,
        dict(affordance.state),
    )


def _binding(observation_id: str, affordance: Affordance) -> ActionBinding:
    metadata = action_metadata("dom", affordance.action)
    effects = tuple(filter(None, (affordance.effect_class or affordance.operation_ref,)))
    return ActionBinding(
        binding_id=f"{observation_id}:{affordance.id}:{affordance.action}",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=affordance.lease.page_revision,
        target_fingerprint=affordance.target_fingerprint,
        target_id=affordance.id,
        surface="dom",
        executor_id="dom",
        semantic_action=metadata.semantic_action,
        primitive_action=metadata.primitive_action,
        semantic_effects=effects,
        parameter_schema=dict(metadata.parameter_schema),
        payload=dict(affordance.locator),
        expires_at_s=affordance.lease.expires_at_s,
        confidence=affordance.confidence,
        risk=ActionRisk(affordance.risk.value),
    )

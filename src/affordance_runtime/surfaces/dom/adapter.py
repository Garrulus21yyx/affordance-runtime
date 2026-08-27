"""DOM acquisition and dispatch behind one surface-local boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    InteractionCapabilityError,
)
from affordance_runtime.actions.classification import classify_dom_action
from affordance_runtime.actions.effect_authority import EffectClass, Externality, Reversibility
from affordance_runtime.actions.effect_policy import semantics_for_operation
from affordance_runtime.execution.contracts import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.surfaces.dom.document import project_structured_document
from affordance_runtime.surfaces.dom.interaction_profile import DOM_INTERACTION_CAPABILITIES
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationOffer,
    SelectedObservationRequest,
    SelectedObservationResult,
)
from affordance_runtime.world.contracts import (
    ActionBinding,
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)

if TYPE_CHECKING:
    from affordance_runtime.actions.contracts import Affordance
    from affordance_runtime.surfaces.dom.browser_session import BrowserSession


@dataclass
class DomSurfaceAdapter:
    session: BrowserSession
    trusted_interaction_operations: frozenset[str] = frozenset()
    owns_physical_reset: bool = field(default=True, repr=False)
    surface: str = field(default="dom", init=False)
    _observation_id: str = field(default="", init=False)
    _source_revision: str = field(default="", init=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)

    @property
    def physical_environment_id(self) -> str:
        return f"browser_session:{id(self.session)}"

    def __post_init__(self) -> None:
        operations = frozenset(self.trusted_interaction_operations)
        for operation in operations:
            semantics = semantics_for_operation(operation)
            if semantics is None or (
                semantics.effect_class is not EffectClass.INTERACTION_ONLY
                or semantics.externality is not Externality.LOCAL
                or semantics.reversibility is not Reversibility.REVERSIBLE
            ):
                raise ValueError("trusted DOM interaction operation is not registered as local reversible interaction")
        self.trusted_interaction_operations = operations

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        return (ObservationOffer(
            self.surface, "structural", "structural", "low",
        ),)

    def initialize_task(self, task: TaskGoal) -> None:
        self._task = task
        self._observation_id = ""
        self._source_revision = ""

    async def reset_physical(self) -> None:
        self.session.reset()

    async def acquire(self, request: SelectedObservationRequest) -> SelectedObservationResult:
        snapshot = self.session.capture(page_id="agent-loop", task_instruction="")
        if self._task is None:
            raise RuntimeError("DOM surface adapter must be reset before observation")
        observation_id = snapshot.observation.snapshot_id
        document = project_structured_document(
            str(snapshot.observation.metadata.get("html") or ""),
            snapshot.observation.url,
        )
        document_enabled = (
            len(document.targets) > 1
            or "structured_document" in self._task.requested_outputs
        )
        action_targets = tuple(_target(affordance) for affordance in snapshot.affordance_model.affordances)
        targets = (*action_targets, *(document.targets if document_enabled else ()))
        binding_results = tuple(
            _binding(
                self._task,
                observation_id,
                affordance,
                self.trusted_interaction_operations,
            )
            for affordance in snapshot.affordance_model.affordances
        )
        bindings = tuple(binding for binding in binding_results if binding is not None)
        unsupported = tuple(
            affordance.action
            for affordance, binding in zip(snapshot.affordance_model.affordances, binding_results, strict=True)
            if binding is None
        )
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
        observation = SurfaceObservation(
            observation_id,
            self.surface,
            snapshot.observation.page_revision,
            ObservationSourceProfile.dom(),
            targets,
            facts,
            bindings,
            CoverageState.TRUNCATED if document_enabled and document.truncated else CoverageState.COMPLETE,
            {
                "url": snapshot.observation.url,
                "screenshot_ref": snapshot.observation.screenshot_ref,
                "unsupported_actions": unsupported,
                **({"structured_document": document.artifact} if document_enabled else {}),
            },
            acquisition_root_id=f"browser:{snapshot.observation.page_revision}",
        )
        return SelectedObservationResult.acquired(
            request,
            observation,
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        return self._currentness(request)[0]

    def _currentness(self, request: BoundActionRequest) -> tuple[bool, int]:
        binding = request.binding
        identity_is_current = (
            binding.surface == self.surface
            and binding.source_observation_id == self._observation_id
            and binding.source_revision == self._source_revision
            and (not binding.expires_at_s or time() <= binding.expires_at_s)
        )
        if not identity_is_current:
            return False, 0
        live = self.session.probe_dom_target(binding.source_target_id)
        current = bool(live and live[0] == binding.source_revision and live[1] == binding.target_fingerprint)
        return current, 1

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        current, probe_count = self._currentness(request)
        if not current:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                self.surface,
                False,
                ActionError.STALE_BINDING,
                {"currentness_probe_count": probe_count},
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
                    {"currentness_probe_count": probe_count},
                )
        except Exception as exc:
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                self.surface,
                False,
                ActionError.EXECUTION_FAILED,
                {"error_type": type(exc).__name__, "currentness_probe_count": probe_count},
            )
        return ActionResult(
            request.request_id,
            DispatchStatus.SENT,
            self.surface,
            True,
            adapter_evidence={
                "dispatched_action": request.intent.semantic_action,
                "currentness_probe_count": probe_count,
            },
        )


def _target(affordance: Affordance) -> SemanticTarget:
    return SemanticTarget(
        affordance.id,
        affordance.role,
        affordance.label,
        dict(affordance.state),
    )


def _binding(
    task: TaskGoal,
    observation_id: str,
    affordance: Affordance,
    trusted_interaction_operations: frozenset[str],
) -> ActionBinding | None:
    try:
        translator = DOM_INTERACTION_CAPABILITIES.resolve_primitive(affordance.action)
        schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(translator.semantic_action)
    except InteractionCapabilityError:
        return None
    classification = classify_dom_action(
        task,
        affordance,
        translator.semantic_action,
        trusted_interaction_operations=trusted_interaction_operations,
    )
    return ActionBinding(
        binding_id=f"{observation_id}:{affordance.id}:{affordance.action}",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=affordance.lease.page_revision,
        target_fingerprint=affordance.target_fingerprint,
        target_id=affordance.id,
        source_target_id=affordance.id,
        surface="dom",
        executor_id="dom",
        semantic_action=translator.semantic_action,
        primitive_action=translator.primitive_action,
        effect_category=classification.category.value,
        semantic_effects=classification.semantic_effects,
        parameter_schema=schema,
        payload=dict(affordance.locator),
        observation_barrier=classification.observation_barrier,
        expires_at_s=affordance.lease.expires_at_s,
        confidence=affordance.confidence,
        risk=classification.risk,
        resource_ref=affordance.id,
        reversibility=classification.reversibility,
    )

"""WoT acquisition and dispatch behind one unified surface adapter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from time import monotonic, time
from typing import Any, Callable

from affordance_runtime.adapters.wot import ThingAffordanceModel, WotAdapter
from affordance_runtime.adapters.wot_security import SecurityScheme
from affordance_runtime.execution.contracts import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.wot.interaction_profile import WOT_INTERACTION_CAPABILITIES
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import ObservationOffer
from affordance_runtime.world.action_classification import classify_wot_action
from affordance_runtime.world.contracts import (
    ActionBinding,
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)
from affordance_runtime.world.interaction_capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.world.schema_validation import validate_value

from .contracts import (
    WotAffordanceBinding,
    WotDeploymentScope,
    WotTransportResult,
    WotTransportStatus,
    thing_description_digest,
)
from .currentness import wot_affordance_is_current
from .transport import WotTransportPort


@dataclass
class WotSurfaceAdapter:
    transport: WotTransportPort
    deployment_scope: WotDeploymentScope = WotDeploymentScope.PHYSICAL_DEVICE
    parser: WotAdapter = field(default_factory=WotAdapter, repr=False)
    clock: Callable[[], float] = field(default=monotonic, repr=False)
    surface: str = field(default="wot", init=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)
    _observation_id: str = field(default="", init=False)
    _td_digest: str = field(default="", init=False)
    _routes: dict[str, tuple[WotAffordanceBinding, SecurityScheme]] = field(default_factory=dict, init=False, repr=False)
    _last_sent_at: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        return (ObservationOffer(self.surface, "environment_state", "authoritative", "medium", self.surface),)

    def prepare(self, task: TaskGoal) -> None:
        self._task = task
        self._observation_id = ""
        self._td_digest = ""
        self._routes.clear()
        self._last_sent_at.clear()

    async def reset(self, task: TaskGoal) -> None:
        self.prepare(task)
        self.transport.reset()

    async def observe(self, reason: str) -> SurfaceObservation:
        del reason
        if self._task is None:
            raise RuntimeError("WoT surface adapter must be reset before observation")
        td = self.transport.fetch_thing_description()
        _validate_td_identity(td)
        td_digest = thing_description_digest(td)
        observation_id = f"wot:{uuid.uuid4().hex}"
        model = self.parser.parse(
            td,
            environment_revision=td_digest,
            snapshot_id=observation_id,
            page_revision=td_digest,
        )
        property_targets, facts, read_errors = self._read_state(model, observation_id, td_digest)
        action_targets, candidate_bindings, routes = self._actions(model, observation_id, td_digest)
        event_targets = tuple(
            SemanticTarget(f"wot:{model.thing_id}:event:{name}", "event", name)
            for name in model.events
        )
        self._observation_id = observation_id
        self._td_digest = td_digest
        self._routes = routes
        coverage = _coverage(len(model.state_sources), len(property_targets), len(read_errors))
        return SurfaceObservation(
            observation_id,
            self.surface,
            td_digest,
            ObservationSourceProfile.wot(),
            property_targets + action_targets + event_targets,
            facts,
            candidate_bindings,
            coverage,
            {
                "thing_id": model.thing_id,
                "read_errors": read_errors,
                "unsupported_events": model.events,
                "parser_issues": model.parser_issues,
            },
            acquisition_root_id=f"wot:{td_digest}",
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        binding = request.binding
        route_entry = self._routes.get(binding.binding_id)
        return bool(
            route_entry
            and binding.surface == self.surface
            and binding.source_observation_id == self._observation_id
            and binding.source_revision == self._td_digest
            and (not binding.expires_at_s or time() <= binding.expires_at_s)
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        if not self.is_current(request):
            return self._not_sent(request, ActionError.STALE_BINDING, 0)
        route, scheme = self._routes[request.binding.binding_id]
        try:
            live_td = self.transport.probe_thing_revision()
            _validate_td_identity(live_td)
            live_digest = thing_description_digest(live_td)
            live_model = self.parser.parse(live_td, environment_revision=live_digest)
        except Exception as exc:
            return self._unavailable(request, exc)
        if not wot_affordance_is_current(route, live_digest, live_model):
            return self._not_sent(request, ActionError.STALE_BINDING, 1)
        if self._rate_limited(route):
            return self._not_sent(request, ActionError.RATE_LIMITED, 1)
        try:
            validate_value(dict(request.intent.parameters), request.binding.parameter_schema)
        except ValueError:
            return self._not_sent(request, ActionError.INVALID_PARAMETERS, 1)
        try:
            transport_result = self.transport.execute_affordance(
                route,
                scheme,
                dict(request.intent.parameters),
            )
        except Exception as exc:
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                self.surface,
                False,
                ActionError.EXECUTION_FAILED,
                {"currentness_probe_count": 1, "error_type": type(exc).__name__},
            )
        if transport_result.status != WotTransportStatus.NOT_SENT:
            self._last_sent_at[route.source_affordance_id] = self.clock()
        return self._action_result(request, transport_result)

    def _read_state(
        self,
        model: ThingAffordanceModel,
        observation_id: str,
        td_digest: str,
    ) -> tuple[tuple[SemanticTarget, ...], tuple[StateFact, ...], tuple[str, ...]]:
        targets: list[SemanticTarget] = []
        facts: list[StateFact] = []
        errors: list[str] = []
        for source in model.state_sources:
            name = str(source.get("property") or "")
            scheme = model.security_schemes.get(str(source.get("security_scheme_ref") or ""))
            if not source.get("available") or scheme is None:
                errors.append(f"{name}:unavailable")
                continue
            try:
                route = WotAffordanceBinding.from_state_source(observation_id, td_digest, model.thing_id, source)
                result = self.transport.read_property(route, scheme)
            except Exception as exc:
                errors.append(f"{name}:{type(exc).__name__}")
                continue
            if not result.transport_success:
                errors.append(f"{name}:{result.error_type or 'read_failed'}")
                continue
            try:
                validate_value(result.value, route.input_schema, path=name)
            except ValueError:
                errors.append(f"{name}:schema_mismatch")
                continue
            target_id = f"wot:{model.thing_id}:property:{name}"
            targets.append(SemanticTarget(target_id, "property", name, {name: result.value}))
            facts.append(StateFact(f"{observation_id}:{target_id}:{name}", target_id, name, result.value, observation_id))
        return tuple(targets), tuple(facts), tuple(errors)

    def _actions(
        self,
        model: ThingAffordanceModel,
        observation_id: str,
        td_digest: str,
    ) -> tuple[tuple[SemanticTarget, ...], tuple[ActionBinding, ...], dict[str, tuple[WotAffordanceBinding, SecurityScheme]]]:
        targets: list[SemanticTarget] = []
        bindings: list[ActionBinding] = []
        routes: dict[str, tuple[WotAffordanceBinding, SecurityScheme]] = {}
        for affordance in model.affordances:
            target_id = f"wot:{model.thing_id}:{affordance.role}:{affordance.label}"
            try:
                route = WotAffordanceBinding.from_affordance(observation_id, td_digest, model, affordance)
            except ValueError:
                continue
            scheme = model.security_schemes.get(route.security_scheme_ref)
            if scheme is None or affordance.action != "invoke":
                continue
            supports = getattr(self.transport, "supports", None)
            if supports is not None and not supports(route):
                continue
            try:
                binding = self._binding(affordance, route, target_id)
            except ValueError:
                continue
            targets.append(SemanticTarget(target_id, affordance.role, affordance.label))
            bindings.append(binding)
            routes[binding.binding_id] = (route, scheme)
        return tuple(targets), tuple(bindings), routes

    def _binding(self, affordance: Any, route: WotAffordanceBinding, target_id: str) -> ActionBinding:
        if self._task is None:
            raise RuntimeError("WoT surface adapter must be reset before binding")
        translator = WOT_INTERACTION_CAPABILITIES.resolve_primitive(route.primitive_action)
        schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(translator.semantic_action)
        authored = affordance.risk.value if bool(getattr(affordance, "risk_asserted", False)) else ""
        classification = classify_wot_action(
            self._task,
            affordance.role,
            translator.semantic_action,
            self.deployment_scope,
            authored_risk=authored,
        )
        binding_id = f"{route.source_observation_id}:{route.source_affordance_id}:{route.primitive_action}"
        return ActionBinding(
            binding_id,
            route.source_observation_id,
            route.source_observation_id,
            route.source_revision,
            route.affordance_fingerprint,
            target_id,
            route.source_affordance_id,
            self.surface,
            route.executor_id,
            translator.semantic_action,
            translator.primitive_action,
            classification.category.value,
            classification.semantic_effects,
            schema,
            route.private_payload(),
            classification.observation_barrier,
            route.expires_at_s,
            affordance.confidence,
            risk=classification.risk,
        )

    def _rate_limited(self, route: WotAffordanceBinding) -> bool:
        previous = self._last_sent_at.get(route.source_affordance_id)
        return bool(
            route.min_interval_ms
            and previous is not None
            and (self.clock() - previous) * 1000 < route.min_interval_ms
        )

    def _action_result(self, request: BoundActionRequest, result: WotTransportResult) -> ActionResult:
        status = DispatchStatus(result.status.value)
        error = None if result.transport_success else ActionError.EXECUTION_FAILED
        return ActionResult(
            request.request_id,
            status,
            self.surface,
            result.transport_success,
            error,
            {
                "currentness_probe_count": 1,
                "transport_status": result.status.value,
                **dict(result.evidence),
            },
        )

    def _unavailable(self, request: BoundActionRequest, exc: Exception) -> ActionResult:
        return self._not_sent(request, ActionError.CURRENTNESS_UNAVAILABLE, 1, type(exc).__name__)

    def _not_sent(
        self,
        request: BoundActionRequest,
        error: ActionError,
        probes: int,
        error_type: str = "",
    ) -> ActionResult:
        evidence: dict[str, Any] = {"currentness_probe_count": probes}
        if error_type:
            evidence["error_type"] = error_type
        return ActionResult(request.request_id, DispatchStatus.NOT_SENT, self.surface, False, error, evidence)


def _validate_td_identity(td: dict[str, Any]) -> None:
    if not str(td.get("id") or "").strip():
        raise ValueError("WoT Thing Description requires explicit thing identity")


def _coverage(declared_reads: int, successful_reads: int, failed_reads: int) -> CoverageState:
    if failed_reads == 0 and successful_reads == declared_reads:
        return CoverageState.COMPLETE
    if successful_reads == 0:
        return CoverageState.FAILED
    return CoverageState.TRUNCATED

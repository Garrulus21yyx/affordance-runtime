"""DOM acquisition and dispatch behind one surface-local boundary."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    InteractionCapabilityError,
)
from affordance_runtime.actions.classification import classify_dom_action
from affordance_runtime.actions.effect_authority import EffectClass, Externality
from affordance_runtime.actions.effect_policy import semantics_for_operation
from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.grounding import GroundingSource
from affordance_runtime.actions.space_contracts import ActionRisk
from affordance_runtime.execution.contracts import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.surfaces.dom.document import project_structured_document
from affordance_runtime.surfaces.dom.interaction_profile import (
    DOM_BROWSER_GLOBAL_PRIMITIVES,
    DOM_INTERACTION_CAPABILITIES,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationOffer,
    SelectedObservationRequest,
    SelectedObservationResult,
)
from affordance_runtime.world.contracts import (
    ActionBinding,
    CoverageState,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)
from affordance_runtime.world.observation import CoverageCompleteness

if TYPE_CHECKING:
    from affordance_runtime.actions.contracts import Affordance
    from affordance_runtime.surfaces.dom.browser_session import BrowserSession


MAX_VISIBLE_TEXT_RECORDS = 128
MAX_VISIBLE_TEXT_RECORD_CHARS = 1_200
_PUBLIC_WHITESPACE = re.compile(r"\s+")
_ACTIVE_LAYER_ROLES = frozenset({"alert", "alertdialog", "dialog"})


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
        return (
            ObservationOffer(
                self.surface,
                "structural",
                "structural",
                "low",
            ),
        )

    def initialize_task(self, task: TaskGoal) -> None:
        self._task = task
        self._observation_id = ""
        self._source_revision = ""

    async def reset_physical(self) -> None:
        self.session.reset()

    async def acquire(self, request: SelectedObservationRequest) -> SelectedObservationResult:
        snapshot = self.session.capture(page_id="agent-loop", task_instruction="")
        return self.project_snapshot(request, snapshot)

    def project_snapshot(self, request: SelectedObservationRequest, snapshot) -> SelectedObservationResult:
        """Project a capture supplied by the physical BrowserSession owner."""

        if self._task is None:
            raise RuntimeError("DOM surface adapter must be reset before observation")
        observation_id = snapshot.observation.snapshot_id
        document = project_structured_document(
            str(snapshot.observation.metadata.get("html") or ""),
            snapshot.observation.url,
        )
        document_enabled = len(document.targets) > 1 or "structured_document" in self._task.requested_outputs
        browser_state = self.session.browser_context_state()
        browser_target = _browser_context_target(browser_state)
        action_targets = tuple(_target(affordance) for affordance in snapshot.affordance_model.affordances)
        layer_targets, action_targets, blocked_keys = _project_browser_layers(
            snapshot.layers,
            tuple(snapshot.affordance_model.affordances),
            action_targets,
        )
        text_targets, text_projection_truncated = _visible_text_targets(
            str(snapshot.observation.metadata.get("visible_text") or ""),
            source_truncated=snapshot.observation.metadata.get("visible_text_truncated") is True,
        )
        readable_targets = (*text_targets, *(document.targets if document_enabled else ()))
        targets = (browser_target, *layer_targets, *action_targets, *readable_targets)
        structure = _dom_structure(browser_target, action_targets, readable_targets, layer_targets)
        binding_results = tuple(
            None
            if _affordance_key(affordance) in blocked_keys
            else _binding(
                self._task,
                observation_id,
                affordance,
                self.trusted_interaction_operations,
            )
            for affordance in snapshot.affordance_model.affordances
        )
        bindings = tuple(binding for binding in binding_results if binding is not None)
        bindings = (
            *_browser_context_bindings(observation_id, snapshot.observation.page_revision, browser_state),
            *bindings,
        )
        unsupported = tuple(
            affordance.action
            for affordance, binding in zip(snapshot.affordance_model.affordances, binding_results, strict=True)
            if binding is None and _affordance_key(affordance) not in blocked_keys
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
        media = _snapshot_media(snapshot, action_targets)
        dom_coverage = next(
            (item for item in snapshot.source_coverage if item.source is GroundingSource.DOM),
            None,
        )
        dom_scope_truncated = bool(
            dom_coverage is not None and dom_coverage.completeness is not CoverageCompleteness.COMPLETE
        )
        observation = SurfaceObservation(
            observation_id,
            self.surface,
            snapshot.observation.page_revision,
            ObservationSourceProfile.dom(),
            targets,
            facts,
            bindings,
            (
                CoverageState.TRUNCATED
                if dom_scope_truncated or text_projection_truncated or (document_enabled and document.truncated)
                else CoverageState.COMPLETE
            ),
            {
                "url": snapshot.observation.url,
                "screenshot_ref": snapshot.observation.screenshot_ref,
                "unsupported_actions": unsupported,
                **({"structured_document": document.artifact} if document_enabled else {}),
            },
            media=media,
            acquisition_root_id=f"browser:{snapshot.observation.page_revision}",
            structure=structure,
            structure_total_count=len(structure),
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
        )
        if not identity_is_current:
            return False, 0
        if binding.payload.get("binding_kind") == "browser_context":
            current_fingerprint = _browser_context_fingerprint(self.session.browser_context_state())
            return current_fingerprint == binding.target_fingerprint, 1
        live = self.session.probe_dom_target(binding.source_target_id)
        is_current = bool(live and live[0] == binding.source_revision and live[1] == binding.target_fingerprint)
        return is_current, 1

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
            primitive = request.binding.primitive_action
            if primitive == "click":
                self.session.click(selector)
            elif primitive in {"type", "fill"}:
                self.session.fill(selector, str(request.intent.parameters["text"]))
            elif primitive == "select":
                self.session.select_option(selector, str(request.intent.parameters["value"]))
            elif primitive == "goto":
                url = request.intent.parameters.get("url")
                if not _valid_navigation_url(url):
                    return ActionResult(
                        request.request_id,
                        DispatchStatus.NOT_SENT,
                        self.surface,
                        False,
                        ActionError.INVALID_PARAMETERS,
                        {"currentness_probe_count": probe_count},
                    )
                self.session.open(str(url))
            elif primitive == "go_back":
                self.session.go_back()
            elif primitive == "go_forward":
                self.session.go_forward()
            elif primitive == "new_tab":
                self.session.new_tab()
            elif primitive == "tab_focus":
                self.session.focus_tab(int(request.intent.parameters["index"]))
            elif primitive == "tab_close":
                self.session.close_tab()
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


def _affordance_key(affordance: Affordance) -> str:
    return str(affordance.locator.get("backend_handle") or affordance.locator.get("selector") or "")


def _project_browser_layers(layers, affordances, action_targets):
    """Project browser-owned layer facts and relate contained controls without exposing routes."""

    member_parent: dict[str, str] = {}
    blocked_by: dict[str, str] = {}
    projected: list[SemanticTarget] = []
    for index, layer in enumerate(layers):
        target_id = f"dom-layer:{index}"
        for member_key in layer.member_keys:
            member_parent.setdefault(member_key, target_id)
        for occluded_key in layer.occluded_keys:
            blocked_by.setdefault(occluded_key, target_id)
        projected.append(
            SemanticTarget(
                target_id,
                layer.role,
                layer.label,
                {
                    "visible": True,
                    "active_layer": True,
                    "layer_kind": layer.kind.value,
                    "modal": layer.modal,
                    "blocks_background": layer.blocks_background,
                    "blocked_control_count": len(layer.occluded_keys),
                    **({"visible_text": layer.text} if layer.text and layer.text != layer.label else {}),
                },
            )
        )
    adjusted: list[SemanticTarget] = []
    children: dict[str, list[str]] = {target.target_id: [] for target in projected}
    for affordance, target in zip(affordances, action_targets, strict=True):
        key = _affordance_key(affordance)
        parent_id = member_parent.get(key, "")
        if parent_id:
            children[parent_id].append(target.target_id)
            target = replace(target, relations={**target.relations, "parent_id": parent_id})
        blocking_layer_id = blocked_by.get(key, "")
        if blocking_layer_id:
            target = replace(
                target,
                state={
                    **target.state,
                    "interaction_blocked": True,
                    "blocked_by_active_layer": blocking_layer_id,
                },
            )
        adjusted.append(target)
    return (
        tuple(replace(target, relations={"child_ids": tuple(children[target.target_id])}) for target in projected),
        tuple(adjusted),
        frozenset(blocked_by),
    )


def _visible_text_targets(
    value: str,
    *,
    source_truncated: bool,
) -> tuple[tuple[SemanticTarget, ...], bool]:
    records: list[str] = []
    projection_truncated = source_truncated
    for raw_line in value.splitlines():
        line = _PUBLIC_WHITESPACE.sub(" ", raw_line).strip()
        while line:
            if len(records) >= MAX_VISIBLE_TEXT_RECORDS:
                projection_truncated = True
                break
            records.append(line[:MAX_VISIBLE_TEXT_RECORD_CHARS])
            line = line[MAX_VISIBLE_TEXT_RECORD_CHARS:]
        if len(records) >= MAX_VISIBLE_TEXT_RECORDS and line:
            break
    targets = tuple(
        SemanticTarget(
            f"dom-readable-text:{index}",
            "StaticText",
            text,
            {
                "visible": True,
                **(
                    {"semantic.accessible_name.truncated": True}
                    if projection_truncated and index == len(records) - 1
                    else {}
                ),
            },
        )
        for index, text in enumerate(records)
    )
    return targets, projection_truncated


def _dom_structure(
    browser_target: SemanticTarget,
    action_targets: tuple[SemanticTarget, ...],
    readable_targets: tuple[SemanticTarget, ...],
    layer_targets: tuple[SemanticTarget, ...] = (),
) -> tuple[ObservationStructureNode, ...]:
    """Publish bounded readable content and captured control order from one DOM epoch."""

    controls = (browser_target, *action_targets)
    root_id = "dom-page-root"
    controls_id = "dom-controls-root"
    readable_id = "dom-readable-root"
    control_node_ids = tuple(f"dom-control-node:{index}" for index in range(len(controls)))
    readable_node_ids = tuple(f"dom-readable-node:{index}" for index in range(len(readable_targets)))
    live_layer_node_ids = {
        target.target_id: f"dom-live-layer-node:{index}" for index, target in enumerate(layer_targets)
    }
    live_layer_members: dict[str, list[str]] = {target.target_id: [] for target in layer_targets}
    layer_groups: dict[tuple[str, str], list[tuple[str, SemanticTarget]]] = {}
    direct_control_nodes: list[str] = []
    for structure_id, target in zip(control_node_ids, controls, strict=True):
        parent_id = str(target.relations.get("parent_id") or "")
        if parent_id in live_layer_members:
            live_layer_members[parent_id].append(structure_id)
            continue
        scope_role = str(target.state.get("semantic_scope_role") or "").casefold()
        scope_label = str(target.state.get("semantic_scope_label") or "").strip()
        if scope_role in _ACTIVE_LAYER_ROLES and scope_label:
            layer_groups.setdefault((scope_role, scope_label), []).append((structure_id, target))
        else:
            direct_control_nodes.append(structure_id)
    layer_nodes = tuple(
        ObservationStructureNode(
            f"dom-layer-node:{index}",
            role,
            label,
            {"active_layer": True},
            parent_structure_id=controls_id,
            child_structure_ids=tuple(structure_id for structure_id, _target in members),
        )
        for index, ((role, label), members) in enumerate(layer_groups.items())
    )
    layer_parent_by_control = {
        structure_id: layer.structure_id
        for layer, members in zip(layer_nodes, layer_groups.values(), strict=True)
        for structure_id, _target in members
    }
    layer_parent_by_control.update(
        {
            structure_id: live_layer_node_ids[target_id]
            for target_id, members in live_layer_members.items()
            for structure_id in members
        }
    )
    live_layer_nodes = tuple(
        ObservationStructureNode(
            live_layer_node_ids[target.target_id],
            target.role,
            target.label,
            dict(target.state),
            parent_structure_id=controls_id,
            child_structure_ids=tuple(live_layer_members[target.target_id]),
            semantic_target_id=target.target_id,
        )
        for target in layer_targets
    )
    root_children = (controls_id, *((readable_id,) if readable_targets else ()))
    return (
        ObservationStructureNode(
            root_id,
            "document",
            "Current page",
            child_structure_ids=root_children,
        ),
        ObservationStructureNode(
            controls_id,
            "region",
            "Interactive controls",
            parent_structure_id=root_id,
            child_structure_ids=(
                *direct_control_nodes,
                *(item.structure_id for item in live_layer_nodes),
                *(item.structure_id for item in layer_nodes),
            ),
        ),
        *(
            ObservationStructureNode(
                structure_id,
                target.role,
                target.label,
                parent_structure_id=layer_parent_by_control.get(structure_id, controls_id),
                semantic_target_id=target.target_id,
            )
            for structure_id, target in zip(control_node_ids, controls, strict=True)
        ),
        *live_layer_nodes,
        *layer_nodes,
        *(
            (
                ObservationStructureNode(
                    readable_id,
                    "region",
                    "Visible page text",
                    parent_structure_id=root_id,
                    child_structure_ids=readable_node_ids,
                ),
                *(
                    ObservationStructureNode(
                        structure_id,
                        target.role,
                        target.label,
                        parent_structure_id=readable_id,
                        semantic_target_id=target.target_id,
                    )
                    for structure_id, target in zip(
                        readable_node_ids,
                        readable_targets,
                        strict=True,
                    )
                ),
            )
            if readable_targets
            else ()
        ),
    )


def _snapshot_media(snapshot, targets: tuple[SemanticTarget, ...]) -> tuple[ObservationMedia, ...]:
    frame = snapshot.visual_frame
    if frame is None:
        return ()
    known = {item.target_id for item in targets}
    regions: list[ObservationGroundingRegion] = []
    for affordance in snapshot.affordance_model.affordances:
        if affordance.id not in known:
            continue
        raw = affordance.locator.get("bbox")
        if not isinstance(raw, tuple | list) or len(raw) != 4:
            continue
        try:
            x, y, width, height = (float(item) for item in raw)
        except (TypeError, ValueError):
            continue
        left = max(0, min(frame.image_width - 1, round(x)))
        top = max(0, min(frame.image_height - 1, round(y)))
        right = max(left + 1, min(frame.image_width, round(x + width)))
        bottom = max(top + 1, min(frame.image_height, round(y + height)))
        if right <= left or bottom <= top:
            continue
        regions.append(
            ObservationGroundingRegion(
                affordance.id,
                (left, top, right - left, bottom - top),
                affordance.confidence,
                "browser-session:viewport_pixels",
            )
        )
    return (
        ObservationMedia(
            "screenshot",
            "screenshot",
            "image/png",
            frame.image_bytes,
            tuple(regions),
            capture_group_id=f"browser:{snapshot.observation.page_revision}",
            variant=ObservationMediaVariant.RAW,
            dimensions=(frame.image_width, frame.image_height),
            coordinate_space_id="browser-session:viewport_pixels",
        ),
    )


def _browser_context_target(state: object) -> SemanticTarget:
    public_tabs = tuple(
        {
            "index": tab["index"],
            "title": _public_title(tab.get("title")),
            "route": _public_route(tab.get("url")) or "opaque",
            "active": tab["active"],
        }
        for tab in _browser_tabs(state)
    )
    return SemanticTarget(
        "browser-context:current",
        "browser_context",
        "Browser navigation",
        {
            "subject.kind": "browser_context",
            "open_tabs": public_tabs,
            "active_tab_index": _active_tab_index(state),
            "navigation_scope": "unrestricted",
        },
    )


def _browser_context_bindings(
    observation_id: str,
    source_revision: str,
    state: object,
) -> tuple[ActionBinding, ...]:
    tabs = _browser_tabs(state)
    active_index = _active_tab_index(state)
    fingerprint = _browser_context_fingerprint(state)
    primitives = tuple(
        primitive
        for primitive in DOM_BROWSER_GLOBAL_PRIMITIVES
        if primitive != "tab_focus" or len(tabs) > 1
        if primitive != "tab_close" or len(tabs) > 1
    )
    bindings = []
    for primitive in primitives:
        schema = (
            INTERACTION_CAPABILITY_REGISTRY.parameter_schema(
                primitive,
                current_value_schema={
                    "type": "integer",
                    "enum": [index for index in range(len(tabs)) if index != active_index],
                },
            )
            if primitive == "tab_focus"
            else INTERACTION_CAPABILITY_REGISTRY.parameter_schema(primitive)
        )
        bindings.append(
            ActionBinding(
                f"{observation_id}:browser-context:{primitive}",
                observation_id,
                observation_id,
                source_revision,
                fingerprint,
                "browser-context:current",
                "browser-context:current",
                "dom",
                "dom",
                primitive,
                primitive,
                "local_reversible",
                ("external_ui_interaction",),
                schema,
                {"binding_kind": "browser_context"},
                observation_barrier=True,
                risk=ActionRisk.LOW,
                reversibility=Reversibility.REVERSIBLE,
            )
        )
    return tuple(bindings)


def _browser_tabs(state: object) -> tuple[dict[str, object], ...]:
    if not isinstance(state, dict):
        raise TypeError("browser context state must be an object")
    raw_tabs = state.get("open_tabs")
    if not isinstance(raw_tabs, tuple | list) or not raw_tabs:
        raise ValueError("browser context requires at least one tab")
    tabs = tuple(raw_tabs)
    if any(not isinstance(tab, dict) for tab in tabs):
        raise TypeError("browser context tabs must be objects")
    return tabs


def _active_tab_index(state: object) -> int:
    if not isinstance(state, dict):
        raise TypeError("browser context state must be an object")
    value = state.get("active_tab_index")
    tabs = _browser_tabs(state)
    if type(value) is not int or not 0 <= value < len(tabs):
        raise ValueError("browser context active tab is invalid")
    return value


def _browser_context_fingerprint(state: object) -> str:
    tabs = _browser_tabs(state)
    payload = (
        tuple(
            (
                tab["index"] if type(tab.get("index")) is int else -1,
                str(tab.get("url") or ""),
                bool(tab.get("active")),
            )
            for tab in tabs
        ),
        _active_tab_index(state),
    )
    return "sha256:" + hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _public_route(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path or "/", "", ""))[:1_000]


def _public_title(value: object) -> str:
    return re.sub(r"\s+", " ", value).strip()[:240] if isinstance(value, str) else ""


def _valid_navigation_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return bool(
        parsed.scheme in {"http", "https"} and parsed.hostname and parsed.username is None and parsed.password is None
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
        # DOM currentness is proven by the source revision plus a live target
        # fingerprint probe immediately before dispatch.  Publishing the
        # parser's short-lived internal lease here would make model-visible
        # actions expire merely because model inference took longer than the
        # parser lease.
        expires_at_s=0.0,
        confidence=affordance.confidence,
        risk=classification.risk,
        resource_ref=affordance.id,
        reversibility=classification.reversibility,
    )

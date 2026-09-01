"""Bounded structural BrowserGym observation projection."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    VerificationFamily,
)
from affordance_runtime.actions.schema_validation import MAX_OPTION_DOMAIN_ITEMS
from affordance_runtime.surfaces.browsergym.binding import (
    BrowserGymDragBinding,
    BrowserGymDragDestination,
    BrowserGymElementBinding,
    BrowserGymFocusedContextBinding,
    BrowserGymNavigationBinding,
    BrowserGymPrivateBinding,
    BrowserGymViewportBinding,
)
from affordance_runtime.surfaces.browsergym.capture_frame import (
    BrowserGymCaptureFrame,
    browsergym_capture_frame,
)
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.interaction_profile import (
    BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES,
    BROWSERGYM_INTERACTION_CAPABILITIES,
    informational_browsergym_roles,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    BrowserGymSemanticAnalysis,
    CanonicalBrowserControl,
    analyze_browsergym_semantics,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
    BrowserGymTaskStateSnapshot,
)
from affordance_runtime.surfaces.semantic_shape import (
    close_repeated_source_structure,
    explicit_role_semantic_shape,
)
from affordance_runtime.world import (
    MAX_OBSERVATION_GROUNDING_REGIONS,
    CoverageState,
    EntityInventoryIssueCode,
    EntityInventoryStatus,
    EntityInventorySummary,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticInventorySummary,
    SemanticShape,
    SemanticShapeKind,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)
from affordance_runtime.world.regular_lattice import (
    SpatialNode,
    VisibleNumericLabel,
    derive_regular_lattice,
)

MAX_INVENTORY_FACTS = 4_096
MAX_STRUCTURE_NODES = 2_048

def _source_semantic_shape(
    structure_node,
    *,
    retained_private_ids: frozenset[str],
    has_semantic_target: bool,
) -> SemanticShape:
    """Classify only explicit source structure; never infer from repetition or page content."""

    complete = all(child in retained_private_ids for child in structure_node.private_child_ids)
    return explicit_role_semantic_shape(
        structure_node.role,
        has_children=bool(structure_node.private_child_ids),
        has_semantic_target=has_semantic_target,
        complete=complete,
    )


@dataclass(frozen=True)
class BrowserGymProjection:
    source: SurfaceObservation
    private_bindings: tuple[BrowserGymPrivateBinding, ...]
    target_count_total: int
    fact_count_total: int
    semantic_analysis: BrowserGymSemanticAnalysis


def project_browsergym_observation(
    raw: dict[str, object],
    *,
    observation_id: str,
    source_revision: str,
    page_identity: str,
    episode_identity: str,
    task_state: BrowserGymTaskStateSnapshot,
    entity_identity: BrowserGymEntityIdentityMap,
    browser_global_primitives: tuple[str, ...] = (),
    browser_navigation_locations: tuple[str, ...] | None = None,
    capture_frame: BrowserGymCaptureFrame | None = None,
) -> BrowserGymProjection:
    capture_frame = capture_frame or browsergym_capture_frame(
        raw,
        acquisition_root_id=observation_id,
        page_identity=page_identity,
        episode_identity=episode_identity,
    )
    analysis = analyze_browsergym_semantics(raw)
    candidates = list(analysis.controls)
    # Action-bearing inventory is all-or-typed-capacity.  BrowserGym already
    # produced this finite supported control set, so retain it in full; only
    # read-only facts/structure may remain explicitly partial below.
    projected = candidates
    lattice = derive_regular_lattice(
        tuple(
            SpatialNode(node.private_node_id, node.private_parent_id, node.private_bbox)
            for node in projected
            if (
                node.private_bbox is not None
                and node.executable
                and any(
                    offer.semantic_action == "activate"
                    for offer in node.executable_offers
                )
            )
        ),
        _visible_numeric_labels(raw),
    )
    lattice_by_node = {item.node_id: item for item in lattice.memberships}
    targets: list[SemanticTarget] = []
    facts: list[StateFact] = []
    bindings: list[ActionBinding] = []
    private: list[BrowserGymPrivateBinding] = []
    fact_total = (
        sum(len(node.public_state) + bool(node.public_options) for node in candidates)
        + 3 * len(lattice.memberships)
    )
    candidate_node_ids = {node.private_node_id for node in candidates}
    relation_total = sum(
        bool(node.private_parent_id and node.private_parent_id in candidate_node_ids)
        + sum(child_id in candidate_node_ids for child_id in node.private_child_ids)
        for node in candidates
    )
    option_value_total = sum(len(node.public_options) for node in candidates)
    option_value_count = 0
    issues: list[EntityInventoryIssueCode] = []
    target_ids = {
        node.private_node_id: entity_identity.entity_id(
            node,
            page_identity=page_identity,
            episode_identity=episode_identity,
        )
        for node in projected
    }
    retained_structure = _retain_source_structure(analysis.structure, tuple(projected))
    structure_ids = {
        structure_node.private_node_id: entity_identity.structure_id(
            structure_node,
            page_identity=page_identity,
            episode_identity=episode_identity,
        )
        for structure_node in retained_structure
    }
    retained_private_ids = frozenset(structure_ids)
    derived_structure_children: dict[str, list[str]] = {}
    for structure_node in retained_structure:
        if structure_node.private_parent_id in structure_ids:
            derived_structure_children.setdefault(structure_node.private_parent_id, []).append(
                structure_node.private_node_id
            )
    structure = close_repeated_source_structure(tuple(
        ObservationStructureNode(
            structure_ids[structure_node.private_node_id],
            structure_node.role,
            structure_node.accessible_name,
            dict(structure_node.public_state),
            structure_ids.get(structure_node.private_parent_id, ""),
            tuple(
                structure_ids[child_id]
                for child_id in dict.fromkeys((
                    *structure_node.private_child_ids,
                    *derived_structure_children.get(structure_node.private_node_id, ()),
                ))
                if child_id in structure_ids
            ),
            target_ids.get(structure_node.private_node_id, ""),
            bool(
                structure_node.private_parent_id
                and structure_node.private_parent_id not in structure_ids
            ),
            _source_semantic_shape(
                structure_node,
                retained_private_ids=retained_private_ids,
                has_semantic_target=structure_node.private_node_id in target_ids,
            ),
        )
        for structure_node in retained_structure
    ))
    controls_by_node_id = {node.private_node_id: node for node in projected}
    viewport_target, viewport_structure, viewport_public, viewport_private = _viewport_subject(
        raw,
        observation_id,
        source_revision,
        page_identity,
        episode_identity,
    )
    targets.append(viewport_target)
    bindings.append(viewport_public)
    private.append(viewport_private)
    browser_context = _browser_context_subject(
        raw,
        observation_id,
        source_revision,
        page_identity,
        episode_identity,
        browser_global_primitives,
        browser_navigation_locations,
    )
    if browser_context is not None:
        browser_target, browser_structure, browser_pairs = browser_context
        targets.append(browser_target)
        for browser_public, browser_private in browser_pairs:
            bindings.append(browser_public)
            private.append(browser_private)
    for ordinal, node in enumerate(projected):
        target_id = target_ids[node.private_node_id]
        state: dict[str, object] = dict(node.public_state)
        execution_allowed = not _is_tab_panel_container(node, controls_by_node_id)
        drag_destinations = _drag_destinations(node, projected, target_ids)
        membership = lattice_by_node.get(node.private_node_id)
        if membership is not None:
            state.update({
                "grid_coordinate": {"x": membership.x, "y": membership.y},
                "grid_membership": {
                    "grid_id": membership.grid_id,
                    "row_index": membership.row_index,
                    "column_index": membership.column_index,
                },
                "grid_coordinate_confidence": membership.confidence,
            })
        if node.public_options:
            option_domain = node.public_options[:MAX_OPTION_DOMAIN_ITEMS]
            state["option_domain"] = option_domain
            option_value_count += len(option_domain)
            if len(option_domain) < len(node.public_options):
                issues.append(EntityInventoryIssueCode.OPTION_DOMAIN_CAPACITY_EXCEEDED)
        why_not_eligible = _why_not_eligible(node, execution_allowed, drag_destinations)
        if why_not_eligible:
            state["action.why_not_eligible"] = why_not_eligible
        relations: dict[str, object] = {}
        parent = target_ids.get(node.private_parent_id)
        children = tuple(target_ids[child_id] for child_id in node.private_child_ids if child_id in target_ids)
        if parent:
            relations["parent_id"] = parent
        if children:
            relations["child_ids"] = children
        target = SemanticTarget(
            target_id,
            node.role,
            node.accessible_name,
            state,
            relations,
        )
        targets.append(target)
        for key, value in state.items():
            if len(facts) >= MAX_INVENTORY_FACTS:
                break
            facts.append(StateFact(f"{observation_id}:{target_id}:{key}", target_id, key, value, observation_id))
        binding_pairs = _binding_pairs(
            node,
            target_id,
            ordinal,
            observation_id,
            source_revision,
            page_identity,
            episode_identity,
            drag_destinations=drag_destinations,
            execution_allowed=execution_allowed,
        )
        for public, runtime in binding_pairs:
            bindings.append(public)
            private.append(runtime)
    focused = _focused_context_subject(
        projected,
        target_ids,
        observation_id,
        source_revision,
        page_identity,
        episode_identity,
    )
    if focused is not None:
        focused_target, focused_structure, focused_bindings = focused
        targets.append(focused_target)
        for focused_public, focused_private in focused_bindings:
            bindings.append(focused_public)
            private.append(focused_private)
    fact_total = max(fact_total, len(facts))
    if fact_total > len(facts):
        issues.append(EntityInventoryIssueCode.FACT_CAPACITY_EXCEEDED)
    relation_count = sum(
        bool(target.relations.get("parent_id")) + len(target.relations.get("child_ids", ())) for target in targets
    )
    relation_total_count = relation_total + (
        len(focused_target.relations.get("child_ids", ()))
        if focused is not None
        else 0
    )
    issues = list(dict.fromkeys(issues))
    truncated = bool(issues)
    coverage = CoverageState.TRUNCATED if truncated else CoverageState.COMPLETE
    artifacts = {}
    artifacts["regular_lattice_semantics"] = {
        "public_summary": (
            f"Regular lattice derivation: {lattice.code}; "
            f"derived targets: {len(lattice.memberships)}."
        ),
        "status": lattice.code.value,
        "derived_target_count": len(lattice.memberships),
    }
    artifacts[BROWSERGYM_TASK_STATE_EVIDENCE_KEY] = {
        "public_summary": "Current provider-native BrowserGym task state.",
        "source": task_state.source.value,
    }
    eligibility_diagnostics = _eligibility_diagnostics(targets, bindings)
    if eligibility_diagnostics:
        artifacts["browsergym_action_eligibility"] = {
            "public_summary": "Non-authoritative diagnostics for BrowserGym targets visible in structure but absent from action bindings.",
            "items": eligibility_diagnostics,
        }
    screenshot_media = _screenshot_media(
        capture_frame,
        observation_id,
        _screenshot_grounding_regions(raw, tuple(projected), target_ids),
    )
    if screenshot_media:
        artifacts["screenshot_semantic_state"] = {
            "public_summary": "Current screenshot state for bounded before/after effect comparison.",
        }
    derived_subject_count = 1 + int(focused is not None) + int(browser_context is not None)
    actionable_target_count = len({binding.target_id for binding in bindings})
    projected_target_count = len(targets)
    recognized_target_count = analysis.inventory.recognized_target_count + derived_subject_count
    inventory = SemanticInventorySummary.assessed(
        analysis.inventory.profile_id,
        recognized_target_count=recognized_target_count,
        projected_target_count=projected_target_count,
        actionable_target_count=actionable_target_count,
        non_executable_target_count=projected_target_count - actionable_target_count,
        omitted_target_count=recognized_target_count - projected_target_count,
        informational_target_count=sum(
            target.role in informational_browsergym_roles() for target in targets
        ),
    )
    entity_inventory = EntityInventorySummary(
        EntityInventoryStatus.PARTIAL if truncated else EntityInventoryStatus.COMPLETE,
        len(targets),
        len(candidates) + derived_subject_count,
        len(facts),
        fact_total,
        relation_count,
        relation_total_count,
        option_value_count,
        option_value_total,
        tuple(issues),
    )
    source = SurfaceObservation(
        observation_id,
        "browsergym",
        source_revision,
        ObservationSourceProfile.dom(),
        tuple(targets),
        tuple(facts),
        tuple(bindings),
        coverage,
        artifacts,
        inventory,
        screenshot_media,
        entity_inventory,
        acquisition_root_id=observation_id,
        structure=(
            *structure,
            viewport_structure,
            *((browser_structure,) if browser_context is not None else ()),
            *((focused_structure,) if focused is not None else ()),
        ),
        structure_total_count=(
            len(analysis.structure)
            + 1
            + int(browser_context is not None)
            + int(focused is not None)
        ),
    )
    return BrowserGymProjection(
        source,
        tuple(private),
        len(candidates) + derived_subject_count,
        fact_total,
        analysis,
    )


def _viewport_subject(
    raw: dict[str, object],
    observation_id: str,
    revision: str,
    page_identity: str,
    episode_identity: str,
) -> tuple[SemanticTarget, ObservationStructureNode, ActionBinding, BrowserGymViewportBinding]:
    target_id = "viewport:current"
    width, height = _viewport_dimensions(raw)
    state = {"subject.kind": "viewport", "scroll_extent_source": "viewport"}
    page_route = _public_page_route(raw.get("url"))
    if page_route:
        state["page.route"] = page_route
    target = SemanticTarget(target_id, "viewport", "Current page viewport", state, {})
    structure = ObservationStructureNode(
        "structure:viewport:current",
        "viewport",
        "Current page viewport",
        state,
        "",
        (),
        target_id,
        False,
        SemanticShape.resolved(SemanticShapeKind.ATOM),
    )
    schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema("scroll")
    binding_id = f"binding:{observation_id}:viewport:scroll"
    public = ActionBinding(
        binding_id,
        observation_id,
        observation_id,
        revision,
        _public_fingerprint(("viewport", target.label, tuple(sorted(state.items())))),
        target_id,
        target_id,
        "browsergym",
        "browsergym",
        "scroll",
        "scroll",
        "local_reversible",
        ("external_ui_interaction",),
        schema,
        {},
        observation_barrier=True,
        risk=ActionRisk.LOW,
        verification_family=VerificationFamily.SCROLL_STATE.value,
    )
    private = BrowserGymViewportBinding(
        binding_id,
        observation_id,
        revision,
        page_identity,
        episode_identity,
        target_id,
        "scroll",
        width,
        height,
    )
    return target, structure, public, private


def _public_page_route(value: object) -> str:
    """Expose the visible origin/path while excluding query, fragment, and credentials."""

    if not isinstance(value, str) or not value.strip():
        return ""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path or "/", "", ""))[:1_000]


def _public_page_title(value: object) -> str:
    """Expose BrowserGym's browser-owned tab title as bounded display metadata."""

    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:240]


def _browser_context_subject(
    raw: dict[str, object],
    observation_id: str,
    revision: str,
    page_identity: str,
    episode_identity: str,
    primitives: tuple[str, ...],
    navigation_locations: tuple[str, ...] | None,
) -> tuple[
    SemanticTarget,
    ObservationStructureNode,
    tuple[tuple[ActionBinding, BrowserGymNavigationBinding], ...],
] | None:
    supported = tuple(primitives)
    if len(set(supported)) != len(supported) or any(
        item not in BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES for item in supported
    ):
        raise ValueError("BrowserGym browser-action profile is invalid")
    if not supported:
        return None
    raw_urls = _string_sequence(raw.get("open_pages_urls"))
    if not raw_urls:
        current = raw.get("url")
        raw_urls = (current,) if isinstance(current, str) and current else ()
    raw_titles = _indexed_string_sequence(raw.get("open_pages_titles"))
    active_index = _active_page_index(raw.get("active_page_index"), len(raw_urls))
    public_tabs = tuple(
        {
            "index": index,
            **(
                {"title": title}
                if (title := _public_page_title(
                    raw_titles[index] if index < len(raw_titles) else ""
                ))
                else {}
            ),
            "route": _public_page_route(url) or "opaque",
            "active": index == active_index,
        }
        for index, url in enumerate(raw_urls)
    )
    target_id = "browser-context:current"
    state: dict[str, object] = {
        "subject.kind": "browser_context",
        "open_tabs": public_tabs,
        "active_tab_index": active_index,
        "navigation_scope": (
            "unrestricted" if navigation_locations is None else "environment_restricted"
        ),
    }
    target = SemanticTarget(target_id, "browser_context", "Browser navigation", state, {})
    structure = ObservationStructureNode(
        "structure:browser-context:current",
        "browser_context",
        "Browser navigation",
        state,
        "",
        (),
        target_id,
        False,
        SemanticShape.resolved(SemanticShapeKind.ATOM),
    )
    # Titles are semantic display metadata supplied by BrowserGym, not binding
    # identity. A dynamic title change must not make a browser-global action stale.
    tab_identity = tuple(
        (tab["index"], tab["route"], tab["active"])
        for tab in public_tabs
    )
    fingerprint = _public_fingerprint(("browser_context", tab_identity, active_index))
    pairs: list[tuple[ActionBinding, BrowserGymNavigationBinding]] = []
    for primitive in supported:
        if primitive == "tab_focus":
            available_indexes = [index for index in range(len(raw_urls)) if index != active_index]
            if not available_indexes:
                continue
            schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(
                primitive,
                current_value_schema={"type": "integer", "enum": available_indexes},
            )
        else:
            schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(primitive)
        binding_id = f"binding:{observation_id}:browser-context:{primitive}"
        public = ActionBinding(
            binding_id,
            observation_id,
            observation_id,
            revision,
            fingerprint,
            target_id,
            target_id,
            "browsergym",
            "browsergym",
            primitive,
            primitive,
            "local_reversible",
            ("external_ui_interaction",),
            schema,
            {},
            observation_barrier=True,
            risk=ActionRisk.LOW,
            verification_family=VerificationFamily.NAVIGATION_CONTEXT.value,
        )
        private = BrowserGymNavigationBinding(
            binding_id=binding_id,
            source_observation_id=observation_id,
            source_revision=revision,
            page_identity=page_identity,
            episode_identity=episode_identity,
            semantic_target_id=target_id,
            supported_primitive=primitive,
            open_pages_urls=raw_urls,
            navigation_locations=navigation_locations,
        )
        pairs.append((public, private))
    return target, structure, tuple(pairs)


def normalize_browser_navigation_locations(urls: tuple[str, ...]) -> tuple[str, ...]:
    """Project explicitly configured HTTP(S) URLs to BrowserGym's netloc contract."""

    locations: list[str] = []
    for value in urls:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("browser navigation URL must be nonempty")
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
            raise ValueError("browser navigation URL must be an HTTP(S) origin without credentials")
        location = parsed.hostname.casefold()
        if parsed.port is not None:
            location = f"{location}:{parsed.port}"
        locations.append(location)
    normalized = tuple(dict.fromkeys(locations))
    if not normalized:
        raise ValueError("restricted browser navigation requires at least one location")
    return normalized


def _string_sequence(value: object) -> tuple[str, ...]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple | list):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def _indexed_string_sequence(value: object) -> tuple[str, ...]:
    """Keep BrowserGym's positional tab metadata aligned with open_pages_urls."""

    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple | list):
        return tuple(item if isinstance(item, str) else "" for item in value)
    return ()


def _active_page_index(value: object, tab_count: int) -> int:
    if tab_count <= 0:
        return 0
    raw = value
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, tuple | list) and len(raw) == 1:
        raw = raw[0]
    return raw if type(raw) is int and 0 <= raw < tab_count else 0


def _focused_context_subject(
    controls: list[CanonicalBrowserControl],
    target_ids: dict[str, str],
    observation_id: str,
    revision: str,
    page_identity: str,
    episode_identity: str,
) -> tuple[
    SemanticTarget,
    ObservationStructureNode,
    tuple[tuple[ActionBinding, BrowserGymFocusedContextBinding], ...],
] | None:
    focused = tuple(
        control
        for control in controls
        if dict(control.public_state).get("focused") is True
        and control.private_node_id in target_ids
    )
    if len(focused) > 1:
        return None
    focused_control = focused[0] if focused else None
    has_element_press = focused_control is not None and any(
        offer.semantic_action == "press_key" and offer.primitive_action == "press"
        for offer in focused_control.executable_offers
    )
    target_id = "focused-context:current"
    state: dict[str, object] = {"subject.kind": "focused_context"}
    relations: dict[str, object] = {}
    child_ids: tuple[str, ...] = ()
    if focused_control is not None:
        state["focused"] = True
        state["focused_role"] = focused_control.role
        if focused_control.accessible_name:
            state["focused_label"] = focused_control.accessible_name
        focused_target_id = target_ids[focused_control.private_node_id]
        relations["child_ids"] = (focused_target_id,)
        child_ids = (focused_target_id,)
    else:
        state["focused"] = "unknown"
    target = SemanticTarget(target_id, "focused_context", "Current keyboard focus", state, relations)
    structure = ObservationStructureNode(
        "structure:focused-context:current",
        "focused_context",
        "Current keyboard focus",
        state,
        "",
        (),
        target_id,
        False,
        SemanticShape.resolved(SemanticShapeKind.ATOM),
    )
    fingerprint = _public_fingerprint(
        ("focused_context", target.label, tuple(sorted(state.items())), child_ids)
    )
    actions = [("hotkey", "keyboard_hotkey")]
    if not has_element_press:
        actions.insert(0, ("press_key", "keyboard_press"))
    pairs = []
    for semantic_action, primitive_action in actions:
        binding_id = f"binding:{observation_id}:focused-context:{semantic_action.replace('_', '-')}"
        public = ActionBinding(
            binding_id,
            observation_id,
            observation_id,
            revision,
            fingerprint,
            target_id,
            target_id,
            "browsergym",
            "browsergym",
            semantic_action,
            primitive_action,
            "local_reversible",
            ("external_ui_interaction",),
            INTERACTION_CAPABILITY_REGISTRY.parameter_schema(semantic_action),
            {},
            observation_barrier=True,
            risk=ActionRisk.LOW,
            verification_family=VerificationFamily.SEMANTIC.value,
        )
        runtime = BrowserGymFocusedContextBinding(
            binding_id,
            observation_id,
            revision,
            page_identity,
            episode_identity,
            target_id,
            primitive_action,
            focused_control.private_bid if focused_control is not None else "",
            focused_control.private_navigation_potential if focused_control is not None else False,
        )
        pairs.append((public, runtime))
    return target, structure, tuple(pairs)


def _viewport_dimensions(raw: dict[str, object]) -> tuple[int, int]:
    screenshot = raw.get("screenshot")
    shape = getattr(screenshot, "shape", None)
    if isinstance(shape, tuple) and len(shape) >= 2:
        height, width = shape[0], shape[1]
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            return width, height
    return 800, 600


def _public_fingerprint(value: object) -> str:
    return "sha256:" + hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def _visible_numeric_labels(raw: dict[str, object]) -> tuple[VisibleNumericLabel, ...]:
    """Read visible numeric labels and geometry already present in one AX snapshot."""

    tree = raw.get("axtree_object")
    nodes = tree.get("nodes") if isinstance(tree, dict) else None
    extra = raw.get("extra_element_properties")
    if not isinstance(nodes, list) or not isinstance(extra, dict):
        return ()
    records = {
        str(node.get("nodeId")): node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("nodeId"), str | int)
    }
    result: list[VisibleNumericLabel] = []
    for node_id, node in records.items():
        bid = node.get("browsergym_id")
        parent = node.get("parentId")
        if not isinstance(bid, str) or not bid or not isinstance(parent, str | int):
            continue
        properties = extra.get(bid)
        if not isinstance(properties, dict) or properties.get("clickable") is True:
            continue
        bbox = _numeric_bbox(properties.get("bbox"))
        text = _descendant_numeric_text(node, records)
        if bbox is None or text is None:
            continue
        value = float(text)
        normalized: int | float = int(value) if value.is_integer() else value
        label_digest = hashlib.sha256(f"{node_id}\0{text}\0{bbox}".encode()).hexdigest()[:16]
        result.append(VisibleNumericLabel(
            f"label:{label_digest}", str(parent), normalized, bbox,
        ))
    return tuple(result)


def _retain_source_structure(
    structure: tuple[object, ...],
    projected_controls: tuple[CanonicalBrowserControl, ...],
) -> tuple[object, ...]:
    """Keep projected controls structurally attached before adding bounded context."""

    by_node = {node.private_node_id: node for node in structure if node.private_node_id}
    structure_index = {
        node.private_node_id: index
        for index, node in enumerate(structure)
        if node.private_node_id
    }
    required: set[str] = set()
    for control in projected_controls:
        current_id = control.private_node_id
        while current_id and current_id in by_node and current_id not in required:
            required.add(current_id)
            current_id = by_node[current_id].private_parent_id
    limit = max(MAX_STRUCTURE_NODES, len(required))
    retained_ids: set[str] = set()
    retained: list[object] = []
    for node in structure:
        if node.private_node_id in required:
            retained.append(node)
            retained_ids.add(node.private_node_id)
    for node in structure:
        if len(retained) >= limit:
            break
        if node.private_node_id in retained_ids:
            continue
        retained.append(node)
        retained_ids.add(node.private_node_id)
    retained.sort(key=lambda item: structure_index[item.private_node_id])
    return tuple(retained)


def _descendant_numeric_text(
    owner: dict[str, object],
    records: dict[str, dict[str, object]],
) -> str | None:
    owner_children = owner.get("childIds", ())
    pending = list(owner_children) if isinstance(owner_children, list | tuple) else []
    found: list[str] = []
    visited: set[str] = set()
    while pending and len(visited) < 16:
        node_id = str(pending.pop())
        if node_id in visited:
            continue
        visited.add(node_id)
        node = records.get(node_id)
        if node is None:
            continue
        value = node.get("name")
        text = value.get("value") if isinstance(value, dict) else value
        if isinstance(text, str) and text.strip():
            found.append(text.strip())
        children = node.get("childIds")
        if isinstance(children, list):
            pending.extend(children)
    unique = tuple(dict.fromkeys(found))
    if len(unique) != 1 or re.fullmatch(r"[+-]?\d+(?:\.\d+)?", unique[0]) is None:
        return None
    return unique[0]


def _numeric_bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _binding_pairs(
    node: CanonicalBrowserControl,
    target_id: str,
    ordinal: int,
    observation_id: str,
    revision: str,
    page_identity: str,
    episode_identity: str,
    *,
    drag_destinations: tuple[tuple[str, CanonicalBrowserControl], ...] = (),
    execution_allowed: bool = True,
):
    if not node.executable or not execution_allowed:
        return ()
    options = node.private_options
    result = []
    for offer_index, offer in enumerate(node.executable_offers):
        translator = BROWSERGYM_INTERACTION_CAPABILITIES.resolve_primitive(
            offer.primitive_action
        )
        semantic = translator.semantic_action
        if semantic == "drag_to" and not drag_destinations:
            continue
        if semantic == "select_option" and len(options) > MAX_OPTION_DOMAIN_ITEMS:
            continue
        current_value_schema = (
            {"type": "string", "enum": [label for label, _ in options]}
            if semantic == "select_option"
            else None
        )
        schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(
            semantic,
            current_value_schema=current_value_schema,
        )
        binding_id = f"binding:{observation_id}:{ordinal}:{offer_index}:{semantic}"
        public = ActionBinding(
            binding_id,
            observation_id,
            observation_id,
            revision,
            node.public_fingerprint,
            target_id,
            target_id,
            "browsergym",
            "browsergym",
            semantic,
            translator.primitive_action,
            "local_reversible",
            ("external_ui_interaction",),
            schema,
            {},
            observation_barrier=True,
            risk=ActionRisk.LOW,
            destination_required=semantic == "drag_to",
            eligible_destination_ids=tuple(
                destination_id for destination_id, _destination in drag_destinations
            ) if semantic == "drag_to" else (),
            verification_family=(
                VerificationFamily.SEMANTIC.value
                if semantic == "press_key"
                else ""
            ),
        )
        runtime: BrowserGymPrivateBinding
        if semantic == "drag_to":
            runtime = BrowserGymDragBinding(
                binding_id,
                observation_id,
                revision,
                page_identity,
                episode_identity,
                node.private_bid,
                target_id,
                translator.primitive_action,
                node,
                tuple(
                    BrowserGymDragDestination(
                        destination_id,
                        destination.private_bid,
                        destination,
                    )
                    for destination_id, destination in drag_destinations
                ),
            )
        else:
            runtime = BrowserGymElementBinding(
                binding_id,
                observation_id,
                revision,
                page_identity,
                episode_identity,
                node.private_bid,
                target_id,
                translator.primitive_action,
                node,
            )
        result.append((public, runtime))
    return tuple(result)


def _why_not_eligible(
    node: CanonicalBrowserControl,
    execution_allowed: bool,
    drag_destinations: tuple[tuple[str, CanonicalBrowserControl], ...],
) -> tuple[str, ...]:
    if not node.role_spec.executable:
        return ()
    if node.executable and execution_allowed:
        drag_offers = tuple(offer for offer in node.executable_offers if offer.semantic_action == "drag_to")
        if not drag_offers or drag_destinations:
            return ()
    reasons: list[str] = []
    if not execution_allowed:
        reasons.append("execution_suppressed_tab_panel_container")
    availability = dict(node.availability.as_tuple())
    for offer in node.role_spec.offers:
        for requirement in offer.execution_requirements:
            state = _requirement_state(requirement, availability)
            if state:
                reasons.append(state)
        if offer.semantic_action == "select_option" and not node.private_options:
            reasons.append("select_option_domain_unavailable")
        if offer.semantic_action == "drag_to" and not drag_destinations:
            reasons.append("drag_destination_unavailable")
    return tuple(dict.fromkeys(reasons))[:8] or ("no_executable_offer",)


def _requirement_state(requirement: str, availability: dict[str, bool | None]) -> str:
    if requirement == "attached":
        return _availability_reason("attached", availability.get("attached"), expected=True)
    if requirement == "visible":
        return _availability_reason("visible", availability.get("visible"), expected=True)
    if requirement == "enabled":
        return _availability_reason("enabled", availability.get("enabled"), expected=True)
    if requirement == "not_readonly":
        return _availability_reason("readonly", availability.get("readonly"), expected=False)
    if requirement == "editable":
        return _availability_reason("editable", availability.get("editable"), expected=True)
    if requirement == "focusable":
        return _availability_reason("focusable", availability.get("focusable"), expected=True)
    return f"availability.{requirement}_unsupported"


def _availability_reason(field: str, actual: bool | None, *, expected: bool) -> str:
    if actual is expected:
        return ""
    suffix = "unknown" if actual is None else f"{str(actual).lower()}"
    return f"availability.{field}_{suffix}"


def _eligibility_diagnostics(
    targets: list[SemanticTarget],
    bindings: list[ActionBinding],
) -> tuple[dict[str, object], ...]:
    actionable = {binding.target_id for binding in bindings}
    diagnostics = []
    for target in targets:
        reasons = target.state.get("action.why_not_eligible")
        if target.target_id in actionable or not isinstance(reasons, tuple | list) or not reasons:
            continue
        diagnostics.append({
            "target_id": target.target_id,
            "role": target.role,
            "label": target.label,
            "why_not_eligible": tuple(str(item) for item in reasons),
        })
        if len(diagnostics) >= 128:
            break
    return tuple(diagnostics)


def _drag_destinations(
    source: CanonicalBrowserControl,
    controls: list[CanonicalBrowserControl],
    target_ids: dict[str, str],
) -> tuple[tuple[str, CanonicalBrowserControl], ...]:
    """Return only explicit current endpoints in the source's private gesture group."""

    if source.role != "draggable" or not source.private_gesture_group:
        return ()
    same_group = tuple(
        candidate
        for candidate in controls
        if candidate.private_bid != source.private_bid
        and candidate.private_gesture_group == source.private_gesture_group
        and candidate.private_node_id in target_ids
        and candidate.availability.attached is True
        and candidate.availability.visible is True
        and candidate.availability.enabled is True
    )
    explicit = tuple(candidate for candidate in same_group if candidate.role == "drop_target")
    if explicit:
        candidates = explicit
    elif source.private_gesture_kind in {"move", "sort"}:
        candidates = tuple(candidate for candidate in same_group if candidate.role == "draggable")
    else:
        candidates = ()
    return tuple(
        (target_ids[candidate.private_node_id], candidate)
        for candidate in candidates
    )


def _is_tab_panel_container(
    node: CanonicalBrowserControl,
    controls_by_node_id: dict[str, CanonicalBrowserControl],
) -> bool:
    """Normalize AX tab-panels without granting or inferring task semantics."""

    return node.role == "tab" and _owns_form_control(node, controls_by_node_id)


def _owns_form_control(
    node: CanonicalBrowserControl,
    controls_by_node_id: dict[str, CanonicalBrowserControl],
) -> bool:
    pending = list(node.private_child_ids)
    visited: set[str] = set()
    while pending:
        child_id = pending.pop()
        if child_id in visited:
            continue
        visited.add(child_id)
        child = controls_by_node_id.get(child_id)
        if child is None:
            continue
        if child.role in {
            "button", "checkbox", "combobox", "listbox", "radio", "searchbox", "textbox",
        }:
            return True
        pending.extend(child.private_child_ids)
    return False


def _screenshot_media(
    capture_frame: BrowserGymCaptureFrame | None,
    observation_id: str,
    grounding_regions: tuple[ObservationGroundingRegion, ...],
) -> tuple[ObservationMedia, ...]:
    if capture_frame is None:
        return ()
    return (
        ObservationMedia(
            "screenshot",
            "screenshot",
            "image/png",
            capture_frame.image_bytes,
            grounding_regions,
            capture_group_id=capture_frame.acquisition_root_id or observation_id,
            variant=ObservationMediaVariant.RAW,
            dimensions=(capture_frame.image_width, capture_frame.image_height),
            coordinate_space_id="browsergym:viewport_pixels",
        ),
    )


def _screenshot_grounding_regions(
    raw: dict[str, object],
    controls: tuple[CanonicalBrowserControl, ...],
    target_ids: dict[str, str],
) -> tuple[ObservationGroundingRegion, ...]:
    """Ground only controls that the current viewport screenshot contains."""

    width, height = _viewport_dimensions(raw)
    executable: list[ObservationGroundingRegion] = []
    contextual: list[ObservationGroundingRegion] = []
    for control in controls:
        bbox = _clip_to_viewport(control.private_bbox, width, height)
        if bbox is None:
            continue
        region = ObservationGroundingRegion(
            target_ids[control.private_node_id],
            bbox,
            coordinate_space_id="browsergym:viewport_pixels",
        )
        (executable if control.executable else contextual).append(region)
    return tuple((*executable, *contextual)[:MAX_OBSERVATION_GROUNDING_REGIONS])


def _clip_to_viewport(
    bbox: tuple[int, int, int, int] | None,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    if bbox is None:
        return None
    x, y, box_width, box_height = bbox
    right = min(width, x + box_width)
    bottom = min(height, y + box_height)
    if x >= width or y >= height or right <= x or bottom <= y:
        return None
    return x, y, right - x, bottom - y

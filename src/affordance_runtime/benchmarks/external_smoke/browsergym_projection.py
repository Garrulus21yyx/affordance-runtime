"""Bounded structural BrowserGym observation projection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from affordance_runtime.benchmarks.external_smoke.browsergym_binding import (
    BrowserGymElementBinding,
    semantic_fingerprint,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    MECHANICAL_EVIDENCE_KEY,
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.world import (
    ActionBinding,
    ActionRisk,
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)

MAX_TARGETS = 64
MAX_FACTS = 128
MAX_FACTS_PER_TARGET = 8
MAX_SELECT_OPTIONS = 16
_ROLE_ACTION = {
    "button": ("activate", "click"),
    "link": ("activate", "click"),
    "textbox": ("fill", "fill"),
    "searchbox": ("fill", "fill"),
    "combobox": ("select", "select_option"),
    "listbox": ("select", "select_option"),
}
_STATE_NAMES = frozenset({"checked", "disabled", "expanded", "required", "selected"})


@dataclass(frozen=True)
class BrowserGymProjection:
    world: WorldObservation
    private_bindings: tuple[BrowserGymElementBinding, ...]
    target_count_total: int
    fact_count_total: int


@dataclass(frozen=True)
class _ProjectedNode:
    bid: str
    role: str
    label: str
    state: dict[str, object]
    options: tuple[tuple[str, str], ...]


def project_browsergym_observation(
    raw: dict[str, object],
    *,
    observation_id: str,
    source_revision: str,
    page_identity: str,
    episode_identity: str,
    verifier: BrowserGymVerifierSnapshot,
) -> BrowserGymProjection:
    candidates = _candidates(raw)
    projected = candidates[:MAX_TARGETS]
    targets: list[SemanticTarget] = []
    facts: list[StateFact] = []
    bindings: list[ActionBinding] = []
    private: list[BrowserGymElementBinding] = []
    fact_total = 0
    for ordinal, node in enumerate(projected):
        target_id = _target_id(node.role, node.label, ordinal)
        state = node.state
        target = SemanticTarget(target_id, node.role, node.label, state)
        targets.append(target)
        node_facts = tuple(state.items())
        fact_total += len(node_facts)
        for key, value in node_facts[:MAX_FACTS_PER_TARGET]:
            if len(facts) >= MAX_FACTS:
                break
            facts.append(StateFact(f"{observation_id}:{target_id}:{key}", target_id, key, value, observation_id))
        public, runtime = _binding_pair(
            node, target_id, ordinal, observation_id, source_revision, page_identity, episode_identity,
        )
        if public is not None and runtime is not None:
            bindings.append(public)
            private.append(runtime)
    truncated = len(candidates) > len(projected) or fact_total > len(facts)
    coverage = CoverageState.TRUNCATED if truncated else CoverageState.COMPLETE
    artifacts = {}
    if verifier.evidence_ref:
        artifacts[MECHANICAL_EVIDENCE_KEY] = {"public_summary": ""}
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
    )
    world = WorldObservation(
        observation_id,
        tuple(targets),
        tuple(facts),
        tuple(bindings),
        {"browsergym": coverage},
        sources=(source,),
    )
    return BrowserGymProjection(world, tuple(private), len(candidates), fact_total)


def _candidates(raw: dict[str, object]) -> list[_ProjectedNode]:
    tree = raw.get("axtree_object")
    nodes = tree.get("nodes", ()) if isinstance(tree, dict) else ()
    extras = raw.get("extra_element_properties")
    extras = extras if isinstance(extras, dict) else {}
    options = _options(nodes)
    result: list[_ProjectedNode] = []
    seen: set[tuple[str, str]] = set()
    for value in nodes if isinstance(nodes, list) else ():
        if not isinstance(value, dict) or value.get("ignored") is True:
            continue
        role = _typed_value(value.get("role"))
        bid = value.get("browsergym_id")
        if role not in _ROLE_ACTION or not isinstance(bid, str) or not bid:
            continue
        if (bid, role) in seen or not _visible(extras.get(bid)):
            continue
        seen.add((bid, role))
        label = _typed_value(value.get("name"))[:240]
        state = _state(value)
        option_values = options if role in {"combobox", "listbox"} else ()
        if option_values:
            state["option_count"] = len(option_values)
        result.append(_ProjectedNode(bid, role, label, state, option_values))
    return result


def _binding_pair(node, target_id, ordinal, observation_id, revision, page_identity, episode_identity):
    semantic, primitive = _ROLE_ACTION[node.role]
    options = node.options
    if semantic == "select" and (not options or len(options) > MAX_SELECT_OPTIONS):
        return None, None
    binding_id = f"binding:{observation_id}:{ordinal}:{semantic}"
    schema: dict[str, object] = {"type": "object", "properties": {}, "additionalProperties": False}
    if semantic in {"fill", "select"}:
        value_schema: dict[str, object] = {"type": "string"}
        if semantic == "select":
            value_schema["enum"] = [label for label, _ in options]
        schema = {
            "type": "object", "properties": {"value": value_schema},
            "required": ["value"], "additionalProperties": False,
        }
    fingerprint = semantic_fingerprint(node.role, node.label, node.state)
    public = ActionBinding(
        binding_id, observation_id, observation_id, revision, fingerprint,
        target_id, target_id, "browsergym", "browsergym", semantic, primitive,
        "local_reversible", ("external_ui_interaction",), schema, {},
        observation_barrier=True, risk=ActionRisk.LOW,
    )
    runtime = BrowserGymElementBinding(
        binding_id, observation_id, revision, page_identity, episode_identity,
        node.bid, target_id, primitive, node.role, node.label,
        fingerprint, tuple(node.state), options,
    )
    return public, runtime


def _options(nodes: object) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in nodes if isinstance(nodes, list) else ():
        if not isinstance(item, dict) or _typed_value(item.get("role")) != "option":
            continue
        label = _typed_value(item.get("name"))[:240]
        bid = item.get("browsergym_id")
        if not label or label in seen or not isinstance(bid, str):
            continue
        seen.add(label)
        values.append((label, label))
    return tuple(values)


def _state(node: dict[str, object]) -> dict[str, object]:
    state: dict[str, object] = {}
    value = _typed_value(node.get("value"))
    if value:
        state["value"] = value[:240]
    properties = node.get("properties")
    for item in properties if isinstance(properties, list) else ():
        if not isinstance(item, dict) or item.get("name") not in _STATE_NAMES:
            continue
        state[str(item["name"])] = _raw_typed_value(item.get("value"))
    return state


def _typed_value(value: object) -> str:
    raw = _raw_typed_value(value)
    return raw if isinstance(raw, str) else ""


def _raw_typed_value(value: object) -> object:
    return value.get("value", "") if isinstance(value, dict) else ""


def _visible(value: object) -> bool:
    return not isinstance(value, dict) or value.get("visibility", 1) not in {0, 0.0}


def _target_id(role: str, label: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{role}\0{label}\0{ordinal}".encode()).hexdigest()[:16]
    return f"target:{digest}"

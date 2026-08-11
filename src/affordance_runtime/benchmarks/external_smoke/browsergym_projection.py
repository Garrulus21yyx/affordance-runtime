"""Bounded structural BrowserGym observation projection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from affordance_runtime.benchmarks.external_smoke.browsergym_binding import (
    BrowserGymElementBinding,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    BrowserGymSemanticAnalysis,
    CanonicalBrowserControl,
    analyze_browsergym_semantics,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    MECHANICAL_EVIDENCE_KEY,
    MECHANICAL_STATUS_EVIDENCE_KEY,
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.world import (
    ActionBinding,
    ActionRisk,
    CoverageState,
    ObservationSourceProfile,
    SemanticInventorySummary,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)

MAX_TARGETS = 64
MAX_FACTS = 128
MAX_FACTS_PER_TARGET = 8
MAX_SELECT_OPTIONS = 16


@dataclass(frozen=True)
class BrowserGymProjection:
    world: WorldObservation
    private_bindings: tuple[BrowserGymElementBinding, ...]
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
    verifier: BrowserGymVerifierSnapshot,
) -> BrowserGymProjection:
    analysis = analyze_browsergym_semantics(raw)
    candidates = list(analysis.controls)
    projected = candidates[:MAX_TARGETS]
    targets: list[SemanticTarget] = []
    facts: list[StateFact] = []
    bindings: list[ActionBinding] = []
    private: list[BrowserGymElementBinding] = []
    fact_total = 0
    for ordinal, node in enumerate(projected):
        target_id = _target_id(node.role, node.accessible_name, ordinal)
        state = dict(node.public_state)
        target = SemanticTarget(target_id, node.role, node.accessible_name, state)
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
    for evidence_ref in verifier.evidence_refs:
        key = evidence_ref.rsplit(":", 1)[-1]
        if key in {MECHANICAL_EVIDENCE_KEY, MECHANICAL_STATUS_EVIDENCE_KEY}:
            artifacts[key] = {"public_summary": ""}
    actionable_target_count = len({binding.target_id for binding in bindings})
    projected_target_count = len(targets)
    recognized_target_count = analysis.inventory.recognized_target_count
    inventory = SemanticInventorySummary.assessed(
        analysis.inventory.profile_id,
        recognized_target_count=recognized_target_count,
        projected_target_count=projected_target_count,
        actionable_target_count=actionable_target_count,
        non_executable_target_count=projected_target_count - actionable_target_count,
        omitted_target_count=recognized_target_count - projected_target_count,
        informational_target_count=0,
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
    )
    world = WorldObservation(
        observation_id,
        tuple(targets),
        tuple(facts),
        tuple(bindings),
        {"browsergym": coverage},
        sources=(source,),
    )
    return BrowserGymProjection(
        world, tuple(private), len(candidates), fact_total, analysis,
    )


def _binding_pair(
    node: CanonicalBrowserControl,
    target_id: str,
    ordinal: int,
    observation_id: str,
    revision: str,
    page_identity: str,
    episode_identity: str,
):
    spec = node.role_spec
    semantic, primitive = spec.semantic_action, spec.primitive
    if not node.executable:
        return None, None
    options = node.private_options
    if semantic == "select" and len(options) > MAX_SELECT_OPTIONS:
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
    public = ActionBinding(
        binding_id, observation_id, observation_id, revision, node.public_fingerprint,
        target_id, target_id, "browsergym", "browsergym", semantic, primitive,
        "local_reversible", ("external_ui_interaction",), schema, {},
        observation_barrier=True, risk=ActionRisk.LOW,
    )
    runtime = BrowserGymElementBinding(
        binding_id, observation_id, revision, page_identity, episode_identity,
        node.private_bid, target_id, primitive, node,
    )
    return public, runtime


def _target_id(role: str, label: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{role}\0{label}\0{ordinal}".encode()).hexdigest()[:16]
    return f"target:{digest}"

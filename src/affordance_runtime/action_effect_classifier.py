"""Harness-owned, conservative Runtime effect and risk classification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from affordance_runtime.effect_authority_contracts import (
    EffectClass,
    Externality,
    Reversibility,
    RuntimeEffectSignature,
    RuntimeRiskTier,
    RuntimeRiskVector,
    externality_rank,
    reversibility_rank,
)
from affordance_runtime.grounding import (
    ApiGroundingPayload,
    GroundingCandidate,
    GroundingSource,
    WoTGroundingPayload,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.unified_observation import ConflictStatus, UnifiedObservation
from affordance_runtime.verification.contracts import AssuranceLevel

_INTERACTION_POLICY = {
    "focus": (EffectClass.INTERACTION_ONLY, Externality.LOCAL, Reversibility.REVERSIBLE),
    "hover": (EffectClass.INTERACTION_ONLY, Externality.LOCAL, Reversibility.REVERSIBLE),
    "scroll": (EffectClass.INTERACTION_ONLY, Externality.LOCAL, Reversibility.REVERSIBLE),
    "wait": (EffectClass.INTERACTION_ONLY, Externality.LOCAL, Reversibility.REVERSIBLE),
}
_STRUCTURED_ACTION_POLICY = {
    "fill": (EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE, "field.set@v1"),
    "type": (EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE, "field.set@v1"),
    "type_text": (EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE, "field.set@v1"),
    "select": (EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE, "field.set@v1"),
    "select_option": (EffectClass.UPDATE, Externality.LOCAL, Reversibility.REVERSIBLE, "field.set@v1"),
    "navigate": (EffectClass.NAVIGATE, Externality.SAME_ORIGIN, Reversibility.REVERSIBLE, "navigation.navigate@v1"),
}
_WOT_OPERATION_POLICY = {
    "readproperty": (EffectClass.READ, Externality.PHYSICAL_WORLD, Reversibility.REVERSIBLE),
    "writeproperty": (EffectClass.UPDATE, Externality.PHYSICAL_WORLD, Reversibility.UNKNOWN),
    "invokeaction": (EffectClass.INVOKE, Externality.PHYSICAL_WORLD, Reversibility.UNKNOWN),
}


def classify_action(
    observation: UnifiedObservation,
    *,
    target_id: str,
    action_kind: str,
    parameters: object,
    destination_id: str = "",
    candidate: GroundingCandidate | None = None,
    destination_candidate: GroundingCandidate | None = None,
) -> RuntimeEffectSignature:
    _validate_candidate_identity(candidate, target_id, "source")
    _validate_candidate_identity(destination_candidate, destination_id, "destination")
    target = next((item for item in observation.targets if item.target_id == target_id), None)
    destination = next((item for item in observation.targets if item.target_id == destination_id), None)
    selected = candidate
    normalized_action = action_kind.casefold()
    operation_ref: str | None = None
    resource_ref: str | None = target_id if target is not None else None
    effect_class: EffectClass | None = None
    externality: Externality | None = None
    reversibility: Reversibility | None = None
    assurance = AssuranceLevel.WEAK
    assertion_refs: tuple[str, ...] = ()
    resource_sensitivity = RuntimeRiskTier.LOW
    asserted_risk = RuntimeRiskTier.LOW

    if target is not None:
        assertion_refs = tuple(getattr(target, "source_assertion_refs", getattr(target, "source_refs", ())))
        asserted_risk = _higher_risk(asserted_risk, _asserted_risk(target))
        operation_ref = _optional_text(getattr(target, "operation_ref", ""))
        effect_class = _optional_enum(EffectClass, getattr(target, "effect_class", ""))
        externality = _optional_enum(Externality, getattr(target, "externality", ""))
        reversibility = _optional_enum(Reversibility, getattr(target, "reversibility", ""))
        assurance = _optional_enum(AssuranceLevel, getattr(target, "source_assurance", "")) or assurance
        resource_sensitivity = (
            _optional_enum(RuntimeRiskTier, getattr(target, "resource_sensitivity", "")) or resource_sensitivity
        )
        support = next(
            (item for item in getattr(target, "action_support", ()) if item.action_kind == normalized_action),
            None,
        )
        if support is not None:
            asserted_risk = _higher_risk(asserted_risk, _asserted_risk(support))
        if support is not None and selected is None:
            resource_ref = _optional_text(support.resource_ref) or resource_ref
            operation_ref = operation_ref or _optional_text(support.operation_ref)
            effect_class = effect_class or _optional_enum(EffectClass, support.effect_class)
            externality = externality or _optional_enum(Externality, support.externality)
            reversibility = reversibility or _optional_enum(Reversibility, support.reversibility)
            resource_sensitivity = _optional_enum(RuntimeRiskTier, support.resource_sensitivity) or resource_sensitivity
            assurance = _optional_enum(AssuranceLevel, support.source_assurance) or assurance

    if selected is not None:
        assertion_refs = _merge_refs(assertion_refs, selected.evidence_refs)
        asserted_risk = _higher_risk(asserted_risk, _asserted_risk(selected))
        resource_ref = _candidate_resource_ref(selected) or resource_ref
        operation_ref = operation_ref or _optional_text(selected.operation_ref) or _candidate_operation(selected)
        effect_class = effect_class or _optional_enum(EffectClass, selected.effect_class)
        externality = externality or _optional_enum(Externality, selected.externality)
        reversibility = reversibility or _optional_enum(Reversibility, selected.reversibility)
        resource_sensitivity = _optional_enum(RuntimeRiskTier, selected.resource_sensitivity) or resource_sensitivity
        asserted_assurance = _optional_enum(AssuranceLevel, selected.authority_source_assurance)
        if asserted_assurance is not None:
            assurance = asserted_assurance
        elif selected.source in {GroundingSource.API, GroundingSource.WOT, GroundingSource.DEVICE}:
            assurance = AssuranceLevel.STRUCTURAL
        elif selected.source in {GroundingSource.DOM, GroundingSource.ACCESSIBILITY, GroundingSource.SVG}:
            assurance = max(assurance, AssuranceLevel.STRUCTURAL, key=_assurance_rank)
        if isinstance(selected.payload, WoTGroundingPayload):
            typed = _WOT_OPERATION_POLICY.get(selected.payload.operation.casefold())
            if typed:
                effect_class = effect_class or typed[0]
                externality = externality or typed[1]
                reversibility = reversibility or typed[2]

    if destination is not None:
        assertion_refs = _merge_refs(
            assertion_refs,
            tuple(getattr(destination, "source_assertion_refs", getattr(destination, "source_refs", ()))),
        )
        asserted_risk = _higher_risk(asserted_risk, _asserted_risk(destination))
        destination_support = _action_support(destination, normalized_action, destination=True)
        if destination_support is not None:
            asserted_risk = _higher_risk(asserted_risk, _asserted_risk(destination_support))
        resource_sensitivity = _higher_risk(
            resource_sensitivity,
            _optional_enum(RuntimeRiskTier, getattr(destination, "resource_sensitivity", "")),
        )
        if destination_support is not None:
            resource_sensitivity = _higher_risk(
                resource_sensitivity,
                _optional_enum(RuntimeRiskTier, destination_support.resource_sensitivity),
            )
        destination_assurance = _optional_enum(AssuranceLevel, getattr(destination, "source_assurance", ""))
        if destination_support is not None:
            destination_assurance = _weaker_assurance(
                destination_assurance,
                _optional_enum(AssuranceLevel, destination_support.source_assurance),
            )
        if destination_assurance is not None:
            assurance = min(assurance, destination_assurance, key=_assurance_rank)
        externality = _more_external(
            externality,
            _optional_enum(Externality, getattr(destination, "externality", "")),
        )
        if destination_support is not None:
            externality = _more_external(
                externality,
                _optional_enum(Externality, destination_support.externality),
            )
        reversibility = _less_reversible(
            reversibility,
            _optional_enum(Reversibility, getattr(destination, "reversibility", "")),
        )
        if destination_support is not None:
            reversibility = _less_reversible(
                reversibility,
                _optional_enum(Reversibility, destination_support.reversibility),
            )
        effect_class, operation_ref = _reduce_endpoint_effect_operation(
            effect_class,
            operation_ref,
            _optional_enum(
                EffectClass,
                (
                    destination_support.effect_class
                    if destination_support is not None
                    else getattr(destination, "effect_class", "")
                ),
            ),
            _optional_text(
                destination_support.operation_ref
                if destination_support is not None
                else getattr(destination, "operation_ref", "")
            ),
        )

    if destination_candidate is not None:
        assertion_refs = _merge_refs(assertion_refs, destination_candidate.evidence_refs)
        asserted_risk = _higher_risk(asserted_risk, _asserted_risk(destination_candidate))
        resource_sensitivity = _higher_risk(
            resource_sensitivity,
            _optional_enum(RuntimeRiskTier, destination_candidate.resource_sensitivity),
        )
        destination_assurance = _candidate_assurance(destination_candidate)
        if destination_assurance is not None:
            assurance = min(assurance, destination_assurance, key=_assurance_rank)
        externality = _more_external(
            externality,
            _optional_enum(Externality, destination_candidate.externality),
        )
        reversibility = _less_reversible(
            reversibility,
            _optional_enum(Reversibility, destination_candidate.reversibility),
        )
        effect_class, operation_ref = _reduce_endpoint_effect_operation(
            effect_class,
            operation_ref,
            _optional_enum(EffectClass, destination_candidate.effect_class),
            _optional_text(destination_candidate.operation_ref) or _candidate_operation(destination_candidate),
        )

    interaction = _INTERACTION_POLICY.get(normalized_action)
    structured = _STRUCTURED_ACTION_POLICY.get(normalized_action)
    if interaction:
        effect_class = effect_class or interaction[0]
        externality = externality or interaction[1]
        reversibility = reversibility or interaction[2]
        operation_ref = operation_ref or f"interaction.{normalized_action}@v1"
        assurance = max(assurance, AssuranceLevel.STRUCTURAL, key=_assurance_rank)
    elif structured:
        effect_class = effect_class or structured[0]
        externality = externality or structured[1]
        reversibility = reversibility or structured[2]
        operation_ref = operation_ref or structured[3]

    conflict = _more_severe_conflict(_target_conflict(target), _target_conflict(destination))
    risk_vector = _risk_vector(
        effect_class=effect_class,
        externality=externality,
        reversibility=reversibility,
        resource_sensitivity=resource_sensitivity,
        asserted_source=asserted_risk,
        parameters=parameters,
        assurance=assurance,
        conflict_status=conflict,
        capability_asserted=bool(getattr(selected, "operation_ref", "")) if selected else False,
    )
    return RuntimeEffectSignature(
        observation_ref=observation.epoch_id,
        action_kind=normalized_action,
        effect_class=effect_class,
        target_ref=target_id if target is not None else "",
        resource_ref=resource_ref,
        destination_ref=destination_id if destination is not None else None,
        operation_ref=operation_ref,
        parameter_values=parameters,
        externality=externality,
        reversibility=reversibility,
        assurance=assurance,
        conflict_status=conflict or ConflictStatus.INCONCLUSIVE.value,
        coverage_complete=_coverage_complete(
            observation,
            target,
            destination,
            candidate,
            destination_candidate,
            action_kind=normalized_action,
            destination_required=bool(destination_id),
        ),
        candidate_binding_digest=_binding_digest(selected, destination_candidate, target_id, destination_id),
        source_refs=assertion_refs,
        backend_operation=operation_ref or "",
        risk_vector=risk_vector,
    )


def _risk_vector(
    *,
    effect_class: EffectClass | None,
    externality: Externality | None,
    reversibility: Reversibility | None,
    resource_sensitivity: RuntimeRiskTier,
    asserted_source: RuntimeRiskTier,
    parameters: object,
    assurance: AssuranceLevel,
    conflict_status: str,
    capability_asserted: bool,
) -> RuntimeRiskVector:
    effect_risk = {
        EffectClass.READ: RuntimeRiskTier.LOW,
        EffectClass.INTERACTION_ONLY: RuntimeRiskTier.LOW,
        EffectClass.NAVIGATE: RuntimeRiskTier.MODERATE,
        EffectClass.CREATE: RuntimeRiskTier.MODERATE,
        EffectClass.UPDATE: RuntimeRiskTier.MODERATE,
        EffectClass.SEND: RuntimeRiskTier.HIGH,
        EffectClass.SHARE: RuntimeRiskTier.HIGH,
        EffectClass.PAY: RuntimeRiskTier.CRITICAL,
        EffectClass.DELETE: RuntimeRiskTier.CRITICAL,
        EffectClass.INVOKE: RuntimeRiskTier.HIGH,
        EffectClass.EXECUTE: RuntimeRiskTier.CRITICAL,
        EffectClass.UNKNOWN: RuntimeRiskTier.CRITICAL,
        None: RuntimeRiskTier.CRITICAL,
    }[effect_class]
    externality_risk = {
        Externality.LOCAL: RuntimeRiskTier.LOW,
        Externality.SAME_ORIGIN: RuntimeRiskTier.MODERATE,
        Externality.CROSS_ORIGIN: RuntimeRiskTier.HIGH,
        Externality.EXTERNAL_SYSTEM: RuntimeRiskTier.HIGH,
        Externality.PHYSICAL_WORLD: RuntimeRiskTier.CRITICAL,
        Externality.UNKNOWN: RuntimeRiskTier.CRITICAL,
        None: RuntimeRiskTier.CRITICAL,
    }[externality]
    reversibility_risk = {
        Reversibility.REVERSIBLE: RuntimeRiskTier.LOW,
        Reversibility.COMPENSATABLE: RuntimeRiskTier.MODERATE,
        Reversibility.IRREVERSIBLE: RuntimeRiskTier.CRITICAL,
        Reversibility.UNKNOWN: RuntimeRiskTier.CRITICAL,
        None: RuntimeRiskTier.CRITICAL,
    }[reversibility]
    material = RuntimeRiskTier.LOW
    if isinstance(parameters, dict) or hasattr(parameters, "items"):
        slots = {str(key).casefold() for key, _ in parameters.items()}
        if slots & {"recipient", "payee", "amount", "currency", "principal", "permission"}:
            material = RuntimeRiskTier.HIGH
    return RuntimeRiskVector(
        effect_class=effect_risk,
        externality=externality_risk,
        reversibility=reversibility_risk,
        resource_sensitivity=resource_sensitivity,
        asserted_source=asserted_source,
        material_parameters=material,
        capability=RuntimeRiskTier.MODERATE if capability_asserted else RuntimeRiskTier.LOW,
        source_uncertainty=(
            RuntimeRiskTier.LOW
            if assurance == AssuranceLevel.AUTHORITATIVE
            else RuntimeRiskTier.MODERATE
            if assurance == AssuranceLevel.STRUCTURAL
            else RuntimeRiskTier.HIGH
        ),
        conflict=(
            RuntimeRiskTier.CRITICAL
            if conflict_status in {"material_conflict", "inconclusive"}
            else RuntimeRiskTier.LOW
        ),
    )


def _candidate_operation(candidate: GroundingCandidate) -> str | None:
    if isinstance(candidate.payload, ApiGroundingPayload):
        return candidate.payload.operation_id or None
    if isinstance(candidate.payload, WoTGroundingPayload):
        return f"wot.{candidate.payload.operation}@v1"
    return None


def _candidate_resource_ref(candidate: GroundingCandidate) -> str | None:
    backend_handle = _optional_text(getattr(candidate.payload, "backend_handle", ""))
    return backend_handle or candidate.semantic_target_id or None


def _asserted_risk(value: object) -> RuntimeRiskTier | None:
    if not bool(getattr(value, "risk_asserted", False)):
        return None
    raw = getattr(value, "risk", "")
    text = raw.value if hasattr(raw, "value") else str(raw)
    return {
        "low": RuntimeRiskTier.LOW,
        "medium": RuntimeRiskTier.MODERATE,
        "moderate": RuntimeRiskTier.MODERATE,
        "high": RuntimeRiskTier.HIGH,
        "irreversible": RuntimeRiskTier.CRITICAL,
        "critical": RuntimeRiskTier.CRITICAL,
    }.get(text.casefold())


def _higher_risk(current: RuntimeRiskTier, candidate: RuntimeRiskTier | None) -> RuntimeRiskTier:
    if candidate is None:
        return current
    rank = {
        RuntimeRiskTier.LOW: 0,
        RuntimeRiskTier.MODERATE: 1,
        RuntimeRiskTier.HIGH: 2,
        RuntimeRiskTier.CRITICAL: 3,
    }
    return max((current, candidate), key=rank.__getitem__)


def _candidate_assurance(candidate: GroundingCandidate) -> AssuranceLevel | None:
    asserted = _optional_enum(AssuranceLevel, candidate.authority_source_assurance)
    if asserted is not None:
        return asserted
    if candidate.source in {GroundingSource.API, GroundingSource.WOT, GroundingSource.DEVICE}:
        return AssuranceLevel.STRUCTURAL
    if candidate.source in {GroundingSource.DOM, GroundingSource.ACCESSIBILITY, GroundingSource.SVG}:
        return AssuranceLevel.STRUCTURAL
    return AssuranceLevel.WEAK


def _more_external(current: Externality | None, candidate: Externality | None) -> Externality | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max((current, candidate), key=externality_rank)


def _less_reversible(current: Reversibility | None, candidate: Reversibility | None) -> Reversibility | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max((current, candidate), key=reversibility_rank)


def _weaker_assurance(current: AssuranceLevel | None, candidate: AssuranceLevel | None) -> AssuranceLevel | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return min((current, candidate), key=_assurance_rank)


def _action_support(target: object, action: str, *, destination: bool = False):
    supports = tuple(getattr(target, "action_support", ()))
    exact = next((item for item in supports if item.action_kind == action), None)
    if exact is not None or not destination or action != "drag":
        return exact
    return next((item for item in supports if item.action_kind == "drop"), None)


def _target_conflict(target: object | None) -> str:
    if target is None:
        return ConflictStatus.NO_MATERIAL_CONFLICT.value
    status = getattr(getattr(target, "conflict_status", None), "value", "")
    if status:
        return status
    if getattr(target, "conflict_codes", ()):
        return ConflictStatus.MATERIAL_CONFLICT.value
    return ConflictStatus.NO_MATERIAL_CONFLICT.value


def _more_severe_conflict(current: str, candidate: str) -> str:
    rank = {
        ConflictStatus.RESOLVED.value: 0,
        ConflictStatus.NO_MATERIAL_CONFLICT.value: 0,
        ConflictStatus.INCONCLUSIVE.value: 1,
        ConflictStatus.MATERIAL_CONFLICT.value: 2,
    }
    return max((current, candidate), key=lambda value: rank.get(value, 2))


def _merge_refs(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ref for group in groups for ref in group))


def _validate_candidate_identity(
    candidate: GroundingCandidate | None,
    expected_target_id: str,
    endpoint: str,
) -> None:
    if candidate is not None and candidate.semantic_target_id != expected_target_id:
        raise ValueError(f"{endpoint} candidate semantic identity does not match requested target")


def _reduce_endpoint_effect_operation(
    effect_class: EffectClass | None,
    operation_ref: str | None,
    endpoint_effect: EffectClass | None,
    endpoint_operation: str | None,
) -> tuple[EffectClass | None, str | None]:
    if endpoint_effect is not None and effect_class is not None and endpoint_effect != effect_class:
        effect_class = EffectClass.UNKNOWN
    elif effect_class is None:
        effect_class = endpoint_effect
    if endpoint_operation and operation_ref and endpoint_operation != operation_ref:
        operation_ref = None
    elif operation_ref is None:
        operation_ref = endpoint_operation
    return effect_class, operation_ref


def _coverage_complete(
    observation: UnifiedObservation,
    target: object | None,
    destination: object | None,
    candidate: GroundingCandidate | None,
    destination_candidate: GroundingCandidate | None,
    *,
    action_kind: str,
    destination_required: bool,
) -> bool:
    if target is None or (destination_required and destination is None):
        return False
    if not observation.source_coverage:
        return True
    sources: set[GroundingSource] = set()
    for endpoint_candidate in (candidate, destination_candidate):
        if endpoint_candidate is not None:
            sources.add(endpoint_candidate.source)
    bindings = {item.candidate_id: item for item in observation.bindings}
    for endpoint_index, endpoint in enumerate((target, destination)):
        if endpoint is None:
            continue
        support = _action_support(endpoint, action_kind, destination=endpoint_index == 1)
        support_sources = {
            bindings[candidate_id].source
            for candidate_id in getattr(support, "candidate_ids", ())
            if candidate_id in bindings
        }
        if support_sources:
            sources.update(support_sources)
            continue
        surfaces = getattr(endpoint, "surfaces", ())
        if not surfaces:
            surface = getattr(endpoint, "surface", "")
            try:
                surfaces = (GroundingSource(surface),) if surface else ()
            except ValueError:
                surfaces = ()
        sources.update(item for item in surfaces if isinstance(item, GroundingSource))
    coverage = {item.source: item for item in observation.source_coverage}
    return bool(sources) and all(
        source in coverage
        and coverage[source].completeness.value == "complete"
        and not coverage[source].truncated
        and coverage[source].status.value == "observed"
        for source in sources
    )


def _binding_digest(candidate, destination_candidate, target_id: str, destination_id: str) -> str:
    payload = {
        "target_id": target_id,
        "destination_id": destination_id,
        "candidate": asdict(candidate) if candidate is not None else None,
        "destination_candidate": asdict(destination_candidate) if destination_candidate is not None else None,
    }
    encoded = json.dumps(to_json_compatible(payload), sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _optional_text(value: object) -> str | None:
    text = str(value).strip()
    return text or None


def _optional_enum(enum_type, value):
    if not value:
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _assurance_rank(value: AssuranceLevel) -> int:
    return {AssuranceLevel.WEAK: 0, AssuranceLevel.STRUCTURAL: 1, AssuranceLevel.AUTHORITATIVE: 2}[value]

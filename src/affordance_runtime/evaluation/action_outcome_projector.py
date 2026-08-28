"""Production mechanical action-outcome projection from current public world state."""

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    ParameterContractKind,
    VerificationFamily,
)
from affordance_runtime.agent.context.world_transition import (
    PublicFactChange,
    PublicWorldDelta,
    WorldTransitionProjector,
)
from affordance_runtime.evaluation.contracts import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_records import evidence_source_is_current
from affordance_runtime.execution import ExecutionTransition
from affordance_runtime.world import CoverageState
from affordance_runtime.world.evidence_refs import canonical_artifact_ref, canonical_fact_ref
from affordance_runtime.world.public_semantic_digest import public_subject_semantics_changed
from affordance_runtime.world.source_profile import assurance_satisfies


class ProductionActionOutcomeProjector:
    """Project observable local transitions; never infer task progress."""

    async def evaluate(
        self,
        task,
        before,
        request,
        result,
        after,
        public_world_delta: PublicWorldDelta | None = None,
    ) -> ActionOutcome:
        del task
        public_world_delta = public_world_delta or WorldTransitionProjector().project(before, after)
        definition = INTERACTION_CAPABILITY_REGISTRY.require(request.intent.semantic_action)
        family = request.selection.verification_contract.family
        if (
            result.causal_transition is ExecutionTransition.STABLE_NAVIGATION
            or family is VerificationFamily.NAVIGATION_CONTEXT
        ):
            return _evaluate_navigation_context(before, request, after, public_world_delta)
        if family is not VerificationFamily.VALUE_STATE:
            return _evaluation(request, before, after, public_world_delta=public_world_delta)
        if definition.parameter_contract not in {
            ParameterContractKind.TEXT,
            ParameterContractKind.OPTION_VALUE,
        }:
            return _evaluation(request, before, after, public_world_delta=public_world_delta)
        parameter_name = definition.parameter_names[0]
        requested = request.intent.parameters.get(parameter_name)
        if not isinstance(requested, str):
            return _evaluation(request, before, after, public_world_delta=public_world_delta)
        current = _current_value_evidence(after, request.intent.target_id)
        if current is None:
            return _evaluation(request, before, after, public_world_delta=public_world_delta)
        after_value, evidence_ref = current
        before_value = _single_value(before, request.intent.target_id)
        if after_value == requested:
            postcondition = LocalPostconditionStatus.SATISFIED
        else:
            postcondition = LocalPostconditionStatus.UNSATISFIED
        effect = (
            ObservedChange.UNKNOWN
            if before_value is _MISSING
            else ObservedChange.CHANGED
            if _fact_predicate_changed(
                public_world_delta,
                request.intent.target_id,
                "value",
            )
            else ObservedChange.UNCHANGED
        )
        return _evaluation(
            request,
            before,
            after,
            effect,
            postcondition,
            EvidenceMethod.NATIVE,
            (evidence_ref,),
            public_world_delta=public_world_delta,
        )


_MISSING = object()


def _single_value(observation, target_id: str):
    values = tuple(
        fact.value for fact in observation.facts if fact.subject_id == target_id and fact.predicate == "value"
    )
    return values[0] if len(values) == 1 else _MISSING


def _current_value_evidence(observation, target_id: str) -> tuple[object, str] | None:
    if target_id not in {item.target_id for item in observation.targets}:
        return None
    if any(item.subject_id == target_id and item.predicate == "value" for item in observation.conflicts):
        return None
    index = WorldEvidenceIndex.from_observation(observation)
    records = tuple(
        item
        for item in index.records
        if item.kind == "fact" and item.subject_id == target_id and item.predicate == "value"
    )
    if len(records) != 1:
        return None
    record = records[0]
    source = next(
        (item for item in observation.sources if item.observation_id == record.source_observation_id),
        None,
    )
    if (
        source is None
        or source.coverage != CoverageState.COMPLETE
        or not any(
            item.source_observation_id == source.observation_id and item.coverage == CoverageState.COMPLETE
            for item in observation.source_manifest
        )
        or not evidence_source_is_current(record, observation)
        or not assurance_satisfies(record.source_assurance, "structural")
    ):
        return None
    return record.value, record.evidence_ref


def _evaluation(
    request,
    before,
    after,
    observed_change=ObservedChange.UNKNOWN,
    local_postcondition=LocalPostconditionStatus.UNKNOWN,
    evidence_method=EvidenceMethod.NONE,
    refs=(),
    *,
    public_world_delta: PublicWorldDelta,
) -> ActionOutcome:
    reason = _reason(observed_change, local_postcondition, evidence_method)
    evidence: dict[str, object] = {}
    if observed_change is not ObservedChange.UNKNOWN:
        evidence["observed_change"] = observed_change.value
    if local_postcondition is not LocalPostconditionStatus.UNKNOWN:
        evidence["local_postcondition"] = local_postcondition.value
    if evidence_method is not EvidenceMethod.NONE:
        evidence["evidence_method"] = evidence_method.value
    changes = _fact_change_payloads(public_world_delta, tuple(refs))
    if changes:
        evidence["fact_changes"] = changes
    return ActionOutcome(
        request.request_id,
        before.observation_id,
        after.observation_id,
        observed_change,
        local_postcondition,
        evidence_method,
        reason,
        tuple(refs),
        evidence,
        public_world_delta,
    )


def _reason(effect, postcondition, method) -> str:
    if effect is ObservedChange.UNKNOWN and postcondition is LocalPostconditionStatus.UNKNOWN:
        return "local action outcome is not mechanically resolved"
    return f"local action outcome: effect={effect.value}, postcondition={postcondition.value}, method={method.value}"


def _evaluate_navigation_context(
    before,
    request,
    after,
    public_world_delta: PublicWorldDelta,
) -> ActionOutcome:
    semantic_world_changed = public_world_delta.semantic_changed
    target_changed = semantic_world_changed and public_subject_semantics_changed(
        before,
        after,
        request.intent.target_id,
    )
    navigation_target = next(
        (item for item in after.targets if item.target_id == request.intent.target_id),
        None,
    )
    target_refs = (
        _changed_fact_refs(
            public_world_delta,
            after,
            target_id=request.intent.target_id,
            allow_truncated_source=(
                navigation_target is not None
                and navigation_target.role == "browser_context"
            ),
        )
        if semantic_world_changed
        else ()
    )
    if target_refs:
        fact_changes = _fact_change_payloads(public_world_delta, target_refs)
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED,
            (
                LocalPostconditionStatus.UNKNOWN
                if request.intent.expected_outcome
                else LocalPostconditionStatus.NOT_APPLICABLE
            ),
            EvidenceMethod.STRUCTURAL,
            "public target semantics changed with current structural evidence",
            target_refs,
            {
                "verification_profile": "structural_target_diff_v1",
                "expected_effects": request.selection.semantic_effects,
                "observed_change": ObservedChange.CHANGED.value,
                "target_changed": True,
                "structural_world_changed": True,
                "fact_changes": fact_changes,
            },
            public_world_delta,
        )
    before_digests = _screenshot_digests(before)
    after_digests = _screenshot_digests(after)
    evidence_ref = _screenshot_evidence_ref(after)
    screenshot_available = bool(before_digests and after_digests and evidence_ref is not None)
    screenshot_changed = screenshot_available and before_digests != after_digests
    if (
        semantic_world_changed
        and not screenshot_changed
        and not (screenshot_available and target_changed)
    ):
        structural_refs = _changed_fact_refs(public_world_delta, after)
        if structural_refs:
            fact_changes = _fact_change_payloads(public_world_delta, structural_refs)
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.CHANGED,
                (
                    LocalPostconditionStatus.UNKNOWN
                    if request.intent.expected_outcome
                    else LocalPostconditionStatus.NOT_APPLICABLE
                ),
                EvidenceMethod.STRUCTURAL,
                "public structural World semantics changed after interaction",
                structural_refs,
                {
                    "verification_profile": "structural_world_diff_v2",
                    "expected_effects": request.selection.semantic_effects,
                    "observed_change": ObservedChange.CHANGED.value,
                    "target_changed": target_changed,
                    "structural_world_changed": True,
                    "fact_changes": fact_changes,
                },
                public_world_delta,
            )
    if not screenshot_available:
        return _evaluation(request, before, after, public_world_delta=public_world_delta)
    observed_change = ObservedChange.CHANGED if screenshot_changed or target_changed else ObservedChange.UNCHANGED
    local_postcondition = (
        LocalPostconditionStatus.UNKNOWN if request.intent.expected_outcome else LocalPostconditionStatus.NOT_APPLICABLE
    )
    reason = (
        "public screenshot or target semantics changed after interaction"
        if observed_change is ObservedChange.CHANGED
        else "public screenshot and target semantics did not change after interaction"
    )
    return ActionOutcome(
        request.request_id,
        before.observation_id,
        after.observation_id,
        observed_change,
        local_postcondition,
        EvidenceMethod.VISUAL_DIFF,
        reason,
        (evidence_ref,),
        {
            "verification_profile": "visual_diff_v1",
            "expected_effects": request.selection.semantic_effects,
            "observed_change": observed_change.value,
            "local_postcondition": local_postcondition.value,
            "screenshot_changed": screenshot_changed,
            "target_changed": target_changed,
        },
        public_world_delta,
    )


def _changed_fact_refs(
    public_world_delta: PublicWorldDelta,
    after,
    *,
    target_id: str = "",
    allow_truncated_source: bool = False,
) -> tuple[str, ...]:
    index = WorldEvidenceIndex.from_observation(after)
    changed_refs = {
        canonical_fact_ref(item.after.fact_id)
        for item in public_world_delta.fact_changes
        if item.after is not None and item.predicate != "focused" and (not target_id or item.subject_id == target_id)
    }
    refs = tuple(
        record.evidence_ref
        for record in index.records
        if record.kind == "fact"
        and record.evidence_ref in changed_refs
        and evidence_source_is_current(record, after)
        and assurance_satisfies(record.source_assurance, "structural")
        and _source_coverage_admits_current_fact(
            record.source_observation_id,
            after,
            allow_truncated=allow_truncated_source,
        )
    )
    return tuple(dict.fromkeys(refs))


def _fact_predicate_changed(
    public_world_delta: PublicWorldDelta,
    subject_id: str,
    predicate: str,
) -> bool:
    return any(
        item.subject_id == subject_id and item.predicate == predicate
        for item in public_world_delta.fact_changes
    )


def _fact_change_payloads(
    public_world_delta: PublicWorldDelta,
    evidence_refs: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    selected = set(evidence_refs)
    return tuple(
        _fact_change_payload(item)
        for item in public_world_delta.fact_changes
        if item.after is not None and canonical_fact_ref(item.after.fact_id) in selected
    )


def _fact_change_payload(change: PublicFactChange) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": change.kind.value,
        "subject_id": change.subject_id,
        "predicate": change.predicate,
        "after": change.after.value if change.after is not None else None,
        "before_region_key": change.before_region_key,
        "after_region_key": change.after_region_key,
    }
    if change.before is not None:
        payload["before"] = change.before.value
    return payload


def _source_coverage_admits_current_fact(
    source_observation_id: str,
    observation,
    *,
    allow_truncated: bool,
) -> bool:
    source = next(
        (item for item in observation.sources if item.observation_id == source_observation_id),
        None,
    )
    admitted = (
        {CoverageState.COMPLETE, CoverageState.TRUNCATED}
        if allow_truncated
        else {CoverageState.COMPLETE}
    )
    return bool(
        source is not None
        and source.coverage in admitted
        and any(
            item.source_observation_id == source.observation_id
            and item.coverage in admitted
            for item in observation.source_manifest
        )
    )


def _screenshot_digests(observation) -> tuple[str, ...]:
    return tuple(
        sorted({media.sha256 for source in observation.sources for media in source.media if media.kind == "screenshot"})
    )


def _screenshot_evidence_ref(observation) -> str | None:
    source = next(
        (source for source in observation.sources if "screenshot_semantic_state" in source.artifacts and source.media),
        None,
    )
    return canonical_artifact_ref(source.observation_id, "screenshot_semantic_state") if source is not None else None

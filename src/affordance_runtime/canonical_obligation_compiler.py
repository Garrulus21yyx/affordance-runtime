"""Code-owned, generic canonical obligation construction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from pydantic import Field

from affordance_runtime.immutable import freeze_json
from affordance_runtime.simplified_runtime_contracts import SPATIAL_POINT_CAPABILITY
from affordance_runtime.source_ledger import SourceLedger
from affordance_runtime.task_intake import (
    CompilationIssue,
    EvidenceKind,
    EvidenceRequirement,
    GraphConstructionSource,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    SemanticValueRelation,
    SourcedTaskClaim,
    StrictModel,
    TaskClaimKind,
    TaskInteractionOperationKind,
    TaskInteractionRelationSpec,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
)


class CanonicalEffectInput(StrictModel):
    operation_class: OperationClass
    target: str = Field(min_length=1, max_length=480)
    source_unit_ids: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[EvidenceRequirement, ...] = Field(min_length=1)
    depends_on_effect_indexes: tuple[int, ...] = ()
    terminal: bool = True
    interaction_values: tuple[str, ...] = ()
    captures_observation_value: bool = False
    value_source_effect_index: int | None = None
    interaction_relation: TaskInteractionRelationSpec | None = None
    interaction_capability: str = ""
    interaction_operation: TaskInteractionOperationKind = TaskInteractionOperationKind.AUTO


class CanonicalObligationGraph(StrictModel):
    compiler_version: str
    claims: tuple[SourcedTaskClaim, ...]
    obligations: tuple[TaskObligationSpec, ...]


@dataclass(frozen=True)
class CanonicalProposalGraph:
    """Canonicalized graph plus proposal-local reference diagnostics."""

    graph: CanonicalObligationGraph
    proposal_claim_ids: dict[str, str]
    issues: tuple[CompilationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_claim_ids", freeze_json(self.proposal_claim_ids))


@dataclass(frozen=True)
class CanonicalObligationCompiler:
    """Compile source-bound typed effect inputs without provider graph ids."""

    compiler_version: str = "canonical-obligation-v1"

    def compile_requested_effects(
        self,
        source_ledger: SourceLedger,
        effects: tuple[RequestedEffect, ...],
        semantic_value_constraints: tuple[SemanticValueConstraint, ...] = (),
        *,
        preserve_sequence: bool = False,
        success_criteria: tuple[str, ...] = (),
        value_transfer_pairs: tuple[tuple[int, int], ...] = (),
    ) -> CanonicalObligationGraph:
        """Compile source-bound effects without provider graph authority.

        Flat/default calls keep effects independent and terminal unless the
        caller supplies explicit source-bound value constraints. When
        ``preserve_sequence`` is true, the compiler preserves the ordered
        source effect sequence as Runtime-owned dependency edges and marks only
        the final effect terminal. It still never derives a benchmark family,
        GUI target, provider graph id, or dependency from task names, selectors,
        URLs, coordinates, or benchmark metadata.
        """

        known_units = {unit.source_unit_id for unit in source_ledger.units}
        transfer_source_by_destination = {
            destination: source for source, destination in value_transfer_pairs
        }
        transfer_sources = set(transfer_source_by_destination.values())
        inputs: list[CanonicalEffectInput] = []
        exact_values_by_target: dict[str, tuple[str, ...]] = {}
        for constraint in semantic_value_constraints:
            if constraint.relation != SemanticValueRelation.EXACT or not constraint.target:
                continue
            exact_values_by_target[constraint.target] = tuple(
                dict.fromkeys(
                    (*exact_values_by_target.get(constraint.target, ()), constraint.value)
                )
            )
        for effect in effects:
            effect_index = len(inputs)
            if effect.source_ref not in known_units:
                raise ValueError("requested effect references unknown source unit")
            semantic_target = _canonical_effect_target(effect.target)
            interaction_values = exact_values_by_target.get(effect.target, ())
            literal_value = ", ".join(interaction_values)
            completed_action = (
                effect.interaction_operation == TaskInteractionOperationKind.FOCUS
                or (
                    effect.operation_class == OperationClass.NAVIGATION
                    and _success_criteria_marks_action_completed(
                        target=semantic_target,
                        success_criteria=success_criteria,
                    )
                )
            )
            read = (
                effect.operation_class
                in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
                and not completed_action
            )
            relation = (
                TaskObligationRelation.IS_AVAILABLE
                if read
                else (
                    TaskObligationRelation.IS_COMPLETED
                    if completed_action
                    else _effect_relation_for_literal(semantic_target, literal_value)
                )
            )
            value_source_index = transfer_source_by_destination.get(effect_index)
            if value_source_index is not None:
                relation = TaskObligationRelation.EQUALS
            evidence_kind = (
                EvidenceKind.VISUAL_STATE
                if effect.capability == SPATIAL_POINT_CAPABILITY
                else EvidenceKind.DOM_STATE
                if effect.operation_class
                in {
                    OperationClass.READ_ONLY,
                    OperationClass.NAVIGATION,
                    OperationClass.REVERSIBLE_WRITE,
                }
                else EvidenceKind.API_STATE
            )
            inputs.append(
                CanonicalEffectInput(
                    operation_class=effect.operation_class,
                    target=semantic_target,
                    source_unit_ids=(effect.source_ref,),
                    evidence=(
                        EvidenceRequirement(
                            kind=evidence_kind,
                            subject=semantic_target,
                            relation=relation,
                            value_ref=literal_value,
                            minimum_strength="independent",
                            source_constraints=(effect.source_ref,),
                        ),
                    ),
                    depends_on_effect_indexes=tuple(
                        dict.fromkeys(
                            (
                                *((len(inputs) - 1,) if preserve_sequence and inputs else ()),
                                *((value_source_index,) if value_source_index is not None else ()),
                            )
                        )
                    ),
                    terminal=(not preserve_sequence or len(inputs) == len(effects) - 1),
                    interaction_values=interaction_values,
                    captures_observation_value=effect_index in transfer_sources,
                    value_source_effect_index=value_source_index,
                    interaction_relation=effect.interaction_relation,
                    interaction_capability=effect.capability,
                    interaction_operation=effect.interaction_operation,
                )
            )
        return self.compile(source_ledger, tuple(inputs))

    def compile(
        self,
        source_ledger: SourceLedger,
        effects: tuple[CanonicalEffectInput, ...],
    ) -> CanonicalObligationGraph:
        if not effects:
            raise ValueError("canonical obligation compilation requires effects")
        known_units = {unit.source_unit_id for unit in source_ledger.units}
        claims: list[SourcedTaskClaim] = []
        obligations: list[TaskObligationSpec] = []
        obligation_ids = tuple(f"obligation:{_identity(effect)}" for effect in effects)
        for index, effect in enumerate(effects):
            if set(effect.source_unit_ids) - known_units:
                raise ValueError("canonical effect references unknown source unit")
            if any(set(item.source_constraints) - known_units for item in effect.evidence):
                raise ValueError("canonical evidence references unknown source unit")
            if any(item < 0 or item >= index for item in effect.depends_on_effect_indexes):
                raise ValueError("canonical effect dependency must reference an earlier effect")
            if (
                effect.value_source_effect_index is not None
                and effect.value_source_effect_index not in effect.depends_on_effect_indexes
            ):
                raise ValueError("canonical value source must be a declared earlier dependency")
            identity = _identity(effect)
            claim_id = f"claim:{identity}"
            obligation_id = obligation_ids[index]
            primary_evidence = effect.evidence[0]
            relation = primary_evidence.relation
            literal_value = (
                primary_evidence.value_ref
                if relation
                in {
                    TaskObligationRelation.EQUALS,
                    TaskObligationRelation.IS_SELECTED,
                }
                else ""
            )
            read = (
                effect.operation_class
                in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
                and relation != TaskObligationRelation.IS_COMPLETED
            )
            claims.append(SourcedTaskClaim(
                claim_id=claim_id,
                kind=TaskClaimKind.EFFECT,
                statement=(
                    f"{effect.operation_class.value}:{effect.target}={literal_value}"
                    if literal_value
                    else f"{effect.operation_class.value}:{effect.target}"
                ),
                source_ref=effect.source_unit_ids[0],
                source_unit_ids=effect.source_unit_ids,
                construction_source=GraphConstructionSource.CANONICAL_COMPILER,
            ))
            obligations.append(TaskObligationSpec(
                obligation_id=obligation_id,
                kind=TaskObligationKind.PREDICATE if read else TaskObligationKind.EFFECT,
                subject=effect.target,
                relation=relation,
                value_source=(
                    TaskObligationValueSource.OBLIGATION_OUTPUT
                    if effect.value_source_effect_index is not None
                    else (
                        TaskObligationValueSource.OBSERVATION
                        if effect.captures_observation_value
                        else (
                            TaskObligationValueSource.LITERAL
                            if literal_value
                            else TaskObligationValueSource.NONE
                        )
                    )
                ),
                expected_value=literal_value,
                interaction_values=(
                    effect.interaction_values
                    if relation == TaskObligationRelation.IS_SELECTED
                    else ()
                ),
                interaction_relation=effect.interaction_relation,
                interaction_capability=effect.interaction_capability,
                interaction_operation=effect.interaction_operation,
                claim_ids=(claim_id,),
                depends_on=tuple(obligation_ids[item] for item in effect.depends_on_effect_indexes),
                value_obligation_id=(
                    obligation_ids[effect.value_source_effect_index]
                    if effect.value_source_effect_index is not None
                    else ""
                ),
                evidence_requirements=tuple(f"{item.kind.value}:{item.subject}" for item in effect.evidence),
                typed_evidence_requirements=effect.evidence,
                terminal=effect.terminal,
                construction_source=GraphConstructionSource.CANONICAL_COMPILER,
            ))
        return CanonicalObligationGraph(
            compiler_version=self.compiler_version,
            claims=tuple(claims),
            obligations=tuple(obligations),
        )

    def compile_proposed_graph(
        self,
        source_ledger: SourceLedger,
        claims: tuple[SourcedTaskClaim, ...],
        obligations: tuple[TaskObligationSpec, ...],
        *,
        construction_source: GraphConstructionSource,
    ) -> CanonicalProposalGraph:
        """Canonicalize a bounded multi-stage semantic proposal.

        A proposal may supply legal relationship and value-flow semantics, but
        its identifiers, evidence descriptions, and node instances are never
        copied into the authoritative graph. Runtime reconstructs each node,
        dependency, value reference, and typed evidence contract from the
        source-bound semantic proposal.
        """

        known_source_units = {unit.source_unit_id for unit in source_ledger.units}
        issues: list[CompilationIssue] = []
        claim_id_map: dict[str, str] = {}
        canonical_claims: list[SourcedTaskClaim] = []
        claim_source_units: dict[str, tuple[str, ...]] = {}
        for index, claim in enumerate(claims):
            source_unit_ids = claim.source_unit_ids or (claim.source_ref,)
            if set(source_unit_ids) - known_source_units:
                issues.append(
                    CompilationIssue(
                        code="proposal_unknown_source_unit",
                        field=f"candidate_source_claims[{index}].source_unit_ids",
                    )
                )
                continue
            if claim.claim_id in claim_id_map:
                issues.append(
                    CompilationIssue(
                        code="duplicate_proposal_claim_id",
                        field=f"candidate_source_claims[{index}].claim_id",
                    )
                )
                continue
            canonical_id = _proposal_identity(
                "claim",
                {
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "source_unit_ids": source_unit_ids,
                    "required": claim.required,
                },
            )
            claim_id_map[claim.claim_id] = canonical_id
            claim_source_units[claim.claim_id] = source_unit_ids
            canonical_claims.append(
                SourcedTaskClaim(
                    claim_id=canonical_id,
                    kind=claim.kind,
                    statement=claim.statement,
                    source_ref=source_unit_ids[0],
                    required=claim.required,
                    source_unit_ids=source_unit_ids,
                    construction_source=construction_source,
                )
            )

        obligation_id_map: dict[str, str] = {}
        for index, obligation in enumerate(obligations):
            if obligation.obligation_id in obligation_id_map:
                issues.append(
                    CompilationIssue(
                        code="duplicate_proposal_obligation_id",
                        field=f"candidate_obligations[{index}].obligation_id",
                    )
                )
                continue
            obligation_id_map[obligation.obligation_id] = _proposal_identity(
                "obligation",
                {
                    "kind": obligation.kind.value,
                    "subject": obligation.subject,
                    "relation": obligation.relation.value,
                    "value_source": obligation.value_source.value,
                    "expected_value": obligation.expected_value,
                    "interaction_relation": (
                        obligation.interaction_relation.model_dump(mode="json")
                        if obligation.interaction_relation is not None
                        else None
                    ),
                    "terminal": obligation.terminal,
                },
            )

        canonical_obligations: list[TaskObligationSpec] = []
        for index, obligation in enumerate(obligations):
            resolved_obligation_id = obligation_id_map.get(obligation.obligation_id)
            if resolved_obligation_id is None:
                continue
            unknown_claim_ids = set(obligation.claim_ids) - set(claim_id_map)
            unknown_dependency_ids = set(obligation.depends_on) - set(obligation_id_map)
            value_dependency_unknown = (
                bool(obligation.value_obligation_id)
                and obligation.value_obligation_id not in obligation_id_map
            )
            if unknown_claim_ids or unknown_dependency_ids or value_dependency_unknown:
                issues.append(
                    CompilationIssue(
                        code="proposal_unknown_graph_reference",
                        field=f"candidate_obligations[{index}]",
                    )
                )
                continue
            canonical_claim_ids = tuple(claim_id_map[item] for item in obligation.claim_ids)
            source_constraints = tuple(
                dict.fromkeys(
                    source_unit
                    for proposal_claim_id in obligation.claim_ids
                    for source_unit in claim_source_units[proposal_claim_id]
                )
            )
            canonical_value_obligation_id = (
                obligation_id_map[obligation.value_obligation_id]
                if obligation.value_obligation_id
                else ""
            )
            evidence = EvidenceRequirement(
                kind=EvidenceKind.DOM_STATE,
                subject=obligation.subject,
                relation=obligation.relation,
                value_ref=(
                    obligation.expected_value
                    if obligation.expected_value
                    else canonical_value_obligation_id
                ),
                minimum_strength="independent",
                source_constraints=source_constraints,
            )
            canonical_obligations.append(
                TaskObligationSpec(
                    obligation_id=resolved_obligation_id,
                    kind=obligation.kind,
                    subject=obligation.subject,
                    relation=obligation.relation,
                    value_source=obligation.value_source,
                    expected_value=obligation.expected_value,
                    interaction_values=obligation.interaction_values,
                    interaction_relation=obligation.interaction_relation,
                    interaction_capability=obligation.interaction_capability,
                    interaction_operation=obligation.interaction_operation,
                    value_obligation_id=canonical_value_obligation_id,
                    claim_ids=canonical_claim_ids,
                    depends_on=tuple(obligation_id_map[item] for item in obligation.depends_on),
                    evidence_requirements=(f"{evidence.kind.value}:{evidence.subject}",),
                    typed_evidence_requirements=(evidence,),
                    blocking=obligation.blocking,
                    terminal=obligation.terminal,
                    construction_source=construction_source,
                )
            )
        return CanonicalProposalGraph(
            graph=CanonicalObligationGraph(
                compiler_version=self.compiler_version,
                claims=tuple(canonical_claims),
                obligations=tuple(canonical_obligations),
            ),
            proposal_claim_ids=claim_id_map,
            issues=tuple(issues),
        )


_TEXT_SELECTOR_EFFECT = re.compile(
    r"^(?P<role>button|checkbox|combobox|link|listbox|menuitem|radio|tab)"
    r"\[text\(\)=(?P<quote>['\"])(?P<label>[^'\"]+)(?P=quote)\]$",
    re.IGNORECASE,
)


def _canonical_effect_target(target: str) -> str:
    """Repair one bounded provider text-selector form into semantic identity."""

    match = _TEXT_SELECTOR_EFFECT.fullmatch(target.strip())
    if match is None:
        return target
    role = match.group("role").casefold()
    label = match.group("label").strip()
    return f"{role}:label='{label}'"


def _identity(effect: CanonicalEffectInput) -> str:
    payload = json.dumps(effect.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _success_criteria_marks_action_completed(
    *,
    target: str,
    success_criteria: tuple[str, ...],
) -> bool:
    normalized_target = _completion_target_tokens(target)
    descriptor = re.fullmatch(r"([^:]+):label:(.+)", target.strip(), flags=re.IGNORECASE)
    if descriptor:
        normalized_target = _completion_target_tokens(
            f"{descriptor.group(1)} {descriptor.group(2)}"
        )
    if not normalized_target:
        return False
    completion_words = {
        "activate",
        "activated",
        "click",
        "clicked",
        "clicking",
        "complete",
        "completed",
        "focus",
        "focused",
        "press",
        "pressed",
        "select",
        "selected",
        "submit",
        "submitted",
    }
    return any(
        normalized_target.issubset(normalized_tokens)
        and completion_words.intersection(original_tokens)
        for original_tokens, normalized_tokens in (
            (_semantic_tokens(criterion), _completion_target_tokens(criterion))
            for criterion in success_criteria
        )
    )


def _effect_relation_for_literal(
    target: str,
    literal_value: str,
) -> TaskObligationRelation:
    if not literal_value:
        return TaskObligationRelation.HAS_CHANGED
    if _semantic_tokens(target).intersection({"list", "dropdown", "select", "combobox"}):
        return TaskObligationRelation.IS_SELECTED
    return TaskObligationRelation.EQUALS


def _semantic_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _completion_target_tokens(value: str) -> set[str]:
    replacements = {"closed": "close"}
    return {
        replacements.get(token, token)
        for token in _semantic_tokens(value)
        if token not in {"button", "control", "label"}
    }


def _proposal_identity(kind: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{kind}:" + hashlib.sha256(encoded.encode()).hexdigest()[:24]

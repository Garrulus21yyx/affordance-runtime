from dataclasses import is_dataclass

from affordance_runtime import simplified_runtime_contracts
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength


def test_legacy_relation_names_alias_single_canonical_relation_enum() -> None:
    assert simplified_runtime_contracts.StateCriterionRelation is CriterionRelation


def test_canonical_relation_contains_all_legacy_relation_values() -> None:
    assert {item.value for item in CriterionRelation} == {
        "equals",
        "contains",
        "matches",
        "is_visible",
        "is_absent",
        "is_available",
        "is_selected",
        "is_checked",
        "is_expanded",
        "is_completed",
        "is_ordered_as",
        "has_changed",
    }


def test_nominal_criterion_subclasses_are_compatibility_aliases() -> None:
    assert simplified_runtime_contracts.ValueCriterion is simplified_runtime_contracts.StateCriterion
    assert simplified_runtime_contracts.PresenceCriterion is simplified_runtime_contracts.StateCriterion
    assert simplified_runtime_contracts.AbsenceCriterion is simplified_runtime_contracts.StateCriterion
    assert simplified_runtime_contracts.NavigationCriterion is simplified_runtime_contracts.StateCriterion
    assert is_dataclass(simplified_runtime_contracts.StateCriterion)


def test_legacy_evidence_policy_and_strength_names_alias_canonical_vocabulary() -> None:
    assert simplified_runtime_contracts.CriterionEvidencePolicy is EvidencePolicy
    assert simplified_runtime_contracts.EvidenceStrength is EvidenceStrength

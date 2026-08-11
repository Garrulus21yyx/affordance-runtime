"""Stable task and optional planning contracts for the target runtime."""

from affordance_runtime.task.contracts import (
    EvaluationSpec,
    LoopBudget,
    MaterialBinding,
    RiskProfile,
    TaskGoal,
)
from affordance_runtime.task.hypothesis_contracts import (
    HypothesisPredicateAssessment,
    HypothesisProposalMode,
    HypothesisSetCompleteness,
    RequirementHypothesisFailure,
    RequirementHypothesisFailureKind,
    RequirementHypothesisProposal,
    RequirementHypothesisProposalBatch,
    RequirementHypothesisProposer,
    RequirementHypothesisState,
    TrackedHypothesisStatus,
    TrackedRequirementHypothesis,
)
from affordance_runtime.task.hypothesis_runtime import (
    HypothesisAdmissionCode,
    HypothesisAdmissionResult,
    admit_requirement_hypotheses,
    assess_requirement_hypotheses,
)
from affordance_runtime.task.intent_context import IntentContext, IntentExcerpt, IntentSourceKind
from affordance_runtime.task.planning_contracts import LocalObjective, Milestone, TaskPlan

__all__ = [
    "EvaluationSpec",
    "LocalObjective",
    "LoopBudget",
    "IntentContext",
    "IntentExcerpt",
    "IntentSourceKind",
    "HypothesisProposalMode",
    "HypothesisSetCompleteness",
    "HypothesisPredicateAssessment",
    "HypothesisAdmissionCode",
    "HypothesisAdmissionResult",
    "MaterialBinding",
    "Milestone",
    "RiskProfile",
    "RequirementHypothesisFailure",
    "RequirementHypothesisFailureKind",
    "RequirementHypothesisProposal",
    "RequirementHypothesisProposalBatch",
    "RequirementHypothesisProposer",
    "RequirementHypothesisState",
    "TrackedRequirementHypothesis",
    "TrackedHypothesisStatus",
    "admit_requirement_hypotheses",
    "assess_requirement_hypotheses",
    "TaskGoal",
    "TaskPlan",
]

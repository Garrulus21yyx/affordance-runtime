"""Non-authoritative complexity and exact-profile support classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .contracts import ModelConformanceStage, ModelInputComplexity


class ModelProfileSupportStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    STRUCTURED_OUTPUT_INCOMPATIBLE = "structured_output_incompatible"
    SELECT_ACTION_CONTRACT_INCOMPATIBLE = "select_action_contract_incompatible"
    UNION_SCHEMA_INCOMPATIBLE = "union_schema_incompatible"
    CONTEXT_FOLLOWING_INCOMPATIBLE = "context_following_incompatible"
    RUNTIME_POLICY_INCOMPATIBLE = "runtime_policy_incompatible"
    SINGLE_RUN_ATTESTED = "single_run_attested"
    DIAGNOSTIC_PASS = "diagnostic_pass"
    SUPPORTED_WITH_COMPACT_GROUNDING = "supported_with_compact_grounding"
    ACTION_SELECTION_SUPPORTED = "action_selection_supported"
    FULL_RECURRENT_POLICY_SUPPORTED = "full_recurrent_policy_supported"
    UNSUPPORTED = "unsupported_for_agent_policy"


class ModelPolicyCapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_ADMITTED = "not_admitted"
    INCONCLUSIVE_PROVIDER_AVAILABILITY = "inconclusive_provider_availability"


@dataclass(frozen=True)
class ModelPolicyCapabilitySupport:
    structured_output_status: ModelPolicyCapabilityStatus
    action_selection_status: ModelPolicyCapabilityStatus
    full_recurrent_decision_status: ModelPolicyCapabilityStatus


def classify_policy_capabilities(
    level_counts: Mapping[str, tuple[int, int]],
    failure_stages: tuple[ModelConformanceStage, ...],
    *,
    support_attestation: bool,
    recurrent_matrix: Mapping[str, tuple[int, int]] | None,
    critical_matrix_passed: bool = False,
) -> ModelPolicyCapabilitySupport:
    unavailable = ModelConformanceStage.UNAVAILABLE in failure_stages
    if unavailable:
        inconclusive = ModelPolicyCapabilityStatus.INCONCLUSIVE_PROVIDER_AVAILABILITY
        return ModelPolicyCapabilitySupport(inconclusive, inconclusive, inconclusive)
    structured = (
        ModelPolicyCapabilityStatus.SUPPORTED
        if level_counts.get("0", (0, 0))[0] == level_counts.get("0", (0, 0))[1] > 0
        else ModelPolicyCapabilityStatus.NOT_ADMITTED
    )
    action_gate = support_attestation and all(
        level_counts.get(str(level)) == (20, 20) for level in range(5)
    ) and not {
        ModelConformanceStage.STRICT_JSON,
        ModelConformanceStage.PAYLOAD_SCHEMA,
        ModelConformanceStage.ACTION_ID,
        ModelConformanceStage.DESTINATION_ID,
        ModelConformanceStage.PARAMETERS,
        ModelConformanceStage.RUNTIME_ADMISSION,
    }.intersection(failure_stages)
    action = (
        ModelPolicyCapabilityStatus.SUPPORTED
        if action_gate else ModelPolicyCapabilityStatus.NOT_ADMITTED
    )
    if recurrent_matrix is None:
        recurrent = ModelPolicyCapabilityStatus.NOT_ADMITTED
    elif action_gate and critical_matrix_passed and all(
        recurrent_matrix.get(variant) == (20, 20)
        for variant in _RECURRENT_VARIANTS
    ):
        recurrent = ModelPolicyCapabilityStatus.SUPPORTED
    else:
        recurrent = ModelPolicyCapabilityStatus.PARTIAL
    return ModelPolicyCapabilitySupport(structured, action, recurrent)


_RECURRENT_VARIANTS = (
    "select_action", "request_evidence", "request_action_page", "ask_user",
    "propose_done", "wait", "abort",
)


def classify_complexity(value: ModelInputComplexity) -> str:
    if value.serialized_context_bytes <= 4_096 and value.actions <= 4 and value.history_turns <= 2:
        return "tiny"
    if value.serialized_context_bytes <= 16_384 and value.actions <= 16 and value.history_turns <= 8:
        return "small"
    if value.serialized_context_bytes <= 32_768 and value.actions <= 32 and value.history_turns <= 12:
        return "medium"
    return "large"


def root_cause(level_counts: dict[str, tuple[int, int]]) -> str:
    causes = (
        ("0", "provider_or_structured_output_incompatibility"),
        ("1", "exact_id_or_select_action_contract"),
        ("2", "union_schema_complexity"),
        ("3", "agent_context_following"),
        ("4", "runtime_policy_or_completion"),
    )
    for level, cause in causes:
        passed, attempted = level_counts.get(level, (0, 0))
        if attempted and passed < attempted:
            return cause
    return "no_failure_observed"


def classify_support(
    level_counts: dict[str, tuple[int, int]],
    failure_stages: tuple[ModelConformanceStage, ...],
    *,
    support_attestation: bool,
) -> ModelProfileSupportStatus:
    destination_ladder = level_counts and all(level.startswith("D") for level in level_counts)
    if destination_ladder:
        complete = all(passed == total > 0 for passed, total in level_counts.values())
        return (
            ModelProfileSupportStatus.DIAGNOSTIC_PASS
            if complete
            else ModelProfileSupportStatus.CONTEXT_FOLLOWING_INCOMPATIBLE
        )
    if any(stage == ModelConformanceStage.UNAVAILABLE for stage in failure_stages):
        return ModelProfileSupportStatus.UNAVAILABLE
    complete = all(level_counts.get(str(level), (0, 0))[0] == level_counts.get(str(level), (0, 0))[1] > 0 for level in range(5))
    twenty = all(level_counts.get(str(level)) == (20, 20) for level in range(5))
    forbidden_failures = {
        ModelConformanceStage.STRICT_JSON, ModelConformanceStage.PAYLOAD_SCHEMA,
        ModelConformanceStage.ACTION_ID, ModelConformanceStage.DESTINATION_ID,
        ModelConformanceStage.PARAMETERS,
    }
    if support_attestation and twenty and not forbidden_failures.intersection(failure_stages):
        return ModelProfileSupportStatus.ACTION_SELECTION_SUPPORTED
    if complete:
        total = sum(total for _, total in level_counts.values())
        return ModelProfileSupportStatus.SINGLE_RUN_ATTESTED if total == 5 else ModelProfileSupportStatus.DIAGNOSTIC_PASS
    cause = root_cause(level_counts)
    mapping = {
        "provider_or_structured_output_incompatibility": ModelProfileSupportStatus.STRUCTURED_OUTPUT_INCOMPATIBLE,
        "exact_id_or_select_action_contract": ModelProfileSupportStatus.SELECT_ACTION_CONTRACT_INCOMPATIBLE,
        "union_schema_complexity": ModelProfileSupportStatus.UNION_SCHEMA_INCOMPATIBLE,
        "agent_context_following": ModelProfileSupportStatus.CONTEXT_FOLLOWING_INCOMPATIBLE,
        "runtime_policy_or_completion": ModelProfileSupportStatus.RUNTIME_POLICY_INCOMPATIBLE,
    }
    return mapping.get(cause, ModelProfileSupportStatus.UNSUPPORTED)

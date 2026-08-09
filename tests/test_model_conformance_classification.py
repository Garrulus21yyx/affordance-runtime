from affordance_runtime.benchmarks.model_conformance.classification import (
    ModelProfileSupportStatus,
    classify_complexity,
    classify_support,
    root_cause,
)
from affordance_runtime.benchmarks.model_conformance.contracts import (
    ModelConformanceStage,
    ModelInputComplexity,
)


def _complexity(context, actions, history):
    return ModelInputComplexity(context, 10, 10, 1, 7, 5, actions, 0, 1, 1, 0, 0, history, context + 20)


def test_complexity_classification_uses_actual_input_only() -> None:
    assert classify_complexity(_complexity(4_000, 4, 2)) == "tiny"
    assert classify_complexity(_complexity(8_000, 8, 4)) == "small"
    assert classify_complexity(_complexity(20_000, 20, 10)) == "medium"
    assert classify_complexity(_complexity(40_000, 1, 0)) == "large"


def test_root_cause_table_uses_first_failed_level() -> None:
    assert root_cause({"0": (0, 5)}) == "provider_or_structured_output_incompatibility"
    assert root_cause({"0": (5, 5), "1": (0, 5)}) == "exact_id_or_select_action_contract"
    assert root_cause({"1": (5, 5), "2": (0, 5)}) == "union_schema_complexity"
    assert root_cause({"2": (5, 5), "3": (0, 5)}) == "agent_context_following"
    assert root_cause({"3": (5, 5), "4": (0, 5)}) == "runtime_policy_or_completion"


def test_one_success_is_not_supported_and_twenty_per_level_is_required() -> None:
    single = {str(level): (1, 1) for level in range(5)}
    assert classify_support(single, (), support_attestation=False) == ModelProfileSupportStatus.SINGLE_RUN_ATTESTED
    twenty = {str(level): (20, 20) for level in range(5)}
    assert (
        classify_support(twenty, (), support_attestation=True)
        == ModelProfileSupportStatus.ACTION_SELECTION_SUPPORTED
    )
    assert classify_support(
        twenty, (ModelConformanceStage.PAYLOAD_SCHEMA,), support_attestation=True,
    ) != ModelProfileSupportStatus.ACTION_SELECTION_SUPPORTED

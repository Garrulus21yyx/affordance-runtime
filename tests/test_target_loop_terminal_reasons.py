import asyncio
from dataclasses import replace

from affordance_runtime.agent import AgentFailureCode, AgentLoopStatus
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkManifest,
    BenchmarkRunIdentity,
    TerminalReasonCode,
)
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.benchmarks.target_loop.terminal_reasons import project_terminal_reason_code


def test_blocked_runtime_reason_codes_project_to_typed_terminal_reasons() -> None:
    expected = {
        "action_outside_current_page": TerminalReasonCode.ACTION_OUTSIDE_CURRENT_PAGE,
        "destination_outside_current_page": (
            TerminalReasonCode.DESTINATION_OUTSIDE_CURRENT_PAGE
        ),
        "action_outside_action_space": TerminalReasonCode.ACTION_OUTSIDE_ACTION_SPACE,
        "invalid_completion_claim": TerminalReasonCode.INVALID_COMPLETION_CLAIM,
        "completion_evidence_not_current": TerminalReasonCode.COMPLETION_EVIDENCE_NOT_CURRENT,
    }
    for reason_code, code in expected.items():
        assert project_terminal_reason_code(AgentLoopStatus.BLOCKED, reason_code) == code


def test_terminal_reason_projection_never_copies_unknown_runtime_detail() -> None:
    private_detail = "private bid=secret-action destination=secret-option"
    code = project_terminal_reason_code(AgentLoopStatus.BLOCKED, private_detail)
    assert code == TerminalReasonCode.BLOCKED_OTHER
    assert private_detail not in code.value


def test_nonblocked_result_has_no_terminal_reason() -> None:
    assert project_terminal_reason_code(AgentLoopStatus.DONE, "task complete") is None


def test_no_progress_failure_projects_typed_reason_without_message_matching() -> None:
    assert project_terminal_reason_code(
        AgentLoopStatus.FAILED,
        "detail is not an authority",
        AgentFailureCode.NO_PROGRESS_REPETITION,
    ) is TerminalReasonCode.NO_PROGRESS_REPETITION


def test_typed_terminal_reason_advances_harness_contract() -> None:
    assert BenchmarkRunIdentity.__dataclass_fields__["harness_schema_version"].default == (
        "target-loop-harness.v5"
    )


def test_suite_report_projects_agent_result_message_without_retaining_detail() -> None:
    class OutsideActionSpacePolicy:
        async def decide(self, context):
            return SelectAction(context.context_id, "private-action-id")

    manifest = get_manifest("internal-core", "deterministic", 7)
    original = manifest.cases[0]

    def composition(instrumentation):
        value = original.composition_factory(instrumentation)
        return replace(value, policy=OutsideActionSpacePolicy())

    case = replace(
        original,
        composition_factory=composition,
        expected_terminal_statuses=(AgentLoopStatus.BLOCKED,),
        metric_expectations=(),
    )
    suite = asyncio.run(run_suite(BenchmarkManifest(
        manifest.schema_version, manifest.suite_id, manifest.profile_id, manifest.seed, (case,),
    )))

    assert suite.cases[0].terminal_reason_code == TerminalReasonCode.ACTION_OUTSIDE_CURRENT_PAGE
    assert "private-action-id" not in str(suite.cases[0])

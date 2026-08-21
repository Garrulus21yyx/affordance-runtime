from __future__ import annotations

from importlib.resources import files
from typing import Mapping

import yaml


def _prompt(name: str, key: str) -> str:
    resource = files("affordance_runtime.model").joinpath(f"policy/prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    assert isinstance(raw, Mapping)
    assert set(raw) == {"version", key}
    return str(raw[key])


def test_manager_prompt_has_one_two_mode_combined_review_contract() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")

    assert "initial_plan" in prompt
    assert "review_and_route" in prompt
    assert all(
        route in prompt
        for route in (
            "execute_subtask",
            "request_finalization",
            "ask_user",
            "blocked",
        )
    )
    assert all(
        assessment in prompt
        for assessment in (
            "not_applicable",
            "satisfied",
            "unsatisfied",
            "unknown",
            "blocked",
        )
    )
    assert "non-authoritative" in prompt
    assert "materially change" in prompt
    assert "official success" in prompt


def test_manager_prompt_freezes_one_outcome_subtask_granularity() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")

    assert "exactly one dominant, independently reviewable outcome" in prompt
    assert "Do not return an assessment, not_applicable" in prompt
    assert "4–8 ActionPolicy turns" in prompt
    assert "The episode limit is a safety cap, not a planning target" in prompt
    assert "one fresh observable state or evidence packet" in prompt
    assert 'Too small: "Type the first form field."' in prompt
    assert "Submit the related form fields" in prompt
    assert "Verify one candidate against the stated constraint" in prompt
    assert "Discover every candidate, verify all candidates" in prompt
    assert not any(
        benchmark_term in prompt
        for benchmark_term in ("WebArena", "airport", "Magento", "Bestsellers")
    )


def test_manager_prompt_keeps_auditor_exceptional_and_admission_mechanical() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")

    assert "Independent SemanticAuditor is not part of the ordinary episode transition" in prompt
    assert "Exact retained public scalar facts are admitted mechanically" in prompt
    assert "ordinary retrieval, optional pinning, stall, budget" in prompt
    assert "outcome_proposed, and finalization do not require SemanticAuditor" in prompt
    assert "not permission to yield" in prompt
    assert "may satisfy one composite business outcome with several current F refs" in prompt


def test_grounded_agent_prompt_has_no_mixed_final_response_instruction() -> None:
    prompt = _prompt("grounded_agent.yaml", "actor")

    assert "outcome_proposed" in prompt
    assert "final-response turn" not in prompt
    assert "final_response_contract" not in prompt
    assert "Never emit final JSON or prose directly" in prompt
    assert "Pin an offered exact evidence ref only when it must survive" in prompt
    assert "prior pinning is not required" in prompt
    assert 'yield_subtask(kind="needs_replan"' in prompt
    assert "TaskGoal remains authoritative" in prompt


def test_grounded_agent_prompt_distinguishes_model_execution_view_from_runtime_contract() -> None:
    prompt = _prompt("grounded_agent.yaml", "actor")

    assert "complete model-relevant execution contract" in prompt
    assert "Runtime-owned budget" in prompt
    assert "carry-fact selection" in prompt
    assert "audit lineage are enforced outside ActionPolicy" in prompt
    assert "complete current Manager contract" not in prompt


def test_manager_owns_direct_terminal_value_and_no_finalizer_prompt_exists() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")
    finalizer = files("affordance_runtime.model").joinpath("policy/prompts/final_response.yaml")

    assert "direct final_response business value" in prompt
    assert "Never call submit_final_response" in prompt
    assert "{name, arguments}" in prompt
    assert "task_link" in prompt
    assert "assessments need not be equal" in prompt
    assert "subtask_misaligned" in prompt
    assert not finalizer.is_file()


def test_optional_auditor_prompt_cannot_plan_route_or_mutate_state() -> None:
    prompt = _prompt("mission_auditor.yaml", "auditor")

    assert "optional SemanticAuditor" in prompt
    assert "one explicitly submitted" in prompt
    assert "Do not plan, route" in prompt
    assert "mutate MissionState" in prompt
    assert "official success" in prompt

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


def test_grounded_agent_prompt_has_no_mixed_final_response_instruction() -> None:
    prompt = _prompt("grounded_agent.yaml", "actor")

    assert "outcome_proposed" in prompt
    assert "final-response turn" not in prompt
    assert "final_response_contract" not in prompt
    assert "Never emit final JSON or prose directly" in prompt


def test_manager_owns_direct_terminal_value_and_no_finalizer_prompt_exists() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")
    finalizer = files("affordance_runtime.model").joinpath("policy/prompts/final_response.yaml")

    assert "direct final_response business value" in prompt
    assert "Never call submit_final_response" in prompt
    assert "{name, arguments}" in prompt
    assert not finalizer.is_file()


def test_optional_auditor_prompt_cannot_plan_route_or_mutate_state() -> None:
    prompt = _prompt("mission_auditor.yaml", "auditor")

    assert "optional strict" in prompt
    assert "one explicitly submitted" in prompt
    assert "Do not plan, route" in prompt
    assert "mutate MissionState" in prompt
    assert "official success" in prompt

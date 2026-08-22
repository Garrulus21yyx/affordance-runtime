from importlib.resources import files
from typing import Mapping

import yaml


def _prompt(name: str, key: str) -> str:
    resource = files("affordance_runtime.model").joinpath(f"policy/prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    assert isinstance(raw, Mapping)
    assert set(raw) == {"version", key}
    return str(raw[key])


def test_planner_prompt_freezes_low_frequency_roadmap_contract_and_boundaries() -> None:
    prompt = _prompt("milestone_planner.yaml", "planner")
    assert "one to five milestones" in prompt
    assert all(field in prompt for field in ("id", "outcome", "done_when", "required_evidence", "depends_on", "final"))
    assert all(trigger in prompt for trigger in ("start", "needs_replan", "roadmap_exhausted_not_finalizable"))
    assert all(trigger not in prompt for trigger in ("outcome_admitted", "finalization_gap"))
    assert "one page, form field, click, navigation" in prompt
    assert "filling its related filters, submitting, and reading" in prompt
    assert "filling a route" in prompt and "reading the route result" in prompt


def test_planner_prompt_forbids_gui_authority_budget_and_mutable_progress() -> None:
    prompt = _prompt("milestone_planner.yaml", "planner")
    assert "Do not output mutable completed state" in prompt
    assert "episode budget" in prompt
    assert "entry scope" in prompt
    assert "generation-local GUI refs" in prompt
    assert "screen-space click points, selectors, BIDs" in prompt
    assert "geographic coordinates" in prompt
    assert "product selectors" in prompt
    assert not any(term in prompt for term in ("WebArena", "airport", "Magento", "Bestsellers", "Task-7"))


def test_grounded_agent_prompt_assigns_final_response_to_mechanical_boundary() -> None:
    prompt = _prompt("grounded_agent.yaml", "actor")
    assert "outcome_proposed" in prompt
    assert "submit_final_response if offered" in prompt
    assert "one STOP and native evaluation" in prompt
    assert "Pin an offered exact evidence ref only when it must survive" in prompt
    assert 'yield_milestone(kind="needs_replan"' in prompt
    assert "TaskGoal remains authoritative" in prompt


def test_optional_auditor_prompt_cannot_plan_route_or_mutate_state() -> None:
    prompt = _prompt("mission_auditor.yaml", "auditor")
    assert "optional SemanticAuditor" in prompt
    assert "Do not plan, route" in prompt
    assert "mutate MissionState" in prompt
    assert "official success" in prompt
    assert not files("affordance_runtime.model").joinpath("policy/prompts/final_response.yaml").is_file()

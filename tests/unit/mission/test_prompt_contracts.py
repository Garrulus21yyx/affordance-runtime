from __future__ import annotations

import re
from importlib.resources import files
from typing import Mapping

import yaml


def _prompt(name: str, key: str) -> str:
    resource = files("affordance_runtime.model").joinpath(f"policy/prompts/{name}")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    assert isinstance(raw, Mapping)
    assert set(raw) == {"version", key}
    return str(raw[key])


def _section_positions(prompt: str, sections: tuple[str, ...]) -> list[int]:
    positions = [prompt.index(section) for section in sections]
    assert positions == sorted(positions)
    return positions


def test_manager_prompt_is_short_structured_and_limits_environment_projection() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")

    sections = (
        "Identity",
        "Authoritative inputs",
        "Responsibilities",
        "Route rules",
        "Output contract",
    )
    _section_positions(prompt, sections)
    assert len(prompt) < 2_000
    lowered = prompt.casefold()
    for forbidden in ("screenshot", "worldobservation", "actionspace", "selector", "coordinate", "e/f ref"):
        assert forbidden not in lowered
    assert "MissionEnvironmentView" in prompt
    assert "not a second environment authority" in prompt
    assert re.search(r"\bE[- ]?ref\b", prompt, flags=re.IGNORECASE) is None
    assert re.search(r"\bF[- ]?ref\b", prompt, flags=re.IGNORECASE) is None
    assert "never prescribe or copy concrete ActionPolicy tool/capability identifiers" in prompt
    assert "15 turns" in prompt
    assert "5-8 turns" in prompt
    assert "do not default to 20" in prompt


def test_manager_prompt_route_and_authority_contract() -> None:
    prompt = _prompt("mission_manager.yaml", "manager")
    routes = set(re.findall(r"\b(execute_subtask|ask_user|blocked|request_final_audit)\b", prompt))

    assert routes == {"execute_subtask", "ask_user", "blocked", "request_final_audit"}
    assert "Executor claims and prior plans are not proof." in prompt
    assert "accepted audited outcomes and facts" in prompt
    assert "official success" not in prompt.casefold()
    assert "official benchmark successful" not in prompt.casefold()
    assert "Next:" not in prompt
    assert "gui|cli" not in prompt


def test_auditor_prompt_claim_evidence_unknown_and_read_only_contract() -> None:
    prompt = _prompt("mission_auditor.yaml", "auditor")
    sections = (
        "Identity",
        "Evidence boundary",
        "Audit responsibility",
        "Conservative decision rule",
        "Output contract",
    )
    _section_positions(prompt, sections)

    assert len(prompt) < 1700
    assert "self-reported completion are claims, not proof" in prompt
    assert "Every satisfied outcome, promoted fact, or invalidation must cite evidence" in prompt
    assert "Use unknown when the available evidence cannot support a conclusion." in prompt
    assert "Do not execute GUI actions." in prompt
    assert "Do not modify MissionState." in prompt
    lowered = prompt.casefold()
    assert "select_action" not in lowered
    assert "send_msg_to_user" not in lowered
    assert "stop" not in lowered


def test_mission_prompts_do_not_expose_hidden_or_copied_sota_contracts() -> None:
    combined = "\n".join((
        _prompt("mission_manager.yaml", "manager"),
        _prompt("mission_auditor.yaml", "auditor"),
    ))
    lowered = combined.casefold()

    for forbidden in ("hidden evaluator", "expected answer", "reward"):
        assert forbidden not in lowered
    for rejected_sota in (
        "current task state",
        "task contract",
        "acceptance-constraint backcheck",
        "longhorizon-harness",
        "agent s2",
        "dag translator",
        "procedural memory",
    ):
        assert rejected_sota not in lowered

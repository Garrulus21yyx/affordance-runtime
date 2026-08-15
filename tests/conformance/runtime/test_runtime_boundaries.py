import re
from pathlib import Path

from affordance_runtime.actions.contracts import ExecutionReceipt, Observation, VerifierSpec
from affordance_runtime.verification.mechanical import VerifierLadder


def _receipt(**evidence: object) -> ExecutionReceipt:
    return ExecutionReceipt(
        "contract",
        "portable-web",
        True,
        "rev-1",
        "rev-1",
        1.0,
        evidence=dict(evidence),
    )


def test_generic_dom_attribute_verifier_uses_declared_identity_attribute() -> None:
    observation = Observation(
        "rev-2",
        metadata={
            "html": '<input data-runtime-handle="theme" value="dark">',
        },
    )
    spec = VerifierSpec(
        "dom_attribute",
        "theme",
        {
            "target_attribute": "data-runtime-handle",
            "attribute": "value",
            "value": "dark",
        },
    )

    assert VerifierLadder().verify_report([spec], _receipt(), observation).passed


def test_generic_terminal_verifier_keeps_adapter_terminal_success_as_weak_receipt_evidence() -> None:
    spec = VerifierSpec("state_delta_or_terminal", "target", True)
    unchanged = Observation("rev-1")

    assert not VerifierLadder().verify_report(
        [spec],
        _receipt(terminated=True, official_reward=1.0),
        unchanged,
    ).passed
    terminal_report = VerifierLadder().verify_report(
        [spec],
        _receipt(terminal_success=True),
        unchanged,
    )
    assert terminal_report.passed
    assert terminal_report.evidence[0].source == "execution_receipt"
    assert terminal_report.evidence[0].strength == "weak"
    changed = Observation(
        "rev-1",
        metadata={"control_states": {"target": {"checked": True}}},
    )
    state_delta = VerifierSpec(
        "state_delta_or_terminal",
        "target",
        {"field": "checked", "changed_from": False},
    )
    assert VerifierLadder().verify_report(
        [state_delta],
        _receipt(terminal_success=False),
        changed,
    ).passed
    assert not VerifierLadder().verify_report(
        [state_delta],
        _receipt(terminal_failure=True),
        changed,
    ).passed


def test_shared_runtime_sources_contain_no_benchmark_protocol_vocabulary() -> None:
    source_root = Path(__file__).parents[3] / "src" / "affordance_runtime"
    forbidden = (
        "browsergym",
        "miniwob",
        "official_reward",
        "browsergym_set_of_marks",
        "browsergym_visibility_ratio",
        "click_no_navigation",
        "drag_and_drop",
    )
    violations: list[str] = []
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        if (
            "benchmarks" in path.parts
            or relative.parts[:2] == ("surfaces", "browsergym")
            or path.name == "cli.py"
        ):
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for token in forbidden:
            if token in text:
                violations.append(f"{path.relative_to(source_root)}:{token}")
        if re.search(r"\bbid\b", text):
            violations.append(f"{path.relative_to(source_root)}:bid")

    assert violations == []

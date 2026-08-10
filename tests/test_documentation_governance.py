from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
MANIFEST = DOCS / "documentation-manifest.yaml"
DOCS_INDEX = DOCS / "README.md"
ROOT_INDEX = ROOT / "README.md"
EVOLUTION_PLAN = (
    DOCS
    / "superpowers"
    / "plans"
    / "2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md"
)
AUTHORITATIVE_ARCHITECTURE = (
    DOCS
    / "superpowers"
    / "specs"
    / "2026-08-05-task-contract-centered-runtime-authoritative-architecture.md"
)
IMPLEMENTATION_STATUS = DOCS / "implementation-status.md"
CURRENT_PLAN = DOCS / "current-implementation-plan.md"

VALID_LIFECYCLES = {
    "current",
    "immutable_record",
    "archived",
    "redirect",
}


def _manifest_text() -> str:
    return MANIFEST.read_text(encoding="utf-8")


def _section(name: str) -> str:
    text = _manifest_text()
    match = re.search(
        rf"(?ms)^{re.escape(name)}:\n(?P<body>.*?)(?=^[a-z_]+:\n|\Z)",
        text,
    )
    assert match is not None, name
    return match.group("body")


def _paths(section: str) -> tuple[str, ...]:
    return tuple(re.findall(r"(?m)^\s+- (?:role:.*\n\s+)?path: (\S+)$", section))


def _markdown_links(path: Path) -> tuple[str, ...]:
    return tuple(
        match.group(1)
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8"))
    )


def test_manifest_declares_one_current_architecture_and_evolution_plan() -> None:
    text = _manifest_text()

    assert text.count("role: authoritative_architecture") == 1
    assert text.count("role: authoritative_evolution_plan") == 1
    authoritative_paths = _paths(_section("authoritative"))
    assert len(authoritative_paths) == 2
    assert all("/archive/" not in path for path in authoritative_paths)


def test_evolution_plan_has_one_current_phase_truth() -> None:
    text = EVOLUTION_PLAN.read_text(encoding="utf-8")

    assert "`A1–A4` 尚未开始代码实现" not in text
    assert "尚未证明相同\nTaskGoal/AgentPolicy/evaluator" not in text
    assert "P5-A1–A4: COMPLETE_NON_DEFAULT" in text
    assert "P5-B1–B4: COMPLETE_FOR_DECLARED_MINIMUM_PROFILES" in text
    assert "P5-C1–C3: COMPLETE_FOR_SHARED_STATE_DETERMINISTIC_MATRIX" in text
    assert "P5-D1–D4: COMPLETE_NON_DEFAULT" in text
    assert "P5-D5 evaluator control: COMPLETE_FOR_CURRENT_NO_REQUIRED_OUTPUT_PROFILE" in text
    assert "P5-D5 target output validation: COMPLETE_FOR_DECLARED_MINIMUM" in text
    assert "P5-D6.1: COMPLETE" in text
    assert "P5-M0: COMPLETE" in text
    assert "P5-M0.1 AgentContext architecture: COMPLETE_NON_DEFAULT" in text
    assert "model-backed AgentPolicy: CLOSED" in text
    assert "P5-M1.1 strict decision boundary and existing ModelPort bridge: COMPLETE_NON_DEFAULT" in text
    assert "local HTTP provider transport proof: COMPLETE" in text
    assert "live provider profile: EXACT_HEAD_MISTRAL_ATTESTED_FOR_DECLARED_PROFILES" in text
    assert "P5-M2 production evaluator composition: COMPLETE_NON_DEFAULT_FOR_DECLARED_MINIMUM" in text
    assert "P5-M2.1 evidence semantics and dynamic readiness: COMPLETE_NON_DEFAULT" in text
    assert "P5-M3 new-AgentLoop internal benchmark harness: COMPLETE_NON_DEFAULT_FOR_FIXED_MANIFEST" in text
    assert "P5-M4.3 historical MiniWoB-60 run: COMPLETE_VALID_NEGATIVE_EVIDENCE (6/60)" in text
    assert (
        "post-M4.4 separately authorized rerun-v3: "
        "COMPLETE_VALID_NEGATIVE_EVIDENCE (4/60)"
    ) in text
    assert "P5-M4.5-A acquisition lifecycle: NOT_STARTED / NEXT" in text
    assert "P5-M4.5-B ControlTransition accounting: NOT_STARTED / AFTER_M4.5-A" in text


def test_current_queue_orders_short_loop_closure_before_long_horizon() -> None:
    text = CURRENT_PLAN.read_text(encoding="utf-8")

    markers = (
        "P5-M4.5-A observation acquisition lifecycle — next",
        "P5-M4.5-B lossless ControlTransition — queued after A",
        "## Gates after M4.5",
        "VerifiedTaskState evidence promotion",
    )
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "Rerun-v3 completed 60/60 with valid 4/60 evidence" in text
    assert "rerun remains blocked" not in text.lower()


def test_target_contract_keeps_transition_lightweight_and_capture_typed() -> None:
    architecture = AUTHORITATIVE_ARCHITECTURE.read_text(encoding="utf-8")
    status = IMPLEMENTATION_STATUS.read_text(encoding="utf-8")

    for marker in (
        "class ObservationCapabilities",
        "class ObservationAcquisition",
        "class ExecutionOutcome",
        "class ControlTransition",
        "class VerifiedTaskState",
        "AgentLoopState 不由 transition replay 重建",
    ):
        assert marker in architecture
    assert "CAPABILITY_UNAVAILABLE" in architecture
    assert "durable ledger" in architecture
    assert "WorldEnvironment independent capture" in status
    assert "lossless ControlTransition" in status
    assert "CLOSED_FOR_FILL_SELECT_LOCAL_LIVENESS" in status


def test_manifest_paths_and_lifecycles_are_valid() -> None:
    text = _manifest_text()
    paths = re.findall(r"(?m)^\s+path: (\S+)$", text)
    lifecycles = re.findall(r"(?m)^\s+lifecycle: (\S+)$", text)

    assert paths
    assert set(lifecycles) <= VALID_LIFECYCLES
    for relative in paths:
        assert (ROOT / relative).exists(), relative


def test_current_authority_index_does_not_route_through_archive() -> None:
    text = DOCS_INDEX.read_text(encoding="utf-8")
    current_authority = text.split("## 1. Current target authority", 1)[1].split(
        "## 2.", 1
    )[0]

    assert "archive/" not in current_authority
    assert "2026-08-05-task-contract-centered-runtime-authoritative-architecture.md" in (
        current_authority
    )
    assert "2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md" in (
        current_authority
    )


def test_redirects_are_small_archived_pointers_with_live_targets() -> None:
    redirect_paths = _paths(_section("stable_redirects"))

    assert redirect_paths
    for relative in redirect_paths:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        assert "ARCHIVED POINTER" in text, relative
        assert len(text.splitlines()) <= 24, relative
        assert any("archive/" in link for link in _markdown_links(path)), relative
        for link in _markdown_links(path):
            if link.startswith(("http://", "https://", "#")):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            assert target.exists(), f"{relative} -> {link}"


def test_maintained_markdown_relative_links_resolve() -> None:
    maintained_sections = (
        "discovery",
        "authoritative",
        "status",
        "normative",
        "reference",
    )
    maintained = {ROOT_INDEX}
    for section in maintained_sections:
        maintained.update(ROOT / relative for relative in _paths(_section(section)))

    for path in sorted(maintained):
        for link in _markdown_links(path):
            if link.startswith(("http://", "https://", "#")):
                continue
            relative_target = link.split("#", 1)[0]
            if not relative_target:
                continue
            target = (path.parent / relative_target).resolve()
            assert target.exists(), f"{path.relative_to(ROOT)} -> {link}"


def test_every_live_markdown_document_has_one_manifest_lifecycle() -> None:
    classified_sections = (
        "discovery",
        "authoritative",
        "status",
        "normative",
        "reference",
        "stable_redirects",
    )
    classified = {
        ROOT / relative
        for section in classified_sections
        for relative in _paths(_section(section))
        if relative.endswith(".md")
    }
    live_markdown = {
        path
        for path in DOCS.rglob("*.md")
        if not any(
            part in {"archive", "evidence", "change-admission"}
            for part in path.relative_to(DOCS).parts
        )
    }

    assert live_markdown == classified


def test_archive_collections_and_immutable_record_roots_remain_separate() -> None:
    archive_paths = _paths(_section("archive_collections"))
    record_paths = _paths(_section("immutable_records"))

    assert archive_paths
    assert record_paths == ("docs/evidence/", "docs/change-admission/")
    for relative in archive_paths + record_paths:
        assert (ROOT / relative).is_dir(), relative
    assert "semantic_authority: false" in _section("immutable_records")

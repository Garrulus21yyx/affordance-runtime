from __future__ import annotations

import re
import subprocess
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

M45_STATUS_PROJECTIONS = (
    ROOT_INDEX,
    DOCS_INDEX,
    CURRENT_PLAN,
    DOCS / "project-plan.md",
    DOCS / "benchmark-plan.md",
    EVOLUTION_PLAN,
)

M45_B_STATUS = (
    "INTEGRATED_NON_DEFAULT",
    "REOPENED_CONVERGENCE_REVIEW",
    "IMPLEMENTED_NOT_VERIFIED",
)
M45_C_STATUS = (
    "COMPLETE_DIAGNOSTIC",
    "EVIDENCE_VALID_AT_4924CE6",
    "FORMAL_EXIT_NOT_ATTESTED",
    "PERFORMANCE_NOT_CLAIMED",
    "GENERALIZATION_NOT_CLAIMED",
)
M46_STATUS = (
    "M4.6",
    "IN_PROGRESS",
    "COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE",
    "M4.6-B",
    "COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE",
    "M4.6-C",
    "NEXT",
)

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
    assert "P5-M4.5-A acquisition lifecycle: COMPLETE_NON_DEFAULT" in text
    assert all(marker in text for marker in M45_B_STATUS)
    assert all(marker in text for marker in M45_C_STATUS)
    assert all(marker in text for marker in M46_STATUS)


def test_current_queue_orders_short_loop_closure_before_long_horizon() -> None:
    text = CURRENT_PLAN.read_text(encoding="utf-8")

    markers = (
        "P5-M4.5-A observation acquisition lifecycle — complete",
        "P5-M4.5-B control/failure contract — reopened convergence review",
        "P5-M4.5-C same-profile diagnostic — complete diagnostic evidence",
        "P5-M4.6 evidence-directed remediation — in progress",
        "## Gates after M4.6",
        "VerifiedTaskState evidence promotion",
    )
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "separate clean `83dc4fa` run at 4/60" in text


def test_m45_current_status_has_one_authoritative_source_and_consistent_projections() -> None:
    manifest = _manifest_text()
    status_text = IMPLEMENTATION_STATUS.read_text(encoding="utf-8")

    assert (
        "current_code_truth: docs/implementation-status.md" in manifest
    )
    assert status_text.count("Current reviewed M4.5-B closure SHA:") == 1
    assert all(
        marker in status_text
        for marker in (*M45_B_STATUS, *M45_C_STATUS, *M46_STATUS)
    )

    for path in M45_STATUS_PROJECTIONS:
        text = path.read_text(encoding="utf-8")
        assert all(marker in text for marker in M45_B_STATUS), path
        assert all(marker in text for marker in M45_C_STATUS), path
        assert all(marker in text for marker in M46_STATUS), path


def test_m45_open_b_does_not_rewrite_completed_diagnostic_or_reviewed_sha() -> None:
    text = IMPLEMENTATION_STATUS.read_text(encoding="utf-8")
    reviewed = re.search(
        r"Current reviewed M4\.5-B closure SHA:\*\* `([^`]+)`",
        text,
    )

    assert reviewed is not None
    assert "REOPENED_CONVERGENCE_REVIEW" in text
    assert "IMPLEMENTED_NOT_VERIFIED" in text
    assert all(marker in text for marker in M45_C_STATUS)
    assert "BLOCKED_BY_M4_5_B_CONVERGENCE" not in text
    assert reviewed.group(1) == "NONE"


def test_m45_c_run_and_m46_remediation_identities_are_not_conflated() -> None:
    attribution = (
        DOCS / "reviews" / "2026-08-11-p5-m4-5-miniwob-60-diagnostic.md"
    ).read_text(encoding="utf-8")
    remediation = (
        DOCS
        / "reviews"
        / "2026-08-11-p5-m4-6-evidence-directed-short-loop-remediation.md"
    ).read_text(encoding="utf-8")

    run_sha = "4924ce61748d8efdec4fcc6de494acf8a9f224cc"
    archive_sha = "5f8d6acf3700831a05d73f93a5c66488a6298fd7"
    run_id = "miniwob-60:e9551acfcd31466e91481ee5923fc9af"
    for text in (attribution, remediation):
        assert run_sha in text
        assert archive_sha in text
        assert run_id in text
        assert "generalization" in text.casefold()
    assert "docs-only" in remediation
    assert "Implementation SHA" in remediation
    assert "Verification run ID" in remediation
    assert "must never be edited or backfilled" in remediation


def test_normative_architecture_does_not_override_implementation_status() -> None:
    text = AUTHORITATIVE_ARCHITECTURE.read_text(encoding="utf-8")

    assert "Implementation truth:" in text
    assert "Current reviewed M4.5-B closure SHA" not in text
    assert "VERIFIED_CLOSED" not in text


def test_reviewed_sha_if_present_is_clean_committed_head() -> None:
    text = IMPLEMENTATION_STATUS.read_text(encoding="utf-8")
    match = re.search(
        r"Current reviewed M4\.5-B closure SHA:\*\* `([^`]+)`",
        text,
    )
    assert match is not None
    reviewed = match.group(1)
    if reviewed == "NONE":
        return

    resolved = subprocess.run(
        ("git", "rev-parse", "--verify", f"{reviewed}^{{commit}}"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ("git", "status", "--porcelain"), cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout
    assert resolved == head
    assert not dirty


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

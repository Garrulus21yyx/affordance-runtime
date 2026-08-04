from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs" / "affordance-runtime-deep-dive"
AUDIT = SITE / "architecture-modification-audit.md"
BASELINE = "786857f8fb61aa99f2c7e6a23eb8225957e1438b"
PUBLIC_BASE = "https://garrulus21yyx.github.io/affordance-runtime"

OPINION_IDS = [*(f"OP-{index:02d}" for index in range(25))]
KEEP_IDS = [*(f"KEEP-{index:02d}" for index in range(1, 6))]
FLAT_IDS = [*(f"FLAT-{index:02d}" for index in range(1, 6))]
PRIORITY_IDS = [
    *(f"P0-{index}" for index in range(1, 7)),
    *(f"P1-{index}" for index in range(1, 6)),
    *(f"P2-{index}" for index in range(1, 6)),
    *(f"P3-{index}" for index in range(1, 4)),
]
CHAIN_IDS = [*(f"CHAIN-{index:02d}" for index in range(1, 12))]
PAGE_IDS = [
    "PAGE-INTAKE",
    "PAGE-PLANNING",
    "PAGE-PERCEPTION",
    "PAGE-VERIFICATION",
    "PAGE-CONTEXT",
    "PAGE-AGENT-LOOP",
]
FINAL_IDS = [
    *(f"FINAL-ROUNDTRIP-{index:02d}" for index in range(1, 5)),
    "FINAL-PRINCIPLE",
]
REQUIRED_AUDIT_IDS = (
    OPINION_IDS
    + KEEP_IDS
    + FLAT_IDS
    + PRIORITY_IDS
    + CHAIN_IDS
    + PAGE_IDS
    + FINAL_IDS
)

DETAIL_ANCHORS = {
    "entrypoints.html": [
        "01-a-external-request",
        "01-b-run-request",
        "01-c-task-tools",
        "01-loss-ledger",
    ],
    "intake.html": [
        "02-a-source-ledger",
        "02-b-intent-draft",
        "02-c-canonical-obligations",
        "02-d-task-spec-admission",
        "02-loss-ledger",
    ],
    "planning.html": [
        "03-a-plan-candidate",
        "03-b-plan-authority",
        "03-c-planning-request",
        "03-d-action-choice",
        "03-loss-ledger",
    ],
    "agent-loop.html": [
        "04-a-stage-input",
        "04-b-stage-result",
        "04-c-runtime-commit",
        "04-d-loop-directive",
        "04-loss-ledger",
    ],
    "perception-action.html": [
        "05-a-browser-snapshot",
        "05-b-unified-observation",
        "05-c-grounding-choice",
        "05-d-action-contract",
        "05-e-execution-receipt",
        "05-loss-ledger",
    ],
    "verification.html": [
        "06-a-verification-report",
        "06-b-action-effect",
        "06-c-step-completion",
        "06-d-task-completion",
        "06-loss-ledger",
    ],
    "recovery.html": [
        "07-a-failure-envelope",
        "07-b-recovery-owner",
        "07-c-recovery-outcome",
        "07-d-uncertain-effect",
        "07-loss-ledger",
    ],
    "context.html": [
        "08-a-planning-request",
        "08-b-planner-context",
        "08-c-context-compaction",
        "08-d-history-externalization",
        "08-loss-ledger",
    ],
    "evidence.html": [
        "09-a-trace-dag",
        "09-b-artifacts",
        "09-c-benchmark",
        "09-d-skill-evolution",
        "09-loss-ledger",
    ],
}


class IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")


def html_ids(path: Path) -> list[str]:
    parser = IdParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.ids


def test_audit_contains_every_source_opinion_id() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    missing = [item for item in REQUIRED_AUDIT_IDS if f"`{item}`" not in text]
    assert not missing, f"missing audit IDs: {missing}"


def test_audit_links_every_stable_detail_anchor() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    missing = [
        f"{filename}#{anchor}"
        for filename, anchors in DETAIL_ANCHORS.items()
        for anchor in anchors
        if f"{PUBLIC_BASE}/{filename}#{anchor}" not in text
    ]
    assert not missing, f"missing public anchor mappings: {missing}"


def test_detail_pages_expose_unique_stable_anchors() -> None:
    for filename, required in DETAIL_ANCHORS.items():
        ids = html_ids(SITE / filename)
        assert len(ids) == len(set(ids)), f"duplicate IDs in {filename}"
        missing = set(required) - set(ids)
        assert not missing, f"missing anchors in {filename}: {missing}"


def test_overview_separates_current_and_proposed_architecture() -> None:
    text = (SITE / "index.html").read_text(encoding="utf-8")
    ids = html_ids(SITE / "index.html")
    required = {
        "current-architecture",
        "proposed-architecture",
        "architecture-diff",
        "modification-audit",
    }
    assert required <= set(ids)
    assert "CURRENT · 当前实现" in text
    assert "PROPOSED · 建议目标（尚未实现）" in text
    assert "StepSpec → legacy SubgoalSpec → StepSpec" in text
    assert "TaskCompletionVerifier" in text


def test_audit_preserves_fact_baseline_and_status_vocabulary() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    assert BASELINE in text
    assert f"/blob/{BASELINE}/src/affordance_runtime/" in text
    for status in ("CURRENT", "KEEP", "GAP", "PROPOSED", "DEFERRED"):
        assert f"`{status}`" in text
    assert "建议目标不是当前实现" in text


def test_named_pages_distinguish_current_facts_from_targets() -> None:
    expected = {
        "intake.html": ("raw-text", "TaskSpecAuthority"),
        "planning.html": ("legacy SubgoalSpec", "TaskPlan&lt;StepSpec&gt;"),
        "perception-action.html": ("PlannerObservationView", "Runtime candidate space"),
        "verification.html": ("两条窄机制", "completion expression"),
        "context.html": ("PlannerContext", "pure provider serializer"),
        "agent-loop.html": ("REUSE_LATEST_OBSERVATION", "建议目标"),
    }
    for filename, markers in expected.items():
        text = (SITE / filename).read_text(encoding="utf-8")
        assert all(marker in text for marker in markers), (filename, markers)

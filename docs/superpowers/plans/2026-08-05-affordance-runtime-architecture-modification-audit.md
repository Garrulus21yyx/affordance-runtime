# Affordance Runtime Architecture Modification Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Produce a complete Chinese Markdown audit of the supplied architecture modification opinion, map every source point to exact live-page anchors and baseline code evidence, and show the current and proposed architectures side by side on the GitHub Pages overview.

**Architecture:** Keep the implementation baseline fixed at `786857f8fb61aa99f2c7e6a23eb8225957e1438b`. Add a traceability-first Markdown report as the canonical opinion audit, stable anchors to the existing nine detail pages, a clearly labelled CURRENT/PROPOSED comparison in the overview, and narrowly scoped factual corrections on the six pages named by the opinion. A documentation test enforces coverage IDs, anchor existence, state labels, baseline links, and the separation between current facts and proposals.

**Tech Stack:** Static HTML5, existing CSS/JavaScript, Markdown, Python standard-library HTML parsing, pytest, Ruff, Playwright, GitHub Pages.

---

## File map

- Create `docs/affordance-runtime-deep-dive/architecture-modification-audit.md`: canonical detailed opinion audit and coverage ledger.
- Create `tests/test_architecture_modification_audit.py`: deterministic completeness, anchor, status-label and fixed-baseline checks.
- Modify `docs/affordance-runtime-deep-dive/index.html`: current/proposed architecture maps, per-layer comparison, report entry link and stable overview anchors.
- Modify `docs/affordance-runtime-deep-dive/styles.css`: current/proposed labels, architecture comparison layout, anchor scroll offset and mobile containment.
- Modify all nine detail HTML files: add stable conversion-block and loss-ledger IDs.
- Modify six detail HTML files (`intake.html`, `planning.html`, `perception-action.html`, `verification.html`, `context.html`, `agent-loop.html`): add narrowly scoped current/proposed correction notes.
- Modify `docs/affordance-runtime-deep-dive/README.md`: document the new audit, anchor stability and fact/proposal maintenance rules.

## Canonical identifier sets

The implementation and tests use these exact source-opinion IDs:

```text
OP-00 OP-01 OP-02 OP-03 OP-04 OP-05 OP-06 OP-07 OP-08 OP-09
OP-10 OP-11 OP-12 OP-13 OP-14 OP-15 OP-16 OP-17 OP-18 OP-19
OP-20 OP-21 OP-22 OP-23 OP-24

KEEP-01 KEEP-02 KEEP-03 KEEP-04 KEEP-05
FLAT-01 FLAT-02 FLAT-03 FLAT-04 FLAT-05
P0-1 P0-2 P0-3 P0-4 P0-5 P0-6
P1-1 P1-2 P1-3 P1-4 P1-5
P2-1 P2-2 P2-3 P2-4 P2-5
P3-1 P3-2 P3-3
CHAIN-01 CHAIN-02 CHAIN-03 CHAIN-04 CHAIN-05 CHAIN-06
CHAIN-07 CHAIN-08 CHAIN-09 CHAIN-10 CHAIN-11
PAGE-INTAKE PAGE-PLANNING PAGE-PERCEPTION PAGE-VERIFICATION
PAGE-CONTEXT PAGE-AGENT-LOOP
FINAL-ROUNDTRIP-01 FINAL-ROUNDTRIP-02 FINAL-ROUNDTRIP-03
FINAL-ROUNDTRIP-04 FINAL-PRINCIPLE
```

The detail pages use these exact stable IDs:

```text
entrypoints.html: 01-a-external-request, 01-b-run-request, 01-c-task-tools, 01-loss-ledger
intake.html: 02-a-source-ledger, 02-b-intent-draft, 02-c-canonical-obligations, 02-d-task-spec-admission, 02-loss-ledger
planning.html: 03-a-plan-candidate, 03-b-plan-authority, 03-c-planning-request, 03-d-action-choice, 03-loss-ledger
agent-loop.html: 04-a-stage-input, 04-b-stage-result, 04-c-runtime-commit, 04-d-loop-directive, 04-loss-ledger
perception-action.html: 05-a-browser-snapshot, 05-b-unified-observation, 05-c-grounding-choice, 05-d-action-contract, 05-e-execution-receipt, 05-loss-ledger
verification.html: 06-a-verification-report, 06-b-action-effect, 06-c-step-completion, 06-d-task-completion, 06-loss-ledger
recovery.html: 07-a-failure-envelope, 07-b-recovery-owner, 07-c-recovery-outcome, 07-d-uncertain-effect, 07-loss-ledger
context.html: 08-a-planning-request, 08-b-planner-context, 08-c-context-compaction, 08-d-history-externalization, 08-loss-ledger
evidence.html: 09-a-trace-dag, 09-b-artifacts, 09-c-benchmark, 09-d-skill-evolution, 09-loss-ledger
index.html: current-architecture, proposed-architecture, architecture-diff, modification-audit
```

---

### Task 1: Add the failing traceability contract

**Files:**
- Create: `tests/test_architecture_modification_audit.py`
- Test: `tests/test_architecture_modification_audit.py`

- [x] **Step 1: Write a documentation contract that enumerates every required source ID and anchor**

Create the test with Python standard-library parsing. Use these constants and checks verbatim:

```python
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
REQUIRED_AUDIT_IDS = OPINION_IDS + KEEP_IDS + FLAT_IDS + PRIORITY_IDS + CHAIN_IDS + PAGE_IDS + FINAL_IDS

DETAIL_ANCHORS = {
    "entrypoints.html": ["01-a-external-request", "01-b-run-request", "01-c-task-tools", "01-loss-ledger"],
    "intake.html": ["02-a-source-ledger", "02-b-intent-draft", "02-c-canonical-obligations", "02-d-task-spec-admission", "02-loss-ledger"],
    "planning.html": ["03-a-plan-candidate", "03-b-plan-authority", "03-c-planning-request", "03-d-action-choice", "03-loss-ledger"],
    "agent-loop.html": ["04-a-stage-input", "04-b-stage-result", "04-c-runtime-commit", "04-d-loop-directive", "04-loss-ledger"],
    "perception-action.html": ["05-a-browser-snapshot", "05-b-unified-observation", "05-c-grounding-choice", "05-d-action-contract", "05-e-execution-receipt", "05-loss-ledger"],
    "verification.html": ["06-a-verification-report", "06-b-action-effect", "06-c-step-completion", "06-d-task-completion", "06-loss-ledger"],
    "recovery.html": ["07-a-failure-envelope", "07-b-recovery-owner", "07-c-recovery-outcome", "07-d-uncertain-effect", "07-loss-ledger"],
    "context.html": ["08-a-planning-request", "08-b-planner-context", "08-c-context-compaction", "08-d-history-externalization", "08-loss-ledger"],
    "evidence.html": ["09-a-trace-dag", "09-b-artifacts", "09-c-benchmark", "09-d-skill-evolution", "09-loss-ledger"],
}


class IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
    missing = [item for item in REQUIRED_AUDIT_IDS if text.count(f"`{item}`") == 0]
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
        assert not (set(required) - set(ids)), f"missing anchors in {filename}: {set(required) - set(ids)}"


def test_overview_separates_current_and_proposed_architecture() -> None:
    text = (SITE / "index.html").read_text(encoding="utf-8")
    ids = html_ids(SITE / "index.html")
    assert {"current-architecture", "proposed-architecture", "architecture-diff", "modification-audit"} <= set(ids)
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
```

- [x] **Step 2: Run the contract and confirm that the missing deliverables fail**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_architecture_modification_audit.py -q
```

Expected: failures because `architecture-modification-audit.md`, the stable detail anchors and the overview comparison do not yet exist.

- [x] **Step 3: Commit the failing contract**

```bash
git add tests/test_architecture_modification_audit.py
git commit -m "test architecture audit traceability"
```

---

### Task 2: Add stable anchors without changing chapter meaning

**Files:**
- Modify: `docs/affordance-runtime-deep-dive/entrypoints.html`
- Modify: `docs/affordance-runtime-deep-dive/intake.html`
- Modify: `docs/affordance-runtime-deep-dive/planning.html`
- Modify: `docs/affordance-runtime-deep-dive/agent-loop.html`
- Modify: `docs/affordance-runtime-deep-dive/perception-action.html`
- Modify: `docs/affordance-runtime-deep-dive/verification.html`
- Modify: `docs/affordance-runtime-deep-dive/recovery.html`
- Modify: `docs/affordance-runtime-deep-dive/context.html`
- Modify: `docs/affordance-runtime-deep-dive/evidence.html`
- Modify: `docs/affordance-runtime-deep-dive/styles.css`
- Test: `tests/test_architecture_modification_audit.py`

- [x] **Step 1: Assign every conversion block the canonical ID from the file map**

For each `<article class="conversion-block">`, add the matching `id`, for example:

```html
<article class="conversion-block" id="02-a-source-ledger">
```

For each `<section class="loss-ledger">`, add the matching page loss-ledger ID, for example:

```html
<section class="loss-ledger" id="02-loss-ledger">
```

Use exactly the complete anchor list in “Canonical identifier sets”; do not rename visible step IDs or headings.

- [x] **Step 2: Make fixed-header anchor navigation readable**

Add the following CSS:

```css
.conversion-block,
.loss-ledger,
.architecture-view,
.architecture-diff {
  scroll-margin-top: 1.5rem;
}
```

- [x] **Step 3: Run the anchor test**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_architecture_modification_audit.py::test_detail_pages_expose_unique_stable_anchors -q
```

Expected: `1 passed`.

- [x] **Step 4: Check HTML ID uniqueness across all pages**

Run:

```bash
PYTHONPATH=src python - <<'PY'
from html.parser import HTMLParser
from pathlib import Path

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
    def handle_starttag(self, tag, attrs):
        value = dict(attrs).get("id")
        if value:
            self.ids.append(value)

for path in sorted(Path("docs/affordance-runtime-deep-dive").glob("*.html")):
    parser = Parser()
    parser.feed(path.read_text(encoding="utf-8"))
    duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    assert not duplicates, (path, duplicates)
print("HTML ID PASS")
PY
```

Expected: `HTML ID PASS`.

- [x] **Step 5: Commit the anchor contract**

```bash
git add docs/affordance-runtime-deep-dive/*.html docs/affordance-runtime-deep-dive/styles.css
git commit -m "add stable architecture report anchors"
```

---

### Task 3: Write the complete traceability-first Markdown audit

**Files:**
- Create: `docs/affordance-runtime-deep-dive/architecture-modification-audit.md`
- Test: `tests/test_architecture_modification_audit.py`

- [x] **Step 1: Create the report front matter and evidence rules**

The document must begin with these sections and statements:

```markdown
# Affordance Runtime 架构修改意见逐条审计与页面对照

> 事实基线：`agent/migrate-runtime-components @ 786857f8fb61aa99f2c7e6a23eb8225957e1438b`
>
> 本文区分当前事实与目标建议。**建议目标不是当前实现**；意见要求保留的安全边界也不是“需要扁平化的冗余”。

## 阅读规则

- `CURRENT`：固定基线中可由代码证明的事实。
- `KEEP`：意见明确要求保留的当前边界。
- `GAP`：意见指出的当前缺口或有损往返。
- `PROPOSED`：意见建议的目标结构，尚未实现。
- `DEFERRED`：意见明确后置的能力。

## 审计总览
```

The overview table must summarize all 25 `OP-*` items with columns: ID, faithful opinion, status, exact public page anchor, baseline code evidence, and disposition.

- [x] **Step 2: Write `OP-00` through `OP-08` without collapsing intake and planning distinctions**

Use one H3 section per ID and the fixed ten-field template from the design spec. Preserve these subjects exactly:

```text
OP-00 external request and dual ingress
OP-01 SourceLedger and clause-split limits
OP-02 natural language to IntentProposal and repeated interpretation
OP-03 composable SemanticExpr instead of closed scalar
OP-04 TaskSpecAuthority admission boundary
OP-05 TaskSpec compression into requirement authority
OP-06 task-level versus step-level planning
OP-07 StepSpec → legacy SubgoalSpec → StepSpec loss
OP-08 multiple terminal obligations and composite completion
```

Map them to `entrypoints.html#01-b-run-request`, `intake.html#02-a-source-ledger`, `intake.html#02-b-intent-draft`, `intake.html#02-c-canonical-obligations`, `intake.html#02-d-task-spec-admission`, `planning.html#03-a-plan-candidate`, `planning.html#03-b-plan-authority`, and `verification.html#06-d-task-completion` as applicable. Every source link must include the full baseline SHA.

- [x] **Step 3: Write `OP-09` through `OP-16` and preserve candidate-space versus prompt-space separation**

Preserve these subjects exactly:

```text
OP-09 current perception order versus proposed canonical order
OP-10 multi-source conflict loss in planner projection
OP-11 PlanningRequest → PlannerContext duplicate projection
OP-12 strict planner versus historical compatibility planner
OP-13 insufficient semantics in N-choice selection
OP-14 keep the 0/1/N ActionChoice model and refine failure ownership/open escape hatch
OP-15 keep grounding and add predicate resolution rather than raw-text regex
OP-16 keep ActionContract and execution boundaries; split internal services behind a façade
```

Map to `perception-action.html#05-a-browser-snapshot`, `#05-b-unified-observation`, `#05-c-grounding-choice`, `context.html#08-a-planning-request`, `#08-b-planner-context`, `planning.html#03-d-action-choice`, `perception-action.html#05-d-action-contract`, and `#05-e-execution-receipt`.

- [x] **Step 4: Write `OP-17` through `OP-24` and separate effect, step and task evidence**

Preserve these subjects exactly:

```text
OP-17 keep fresh post-action observation and independent verifier ladder
OP-18 reuse post-action observation instead of immediate duplicate capture
OP-19 distinguish current-state truth from causal attribution
OP-20 current TaskCompletionVerifier closure gap and over-strong page wording
OP-21 Evidence Validity Policy
OP-22 ModelVerifier only as Evidence Provider
OP-23 keep recovery architecture and refine owner classification
OP-24 Trace, Artifact, Benchmark and Skill Evolution stay outside synchronous completion authority
```

Map to `verification.html#06-a-verification-report`, `#06-c-step-completion`, `#06-d-task-completion`, `agent-loop.html#04-d-loop-directive`, `recovery.html#07-b-recovery-owner`, and all relevant `evidence.html` anchors.

- [x] **Step 5: Add the complete non-OP ledgers**

Add dedicated sections whose rows contain every ID from these groups and preserve the supplied meaning:

```text
KEEP-01 untrusted IntentProposal → admitted TaskSpec
KEEP-02 untrusted PlanCandidate → admitted TaskPlan
KEEP-03 Planner ActionProposal → Runtime ActionContract
KEEP-04 ExecutionReceipt → independent VerificationResult
KEEP-05 VerificationResult → Runtime TaskProgress

FLAT-01 LLM graph + Runtime graph + raw-text regex parser
FLAT-02 obligation → StepSpec → SubgoalSpec → StepSpec
FLAT-03 BrowserSnapshot → bounded PlannerObservation → UnifiedObservation → ActionChoice
FLAT-04 PlanningRequest → PlannerContext → provider JSON plus repeated blobs
FLAT-05 terminal-readiness compatibility + progress completion + latest-report completion
```

Then add exact P0, P1, P2 and P3 ledgers using every priority ID from the canonical set. Do not merge `P0-2` and `P0-3`: composable semantic support must precede deletion of regex normalizers.

- [x] **Step 6: Add the 11-stage proposed production chain and six page dispositions**

Write `CHAIN-01` through `CHAIN-11` in the same order as the opinion:

```text
external input; source and one semantic interpretation; TaskSpec authority;
task-level planning; perception; current-step precheck; step-level decision;
contract and execution; post-action proof; step/task progress; unique task completion authority
```

Write `PAGE-INTAKE`, `PAGE-PLANNING`, `PAGE-PERCEPTION`, `PAGE-VERIFICATION`, `PAGE-CONTEXT`, and `PAGE-AGENT-LOOP` as a page-change matrix. Add `FINAL-ROUNDTRIP-01` through `FINAL-ROUNDTRIP-04` and `FINAL-PRINCIPLE` verbatim in meaning: natural language once, one lossless requirement/criterion representation, TaskPlan directly stores StepSpec, Runtime uses full UnifiedObservation, and one post-action observation proves effect/step/task.

- [x] **Step 7: Add a machine-readable coverage ledger**

End the document with a table containing one row for every required source ID. Use columns:

```text
Source ID | Markdown section | Public page anchor | Baseline evidence or “target proposal” | Disposition
```

Do not leave blank cells and do not use placeholder tokens, “同上” or “见前文”.

- [x] **Step 8: Run the Markdown coverage and baseline tests**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/test_architecture_modification_audit.py::test_audit_contains_every_source_opinion_id \
  tests/test_architecture_modification_audit.py::test_audit_links_every_stable_detail_anchor \
  tests/test_architecture_modification_audit.py::test_audit_preserves_fact_baseline_and_status_vocabulary \
  -q
```

Expected: `3 passed`.

- [x] **Step 9: Commit the canonical audit**

```bash
git add docs/affordance-runtime-deep-dive/architecture-modification-audit.md
git commit -m "document architecture modification audit"
```

---

### Task 4: Put current and proposed architectures into the overview

**Files:**
- Modify: `docs/affordance-runtime-deep-dive/index.html`
- Modify: `docs/affordance-runtime-deep-dive/styles.css`
- Test: `tests/test_architecture_modification_audit.py`

- [x] **Step 1: Add a visible link to the detailed Markdown audit**

Add `id="modification-audit"` in Section 02 and a link to the GitHub-rendered Markdown on the source branch. The link label must say “逐条修改意见审计（Markdown）”, and the nearby text must state that implementation facts stay bound to the baseline SHA.

- [x] **Step 2: Render the true current implementation chain**

Add an architecture block with `id="current-architecture"`, class `architecture-view current`, and visible label `CURRENT · 当前实现`. Its chain must include:

```text
UserRequest → SourceLedger → LLMIntentDraft → IntentDraft
→ raw-text semantic normalizers → CanonicalObligationCompiler → TaskSpec
→ PlanCandidate<StepSpec> → TaskPlan<SubgoalSpec> → TaskPlanView<StepSpec>
→ bounded PlannerObservationView → UnifiedObservation → ActionChoice
→ PlanningRequest → PlannerContext → provider JSON
→ ActionContract → ExecutionReceipt → fresh post-action observation → VerificationReport
→ legacy TaskProgress → latest-report TaskCompletionVerifier
```

State explicitly that this is a readable projection of the fixed baseline, not a proposed design.

- [x] **Step 3: Render the proposed 11-stage chain**

Add an architecture block with `id="proposed-architecture"`, class `architecture-view proposed`, and visible label `PROPOSED · 建议目标（尚未实现）`. Render `CHAIN-01` through `CHAIN-11` without deleting the authority boundaries:

```text
UserRequest → SourceLedger → IntentProposal → TaskSpecAuthority → TaskSpec
→ TaskComplexityRouter → PlanCandidate<StepSpec> → TaskPlanAuthority → TaskPlan<StepSpec>
→ canonical UnifiedObservation → StepCompletionPrecheck → ActionChoiceBuilder
→ bounded ChoicePlanningRequest when N choices → ActionContract → ExecutionReceipt
→ reusable post-action UnifiedObservation → verifier ladder → TaskProgress
→ full TaskSpec completion expression → TaskCompletionVerifier → RuntimeCommitter → TaskCompleted
```

- [x] **Step 4: Add a per-layer current/proposed difference table**

Add `id="architecture-diff"` and class `architecture-diff`. Include rows for semantics, TaskSpec, task planning, observation, model context, choice, execution, post-action observation, step evidence, task completion, and offline evidence. Each row must include change type, semantic-loss/authority implication and linked `OP-*` IDs.

- [x] **Step 5: Preserve the three-plane explanation and clarify flattening scope**

Keep data/control/authority planes and add this rule in a warning callout:

```text
扁平化的是重复数据表示和重叠权威所有者；Intent/Plan admission、ActionContract、独立验证、Runtime progress commit 等安全边界必须保留。
```

- [x] **Step 6: Style the comparison without color-only semantics**

Add CSS for `.architecture-comparison`, `.architecture-view`, `.architecture-label`, `.architecture-diff`, `.current`, and `.proposed`. Use borders, headings and explicit text labels; at `max-width: 760px`, stack columns and keep tables inside `.scroll-table`.

- [x] **Step 7: Run the overview separation test**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_architecture_modification_audit.py::test_overview_separates_current_and_proposed_architecture -q
```

Expected: `1 passed`.

- [x] **Step 8: Commit the overview comparison**

```bash
git add docs/affordance-runtime-deep-dive/index.html docs/affordance-runtime-deep-dive/styles.css
git commit -m "compare current and proposed runtime architecture"
```

---

### Task 5: Correct the six named detail pages without rewriting them

**Files:**
- Modify: `docs/affordance-runtime-deep-dive/intake.html`
- Modify: `docs/affordance-runtime-deep-dive/planning.html`
- Modify: `docs/affordance-runtime-deep-dive/perception-action.html`
- Modify: `docs/affordance-runtime-deep-dive/verification.html`
- Modify: `docs/affordance-runtime-deep-dive/context.html`
- Modify: `docs/affordance-runtime-deep-dive/agent-loop.html`
- Modify: `docs/affordance-runtime-deep-dive/styles.css`
- Test: `tests/test_architecture_modification_audit.py`

- [x] **Step 1: Add a reusable current/proposed comparison callout style**

Add `.architecture-note`, `.architecture-note .current-fact`, and `.architecture-note .proposed-target`. Each note must display text labels `当前实现` and `建议目标（尚未实现）`; color may reinforce but never replace the labels.

- [x] **Step 2: Correct intake semantics and authority wording**

Near `#02-b-intent-draft`, `#02-c-canonical-obligations`, and `#02-d-task-spec-admission`, state:

```text
当前实现：LLMIntentDraft / IntentDraft 后仍有 raw-text regex normalizers、CanonicalObligationCompiler、deterministic coverage 和 optional model coverage review。
建议目标（尚未实现）：IntentProposal → TaskSpecAuthority.admit() → TaskSpec；Runtime validates and allocates authority-owned IDs but does not reinterpret raw text.
```

Also state that `PREFIX`/`SUFFIX` exist in intake schema but `compile_requested_effects()` only admits `EXACT` into the canonical obligation path. Do not claim the normalizers are already legacy-disabled.

- [x] **Step 3: Correct the planning authority round trip**

Near `#03-b-plan-authority`, add the exact current chain:

```text
PlanCandidate<StepSpec> → TaskPlanAuthorityBinder._subgoal_from_step() → TaskPlan<SubgoalSpec> → project_state_legacy_task_plan_to_step_view() → TaskPlanView<StepSpec>
```

State that `_subgoal_from_step()` selects `completion_criteria[0]` and stringifies expected values. Mark direct `TaskPlan<StepSpec> + TaskProgress` as proposed, not current.

- [x] **Step 4: Correct perception ordering and candidate-space semantics**

Near `#05-b-unified-observation`, distinguish:

```text
CURRENT: BrowserSnapshot → bounded PlannerObservationView → UnifiedObservation.from_planner_observation() → Runtime ActionChoiceBuilder
PROPOSED: BrowserSnapshot/perception fusion → canonical full UnifiedObservation → Runtime candidate space; a separate bounded PlanningObservationView is only for the model prompt
```

Near `#05-c-grounding-choice`, preserve the opinion’s recommendation to add a predicate resolver rather than more raw-text regex.

- [x] **Step 5: Correct task-completion claims**

Rewrite the transformer and risk text at `#06-d-task-completion` so it says:

```text
当前存在两条窄机制：legacy TaskPlan/PlanProgress 的 TerminalReadinessEvaluator，以及主要依赖最新独立 passed VerificationReport 的 TaskCompletionVerifier。二者都不能等同于对完整 TaskSpec completion expression 的通用 closure 求值。
```

Add the proposed input set `TaskSpec completion expression + TaskProgress evidence index + current observation + evidence validity policy`, and preserve the fact that receipt success alone cannot complete a task.

- [x] **Step 6: Correct context-domain duplication wording**

Near `#08-b-planner-context`, label `PlanningRequest → PlannerContext → model messages` as current. Label `PlanningRequest → pure provider serializer → model messages` as proposed. Keep current compaction behavior in `#08-c-context-compaction`; do not imply `PlannerContext` has already been removed.

- [x] **Step 7: Add post-action observation reuse as a proposal**

Near `#04-d-loop-directive`, state that current flow can capture a post-action snapshot in ProgressStage and then capture again when the next coordinator turn enters PerceptionStage. Show `REUSE_LATEST_OBSERVATION` or `CONTINUE_WITH_OBSERVATION` only as a proposed directive, with recapture retained for loading, conflict, inconclusive verification, targeted perception or timeout.

- [x] **Step 8: Add page-specific marker assertions to the documentation test**

Append this test:

```python
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
```

- [x] **Step 9: Run all documentation contract tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_architecture_modification_audit.py -q
```

Expected: all tests pass.

- [x] **Step 10: Commit the targeted detail corrections**

```bash
git add \
  docs/affordance-runtime-deep-dive/intake.html \
  docs/affordance-runtime-deep-dive/planning.html \
  docs/affordance-runtime-deep-dive/perception-action.html \
  docs/affordance-runtime-deep-dive/verification.html \
  docs/affordance-runtime-deep-dive/context.html \
  docs/affordance-runtime-deep-dive/agent-loop.html \
  docs/affordance-runtime-deep-dive/styles.css \
  tests/test_architecture_modification_audit.py
git commit -m "clarify current and proposed architecture details"
```

---

### Task 6: Document maintenance rules and run complete local verification

**Files:**
- Modify: `docs/affordance-runtime-deep-dive/README.md`
- Test: `tests/test_architecture_modification_audit.py`

- [x] **Step 1: Update maintenance documentation**

Document:

```text
architecture-modification-audit.md is the canonical traceability report for the supplied opinion;
CURRENT/KEEP/GAP/PROPOSED/DEFERRED labels may not be collapsed;
stable detail anchors are public API and must be updated only with redirect-compatible links;
implementation claims and source links remain bound to 786857f8...;
future Runtime changes require a new baseline audit rather than silently changing this report.
```

- [x] **Step 2: Check Markdown for placeholders and missing source IDs**

Run:

```bash
if rg -n 'T[B]D|T[O]DO|待补|稍后填写|同上|见前文' docs/affordance-runtime-deep-dive/architecture-modification-audit.md; then
  exit 1
fi
PYTHONPATH=src python -m pytest tests/test_architecture_modification_audit.py -q
```

Expected: no placeholder matches and all documentation tests pass.

- [x] **Step 3: Validate HTML links, fragments and assets locally**

Run a Python standard-library crawler across all ten HTML pages. It must parse every local `href`, confirm the target file exists, and confirm fragments exist in the target file. Expected final output:

```text
LOCAL LINK PASS: 10 HTML pages
```

- [x] **Step 4: Run syntax and repository verification**

Run:

```bash
node --check docs/affordance-runtime-deep-dive/site.js
ruff check src tests
PYTHONPATH=src python -m pytest -q
git diff --check
```

Expected: JavaScript syntax passes, Ruff passes, all tests pass, and no whitespace errors are reported.

- [x] **Step 5: Run desktop and mobile browser verification**

Serve `docs/affordance-runtime-deep-dive` over HTTP and use Playwright to visit the overview plus nine detail pages at widths 1280 and 320. For every visit assert:

```text
document.documentElement.scrollWidth === window.innerWidth
no console error
current-architecture and proposed-architecture visible on overview
all canonical fragment URLs land on a visible target
```

Expected: `20/20 viewport checks passed` and no console errors.

- [x] **Step 6: Commit maintenance documentation and final test adjustments**

```bash
git add docs/affordance-runtime-deep-dive/README.md tests/test_architecture_modification_audit.py
git commit -m "document architecture audit maintenance"
```

---

### Task 7: Publish and verify GitHub Pages

**Files:**
- No additional source files expected.
- Deploy: subtree rooted at `docs/affordance-runtime-deep-dive` to `gh-pages`.

- [ ] **Step 1: Confirm the source branch is clean and push it**

Run:

```bash
git status -sb
git push origin agent/migrate-runtime-components
```

Expected: only the branch tracking line remains and the push succeeds.

- [ ] **Step 2: Deploy the site subtree to `gh-pages`**

Use the repository’s established subtree deployment procedure from the previous report publication. Confirm the deployed commit contains `architecture-modification-audit.md`, the updated `index.html`, all nine detail pages, CSS and JavaScript.

- [ ] **Step 3: Wait for GitHub Pages to report a successful build**

Query the Pages build API until the deployed commit reports `built` with no error. Do not claim publication merely because `git push` succeeded.

- [ ] **Step 4: Verify public pages and exact anchors**

Fetch the overview, nine detail pages and representative anchors with a cache-busting query. Confirm HTTP 200 and markers for:

```text
CURRENT · 当前实现
PROPOSED · 建议目标（尚未实现）
02-b-intent-draft
03-b-plan-authority
05-b-unified-observation
06-d-task-completion
08-b-planner-context
04-d-loop-directive
```

Expected: all public URLs return 200 and contain the correct current/proposed text.

- [ ] **Step 5: Record completion in this plan and commit the status update**

Mark every completed checkbox, run `git diff --check`, commit only the plan status, and push the source branch. The Pages subtree does not need redeployment for a plan-only change outside the site directory.

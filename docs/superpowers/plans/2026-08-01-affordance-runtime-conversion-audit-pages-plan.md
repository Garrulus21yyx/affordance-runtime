# Affordance Runtime Conversion Audit Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add nine source-anchored conversion-audit detail pages to the existing Affordance Runtime GitHub Pages report without restructuring the overview page.

**Architecture:** Keep `index.html` as the overview and link each core E2E chapter to one standalone HTML page. Every detail page reuses shared CSS/JavaScript and presents a sequence of typed conversion blocks followed by a semantic-loss ledger and previous/next navigation.

**Tech Stack:** Static HTML5, shared CSS, minimal vanilla JavaScript, Python `html.parser` validation, Playwright CLI, GitHub Pages from `gh-pages`.

---

### Task 1: Add the shared conversion-audit visual language

**Files:**
- Modify: `docs/affordance-runtime-deep-dive/styles.css`

- [x] **Step 1: Add detail-page layout classes**

Add styles for `.detail-hero`, `.detail-nav`, `.conversion-block`, `.conversion-arrow`, `.field-map`, `.preserve-loss`, `.loss-ledger`, `.loss-kind`, and `.chapter-link`. Reuse the current palette and typography; do not add dependencies.

- [x] **Step 2: Add responsive behavior**

At widths below 680px, stack conversion input/output panels, keep field tables inside `.scroll-table`, and ensure detail navigation wraps without increasing document `scrollWidth` beyond `innerWidth`.

- [x] **Step 3: Run CSS/HTML static checks**

Run: `git diff --check`

Expected: exit 0.

### Task 2: Create ingress, intake, and planning audit pages

**Files:**
- Create: `docs/affordance-runtime-deep-dive/entrypoints.html`
- Create: `docs/affordance-runtime-deep-dive/intake.html`
- Create: `docs/affordance-runtime-deep-dive/planning.html`

- [x] **Step 1: Write ingress conversions**

Cover `TaskRequest/UserRequest → RunRequest`, `RunRequest → TaskRuntimeService/TaskRunner`, and external task tools → internal run call. Map goal, IDs, target, constraints, capabilities, source refs, and omitted primitive GUI authority. Explain envelope normalization and mismatch rejection.

- [x] **Step 2: Write intake conversions**

Cover `UserRequest → SourceLedger → LLMIntentDraft/IntentDraft → canonical obligations → TaskSpec`. Distinguish clause-splitting loss, model interpretation loss, deterministic rejection, canonical re-identification, and coverage validation.

- [x] **Step 3: Write planning conversions**

Cover `TaskSpec obligations → PlanCandidate → TaskPlan/StepSpec`, `StateKernel + BrowserSnapshot → PlanningRequest`, and `PlanningRequest → ActionChoice → PlannerProposal`. Explain plan granularity loss, bounded observation loss, choice-set exclusion, and identity validation.

- [x] **Step 4: Check required audit fields**

Run a Python parser asserting each page contains `输入`, `转换`, `输出`, `保留`, `语义损失`, `风险`, `防护`, and `失败出口` text markers.

Expected: all three pages pass.

### Task 3: Create loop, perception/action, and verification audit pages

**Files:**
- Create: `docs/affordance-runtime-deep-dive/agent-loop.html`
- Create: `docs/affordance-runtime-deep-dive/perception-action.html`
- Create: `docs/affordance-runtime-deep-dive/verification.html`

- [x] **Step 1: Write loop conversions**

Cover `RuntimeStateSnapshot → StageInput → StageResult/RuntimeTransition → RuntimeCommitter → StateKernel + Trace events`. Explain detached-projection loss, transition-only write authority, event projection, and branch/failure directives.

- [x] **Step 2: Write perception/action conversions**

Cover raw DOM/accessibility/visual/device signals → `BrowserSnapshot`, snapshot → `UnifiedObservation`, `InteractionIntent → GroundingCandidate/ActionChoice`, proposal → `ActionContract`, and executor result → `ExecutionReceipt`. Explain fusion conflict, target normalization, candidate filtering, snapshot binding, and receipt limitations.

- [x] **Step 3: Write verification conversions**

Cover receipt + post-observation → verifier evidence/report, report → action-effect/step/task decisions, and terminal candidate → readiness/terminal commit. Explain observation blind spots, evidence attribution loss, UNKNOWN preservation, and why receipt success is not task success.

- [x] **Step 4: Check required audit fields**

Run the same marker parser for all three pages.

Expected: all three pages pass.

### Task 4: Create recovery, context, and evidence audit pages

**Files:**
- Create: `docs/affordance-runtime-deep-dive/recovery.html`
- Create: `docs/affordance-runtime-deep-dive/context.html`
- Create: `docs/affordance-runtime-deep-dive/evidence.html`

- [x] **Step 1: Write recovery conversions**

Cover raw phase error → `FailureEnvelope`, envelope → `RecoveryDecision/owner`, decision → changed command/outcome, and uncertain receipt → effect status. Explain debug normalization, semantic hashing, failure-family collapse, attempted-strategy retention, and no-op rejection.

- [x] **Step 2: Write context conversions**

Cover StateKernel/TaskSpec/snapshot → `PlannerContext`, context → serialized model messages, and context → compacted context. List every bounded collection, hashed/externalized reference, critical invariant retained, and the absence of general conversation-history summarization.

- [x] **Step 3: Write evidence conversions**

Cover stage events → `TraceNode/TraceDag`, runtime objects → artifacts/JSONL, verified traces → mined TaskSkill candidate, and replay reports → promotion decision. Explain payload freezing, serialization reduction, artifact indirection, benchmark aggregation, quarantine, and digest binding.

- [x] **Step 4: Check required audit fields**

Run the same marker parser for all three pages.

Expected: all three pages pass.

### Task 5: Connect the overview and validate the static site

**Files:**
- Modify: `docs/affordance-runtime-deep-dive/index.html`
- Modify: `docs/affordance-runtime-deep-dive/README.md`

- [x] **Step 1: Add chapter links**

Add one `.chapter-link` after the introductory content in sections `entrypoints`, `intake`, `planning`, `agent-loop`, `perception-action`, `verification`, `recovery`, `context`, and `evidence`. Link to the corresponding detail page without changing existing section order or prose.

- [x] **Step 2: Update maintenance documentation**

Document the nine pages, the shared audit template, and the rule that overview and detail links must remain synchronized.

- [x] **Step 3: Validate every HTML file and link**

Run a Python `html.parser` script over `docs/affordance-runtime-deep-dive/*.html` checking duplicate IDs, local resources, local page links, fragments, detail navigation, and required audit markers.

Expected: zero errors.

- [x] **Step 4: Validate desktop and mobile rendering**

Serve `docs`, open overview and all detail pages with Playwright, assert console error count 0 and `document.documentElement.scrollWidth === innerWidth` at 1280px and 320px.

Expected: all ten pages pass.

### Task 6: Verify, commit, publish, and inspect the live site

**Files:**
- Verify: all changed report files

- [x] **Step 1: Run repository verification**

Run: `PYTHONPATH=src python -m pytest -q && ruff check src tests && git diff --check`

Expected: 1459 tests pass, Ruff passes, diff check exits 0.

- [ ] **Step 2: Commit and push source changes**

Stage only the report pages, shared CSS, overview, README, design, and this plan. Commit with `add conversion audit chapter pages` and push `agent/migrate-runtime-components`.

- [ ] **Step 3: Publish the static subtree**

Run `git subtree split --prefix docs/affordance-runtime-deep-dive HEAD`, push that commit to `refs/heads/gh-pages`, and wait for the Pages build to reach `built`.

- [ ] **Step 4: Verify public URLs**

Fetch the root page and every detail page under `https://garrulus21yyx.github.io/affordance-runtime/`. Require HTTP 200 and verify each page-specific `<title>` plus semantic-loss ledger marker.

Expected: all ten public URLs pass.

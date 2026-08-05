# Semantic Authority and Task Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Production code changes and subagent delegation are outside this plan.

**Goal:** Amend the existing Task Contract-centered authority so source text has bounded read-only contextual use without downstream semantic-authority expansion, while closing requirement identity, dependency, choice-presentation, and required-output semantics.

**Architecture:** The first supplied review is the baseline; the second review overrides only its strict raw-text firewall. The result is one semantic admission owner, a bounded non-authoritative `SourceContextView` for named semantic consumers, a raw-text-free execution/evaluation chain, canonical requirement IDs, single-location dependency semantics, complete choice presentation, and required-output completion closure. The existing architecture and evolution plan remain the only two authorities.

**Tech Stack:** Markdown contracts, Python/pytest governance tests, repository-relative links, Mermaid CLI validation.

---

### Task 1: Freeze the merged amendment in failing governance tests

**Files:**

- Modify: `tests/test_horizontal_architecture_governance.py`

- [x] Add assertions for `NLI-01` through `NLI-08`, explicitly rejecting the strict raw-text-firewall wording.
- [x] Add assertions for `REQ-01` through `REQ-05`, `DEP-01` through `DEP-03`, `CHOICE-13`, and `OUT-01` through `OUT-03` in both current authority documents.
- [x] Add contract-shape assertions for `SourceContextView`, `AnchoredExcerpt`, `TaskRequirement`, `requirement_refs`, bounded `ChoicePresentation`, `TaskSpecGap`, and required-output materialization.
- [x] Run the focused test and confirm it fails before documentation changes.

### Task 2: Amend the authoritative architecture in place

**Files:**

- Modify: `docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md`

- [x] Add a three-layer Semantic Authority Boundary: meaning write authority, bounded read-only semantic context, and raw-text-free execution authority.
- [x] Define `SourceContextView` and `AnchoredExcerpt`, including the exact consumer allowlist and explicitly non-authoritative status.
- [x] Define `TaskRequirement`, stable canonical IDs, TaskSpec reference containers, StepSpec `requirement_refs`, and TaskPlanAuthority coverage rejection.
- [x] State the single semantic-value dependency and TaskPlan-only execution-order rules.
- [x] Complete `ChoicePresentation` bounded semantic fields without execution bindings or hidden IDs.
- [x] Make materialized, source-bound required outputs a TaskCompleted condition.
- [x] Add the complete `NLI`, `REQ`, `DEP`, `CHOICE-13`, and `OUT` invariant ledgers and behavioral gates.

### Task 3: Synchronize the authoritative evolution plan

**Files:**

- Modify: `docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md`

- [x] Record the merged review decision and precedence of the second review over the strict firewall language.
- [x] Add migration slices for SourceContextView/read-set enforcement, TaskRequirement identity, dependency cleanup, ChoicePresentation, and output closure.
- [x] Add deletion/isolation gates preventing raw-text flow into action construction, gates, execution, evaluation, and commit.
- [x] Map all new invariant IDs to implementation slices and acceptance evidence.

### Task 4: Synchronize maintained contracts, queue, and status

**Files:**

- Modify: `docs/task-intake-and-planner.md`
- Modify: `docs/responsibility-containment-boundary.md`
- Modify: `docs/architecture-governance-track.md`
- Modify: `docs/orchestration-and-feedback.md`
- Modify: `docs/trace-and-evaluation.md`
- Modify: `docs/current-implementation-plan.md`
- Modify: `docs/implementation-status.md`
- Modify: `docs/documentation-governance.md`

- [x] State `single semantic admission, bounded contextual rereading, no downstream authority expansion` consistently.
- [x] Record the exact raw-language reader matrix and execution-chain prohibition.
- [x] Add canonical requirement traceability, dependency, ChoicePresentation, TaskSpecGap, and output-closure contracts to their owning documents.
- [x] Mark the amendment as authoritative target documentation only; do not claim production cutover.
- [x] Keep the next production queue substitutive and fold the additions into P0-D/P2/P3/P4 rather than creating parallel owners.

### Task 5: Verify the amendment and reader discovery

**Files:**

- Modify: `tests/test_horizontal_architecture_governance.py`
- Verify: `tests/test_documentation_governance.py`

- [x] Run focused authority and documentation governance tests.
- [x] Run the full test suite and Ruff on changed tests.
- [x] Run `git diff --check` and maintained-link/lifecycle coverage.
- [x] Render every Mermaid block in the authoritative architecture.
- [x] Check that a no-context reader can answer who may admit meaning, who may read bounded source text, what execution modules may read, how requirements/dependencies are represented, what N-choice sees, and when outputs close the task.

### Task 6: Archive the completed amendment plan

**Files:**

- Move: `docs/superpowers/plans/2026-08-05-semantic-authority-and-task-contract-closure-plan.md`
- Modify: `docs/archive/superseded-2026-08-05/README.md`
- Modify: `docs/documentation-manifest.yaml`

- [x] Mark every plan checkbox and completion record done only after verification.
- [x] Move this completed plan under `docs/archive/superseded-2026-08-05/superpowers/plans/`.
- [x] Remove the temporary live-plan manifest entry and index the archived plan.
- [x] Re-run the simple documentation gate to prove every live Markdown file has one lifecycle.

## Completion record

| Task | Status | Evidence |
|---|---|---|
| 1. Failing tests | done | focused test failed on missing `NLI-01` before amendment |
| 2. Architecture amendment | done | authoritative spec includes three-layer boundary and all closure contracts |
| 3. Evolution plan | done | migration slices, gates, coverage ledger and review precedence synchronized |
| 4. Maintained synchronization | done | discovery, intake, containment, governance, orchestration, evaluation, queue and status aligned |
| 5. Verification | done | 1474 tests, Ruff, diff check, links/lifecycle, 8 Mermaid renders, 7 reader questions |
| 6. Plan archive | done | completed plan archived and temporary manifest entry removed |

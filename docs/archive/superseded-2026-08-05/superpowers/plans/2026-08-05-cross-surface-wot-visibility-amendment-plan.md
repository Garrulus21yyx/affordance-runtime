# Cross-Surface WoT Visibility Amendment Implementation Plan

> **Lifecycle:** ARCHIVED COMPLETED PLAN
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WoT explicitly visible beside DOM/AX/Visual/SVG/API/Device in the existing Task Contract-centered authority without adding a new Runtime chain or changing production behavior.

**Architecture:** Preserve one shared TaskSpec → TaskPlan → logical Catalog → ActionContract → LoopEvaluator chain. Add `Surface.WOT` and three typed WoT acquisition/evidence terms at their correct semantic layers, record current code foundations separately from pending P0-B/P0-C cutover, and freeze the shared-surface invariants in documentation tests.

**Tech Stack:** Markdown authority/contracts, Python pytest documentation governance, Mermaid validation.

---

### Task 1: Freeze the cross-surface contract with a failing documentation test

**Files:**
- Modify: `tests/test_horizontal_architecture_governance.py`

- [x] **Step 1: Add a test requiring `SURFACE-01`–`SURFACE-03`, explicit WoT graph vocabulary, typed WoT evidence roles, maintained-contract synchronization, and pending canonical/full-Catalog cutover truth.**
- [x] **Step 2: Run the new focused test and confirm it fails because the explicit vocabulary is absent.**

### Task 2: Amend the two existing authority documents

**Files:**
- Modify: `docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md`
- Modify: `docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md`

- [x] **Step 1: Add WoT to the environment/source graph and canonical surface vocabulary without creating a WoT-specific planner or task contract.**
- [x] **Step 2: Define `WOT_DESCRIPTION`, `WOT_PROPERTY_STATE`, and `WOT_ACTION_RESULT` with distinct authority/evidence limits.**
- [x] **Step 3: Add `SURFACE-01`–`SURFACE-03` and a coverage-table decision that Planner selects semantics while ActionContractBuilder selects the current backend/binding.**

### Task 3: Synchronize maintained contracts and implementation truth

**Files:**
- Modify: `docs/active-perception-and-online-recovery.md`
- Modify: `docs/trace-and-evaluation.md`
- Modify: `docs/implementation-status.md`
- Modify: `docs/current-implementation-plan.md`
- Modify: `docs/project-plan.md`
- Modify: `docs/README.md`
- Modify: `README.md`

- [x] **Step 1: State that DOM/AX/Visual/SVG/WoT/API/Device are composable surfaces under one canonical epoch and one semantic target.**
- [x] **Step 2: Record existing DOM, visual/SVG, and WoT foundations while keeping P0-B/P0-C/P1–P2 production cutover pending.**
- [x] **Step 3: Clarify that a WoT action result is a receipt/outcome and high-risk completion still requires authoritative final recheck.**

### Task 4: Close and verify the documentation slice

**Files:**
- Archived after completion: this file
- Update: `docs/archive/superseded-2026-08-05/README.md`

- [x] **Step 1: Run the focused documentation test and the documentation/architecture suites.**
- [x] **Step 2: Render all Mermaid diagrams and run `git diff --check`.**
- [x] **Step 3: Run the full pytest suite and Ruff.**
- [x] **Step 4: Mark this plan complete, archive it as a non-authoritative completed plan, and verify lifecycle/link gates again.**

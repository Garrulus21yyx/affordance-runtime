# Documentation Authority Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not delegate production documentation writes.

**Goal:** Reduce `docs/` to a clear current-authority surface, archive superseded prose and plans without losing history, synchronize maintained documents with the Task Contract-centered architecture, and add only a simple mechanical documentation gate.

**Architecture:** Separate current normative/status/reference documents from immutable evidence, immutable change-admission records, and archived history. Keep one human index and one machine-readable manifest as the discovery entrypoints. The simple gate validates only lifecycle metadata, current entrypoint targets, archive replacement pointers, and uniqueness of the authoritative architecture/plan; it does not scan historical prose or prohibit deprecated words globally.

**Tech Stack:** Markdown, YAML, static HTML archive, Python/pytest governance checks, repository-relative links, Mermaid validation.

---

## Scope and non-goals

In scope:

- all 506 files under `docs/` are inventoried;
- 318 evidence files and 87 change-admission records remain immutable and in place;
- dated audits, completed M8 logs, superseded superpowers plans/specs, reviews, and the fixed-baseline deep-dive site move under `docs/archive/`;
- current plans/status/governance and maintained contract/reference docs use the 2026-08-05 Task Contract terminology;
- `docs/README.md` and `docs/documentation-manifest.yaml` become the human/AI discovery surfaces;
- link and lifecycle tests cover the new structure.

Out of scope:

- production Runtime code changes;
- rewriting immutable evidence or change-admission payloads;
- deleting historical facts;
- broad keyword bans over archive/evidence/change-admission;
- an elaborate policy engine, schema service, or documentation build system;
- web research or refreshing the old open-source landscape comparison.

## Target lifecycle classes

| Class | Meaning | Discovery behavior |
|---|---|---|
| `authoritative` | single target architecture or its single evolution plan | linked first from README and manifest |
| `normative` | maintained policy/contract subordinate to the authority | grouped by owned responsibility |
| `status` | current implementation truth or active execution queue | never treated as target design |
| `reference` | maintained integration/scenario/security guidance | searchable, non-authoritative |
| `immutable_record` | evidence and change-admission | remains in existing record directories |
| `archived` | superseded design, plan, audit, review, report, or log | reachable through archive index only |

## Archive set

Move into `docs/archive/superseded-2026-08-05/`:

- dated root audits and remediation records from 2026-07-22 through 2026-07-26;
- completed M8 execution logs/plans;
- `docs/audits/` and `docs/reviews/` historical contents;
- superseded superpowers architecture/plans/designs dated 2026-07-29, 2026-07-31, 2026-08-01, and the pre-authority 2026-08-05 modification-audit documents;
- the fixed-baseline `docs/affordance-runtime-deep-dive/` report;
- historical origin/comparison references that are not maintained current guidance.

Leave small redirect stubs only where immutable change-admission records depend on the old path. Redirects must say `ARCHIVED POINTER`, name the archive target, and link the current authority.

## Maintained set

Primary discovery and truth:

- `README.md`
- `docs/README.md`
- `docs/documentation-manifest.yaml`
- `docs/documentation-governance.md`
- `docs/architecture.md`
- current authoritative architecture and evolution plan
- `docs/project-plan.md`
- `docs/current-implementation-plan.md`
- `docs/implementation-status.md`

Maintained subordinate documents:

- architecture governance, responsibility containment, Runtime-first and benchmark boundaries;
- Task intake/planner, active perception/recovery, orchestration, trace/evaluation, integrations, harness evolution, benchmark plan;
- scenarios and ActionContract digest threat model.

## Simple gate definition

The gate is intentionally limited to:

1. manifest paths exist and lifecycle values are valid;
2. exactly one authoritative architecture and one authoritative evolution plan are declared;
3. README current-authority links do not target `docs/archive/`;
4. archived Markdown files have an archive notice or live below an archive directory with an indexed collection notice;
5. redirect stubs point to an existing archive target and current authority;
6. maintained Markdown relative links resolve.

The gate explicitly does not parse historical semantics, ban words, enforce prose style, or inspect evidence/change-admission contents.

### Task 1: Freeze the inventory and lifecycle decisions

**Files:**

- Create: `docs/documentation-manifest.yaml`
- Create: `docs/documentation-governance.md`
- Modify: `docs/superpowers/plans/2026-08-05-documentation-authority-consolidation-plan.md`

- [x] Record the authoritative, normative, status, reference, immutable-record, and archived collections.
- [x] State authority precedence and current-implementation-vs-target separation.
- [x] Record archive destinations and required redirect stubs.
- [x] Mark Task 1 complete with produced files.

### Task 2: Archive superseded prose, plans, audits, reviews, and report assets

**Files:**

- Create: `docs/archive/superseded-2026-08-05/README.md`
- Move: dated audits, completed M8 logs, historical audits/reviews, old superpowers plans/specs, old deep-dive report, historical origin/comparison references
- Create/Modify: redirect stubs at externally or immutably referenced legacy paths

- [x] Create the archive collection index with reason, date, current replacement, and preservation rule.
- [x] Move the approved archive set without changing evidence/change-admission files.
- [x] Add minimal redirect stubs only for referenced legacy superpowers paths.
- [x] Verify every moved path is listed in the archive index.

### Task 3: Rebuild the current discovery surface

**Files:**

- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/complete-architecture-blueprint.md`
- Modify: `docs/design-freeze.md`

- [x] Make `docs/README.md` the single human and AI starting point.
- [x] Separate target authority, implementation truth, maintained policies/contracts, immutable records, and archive.
- [x] Remove current-entry links to dated historical audits and superseded intake governance.
- [x] Keep stable root redirects short and unambiguous.

### Task 4: Condense current planning and status ledgers

**Files:**

- Archive snapshot: previous `docs/project-plan.md`
- Archive snapshot: previous `docs/current-implementation-plan.md`
- Archive snapshot: previous `docs/implementation-status.md`
- Modify: `docs/project-plan.md`
- Modify: `docs/current-implementation-plan.md`
- Modify: `docs/implementation-status.md`

- [x] Preserve full pre-consolidation histories in the archive.
- [x] Rewrite the current project plan around P0-A through P5 from the authoritative evolution plan.
- [x] Rewrite the active implementation plan as a bounded queue with owner, dependency, exit gate, and current implementation caveat.
- [x] Rewrite implementation status as current truth plus links to immutable records and archived history.
- [x] Do not claim the target architecture is implemented.

### Task 5: Synchronize maintained governance and contract documents

**Files:**

- Modify: `docs/architecture-governance-track.md`
- Modify: `docs/responsibility-containment-boundary.md`
- Modify: `docs/runtime-first-boundary.md`
- Modify: `docs/benchmark-governance-boundary.md`
- Modify: `docs/task-intake-and-planner.md`
- Modify: `docs/active-perception-and-online-recovery.md`
- Modify: `docs/orchestration-and-feedback.md`
- Modify: `docs/trace-and-evaluation.md`
- Modify: `docs/integrations.md`
- Modify: `docs/harness-evolution.md`
- Modify: `docs/benchmark-plan.md`
- Modify: scenario and security reference Markdown

- [x] Add consistent lifecycle/authority/scope headers.
- [x] Replace default SourceLedger/obligation authority with SourceEnvelope, selective SourceAnchor, optional SemanticAudit, and TaskSpecAuthority.
- [x] Preserve TaskPlan as an observation-grounded milestone graph and ActionChoiceCatalog as Runtime-owned before model presentation.
- [x] Replace platform-style verification language with loop-native typed evaluation and separate TaskCompletionEvaluator/RuntimeCommitter authority.
- [x] Preserve ActionContract, capability, approval, preflight, recovery, trace, and benchmark safety boundaries.

### Task 6: Add the simple documentation gate

**Files:**

- Create: `tests/test_documentation_governance.py`
- Modify: `tests/test_horizontal_architecture_governance.py`

- [x] Add a failing test for manifest lifecycle/path validity and single architecture/plan authority.
- [x] Add a failing test that current README authority links cannot target archive.
- [x] Add a failing test for archive index and redirect-target existence.
- [x] Add a failing maintained-relative-link test excluding immutable records and archive prose.
- [x] Update existing governance assertions to use current documents and archive paths rather than requiring historical prose in live status files.
- [x] Run focused tests and confirm the gate stays simple.

### Task 7: Full verification and reader-discovery check

**Files:**

- Modify: this plan's completion table only if verification passes

- [x] Run architecture-modification, horizontal-governance, and documentation-governance tests.
- [x] Run Ruff on changed tests.
- [x] Verify all maintained relative links and Markdown fence parity.
- [x] Render Mermaid blocks in maintained current authority documents.
- [x] Confirm no production source/config files changed.
- [x] Ask representative no-context discovery questions against README/manifest and fix ambiguous routing.

## Completion table

| Task | Status | Produced files / evidence |
|---|---|---|
| 1. Inventory and lifecycle | `done` | `docs/documentation-manifest.yaml`, `docs/documentation-governance.md`, this plan |
| 2. Archive | `done` | `docs/archive/superseded-2026-08-05/`, stable archived pointers |
| 3. Discovery surface | `done` | root README, `docs/README.md`, `docs/architecture.md` |
| 4. Current plan/status | `done` | concise roadmap, active queue, implementation truth; full snapshots archived |
| 5. Maintained docs sync | `done` | eleven normative contracts plus scenarios/security reference aligned |
| 6. Simple gate | `done` | `tests/test_documentation_governance.py`; historical assertions read archive snapshots |
| 7. Verification/reader check | `done` | focused governance tests, Ruff, link/fence checks, seven Mermaid renders |

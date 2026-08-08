# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Updated:** 2026-08-08
> **Start baseline:** `codex/migrate-world-interaction-capabilities@b14e6fbbafc83f4e163bdada4a4e3750010f6a84`
> **Implementation truth:** [Implementation Status](implementation-status.md)

## Current decision

The transaction-platform queue remains stopped. P5-A/B1/C1 has established the
target contracts, minimum Unified World Interface, and real DOM plus
Visual-only short loops without changing the default product path.

## Slice status

| Slice | Status | Current result / debt |
|---|---|---|
| R0 | complete | facts reconciled; smart-room atomic mismatch fix; lockfiles/npm ci; WoT metadata/security/event boundary |
| A1 | complete, non-default | strong TaskGoal and optional EvaluationSpec; legacy projection is one-way edge |
| A2 | complete, contracts only | optional replaceable TaskPlan/Milestone/LocalObjective; no model planner |
| A3 | complete, non-default | immutable WorldObservation, private bindings, policy view, runtime ActionSpace |
| A4 | complete, non-default | ActionIntent/request/result, evaluations, decisions, bounded turns |
| B1 | complete for DOM minimum | SurfaceAdapter, UnifiedWorldEnvironment, DOM adapter, binder |
| C1 | complete, non-default | real Chromium positive loop plus negative matrix |
| C1.1/B1.1 | complete | task-aware ActionSpace, source/world/fingerprint currentness, lineage, schema, budget, Finish/unknown closure |
| C1.2/B1.2 | complete | exact option/binding groups, Runtime-owned coarse effect/risk, single-probe currentness, reset/schema/attempt lineage |
| C2/B3 Visual | complete, non-default | screenshot-only proposer, private coordinates, one-probe pointer execution, real Chromium loop |
| WoT vertical | `NOT_STARTED` | next candidate slice; reuse the same TaskGoal/policy/evaluators |
| P5-D | `NOT_STARTED` | full semantic confirmation continuation |
| P5-E | `NOT_STARTED` | long-horizon plan execution |
| ActionBatch integration | `NOT_STARTED` | isolated legacy-contract helper remains only |
| default cutover/deletion | `NOT_STARTED` | old baseline retained and frozen |

## Next admitted slice

Stop after the Visual closure. The next independently admitted slice may add a
single-surface WoT adapter/positive loop using the exact admitted-selection
contract and the same task, policy, semantic ActionSpace, and evaluators. Do not add batch,
long-horizon planning, global confirmation registries, external full-agent
benchmarks, or old-core deletion to that slice.

## Frozen work

- new RuntimeDelta/RuntimeCommitter/StateKernel capability;
- ledger, checkpoint/resume, event sourcing, generic recovery transaction;
- global approval/capability/token registry or worker fencing;
- ActionBatch integration and long-horizon plan mutation;
- default cutover or deletion before the positive cross-surface gates.

## Verification policy

Every target slice runs focused pytest, Ruff, mypy on affected modules,
`git diff --check`, then the full suite. Evidence is exact-revision/profile
scoped; benchmark oracles never drive product behavior.

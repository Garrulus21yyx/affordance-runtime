# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Updated:** 2026-08-08
> **Start baseline:** `codex/migrate-world-interaction-capabilities@792d327112cd72f3cb5c9bd02c273c80f626f349`
> **Implementation truth:** [Implementation Status](implementation-status.md)

## Current decision

The transaction-platform queue remains stopped. P5-A/B1/C1 has established the
target contracts, minimum Unified World Interface, and real DOM plus
Visual-only and WoT local-simulation short loops without changing the default product path.

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
| C3/B4 WoT | complete, non-default | real local HTTP TD/read/invoke, private transport binding, deployment scope, one-probe execution |
| DOM/Visual/WoT matrix | proven for shared-state task | same TaskGoal/policy/evaluators; adapter-only variation, no fusion |
| P5-D | complete, non-default | semantic confirmation, fresh rebind, single-send consumption, explicit effect certainty |
| P5-D6.1 | complete, non-default | effective risk, destination, presentation, terminal immutability, policy reselection, evaluation lineage/evidence, task-evaluation control |
| P5-M0 | complete, non-default | model-safe policy projections, evidence-resolved evaluations, target output integrity |
| P5-M0.1 AgentContext architecture | `COMPLETE_NON_DEFAULT` | disposable unified context, bounded intent/world/history, current context identity, relevance, paging, source assurance, typed decisions |
| P5-M0.1.1 operational closure | `COMPLETE_NON_DEFAULT` | one-shot epochs, fresh acquisition identity, cursor paging, projection coherence, recurrent decision history |
| P5-M1 model-backed AgentPolicy | `CLOSED` | canonical structured decision contract and deterministic evaluators retained |
| P5-M1.1 ModelPort bridge/hardening | `CLOSED` | hostile JSON, deadline, typed failures/metadata, zero retry/fallback, local HTTP proof; live unavailable |
| P5-M2 production evaluator composition | `CLOSED_FOR_DECLARED_MINIMUM` | Runtime-composed mechanical/semantic/user/hybrid criteria and output binding |
| P5-M2.1 evidence semantics closure | `CLOSED_FOR_DECLARED_PROFILES` | relevance-bound effects, strong no-effect scope, presented evidence only, dynamic readiness |
| P5-M3 new-loop benchmark harness | `CLOSED_FOR_INTERNAL_FIXED_MANIFEST` | internal core/safety/evaluation accepted; external suites not run |
| P5-M3.1 measurement/real adapters | `CLOSED_LOCALLY` | typed expectations, actual safety counters, real DOM/Visual/WoT suite, exact-head attestation command |
| P5-M3.2 admission package | `PARTIAL_FAIL_CLOSED` | full-CI/live workflows and fixed external manifest exist; target-loop BrowserGym environment wrapper remains open |
| P5-E | `NOT_STARTED` | long-horizon plan execution |
| ActionBatch integration | `NOT_STARTED` | isolated legacy-contract helper remains only |
| default cutover/deletion | `NOT_STARTED` | old baseline retained and frozen |

## Next admitted slice

The three-surface single-adapter matrix, P5-D current profile, and P5-D6.1 are
complete. P5-M0, P5-M0.1, P5-M0.1.1, P5-M1 and the P5-M1.1 existing-transport bridge are
complete on the non-default path. P5-M2 criterion-specific composition is also
complete for its declared minimum, and M2.1 closes its evidence-semantic entry
gates. P5-M3 now closes the internal fixed-manifest harness. External benchmark
admission remains blocked until final-head full CI, exact live policy evidence,
and the target-loop BrowserGym environment wrapper all close. The reviewed
mechanical manifest is not itself execution authority; default cutover and
old-core deletion remain unauthorized.

## Frozen work

- new RuntimeDelta/RuntimeCommitter/StateKernel capability;
- ledger, checkpoint/resume, event sourcing, generic recovery transaction;
- global approval/capability/token registry or worker fencing;
- ActionBatch integration and long-horizon plan mutation;
- default cutover or deletion before the positive cross-surface gates.
- any AgentContext ownership of Runtime state, private route projection, or
  LocalObjective-based legality/risk change.

## Verification policy

Every target slice runs focused pytest, Ruff, mypy on affected modules,
`git diff --check`, then the full suite. Evidence is exact-revision/profile
scoped; benchmark oracles never drive product behavior.

## P5-M3.3 closure

Exact model input/schema complexity is measured and installed Ollama failures
are stage-attributed. A canonical 1,024-character completion-summary budget
closes the observed full-union grammar-initialization blocker: exact Qwen and
Llama diagnostic reruns each pass Level 2, then fail current-page destination
admission at Levels 3/4. Stable profile support remains open and compact
grounding remains diagnostic-only. The production default stays format-only.
External execution remains blocked by
the optional BrowserGym dependency, target-loop external environment adapter
and admission package; M3.3 does not authorize that run or a default cutover.

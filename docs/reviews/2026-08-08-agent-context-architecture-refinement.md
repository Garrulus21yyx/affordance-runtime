# AgentContext Recurrent Loop Architecture Refinement

> **Lifecycle:** CURRENT ARCHITECTURE REVIEW
> **Baseline:** `codex/migrate-world-interaction-capabilities@792d327112cd72f3cb5c9bd02c273c80f626f349`
> **Scope:** documentation-only target refinement

## Decision

The target model boundary is one disposable `AgentContext` per policy turn:

```text
Runtime authoritative state
→ bounded one-way AgentContext projection
→ typed AgentDecision bound to current context_id
→ Runtime validation and current private binding
→ execute once
→ fresh observation
→ validated action/task evaluation
```

This unifies model-facing task, bounded raw intent, progress, world, action
page, semantic history, pending state and budgets. It does not create a new
Runtime state aggregate. The model proposes open-world semantic decisions;
Runtime retains context freshness, Internal ActionSpace membership, legality,
risk/confirmation, private route, dispatch truth, evidence and completion.

## Preserved implementation truth

P5-A1–A4, declared P5-B1–B4 minimum profiles, deterministic P5-C1–C3 matrix,
P5-D, P5-D6.1 and P5-M0 remain complete on the non-default target path. The old
Coordinator baseline remains default. Semantic fusion, model-backed policy,
production model evaluators, new-loop harness, long-horizon, ActionBatch,
external benchmark and default cutover remain unstarted or blocked as recorded
by Implementation Status.

## New documented target

- bounded, source-labelled `IntentContextView(authority=context_only)`;
- opaque `ContextIdentity` over task, observation, action-space/page, progress
  and pending revisions; stale decisions execute zero times;
- truthful bounded ModelWorld/progress/history/pending/budget projections;
- source assurance separate from execution authorization;
- LocalObjective relevance (`DIRECT/ENABLING/INFORMATION/OTHER`) separate from
  TaskGoal legality;
- current-page-only action selection and typed paging requests;
- `SelectAction | RequestObservation | RequestActionPage | AskUser |
  ProposeDone | Wait | Abort`;
- semantic confirmation dominance with exact equality as the conservative
  current implementation state;
- criterion-specific `MECHANICAL/SEMANTIC/USER_ACCEPTANCE/HYBRID` completion.

All items above are `TARGET_DOCUMENTED / NOT_IMPLEMENTED` unless already
explicitly covered by the P5-M0 implementation record.

## Non-goals and rollback conditions

No TaskSpecAuthority, ActionContract, RuntimeCommitter expansion, StateKernel
expansion, approval registry, event sourcing, durable ledger/resume, universal
provenance envelope, prompt-injection platform or global transaction is
admitted. Roll back the design if AgentContext owns Runtime state, private
binding reaches policy context, LocalObjective changes legality, source
assurance grants execution authority, or stale context can execute.

## Migration and benchmark gate

Next is P5-M0.1 implementation, then P5-M1 model-backed AgentPolicy, P5-M2
production evaluator composition/criterion adjudicators, and P5-M3 new-loop
harness with a fixed small BrowserGym/MiniWoB smoke. Semantic fusion remains
deferred. WebArena/WorkArena wait for an internal 20–50 turn case; OSWorld
waits for AX/Visual/CLI/app-switch contracts. This document runs no benchmark
and makes no generalization claim.

## Change declaration

```text
production code changed: NO
test semantics changed: NO
default path changed: NO
external benchmark run: NO
next implementation slice: P5-M0.1
```

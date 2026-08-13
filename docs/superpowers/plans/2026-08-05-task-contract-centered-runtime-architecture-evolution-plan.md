# Canonical GUI Agent Authority Cutover Plan

> **Lifecycle:** CURRENT MIGRATION ORDER AND EXIT GATES
> **Updated:** 2026-08-13
> **Target semantics:** [Canonical GUI Agent Execution Architecture](../../task-execution-authority-map.md)
> **Implementation truth:** [Implementation Status](../../implementation-status.md)
> **Active queue:** [Current Implementation Plan](../../current-implementation-plan.md)

This document owns migration order only. It does not redefine architecture,
contracts, state, owners, or the Agent interface. If a statement here appears
to do so, the canonical architecture wins and this document must be corrected.

The former task-contract-centered evolution plan is available from Git history.
Keeping its superseded owner tables inline would create a second architecture
authority, so they are intentionally removed rather than maintained as a
compatibility design.

## 1. Starting condition

The repository already contains reusable parts of the canonical chain:

- admitted `TaskSpec` and `TaskPlan<StepSpec.execution>` contracts and
  authorities;
- plan-step execution contracts, entity/set/aggregate reducers, and choice
  flow;
- unified observation, ActionSpace, binding, risk, execution, and evaluation;
- disposable AgentContext and grounded action-tool projection;
- structural, derived, and visual evidence providers.

The current target loop does not compose them as one chain. At `f3ca2df`, the
main Agent must construct `LocalObjective` state through a recurrent tool call.
The exact-head five-case run failed `0/5` before execution. That implementation
is reopened and must not be treated as target architecture.

## 2. Cutover order

Changes are admitted only in this order:

1. **Composition seam.** Inject explicit TaskSpec admission, plan generation,
   and TaskPlan admission into AgentLoop composition. Do not attach a hidden
   planner capability to AgentPolicy.
2. **Active-step state.** Materialize exactly one `StepExecutionState` from the
   active admitted `StepSpec.execution`; reuse the existing entity/set/
   aggregate reducers behind this slot.
3. **Current choice flow.** Resolve the active semantic step against each fresh
   observation and build `ActionChoiceCatalog` from the current ActionSpace.
4. **Action-only policy.** Project ordinary action/control tools. Remove
   `EstablishLocalObjective` and all predicate/scope/aggregate construction from
   the recurrent Agent decision and model-policy schema.
5. **Admission and execution.** Preserve existing context identity,
   ActionSpace membership, risk, currentness, private binding, single dispatch,
   post-action observation, and evaluator boundaries.
6. **Delete the displaced path.** Delete Agent-created LocalObjective state,
   projectors, adapters, tests, and documentation after no production caller
   remains. Do not retain a compatibility core path.
7. **Verify invariants.** Run architecture, state-machine, stale/currentness,
   exceptional-path, and projection-boundary properties.
8. **Verify behavior.** Run named regression witnesses and held-out variations,
   then a fresh real benchmark profile. Witnesses may falsify the architecture;
   they may not introduce task-specific branches.

## 3. Required deletion gates

The cutover is incomplete while any of these remain on the recurrent main-Agent
path:

- `AgentDecision.EstablishLocalObjective`;
- model-facing LocalObjective, predicate AST, quantifier, scope, sequence, or
  aggregate constructor tools;
- `local_objective_state` whose semantic contents originate from Agent output;
- a planner discovered through an attribute on AgentPolicy;
- a second task/step semantic state alongside admitted TaskPlan;
- reconstruction of plan, scope, evidence, binding, or completion authority
  from an AgentContext/tool response;
- benchmark task names, fixed values, expected answers, or case-shaped routing
  in production modules.

The transactional Coordinator/StateKernel/RuntimeCommitter baseline is not
imported into the target AgentLoop. Its obsolete GUI execution path is deleted
only after the target path has fresh behavioral evidence and no default caller.

## 4. Migration invariants

Every intermediate commit must preserve these properties:

1. no exact GUI identity exists before observation;
2. semantic future selectors may persist, physical identities may not;
3. every effectful dispatch belongs to the active plan step, current choice
   catalog, current ActionSpace, and current binding;
4. a stale context, observation, action, or binding produces zero dispatch;
5. one accepted effectful decision produces at most one dispatch;
6. `SENT_UNKNOWN` is never blindly replayed;
7. DOM/derived/visual sources install evidence through one lifecycle;
8. the main Agent returns only a current action/control decision;
9. projections and benchmark artifacts remain non-authoritative;
10. unsupported states fail with typed outcomes rather than implicit fallback.

## 5. Verification sequence

### 5.1 Static and contract checks

- exactly one canonical task-plan type and one active execution-state slot;
- no semantic-state constructor in the main Agent decision union or tool
  catalog;
- no model-policy dependency on planning/predicate/scope/aggregate contracts;
- no old projection promoted to an authority owner;
- documentation manifest, status, queue, and canonical architecture agree.

### 5.2 Property and integration checks

- plan proposal is authority-free until admitted;
- a fresh observation re-resolves selectors and invalidates E-ref/action/
  binding identities;
- forged or stale action selection cannot bind or dispatch;
- structural and visual evidence have identical epoch/currentness rules;
- set and aggregate completion require reducer/evaluator evidence, not Agent
  narration or action count;
- provider/schema failure leaves plan and dispatch state unchanged.

### 5.3 Behavioral checks

Use the five current cases only as regression witnesses. Add held-out changes in
labels, colors, grid size/order, zero/multiple matches, dynamic appearance,
mixed DOM/visual evidence, and provider failure. Then run the frozen real
benchmark profile and persist per-case results.

## 6. Exit gate

The authority cutover is complete only when:

- production composition follows the canonical chain without a parallel
  semantic owner;
- the displaced Agent-created objective path and callers are deleted;
- invariant and exceptional-path tests pass;
- fresh held-out cases do not require new production branches;
- fresh real benchmark evidence exists;
- implementation status records the exact verified revision and does not claim
  more than the evidence supports.

Implementation completion and verified closure remain separate statuses.

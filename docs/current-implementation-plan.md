# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Updated:** 2026-08-07
> **Baseline:** `agent/migrate-runtime-components@8d7cfd6b7d43c72f9b45bb4144a62553d90c23a8`
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Migration authority:** [Evolution Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
> **Implementation truth:** [Implementation Status](implementation-status.md)

## 1. Current decision

The old P5 queue centered on delta/committer/read-view/ledger/checkpoint work is
stopped. The baseline remains runnable while a new path is proven through
positive vertical loops. No Runtime code slice is currently active.

## 2. Most recent slice

### P5-A0 — Documentation consolidation and target refinement

**Status:** complete in the current working tree. Documentation only.

Completed:

- one authoritative target and one authoritative evolution plan;
- responsibility-thin/semantics-strong intake;
- capability-thick/infrastructure-thin execution loop;
- optional TaskPlan<Milestone> and LocalObjective;
- ActionIntent separated from current BoundActionRequest;
- semantic human confirmation with fresh rebind;
- symmetric DOM/AX/Visual/SVG/WoT/API/Device/CLI surface target;
- bounded ActionBatch as a later observation-barrier optimization;
- long-horizon and offline memory/skill stages;
- implementation status kept distinct from target claims;
- links, lifecycle, residual terminology and documentation governance checked.

## 3. Next code slices (not started)

| Order | Slice | Deliverable | Exit gate |
|---:|---|---|---|
| 1 | `P5-A1` | strong TaskGoal, risk-proportionate material inputs, optional EvaluationSpec | no page/surface/route/plan data; effect boundary fail-closed |
| 2 | `P5-A2` | optional TaskPlan<Milestone> and LocalObjective contracts | simple tasks bypass; evaluator owns milestone completion |
| 3 | `P5-A3` | SurfaceObservation, WorldObservation, AgentWorldView, ActionBinding, ActionSpace | no StateKernel/delta/committer dependency |
| 4 | `P5-A4` | ActionIntent, BoundActionRequest, ActionResult, evaluations, Turn, AgentLoopState | intent and request identity separated; legacy projector one-way |
| 5 | `P5-B1` | SurfaceAdapter + ObservationOrchestrator + WorldFusion + ActionSpaceBuilder | truthful coverage/currentness; no BrowserSession special-case core |
| 6 | `P5-B2/C1` | DOM adapter and minimal positive loop | same minimal policy/evaluator reaches COMPLETE |
| 7 | `P5-B3/C2` | Visual/SoM adapter and minimal positive loop | screenshot becomes semantic targets/options; no raw model coordinate |
| 8 | `P5-B4/C3` | WoT adapter/session and minimal positive loop | environment-native state verifies effect; no test-only glue |
| 9 | `P5-C4/C5` | multi-binding route, small AgentLoopState/LoopPolicy/TurnRecorder | one route executes; no RuntimeDelta/StateKernel; recorder non-authoritative |
| 10 | `P5-D` | RiskPolicy, semantic confirmation, current rebind, SENT_UNKNOWN, evaluators | semantic changes re-confirm; binding-only changes do not; no blind retry |
| 11 | `P5-E` | milestones, LocalObjective, bounded context, fact-driven replan, ask_user | one 20–50 turn task retains constraints and verifies intermediate progress |
| 12 | `P5-F` | max-three no-barrier low-risk ActionBatch | same surface/session; no navigation/external effect; fresh observe after batch |
| 13 | `P5-G` | BindingCache, verified Skill, offline promotion | currentness revalidated; no online self-modification or bypass |
| 14 | `P5-H` | surface breadth, default cutover, old-core deletion | positive matrix passes; old transaction core absent from default path |

Only one behavior-changing vertical slice is active at a time. P5-A contracts
precede adapters; DOM/Visual/WoT positive short loops precede planning, Batch,
Skill, and deletion.

## 4. Frozen work

Until a separately approved fault model exists, do not implement or expand:

- RuntimeDelta variants or global atomic commit;
- RuntimeCommitter shadow/frozen-view protocols;
- durable ledger/checkpoint/crash resume;
- generic recovery transaction or changed-dimension taxonomy;
- trace authority or transactional trace ordering;
- global permit/token registry, revocation linearizability, worker fencing;
- mandatory source/authority proof for ordinary GUI tasks;
- cross-day background/proactive workflow core;
- online self-modifying policy or automatic Skill publication.

Baseline bug fixes are allowed only to keep migration evidence runnable.

## 5. Slice admission checklist

- name the user/environment behavior improved;
- name the canonical owner and displaced owner;
- identify one positive surface/long-horizon case;
- list applicable freshness, semantic confirmation, evaluation and no-retry laws;
- state default-path switch and deletion/isolation gate;
- state whether an observation barrier forbids batching;
- avoid parallel owners and unmeasured service/store/protocol abstractions.

## 6. Verification policy

Docs-only work:

```text
git diff --check
documentation governance and maintained-link checks
residual target-language and reader-question checks
```

Future code slices add focused positive/negative tests, adapter conformance,
cross-surface matrix, long-horizon evaluation, Batch/cache ablations, full
pytest, Ruff and mypy in proportion to risk. Evidence is revision/profile scoped.

## 7. Execution order

```text
DONE    P5-A0 docs consolidation and target refinement
ACTIVE  none (no code slice authorized or started)
NEXT    P5-A1–A4 target contracts
THEN    P5-B + P5-C DOM → Visual → WoT positive short loops
THEN    P5-D semantic confirmation and unknown-effect handling
THEN    P5-E long-horizon planning
THEN    P5-F bounded ActionBatch
THEN    P5-G evaluated memory/skill sidecars
LAST    P5-H breadth, default cutover and old-core deletion
```

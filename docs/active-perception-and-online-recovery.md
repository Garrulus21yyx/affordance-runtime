# Active Perception and Bounded Loop Recovery

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** observation acquisition, fusion, active perception, and loop recovery

## 1. Observation boundary

Each DOM/AX/Visual/SVG/WoT/API/Device/CLI SurfaceAdapter returns a
`SurfaceObservation` with revision, semantic entities, state facts, action
bindings, coverage, confidence, and artifacts.
`WorldFusion` creates one immutable `WorldObservation` with canonical targets,
facts, coverage, conflicts, and all current bindings.

Not acquired, failed, truncated, stale, and complete absence are distinct.
BrowserSession is not a privileged architecture path.

`ObservationOrchestrator` selects surfaces from TaskGoal, LocalObjective,
budget, coverage gaps and conflicts. `WorldFusion` returns accepted semantic
targets, explicit conflicts, or a need to reobserve; it does not maintain a
long-lived probabilistic execution authority.

## 2. Agent view

`AgentWorldView` exposes only the semantic information needed to decide:
target ID, role, label, state, supported actions, and necessary relations.
Bindings, selectors, coordinates, WoT forms, API handles, and credentials remain
Runtime-private.

## 3. Active perception

Observation policy starts with fresh low-cost structured sources, then requests
targeted DOM/AX/WoT/API/Device/CLI reads or visual capture when coverage, conflict,
or evidence gaps justify them. Full screenshot/VLM recapture is not the default
when a smaller observation can answer the question.

Budgets account for observation count, visual/model calls, latency, and
stability waits. The policy may return reuse, targeted augment, recapture, or
wait-and-recapture.

## 4. Post-action observation

Every effectful request—and every admitted no-barrier ActionBatch—produces a
fresh observation before effect or task completion is evaluated. At minimum
the affected target is reobserved; external
effects expand the scope required by the evaluator.

## 5. Bounded recovery

Public recovery decisions are only:

| Condition | Decision |
|---|---|
| stale or grounding failure | reobserve and decide again |
| missing user information | ask user |
| unknown effect | reobserve/evaluate; never replay old request |
| explicit failure or exhausted budget | stop and report |

Provider schema repair stays inside the model adapter. Route changes happen in
a new turn from a new observation. No generic recovery transaction or changed-
dimension taxonomy is required.

## 6. Current migration note

Existing active perception and canonical observation are retained assets.
Current PerceptionSession/BrowserSession special-casing and broad recovery
protocol are migration debt described in Implementation Status.

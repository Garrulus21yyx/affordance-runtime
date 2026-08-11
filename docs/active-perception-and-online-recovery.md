# Active Perception and Bounded Loop Recovery

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** observation acquisition, fusion, active perception, and loop recovery

## 1. Observation boundary

Each DOM/AX/Visual/SVG/WoT/API/Device/CLI SurfaceAdapter returns a
`SurfaceObservation` with revision, semantic entities, state facts, action
bindings, coverage, confidence, and artifacts.
`WorldFusion` creates one immutable `WorldObservation` with canonical targets,
facts, coverage, conflicts, and all current bindings.

Each source may additionally publish a frozen `SemanticInventorySummary` for
one named inventory profile. It reports recognized, actually projected,
uniquely bound/actionable, projected-non-executable, omitted and informational
target-like units. `recognized = projected + omitted` and `projected =
actionable + non_executable`; informational is a subset of non-executable.
This inventory is orthogonal to projection `CoverageState`: complete projection
coverage means the existing projection quotas did not truncate that profile,
not that the page or task is semantically complete. ActionSpace remains the
only action-availability authority.

Not acquired, failed, truncated, stale, and complete absence are distinct.
BrowserSession is not a privileged architecture path.

Observation acquisition lifecycle and observation evidence are also distinct:

- `ObservationCapabilities.independent_capture` says whether Runtime may obtain
  a new snapshot without an action/reset;
- `ObservationCapabilities.post_action_observation` says whether execute can
  return a result observation;
- source modality, assurance, coverage and verification strength describe an
  observation already acquired, not whether another acquisition is possible.

The minimum target environment contract is:

```text
reset(task)      → ObservationAcquisition(initial)
capture(request) → ObservationAcquisition
execute(request) → ExecutionOutcome(ActionResult, post_acquisition)
```

`ObservationAcquisition` is `ACQUIRED`, `CAPABILITY_UNAVAILABLE`, or `FAILED`
and identifies reset/independent/post-action origin. Successful reset must
provide the initial acquired observation. `capture()` is a total typed request:
a backend without independent capture reports `CAPABILITY_UNAVAILABLE`; an
available acquisition that fails reports `FAILED`. Expected capability limits
must not escape as a bare RuntimeError. `ExecutionOutcome.post_acquisition`
uses the same typed result, so `None` cannot conflate unsupported and failed.

The two aggregate capabilities are a minimum adapter-level statement. A
multi-source backend may additionally scope offers by source, modality,
assurance and cost. Capability=true never asserts that a particular call
succeeded, and high-assurance evidence never grants an unavailable capture.

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
wait-and-recapture only within current offers. A model may request observation;
Runtime owns capability selection and the typed unavailable/failure result.

## 4. Normal and recovery acquisition paths

The normal action path is:

```text
bind → execute once → ExecutionOutcome
                    ├─ ActionResult
                    └─ acquired post observation → evaluate
```

It consumes the observation returned by execution directly; it does not write
an opaque cache and then pretend a generic active observe call acquired it.
Every effectful request—and every admitted no-barrier ActionBatch—must obtain a
fresh after observation before a confirmed effect or completion claim. At
minimum the affected target is reobserved; external effects expand evaluator
scope.

The perception/recovery path is:

```text
RequestObservation | Wait | stale/currentness | confirmation refresh
→ inspect capabilities → capture(request)
→ acquired world, typed unavailable, or typed failure
```

If execute does not provide a post observation, Runtime may use independent
capture only when that capability is offered. If neither path can satisfy the
evaluator, Runtime fails closed through typed control/evaluation policy; it
does not reuse the before observation or fabricate acquisition identity.

M4.6-D distinguishes acquisition freshness from information gain only for
policy-origin `RequestObservation`. Its result digest covers canonical public
targets/facts/state/relations/conflicts/inventory, public action semantics and
current validated task status; it excludes observation/target/fact/evidence/
binding/action/action-space/page IDs, context generation, free-form request
reason and private BID/route. An ID-only capture is therefore fresh acquisition
but no semantic gain. Runtime binding/currentness/confirmation/post-action
refresh is exempt because unchanged public semantics may still refresh private
currentness or evaluation lineage. Task terminal truth is evaluated before any
no-gain disposition. Policy-origin observation no-gain shares M4.6-D's frozen
two-distinct-issue same-scope budget: the same request/result fingerprint
repeating stops immediately, while a different no-gain control request consumes
the remaining budget rather than resetting it.

## 5. Bounded recovery

Public recovery decisions are only:

| Condition | Decision |
|---|---|
| stale or grounding failure | reobserve and decide again |
| missing user information | ask user |
| unknown effect | reobserve/evaluate; never replay old request |
| explicit failure or exhausted budget | stop and report |

“Reobserve” in this table means capability-admitted capture; unavailable is a
typed outcome, not an unconditional promise. Provider schema repair stays
inside the model adapter. Route changes happen in a new control transition from
a new observation. No generic recovery transaction or changed-dimension
taxonomy is required. Dispatch truth is independent: `SENT_UNKNOWN` cannot be
downgraded or replayed because after-acquisition failed.

## 6. Current migration note

Existing active perception and canonical observation are retained assets.
Current PerceptionSession/BrowserSession special-casing and broad recovery
protocol are migration debt described in Implementation Status. At the P5-M4
baseline, the pinned BrowserGym adapter consumed a one-use raw snapshot from
reset/step and its public `observe()` name overstated independent-capture
capability. M4.5-A replaced that mismatch: logical reset returns the prepared
initial acquisition, execute returns its post acquisition directly, and
owner-thread `capture()` performs a fresh read-only current-world acquisition
with origin/freshness validation and page-native verifier reacquisition.

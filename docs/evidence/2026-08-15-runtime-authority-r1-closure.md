# Runtime authority R1 acquisition convergence

> **Lifecycle:** CURRENT IMPLEMENTATION EVIDENCE
> **Date:** 2026-08-15
> **Status:** `R1_IMPLEMENTED / SINGLE_ACQUISITION_COORDINATOR / EXACT_OBSERVATION_ACQUISITION_AGGREGATE / GENERIC_BROWSERGYM_CONVERGED / ACQUISITION_PROPERTIES_VERIFIED / INDEPENDENT_FRESH_CONTEXT_REVIEW_COMPLETE / R2_IMPLEMENTATION_READY / A.2_STILL_OPEN / LIVE_NOT_RUN`
> **Normative contract:** [Runtime authority aggregate convergence](../runtime-authority-aggregate-convergence.md)
> **R0 inventory:** [Runtime authority R0 consumer inventory](2026-08-15-runtime-authority-r0-consumer-inventory.md)

## 1. Implemented boundary

R1 changes only observation acquisition ownership and conservation. The product
path is now:

```text
UnifiedWorldEnvironment (facade)
  -> ObservationAcquisitionCoordinator (sole lifecycle/finalization owner)
       -> ObservationOrchestrator (selection only)
       -> SurfaceAdapter / GroupedObservationAdapter (physical/provider result only)
       -> WorldFusion (fusion only)
       -> exact ObservationAcquisition
```

`ObservationAcquisitionCoordinator` is the only production code that directly
constructs a terminal `ObservationAcquisition`. Generic DOM, Visual, WoT and
HTTP adapters use this path. `BrowserGymSurfaceAdapter` uses the same path and
implements only task initialization, one physical reset owner, grouped frame
capture/reuse, source-local AX/DOM/screenshot projection, selected provider
results, execution and private binding mechanics. It returns
`SurfaceObservation`; it does not select sources, fuse worlds or finalize
acquisitions.

This slice does not implement R2 execution/evaluation/transition composition or
R3 projection cleanup. The legacy R2-compatible `ExecutionOutcome` still has a
mandatory post-acquisition slot and represents `NOT_SENT` with a typed
synthetic pre-selection-unavailable post slot. That is not the frozen final
execution algebra and is not claimed as lossless.

## 2. Exact aggregate and legal terminal shapes

The immutable root stores exactly:

```text
acquisition_id
origin
original WorldObservationRequest
stage
final ObservationSelectionPlan | None
ProviderActivation(request, result)*
WorldFusionResult | None
top-level AcquisitionStatus
typed AcquisitionReason(kind, code, stage, source_ids, need_ids)
```

`observation`, `source_results`, `per_need_outcomes` and `reason_code` are
read-only derivations, not independent writable truth. Every activation
conserves the root acquisition ID, lifecycle kind, source, selection and
complete selected-need disposition.

| Terminal stage | Required shape |
|---|---|
| `PRE_SELECTION_UNAVAILABLE` | no plan, activation or fusion; capability-unavailable status |
| `INITIALIZATION_FAILED` | plan retained; no activation or fusion; failed status |
| `SOURCE_ACQUISITION_FAILED` | plan and all selected terminal activations retained; no fusion; failed or capability-unavailable status |
| `FUSION_FAILED` | plan, all activations and exact non-fused fusion result retained; failed status |
| `CANCELLED` | request plus every reached plan/activation retained; cancelled status; `AcquisitionCancelled` carries the aggregate |
| `ACQUIRED_ALL_NEEDS_FULFILLED` | complete activations, fused world and all selected needs fulfilled |
| `ACQUIRED_WITH_UNRESOLVED_NEEDS` | complete activations and fused world, with an unresolved need or optional source gap |

Malformed provider values, wrong source identity and incomplete need results are
normalized at the coordinator boundary to typed source failures. Required-source
failure prevents fusion. Optional failure may preserve an acquired world as
partial success. A fused world becomes current only after successful fusion,
and post-action route selection consumes exact binding-source lineage.

## 3. Grouping, cancellation and fallback

The coordinator partitions selected requests by acquisition group. If one
grouped adapter owns the entire group, it is called once and returns one
terminal selected result per request; otherwise each provider is called once.
BrowserGym may reuse one physical frame for AX, DOM and screenshot results, but
reuse never changes selection or activation identity.

Cancellation is closed at each reached boundary. Initialization cancellation
has the plan and no activations; provider cancellation retains prior terminal
activations and closes the active plus not-yet-reached activation requests as
typed cancelled results; fusion cancellation contains complete activations.
The exact cancelled aggregate is retained before cancellation propagates.

`FreshAcquisition` is deleted. Freshness control retains an exact
`FreshObservationOutcome(acquisition=...)`. A post-action primary acquisition
and independent fallback are distinct acquisitions joined by
`LinkedAcquisition`; fallback never overwrites or merges primary identity,
plan, activations or need outcomes.

## 4. Deleted owners and migrated substitutes

The displaced BrowserGym acquisition module, `BrowserGymEnvironment`,
`FreshAcquisition`, and both duplicated `StaticEnvironment` implementations
are physically deleted. Benchmark and test scenarios provide action results and
exact original single-source observations through `ScriptedSurfaceAdapter`
behind the production coordinator. The convenience facade may unwrap only the
one exact `SurfaceObservation` contained by a scenario world; it performs no
fusion, synthesis or terminal finalization and rejects multi-source worlds.
Legacy tests that depended on impossible pre-fused or fixture-authored
authority were deleted with that owner.

No dual write, read-new/fallback-old constructor, shadow acquisition schema,
event ledger, graph store, workflow engine or new interaction capability was
introduced.

## 5. Property and architecture evidence

| Property | Evidence |
|---|---|
| exactly one production constructor owner | AST architecture scan |
| BrowserGym cannot select/fuse/finalize | architecture redline |
| grouped cancellation closes later groups without activating them | held-out two-group integration test |
| deleted owners and fixture names are unreachable | repository reachability scan |
| plan selections and activations correlate exactly | aggregate validation + generated tests |
| every selected need has exactly one terminal result | generated need partitions |
| partial fulfillment remains acquired and unresolved | generated mixed-need test |
| malformed provider identity fails typed | coordinator exceptional-path tests |
| all terminal stages retain every reached fact | integration state-shape tests |
| grouped capture reuses mechanics without lifecycle ownership | BrowserGym integration tests |
| primary and fallback remain distinct linked aggregates | observation-control test |
| tests and benchmarks traverse product composition | scripted-adapter migration + architecture scan |
| scripted facade cannot fuse or synthesize a source | package redline + multi-source rejection |

Final command results and independent review disposition are recorded in
section 7 after validation.

## 6. Honest R2/R3 boundary

R2 must make `ExecutionOutcome` retain the exact `BoundActionRequest`, exact
`ActionResult`, and optional post acquisition only after dispatch; preserve
`SENT`/`SENT_UNKNOWN` dispatch truth through later failures; compose exact
execution/evaluation values into `ControlTransition`; and delete the summary
owners and compatibility `Turn`.

R3 must make feedback/history/session/result/benchmark values strictly one-way
views, mechanically reject their use by authority APIs, and finish any
remaining projection and public-composition migration. A.2 remains open until
those gates pass.

## 7. Verification and independent review

Final local gates:

- full repository: `1629 passed, 27 skipped`;
- final documentation governance plus architecture ownership/reachability:
  `81 passed`;
- third fresh-context reviewer focused R1 gate: `67 passed`;
- post-review staged-cancellation/property gate: `10 passed`;
- Ruff: passed;
- mypy: passed over 334 source files;
- `git diff --check`: passed;
- clean isolated wheel build/install/export: passed; deleted static and
  BrowserGym acquisition modules are absent and the scripted backend is present;
- repository stale-owner/deleted-path search: no product or test references;
- BrowserGym package-wide selection/fusion/finalization redline: passed;
- benchmark-specific branch audit: no task/case/MiniWoB branch in the changed
  acquisition owner, freshness control or BrowserGym backend.

The first fresh review failed on BrowserGym-local fusion, incomplete grouped
cancellation, a synthetic scripted-source path and stale status text. Those
findings were repaired. The second fresh review then found structural-first
cancellation omitted a deferred visual activation; the coordinator and
aggregate shape validation were tightened and a held-out test added. A third
fresh reviewer, with no prior context, uniquely recovered the owner graph,
seven states, BrowserGym/fallback/cancellation/partial semantics and R2/R3
boundary, then found no second R1 owner, schema or compatibility path. Its
verdict was PASS.

No live benchmark was run. R1 implementation and property review are complete;
whole A.2 closure remains explicitly open behind R2 and R3.

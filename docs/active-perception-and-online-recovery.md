# Active Perception and Bounded Loop Recovery

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** observation acquisition, fusion, active perception, and loop recovery

## 1. Observation boundary

Each DOM/AX/Visual/SVG/WoT/API/Device/CLI SurfaceAdapter returns a
`SurfaceObservation` with revision, semantic entities, state facts, action
bindings, coverage, confidence, and artifacts.
`WorldFusion` creates one immutable `WorldObservation` with canonical targets,
facts, coverage, conflicts, and all current bindings.

AX plus visible clickable raw-DOM identity is the browser control plane. The
pinned BrowserGym adapter marks all DOM elements, so actionable SVG children
that default AX projection would omit receive private BIDs and participate in
the same E-ref/Playwright route as ordinary HTML controls. A configured visual provider is only an
available evidence source: Runtime reevaluates the current structural evidence
on every acquisition and invokes Vision only for a typed coverage, binding,
candidate-ambiguity, explicit-observation, or unresolved-postcondition gap.
Prior visual selection never persists into the next frame.

The provider split is explicit. OmniParser may propose bounded open-world
regions and is always observation-only. Every region-proposer output is
normalized to observation-only at each current adapter boundary, even if a
custom/legacy provider claims an action primitive. When the main Agent already
receives the current screenshot plus marked structural candidates, it owns the
semantic action and offered E-ref choice in one call; Runtime does not invoke a
second pre-policy visual disambiguator. A dedicated disambiguator remains an
optional bounded port for policies that cannot consume that evidence, and may
return only one offered call-local E-ref. Set-valued tasks never use that port:
the optional predicate-classification port must return one `true/false/unknown`
assessment for every supplied E-ref, cannot claim candidate coverage, and
cannot return an action or point. Point
grounders such as GLM remain isolated benchmark/compatibility arms and are not
a BrowserGym target-loop observation capability. Region proposal and candidate
choice have separate call/success counters; point-benchmark counters cannot
grant Runtime action authority.

SoM E-refs are assigned in stable visual reading order and labels are placed
outside tiny controls, keeping both the target pixels and the reference
legible. Agent tools require an explicit E-ref only when more than one target
is legal for that semantic operation; for a singleton, the ephemeral tool
binding already carries the sole identity and Runtime resolves it privately.
The BrowserGym projection also exposes current selected state and a normalized
`appearance.color_family` derived from visible computed style. It no longer
promotes repeated-leaf similarity to an exact count. These are public
current-frame facts, not bindings or hidden task answers. The main Agent may
explicitly propose a bounded `FactEquals`; no color name, task slug or widget
kind is encoded in Catalog. `CandidateUniverse` keeps scope coverage
separate from predicate-classification coverage, and the reducer releases one
independent member at a time. A successor is exposed only after all admitted
members have confirmed effects and a fresh stable scope produces a
`SetCompletionCertificate`. The underlying Runtime action space and DOM
authority remain unchanged.

Mechanically derivable spatial relations are also observation evidence, not a
reason to call a point grounder. For one bounded regular lattice, the adapter
clusters current executable element centers into complete rows/columns and fits
visible numeric label groups independently for each axis. A successful fit
publishes observation-bound grid membership and Cartesian values on the
existing DOM targets. The same generic typed objective tool can select one of
these values and reduce an `EXACTLY_ONE` objective to one current action.
The lattice provider does not parse task text. Missing axes, irregular spacing,
duplicate/empty cells, ambiguous mappings or multiple lattices produce a typed
non-result and no coordinate fact. No derived fact creates a binding; execution
still resolves through the current DOM identity.

Visual evidence and visual execution authority are separate. Same-acquisition
visual regions merge with DOM entities only through explicit
`EntityCorrespondence`. A corresponded region cannot retain a coordinate
binding. In the BrowserGym target loop an unmatched V-ref is observation-only
and exposes no private coordinate route; ambiguous, conflicting, stale,
unsupported, or low-confidence regions are likewise non-executable. A future
safe-region executor requires a separately admitted contract. Missing or
incoherent acquisition identity fails closed.

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
reset(task)      → ObservationAcquisition(initial request closure)
capture(request) → ObservationAcquisition(request, plan, activations, fusion)
execute(request) → ExecutionOutcome(exact bound request, ActionResult, post acquisition?)
```

`ObservationAcquisition` is `ACQUIRED`, `CAPABILITY_UNAVAILABLE`, `FAILED`, or
`CANCELLED`,
identifies reset/independent/post-action origin, and retains the exact request,
reached plan/provider/need/fusion outcomes and typed failure stage. Successful
reset must provide the initial acquired observation. `capture()` is a total typed request:
a backend without independent capture reports `CAPABILITY_UNAVAILABLE`; an
available acquisition that fails reports `FAILED`. Expected capability limits
must not escape as a bare RuntimeError. The final R2
`ExecutionOutcome.post_acquisition` is absent only for `NOT_SENT`; `SENT` and
`SENT_UNKNOWN` retain the exact typed primary acquisition. R1 does not yet
implement this shape: compatibility execution still carries a typed synthetic
pre-selection-unavailable post slot for `NOT_SENT`. That slot is not dispatch
or capture evidence and must be removed in R2.

The two aggregate capabilities are a minimum adapter-level statement. A
multi-source backend may additionally scope offers by source, modality,
assurance and cost. Capability=true never asserts that a particular call
succeeded, and high-assurance evidence never grants an unavailable capture.

`ObservationOrchestrator` is the sole source-selection owner. It selects from
typed epistemic need, current coverage/freshness/conflict, evaluator obligation,
available offers, assurance, acquisition group, cost and budget. TaskGoal or a
model may contribute a public evidence need, but cannot select a private source
or route. `WorldFusion` adjudicates only the selected, normalized observations;
it never chooses or acquires a source. The Actor projector renders only the
accepted world and cannot escalate acquisition.

Physical capture, semantic source activation, world fusion and Actor delivery
are distinct. A BrowserGym/Playwright read may return screenshot, DOM and AX
together, while the normal semantic plan activates only one sufficient
structural lens. Raw channel availability does not automatically make it a
fused source or model input. A second targeted source is admitted only for a
typed residual coverage, ambiguity, visual-property or verification need. The
first A.2 budget is one normal source and at most one complementary source.

The detailed policy, selection matrix and SOTA reuse boundary are defined by the
[Wave A.2 adaptive observation policy](plans/2026-08-15-adaptive-observation-policy-a2.md).
Its closure is withdrawn under
[Runtime authority aggregate convergence](runtime-authority-aggregate-convergence.md):
R1 now closes the exact acquisition aggregate and removes BrowserGym's second
lifecycle. R2 still narrows it into control summaries and R3 must finish the
one-way model/benchmark projection boundary.
Agent-side open semantic gaps continue to enter through the sole semantic
`request_evidence` tool; Runtime alone admits assurance, selects sources and
owns acquisition. The next context must expose the result of that exact need,
not infer gain from an unrelated whole-world digest.

One accepted semantic action selects one current route. A typed `NOT_SENT` may
admit one bounded alternate only after fresh acquisition/fusion and semantic
revalidation; `SENT` or `SENT_UNKNOWN` forbids alternate execution. Views
derived from one raw capture share provenance and cannot be counted as
independent agreement.

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

An empty binding set or repeated role/label is not by itself a visual need.
Runtime first considers terminal/read-only state and distinctions already
available through canonical structure, `within`, state, relations and the
current ActionSpace. Visual escalation is valid only when a relevant typed need
remains unresolved.

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
reason and private BID/route. It also excludes the active action-page
query/filter/view; the full public action contract is the action component. An
ID-only capture is therefore fresh acquisition
but no semantic gain. Runtime binding/currentness/confirmation/post-action
refresh is exempt because unchanged public semantics may still refresh private
currentness or evaluation lineage. Task terminal truth is evaluated before any
no-gain disposition. Policy-origin observation no-gain shares M4.6-D's frozen
two-distinct-issue same-scope budget: the same request/result fingerprint
repeating stops immediately, while a different no-gain control request consumes
the remaining budget rather than resetting it.

This convergence contract is implemented at
`9e92bd2d3b55a696f06ae77fd029b4bc6db9a903` with valid targeted run
`miniwob-control-feedback-25:98e8fff597d94badb82a44f6ed1a4c44`; independent
held-out review remains required before restoring D closure.

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
PerceptionSession/BrowserSession special-casing and broad recovery remain
migration debt outside the Unified target path. R1 routes logical reset,
independent capture and post-action capture through the single
`ObservationAcquisitionCoordinator`. `BrowserGymSurfaceAdapter` owns grouped
physical frame acquisition/reuse and private execution mechanics only; it
cannot select, fuse or finalize an acquisition. R2 control-transition
composition and R3 projection boundaries remain open, so this is not A.2
closure evidence.

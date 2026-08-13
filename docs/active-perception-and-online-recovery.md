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

`ObservationOrchestrator` selects surfaces from TaskGoal/TaskSpec, the active
StepExecutionState's evidence obligations, budget, coverage gaps, and conflicts.
`WorldFusion` returns accepted semantic
targets, explicit conflicts, or a need to reobserve; it does not maintain a
long-lived probabilistic execution authority.

This is the normative Unified contract, not the current implementation claim.
As of M4.6-E step 11, `UnifiedWorldEnvironment` can host several adapters but
still observes all of them and concatenates their values; semantic fusion and
explicit route selection remain pending. M4.6-E step 12 closes that seam before
visual execution binding. It separates three decisions: Runtime acquisition-
source selection, deterministic world fusion, and bounded model-presentation
selection. A model may request public modality/assurance/subject information,
but Runtime selects the source and private route. The selector must use typed
requirements/offers/gaps rather than task slugs or benchmark cohort metadata.

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
Current PerceptionSession/BrowserSession special-casing and broad recovery
protocol are migration debt described in Implementation Status. At the P5-M4
baseline, the pinned BrowserGym adapter consumed a one-use raw snapshot from
reset/step and its public `observe()` name overstated independent-capture
capability. M4.5-A replaced that mismatch: logical reset returns the prepared
initial acquisition, execute returns its post acquisition directly, and
owner-thread `capture()` performs a fresh read-only current-world acquisition
with origin/freshness validation and page-native verifier reacquisition.
The legacy BrowserSession coordinator may still derive task-level visual needs
and use heuristic semantic grouping; it is not correspondence or execution
authority for the Unified target path. Until migrated, it must not be used as
closure evidence for DOM/visual fusion, and new visual capability work belongs
behind the Unified evidence gate and source ports.

# Active Perception and Online Recovery Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** capture, canonical observation, coverage/conflict, observation continuation, and typed recovery
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

The context, surface, coordinate, and restart clauses below include target
contracts spanning future hardening and not-yet-started P5-R recovery. They are
acceptance constraints for those cutovers, not a claim that the current product
path already implements those types or lifecycle checks.

Under the current one-session MVP, snapshot/page revision/target fingerprint/
expiry were the P4 freshness dimensions and now pass their MVP closure evidence.
Account/profile/tenant proof,
full coordinate transforms, leases/fencing and restart identity are optional
scenario hardening and do not block the now-admitted P5 work.

## 1. Observation authority

```text
environment sources
→ PerceptionSession.capture
→ PerceptionCapture + SourceCoverage
→ CanonicalObservationBuilder
→ immutable UnifiedObservation epoch
```

The canonical observation is the only current semantic observation authority
for Runtime grounding, Catalog construction, binding, preflight, and typed
evaluation. PlannerObservationView and ChoicePage are bounded projections and
cannot be converted back into Runtime authority.

`UnifiedObservation` is a logical epoch contract, not a requirement to copy one
giant frozen tuple into every consumer. The physical MVP may store an immutable
epoch header plus Target, Binding, Fact, and Coverage indexes behind an
`ObservationRef`. Runtime collaborators receive restricted read-only index
access; model projectors receive bounded copies. Layout changes cannot alter
canonical identity, coverage/conflict semantics, or digest.

## 2. Acquisition and coverage

PerceptionCapture records what each source actually acquired, including source
identity, freshness, limits, errors, and coverage. Canonical targets retain
available source surfaces, action supports/bindings, typed state facts, source
assertions, confidence, and explicit conflict state.

The acquisition adapter that performed a source read owns that source's
`SourceCoverage` for the exact epoch and scope. It must report attempted scope,
the shared `AcquisitionEpochRef`, capture policy/version, item count,
source-exhaustion, typed termination/truncation reason, omissions when knowable,
errors, and completeness. Items/assertions/coverage from another acquisition
epoch are rejected as a unit. `CanonicalObservationBuilder` may validate and
aggregate those records; it must not manufacture `COMPLETE`, infer completeness
from candidate presence or count, or silently fill a missing/malformed record.
Missing, malformed, stale, or scope-mismatched coverage is `UNKNOWN`. It cannot
support an absence claim, and effectful/high-risk use must route to bounded
active perception or `UNPROVEN` according to policy.

DOM, AX, Visual, SVG, WoT, API, and Device are composable surfaces within the
same canonical epoch, not parallel agent chains. One semantic CanonicalTarget
retains all current bindings, assertions, coverage, and conflicts. When several
bindings support the same action without material conflict, the Catalog exposes
one backend-neutral semantic choice; the route owner inside
`ActionTransactionMaterializer` selects the current backend/binding later.

WoT roles are deliberately distinct. WOT_DESCRIPTION is capability and
grounding metadata; it describes Thing identity, forms, operations, and action
support but is not current device-state evidence. WOT_PROPERTY_STATE is fresh
device-state evidence with resource/version identity and coverage. WoT capture
must report the same freshness, truncation, absence, and conflict semantics as
other sources.

These cases are distinct:

- target absent under complete relevant coverage;
- relevant source not acquired;
- required property not observed;
- material sources conflict;
- target exists but no legal action support;
- model presentation omitted the target.

Only the first permits a true target-not-present conclusion.

## 3. Execution context, surface, and coordinates

Execution context is not one universal bag of fields. Runtime keeps three
separate contracts with different lifetimes and owners:

| Contract | Lifetime and contents | Forbidden use |
|---|---|---|
| `ExecutionContextRequirementRef` | durable opaque reference/digest for required account, profile, tenant, app, or resource scope | cookie, token, credential, live handle, or proof that the current surface satisfies it |
| `LiveSurfaceBinding` | ephemeral fact binding backend/display, account/profile, session generation, run owner, app/process, window/tab/frame/document, focus/modal state, and surface revision | persistence as resumable authority or substitution by URL/DOM/screenshot equality |
| `CoordinateBinding` | ephemeral route-specific source-to-destination transform and its observation/surface identity | reusable normalized points or implicit re-scaling after geometry changes |

The same URL, DOM, or screenshot under a different account, profile, session
generation, window, tab, frame, or document is a different execution context.
A context mismatch invalidates the Catalog, selection, contract, approval, and
coordinate binding; it is not repaired by relocating the old contract.

When a route uses a point, bounding box, selector, or node,
`CoordinateBinding` binds source/destination coordinate spaces, screenshot
ref/hash/size, logical and physical viewport, crop, scroll, device-pixel ratio,
browser zoom, OS scale, orientation, window/display origin, transform
version/digest, and document/frame identity as applicable. Resize, scroll,
zoom, display/window movement, tab/frame/document change, focus, modal, or
occlusion change makes it stale according to route policy. The real input
boundary performs the final visibility, occlusion, surface revision, transform
digest, and lease check.

`SurfaceLease` is the exclusive right for the current run/session generation to
mutate one GUI input surface. It is distinct from target freshness
(`AffordanceLease`) and from task/run ownership; their TTLs and fencing tokens
must not be reused. The modular-monolith closure uses an in-process or existing
session-lifecycle protocol, not a distributed lease service. A `SurfaceLease`,
`LiveSurfaceBinding`, and `CoordinateBinding` are never persisted or revived
from a checkpoint. Lease loss before dispatch denies the attempt. Lease loss
after the dispatch boundary produces uncertain transport/effect state and
requires reconciliation; it never licenses a blind retry.

## 4. Active perception

Runtime may request a bounded read-only probe when a required source/property is
missing and the acquisition budget allows it. Targeted capture creates a new
canonical epoch; it does not patch the previous object in place.

Active perception cannot widen TaskSpec authorization, execute an effect,
manufacture a selector, or treat page content as user instruction.

## 5. Post-action observation continuation

Post-action capture goes through the same canonical builder and normally becomes
the next loop epoch. Perception owner returns one typed disposition:

| Disposition | When |
|---|---|
| `REUSE` | fresh, stable, no material conflict, required next sources present |
| `AUGMENT_TARGETED` | only a known required source/property is missing |
| `RECAPTURE` | stale, conflict, invalid capture, or broad new-source need |
| `WAIT_AND_RECAPTURE` | loading, asynchronous mutation, or pending external state |

A reusable post-action observation is not captured again immediately.
Coordinator executes this result; it does not invent the disposition.

## 6. Failure ownership

| Typed cause | Owner/response |
|---|---|
| coverage insufficient / state unobserved | Runtime perception recovery |
| complete coverage + step target absent | Task Planner replan |
| stale observation/Catalog/contract | reobserve and rebuild |
| material conflict | inspect, block, or user/terminal according to risk |
| invalid/unpresented model choice | planner/provider repair or next page |
| capability/approval failure | safety/user owner |
| open semantic unresolved | restricted resolver, then user/planner/terminal |
| final evidence insufficient | final acquisition/replan/block |
| uncertain external effect | authoritative recheck; never blind retry |

Owner selection comes from typed facts, not generic error-text parsing.

## 7. Recovery constraints

Recovery is budgeted and side-effect-aware. A command may inspect, wait,
targeted-perceive, replan, rebuild, request approval/clarification, or terminate.
It cannot mutate TaskSpec, reuse stale approval, silently relocate an old
ActionContract, or automatically repeat an uncertain non-idempotent effect.
Cross-surface rerouting follows the same rule: a failed DOM, visual, or WoT
binding requires a fresh epoch and a rebuilt contract; Runtime never patches the
old contract to point at another backend.

A checkpoint may retain `last_committed_observation_ref` plus bounded refs and
digests for audit and dependency validation. After restart that observation is
historical evidence, not current observation authority. Resume validation may
accept, reject, or route the run to an existing owner; it does not recreate a
browser/app session, surface lease, live binding, coordinate transform, or
executable contract. Before any further action, the session owner establishes a
new generation and lease, the perception owner captures and submits a fresh
canonical observation for `RuntimeCommitter` to commit, and normal
Catalog/contract/gate construction runs again. A dispatch-started attempt without conclusive receipt/effect is routed to
effect reconciliation rather than replay.

## 8. Progress and trace

Current facts remain in the canonical observation. Contract-bound causality is
kept in bounded recent ActionOutcomes. Durable artifact/resource/transaction/
human evidence may cross epochs. Recovery and observation events are committed
in order by RuntimeCommitter and consumed by offline trace/evaluation.

The previous M8.6-era detailed design is archived at
[maintained-pre-consolidation/active-perception-and-online-recovery.md](archive/superseded-2026-08-05/maintained-pre-consolidation/active-perception-and-online-recovery.md).

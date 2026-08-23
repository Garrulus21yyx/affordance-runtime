# Benchmark

## Status

Current status: **single-ActionPolicy retained / C8 causal post-action transition rerun, C10 action
discoverability/joint delivery packing, C11 benchmark finalization, and C12 TaskGoal public-input projection reopened
and non-closed / C8–C9 prior
implementation evidence scoped / no live run authorized**. Prior
Planner/Auditor G0–G6 artifacts remain historical evidence for the superseded mission path; they do not establish the
current end-to-end invariants or authorize another live run.

This file contains only the current benchmark contract and next execution order. Chronological run evidence is archived
in [`history/benchmark-pre-milestone-convergence-2026-08-22.md`](history/benchmark-pre-milestone-convergence-2026-08-22.md).
The target runtime, owner map, deletion plan, and bounded recovery protocol are in
[`architecture.md`](architecture.md). [`single-action-policy-convergence.md`](single-action-policy-convergence.md) is
migration history, not a second current status or acceptance authority.

No live run is authorized merely because implementation or unit tests pass.

Implementation checkpoint (2026-08-23): substantial C8–C12 owner changes are present in the current tree and the active public case
schema is `target-loop-case.v12`. v12 serializes one `FailureFacts` value instead of the v11 duplicate
failure/cleanup/watchdog fields; the active codec rejects v11 rather than reconstructing it through current semantics.
Historical v6–v11 evidence remains archive-only. The C10/C11 follow-up makes the four pre-provider construction stages
total, emits exactly one disposition-complete local terminal case event before viewer shutdown, and moves bounded suite
commit/export into the existing runner with one SQLite current-disposition row. The CLI duplicate suite commit/export
is removed. The WebArena follow-up removes the `PUBLIC_FINAL_RESPONSE_CONTRACT_KEY` route completely. The official
BrowserGym goal is retained verbatim as bounded task text; response schema is absent from `TaskGoal.inputs`, ordinary
task projection, and Runtime schema validation. One environment-owned codec validates and canonicalizes through the
pinned webarena-verified 1.2.3 `FinalAgentResponse` immediately before the existing BrowserGym STOP path. Invalid
content returns typed `final_response_invalid` before STOP. Plain-text environments retain an identity codec, CoreLoop
does not import WebArena, and the official native evaluator remains completion authority.

The pre-Run21 C10 provider-free checkpoint repaired the run3 candidate-to-region expansion and route/Manifest defects,
but its delivery-boundedness proof was incomplete. It placed exact/focus/delta/recovery recall into a global protected
partition before packing. Run21 proved that a legal large transition can place 84 actions in that partition, leaving
`TurnPacker` no removable record and causing a local `context_capacity` failure before any provider call. C10 therefore
remains reopened. The replacement contract is bounded delivery obligations over complete cursor-backed recall
inventories; only records admitted to the frozen current page are protected.

The earlier fresh-review follow-up additionally made destination-route conflicts atomic: partially overlapping incompatible
destination domains fail closed at `ActionSpaceBuilder`, while compatible adjacency is merged and Binder selects a
binding that owns the chosen edge. Historical recent-step targets no longer expand a current region. The six-page
transition diagnostic now uses `TurnPacker` for both the post-transition and local-follow-up request and records their
frozen route/fragment/backoff and complete cost breakdowns. The Pager's copied byte allocation and schema-size veto
are deleted. Its conclusion that explicit continuation/exact/focus/delta recovery could remain an unbounded mandatory
set is superseded by Run21. Atomic conflicts remain model-visible, cursor-pageable non-executable why-not records rather
than internal-only issues.

The formerly reported **1,551 tests with 24 skips**, **136 focused tests with 2 skips**, and **240 expanded tests with
5 skips** are revision-scoped historical checkpoints, not results for the current dirty tree. Later changes to Store,
Grounding, RequestAdmission, diagnostics, and tests invalidate that current-tree claim; the current relevant gate has
a failing inventory-enumeration permutation property. No model provider, live ActionPolicy, live benchmark, or Task-7
replay was run.

`evidence/w1b-world-c8-c10-provider-free-20260823-run30/` is now classified as stale for current-tree verification. It
was written before those later source changes and carries no source revision/digest binding. Its internal facts remain
historically valid—six provider-free `ok` records, empty acceptance-error lists, and zero recorded provider attempts—
but its 7,98x values are `estimated_total_tokens`, not the full request total including the output reserve. Run30 did
not prove the final production Store transition, zero-prefix continuation recovery, ordered complete inventory union,
or identity equality between the admitted envelope and the object consumed by the provider adapter. Runs 22, 24, 25,
28, and 29 remain superseded diagnostic-migration artifacts.

Production and test code are frozen until the single normative chain in `architecture.md` is approved. Migration and
acceptance are serial and non-circular:

0. **Recording boundary.** Add a test-only local Recording Provider around the actual current
   `ModelBackedAgentPolicy → CoreLoop → provider adapter` boundary. It records the physical request but owns no
   production semantics and calls no model provider.
1. **World.** One `CanonicalPublicWorldProjection` allocates every public ref/order exactly once. Private-ID value,
   private inventory enumeration, and identity-only remount cannot change canonical public records/page-membership
   inputs; remount retains a lossless raw delta while producing no public effect atom or `new_document`. All former
   public ref/order allocators must be physically removed before this stage is green.
2. **Delivery.** Store-owned typed continuation capabilities traverse the real canonical-projection/Store/Plan/Packer/
   Manifest/Catalog path for every bounded obligation kind. A zero-admitted suffix remains callable, is selected through
   the Recording Provider, commits only through `CoreLoop → Store.reduce → RunState.apply`, becomes next-turn
   foreground, and delivers without loss or cursor cycle. Plan, Packer, and Catalog may not reinterpret cursor state.
3. **Envelope.** `ProviderEnvelopeBinder` creates one `CanonicalProviderEnvelope`; RequestAdmission admits and prices
   that same value, and the PydanticAI adapter transports it unchanged. Public text remains lexically neutral while
   typed private provenance fails before capacity or provider dispatch.
4. **Vertical conservation.** Run the complete chain from fresh World through the Recording Provider and from a
   recorded tool call through Resolver/Binder. Only here must Manifest, Catalog, physical envelope digest, and complete
   cost remain invariant under private permutations, with visible/callable route equivalence preserved end to end.

Each stage must pass its own production-path gate before the next owner migration begins; an earlier stage does not
depend on an owner scheduled later. Builder-only probes, mocked fitter cost loops, unordered set-subset checks, and
source-unbound artifacts are supporting diagnostics only. After the vertical gate, rerun focused and relevant
properties, full pytest, Ruff, compileall, `git diff --check`, negative searches, and a newly revision-bound six-page
provider-free diagnostic, followed by a fresh-context read-only audit. None of these authorizes a live benchmark.

The pre-Run21 provider-free rerun is
`evidence/w1b-world-c10-joint-packing-provider-free-20260823-run17/`: all six pages are `ok`, `ready=true`, every
acceptance-error list is empty, every recovery cursor is finite/non-cyclic, and provider attempts remain zero. Initial
request tokens are 7,920 / 7,986 / 7,995 / 7,913 / 7,873 / 7,929 for tasks 0 / 7 / 21 / 27 / 44 / 266; the median is
7,924.5 under the unchanged 8,000 gate. Packed post-transition requests are respectively 7,915 / 8,561 / 8,243 /
7,988 / 7,895 / 7,971 tokens; packed local-follow-up requests are 8,083 / 8,730 / 8,412 / 7,987 / 7,959 / 8,020.
Every one records one optional backoff and no acceptance error. The run3 failures remain preserved as the
before-witness. Run21 then falsified cardinality independence, so the earlier fresh-context statement that no P0/P1
packing gap remained is withdrawn. Run30 is historical provider-free evidence for the revision it exercised, not
evidence for the current replacement implementation and not a live generalization witness. C8–C12 and overall status
remain reopened/non-closed. Fresh verification must wait for Gate 0, the three serial authority cutovers, and the final
vertical conservation gate; a live witness remains separately authorized.

| Task | old C8 tokens / Manifest E | run3 tokens / Manifest E | pre-Run21 run17 tokens / Manifest E / exact routes |
|---:|---:|---:|---:|
| 0 | 7,767 / 16 | 15,312 / 24 | 7,920 / 7 / 13 |
| 7 | 7,543 / 12 | 17,735 / 30 | 7,986 / 6 / 11 |
| 21 | 7,996 / 6 | 20,251 / 25 | 7,995 / 4 / 5 |
| 27 | 7,432 / 9 | 9,769 / 9 | 7,913 / 7 / 11 |
| 44 | 8,019 / 11 | projection failed / 0 | 7,873 / 8 / 13 |
| 266 | 8,591 / 16 | 11,874 / 14 | 7,929 / 7 / 12 |

The legacy artifacts predate exact `action_routes`, so their Manifest column is executable-ref count; the new column
reports both executable refs and exact route count rather than pretending the old artifacts recorded route lineage.

### Run20: two failures, one projection-authority pattern

Run20 is a required regression witness, not a production special case:

| Layer | Durable evidence | Classification |
|---|---|---|
| GUI behavior | fresh World and complete ActionSpace contained executable `E22 Go`; the default page and automatic candidates omitted it; five valid natural-language `find_controls` calls returned only `E24 Reverse Directions`; Runtime stopped after 10 policy steps, 4 observations, and 3 GUI executions | action-discoverability defect followed by the intended bounded Monitor stop; not provider, Binder, executor, cleanup, or environment failure |
| reporting/lifecycle | trace reached `run_finished(blocked)` and `CASE_BODY_RETURNED`; `BenchmarkCaseResult` rejected owner-produced `exact_replay`; SQLite remained `cleanup_status=not_run`, `report_status=not_generated`, with zero case/run reports | `HARNESS_PROJECTION`; cleanup was never attempted, so it is not a cleanup failure |

The case trace is
[`trace.jsonl`](../evidence/live/w1b-task-7-deepseek-v4-flash-run20/traces/webarena-verified-w1b-task-7/trace.jsonl),
the exception is in
[`benchmark.log`](../evidence/live/w1b-task-7-deepseek-v4-flash-run20/benchmark.log), and the durable lifecycle state is
in that run's `run-results.sqlite3`.

The shared causal pattern is a non-authoritative projection vetoing an owner fact:

```text
legal current action → lexical rank/filter veto → model cannot name a current ref
typed Runtime diagnostic → string snapshot → copied benchmark vocabulary veto
```

Run20 additionally exposed that `control_stalled` exists only in display feedback rather than as a typed terminal
reason. Therefore merely adding `exact_replay` to a string set would still misclassify the case as `blocked_other`.
The active gates prove conservation through every owner and consumer; neither exact text nor Task-7 appears in a
production branch.

### Run21: high recall was incorrectly treated as simultaneous prompt delivery

Run21 is the required cardinality and privacy witness for C10. The action preceding the failure was dispatched and a
fresh result page was acquired. The next policy request failed locally before DeepSeek was called:

| Request | Actor World | History | Tool schema | delivered action fragments | protected pre-pack fragments | complete request | Outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| preceding admitted turn | 2,638 | 4,025 | 1,601 | 6 | 6 | 16,228 | provider accepted |
| post-transition turn | 53,280 | 4,415 | 3,833 | 84 | 84 | 69,504 | local `context_capacity`, provider attempts 0 |

The capacity limit was 62,904 input tokens with a separate 4,096 output reserve. Cleanup, case projection, report
commit/export, FINAL commit, and viewer shutdown all completed; this witness is not a finalization regression. The
large typed delta is legitimate Runtime evidence about a page transition/remount. The defect is its conversion:

```text
large current external effect
→ many current actions receive delta/focus/container recall reasons
→ every recalled action is marked protected before packing
→ TurnPacker can remove only optional records, but optional count is zero
→ Actor World + Manifest + ToolCatalog grow together
→ RequestAdmission correctly rejects the request
```

Raw target/fact added/removed counts and identity churn are private diagnostic facts. They must stay in Trace and must
not be rendered as model semantics. The model receives a deterministic typed effect header, a bounded exact evidence
page, a bounded current-interaction action page, `continuation_available`, and bounded continuation scopes backed by
private cursors. Full delta/effect/region-member/omission totals are not model-visible; large raw churn numbers are
never inserted merely because the transition was large.

The post-transition failing turn had `provider_attempts=0`, so its `167/139/496/440`-class trace diagnostics were not
sent to DeepSeek; they are evidence of the conversion defect, not a provider transcript. The preceding admitted
Run21 request nevertheless proves the current privacy boundary is still wrong: its physical request contained a full
`LatestEffect count=4`, `ChangedRegion members=74/omitted_count=54`, and RecoveryDirectory member totals as high as
361. Its `CurrentFindings.source` also repeated generation-specific
`browsergym-observation:<uuid>:4` strings. The target gate therefore inspects the final physical provider request, not
only an intermediate renderer object.

Run21 falsifies the contract “exact/focus/delta recall is one protected mandatory partition.” The replacement invariant
is:

```text
complete authority and high-recall inventories remain inside Runtime
→ each recall source becomes a bounded, cursor-backed DeliveryObligation
→ the highest-precedence nonempty obligation is foreground with minimum_progress=1; all-empty means 0
→ TurnPacker admits only budget-fit atomic current-page records
→ admitted records become protected in ModelTurnDelivery/Manifest/Catalog
→ omitted inventory remains finitely reachable
```

This is not a label-, task-, site-, count-, or threshold-specific repair. Focus neighborhoods, delta actions/values,
exact-query results, changed regions, base inventory, destination fan-out, and route issues all obey the same bounded
page contract.

### Run3: World stable, final delivery inflated

Run3 is the required compression/packing regression witness. It distinguishes internal authority size from provider
input and therefore forbids solving action recall by dumping more World:

| task | invariant internal evidence | old → run3 rendered bytes | old → run3 `actor_world_tokens` | old → run3 delivered `E/N/F` |
|---:|---|---:|---:|---:|
| 0 | 825 facts, 365 targets, 61 bindings unchanged | 10,076 → 16,247 | 3,574 → 5,744 | `16/52/116 → 24/69/176` |
| 7 | 438 facts; World/Actor serialization effectively unchanged | 9,566 → 20,335 | 3,371 → 7,194 | `12/6/54 → 30/86/251` |
| 21 | 1,059 facts and 376 targets unchanged | 10,232 → 29,724 | 3,563 → 10,415 | `6/17/33 → 25/125/340` |
| 27 | World/Actor unchanged | 8,955 → 8,857 | 3,180 → 3,154 | no material growth |
| 266 | World/Actor unchanged | 11,820 → 11,712 | 4,200 → 4,164 | no material growth |

The evidence classifies the defect as selection-scope inflation, not World/Fusion duplication, ActorWorld pruning
regression, tokenizer variance, history growth, or VLM cost. Structural deduplication remains green; a leading
candidate can instead pull one large region's distinct siblings/facts into `ActiveView`. Page-conditional growth and
the absent joint request fitter then expand the manifest and dynamic schema. Task 44 remains a separate formal
projection failure and is not used in this comparison.

The corrective benchmark contract is not “restore the 10 KiB renderer guard” and not “relax the 8k diagnostic.” It is:

```text
lossless internal World/ActionSpace
→ complete high-recall inventories with independent finite cursors
→ bounded delivery obligations; only admitted current-page records become protected
→ compact route/context fragments, no candidate-implied full region
→ deterministic joint TurnPacker over World + routes + media + actual ToolCatalog + fixed request cost
→ atomic ModelTurnDelivery/Manifest/Catalog or typed context_capacity before provider
```

The old and run3 artifact directories remain frozen comparison inputs. A future implementation must improve the
delivery/cost gates without changing the complete internal action inventory, hiding recoverable routes, adding a task/
site branch, or weakening the public route/schema invariants. The frozen 8,000-token median initial-page diagnostic
remains the cost gate; failure must be fixed by selection/factorization/packing rather than by raising it.

### Reopened BrowserGym transition gate

The new gate proves `dispatch → causal stable World → StepResult` without using Task-7 or OSM-specific branches:

- a link whose click returns before a 300 ms JavaScript-delayed navigation must capture the destination as the click's
  `after_world`;
- next ActionPolicy invocation is impossible before navigation commit, DOMContentLoaded, quiet-window satisfaction,
  and post capture;
- destination error content is carried by the click transition trace rather than attributed to the following action;
- navigation timeout and unstable acquisition are typed and admit no World;
- a mechanically non-navigation button skips the navigation-start lease;
- source inspection and timing tests reject a fixed long sleep as the synchronization owner.

Until this gate, the full provider-free suite, static checks, durable evidence, and a fresh-context review agree, do not
run Task-7 live again. The OSM broken route is environment/data failure and ActionPolicy route efficiency is a separate
quality dimension; neither may be used to patch or waive the transition invariant.

Historical implementation verification for the causal-navigation gate is archived with the prior revision. The
generic delayed-navigation, instability, trace-order, and non-navigation witnesses remain useful regression evidence,
but their revision-local test count and review are not current whole-runtime closure after Run20. The transition gate
stays open until it is rerun with C8–C12 and the current tree.

### Reopened Observation Delivery and AgentWorkspace gate

Later live evidence falsified two assumptions that the earlier six-page initial-World diagnostic did not test:

1. a global task/plan lexical Top-k over current public scalar facts does not guarantee that an exact result produced by
   the preceding GUI action is placed in the next model request;
2. append-oriented `recent_steps` with a fixed history cap is not a total bounded workspace and can fail before any
   provider request after useful results have already appeared.

The active provider-free gate therefore proves the full transition-to-request path:

```text
causal before/after World
→ one typed PublicWorldDelta
→ versioned existing regions and cached unchanged outline
→ exact LatestEffect/CurrentFindings/ChangedRegions delivery
→ total WorkspaceReducer
→ RequestAdmission as sole capacity authority
→ provider request or typed local context_capacity
```

This gate must use generic generated/property cases plus the six real-page diagnostics. Task-7 and the text `33km` are
regression witnesses only; production tests and code may not branch on them. C8–C9 implementation, full checks, durable
provider-free evidence, and a new independent fresh-context review must agree before any live witness is authorized.

Implementation checkpoint on 2026-08-22 (not C8–C9 closure): stages 1–6 freeze `PublicWorldDelta`, `RegionVersion`,
`CurrentFinding`, `SemanticEvent`, `ActivitySummary`, `AgentWorkspace`, and `AgentLoopProfile`; one
`WorldTransitionProjector` now supplies exact target/fact additions, removals, modifications, stable region membership,
and before/after lineage. Runtime action evaluation, observation evaluation, current delivery index, Monitor, compact
continuity, and trace share that projection. The existing `WorldDeliveryIndex` now versions stable regions, reuses
unchanged cached outlines, and keeps exact current membership. Default production delivery is change-first and carries
the latest exact GUI effect across local reads/searches; it no longer produces global lexical `EvidenceCandidates`.
`RunState` now stores a bounded `AgentWorkspace` rather than append-only recent history. A total reducer retains only
four detailed steps, exact bounded semantic events and working facts, aggregates ordinary activity by family, and does
not fail after 1,000 differing reads; Full Trace retains all 1,000 raw steps. The old history renderer, independent
history byte cap, RunState pre-cap, `EpisodeHistoryCapacityError`, and `fact_change_count` projection are removed.
`RequestAdmission` now owns complete request allocation, workspace fitting, estimation, and local
`context_capacity`; irreducible requests reach no provider. The provider Binder only serializes admitted requests.
`EpisodeMonitor` now owns exactly three information digests plus bounded observation/recovery and public-attempt
diagnostic state. Different query/region observations with no World/Findings/Facts increment form one streak.
Dispatched GUI actions use the existing ref-free `PublicAttemptSignature`: two identical no-information attempts
produce one recovery and its prohibited signature, and CoreLoop rejects the third identical selection before physical
dispatch. Monitor-owned attempt digest/streak/count fields are projected directly into `EpisodeSnapshot`, replacing
the old constant placeholders without creating a benchmark-side counter. `AgentLoopProfile(30, 8, 1)` caps the old turn
budget rather than increasing it. No live or Task-7 run was performed, no prompt or historical budget was increased,
the fresh-audit gate passed, and the separately authorized live gate stays open.

Provider-free transition evidence on 2026-08-22 is persisted at
`evidence/w1b-world-c8-transition-provider-free-run3/`. All six frozen cases report no acceptance errors: typed delta
and independent serialized snapshot diff agree, the exact changed value enters LatestEffect, and every unchanged
region reuses its version/cache. Each provider-free mutation fixture is applied to a separately captured real-page
shape, then committed through `StepResult → WorkspaceReducer → EpisodeMonitor → RequestAdmission`; an actual typed
`search_page_content` local step follows and preserves LatestEffect before a second admitted request. These fixtures do
not claim a real dispatched site mutation or replace the separately authorized live witnesses. Every transition
diagnostic records `provider_attempts=0`, and all seven JSON artifacts explicitly record the unchanged
`AgentLoopProfile(30, 8, 1)`. The complete initial-page request estimates are 7,432–8,591 tokens with a 7,881.5
median, below the frozen 8,000 median gate. The global EvidenceCandidates compatibility path and secondary
`admit_model_request` owner are physically deleted; unexpected local ValueError maps to `internal_error`.
Revision-local test counts and reviews are archived rather than repeated here because they no longer prove the active
gates.

Run19 confirmed that external GUI change-first delivery works, then falsified the broader closure claim: repeated
`search_page_content` calls returned the same non-empty local result, but no owner classified delivery novelty, the
Workspace hard-coded `new_finding_count=0`, and Monitor observed only unchanged World findings. The active contract is
therefore `StepResult → ObservationDeliveryStore.reduce → DeliveryTransition(next_store, information_delta)`, with the
same delta consumed by Workspace and Monitor. First unseen result items are `new_information`; identical World,
arguments, and result are `exact_replay`, recover immediately, omit the repeated full payload, and stall on recurrence
after recovery. Varied observation methods retain the general `AgentLoopProfile` threshold.

The same run also showed an earlier finalization boundary defect: STOP and post capture succeeded, while an
exception in native snapshot/classification/projection/validation was broadly caught and rewritten as UNKNOWN; after
`run_finished`, the case body did not return, so preliminary persistence and cleanup did not begin. The implementation
added a scoped evaluator outcome algebra, immediate local diagnostics, a local-only `run_finished` handoff, and a
case-return deadline. Run20 then proved that projection construction can still escape before persistence and cleanup,
so those changes are regression evidence rather than a closed finalization contract. No further live run is
authorized.

## Purpose

Benchmarks measure whether the single GUI runtime generalizes across real pages while preserving authority, recovery,
cost, and long-horizon continuity. Tests and architecture review protect contracts; live benchmark results remain the
final capability evidence.

Primary questions:

1. Does the agent complete supported tasks through the official native evaluator?
2. Does World delivery remain compact, understandable, and recoverable on real pages?
3. Does the exact public effect of the latest GUI action appear before the ordinary page outline without a model search
   call?
4. Does every currently legal control have a finite public discovery route, including short/Unicode labels, page-tail
   controls, and same-functional-container neighbors?
5. Can current public evidence be used directly, with an optional exact working note only when it must survive a view
   change?
6. Does arbitrary ordinary step growth remain bounded through one total AgentWorkspace reducer and one request-capacity
   owner?
7. Can one continuous ActionPolicy complete the task without mandatory Planner, milestone, Auditor, or MissionState
   transitions?
8. Is each delivered action ref present in the exact admitted text/tool/image payload, and is every actionable image
   mark admitted by the same manifest?
9. Do stalls, route regression, provider failure, uncertain dispatch, report projection, cleanup, and viewer failure
   terminate or recover through typed bounded paths without erasing case truth?
10. Are token, latency, model-call, and unnecessary-action costs competitive with a compact single-agent baseline?

## Cohorts

### W0 — environment readiness

W0 verifies official dependency registration, six site health checks, reset, STOP/native-evaluator invocation, pinned
container images, and a durable readiness manifest. W0 is already complete; it is not rerun unless the environment or
official dependency commit changes.

### W1a — provider-free contracts

W1a exercises the architecture without a real model:

- one BrowserGym session across the continuous case loop and no second reset;
- complete decision/receipt/state-transition algebra;
- native-tool wire and representation-only normalization;
- one before/after public World delta consumed consistently by outcome, delivery, Monitor, continuity, and trace;
- one existing `WorldDeliveryIndex` carrying canonical public container/order/focus facets for regions, forms,
  discovery, and rendering;
- changed-region version/cache behavior, latest-effect salience, World/Action recovery, and ref currentness;
- exact/structured high-recall action discovery with complete cursor-backed inventories, one additive
  `ActionDeliveryPlan` of bounded delivery obligations, independent continuation, and non-authoritative ranking;
- deterministic joint packing of compact World fragments, exact route-bearing text/media fragments, and the actual
  factorized ToolCatalog; atomic manifest/catalog lineage is derived only from admitted fragment route deltas;
- current evidence use without mandatory pin/audit and optional exact working-note retention;
- total AgentWorkspace reduction under arbitrary ordinary step growth and whole-request admission by one capacity owner;
- information-delta activity aggregation and a typed operational `CONTROL_STALLED` without task-semantic blocking;
- closed capacity/tool/provider/internal exception classification;
- lossless public TaskGoal→GoalCompiler request projection and direct GoalCompiler/CoreAgentLoop composition with no
  lexical key filter or mission fallback;
- route/effect/protocol stall recovery;
- monotonic durable body/final result, total report projection, cleanup deadline, transport retry, and viewer fail-open
  behavior.

### W1b-World — six real-page diagnostics

Read-only provider-free diagnostics use these frozen official cases as heterogeneous page witnesses:

| Task | Site family | Primary stress |
|---:|---|---|
| 0 | shopping_admin | navigation, report form, result table |
| 7 | map | search, directions form, dynamic route result |
| 21 | shopping | dense commerce content and actions |
| 27 | reddit | searchbox and repeated feed structure |
| 44 | gitlab | very large structured application page |
| 266 | wikipedia + map | multi-site content and navigation |

These cases verify general contracts; production code may not branch on task id, site label, text witness, selector, or
expected output.

For each page the diagnostic captures at least one generic typed transition in addition to the initial World. It must
prove that added/modified public values enter `LatestEffect` and `CurrentFindings` where eligible, changed regions are
exact or completely paged, unchanged regions reuse cached versions, local read/search does not erase the effect, and
agent-browser-style serialized diff does not reveal a public addition absent from the typed delta/delivery manifest.
It also probes controls beyond the initial byte/page budget, real AX-role/public-DOM-tag container mismatches,
field-to-sibling-submit reachability, base and query continuation, and final text/image/manifest agreement. The map page
is one heterogeneous snapshot; the properties use generated and held-out labels/structures and may not encode its
task id, `Go`, OSM classes, fixed refs, or selectors.

Each page also records internal World/Actor size separately from final delivery, recall/obligation/current-page counts,
candidate-to-region expansion reasons, omitted-record cursors, actual factorized ToolCatalog bytes/tokens, packing
backoff count, and the final complete-request estimate. A larger or differently partitioned internal World does not
fail by itself; unexplained final-delivery growth, missing recoverable routes, post-hoc manifest routes, an
unrecoverable omission, or exceeding the frozen median gate does.

### W1b-Agent — live compatibility smokes

Live cases begin only after W1a and W1b-World close. Run one explicitly requested witness at a time, persist the case
result before cleanup, and diagnose the first shared contract failure before continuing. A single successful witness
does not close W1b.

### W2 — frozen hard cohort

W2 is the predeclared 12-case WebArena-Verified Hard cohort. Each case has an isolated TaskGoal/GoalPlan, working set,
session, and trace. No cross-case long-term memory or recall is allowed. W2 starts only after W1b closure.

## Active C8–C12 provider-free gates

### C8 — transition and incremental-delivery properties

Generated typed Worlds and held-out real-page transitions must prove:

- `PublicWorldDelta` is complete for every supported public addition, removal, and modification and binds one exact
  before/after lineage;
- ActionOutcome, Monitor, ObservationDelivery, SemanticEvent projection, and trace consume that same delta object or
  exact serialized value, rather than independently rebuilding change;
- one deterministic `PublicEffectProjector` converts the lossless identity-based delta plus before/after supported-
  public snapshots and prior/current existing `WorldDeliveryIndex` public structural slots into the active
  `PublicEffectInventory`. Exact public semantic
  multiset intersection cancels remount-only churn; stable-slot value changes become `modified`; residual after/before
  atoms become `added`/ref-free `removed`. Ambiguous pairs remain explicit add/remove rather than being guessed;
- generated before/after source and private-ID permutations prove: a full identity remount of the same public semantic
  multiset emits zero model effect atoms; duplicate multiplicity `+1|-1` emits exactly one residual add/remove; one
  stable public-slot value change emits one modified record; and an ambiguous-slot change remains one add plus one
  remove. In every case raw `PublicWorldDelta` and private Trace remain lossless;
- every residual added, modified, and removed supported public value enters that active effect inventory. The next
  model turn receives a bounded exact current/tombstone page; Runtime retains the private cursor bound to a public
  continuation scope rather than serializing either the cursor or the whole inventory;
- removed target/fact records preserve prior public label/role/path or predicate/value and provenance as
  `change=removed,current=false` tombstones. They carry no current E/N/F ref and never enter ActionSpace, Manifest,
  ToolCatalog, Binder, remember/evaluator evidence refs, or another executable/current authority;
- raw target/fact added/removed counts and records, full LatestEffect cardinality, remount/identity-renewal counts,
  changed-region and RecoveryDirectory member totals, whole-inventory omission totals, and private digests stay in private
  Trace/diagnostics. Model delivery contains only a typed effect header derived from existing public facts, current
  exact/tombstone page records, `continuation_available`, and bounded continuation scopes;
- local `read_region`, `search_page_content`, and `find_controls` do not clear the latest external effect;
- World effect rendering and effect-derived action recall read the same `ObservationDeliveryStore.latest_effect`
  `PublicEffectInventory`. The projector produces target/fact atoms and current changed-target public structural-slot
  keys, not action operations/routes. Action recall joins those keys to the complete current `ActionSpace`, never raw
  `delta_membership`, and a removed tombstone is never executable. A route-contract-only change remains reachable by
  base continuation and is not guessed by the effect projector. An intervening local same-World step cannot clear
  action-effect recall while the prior `LatestEffect` remains
  visible;
- a later GUI effect supersedes the prior active-effect cursor after `WorkspaceReducer` has selected a deterministic
  bounded exact subset for `SemanticEvent`; the current World/recovery surface remains authority for current facts and
  private Trace retains the full raw delta/reconciled effect. The event does not copy the whole effect;
- unchanged region digests reuse their cached outline; changed region versions increase; navigation/document-lineage
  change invalidates stale refs and old cache membership;
- rendering/fitting never authorizes a target absent from the current complete ActionSpace;
- an independent serialized public-snapshot diff detects no addition/removal absent from the typed delta, except an
  explicitly documented non-semantic serialization difference;
- no second browser session, DOM walker, RegionIndex, selector/ref registry, action registry, or Agent loop is created.

Required regression shape:

```text
form submit or Go-like action
→ result/status/table text appears in after World
→ next ordinary request begins with the exact public change
→ zero content-search/read calls required for first visibility
```

The witness values and labels are generated or held out. An assertion tied only to `Distance: 33km` is insufficient.

### C9 — bounded-workspace and capacity properties

Property/state-machine tests must prove:

- four or fewer latest steps retain detail; older significant GUI effects, public results, working-note changes, typed
  failures, and recovery transitions retain exact bounded SemanticEvents;
- 1,000 ordinary supported steps, including non-identical read/search arguments, always return a reduced workspace or
  one typed irreducible capacity result; ordinary accumulation never raises a history exception;
- repeated no-information reads/searches/waits update one bounded `ActivitySummary` family rather than append entries;
- first non-empty local observation result records its unseen public items and exact count; the same World/arguments/
  result is `exact_replay`, is not redelivered in full, recovers immediately, and stalls on post-recovery recurrence;
- a precise public result remains available after leaving the latest-four window and after a local search-view change;
- a whole address is retained exactly and is not mechanically split into inferred business fields;
- `RequestAdmission` is the only component that allocates/adjudicates capacity for the complete request;
- RunState, history, renderer, and provider Binder contain no independent model-history cap or pruning authority;
- local irreducible overflow is `context_capacity`, `provider_attempts=0`; only grounded tool-resolution failure is
  `invalid_tool_arguments`; transport failure is `provider_unavailable`; unexpected Runtime failure is
  `internal_error`;
- World/finding/working-fact digests unchanged across observation-only activity produce one generic stall family even
  when query or region changes;
- the configured recovery threshold produces RECOVERY once, recurrence produces operational `CONTROL_STALLED`, and
  TaskEvaluation remains `INCOMPLETE|UNKNOWN`;
- Full Trace retains every raw step and is not read back as model workspace.

Profile values are recorded in each artifact. They may vary by declared experiment profile, but may not depend on task
id, site, page label, expected answer, or known trajectory.

### C10 — action discoverability, joint packing, and atomic-delivery properties

Generated controls, held-out page structures, and frozen real-page snapshots must prove legal-action conservation from
the fresh World to Binder:

- the existing `WorldDeliveryIndex` is the only unnumbered public structural index; AX roles and supported public DOM
  tags are normalized once into typed container membership, stable source/tree slots, focus neighborhood, viewport
  status, and region membership. It allocates no model ref/order and owns no temporal delta/cursor state;
- one immutable `CanonicalPublicWorldProjection` consumes the fresh World, that unnumbered index, and complete
  ActionSpace and allocates every public target/fact/region record, `E/N/F/R` ref, and public total order exactly once.
  Grounding, findings, effects, pager, renderer, Manifest, Catalog, Workspace, Monitor, and evaluator views consume the
  same projection identity; repository-negative checks find no surviving alternative allocator or raw-inventory sort;
- `PublicWorldDelta` remains the lossless before/after transition, while `PublicEffectInventory` reconciles prior/current
  canonical semantic records. Effect rendering and effect-prioritized action recall consume that inventory, never raw
  identity-delta membership;
- when Fusion aligns equivalent targets from two or more structural sources, every canonical target belongs to exactly
  one deterministic primary region while secondary source provenance remains observable. Permuting source order leaves
  region membership, functional path, route recall, and public presentation unchanged;
- when the SurfaceAdapter recognizes more action-bearing controls than its supported bound, it either preserves all
  controls/bindings in the internal action inventory or returns typed acquisition capacity with no actionable World.
  A first-N slice cannot produce `source_coverage=complete` or an authoritative exact miss; read-only partial coverage
  and omitted counts survive every projection;
- one shared option-domain bound is used by SurfaceAdapter, parameter-schema validation, ActionSpace, and ToolCatalog.
  Generated select domains at 12, 13, 16, 17, the declared bound, and bound+1 either conserve every option and a
  resolvable `select_option` route or emit typed non-complete capacity/eligibility; no executable control is silently
  left without a binding/why-not reason;
- generated destination-required actions at 16, 17, the declared route bound, and bound+1 preserve every legal
  `(operation,source,destination)` record internally or fail typed before an actionable partial World. RequestAdmission
  pages the same records seen by the final manifest/catalog; repository search finds no independent
  `max_destinations_per_option` truncation or estimator that counts fewer routes than delivery;
- generated aligned-source bindings with the same public route selector and identical contracts merge into one
  ActionSpace route; incompatible parameter/effect/barrier/verifier contracts close there as typed
  `action_route_conflict` with a visible why-not fact and no route. Neither case may first fail as `catalog_invalid`;
- every legal `ActionOption` whose one atomic public route/schema representation fits the declared active provider/
  RequestAdmission profile is recoverable in finitely many calls by its exact normalized public label, role,
  operation, structural context, or public continuation route backed by a lossless private inventory cursor; generated labels include one- and two-character,
  Unicode, punctuation, whitespace-normalization, empty-label, and duplicate-label cases;
- a legal but atomically unrepresentable route remains in complete ActionSpace and, when foregrounded, fails
  deterministic typed `context_capacity` with the offending component and zero provider attempts; it is never
  classified as an exact miss, silently omitted, or used to weaken the recoverability claim for representable routes;
- generated label/query lengths include 1, 2, 119, 120, 121, the declared public bound (at least the current
  BrowserGym 240-character label bound), and bound+1. Every admitted label fits an exact query; over-bound input is
  typed rather than sliced, and repository search finds no `query[:120]` or equivalent silent truncation;
- a complete label span in a longer natural-language query enters the exact recall inventory. Extra query words can
  rerank but cannot delete it when the full query is within its declared bound; duplicate exact labels remain
  distinguishable by public path/role/operation and are never silently collapsed to an unrelated sibling;
- the focused field's legal same-container submit/action siblings enter structural recall even when task words do not
  match. Effect-prioritized routes are a deterministic join of active `PublicEffectInventory` changed-target slots to
  the complete current ActionSpace, the sole legal-action authority;
  no unproduced `newly_revealed` flag or local-step empty delta is accepted as a substitute;
- authority inventory, recall inventory, current delivery page, and recovery surface are generated as four distinct
  types/contracts. Exact/role/operation, continuation, focus/container, viewport, delta, base, destination, and route-
  issue fan-out produce complete deterministic recall inventories and bounded cursor-backed `DeliveryObligation`
  groups; none maps collection membership directly to an unbounded `protected` Boolean;
- each delivery obligation records owner lineage, deterministic atomic records, foreground priority,
  source/result coverage, and a private Runtime continuation exposed only as a bounded public scope. The plan stores
  one derived `foreground_scope|None`, not a mutable minimum on every group. The highest-precedence eligible obligation
  with an undelivered supported record is foreground and mechanically requires one record; when all eligible
  inventories are empty it requires zero. No kind-specific exception or model choice sets this value. Other groups
  expose a bounded directory entry and may contribute as capacity permits. There is no
  simultaneous one-record requirement for every group;
- obligation-group cardinality is bounded by the declared protocol kinds/current explicit lens, not target/fact/region
  cardinality. Generating more changed targets, facts, regions, actions, destinations, or issues grows only Runtime
  inventory/cursor remainder and private diagnostics, not fixed-shell or group-metadata count;
- exact query or explicit continuation foregrounding delivers at least one exact/structural record when one remains and
  one atomic record is representable. After a record is admitted to the frozen page, objective/semantic score and later
  rendering cannot remove or reorder it. Before admission, recall reason is not prompt protection;
- automatic candidates and explicit exact/inventory discovery do not share a vetoing ranker. A semantic false
  positive cannot cut off exact matches or the base continuation;
- base page, query page, automatic candidates, and search candidates are projections of one immutable per-turn
  `ActionDeliveryPlan`, not four mutable stores. Generated query/delta/focus/container/issue inventories with more
  records than one request retain their complete order behind independent cursors and contribute only budget-fit
  current-page prefixes; there is no `top_k=None` or whole-delta/whole-neighborhood bypass;
- private base, query, external-effect, focus/container, destination, and issue cursors each enumerate their declared ordered
  result set. Every foreground continuation with `has_more=true`
  delivers at least one previously undelivered public target/verb record into the model payload and manifest, with no
  cycle, skip, or repetition-only page;
- dynamic continuation tools are bounded by operation/scope, not record count. `read_next_page` exposes no argument
  for one live scope or a maximum three-value `effect|page_directory|active_read` enum;
  `action_results_next_page` exposes only the
  bounded action-obligation kinds that currently have a continuation. Runtime bindings, not tool arguments, carry the
  private cursor. Generated inventory growth does not increase tool count or add one schema enum member per record;
- generated Worlds with more regions than one directory page are fully enumerated through
  `read_next_page(scope=page_directory)`; a region first exposed on the final directory page can then be selected and
  its complete contents enumerated through `active_read`. After that local read, both `effect` and `page_directory`
  continuations remain resumable. A fresh World or foreign owner/kind/order/offset cursor fails typed stale before
  provider/GUI dispatch; it is never normalized into a current scope;
- action-page allocation comes from `RequestAdmission` and is measured over actual public route records. Varying
  private-ID lengths, internal schema/description size, or observation identity cannot change page membership; one
  unrepresentable public route closes as typed capacity;
- repository negative search finds no independent ActionPager, ModelTurnDelivery, or grounded-catalog byte veto. A
  generated large but legal relational catalog is either admitted by whole-request admission or returns
  `context_capacity` with `provider_attempts=0`, never `invalid_tool_arguments`/catalog-invalid;
- a compact action fragment contains the route, public label/role/operation, functional path/container, and declared
  focus/viewport/delta reasons without expanding all members/facts of its region. Adding or changing only the leading
  candidate cannot change `ActiveView` region membership; full region contents require an explicit region/change/focus
  fragment and an independently visible cost/recovery handle. Repository negative search finds no
  `leading candidate → selected_region_keys` path;
- the deterministic `TurnPacker` starts from the declared fixed request cost plus a bounded current-page/effect/
  recovery shell and attempts only the foreground group's declared zero/one minimum first. After every tentative record
  it compiles the exact fragment-route deltas, media, Manifest, and factorized ToolCatalog and reprices the complete
  provider-bound request. If the required foreground record cannot fit, it returns typed capacity. Otherwise it makes
  deterministic depth rounds: each eligible obligation in priority order gets at most one next-record attempt per
  round before any group receives another. Overflow leaves that optional head and suffix behind the same cursor and
  does not block later groups;
- typed `context_capacity` with `provider_attempts=0` is valid only when the bounded fixed shell or one required atomic
  foreground record plus its route/catalog representation cannot fit—not because a collection has many
  focus/delta/exact/issue members. The packer has no model call, mutable cross-turn state, generic knapsack/search
  objective, or capacity constant independent of `RequestAdmission`;
- packing is deterministic under private-ID/source enumeration permutation. For every admitted request, the sum of
  recorded system/task/plan, World fragments, workspace/history, media, exact compiled tool schema, wire overhead, and
  output reserve equals the estimator input used for final RequestAdmission. Every omitted supported record remains
  behind a typed cursor; no route/schema branch, scalar changed value, tool-call/result pair, or actual image mark is
  split;
- `ProviderEnvelopeBinder` creates the only `CanonicalProviderEnvelope` from ModelTurnDelivery, frozen Catalog,
  task/plan/workspace/history, media, settings, and output contract. RequestAdmission validates/prices and returns that
  exact value; the PydanticAI adapter transports it unchanged. The Recording Provider observes the same canonical
  digest and fields. Sidecar components and post-admission message/tool/media reconstruction are absent;
- generated fan-out uses `0, 1, page_bound-1, page_bound, page_bound+1, 2×page_bound, 4×page_bound` records for each
  exact-query, external-effect action/value, focus-container, base, destination, and route-issue obligation. If one
  atomic record fits, every nonempty foreground page is admitted, the union of cursor pages equals the internal ordered
  inventory, and request size remains bounded independently of total inventory cardinality;
- generated combination cases make two through all obligation kinds nonempty simultaneously and vary budgets at exact
  fit and one unit below. They prove there is only one required foreground minimum, the complete request remains
  bounded, every group's delivered pages plus cursor suffix equal its authority inventory, adding low-priority
  inventory cannot evict that foreground minimum, and a too-large optional head blocks only its own consecutive cursor
  while later small groups are still admitted. This is a cross-product/state property, not separate one-group examples;
- a state-machine sequence `external GUI effect → packed model view → local read/find/search → packed model view → next
  external GUI effect` proves that the first two model views consume the same active external-effect identity and
  cursor suffix, while the later external effect supersedes it exactly once. No local empty same-World delta may clear
  only the action side of that contract;
- prompt-privacy properties preserve raw target/fact added/removed records/counts and identity-renewal counts in private Trace and
  packing diagnostics, together with full LatestEffect/region-member/RecoveryDirectory/omission totals, while the
  serialized `ModelTurnDelivery`, complete admitted physical provider request/transcript, and the exact would-be
  provider serialization priced by a local pre-provider capacity decision contain no such diagnostic inventory/count
  fields, raw remount records, private cursor, observation/source-record ID, UUID, capture epoch, or identity-derived
  source string. They contain only the public typed effect header, exact
  current/tombstone page records, `continuation_available`, and bounded continuation scopes. Trace
  retention and model omission must both hold in the same test;
- the effect header has a fixed field algebra and may name only public regions represented on the current admitted
  effect/directory pages. Increasing total changed-region count cannot grow the header or inject a full region-label
  inventory; the public directory continuation is the recovery path;
- trace/report properties distinguish tentative and frozen ModelTurnDelivery/ToolCatalog costs. A pre-provider capacity
  turn retains its current ActionSpace identity/count, obligation/cardinality breakdown, typed decision, offending
  component, per-turn provider attempts=0, and tentative cost without claiming a frozen catalog; run-level provider
  attempts remain the explicit sum of prior physical calls;
- the public action-page decision contains only query or bounded current continuation scope plus tool-call identity.
  Physical provider payload, tool arguments, decision, discovery result, history, InformationDelta, Workspace, and
  public trace/report projections contain no private cursor. Repository
  negative search finds no `target_id`, `relevance_role`, or `exact_target_ref` ghost filters in that decision's
  payload/history/Monitor chain;
- discovery emits one typed `ActionDiscoveryResult`; CoreLoop only commits it and contains no ad-hoc public result
  dictionary or independent match/coverage vocabulary;
- changing private target/action/binding IDs, fresh observation identity, hash seed, or input enumeration order does
  not change public recall or public tie order. Ties use source/tree/viewport order and action-variant ordinal;
- generated observation/source-record IDs vary in value and encoded length while public surface/modality/coverage and
  structure stay fixed. ModelTurnDelivery, physical provider payload, Workspace/history/public results, page
  membership, Manifest/Catalog, and complete request cost remain byte-identical; only private lineage/Trace changes;
- discovery results, recent history, InformationDelta, Workspace, trace public fields, and reports contain public
  ref/label/role/verb/match-kind/coverage/continuation-scope records and no Runtime inventory/result/action-variant
  totals, private cursor, action, target, binding, selector, BID, or coordinate IDs. A public source-provided business
  count may remain an ordinary fact; current route variants appear as verbs rather than a diagnostic count;
- `DeliveryManifest.action_routes` equals the ordered union of exact route deltas carried by final admitted text
  fragments plus actually attached actionable image marks. A byte-rejected fragment contributes no routes; model tool
  operands only consume the manifest. Repository negative search finds no post-hoc ref scan such as
  `_manifest_with_routes` that reconstructs source/destination relations from complete ActionSpace. Annotation
  absence/failure, out-of-frame or wrong-coordinate boxes, and raw or
  unattached screenshots contribute no marks/routes; each `E` mark has exact current route and source/destination
  operand-role closure. Annotated media MIME, magic bytes, digest, and payload agree, including JPEG input converted to
  PNG output;
- `ModelTurnDelivery` contains the exact ordered attached-media records, and `delivery_id` changes when final text,
  media MIME/digest/actual marks, or action routes change. Provider binding attaches exactly `delivery.media` with no
  independent `request.image_inputs` bypass; a boolean image-presence flag cannot stand in for media lineage;
- for every PerTurnToolCatalog entry and generated argument value, public schema admission is equivalent to exactly one
  private resolution row. Operation target/destination pairs and per-target business enum/range domains never widen
  into a Cartesian product;
- generated catalog factorization groups rows only when operation, operand roles, legal destination relation, and
  business parameter schema are identical. Sparse source/destination graphs preserve exact adjacency rather than
  independent enums; factorized and unfactorized relations accept the same calls and resolve to the same unique rows.
  TurnPacker prices the actual factorized schema bound to the provider;
- generated schema ASTs prove that the one `actions.schema_validation` contract and its value interpreter support the
  same bounded object/array/scalar/enum/const/range/discriminated-union subset. ToolSpec/catalog construction rejects
  unknown keywords, malformed combinations, ill-typed bounds, and overlapping or undiscriminated `oneOf` branches as
  typed pre-provider schema failures; repository search finds no JSON-tree-only schema admission path;
- fault injection at delivery construction, catalog compilation, RequestAdmission, and provider binding returns the
  declared typed local/schema/capacity outcome with `provider_attempts=0` before the bind boundary. Failure diagnostics
  use only constructed optional artifacts; the handler never raises a secondary unbound-local exception;
- repository negative search finds no active `set_form_fields`, `SetFormFields`, `ActionOption.batchable`,
  `ActionBatch`, `execute_action_batch`, form-key generator, compound-form resolver/Binder/executor, `from_form_fields`,
  or partial-form receipt path. `ExecutionReceiptBatch.from_atomic` remains for atomic attempt/uncertainty conservation.
  Generated same-label forms remain distinct in
  `WorldDeliveryIndex` for structural recall, while field edits use ordinary one-target routes and one fresh World per
  dispatch;
- one shared `PublicRefCodec` is used by every live producer/consumer. Generated refs around the declared cardinality
  boundary, including the current E999/E1000 disagreement, have identical validity in grounding, candidates, manifest,
  decisions, schemas, resolver, renderer, history, and trace; overflow is typed capacity before publication;
- an optional semantic/model reranker may improve ordering from current public World facts but may not reduce exact or
  structural recall and may return typed unavailable without changing reachability. A VLM may add typed evidence only
  through SurfaceAdapter/Fusion; repository/runtime inspection finds no direct discovery-to-VLM authority path;
- run3 comparison properties freeze internal target/fact/binding conservation and presentation-collapse counts, then
  vary functional partition sizes and leading optional candidates. They prove no candidate-only whole-region
  expansion, no loss of exact/structural routes, complete cursor recovery, and bounded total request cost. Tasks
  0/7/21/27/266 are evidence fixtures, not task-specific assertions;
- an end-to-end property traverses `fresh World → unnumbered WorldDeliveryIndex + complete ActionSpace →
  CanonicalPublicWorldProjection → PublicEffectInventory → ObservationDeliveryStore → ActionRecallSet → cursor-backed
  DeliveryObligations → TurnPacker → frozen ModelTurnDelivery/Manifest → PerTurnToolCatalog →
  CanonicalProviderEnvelope → RequestAdmission → Recording Provider → Resolver → Binder` and proves the admitted
  operation/ref/destination tuple resolves to the same current legal option. Executor actionability is tested
  separately and never used to excuse a delivery miss.

Required generic regression shape:

```text
field becomes current inside a source-provided form-like container
→ short-label sibling submit lies beyond the default byte/page budget
→ automatic structural recall or exact-label search delivers its current public ref
→ an unrelated longer lexical match may rank later but cannot replace it
→ Resolver/Binder accepts the delivered option
```

The held-out set includes non-map forms and randomized labels. A production assertion tied to `Go`, Directions,
OpenStreetMap, a fixed DOM class, or an expected rank is invalid.

### C11 — terminal algebra and finalization-totality properties

Property, model-based sequence, subprocess-crash, and fault-injection tests must prove terminal-outcome conservation:

- every currently reachable owner value is generated through every declared consumer with its enum or one exhaustive
  map. `InformationDeltaKind` traverses ObservationDelivery→Workspace/Monitor/private trace; persisted `RunStatus`,
  `DecisionKind`, action/receipt outcomes, `ControlTermination`, cleanup disposition, and report disposition traverse
  snapshot→durable case facts→public codec→decode→aggregation; evaluated official outcomes traverse their immutable
  checkpoint→id/digest join→codec/aggregation path. Consumers do not maintain copied string vocabularies;
- Monitor repetition commits typed `CONTROL_STALLED`; policy/step budget exhaustion commits typed
  `TURN_BUDGET_EXHAUSTED`; neither is inferred from display feedback or degraded to `blocked_other`;
- obsolete `last_progress_event_type` values, the reader of removed `context.progress`, and metrics without a live
  producer are deleted rather than expanded. Any retained metric names its typed producer and is nonzero under a
  generated witness;
- every body return, timeout, interruption, or exception constructs a bounded `CaseOutcomeRecord` with run/case
  identity and attempts revision `BODY` before rich projection. A successful BODY commit is durable before projection;
  a failed commit records `HARNESS_PERSISTENCE` in the remaining local/trace diagnosis, still reaches the outer cleanup
  disposition (exactly once when a handle was acquired), and never falsely claims BODY durability. Projection
  incompatibility is typed `HARNESS_PROJECTION` without changing Runtime/task outcome;
- the case finalizer is installed before environment acquisition. Once an environment handle is acquired, cleanup is
  attempted exactly once with a deadline under the outer `finally`; if acquisition never succeeds, no cleanup call is
  fabricated and the typed disposition is `NOT_ACQUIRED|NOT_APPLICABLE`. This remains true when trace event/write/seal,
  snapshot, projection construction, validation, encoding, body commit, lifecycle observation, cleanup, final
  projection/commit, JSON export, aggregation, summary export, or observer callbacks fault;
- the store owns one bounded write API. Revisions are monotonic (`BODY < CLEANUP < FINAL`); BODY is insert-only with
  byte-identical idempotent retry, CLEANUP fields only fill/advance, and equal/stale BODY retries cannot clear them.
  Generated interleavings include late same-revision and stale workers. A timed-out/cancelled worker cannot overwrite a
  newer revision; compare-and-swap conflict returns typed persistence failure and `INSERT OR REPLACE` is not accepted;
- `failure_reason` and other display text cannot affect status, `execution_completed`, terminal classification, or
  acceptance. For every public case, `accept(x) == accept(decode(encode(x)))`;
- Runtime and benchmark failure codes share one bounded codec or an exhaustive lossless mapping. Every supported
  evaluator-outcome/Runtime-status pair, including post-STOP incomplete plus failed Runtime, maps exactly once and is
  never silently discarded;
- an immutable `OfficialOutcomeCheckpoint` is the only durable copy of an evaluated official outcome.
  `CaseOutcomeRecord` stores only checkpoint id+digest (or a non-official evaluator-port disposition); generated
  missing, mismatched, or deliberately divergent pairs fail typed before projection rather than choosing one copy;
- behavior, evaluator, persistence, projection, cleanup, and export dispositions remain orthogonal. A harness failure
  fails benchmark acceptance but cannot rewrite a blocked GUI behavior into a provider/environment/task failure;
- local trace write/seal failure is typed `HARNESS_TRACE`, invalidates benchmark evidence, and remains unable to abort
  Runtime handoff or bypass cleanup; viewer/export failure remains a weaker fail-open disposition;
- executor fault injection covers before-dispatch and after-possible-dispatch boundaries. Every ordinary exception
  becomes a typed outcome, diagnostic, Runtime failure/receipt as applicable; an uncertain crossed boundary is
  `SENT_UNKNOWN` and cannot replay. No path terminates with only a display `execution_failed` string and missing receipt
  truth;
- zero-case, partial-case, between-case interruption, and per-case finalization failure produce a typed partial run
  record from the durable completed prefix; aggregation never uses a strict zip or an unpersisted in-memory result as
  authority;
- `CASE_FINISHED` is committed only with the final durable revision after body, cleanup, and report dispositions are
  known. SQLite keeps one current phase plus typed dispositions; local trace may observe chronology, but no second
  lifecycle event ledger controls the runner;
- before sealing trace, the runner records `FINAL_ATTEMPT` with expected prior revision/report disposition. Injected
  FINAL-commit failure leaves durable BODY/CLEANUP and a non-finished SQLite phase (plus that trace event when sealing
  succeeded); it need not make the failed sink persist its own failure and may never emit false `CASE_FINISHED`;
- detached status reads SQLite first and distinguishes body-not-returned, durable-body/report-pending, projection
  failure, cleanup not-started/running/completed, partial run, export failure, and complete report. Empty or stale JSON
  files cannot prove completion;
- unsupported future enum/schema values fail closed as typed projection facts while minimal persistence, exactly-once
  cleanup, partial aggregation, and detached diagnosis still complete.

The target schema deletes direct duplicate failure/cleanup/watchdog fields and fields with no production producer.
Historical v6–v11 readers live in an archive adapter; the active constructor and SQLite/JSON codec share one current
schema/privacy path.

### C12 — TaskGoal public-input and GoalPlan conservation

Provider-free generated requests, captured compiler calls, and recording policy contexts must prove that task intake,
advisory planning, and policy delivery do not police business vocabulary across either branch:

```text
NaturalLanguageTaskRequest → ThinTaskIntake → TaskGoal
                                            ├→ GoalCompiler request
                                            └→ every AgentContext.task → ActionPolicy
```

- every bounded JSON-compatible value admitted in public `TaskGoal.inputs` and `success_criteria` appears exactly in
  the initial GoalCompiler request and every ActionPolicy task context, including nested keys named `coordinates`,
  `coordinate`, `selector`, `path`, `viewport`, `x`, `y`, `dom_id`, `target_id`, and generated spelling/case variants;
- renaming a public key without changing its typed visibility changes only that key, never whether the field is
  present. If private task material is added later, TaskIntake excludes it by an explicit typed visibility field
  regardless of its name;
- one declared intake bound precedes TaskGoal construction. Inputs within it survive both branches exactly; item/depth/
  string/binary boundaries and bound+1 cases fail typed rather than silently slicing to 12 items, depth 3, 240
  characters, or `[TRUNCATED]`. A later request-capacity failure is also typed and does not delete a subtree, fabricate
  `NeedsInput`, or reinterpret partial input as the user's goal;
- the compiler output remains exactly the bounded five-field advisory GoalPlan algebra and cannot carry an action,
  tool, ref, selector, coordinate route, mutable progress, or permission. PerTurnToolCatalog/Binder remain the only
  action route;
- every Ready GoalPlan is projected unchanged into each `AgentContext`, while every complete ActionSpace route remains
  available. Generated fresh-World sequences expose already-satisfied objectives, active toggles, ready dependencies,
  and a final item to a recording ActionPolicy and admit exactly one typed decision per turn. GUI decisions carry
  exactly one current route; local observation, `AskUser`, and final-response branches carry zero GUI routes, so every
  turn has at most one. Repository search finds no Runtime item status, frontier, progress calculator, plan-based action
  filter, or auto-advance state;
- the ActionPolicy contract requires preserving visibly satisfied objectives, avoiding an already active toggle unless
  TaskGoal asks for reversal, preferring an unsatisfied dependency-ready item, and attempting the final item only after
  every dependency is clearly satisfied in fresh World. Provider-free tests prove the required context/route boundary;
  actual model adherence is separately measured on held-out W1b-Agent trajectories and cannot be claimed from a fake;
- generated envelopes prove 1–8 items, unique IDs, existing acyclic dependencies, bounded text, and at most one final;
  malformed shape admits at most one schema repair and one boundary repair, and every initial/repair transcript is
  recorded immediately;
- `Ready|NotRequired|NeedsInput|Unsupported|Failed` retain their declared control semantics. Provider/schema failure
  and `Unsupported|Failed` continue the ordinary GUI loop; only a genuinely absent user-owned fact can produce
  `NeedsInput`; task start invokes exactly one compile, an explicit TaskGoal revision invokes exactly one new compile,
  and World/layout/stall/action changes invoke none;
- repository negative search finds no active `_PRIVATE_INPUT_KEYS`, `_private_input_path`, `_PRIVATE_TASK_KEYS`, or
  `_model_private_key/_route_key` call in TaskGoal/TaskContext projection, and no `is_private_goal_semantic_name`,
  `GoalSemanticContract`, or adapter/environment goal-semantic-contract port.
  Historical readers, if retained, are archive-only and cannot enter current intake→TaskGoal→GoalCompiler→AgentContext
  composition;
- initial and permitted repair transcripts preserve the exact public request lineage. Tests use generated nested
  mappings and a recording fake provider, not a list of benchmark phrases or a live model.

## Superseded milestone-path evidence

G0–G6, the 1,487-pass/19-skip checkpoint, and run8's six-page diagnostic are revision-local evidence for the removed
Planner/Milestone/Auditor path. Their detailed criteria and results live in
[`history/benchmark-pre-milestone-convergence-2026-08-22.md`](history/benchmark-pre-milestone-convergence-2026-08-22.md)
and `evidence/w1b-world-planner-auditor-provider-free-20260822-run8/`. They are retained as regression inputs only:
Run20 falsified their broad projection/finalization assumption, and none is a present-tense owner, acceptance gate, or
permission to restore Manager, Auditor, compound actions, or mission state.

The active gates are C8–C12 above. Reusable constraints from the old evidence—one CoreLoop/Binder/executor, typed
receipts, bounded recovery, ref privacy, native evaluation, and viewer fail-open behavior—have been restated there or
in [`architecture.md`](architecture.md) against the current single-ActionPolicy owners. No live model run accompanied
the historical provider-free checkpoint.

## Live W1b acceptance

Live execution is separately authorized. For each run report:

- official task id, site family, seed, model/profile, prompt/catalog/context versions;
- official success and native-evaluator result;
- GUI decisions and physical dispatch receipts;
- ActionPolicy ordinary/recovery, representation-repair, and transport-retry calls; Planner/Auditor counts must be zero
  after migration;
- per-role prompt/completion/reasoning tokens and latency;
- request component estimates for task/plan, latest effect, changed regions, cached outline, AgentWorkspace, actual
  factorized tool schema, media/wire overhead, and output reserve; recall/obligation/admitted-page/omitted counts,
  packing backoffs, and continuation cursors;
- private diagnostic public-delta counts, changed/unchanged region reuse, latest-effect bytes/tokens, recoverability,
  ActionCandidate recall/rank, repeated-read rate, navigation excess, and no-progress rate;
- exact-label recall, structured-neighbor recall@k, semantic candidate recall@k, base/query continuation progress,
  private-ID leakage count, and text/image/manifest disagreement count;
- recent-detail, SemanticEvent, ActivitySummary, WorkingFact, workspace-fit, and whole-request-admission costs;
- optional working-note events, typed recoveries, direct final-response lifecycle, and hard-cap exits;
- typed control termination, case-body revision, report/projection disposition, cleanup disposition, late-write rejection,
  export/viewer disposition, and detached durable-result status.

For a short single-site report task, engineering targets are:

- total provider tokens: target 50k–80k, ordinary upper bound 100k;
- ordinary prompt p95 below 12k;
- zero full-context semantic repair;
- zero Planner and Auditor calls;
- no repeated unchanged region read before a valid control/evidence alternative is offered.

These are cost targets, not success substitutions.

## Required artifacts

Every case writes:

```text
run manifest
traces/<case-id>/trace.jsonl          # private, complete, local authority
artifacts/<content-addressed media>
run-results.sqlite3                   # BODY/CLEANUP/FINAL monotonic case truth + report/run dispositions
cases/<case-id>.json                  # optional materialized view
summary.json                          # optional aggregate view
```

Public reports exclude prompts, model responses, selectors, coordinates, credentials, hidden state, oracle answers,
reward payloads, and screenshots unless explicitly approved. Trace-write failure invalidates benchmark evidence but
does not change Runtime control behavior. Each durable `BODY` row contains enough run/case/profile/manifest identity to
remain self-describing if the process dies during cleanup; JSON and summary files are rebuildable views, not completion
authorities.

## Execution order

This is the only active migration order. The detailed C8–C12 properties below constrain the relevant stage; they do not
authorize parallel owner changes. Every production stage must follow the six-step per-stage cutover protocol in
`architecture.md`: freeze producer/consumer/deletion scope, implement the positive typed owner, migrate all consumers,
delete the displaced path, pass owner + CoreLoop gates, and stop before the next owner. A local regression or compile
failure cannot authorize a caller-side fallback, threshold adjustment, compatibility alias, or case branch.

1. Keep production/tests frozen. Preserve the dirty worktree, keep all earlier artifacts revision-scoped, and do not
   call a model provider or live benchmark.
2. Build Gate 0 as test-only Recording Provider instrumentation around the actual production policy/CoreLoop/provider
   boundary. It must not become a second request builder, evaluator, loop, or Runtime state.
3. Cut over **World only**: create one `CanonicalPublicWorldProjection` value from fresh World + the existing
   unnumbered `WorldDeliveryIndex` + complete ActionSpace; migrate every public ref/order consumer; physically remove
   every alternative public allocator/orderer; pass the World owner-local gate.
4. Cut over **Delivery only**: make `ObservationDeliveryStore` the sole inventory/cursor transition owner; make
   `ActionRecallSet`, `ActionDeliveryPlan`, and `TurnPacker` immutable consumers; compile Manifest routes and Catalog
   continuation tools from one frozen page; remove competing base/query/effect/candidate state and continuation
   inequalities; pass the two-turn production gate.
5. Cut over **Envelope only**: add one `ProviderEnvelopeBinder`; make RequestAdmission accept/return its exact
   `CanonicalProviderEnvelope`; reduce PydanticAI integration to a lossless wire codec; remove sidecar privacy/cost
   substitutes and post-admission message/tool/media reconstruction; pass the Recording Provider identity gate.
6. Run the vertical World → Delivery → Manifest/Catalog → Envelope → provider-recording and tool-call → Resolver →
   Binder conservation gate. This is the first point where final envelope digest/cost and end-to-end route equivalence
   count as evidence.
7. Run all relevant C8–C12 properties, causal BrowserGym transition gates, benchmark finalization fault gates, full
   pytest/static checks, repository negative searches, and a new revision-bound six-page provider-free diagnostic.
8. Run an independent fresh-context read-only review. Reconcile implementation, docs, schema version, evidence, and
   status while keeping implementation-complete distinct from verified closure.
9. Only after every active gate passes and the user explicitly authorizes it, run one non-Task-7 held-out live witness,
   then a bounded W1b cohort. Task-7 replay alone cannot satisfy closure.

The owner-local deletion details—short-token vetoes, duplicate role classifiers, `mandatory/protected` fan-out,
candidate-implied region expansion, post-hoc route inference, compound form execution, lexical TaskGoal filtering,
copied terminal vocabularies, and non-total benchmark finalization—remain in the architecture migration/deletion map.
They must be removed in the stage that owns them; they are not separate implementation phases or permission to edit
multiple owners at once.

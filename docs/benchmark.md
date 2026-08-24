# Benchmark

## Current status

The thin tool-result/history cutover, accepted-response repair, owner-level action-discovery/catalog repair,
readable-AX completeness repair, single-current-World cutover, atomic PageMap/Manifest repair, and bounded post-action
recapture repair, and BrowserGym large-page liveness, viewport-grounded media, canonical public-identity, and linear
fresh-World projection repairs are implemented. The current convergence patch additionally filters control discovery,
publishes only profile-supported BrowserGym navigation, detects same-World discovery loops, proactively processes SDK
history, bounds the PageMap directory while retaining the complete recoverable region index, orders the ordinary
model-visible action prefix by the existing task-aware rank before incidental focus, and gives Monitor
producer-specific recovery guidance for action discovery versus local-result replay. The current owner repair further
decouples action callability from that prefix: stable registry action schemas accept current E-ref syntax and the
existing complete current `ActionSpace` resolver performs exact route/domain validation.
Task266 run6 crossed the run5 failure and exposed the remaining browser-profile selector mismatch. Browser-level
primitives now follow BrowserGym's target-less public shape and bind the unique fresh `browser_context` privately;
page-control primitives still require current `E-ref` grounding. Explicit `find_controls` recall is limited to literal
token/phrase boundaries and no longer uses hand-written prefix/suffix or fuzzy expansion.
Task266 run7 crossed that repaired navigation boundary, found the real Wikipedia search textbox, entered the query,
and received a stable fresh World. It then exposed a separate explicit-recall algebra defect: `link` in
`Portland (Maine) link` matched the role of every background link even when `Portland` and `Maine` matched neither its
label nor path. The autocomplete rows themselves were honestly projected as non-executable `StaticText`; no action was
missing from the catalog. The recall owner now requires remaining target terms to match label/path, ranks all genuine
matches by target coverage, and leaves an executable-control miss empty instead of suggesting readable-content search.
Verification counts below are refreshed only after the current full provider-free run. The repository-wide mypy
command still reports its pre-existing baseline errors in unchanged modules.

Current provider-free verification passes `136` focused action-recall/delivery/catalog tests, and the full suite at
`1692 passed / 19 skipped`. Ruff, compileall, `git diff --check`, and the bounded fresh review
pass. This is implementation evidence for the bounded changes, not a live witness for the Task266 repair.

Overall project status remains **reopened / non-closed**. This cutover does not close:

- post-repair live validation of the combined BrowserGym large-page capture/projection repairs;
- the Planner lexical-admission gap;
- any broader live provider/benchmark gate.

Run18 is the accepted post-repair Task21 witness: Runtime ended `done` and the native evaluator returned
`verified_success`. Task27 run2 accepted with native `verified_success`, live-verifying the post-action recapture
repair; Task44 run1 also accepted. Task266 run1 is a stopped, failed pre-repair diagnostic for the liveness defect
described below; Task266 run2 live-validates liveness but is a failed pre-repair diagnostic for the subsequent media
projection defect. Task266 run3 crossed that repaired media boundary and is a failed pre-repair diagnostic for the
subsequent public-identity capacity defect. Task266 run5 crossed those large-page boundaries and failed normally at a
later action-delivery ordering defect: the complete current ActionSpace contained the correct ranked result link, but
the bounded model catalog exposed an incidental focus route instead. Run5 is pre-repair evidence, not acceptance.
Task266 run6 crossed that action-callability boundary, activated the intended article, and recovered the official city
coordinates. It then failed normally after the model searched twice for an address-bar control because `goto` still
required a browser-context `E-ref` absent from the compact observation; Monitor blocked the loop. Run6 is also
pre-repair evidence, not acceptance.
Task266 run7 crossed the target-less browser-navigation repair and failed normally after six valid policy calls, one
effectful query-entry dispatch, and zero invalid tool arguments. Its `find_controls("Portland (Maine) link")`
ToolReturn contained alphabetical background links such as Africa and Agriculture because the shared role token alone
qualified them. Two identical `read_region(R13)` results followed; Monitor emitted one recovery and then blocked the
control stall. Run7 is failed pre-repair evidence for explicit control recall, not acceptance.

The explicitly authorized W1b run8 witness is a failed pre-repair diagnostic, not acceptance. It proved progress-note
retention in physical history, then terminated with `policy_failure_code=invalid_tool_arguments` when the model chose
an `E25` route returned by `find_controls` but the next `activate` schema admitted only `E53`. Run10 revalidated that
catalog repair with five valid model tool calls and zero invalid arguments, then failed the native evaluator because
readable AX text had been silently truncated upstream. The untracked `output/` directory is unrelated user data and is
not an acceptance artifact.

Official success remains the benchmark-native evaluator's or `TaskEvaluator`'s post-capture result. A model final
answer, local action receipt, GoalPlan item, or Monitor classification cannot declare a GUI task successful.

## What this cutover fixes

The held-out R9 sequence exposed three related symptoms:

1. search returned a current region ref that the next `read_region` schema did not admit;
2. a large region result was bounded by logical item count rather than final serialized bytes;
3. the resulting data was copied through Store/Workspace/TurnPacker and changed shape before the model consumed it.

The later live trace added a fourth, directly observed symptom: one turn received the requested names, the next read a
continuation page, and the following turn repeated the search. `TaskGoal`, `GoalPlan`, and fresh World were present.
The PydanticAI bridge had retained only the latest pending exchange, so the earlier completed ToolReturn was absent.

After direct call/result history was restored, the same trace exposed the remaining owner defect: the provider response
contained the model's conclusion that the answer was ready, but the bridge reconstructed the accepted response as a new
`ModelResponse` containing only `ToolCallPart`. The raw conclusion therefore existed in Trace but not in the next model
turn. Retaining the full hidden reasoning would make the already growing context worse, so the positive contract is one
short, model-authored, visible progress note plus one accepted call. No second summarizer model or Runtime evidence
memory is introduced.

The authorized run8 trace verified that repair: later `llm.input_messages` contained the earlier bounded progress notes,
accepted calls, and matching ToolReturns. It then exposed a distinct capability-publication defect. The
`find_controls` ToolReturn contained `E25` and `activate`; the next ToolCatalog admitted only the first query route,
`E53`, because remaining query routes were treated as soft-target optional inventory. The model selected `E25` from
the immediately preceding result and the call failed schema validation. This was not a World, task, GoalPlan, or model
comprehension failure.

The authorized run10 trace verified the route repair and then exposed the next shared owner defect. `read_region`
reported a complete item inventory, but `SurfaceAdapter` had sliced every AX accessible name to 240 characters before
World construction. Catso's and Michelle's relevant conclusions were after character 240, so the model received only
the prefixes and reasonably excluded them; its retained progress note then called the incomplete observation complete.
The failure was observation loss plus a dishonest completeness label, not missing TaskGoal, World identity, history
compression, cursor state, or a need for another summarizer model.

Run11 verified the readable-AX repair in the live agent chain: search/read returned full complete records for all four
relevant descriptions, with ten valid tool calls and no argument failures. The last provider request then timed out
before returning any final decision, so no native evaluation occurred. Run12 reached STOP and native evaluation with
five valid calls and no argument failures, but the model submitted only the two literal `ear cup` matches. Its recorded
reasoning explicitly said Catso and Michelle semantically imply small ear cups, then discarded them as non-literal.
That is an ActionPolicy semantic-admission defect, not renewed observation or history loss.

Run13 then failed for a different, fully traced reason. Page 2 was stable and the same request already contained
Michelle Davis's full completed ToolReturn, but the model-visible current observation also contained the previous GUI
receipt as `LatestEffect transition=new_document`, plus `ActionCandidates empty`. That state came from a retained
Store projection, not BrowserGym navigation. The repeated `wait` calls were therefore a rational response to
contradictory context, not missing task text, lost evidence, insufficient search, or failure to refresh after the GUI
action.

The current repair deletes that second current-state path. Fresh World/PageMap is the only model-visible GUI state;
completed actions remain historical receipts; Store is confined to bounded Monitor digests in `RunState` and is absent
from `AgentContext`. A Recording FunctionModel vertical gate executes a GUI action, reaches a second policy call over
the fresh post-action World, and verifies that `LatestEffect`, `CurrentFindings`, `ChangedRegions`, and `new_document`
are absent. No replacement effect channel or lifecycle was introduced.

The authorized run15 trace revalidated that cutover and exposed the next acceptance gap. It made 12 policy turns with
zero `wait` calls, clicked the Reviews tab once, and BrowserGym captured a fresh second observation containing the full
review records. The following turn failed locally with zero provider attempts:

```text
ValueError: delivery Manifest contains a ref absent from admitted text/media
```

The exact missing ref was `R11`, the review form region. `TurnPacker` starts from the legal zero-candidate prefix;
`PageMap` registered every region ref but returned an empty descriptor when `R11`'s optional heading exceeded the
descriptor budget. Default/full candidate selections happened to print `R11` elsewhere and masked the producer bug.
The renderer had the same algebraic defect for facts on nodes hidden by duplicate-text suppression.

The owner repair makes PageMap/Manifest construction atomic. Every emitted region has one minimal descriptor; optional
descriptor fields are admitted individually. Hidden nodes cannot register facts. The existing `ModelTurnDelivery`
gate remains strict and rejects any future non-atomic projection before provider invocation. Replaying run15's exact
656-target fresh observation with 137 current actions and the zero-candidate selection now builds a 15-region delivery,
keeps `R11` in both text and Manifest, and compiles the current tool catalog.

The large-page follow-up now bounds the aggregate PageMap directory instead of emitting every descriptor indefinitely.
Selected/candidate/salient/landmark regions are prioritized; a reduced map reports `shown/total`, `coverage=partial`,
and its existing recovery tools. `WorldDeliveryIndex` remains complete, and `list_regions` can enumerate every omitted
region. This is current-view token fitting, not content-prefix clipping, evidence storage, or a new cursor protocol.

Run15 also showed a separate search-contract pollution: query `small` matched HTML tag/class/ID scaffolding even though
the tool advertised `searched_domain=readable_content`. Search matching and returned state now use visible labels/text,
normal public semantic values, and human-facing title/alt/placeholder/ARIA attributes while excluding structural DOM,
appearance, layout, and internal bookkeeping fields. This fixes the advertised boundary without adding search DSL,
BM25, dense retrieval, a summarizer, or a benchmark-specific extractor.

The authorized run16 trace passed the agent-side task. It made 16 valid policy/tool calls, issued no invalid arguments,
returned the four correct names in a schema-valid official final response, sent one STOP, captured one post-STOP World,
and invoked the native evaluator once. The native snapshot classified success, but the Runtime ended with
`task_evaluator_validation_failed: COMPLETE task evaluation is missing a requested output`.

That failure was an acceptance-contract half-migration. W1b still declared the model's final STOP payload as
`requested_outputs=("webarena_final_response",)`. The generic validator therefore correctly required a corresponding
current-World `EvaluatedOutput`, while the current WebArena path correctly treated the same value as the
environment-codec-normalized payload already sent to BrowserGym. The serial cutover had removed the old public response
schema path but had not removed this stale output declaration or its W0 manifest field.

The repair deletes those two obsolete declarations and does not weaken `validate_required_outputs`. A new production
vertical test opens the W1b composition over fake BrowserGym, supplies a valid official response, and proves
codec-normalized content -> exactly one STOP -> post-STOP capture -> native success -> `RunStatus.DONE`, while
`TaskEvaluation.outputs` remains empty. No response artifact, evaluator projection, Store, or additional terminal state
was added. Run16 remains diagnostic evidence; run18 is the accepted post-repair live witness.

Task27 run1 failed after the model correctly selected and BrowserGym dispatched the Forums link exactly once. The
transition trace records `/ -> /forums`, navigation start and commit, and document epoch `1 -> 2`, but the bounded
post-action DOM-quiet gate returned `acquisition_unstable` before capture. `CoreAgentLoop` did not invoke the existing
independent recapture because that path was restricted to `sent_unknown`; BrowserGym would also have rejected the
recapture because the instability code remained sticky.

The repair generalizes the already-bounded execution contract: any dispatched action whose normal post acquisition is
not acquired may receive one independent read-only recovery acquisition. BrowserGym permits that second acquisition
for `acquisition_unstable`, using its existing `capture_current()` path, while `navigation_pending` remains typed and
fail-closed. The action is never replayed, a successful recovery becomes the same receipt's after-observation, and a
failed recovery cannot reach another policy turn with stale World. No action retry, timer loop, transition framework,
cursor, evidence path, or benchmark-specific branch was added. Task27 run1 remains a pre-repair failed witness;
Task27 run2 is the accepted post-repair witness.

Task266 run1 then reached the Wiki search results and the model correctly selected the `Portland, Maine` link. Its last
model call completed in about 4.1 seconds; no later `step_completed` event appeared, heartbeat stopped, and the live
Python/Playwright processes continued consuming CPU. The user explicitly sent SIGTERM to the single detached session,
but the blocked event loop did not process it until about 534 seconds; formal durable status is
`failed / environment_unresponsive`, with trace and SQLite evidence intact.

The failure was not provider latency or missing fallback policy. The Portland article contains 5,064 HTML elements and
1,482 links; the pinned BrowserGym extraction yielded 12,369 AX nodes and 3,397 BIDs. After BrowserGym had already
captured one DOM/AX snapshot, the project made five synchronous Playwright calls per BID to add private physical
properties—roughly 17,000 RPCs. That synchronous facade was called on the asyncio event loop, preventing heartbeat and
the 900-second watchdog from being scheduled. Its 180-second command timeout then queued `capture_current()` behind
the still-running owner command, so the existing observation fallback could not execute.

The owner repair keeps the published contract and removes the unbounded mechanism. Physical properties are evaluated
once per frame in the browser and joined to the BrowserGym snapshot by private BID. All synchronous currentness,
step, capture, finalization, and health calls execute off the asyncio loop. A hard owner timeout poisons that physical
session and rejects later capture immediately rather than queueing behind uninterruptible work; no action replay is
allowed. The exact Portland page now completes BrowserGym extraction in about 1.55 seconds and bulk enrichment in
about 1.0 second for all 3,397 BIDs. This is a general page-size invariant, not a Wiki/Task266 threshold or branch.
Task266 run1 remains pre-repair evidence.

Task266 run2 completed normally in about 164.5 seconds with heartbeat continuously schedulable. The model again chose
the correct article, and BrowserGym returned `stable_navigation` with post-capture complete at about 7.0 seconds. The
run then ended `blocked / post_action_acquisition_failed`: screenshot projection copied 2,413 page-wide boxes into one
1280×720 media record even though its existing contract admits at most 512 grounding regions. Exact replay measured
5,999 valid structural controls but only 70 boxes intersecting the current viewport; off-screen boxes extended to
about y=27,512.

The media owner now retains only viewport-intersecting boxes, clips them to the captured image, and prioritizes
executable controls if a viewport itself exceeds the existing bound. Structural targets and bindings remain complete;
the exact page projects 6,001 total targets, 1,923 bindings, 4,096 bounded facts, and 70 valid screenshot regions.
Post-action projection exceptions now also preserve a typed `post_action_projection_failed` reason plus the bounded
execution diagnostic. This reuses the existing screenshot, geometry, media contract, and recovery route; it adds no
result cursor, screenshot paging, task heuristic, or alternate World. Task266 run2 is pre-repair evidence for this
defect; a new explicitly authorized live run is required for acceptance.

Task266 run3 then crossed screenshot projection. The trace contains completed query entry, submission, current-page
reads, and selection of the intended article before sequence 22 recorded
`ValueError: public reference capacity exceeded`. Formal status is
`failed / harness_projection / case_projection_failed` after about 184.1 seconds. Heartbeats at approximately 30,
65, 95, 128, and 184 seconds prove the process was schedulable; zeroed formal action/model metrics are unmeasured case
projection output, not evidence that the preceding trace did not execute.

The canonical owner had assigned separate public identities to a semantic target and its one linked structure
occurrence. The repair aliases that unique occurrence to the existing semantic `E/N` ref, while preserving separate
refs for unlinked structure and repeated real occurrences. The exact article now remains below every public ref-kind
bound with `E=985`, `N=5,740`, `F=8,668`, and `R=335`.

Held-out full-chain replay also found that the private `WorldEvidenceIndex` imposed a second 4,096-record threshold on
an already accepted World containing 4,096 facts plus controlled artifacts. The threshold is removed: the index now
resolves the current World's complete canonical fact/artifact set and publishes no result body or model-visible
inventory. Sorted lookup replaces repeated linear membership checks.

Finally, measured large-page stalls came from repeated derivation, not BrowserGym or provider waiting. World component
validation and Fusion performed per-entity full scans, and automatic candidate ranking performed pairwise fuzzy
matching across the full task instruction and all 1,923 actions. Local maps make the World derivations linear in their
accepted inventories; automatic ranking uses lexical/structural signals and reserves fuzzy matching for an explicit
bounded query. This changes no action authority, schema, World, or ToolReturn contract.

The exact post-repair local chain now completes `BrowserGym capture -> Surface -> Fusion -> ActionSpace ->
WorldDeliveryIndex -> CanonicalPublicWorldProjection -> ContextBuilder -> ModelTurnDelivery` in about 27.2 seconds,
with stage times `10.1 / 4.3 / 5.2 / 0.3 / 4.2 / 1.0 / 1.9 / 0.1` seconds. It produces 6,001 targets, 1,923 actions,
335 regions, 8,668 public fact records, 9,131 private resolver refs, 10 actually admitted manifest refs, and an
85,257-byte bounded model delivery. No ref-cap increase, evidence side channel, fallback, retry, task branch, or cursor
was introduced. Run3 remains pre-repair evidence; acceptance still requires a fresh authorized live run.

The bounded general repair is in the existing ActionPolicy prompt: `search_page_content` is an exact-substring locator,
while the complete records it returns are judged by the model for entailment/paraphrase. For a known collection the
model reads its region and follows visible GUI pagination instead of issuing synonym searches. Partial source
coverage, visible pagination, or a displayed total larger than inspected records keeps an exhaustive retrieval open
while the current GUI can inspect it. No reviewer, task phrase, site, expected answer, BM25/dense index, second model,
or Runtime semantic branch is encoded.

Those defects were generalized into a generic evidence inventory and continuation system. Subsequent subtype,
currentness, producer, and Store-composition failures all arose on that shared path.

The current repair removes the duplicated path:

```text
local ToolCall(call_id)
-> current catalog resolver
-> owner-bounded direct result
-> StepResult
-> same-call PydanticAI ToolReturn
-> bounded visible progress + typed call/result history for later policy turns
-> next Recording FunctionModel turn
```

Read/search/list pagination is optional and local to the same tool. Search returns the smallest complete enclosing
repeated item so ordinary record lookup does not require reading an entire large region. GUI effects and action
discovery do not use the read cursor.

BrowserGym informational AX text is now preserved into World. The read owner packs whole repeated records against the
final ToolReturn byte budget; it does not cap every body at 240 or 2048 before computing that total. Only a record that
cannot fit alone is safety-bounded and returned as `partial_item` with `content_truncated=true`. A real-page Chromium
AX diagnostic confirmed that the four relevant bodies (327, 660, 1112, and 906 characters) survive the semantic owner,
including the two conclusions beyond character 240. This diagnostic supports the owner repair but is not a benchmark
acceptance run.

Action discovery now has one explicit bounded invariant:

```text
find_controls same-World ToolReturn routes
== routes admitted to the next same-World ToolCatalog
```

The ActionDeliveryPlan fails closed if a returned route cannot be closed over the current `ActionSpace`. TurnPacker
admits the complete bounded query capability set against the hard request limit before soft-target optional inventory.
If history prevents hard admission, the existing PydanticAI-boundary history compactor drops oldest complete exchanges
and repacks; no partial query result is advertised. No cursor, Store body, evidence inventory, or new state machine is
introduced.

The query owner now also enforces the missing filter invariant: role/operation terms may constrain a candidate, but
cannot qualify it while remaining target terms match neither its label nor functional path. Genuine matches remain a
bounded ranked set for the model rather than a Runtime-selected singleton. Focus and viewport break equal ordering but
never admit unrelated controls. Because this result is capability discovery rather than task evidence, Store produces
no information novelty for it; Monitor recovers on a second consecutive same-World discovery and blocks another
post-recovery discovery loop.

The WebArena runner now explicitly selects BrowserGym's installed `goto`, `go_back`, `go_forward`, `new_tab`,
`tab_focus`, and `tab_close` primitives as ordinary current `browser_context` actions. The adapter does not infer this
from task text or benchmark/task ID. They traverse the existing
Catalog/Binder/Executor/stable-capture route; MiniWoB receives none of these global actions. `tab_focus` is present only
when another current tab exists and enumerates its current tab index.

## Provider-free acceptance gates

### G1 — exhaustive local-tool producer algebra

For every local tool registered by the current grounded catalog, a schema-valid generated call is resolved and the
exact decision/result subtype is checked. The gate also asserts that `read_next_page` and
`action_results_next_page` are not registered.

This prevents the original class of defect in which a continuation or local producer returned a semantically unrelated
result subtype.

### G2 — owner-bounded read/search/list results

Properties cover:

- ordinary and Unicode result items;
- final serialized ToolReturn byte fitting;
- finite same-tool numeric page progress;
- invalid cursor as a typed result;
- complete records packed first against the final serialized result limit;
- oversized individual content returned as `partial_item` with `content_truncated=true`;
- absence of `content_fragment`/digest/reassembly protocol;
- no loss or duplication across records, with every fitting record exact and every non-fitting record explicitly
  partial.

The byte bound belongs to the read/search/list owner, not Store or request packing.

### G3 — direct same-call result and bounded SDK history

A Recording PydanticAI `FunctionModel` executes:

```text
read_region(Rx)
-> ReadRegionResult(page 1, next_cursor)
-> read_region(Rx, cursor)
-> ReadRegionResult(page 2)
-> submit_final_response
```

The second physical provider input contains page 1 under its original call ID. The final physical input contains both
completed accepted pairs in order: page 1 under call 1 and page 2 under call 2. Their contents equal the corresponding
committed results, and no prior user/World prompt is retained. A terminal response clears the bridge history. The Store
contains only bounded digest receipts and no result body/inventory.

A second Recording PydanticAI gate emits `ThinkingPart + TextPart + two ToolCallPart` values. The accepted response in
the following physical provider input contains only the bounded model-authored `TextPart` and the one accepted normalized
call; its matching ToolReturn follows under the same call ID. Hidden reasoning and the discarded call remain observable
in the raw transcript but are absent from future model context. An overlong visible note retains a bounded prefix and
conclusion suffix with an explicit truncation marker.

A history-pressure gate invokes the official PydanticAI `ProcessHistory` capability before hard overflow. It proves
that oldest complete response/result exchanges leave atomically, exact call IDs remain paired, and the newest response
with its cumulative progress note remains present. No summary model or reconstructed ToolReturn is involved.

### G4 — R-ref follow-up

The `read_region` schema accepts the public `R` syntax for the current canonical World, and the resolver validates the
actual current ref. This avoids building a schema enum from a previously admitted result prefix while preserving
currentness at the correct owner.

Search results continue to return a direct `read_region(region_ref)` follow-up for readable matches.

### G5 — action discovery remains bounded and separate

`find_controls(query)` returns only bounded query-qualified current matches and never dispatches a browser action. It
has no public generic continuation capability and no private public-result inventory. Partial coverage tells the model
to refine the query.
Every `(operation, E-ref[, destination])` route returned in that result is resolved against the next same-World
complete current `ActionSpace`. The public schema stays independent of result count and candidate packing; exact
operation membership, destination adjacency, target-specific parameter domains, and private action identity remain in
the existing resolver. A corrupted, unavailable, or stale ref fails closed before Binder/Executor.

Property and Monitor gates prove that focused/unrelated controls remain excluded, permutations do not change match
membership, discovery creates no `InformationDelta`, and the second consecutive same-World discovery produces typed
recovery rather than an unbounded query loop.

For an ordinary turn without an explicit discovery result, one vertical gate gives the action delivery only one
visible route and proves that the first task-ranked automatic candidate—not an incidental focused-context route—enters
the Manifest. A second gate gives the delivery zero visible routes and proves that its action schema is unchanged and
that every exact current route remains resolvable through the same Catalog resolver. Monitor gates separately prove that
control-discovery recovery and exact local-result replay publish producer-appropriate next routes; the latter points to
same-tool `next_cursor`, a different relevant region, a current executable control, or browser navigation.

### G6 — GUI route remains unchanged

Existing provider-free integration tests continue to verify:

```text
ToolCall -> SelectAction -> Binder -> Executor -> stable capture -> fresh World -> StepResult
```

The post-action repair reuses this route. A failed normal acquisition now permits one independent read-only recapture
for the same dispatch; tests prove a recovered fresh World reaches the receipt and next control state with one physical
action. Task27 run2 supplies the live recapture witness. Task266 runs 2 and 3 remain ordered pre-repair witnesses for
media and public-identity projection; the complete repaired large-page route still requires a fresh live witness.

The current vertical gate additionally forces a second Recording FunctionModel call after a GUI action and verifies
that its observation comes from the fresh `WorldDeliveryIndex` PageMap with no retained effect/currentness block.

Browser-global action gates verify profile isolation and the official BrowserGym action strings for all six navigation
operations. They do not add a local navigation tool or bypass normal currentness and capture.

### G7 — deletion and non-specialization gates

Production negative searches must find no:

- `PublicEvidenceResult`, `PublicResultInventory`, or `PublicResultRecord`;
- `DeliveryContinuationCapability` or `ContinueDeliveryResult`;
- `read_next_page` or `action_results_next_page`;
- admitted-evidence prefix or copied `latest_public_results` transport;
- Store-owned result body/cursor/pending provider exchange;
- model-visible `LatestEffect`/`ChangedRegions` or Store/effect input in `AgentContext`;
- `content_fragment`/fragment offset/reassembly path;
- `remember_fact`, `WorkingFact`, or Workspace working-set result-retention path;
- Task21, R9, reviewer-name, site, selector, or benchmark-case production specialization.

### G8 — atomic current delivery

Every `DeliveryManifest` ref must occur in the same admitted text or exact media. The gate covers oversized optional
region descriptions, hidden/de-duplicated node facts, zero-candidate delivery, partial prefixes, and ordinary full
delivery. It does not allow TurnPacker or the provider bridge to ignore missing refs.

Readable search is checked separately against structural pollution: DOM tag, class, and ID values cannot trigger or
appear in a search result, while visible content with the same query still matches.

A large-directory property separately verifies aggregate PageMap descriptor tokens stay within `DeliveryLimits`, the
partial marker is honest, every emitted R-ref remains atomic with Manifest, and `list_regions` still recovers the full
unchanged region count.

### G9 — one public identity and bounded large-World derivation

A unique source structure occurrence linked to a semantic target reuses that target's `E/N` ref. Unlinked structure
and multiple real occurrences remain separately addressable. A scaled capacity property proves linked structure does
not double public-ref consumption, while duplicate-occurrence and unlinked-node tests preserve ActorWorld uniqueness.

`WorldEvidenceIndex` resolves every canonical fact and controlled artifact in an accepted World; it cannot impose an
independent lower total-count contract. Large-World owner tests also verify reusable explicit-query fuzzy scores and
that automatic ranking does not invoke pairwise fuzzy search over a full task instruction. The exact Portland replay
is the integration witness for the complete current-World delivery, not benchmark acceptance evidence.

## Verification commands

Focused owner/vertical suite:

```bash
pytest -q \
  tests/unit/model \
  tests/integration/model \
  tests/benchmarks/model/test_grounded_tools_v2.py \
  tests/unit/agent/test_action_candidate_delivery.py \
  tests/unit/agent/test_action_delivery_plan_properties.py
```

Result: `324 passed`.

Readable AX owner/vertical suite:

```bash
pytest -q \
  tests/unit/surfaces/browsergym/test_browsergym_canonical_semantics.py \
  tests/unit/agent/test_semantic_delivery.py \
  tests/integration/agent/test_browsergym_read_delivery.py
```

Result: `63 passed`.

Full and static verification:

```bash
pytest -q
ruff check src tests
python -m compileall -q src tests
git diff --check
```

Result: `1676 passed / 25 skipped`; Ruff, compileall, and `git diff --check` pass. One pre-existing
`multiprocessing` fork deprecation warning remains in the observability test.

`mypy src` is not currently a green repository gate: it reports the existing baseline across unchanged modules. This
repair adds no mypy suppression and does not claim that baseline as passing.

No live provider command belongs in this provider-free acceptance sequence.

## Benchmark cohorts

### W0 — environment readiness

Validate the project `.env`, fixed BrowserGym Python 3.12 interpreter, installed BrowserGym/MiniWoB versions, project
MiniWoB URL, and static server health. Do not infer missing runtime configuration from an unconfigured shell.

### W1 — provider-free contracts

Run owner, property, integration, Recording FunctionModel, static, privacy/currentness, and fresh-review gates. W1 can
establish implementation correctness for a bounded contract; it cannot demonstrate GUI generalization.

### W1b — explicitly authorized live compatibility smoke

When authorized, run only the named witness/profile and persist the formal per-case artifact before any optional
summary. A provider timeout, environment failure, GUI case failure, and post-run reporting failure are distinct
outcomes.

### W2 — frozen benchmark cohort

The benchmark cohort is the final empirical test of cross-task/cross-site generalization and robustness. Production
code may not branch on cohort identity, task text, page wording, selector, fixed action ID, or expected output.

## Live-run authorization and execution

A live run begins only after the user explicitly authorizes it. Reuse the project facts in `AGENTS.md`:

1. load `/home/yang/projects/affordance-runtime/.env` without printing secrets;
2. use `/home/yang/.venvs/affordance-browsergym-py312/bin/python`;
3. health-check `http://127.0.0.1:18888/miniwob/click-button.html`;
4. reuse/start the project-specific static service only if needed;
5. set the explicit provider/model profile for the run;
6. persist formal per-case results before auxiliary reporting.

Background execution must use one persistent session. Report its session ID immediately and poll only that session
when the user asks to view progress.

## Fresh-review questions

The final read-only review for this cutover must answer:

1. Is any local ToolReturn body still copied into Store, Workspace, recent user context, or TurnPacker?
2. Can any generic continuation tool still be registered or resolved?
3. Does every registered local producer return the subtype declared by its contract?
4. Can a result exceed its owner byte bound or require fragment reassembly?
5. Does physical PydanticAI history preserve bounded completed accepted call ID/result pairs, append the current
   same-call result, exclude old World prompts, and clear on terminal completion?
6. Does each retained response contain at most one bounded visible progress note and exactly one accepted call, while
   hidden reasoning and discarded calls remain absent from later provider input?
7. Does every route in a same-World `find_controls` ToolReturn appear in the next frozen catalog, including when the
   soft target cannot admit unrelated optional inventory?
8. Does a discovery/current-ActionSpace route mismatch fail closed before provider invocation?
9. Is the BrowserGym change limited to preserving informational AX text and explicitly marking bounded control labels,
   without changing Binder, Executor, GoalPlan, evaluator, or benchmark semantics?
10. Are the remaining action-page/observation cursors private implementation details rather than model-visible evidence
    state?
11. Does a failed normal post-action acquisition receive at most one read-only recapture, preserve one physical
    dispatch, admit only the recovered fresh World, and keep `navigation_pending` fail-closed?
12. Does BrowserGym enrich one captured BID inventory in O(frames) Playwright round trips, keep synchronous physical
    calls off the asyncio loop, and reject fallback immediately after an owner timeout?
13. Does screenshot grounding include only regions present in the captured viewport, clip regions to the image,
    preserve executable priority within the media owner's bound, and leave structural targets and bindings intact?
14. Does `find_controls` exclude unrelated controls, and can repeated discovery avoid both false Store novelty and an
    unbounded same-World loop?
15. Are browser-global actions offered only by the WebArena-family profile and executed through BrowserGym's existing
    ActionSpace/Binder/Executor path?
16. Does SDK history compact before hard overflow while pinning the newest progress response and exact pending pair?
17. Can a large PageMap report honest partial coverage within one aggregate bound while the existing `list_regions`
    tool recovers the complete current region index?

## Exit statement

Passing this document's provider-free gates permits describing the thin result cutover and bounded recapture
implementation as verified. It does not permit describing the whole GUI agent, BrowserGym causal transition, Planner
admission, or benchmark campaign as closed. Those statuses change only when their own falsifiable gates and, where
required, an explicitly authorized live benchmark pass without case-specific production branches.

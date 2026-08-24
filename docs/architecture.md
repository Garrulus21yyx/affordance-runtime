# Architecture

## Current status

The current production target is a thin, single-loop GUI agent. The former generic evidence-delivery system is no
longer part of the architecture: local tool results are not copied into a Store-owned public inventory, repacked as an
admitted prefix, or exposed through generic continuation tools.

Implementation of the thin result/history cutover, action-discovery closure repair, readable-AX completeness repair,
single-current-World cutover, atomic PageMap/Manifest repair, bounded post-action recapture repair, and BrowserGym
large-page liveness, viewport-grounded media, canonical public-identity, and linear fresh-World projection repairs is
complete. The current convergence patch additionally makes control discovery a real filter, publishes BrowserGym's
official global navigation actions only for WebArena-family profiles, counts same-World discovery loops in Monitor,
applies proactive SDK-history processing, byte-bounds the PageMap directory without shrinking current World, and
keeps task-ranked current actions ahead of incidental browser focus when only a bounded action prefix fits. The
current action-boundary repair also makes that rank purely presentational: registry-owned action tools use stable
E-ref-shaped schemas, while the existing complete current `ActionSpace` resolver alone validates the selected ref,
operation, destination, parameters, and private action identity.
Verification counts below are refreshed by the current review; live benchmark validation remains separately authorized.
The repository-wide mypy command still reports its pre-existing baseline errors in unchanged modules and is not counted
as a passing gate.

Current provider-free verification: the focused action-schema/resolver/delivery/PydanticAI surface passes `178`
tests; the full suite passes `1684` with `19` skipped. Ruff, compileall, and diff checks pass. The fresh review found no remaining blocking owner,
currentness, result-pairing, Manifest-conservation, readable-search, public-identity, large-World projection,
recovery-eligibility, or async-liveness defect in this bounded implementation.

Overall project closure is still **open**:

- the combined BrowserGym large-page capture/projection repairs still require a post-repair Task266 live witness
  before their separately scoped gate can close;
- Planner lexical admission still has a known gap.

Run18 live-verified the terminal output-ownership repair on Task21: the official response was accepted, Runtime ended
`done`, and the native evaluator returned `verified_success`. Task27 run2 then live-verified the bounded post-action
recapture path, and Task44 run1 independently completed with native `verified_success`.
Task266 run2 live-verified the large-page liveness repair, then exposed the separate screenshot-grounding projection
defect described below. Run3 crossed that media boundary and exposed the subsequent public-identity capacity defect;
it remains failed pre-repair evidence, not an accepted witness.

A live W1b witness was run after the accepted-response repair. Run8 verified that bounded model-authored progress notes
survived into later physical provider inputs, then failed on an independent action-discovery/catalog mismatch. Run10
revalidated the subsequent catalog repair: all five model calls were contract-valid and the earlier `E25` mismatch did
not recur. It then exposed the separate readable-AX truncation defect described below. Neither failed run is benchmark
acceptance evidence.

## Root cause of the R9 escalation and repeated reads

The original observed problem was small:

1. `search_page_content` returned a current region ref such as `R9`.
2. the following catalog did not admit that ref to `read_region`;
3. after that was repaired, the R9 result exceeded the serialized result budget.

The project then treated exact result conservation as a cross-cutting Runtime problem. One local read result was made
to serve provider history, long-lived evidence, Monitor novelty, Workspace history, pagination inventory, request
packing, and benchmark trace. That produced duplicated result authorities and generic continuation state. The later
subtype and projection failures were consequences of that coupling, not evidence that GUI agents require it.

The repair is owner-first:

- the current catalog/resolver validates the current `R-ref`;
- the read/search/list owner bounds its own public result by serialized bytes;
- PydanticAI pairs that result with the original call ID;
- other components may observe a receipt or digest, but cannot transform the result.

The later live repetition had a separate immediate mechanism on that same overbuilt path. The provider port retained
only one pending exchange. A turn could see the names returned by search, and a continuation turn could see the next
page, but the following turn retained only the latest ToolReturn. The earlier names had disappeared even though
`TaskGoal`, `GoalPlan`, and the fresh World were present and correct, so the model searched again.

The positive repair is the SDK's ordinary conversation contract: keep a bounded sequence of completed typed
`ToolCallPart -> ToolReturnPart` pairs, append the current pending call, and always supply the fresh World separately.
Old World prompts are not retained. This replaces the one-slot exchange and the manual `remember_fact`/working-set
path; it does not add an evidence store, memory subsystem, or cursor state machine.

The live witness then exposed a separate action-capability mismatch. `find_controls` returned `E25` with verb
`activate`, but the next physical `activate` schema admitted only `E53`. The model selected the just-returned `E25`, so
the failure was not missing task context or discarded reasoning. `TurnPacker` had treated the query result as ordinary
optional route inventory: it hard-admitted only its first route, then allowed the soft request target to exclude the
rest even though the complete request was far below the hard context limit.

The positive repair is bounded and owner-local: one same-World `find_controls` result is one capability set. Every
returned `(operation, E-ref[, destination])` route must close over the current `ActionSpace` and be admitted to the
next catalog together. A mapping gap fails closed before provider invocation. Optional unrelated routes still obey the
soft packing target. If the complete bounded query set cannot fit the hard limit with retained history, the existing
PydanticAI-boundary history compactor removes oldest completed call/result pairs and repacks; the query result is never
exposed partially. This adds no result store, cursor, memory, or new state transition.

Run10 then reached the correct review region and returned a formally complete page, but only two of four expected
reviewers. The trace showed the actual information loss before the read owner: every AX accessible name had already
been sliced by `SurfaceAdapter` to the first 240 characters. The omitted Catso and Michelle conclusions occurred after
that boundary, while each downstream record was still labelled `complete_item`. The model's progress note therefore
preserved an honestly reasoned but incomplete conclusion; no history compressor or summarizer can reconstruct text
that never entered World.

The observation contract is now positive and owner-specific:

- BrowserGym informational AX text is preserved in canonical World; the 240-character defensive limit applies only
  to executable/option labels and publishes `semantic.accessible_name.truncated=true` when used;
- read/search operate on the preserved text and first try complete enclosing records against the final serialized
  ToolReturn byte limit;
- an individual record is bounded only when it cannot fit on an otherwise empty result page, and then becomes
  `partial_item` with `content_truncated=true`;
- pagination advances only across records in the same read owner. There is no fragment protocol, evidence inventory,
  second summarizer, or new cursor state machine.

Run11 live-verified this observation contract: Catso's and Michelle's full bodies appeared as complete ToolReturn
records and all same-World routes remained valid. Its final provider call timed out before producing a decision. Run12
then completed STOP and native evaluation but exposed a separate ActionPolicy interpretation defect: the model
explicitly recognized that the two indirect descriptions entail undersized ear cups, then chose only the two records
containing literal `ear cup` wording as the “safest” answer. The World, task, completed call/result history, and full
records were present. The positive policy contract is therefore semantic and generic: `search_page_content` is a thin
exact-substring locator, while the model judges the complete records it returns by entailment/paraphrase rather than
exact token overlap. For a known collection, the model reads its region and follows visible UI pagination instead of
issuing synonym searches. Exhaustive retrieval remains open while visible counts, pagination, or partial source
coverage expose inspectable records. This is one prompt-owner correction in the existing ActionPolicy, not a Runtime
rule, BM25/dense index, benchmark extractor, verifier model, or new state.

Run13 exposed a different context-authority defect after the records themselves were complete. The Page 2
`search_page_content` ToolReturn already contained Michelle Davis's full record, and BrowserGym had returned a stable
fresh post-action observation. The same physical request nevertheless rendered the previous Page 2 click as
`LatestEffect ... transition=new_document`, because a changed public document signature had been mislabeled as a
current navigation state and retained across later local reads. The model followed the documented hierarchy, trusted
that false current-state block, and repeatedly called `wait`.

The repair restores one currentness authority:

- fresh `WorldObservation` is the only current GUI state supplied to the model;
- a completed GUI action remains only in its `StepResult`, bounded recent receipt, and SDK call/result history;
- `AgentContext`, `ContextBuilder`, action packing, and the renderer have no Store/effect projection input;
- `ObservationDeliveryStore` lives only in `RunState` and retains bounded local-result digests for Monitor novelty;
- the fresh `PageMap` is always rendered directly from the current `WorldDeliveryIndex`.

No replacement effect channel, transition state machine, cursor protocol, summary model, or retrieval system was
added.

Run15 verified that the stale-effect path was gone: the model issued no `wait`, BrowserGym captured the fresh Reviews
World, and that World contained the complete review records. The next policy turn then failed locally before any
provider call. `TurnPacker` correctly began with a zero-candidate prefix, but `PageMap` registered `R11` in its
`DeliveryManifest` and dropped the entire `R11` descriptor because optional heading text exceeded the descriptor
budget. `ModelTurnDelivery` rejected the contradictory projection. The same renderer also registered fact refs from
nodes that were subsequently hidden by duplicate-text suppression. This was not another currentness, cursor,
PydanticAI, or model-comprehension failure; it was one projection owner violating atomic delivery.

The positive projection contract is now:

- a public ref enters `DeliveryManifest` if and only if the same delivery contains that ref in admitted text or exact
  media;
- every emitted PageMap region has a minimal `[R] kind/source-coverage/membership/recovery` descriptor; headings,
  labels, counts, and state are optional additions within the per-descriptor budget;
- a hidden or de-duplicated node cannot register its state/fact refs;
- every legal `ActionDeliveryPlan` prefix, including the initial zero-candidate prefix, is validated by the unchanged
  `ModelTurnDelivery` conservation gate before catalog construction or provider invocation.

For a large current page, PageMap itself is now a bounded directory projection. It prioritizes explicitly selected,
current candidate, focused/changed, and functional landmark regions until one aggregate descriptor-token limit. The
header truthfully reports `shown/total` and `coverage=partial`; the complete immutable `WorldDeliveryIndex` remains the
Runtime authority, and the existing `list_regions`, `read_region`, and `search_page_content` tools recover omitted
directory entries. No per-node 240-character cap, hidden PageMap inventory, new cursor, or second World is introduced.

Run15 also showed that exact search for `small` matched DOM scaffolding such as an HTML `small` tag. Search now admits
human-readable labels/text, normal public semantic fact/state values, and title/alt/placeholder/ARIA attributes while
excluding appearance, layout, internal truncation, DOM tag/class/ID, and other structural fields. The excluded fields
are neither match triggers nor returned search state. This remains a deterministic substring locator; it is not BM25,
dense retrieval, or a semantic-search subsystem.

Run16 reached the intended terminal path. The model returned the four correct names in a valid official
`FinalAgentResponse`, Runtime sent one STOP, captured the post-STOP World, and the BrowserGym snapshot classified as
native success. Validation then rejected the proposed `COMPLETE` evaluation because W1b still declared
`requested_outputs=("webarena_final_response",)`, although no current-World artifact with that ID existed.

This was a stale half-migration, not missing agent information. The earlier public-final-response design had treated
the answer as a requested output. The later serial cutover correctly moved representation ownership to the
environment's pinned WebArena codec and retained the official goal verbatim, but left the old requested-output and W0
manifest declarations behind. In the current contract these are different things: `requested_outputs` names
World-backed artifacts that `TaskEvaluation.outputs` must resolve, while the WebArena response is the already
validated payload of the one native STOP action. Duplicating that payload into World or evaluator output would create
a second authority solely to satisfy a stale declaration.

The owner repair removes the obsolete W1b requested-output/manifest declarations. The generic requested-output
validator remains strict for real World-backed deliverables. A fake-BrowserGym vertical gate now exercises the exact
positive path: official codec normalization -> one STOP -> post-STOP capture -> native success -> validated
`TaskEvaluation(COMPLETE)` -> `RunStatus.DONE`, with no output artifact, response Store, or projection side channel.
Run16 remains a failed pre-repair witness. Run18 is the post-repair accepted live witness.

Task27 run1 then exposed the still-open BrowserGym causal-transition gate. The model correctly selected the Forums
link; BrowserGym recorded one `sent` dispatch, a URL change from `/` to `/forums`, navigation start and commit, and a
new document epoch. The first post-action capture nevertheless returned `acquisition_unstable` after its bounded DOM
quiet wait, so `post_capture_started` and `post_capture_completed` were absent. Runtime then blocked without a fresh
World. This was not a policy, task, World projection, ToolReturn, or action-binding failure.

The shared root cause was a half-connected existing recovery contract. `CoreAgentLoop` allowed its one bounded
read-only post-dispatch recapture only for `sent_unknown`, although a known `sent` action can also lose its normal
post-action acquisition. The BrowserGym adapter also made `acquisition_unstable` sticky across every later acquisition,
so the existing `capture_current()` port could never recover it.

The positive contract is now:

```text
one dispatch
-> normal causal post-action acquisition
-> if missing/failed, at most one independent read-only recapture
-> fresh World -> StepResult
```

The recovery never replays the action. BrowserGym admits that recapture only for `acquisition_unstable`; an uncommitted
`navigation_pending` state remains fail-closed because a generic current-page snapshot cannot prove which document it
belongs to. A failed second acquisition remains typed and terminal for the step. The existing execution outcome,
independent-capture port, fresh-World projection, receipt lineage, and policy loop are reused; no retry state machine,
effect channel, cursor, evidence store, or new observation authority was added. Provider-free owner and vertical tests
prove one step, one recapture, recovered after-observation lineage, and no action replay. Task27 run2 is the accepted
post-repair live witness for this contract.

Task266 run1 exposed a separate liveness defect after the model correctly selected the `Portland, Maine` Wiki link.
No provider request was pending. The last completed model turn took about 4.1 seconds, but no subsequent
`step_completed` event appeared and heartbeat stopped. The process and Playwright child remained alive and consumed
CPU until the explicitly requested stop. Because the blocked event loop could not process SIGTERM promptly, the
durable run eventually finalized as `failed / environment_unresponsive`; it is preserved only as a pre-repair
diagnostic.

The page itself made the immediate mechanism measurable. The local Portland article is about 317 KB with 5,064 HTML
elements and 1,482 links. A BrowserGym/Chromium diagnostic produced 12,369 AX nodes and 3,397 marked BIDs. BrowserGym
had already captured those BIDs in one DOM/AX transaction, but `_with_private_control_properties()` then performed
five synchronous Playwright locator calls for every BID (`count`, visibility, enabled, editable, and evaluate): about
17,000 cross-process RPCs for this one page.

Two existing boundaries amplified that O(N × RPC) producer defect. `BrowserGymSurfaceAdapter` invoked the synchronous
thread-bound facade directly from the asyncio event loop, so heartbeat and the 900-second harness watchdog could not
run. After the facade's 180-second command timeout, the normal recovery capture was queued behind the same owner
thread that was still processing the timed-out command, causing another full wait instead of a usable fallback.

The positive liveness contract is now:

```text
BrowserGym DOM/AX snapshot
-> one bulk physical-property evaluation per frame
-> bounded current World projection

async Runtime
-> synchronous BrowserGym call runs off-loop
-> heartbeat/watchdog remain schedulable
-> responsive typed fallback, or fail-closed owner timeout
```

The property owner still returns the same private availability, state, option, geometry, gesture, and navigation
fields; DOMSnapshot geometry remains authoritative for screenshot-aligned boxes. The implementation only replaces
per-node Playwright round trips with one browser-side batch per frame. A hard owner timeout marks that physical session
unavailable, so observation fallback fails immediately rather than joining a queue whose owner cannot service it; the
action is never replayed. This reuses BrowserGym snapshots, Playwright evaluation, the existing thread-bound facade,
typed recovery, and harness watchdog. It adds no Agent fallback policy, page-size heuristic, retry state machine,
cursor, evidence path, or task/site branch.

The exact Portland diagnostic now enriches all 3,397 BIDs in about 1.0 second after BrowserGym's approximately
1.55-second DOM/AX extraction. Provider-free tests prove one batch for a 2,000-control inventory, real-Chromium bulk
semantics, event-loop heartbeat progress during a blocked physical probe, and immediate rejection of recovery after an
owner timeout.

Task266 run2 live-verified that liveness repair: heartbeat remained schedulable, the model selected the same article,
and BrowserGym returned a typed `stable_navigation` snapshot in about 7.0 seconds. The run then blocked at the next
boundary with `post_action_acquisition_failed`. Exact local replay proved that structural semantics had already
accepted 5,999 controls, but screenshot projection attempted to attach every one of the page's 2,413 boxed controls as
a region on the current 1280×720 screenshot. The media contract correctly rejects more than 512 regions, and only 70
of those boxes actually intersected the captured viewport; the furthest page box started around y=27,512.

Screenshot projection now grounds only controls geometrically present in the current image, clips partial edge boxes,
and gives executable controls stable priority within the existing media bound. It does not remove any structural
target or binding. The same Portland snapshot now produces one valid source with 6,001 targets, 1,923 bindings, 4,096
bounded facts, 6,725 retained structure nodes out of 11,251, and 70 in-viewport screenshot regions. Projection
exceptions after dispatch also retain their existing typed reason and bounded owner diagnostic instead of collapsing
to an unexplained capture failure. No page/site rule, image pagination, evidence path, or new fallback was added. A
post-repair Task266 live witness is still required before this combined large-page gate closes.

Task266 run3 confirmed that viewport grounding no longer rejected the article. The agent typed the query, submitted
it, read the search results, and selected the intended article. The fresh article capture then reached canonical public
projection and failed with `ValueError: public reference capacity exceeded`. The formal harness projected that as
`failed / harness_projection / case_projection_failed` after about 184.1 seconds; its zeroed case metrics are a
reporting consequence of case projection failure and do not mean that no browser actions ran. Heartbeats remained
schedulable, so this was neither the earlier event-loop hang nor a missing observation fallback.

The violated identity invariant was local and deterministic. `CanonicalPublicWorldProjection` allocated one `E/N`
record for every semantic World target and then allocated another `N` record for its linked source structure node.
On the article, 6,001 semantic targets plus 6,725 retained structure occurrences crossed the per-kind public-ref bound
even though most pairs represented the same public entity. A unique structure occurrence now reuses its semantic
target's existing ref. An unlinked structural node keeps its own `N` ref, and multiple genuine structure occurrences
of one canonical target remain distinct so `ActorWorldSnapshot` node refs stay globally unique.

Architecture-first replay then exposed the next arbitrary gate before another live run: the accepted World already
contained 4,096 bounded facts plus controlled artifacts, while `WorldEvidenceIndex` separately rejected any total
above 4,096. That private resolver now indexes every fact/artifact already accepted by the current World and retains
only canonical validation; it does not publish an evidence inventory or add model context. Resolution uses the
existing sorted records rather than a second state owner.

The same replay measured three quadratic derivations that made a correct large World look stalled: component
validation scanned all links for every component, Fusion scanned all source targets for every canonical target, and
automatic Top-5 candidate ranking ran pairwise fuzzy matching between a full task instruction and every action token.
They now use local lookup tables, while fuzzy matching is reserved for an explicit bounded action query. These are
disposable computations over one fresh World, not cross-turn caches, fallbacks, cursors, or a new lifecycle.

The exact post-repair Portland chain succeeds with 6,001 targets, 1,923 actions, 335 regions, 8,668 public fact
records, 9,131 private current evidence refs, and an 85,257-byte bounded model delivery. End-to-end local time is about
27.2 seconds: 10.1 seconds BrowserGym capture, 4.3 surface projection, 5.2 fusion, 4.2 delivery index, 1.0 canonical
projection, 1.9 context construction, and 0.1 final delivery. The equivalent pre-optimization replay took about 87.9
seconds and failed at two capacity gates. No ref-width increase, page heuristic, evidence Store, retry, or alternate
World was added. A fresh explicitly authorized Task266 live run is still required for acceptance.

Task266 run5 then exposed an action-delivery ordering defect, not another large-World, cursor, or history failure. The
fresh search-result World already contained the correct current `activate "Portland, Maine"` route, and the automatic
ranker placed it first. However, the delivery plan made an incidental synthetic focused-context `press_key` group the
foreground obligation. With the existing soft request target able to admit one route, the model-visible catalog
therefore contained only that unrelated key action while the correct route stayed private in the complete current
`ActionSpace`.

The trace makes the consequence exact: after typing and submitting the search, the model called
`read_region(R3) -> read_region(R6) -> read_region(R3) -> read_region(R6)`. The first `R3` result honestly returned
`has_more=true` and `next_cursor="20"`; all completed results and model-authored progress notes remained in PydanticAI
history, and no history compaction ran. The model nevertheless had no directly callable result link. On the first exact
read replay, Monitor emitted the same recovery sentence used for `find_controls` loops—including advice not to
continue discovering controls—then blocked the next replay. Runtime terminated normally as `blocked`; BrowserGym and
the provider did not hang.

The owner-level contract is now:

```text
complete fresh ActionSpace
-> private current resolver for every supported operation

task-ranked prefix + incidental focus/container routes
-> bounded model-visible observation only

find_controls(query)
-> bounded current E-ref matches when the visible prefix is insufficient
```

Focus remains visible state and an executable route; it is no longer entitled to displace the task-ranked prefix.
Neither focus nor the ranker can remove a legal current action from the resolver. A syntactically valid but unavailable
or stale E-ref fails as a typed grounding gap before Binder/Executor.
Monitor also renders recovery from the typed producer: action-discovery loops tell the model to use a returned control
or materially change route, while an exact read/search replay points to the same tool's `next_cursor`, a different
relevant region, `find_controls`, or browser navigation. No new action authority, retrieval index, cursor type,
history store, recovery state, or model role was introduced. Run5 remains failed pre-repair evidence; a fresh live
witness is required.

## Normative production chain

```text
TaskGoal + optional static GoalPlan + fresh WorldObservation
-> compact current World + current ToolCatalog + bounded recent receipts
   + bounded completed PydanticAI ToolCall/ToolReturn pairs
-> PydanticAI ToolCall(tool_call_id, schema-valid arguments)
-> Catalog resolver
   -> local read owner, or
   -> SelectAction -> Binder -> Executor -> BrowserGym
-> committed StepResult
-> same-call ToolReturn for local tools / action receipt
-> fresh World after GUI dispatch
-> next model turn
```

There is one `CoreAgentLoop`. It orchestrates typed ports and state advancement; it does not parse provider envelopes,
invent tool schemas, bind private BrowserGym targets, project World semantics, or reconstruct tool results.

## Tool-result contract

### Local read/search/list

`read_region`, `search_page_content`, and `list_regions` return one byte-bounded JSON mapping from their owner. That
mapping is stored in `LocalToolResult.result`, committed in `StepResult`, and projected unchanged as the PydanticAI
`ToolReturn` under the original `tool_call_id`.

Conceptually:

```python
{
    "kind": "Opened | Matches | Page | Empty | InvalidRegion | InvalidCursor | CapacityExceeded",
    "items": [...],
    "has_more": bool,
    "next_cursor": str | None,
    "content_truncated": bool,  # only on an item whose fields were bounded
    # operation-specific coverage metadata
}
```

The concrete result types remain `ReadRegionResult` and `SearchPageContentResult` because they express the local
operation at the Runtime boundary. They do not create a second evidence algebra.

For repeated DOM/AX structures, search returns the smallest enclosing repeated item, with compact role, text, label,
and state fields. A matching child therefore carries its sibling fields (for example, one card's title and author)
without copying internal evidence metadata or serializing the whole surrounding region. The item is
`complete_item` only when its content is complete; any source or owner truncation changes it to `partial_item` and
sets `content_truncated=true`. This rule is generic to the public tree shape and contains no site, task, phrase, or
fixed-region branch.

Pagination, when needed, is deliberately small:

```text
read_region(region_ref=R9)
-> bounded page + next_cursor="20"
read_region(region_ref=R9, cursor="20")
-> next bounded page
```

The cursor is only a bounded offset understood by that same read owner. It is not a Store capability, provider state,
Workspace state, evidence cursor, GUI-effect cursor, or action-result cursor. The current catalog and resolver still
own current-World and current-ref validation. An invalid offset returns `InvalidCursor` deterministically.

The read owner packs complete records first against the final serialized ToolReturn limit. It does not pre-truncate
every field before calculating that total. Only a record that cannot fit on an empty page uses the individual
string/collection safety bound, becomes `partial_item`, and receives `content_truncated=true`. The former
`content_fragment`, record digest, fragment offset, lossless reassembly, and hidden admitted/suffix protocol are
removed. GUI benchmark work does not need arbitrary 100 KiB DOM strings reconstructed exactly by the model.

### Action discovery

`find_controls(query)` applies one deterministic lexical/fuzzy filter to the complete current `ActionSpace`, then
returns only the bounded matching routes. Focus and viewport affect the order of matches; they do not turn unrelated
controls into matches, and the remaining ActionSpace is not appended behind the query result. It has no generic
continuation tool and no private public-result inventory. If matching routes exceed the page bound, the model issues a
narrower natural-language query. Action discovery never executes a control and never turns readable `N/F/R` refs into
executable `E` refs.

The returned page and the next same-World catalog share one current-World contract:

```text
find_controls ToolReturn contains (verb, E-ref[, destination])
-> registry-owned action tool accepts the stable E-ref argument shape
-> current complete ActionSpace resolver validates the exact operation/route/domain
-> SelectAction carries the existing private action identity to Binder
```

The soft packing target may reduce the visible candidate prefix, but it cannot change the action tool shape or current
resolver membership. `ActionDeliveryPlan` and `DeliveryManifest` therefore describe what the model was shown; they are
not a second action-authority or allowlist.

### GUI actions

```text
current E-ref + semantic operation
-> stable registry tool schema
-> complete current ActionSpace resolver
-> Binder resolves private current BrowserGym binding
-> Executor dispatches once
-> stable post-action capture
-> fresh WorldObservation
-> StepResult with bounded receipt/effect
```

The post-action World, not an evidence continuation, is the authority for the next decision. `ActionEffect` only
describes the local UI effect. `TaskEvaluator` or the benchmark-native verifier remains the only task-termination
authority.

Browser-global navigation uses that same route. When the caller explicitly selects a BrowserGym web-navigation
profile (the WebArena runner does so), the adapter projects one current `browser_context` subject and the official
BrowserGym primitives
`goto`, `go_back`, `go_forward`, `new_tab`, `tab_focus`, and `tab_close`. `tab_focus` is offered only with a current
alternative tab; its public schema accepts a non-negative index and the current resolver enforces the exact available
tab domain. The other actions are offered by the profile and validated by their ordinary schemas. MiniWoB receives no browser-global additions. These are ordinary ActionSpace options that
pass through Catalog, Binder, currentness probing, Executor, stable capture, and fresh World—not local-tool shortcuts.
The adapter never infers this capability from task text or a benchmark/task ID; unsupported or duplicate profile
entries fail before World projection.

This boundary matches the mature BrowserGym/AgentLab shape: the current observation carries element identifiers while
the action vocabulary remains a small fixed set such as `click(bid)` and `fill(bid, text)`. AgentOccam likewise improves
performance by aligning and pruning observations/actions and selectively replaying useful history, not by requiring a
task ranker to authorize each control. In this project E-refs are the public observation identifiers, the capability
registry owns the fixed verbs, and the current resolver is the fail-closed execution boundary.

### Call/result pairing

PydanticAI owns tool schema transport, argument validation, `ToolCallPart`, `ToolReturnPart`, call IDs, deferred-result
resumption, and typed message history. `PydanticAIGroundedDecisionPort` retains only those SDK message objects between
policy invocations. It does not retain old user/World prompts, invent a parallel history type, or keep a second pending
exchange in `ObservationDeliveryStore`.

The physical next request must contain:

```text
zero or more completed:
  assistant ToolCallPart(call_id=A)
  -> ToolReturnPart(call_id=A, content=owner_result)
then current pending:
  assistant ToolCallPart(call_id=X)
  -> ToolReturnPart(call_id=X, content=current_committed_result)
-> fresh current context
```

Each call ID occurs in exactly one accepted call/result pair. Discarded extra provider calls never acquire a result or
enter physical history. PydanticAI's `ProcessHistory` capability proactively removes oldest complete exchanges when
estimated history exceeds the existing soft target; TurnPacker repeats the same pair-atomic reduction before a packed
request can remain above that target, with hard-capacity failure as a final guard. The newest model response and current
pending pair are pinned, so the latest cumulative progress note is not discarded independently of its call. A terminal
decision consumes the last result and clears the transport history so it cannot leak into another episode.

## Authority and owners

| Fact or transition | Owner | Non-owners |
|---|---|---|
| user objective | `TaskGoal` | GoalPlan, Monitor, benchmark trace |
| current GUI truth | fresh `WorldObservation` | Workspace, previous tool results |
| public records, `E/N/F/R` refs, and public order | one immutable `CanonicalPublicWorldProjection` | provider, Store, Workspace |
| model-visible tool schemas | current `ToolCatalog` | CoreLoop, provider transport |
| private execution binding | Binder | model, read tools, Trace |
| browser side effect | Executor/BrowserGym | Catalog, Monitor, Workspace |
| local result shape and byte bound | local read/search/list owner | Store, TurnPacker, Workspace |
| delivery text/Manifest atomicity | compact World renderer | TurnPacker, provider bridge, Trace |
| bounded typed call/result history, correlation, and model-authored progress note | PydanticAI boundary | Store, Workspace, Monitor |
| committed step | `StepResult` | ToolReturn projection, Trace |
| local-result novelty/repetition digest | `ObservationDeliveryStore.reduce` in `RunState` | AgentContext, provider bridge, resolver |
| task completion | `TaskEvaluator` / native verifier | action receipt, GoalPlan |

Projections are never authorities. Trace and benchmark artifacts observe owner-produced facts; they cannot rebuild a
missing result or alter control flow.

`RunState` owns the current episode's operational state and advances only from committed `StepResult` values. It does
not become a second World, tool-result, provider-history, or completion authority.

## Context, Store, Workspace, and Monitor

The model context contains only:

- `TaskGoal` and optional static `GoalPlan`;
- the fresh compact canonical World;
- the current bounded ToolCatalog;
- bounded recent semantic receipts and control feedback;
- at most one bounded, visible, non-authoritative progress note on each retained accepted model response;
- bounded completed owner-produced `ToolCallPart/ToolReturnPart` pairs and the current same-call ToolReturn.

Old World/user prompts are excluded from transport history because the fresh World is the current-environment
authority. The ActionPolicy writes at most 500 characters of cumulative durable conclusions before its one tool call,
including exact supported output values and inspected/total scope when known instead of a vague count.
The PydanticAI boundary retains that visible `TextPart` with the accepted normalized `ToolCallPart`, hard-bounds a
misbehaving response at 800 characters with an explicit truncation marker, and excludes hidden `ThinkingPart` content
and discarded extra calls from future model input. Raw provider output remains in Trace. This is same-actor trajectory
context, not a Runtime fact authority, Workspace memory, or a separate summarizer model.

`TurnPacker` budgets the current World, tools, and typed result history but does not summarize, edit, or rebuild
ToolReturn content. The SDK history processor acts before admission rather than waiting for a hard overflow; only an
oldest complete response/call/result exchange can be dropped. This is bounded SDK history retention, not semantic
memory or evidence projection. The newest cumulative progress note is pinned and carries durable conclusions before an
older exchange leaves the window. No separate summarizer model is used.

`ObservationDeliveryStore` now retains only:

- a bounded sequence of local-result digests used for Monitor novelty/repetition.

It is owned by `RunState` and is absent from `AgentContext`. It does not retain public result bodies, result prefixes,
result cursors, action-query inventories, provider pending calls, or continuation capabilities, and it never retains
or projects GUI effects.

`AgentWorkspace` keeps bounded semantic receipts and activity summaries. It has no working-fact inventory and does not
receive exact local-result bodies. `EpisodeMonitor` consumes typed `InformationDelta` and bounded digests; it cannot
decide how a ToolReturn is serialized or make information persist in model context. Control discovery is capability
lookup, not task evidence, so `ObservationDeliveryStore` emits no novelty delta for it. Monitor allows one same-World
discovery step, recovers on the second consecutive discovery, and blocks another discovery after recovery unless a
fresh World, real information result, or operational GUI result resets the loop.

## World, perception, and action boundaries

All DOM, AX, screenshot, visual-provider, WoT, and HTTP observations enter through `SurfaceAdapter` and fusion into the
same `WorldObservation`. The model consumes only the unified public World. Private selectors, backend node IDs,
coordinates, and executor routes stay inside Runtime.

Page semantics, task decomposition, and open-world grounding belong to the agent/model or a replaceable model-backed
specialist. Runtime deterministically owns schema validation, permissions, currentness, binding, dispatch, stable
capture, and typed failures. No benchmark task name, fixed selector, R9 branch, or page phrase is allowed in production
logic.

## GoalPlan boundary

`GoalCompiler` may run once at task start/revision and return a static, bounded `GoalPlan` of at most eight advisory
items. `TaskGoal` remains authoritative. Runtime stores no mutable per-item status, frontier, achievement record, or
second planner loop. The single ActionPolicy reassesses the plan against the fresh World on every step.

## SOTA alignment checked 2026-08-24

Current primary sources converge on a thin loop rather than a result-conservation subsystem:

- [BrowserGym/AgentLab](https://arxiv.org/abs/2412.05467) defines the research interaction as current observation ->
  agent action -> environment step -> next observation, with BrowserGym delegating browser execution to Playwright and
  exposing standardized observation/action spaces. BrowserGym preserves raw DOM/AX observations with minimal
  alteration; AgentLab applies configurable token fitting at prompt-component/page scope rather than silently clipping
  every readable node at a control-label limit. This project reuses BrowserGym's installed `nav`/`tab` primitives
  instead of inventing navigation tools.
- [AgentOccam (ICLR 2025)](https://proceedings.iclr.cc/paper_files/paper/2025/file/f2c6e459b95694a24ac69c469a4ee746-Paper-Conference.pdf)
  reports that aligning the observation and action spaces—removing redundant structure while retaining informative,
  usable page elements—substantially improves a plain single web agent without extra roles or online search. The run5
  repair follows that boundary: it changes which already-legal current route is visible first; it does not add a
  planner, retriever, or Runtime semantic rule.
- [FocusAgent](https://arxiv.org/html/2510.03204) selects task-relevant AXTree line ranges from the preserved tree and
  inserts explicit placeholders for omitted ranges. Its recall-biased soft retrieval is evidence for visible,
  structure-aware reduction rather than unmarked per-node prefix loss.
- [OpenAI computer use](https://developers.openai.com/api/docs/guides/tools-computer-use) specifies a loop of
  `computer_call` -> ordered harness execution -> updated screenshot as `computer_call_output` under the same
  `call_id` -> repeat.
- [Gemini computer use](https://ai.google.dev/gemini-api/docs/computer-use) likewise uses screenshot -> function call ->
  client/Playwright execution -> fresh screenshot in the corresponding function result.
- [PydanticAI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) owns pending call IDs,
  validated deferred results, and message-history resumption.
- [PydanticAI message history](https://pydantic.dev/docs/ai/core-concepts/message-history/) keeps provider-valid message
  history and supports history processors at the SDK boundary rather than requiring a second result ledger.
- [OSWorld](https://arxiv.org/abs/2404.07972) evaluates agents over a task, current screenshot/AX observation, action,
  and next observation trajectory. Its agent history is trajectory context, not a second authoritative desktop state.

Inference for this project: SOTA does require a harness, current observation projection, action schema, private binding,
safe execution, result pairing, and fresh observation. It does not require one tool result to become a durable public
evidence ledger, a generic cursor state machine, a second provider-history owner, or a benchmark-specific extractor.

## Explicit non-goals

- no World, SurfaceAdapter, BrowserGym, Binder, Executor, PydanticAI SDK, GoalPlan, or evaluator redesign for this
  cutover; the provider adapter only adopts the SDK's existing typed message history, while obsolete Workspace/Monitor
  working-fact coupling is removed;
- no Manager/Worker hierarchy, RAG/memory platform, event sourcing, generic evidence ledger, second Runtime loop, or
  provider-specific state machine;
- no site/task/fixture-specific extraction or action branches;
- no live benchmark without explicit user authorization.

## Verification contract

This cutover is implementation-complete only when all of the following agree:

1. every registered local tool resolves to its declared decision subtype;
2. every local read/search/list result is serialized within its owner bound before commit, with every fitting record
   complete and every non-fitting record explicitly partial;
3. a Recording FunctionModel receives every retained committed result under its original call ID, without old World
   prompts, and terminal completion clears the history;
4. a same-tool cursor advances a finite page without creating Store result inventory;
5. GUI dispatch leads to one normal causal acquisition and, when that acquisition fails, at most one read-only
   recapture before a fresh World is admitted; the action is never replayed;
6. production contains no generic result continuation/evidence inventory/reassembly path;
7. focused and full provider-free suites, Ruff, compileall, negative searches, and fresh diff review pass.
8. every Manifest ref is present in the same admitted text/media for zero, partial, and full action-prefix selections;
9. readable search cannot match or return DOM tag/class/ID scaffolding.
10. a unique semantic/structure occurrence has one public identity, every accepted World fact/artifact remains
    resolvable, and large-World derivation does not rescan complete entity/action inventories per item.
11. queried control discovery returns only query-qualified current routes, and same-World discovery loops cannot create
    information novelty that clears Monitor.
12. WebArena-family browser navigation is published only through the existing ActionSpace/BrowserGym route, while
    MiniWoB remains unchanged.
13. proactive SDK history processing preserves exact call/result pairs and the newest cumulative progress note, and a
    partial PageMap remains aggregate-bounded and recoverable through the existing read tools.

These gates prove this bounded implementation. They do not close the BrowserGym transition without its post-repair
live witness, Planner lexical admission, or the broader benchmark campaign.

# Architecture

## Current status

The current production target is a thin, single-loop GUI agent. The former generic evidence-delivery system is no
longer part of the architecture: local tool results are not copied into a Store-owned public inventory, repacked as an
admitted prefix, or exposed through generic continuation tools.

Implementation and provider-free verification of the thin result/history cutover, action-discovery closure repair,
and readable-AX completeness repair are complete. The readable-result focused suite passes `62` tests; the full suite
passes `1656` tests with `24` skipped. Ruff, compileall, and diff checks pass. The repository-wide mypy command still
reports its pre-existing baseline errors in unchanged modules and is not counted as a passing gate.
Overall project closure is still **open**:

- BrowserGym `dispatch -> causal stable fresh World -> StepResult` still requires its separately scoped closure.
- Planner lexical admission still has a known gap.
- The readable-AX repair still needs a post-fix agent benchmark witness; a real-page Chromium AX diagnostic is not a
  benchmark result.

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

`find_controls(query)` returns one owner-bounded ranked page from the complete current `ActionSpace`. It has no generic
continuation tool and no private full-result inventory. If the result coverage is partial, the model issues a narrower
natural-language query. Action discovery never executes a control and never turns readable `N/F/R` refs into
executable `E` refs.

The returned page and the next same-World catalog share one route contract:

```text
find_controls ToolReturn contains (verb, E-ref[, destination])
-> ActionDeliveryPlan closes that exact route over current ActionSpace
-> TurnPacker admits the complete bounded query capability set
-> next ToolCatalog accepts every returned route
```

The soft packing target may reduce unrelated base/effect/interaction inventory, but it cannot turn an already returned
control into a visible but uncallable ref. Hard capacity remains the only reason this whole bounded set can be rejected.

### GUI actions

```text
current E-ref + semantic operation
-> Catalog resolver
-> Binder resolves private current BrowserGym binding
-> Executor dispatches once
-> stable post-action capture
-> fresh WorldObservation
-> StepResult with bounded receipt/effect
```

The post-action World, not an evidence continuation, is the authority for the next decision. `ActionEffect` only
describes the local UI effect. `TaskEvaluator` or the benchmark-native verifier remains the only task-termination
authority.

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
enter physical history. If the request budget is reached, the oldest complete pair is removed atomically; the current
pending pair is never split. A terminal decision consumes the last result and clears the transport history so it
cannot leak into another episode.

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
| bounded typed call/result history, correlation, and model-authored progress note | PydanticAI boundary | Store, Workspace, Monitor |
| committed step | `StepResult` | ToolReturn projection, Trace |
| next Store reduction | `ObservationDeliveryStore.reduce` | provider bridge, resolver |
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
authority. The ActionPolicy writes at most 500 characters of cumulative durable conclusions before its one tool call.
The PydanticAI boundary retains that visible `TextPart` with the accepted normalized `ToolCallPart`, hard-bounds a
misbehaving response at 800 characters with an explicit truncation marker, and excludes hidden `ThinkingPart` content
and discarded extra calls from future model input. Raw provider output remains in Trace. This is same-actor trajectory
context, not a Runtime fact authority, Workspace memory, or a separate summarizer model.

`TurnPacker` budgets the current World, tools, and typed result history but does not summarize, edit, or rebuild
ToolReturn content. When capacity requires reduction, only an oldest complete response/call/result exchange can be
dropped; this is bounded SDK history retention, not semantic memory or evidence projection. A newer cumulative progress
note can carry forward model conclusions before an older exchange leaves the window.

`ObservationDeliveryStore` now retains only:

- the latest reconciled GUI effect needed by the current view/action recall;
- a bounded sequence of local-result digests used for Monitor novelty/repetition.

It does not retain public result bodies, result prefixes, result cursors, action-query inventories, provider pending
calls, or continuation capabilities.

`AgentWorkspace` keeps bounded semantic receipts and activity summaries. It has no working-fact inventory and does not
receive exact local-result bodies. `EpisodeMonitor` consumes typed `InformationDelta` and bounded digests; it cannot
decide how a ToolReturn is serialized or make information persist in model context.

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
  every readable node at a control-label limit.
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
5. GUI dispatch still leads to the existing causal stable fresh-World path;
6. production contains no generic result continuation/evidence inventory/reassembly path;
7. focused and full provider-free suites, Ruff, compileall, negative searches, and fresh diff review pass.

These gates prove this bounded architectural cutover. They do not close the separately reopened BrowserGym transition,
Planner lexical admission, or live benchmark gates.

# Architecture

## Current status

The current production target is a thin, single-loop GUI agent. The former generic evidence-delivery system is no
longer part of the architecture: local tool results are not copied into a Store-owned public inventory, repacked as an
admitted prefix, or exposed through generic continuation tools.

Implementation and provider-free verification of this cutover are complete. The focused suite passes `204` tests; the
full suite passes `1653` tests with `24` skipped. Ruff, compileall, diff/negative searches, and fresh diff review pass.
Overall project closure is still **open** for two independent reasons already recorded by project policy:

- BrowserGym `dispatch -> causal stable fresh World -> StepResult` still requires its separately scoped closure.
- Planner lexical admission still has a known gap.

No live/provider benchmark was run or authorized for this cutover. Historical acceptance files under `evidence/` remain
diagnostic records of the revisions they exercised; they do not define the current architecture.

## Root cause of the R9 escalation

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

## Normative production chain

```text
TaskGoal + optional static GoalPlan + fresh WorldObservation
-> compact current World + current ToolCatalog + bounded recent receipts
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

`read_region`, `search_page_content`, and `list_regions` return one already bounded JSON mapping from their owner. That
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

An individually oversized string/collection is bounded at the tool owner and marked `content_truncated=true`. The
former `content_fragment`, record digest, fragment offset, lossless reassembly, and hidden admitted/suffix protocol are
removed. GUI benchmark work does not need arbitrary 100 KiB DOM strings reconstructed exactly by the model.

### Action discovery

`find_controls(query)` returns one owner-bounded ranked page from the complete current `ActionSpace`. It has no generic
continuation tool and no private full-result inventory. If the result coverage is partial, the model issues a narrower
natural-language query. Action discovery never executes a control and never turns readable `N/F/R` refs into
executable `E` refs.

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

PydanticAI owns tool schema transport, argument validation, `ToolCallPart`, call IDs, pending deferred calls, and
call/result history pairing. The Runtime supplies exactly one committed result for the accepted call. It does not keep
a second pending provider exchange in `ObservationDeliveryStore`.

The physical next request must contain:

```text
accepted assistant ToolCallPart(call_id=X)
-> ToolReturnPart(call_id=X, content=owner_result)
-> fresh current context
```

Discarded extra provider calls never acquire a result or enter the physical history.

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
| call/result correlation | PydanticAI boundary | Store, Monitor |
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
- the immediately paired owner-produced ToolReturn when completing a call.

`TurnPacker` may fit current World/action presentation records to the request budget. It does not edit or rebuild the
current ToolReturn. Completed older message pairs may later be compacted as history, but compaction is separate from
tool execution and cannot create a new result authority.

`ObservationDeliveryStore` now retains only:

- the latest reconciled GUI effect needed by the current view/action recall;
- a bounded sequence of local-result digests used for Monitor novelty/repetition.

It does not retain public result bodies, result prefixes, result cursors, action-query inventories, provider pending
calls, or continuation capabilities.

`AgentWorkspace` keeps bounded semantic receipts and explicitly remembered scalar facts. It is not evidence storage and
does not receive exact local-result bodies. `EpisodeMonitor` consumes typed `InformationDelta` and bounded digests; it
cannot decide how a ToolReturn is serialized.

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
  exposing standardized observation/action spaces.
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

- no World, SurfaceAdapter, BrowserGym, Binder, Executor, PydanticAI, Monitor, Workspace, GoalPlan, or evaluator redesign
  for this cutover;
- no Manager/Worker hierarchy, RAG/memory platform, event sourcing, generic evidence ledger, second Runtime loop, or
  provider-specific state machine;
- no site/task/fixture-specific extraction or action branches;
- no live benchmark without explicit user authorization.

## Verification contract

This cutover is implementation-complete only when all of the following agree:

1. every registered local tool resolves to its declared decision subtype;
2. every local read/search/list result is serialized within its owner bound before commit;
3. a Recording FunctionModel receives the exact committed result under the original call ID;
4. a same-tool cursor advances a finite page without creating Store result inventory;
5. GUI dispatch still leads to the existing causal stable fresh-World path;
6. production contains no generic result continuation/evidence inventory/reassembly path;
7. focused and full provider-free suites, Ruff, compileall, negative searches, and fresh diff review pass.

These gates prove this bounded architectural cutover. They do not close the separately reopened BrowserGym transition,
Planner lexical admission, or live benchmark gates.

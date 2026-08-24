# SOTA GUI Tool Loop Simplification

## Goal

Replace the project-specific public-evidence delivery/cursor pipeline with the smallest coherent GUI-agent loop:

```text
fresh World + bounded recent steps + current ToolCatalog
→ PydanticAI ToolCall(call_id)
→ Catalog resolver / Binder / Executor or local read owner
→ one owner-bounded public ToolReturn under the same call_id
→ next model turn / fresh World after GUI dispatch
```

Only a local read/search result that exceeds its owner byte bound may expose tool-local pagination. GUI effects,
page-directory delivery, action-result delivery, Monitor novelty, Workspace history, and provider call/result pairing
must not share a generic evidence inventory or continuation state machine.

## Positive target contract

- `StepResult` remains the one committed execution fact for Runtime steps.
- PydanticAI owns the pending tool call, message pairing, `call_id`, and deferred `ToolReturn` protocol.
- GUI actions return a bounded receipt/error and are followed by one causal stable fresh `WorldObservation`.
- Local reads/searches construct a fully bounded model-visible mapping at the local tool owner. That mapping is returned
  directly as the same-call `ToolReturn`; no Store, Workspace, Monitor, TurnPacker, or generic projector edits it.
- Read/search pagination, if required, is owned by the read tool (`region_ref/query + offset/page` or one opaque
  tool-local token). Current World/ref validation remains at the existing catalog/binding boundary.
- Model context contains the fresh compact World, current tools, and bounded recent action/result receipts. Optional
  history compression acts on completed message pairs, never on the current tool result's internal structure.
- Trace observes committed inputs/results. Workspace and Monitor consume bounded receipts/digests only and are never
  result or cursor authorities.
- Task termination remains owned by `TaskEvaluator`/native verifier.

## Explicit non-goals

- No World, SurfaceAdapter, ActionSpace, Binder, Executor, BrowserGym, GoalCompiler/GoalPlan, evaluator, or benchmark
  semantic redesign.
- No Manager/Worker, memory/RAG, new state machine, second runtime loop, site/task-specific extraction, or provider
  rewrite.
- No live benchmark without separate user authorization.
- Preserve unrelated user changes and the untracked `output/` directory.

## Causal model

1. Search exposed `R9`, but the next Catalog omitted `read_region(R9)` (follow-up projection defect).
2. `read_region` paged by logical count before its serialized-byte bound (local result-owner defect).
3. A successfully bounded result was copied through Workspace and structurally truncated (duplicate result transport).
4. The prior convergence generalized these defects into Store-owned exact evidence, admitted prefixes, and generic
   continuation capabilities. That coupled unrelated GUI effects, local reads, Monitor novelty, context packing, and
   provider protocol.
5. The target repair restores owner-bounded direct tool results and removes the duplicate authority rather than adding
   another subtype or continuation branch.

## Steps

### 1. Repository-wide causal-surface inventory — completed

- Identify every producer/consumer of `PublicEvidenceResult`, `PublicResultInventory`,
  `DeliveryContinuationCapability`, local-result admitted prefixes, `read_next_page`, and same-call ToolReturn.
- Separate GUI effect/action delivery responsibilities from local read-result transport.
- Record the smallest deletion/migration surface and test gates below.
- Confirmed migration surface: `decisions` and `tool_result_projection` own the local-result algebra;
  `ObservationDeliveryStore` currently duplicates complete result bodies and continuation state;
  `ActionDeliveryPlan` and `ModelTurnDelivery` turn those bodies into admitted prefixes; the grounded catalog then
  exposes generic `read_next_page`/`action_results_next_page` tools over that Store state.
- PydanticAI pending call/history pairing and BrowserGym execution are downstream consumers and remain unchanged.
- Files modified: this plan only.

### 2. Lock executable target contract with owner/vertical tests — completed

- Add/adjust tests for direct same-call bounded local results, GUI receipt + fresh World, completed-message pairing,
  and optional tool-local read pagination.
- Remove expectations that local results first enter Store/TurnPacker or that GUI effects use `read_next_page`.
- Added exhaustive registered-local-tool producer coverage and a Recording FunctionModel vertical pagination route.
- Replaced Store/cursor conservation assertions with direct same-call result, digest-only Store, and fresh-context gates.

### 3. Cut local results to direct PydanticAI ToolReturn — completed

- Make local read/search constructors owner-bounded public results.
- Project the committed local result directly from `StepResult` under the original call ID.
- Remove Store/Workspace/TurnPacker result-body ingestion and admitted-prefix reconstruction.
- `LocalToolResult.result` is the bounded public result and `tool_result_projection` returns it directly.
- PydanticAI receives that exact result under the original call ID; no admitted-prefix reconstruction remains.

### 4. Collapse generic continuation state — completed

- Remove effect/page-directory/action-result continuation from the local tool-result protocol where fresh World/current
  catalog already provides the next state.
- Retain only the minimum tool-local read pagination proven necessary by byte-bounded results.
- Shrink `ObservationDeliveryStore` to responsibilities still required for GUI observation/action delivery, or remove it
  if all remaining fields are immutable current-turn projections.
- Deleted the generic continuation decision/tools/lens and Store-owned result/action inventories.
- `read_region`, `search_page_content`, and `list_regions` accept only their own optional numeric cursor.
- Oversized single records are owner-bounded with `content_truncated=true`; the lossless fragment/digest/reassembly
  protocol was removed.
- `find_controls` returns one bounded query page and instructs the model to refine a partial query; it has no public
  continuation capability or private full-result inventory.

### 5. Migrate context/Monitor/Workspace/Trace consumers — completed

- Keep only bounded receipts/digests in recent steps, Workspace, and Monitor.
- Ensure current tool results are not structurally truncated, duplicated, or injected as ordinary user context.
- Ensure Trace records owner-produced results without becoming a control/state authority.
- `ObservationDeliveryStore` now retains only the latest effect plus bounded local-result digests for Monitor novelty.
- ModelTurnDelivery and recent-step projections no longer inject copied public results or continuation state.

### 6. Documentation and negative deletion gates — completed

- Replaced the conflicting four-thousand-line current specification with concise authoritative architecture and
  benchmark contracts for the thin loop.
- Production negative searches are clean for removed result/evidence/continuation/fragment paths and task/site
  specialization.

### 7. Focused/full verification and fresh review — completed

- Run owner tests, vertical Recording FunctionModel tests, relevant BrowserGym provider-free tests, Ruff, compileall,
  full pytest, and production negative searches.
- Perform a fresh read-only causal review of the committed diff/tree; do not run a provider/live benchmark.
- Record exact results and any remaining uncertainty in this plan and current docs.
- Focused: `204 passed`.
- Full: `1653 passed / 24 skipped`, with one unrelated Python 3.13 multiprocessing deprecation warning.
- Ruff, compileall, `git diff --check`, deletion/specialization searches, and fresh read-only diff review pass.
- No provider, BrowserGym, or live benchmark was run.

## Exit criteria

- One external call produces exactly one same-ID tool result, directly from the committed owner result.
- GUI action execution is followed by a causal stable fresh World; no effect cursor is required.
- Every local read/search result is bounded before commit and reaches the Recording FunctionModel byte/structure-equal.
- Optional read pagination is tool-local, finite, current-World validated, and does not share state with GUI effects,
  action discovery, Monitor, Workspace, or provider history.
- Production has no Store-owned public-result inventory, admitted evidence prefix, generic continuation capability, or
  Workspace/TurnPacker reconstruction of ToolReturn content.
- Focused and full provider-free suites, static checks, generated/held-out local cases, and fresh review agree.
- No new production branch depends on Task21, R9, reviewer text, site identity, or benchmark case labels.

## Progress log

- 2026-08-24: Plan created. No production files changed yet.
- 2026-08-24: Repository-wide causal surface confirmed; the generic continuation path predates R9 and R9 was later
  routed through it. The removal boundary is now fixed at local result construction/projection plus Store/TurnPacker
  duplication, not World, Binder, executor, or provider protocol.
- 2026-08-24: Direct same-call results, same-tool numeric read pagination, digest-only Store, and exhaustive producer /
  Recording FunctionModel gates are implemented. The prior fragment cursor/reassembly protocol and action-discovery
  continuation inventory are also removed. Focused owner/model suite: 204 passed.
- 2026-08-24: Final provider-free verification passes: full suite `1653 passed / 24 skipped`; Ruff, compileall,
  diff/negative searches, and fresh read-only review pass. Architecture/benchmark docs now contain only the current
  thin-loop contract. Live benchmark was neither authorized nor run.

# Benchmark

## Current status

The thin tool-result/history cutover is implemented and provider-free verified. The affected focused suite passes
`164` tests; the full suite passes `1645` tests with `24` skipped. Ruff, compileall, diff/negative searches, and fresh
diff review pass.

Overall project status remains **reopened / non-closed**. This cutover does not close:

- the BrowserGym `dispatch -> causal stable fresh World -> StepResult` gate;
- the Planner lexical-admission gap;
- any live provider/benchmark gate.

No live model or BrowserGym benchmark was run for this cutover. A live run still requires explicit user authorization.
The untracked `output/` directory is unrelated user data and is not an acceptance artifact.

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

Those defects were generalized into a generic evidence inventory and continuation system. Subsequent subtype,
currentness, producer, and Store-composition failures all arose on that shared path.

The current repair removes the duplicated path:

```text
local ToolCall(call_id)
-> current catalog resolver
-> owner-bounded direct result
-> StepResult
-> same-call PydanticAI ToolReturn
-> bounded typed call/result history for later policy turns
-> next Recording FunctionModel turn
```

Read/search/list pagination is optional and local to the same tool. Search returns the smallest complete enclosing
repeated item so ordinary record lookup does not require reading an entire large region. GUI effects and action
discovery do not use the read cursor.

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
- oversized individual content bounded with `content_truncated=true`;
- absence of `content_fragment`/digest/reassembly protocol;
- no loss or duplication among the already bounded public item inventory.

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

### G4 — R-ref follow-up

The `read_region` schema accepts the public `R` syntax for the current canonical World, and the resolver validates the
actual current ref. This avoids building a schema enum from a previously admitted result prefix while preserving
currentness at the correct owner.

Search results continue to return a direct `read_region(region_ref)` follow-up for readable matches.

### G5 — action discovery remains bounded and separate

`find_controls(query)` returns a bounded current result and never dispatches a browser action. It has no public generic
continuation capability and no private full-result inventory. Partial coverage tells the model to refine the query.
Only current `E` refs in the frozen catalog can reach Binder/Executor.

### G6 — GUI route remains unchanged

Existing provider-free integration tests continue to verify:

```text
ToolCall -> SelectAction -> Binder -> Executor -> stable capture -> fresh World -> StepResult
```

This cutover does not claim the separately reopened live BrowserGym transition is closed; it only proves no local-result
change bypassed or replaced that route.

### G7 — deletion and non-specialization gates

Production negative searches must find no:

- `PublicEvidenceResult`, `PublicResultInventory`, or `PublicResultRecord`;
- `DeliveryContinuationCapability` or `ContinueDeliveryResult`;
- `read_next_page` or `action_results_next_page`;
- admitted-evidence prefix or copied `latest_public_results` transport;
- Store-owned result body/cursor/pending provider exchange;
- `content_fragment`/fragment offset/reassembly path;
- `remember_fact`, `WorkingFact`, or Workspace working-set result-retention path;
- Task21, R9, reviewer-name, site, selector, or benchmark-case production specialization.

## Verification commands

Focused owner/vertical suite:

```bash
pytest -q \
  tests/architecture/test_workspace_authority.py \
  tests/architecture/test_single_action_policy_convergence.py \
  tests/unit/agent/test_runtime_algebra.py \
  tests/unit/agent/test_tool_result_projection.py \
  tests/unit/agent/test_episode_context.py \
  tests/unit/agent/test_semantic_delivery.py \
  tests/unit/agent/test_operational_progress_monitor.py \
  tests/benchmarks/model/test_grounded_tools_v2.py \
  tests/integration/model/test_pydantic_ai_spike.py
```

Result: `164 passed`.

Full and static verification:

```bash
pytest -q
ruff check src tests
python -m compileall -q src tests
git diff --check
```

Result: `1645 passed / 24 skipped`; Ruff, compileall, and `git diff --check` pass. One pre-existing Python 3.13
`multiprocessing` fork deprecation warning remains in the observability test.

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
6. Did any change alter World, Binder, Executor, BrowserGym, GoalPlan, evaluator, or live benchmark semantics?
7. Are the remaining action-page/observation cursors private implementation details rather than model-visible evidence
   state?

## Exit statement

Passing this document's provider-free gates permits describing the thin result cutover as verified. It does not permit
describing the whole GUI agent, BrowserGym causal transition, Planner admission, or benchmark campaign as closed. Those
statuses change only when their own falsifiable gates and, where required, an explicitly authorized live benchmark
pass without case-specific production branches.

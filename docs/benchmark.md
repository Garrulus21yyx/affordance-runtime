# Benchmark

## Current status

The thin tool-result/history cutover, accepted-response repair, owner-level action-discovery/catalog repair, and
readable-AX completeness repair are implemented and provider-free verified. The new readable-result focused suite
passes `62` tests; the full suite passes `1656` tests with `24` skipped. Ruff, compileall, and diff checks pass. The
repository-wide mypy command still reports its pre-existing baseline errors in unchanged modules. A fresh-context
review remains part of the final gate.

Overall project status remains **reopened / non-closed**. This cutover does not close:

- the BrowserGym `dispatch -> causal stable fresh World -> StepResult` gate;
- the Planner lexical-admission gap;
- post-fix live benchmark validation of the readable-AX repair;
- any broader live provider/benchmark gate.

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

The bounded general repair is in the existing ActionPolicy prompt: search results are recall candidates; records count
when their meaning clearly entails/paraphrases the requested condition, without requiring identical words, and
incidental keyword overlap remains insufficient. Partial source coverage, visible pagination, or a displayed total
larger than inspected records keeps an exhaustive retrieval open while the current GUI can inspect it. No reviewer,
task phrase, site, expected answer, second model, or Runtime semantic branch is encoded.

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

### G4 — R-ref follow-up

The `read_region` schema accepts the public `R` syntax for the current canonical World, and the resolver validates the
actual current ref. This avoids building a schema enum from a previously admitted result prefix while preserving
currentness at the correct owner.

Search results continue to return a direct `read_region(region_ref)` follow-up for readable matches.

### G5 — action discovery remains bounded and separate

`find_controls(query)` returns a bounded current result and never dispatches a browser action. It has no public generic
continuation capability and no private full-result inventory. Partial coverage tells the model to refine the query.
Every `(operation, E-ref[, destination])` route returned in that result is admitted to the next same-World frozen
catalog as one bounded capability set. A vertical gate forces the soft target to one token, verifies that every returned
route still appears in the manifest/catalog, and resolves every route through the real catalog resolver. A second gate
corrupts one returned ref and verifies fail-closed behavior before provider invocation. Only current `E` refs in the
frozen catalog can reach Binder/Executor.

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

Result: `62 passed`.

Full and static verification:

```bash
pytest -q
ruff check src tests
python -m compileall -q src tests
git diff --check
```

Result: `1656 passed / 24 skipped`; Ruff, compileall, and `git diff --check` pass. One pre-existing
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

## Exit statement

Passing this document's provider-free gates permits describing the thin result cutover as verified. It does not permit
describing the whole GUI agent, BrowserGym causal transition, Planner admission, or benchmark campaign as closed. Those
statuses change only when their own falsifiable gates and, where required, an explicitly authorized live benchmark
pass without case-specific production branches.

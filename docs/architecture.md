# Architecture

## Current status

The current production target is a thin, single-loop GUI agent. The former generic evidence-delivery system is no
longer part of the architecture: local tool results are not copied into a Store-owned public inventory, repacked as an
admitted prefix, or exposed through generic continuation tools.

The first four-case untouched W2 batch after Task740/759 did not support broader closure. Tasks 424, 681, 672, and
556 all failed. Tasks 681 and 672 reached the correct Postmill forum with the exact repository/title/body facts, yet
could not reach the current `Submit` link; Task556 read the exact `Christopher Nolan filmography` link text, then
activated a different ranked `Christopher Nolan` link and terminal-failed. The traces rule out cursor, history,
Monitor, ToolReturn, and ActionSpace construction as the shared cause. For Task681, the fresh World contained 347
legal actions and the existing `ActionPager` had already selected a bounded 32-action page, including the current
site controls. The packed observation nevertheless contained only one lexical suggestion (`Forums`) plus focus.

The reopened owner defect was in `ActionDeliveryPlan`: `ContextBuilder` passed its existing bounded
`base_actions`, but `build_action_delivery_plan` never consumed that argument. It rebuilt presentation from a task
lexical Top-5 and the complete ActionSpace, while `TurnPacker` hard-admitted only the first ranked record. Read/search
made the same split in another form: an AX link or button returned as readable text deliberately lost its executable
`E-ref`, even though the fresh World and complete catalog already owned that exact identity and route. Earlier gates
proved that a literal `find_controls` result remained callable and that focus plus one ranked action survived packing;
they did not prove that the existing bounded action page survived, or that a readable interactive element retained
its grounding. Treating eventual lexical recovery as equivalent to direct usability was the acceptance gap.

The positive contract is now one observation/action alignment, not a new retrieval or state path:

```text
fresh World -> complete current ActionSpace -> complete current Catalog resolver
            -> ActionPager-owned bounded current page
               + at most five non-authoritative task-ranked suggestions
            -> one ActionDeliveryPlan capability set -> model

read_region/search_page_content -> bounded readable records
  returned target is current executable -> attach the same fresh E-ref + current verbs
  returned target is read-only          -> retain its N/F/R identity
```

The bounded base capability set is hard-admitted as a set; the complete ActionSpace is no longer copied into the
presentation plan as optional inventory. `find_controls` remains the literal bounded lookup over the complete current
ActionSpace, and the unchanged catalog resolver remains the only authority that can accept an E-ref. Read/search do
not search all controls and do not manufacture executable identities; they only preserve the grounding of records
they already returned. No delivery lens, synonym table, dense index, cursor, Store inventory, memory, Replanner,
second Binder, or second loop was introduced.

This boundary matches the primary-source GUI-agent pattern. BrowserGym defines browser actions directly over the
current element `bid` and its observation implementation already carries element bid/visibility/bbox metadata
([action space](https://browsergym.readthedocs.io/latest/core/action_space.html),
[observation source](https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/core/src/browsergym/core/observation.py)).
AgentOccam reports its largest gains from aligning and simplifying observation/action representations; specifically,
it merges an interactive element with same-label text while preserving the useful element rather than delegating the
choice to a Runtime lexical singleton ([ICLR 2025 paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/f2c6e459b95694a24ac69c469a4ee746-Paper-Conference.pdf)).
The local implementation keeps the same single ActionPolicy and mature BrowserGym/PydanticAI boundaries.

Commit `52dd6171` has now crossed the original Postmill witness. Task681 completed native evaluation with
`verified_success` after 28 ActionPolicy calls and 345,929 total tokens, compared with the pre-repair run's 60-call
block and 1,187,000-token scale. It entered `/submit/technology`, filled the repository URL and post fields, and
submitted with zero grounding gaps, waits, or fallbacks. Task672 also crossed its former create-post boundary, entered
`/submit/gaming`, acquired the product page, and returned to the form with zero grounding gaps. It later failed for a
different reason: the policy repeatedly reread the first page of a region instead of following the returned
continuation, then exhausted a deliberate output response. This is not evidence for reopening the observation/action
alignment owner.

Fresh untouched Task426 did not support broader closure. The policy correctly identified Shanksville and executed the
fresh Wikipedia search-box grounding, but selected `ArrowDown` repeatedly instead of the already offered `Enter` key.
The first deliberate recovery then spent its entire 2,048-token response on thinking and produced no call. After that
typed invalid response, the next loop could not pair the still-pending accepted call with the immediate failed step
and failed before provider dispatch. The trace recorder also counted an historical response from the PydanticAI run
messages as though it were a current physical attempt. These are ActionPolicy/provider-history recovery and
observability lifecycle defects, not missing controls or grounds for another projection, ranker, cursor, Monitor, or
World path. Broader closure remains explicitly open while that owner contract is reviewed.

That owner review found one shared lifecycle gap rather than a need for another recovery path. The installed
PydanticAI 2.31.1 `capture_run_messages` contract includes normalized supplied history as well as messages stamped by
the current SDK `run_id`. The bridge had instead guessed the current physical response suffix from the maximum retry
count; when a deliberate response terminated on length before consuming its retry allowance, one historical response
was misclassified as current. After the typed failure, the bridge also retained the old pending-call frontier even
though the captured current request had already delivered its ToolReturn, so the immediate failure step could not
provide that same result again.

The provider-history owner now supports exactly two canonical frontiers:

```text
pending frontier: accepted ToolCall awaits the next Runtime ToolReturn
closed frontier:  the exact SDK request delivered that ToolReturn, but no replacement ToolCall was accepted
```

On exhausted output validation, the bridge uses the SDK `run_id` to record only current physical responses, retains
the exact current request that closes every prior call/result pair, and drops rejected response/retry prose. The next
fresh-World ActionPolicy call extends that same official history from the closed frontier. Canonical envelope
validation accepts both frontiers and still rejects orphaned, duplicate, mismatched, or synthetic exchanges. No
Workspace lookup, trace replay, CoreLoop fallback, pending-result store, retry state machine, or second history owner
was added. A vertical test exercises `accepted call -> ToolReturn -> single truncated response -> typed failure ->
next accepted call` and verifies exact call/result conservation plus one-response accounting.

Task426
[`history-recovery-run2`](../evidence/live/w2-task-426-deepseek-v4-flash-20260827-history-recovery-run2/run.json)
crosses this provider-history lifecycle three times. The run produced three physical `output_truncated` outcomes and
continued to later provider calls after each; it made 81 valid tool calls with zero grounding gaps, invalid arguments,
or post-failure internal-history errors. It did not complete the task. The policy repeatedly opened the exact current
Shanksville search result, received `/relation/189076 -> Not Found`, returned to search, and tried the same failed route
again. After 84 policy calls, two final typed invalid responses let the existing Monitor block the stalled episode.
This is now a separate long-horizon failed-route convergence and efficiency witness; it does not justify reopening
the action projection or canonical provider-history contracts.

The failed-route owner repair is implemented but not yet live-verified. `EpisodeMonitor` now retains its existing
bounded ref-free GUI-attempt window across local `NEW_INFORMATION`, because new public text does not prove task
progress. When a dispatched action returns to a semantic page where an earlier outbound attempt began, the Monitor
emits the already-declared `ROUTE_REGRESSION` fact on that first closed excursion. It does not classify the route as
semantically wrong. The signal purchases one existing deliberate `ActionPolicy` call over `TaskGoal`, fresh World,
recent completed results, and the outbound signature; the model owns whether the acquired result is useful and which
different action to take. An immediate exact outbound replay is rejected by the existing CoreLoop before dispatch,
with the same one-fallback-then-block algebra already used for rejected local-tool recovery. The unowned
`STRATEGY_STALL` recovery kind was removed. No Replanner, planning tree, progress state, Store, cursor, history path,
or task/site keyword rule was added.

This boundary follows the useful separation in current primary work: VeriGUI verifies local action effects against
the next observation, while AgentOccam exposes model-owned branch/prune decisions and Agent S2 delegates semantic
plan revision to a model role rather than a deterministic executor
([VeriGUI](https://arxiv.org/abs/2604.05477),
[AgentOccam](https://arxiv.org/abs/2410.13825),
[Agent S2](https://arxiv.org/abs/2504.00906)). The project-level inference is narrower than those systems: Runtime
proves only the closed route and exact replay; the single ActionPolicy performs the reflection. Provider-free
verification covers first-return recovery, an intervening informative read, forward-only non-regression, one
deliberate event, exact GUI replay with zero additional dispatch, and a materially different route reaching task
completion. Live Task426 and one fresh held-out long task remain required before this gap can be closed.
The fixed BrowserGym Python full suite reports 1,822 passed and 19 skipped; its sole failure remains the pre-existing
`docs/interaction-shell.md` documentation-governance count, not a product or recovery regression.

### Local agent shell

The local benchmark Console now presents the existing Runtime as an ordinary-user agent shell. The center column is
one task conversation with owner-emitted status and outcomes; the right column shows the latest Runtime-captured
browser frame. Experiment configuration, failed-run review, raw trace JSON, and runner output live under Labs instead
of competing with the user task in the foreground.

The Console server owns both new read projections. `/activity` maps trace events into a bounded public vocabulary and
does not expose World payloads, selectors, private bindings, or provider transcripts. `/browser-frame` serves only the
latest image referenced by an observation after resolving it inside the run's trace directory and verifying its
recorded SHA-256 digest. The browser pane is therefore a near-real-time, read-only view of Runtime evidence, not a
second browser authority and not pixel-derived task state. Raw `/events` remains available only to the explicit Labs
evidence view.

This shell does not invent a free-form Runtime session API, task revision, or interactive browser takeover. Those
controls are visibly unavailable until their owning Runtime contracts exist; the current benchmark runner remains the
only launch and stop owner. Run history and automatic bad-case grouping are bounded to the current Console process.
This UI work changes neither the single `CoreAgentLoop` nor the benchmark closure status below.

Implementation of the thin result/history cutover, action-discovery closure repair, readable-AX completeness repair,
single-current-World cutover, atomic PageMap/Manifest repair, bounded post-action recapture repair, and BrowserGym
large-page liveness, viewport-grounded media, canonical public-identity, and linear fresh-World projection repairs is
complete. The current convergence patch additionally makes control discovery a real filter, publishes BrowserGym's
official global navigation actions only for WebArena-family profiles, counts same-World discovery loops in Monitor,
applies proactive SDK-history processing, byte-bounds the PageMap directory without shrinking current World, and
keeps both one fresh focused executable target and one task-ranked target when an ordinary bounded action prefix is
packed; an explicit `find_controls` result remains one complete higher-priority capability set. The
current action-boundary repair also makes that rank purely presentational: registry-owned action tools use stable
E-ref-shaped schemas, while the existing complete current `ActionSpace` resolver alone validates the selected ref,
operation, destination, parameters, and private action identity.

The latest Task266 convergence repair closes three owner contracts without adding another memory, evidence, cursor,
or control-flow path. `GoalCompiler` now requests disabled thinking whenever the selected provider declares that
wire capability; providers without the capability remain unchanged. ActionPolicy and Harness compaction consume one
prompt-owned evidence-status rule: an exact identifier encoded by a resolved link remains identity evidence when the
destination later fails to load, and a verified claim should not remain unresolved. The summary is non-authoritative
model text: the PydanticAI history owner validates only its typed message/call-result shape and does not infer claim
identity by comparing numbers across headings. It creates no fact store and makes no independent task judgment.

Control discovery also now gives a candidate's exact public label ownership of colliding query tokens before applying
inventory-wide role/operation facets. Thus `Go button` finds the current `Go` button even though the same ActionSpace
also contains `go_back`/`go_forward`; an explicit mismatching role still rejects the candidate, and every genuine
match remains visible. An exhausted PydanticAI output-retry capture records only the response suffix permitted by the
invocation's existing `UsageLimits`; PydanticAI may merge adjacent historical request messages, but old responses can
no longer be counted as physical calls from the current invocation.

The authorized
[`run37`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run37/run.json) crossed these contracts and ended
`done` with native `verified_success`, returning relation `2176999` and driving distance `287km`. It made one
GoalCompiler call, 39 ordinary ActionPolicy calls, zero recovery calls, and exactly one STOP, post-STOP capture, and
native evaluation. This is a live correctness witness for this Task266 causal line, not closure of the broader
held-out benchmark campaign. Its 870,289 accumulated history tokens also falsified the efficiency claim that
pressure-only semantic compaction was sufficient: 135 historical user prompts replayed the same TaskGoal/GoalPlan and
large expired Worlds, while only 39 prompts represented the authoritative current turn.

The history owner now performs a cheap structural projection before deciding whether semantic compaction is needed.
One metadata-marked SDK `UserPromptPart` anchors the current `TaskGoal + GoalPlan`. Every historical World prompt is
removed before packing because `TurnPacker` supplies exactly one authoritative fresh World for the current call;
every ToolCall/ToolReturn and public model `TextPart` remain exact. Once a ToolReturn has closed an older response, its
private `ThinkingPart` may expire only when that same response already contains a non-empty public `TextPart` carrying
the model-visible conclusion. The unresolved response and a tool-only reasoning response remain exact. Harness
`SummarizingCompaction` has two size-only admission arms: the existing 80% complete-request capacity guard, and a 50%
history high-water mark that also requires at least 15% of history capacity to be reclaimable outside the exact suffix.
Once admitted, Harness targets 30% of history capacity and preserves the newest pair-safe 12% suffix exactly. The
separate reclaim threshold supplies hysteresis, so a summary plus a small amount of new history cannot immediately
schedule another model call. No result kind, task text, semantic novelty, Monitor state, or summary-output cap
participates in scheduling. This is one projection inside the existing PydanticAI history owner, not a memory,
progress reducer, evidence path, cursor, or second current-state authority.

The authorized W1b Task7
[`run1`](../evidence/live/w1b-task-7-deepseek-v4-flash-20260826-run1/run.json) falsified one wrapper assumption in that
history owner. A throwaway summary view had replaced typed `ToolReturnPart` values with `SystemPromptPart` values to
bypass Harness's prose-display clipping. Harness therefore could not recognize one completed call/result pair at its
token cutoff; the third incremental compaction retained the old `find_controls` return while summarizing its call.
The newest pending call remained exact, so the wrapper's pending-only check accepted the invalid history. Canonical
provider projection then correctly rejected it before Catalog construction. The owner repair deletes that synthetic
view and gives Harness the original typed PydanticAI history, whose official cutoff is pair-safe. Before accepting any
compaction, the same boundary now projects the whole candidate through the canonical history algebra; an invalid
third-party result restores the byte-for-byte input history instead of terminating ActionPolicy. Recent raw reasoning
and model conclusions remain exact, while full original results remain in trace.

[`run2`](../evidence/live/w1b-task-7-deepseek-v4-flash-20260826-run2/run.json) crosses the repaired boundary and ends
with native `verified_success`. Both age/size-triggered compactions continued into an ActionPolicy request with 18
catalog tools. The run made 16 valid policy calls, zero invalid, grounding, stale, or wait outcomes, and exactly one
STOP, post-STOP capture, and native evaluator call. It returned Pittsburgh International Airport, Pennsylvania,
15231 after reading the explicit 33 km OSRM route. This is a live witness for typed pair-safe compaction under actual
age/size pressure, not closure of the broader held-out benchmark campaign.

[`run38`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run38/run.json) remained behaviorally correct—native
`verified_success`, 43 valid policy calls, zero waits, zero invalid calls, and one STOP—but falsified the first
efficiency implementation. Six pressured summaries were semantically rejected because a Runtime regex treated any
number repeated under `Verified facts` and `Remaining questions` as the same contradictory claim. Every rejection
restored raw history, so the run paid both 198,783 compactor input tokens and the ordinary ActionPolicy requests;
prompt tokens rose to 1,379,172. Claim identity is open-world semantics, not a deterministic history invariant. The
history owner now accepts Harness summary prose after typed message and exact suffix validation; the shared prompt
remains guidance, and the current task, one fresh World, and exact call/result history remain available to the single
ActionPolicy. No retry or alternate summary path was added. A post-repair live efficiency witness was required.

[`run39`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run39/run.json) crossed that scheduling repair: one
28,734-token summary was accepted, later ActionPolicy requests fell from about 33k to 13--20k, and the native evaluator
again returned `verified_success`. It also isolated the remaining semantic pollution. The accepted summary preserved
relation `2176999` under verified facts while simultaneously placing it under `Remaining questions` and setting
re-verification as `Next intent`; the policy then repeated coordinate and name searches. The summary contract now
contains only stable completed outcomes, verified facts, and failed strategies. It cannot publish current stage,
working hypotheses, remaining work, or next intent. Those prospective decisions are recalculated by the one
ActionPolicy from the current TaskGoal, static GoalPlan, fresh World, and recent exact suffix. This removes mutable
planning from long-term compaction rather than adding a validator or second progress owner. A fresh witness for this
final prompt contract remained required.

[`run40`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run40/run.json) is the final same-task witness. It
ended with native `verified_success`, 34 valid policy calls, zero waits, zero invalid arguments, one STOP, and no
compactor call. The structural history tier kept every complete request below semantic pressure, so Harness correctly
did no model-backed work; the model used relation `2176999`, found `Distance: 287km`, and submitted directly rather
than reopening relation verification. Prompt tokens fell from run37's 1,008,148 to 847,397 (160,751 / 15.9%), and
model latency fell from about 127.7s to 98.9s. End-to-end wall time was about 350s versus 325s because BrowserGym
transition time varied, so no wall-time improvement is claimed. The stable-only summary contract remains covered by
provider-boundary tests; Task7 run2 later crossed that live pressure twice, while run40 demonstrates the preferred
cheap path.

The latest repair keeps the generic BrowserGym browser profile unrestricted, while an environment may explicitly
provide a navigation scope. WebArena is the only current selector of that restricted profile: its runner reads the
official BrowserGym `ENV_VARS` URL set once and gives the normalized locations to the existing private browser-context
binding. World publishes only `navigation_scope=environment_restricted`, while the ordinary ActionSpace/Catalog keeps
the registry's generic HTTP(S) `goto` shape. BrowserGym execution checks the selected destination against the private
scope before `step` and returns typed `NOT_SENT/destination_outside_environment` on rejection. There is no
task-, URL-, or site-name detection, model-visible service directory, or alternate navigation executor.
Task266 run6 crossed that repaired boundary, activated the intended article, and recovered Portland's official
coordinates. It then exposed a narrower browser-profile mismatch: the generic tool compiler still required an `E-ref`
for `goto/go_back/go_forward/new_tab/tab_focus/tab_close`, even though BrowserGym's official navigation primitives are
target-less browser operations. The compiler now binds the single current `browser_context` privately and publishes
only each primitive's business parameters. Page controls retain explicit current `E-ref` grounding. Explicit
`find_controls` recall is literal token/phrase bounded; the former hand-written prefix/suffix and fuzzy expansion no
longer turns substrings such as `ion` into navigation matches. This adds no browser state, site detection, action
authority, or retrieval service.
Task266 run7 crossed that browser-profile boundary: the first discovery returned the real Wikipedia search textbox,
the model entered `Portland, Maine`, BrowserGym captured the fresh value, and every tool call remained valid. The
fresh World then exposed the autocomplete rows as readable `StaticText`, not executable controls. When the model
asked `find_controls("Portland (Maine) link")`, the remaining recall algebra admitted every page link because `link`
matched the role even when none of the target words matched. Alphabetical background links displaced the requested
target, the model replayed the readable region, and Monitor correctly blocked the same-World control stall.

The explicit-query owner now treats each current action's existing role/operation tokens as control constraints for
that candidate and requires any remaining query terms to match its label or functional path. Matches are ordered by
target-term coverage but are not collapsed to one Runtime-guessed subgoal. A role/operation-only hit cannot admit a
control when unmatched target terms remain. An empty executable-control result stays empty and does not redirect to
readable-content search. This is deterministic retrieval over the complete current `ActionSpace`; it adds no keyword
table, site/task branch, semantic index, model ranker, or alternate action authority.
Candidate qualification separates local evidence from structural context. Tokens shared by every page-control
functional path are common page ancestry: they may remain available to non-authoritative ranking but cannot alone
admit any control into `find_controls`. Browser-context primitives keep their separate capability scope and do not
defeat this inventory-wide ancestry calculation. A public label or discriminative local path still qualifies
normally; no URL, site, task, or vocabulary special case is involved. The result also reports every query term not
supported by the returned controls. A partial literal match is therefore truthful: a control may match `dashboard`
while `period` and `selector` remain explicitly unmatched. This field is derived by the same recall owner from the
same candidate matches; it is not a second search path.

The authorized W1b Task0
[`run4`](../evidence/live/w1b-task-0-deepseek-v4-flash-20260826-run4/run.json) crosses both repairs. Shared page ancestry
no longer filled discovery with unrelated controls, partial matches exposed their unsupported terms, and exactly one
age/size-triggered Harness compaction handled expired model prose. The run made 28 valid policy tool calls, zero
invalid, grounding, stale, or wait outcomes, then submitted `Quest Lumaflex™ Band`; the native evaluator returned
`verified_success`. This is a live witness for these two bounded contracts, not closure of the broader held-out
campaign.
Task266 run8 crossed that repaired recall boundary, activated the intended article, and read the official coordinates.
It then navigated to an unauthorized external API even though the benchmark-provided map was already open in tab 0.
BrowserGym correctly terminated the WebArena task, so the following currentness result was the expected
`task_done/stale`, not a stale-ref regression. The authoritative fresh World already contained `active_tab_index` and
the public `index -> route` mapping, but indexed compact rendering reduced non-entity action subjects to region
headings and discarded their state. The browser-only direct-observation patch has been removed. The sole compact
renderer now emits every current non-entity `InteractionSubjectKind` already present in the same Actor World before
the folded page directory. Adding another action for an existing subject kind requires no renderer branch. Browser
schemas, ActionSpace resolution, Binder, BrowserGym authorization, and lifecycle handling remain unchanged; no tool
name, task, site, or route inference was added.
Task266 run9 crossed that compact-observation repair: the model saw the tab inventory, focused the intended pages,
recovered Portland's official coordinates, returned to the map, and selected the real directions control. BrowserGym
then rejected that click before dispatch as `stale_binding/state_changed`. The target BID, role, label, page, episode,
and executable click offer were unchanged; only presentation fields in the canonical `public_state` had changed. The
project comparator was treating CSS/appearance/active state and the complete availability record as a second physical
identity authority instead of using the selected interaction offer's existing `currentness_fields` contract and
Playwright actionability.

The owner repair removes that duplicated authority. Element currentness now compares the fresh World lineage, BID,
role, accessible label, the selected offer's declared semantic state, and select/drag binding domains only. Unrelated
appearance/layout state is observational context, not binding identity; live executability is still derived from the
same offer and the final physical action remains BrowserGym/Playwright-owned. A typed physical
`NOT_SENT/stale_binding` reuses the one existing binding-refresh capture and returns the fresh World to the single
ActionPolicy. It never replays the action and introduces no retry loop, alternate World, or second currentness store.

Task266 run10 then exposed two previously contradictory control contracts. Four of eight provider responses contained
multiple tool calls despite `parallel_tool_calls=false`; the PydanticAI bridge silently kept the first valid member,
while neither canonical history nor benchmark metrics disclosed that selection. Later, after one exact local-result
replay activated recovery, Monitor blocked a materially different `read_region` merely because it also produced no
new information. Neither failure was missing World/task context, evidence, cursor state, or GUI grounding.

The first repair rejected the complete multi-call envelope and re-asked the provider once. Task266 run11 falsified
that design: DeepSeek returned two calls again despite the explicit correction and terminated before a second action.
This was a brittle provider-compliance gate, not an execution-currentness invariant.

The converged owner contract restores one decision and one precise recovery identity:

- provider calls are ordered proposals at the Catalog boundary; only the first call is normalized and resolved;
- later calls are never executed, queued as Runtime work, or used as fallback if the first call is invalid;
- canonical PydanticAI history retains every exact proposed `ToolCallPart`. On the next provider turn PydanticAI pairs
  the selected first call with its real result and every later call with a native same-ID `ToolFailed(not executed)`;
  all proposals are therefore closed together before the fresh World is reconsidered;
- raw provider output remains in the transcript; benchmark metrics count each multi-call envelope, and invocation
  diagnostics record the proposals discarded from execution;
- Monitor uses one consecutive same-World no-progress episode. A different empty query, no-match region,
  observation-only step, or ineffectual same-World GUI dispatch cannot clear it. Typed `NEW_INFORMATION`, a GUI
  transition with a satisfied local postcondition/observed change, or a causally dispatched action that reaches a
  different fresh public World starts the next episode; otherwise recovery advances once and then blocks bounded
  recurrence.

This is the atomic-action variant used explicitly by [Agent S2](https://arxiv.org/abs/2504.00906), whose Worker chooses
one atomic action from the latest observation. Systems that execute batches make that algebra explicit instead:
[UI-TARS](https://github.com/bytedance/UI-TARS) parses an action sequence, while the
[OpenAI Computer Use loop](https://developers.openai.com/api/docs/guides/tools-computer-use) executes an ordered
`actions[]` batch before the next screenshot. This Runtime has no batch transaction/currentness contract, so it does
not reinterpret arbitrary heterogeneous function calls as such a batch. The repair reuses the canonical envelope,
PydanticAI history, Catalog resolver, typed attempt signature, and outer step budget. It adds no pending-call queue,
multi-action scheduler, second Runtime loop, evidence path, cursor protocol, or Monitor model. Post-repair live
benchmark validation remains separately authorized.
Live benchmark validation remains separately authorized. The repository-wide mypy command still reports its
pre-existing baseline errors in unchanged modules and is not counted
as a passing gate.

Task266 run13 crossed the history and cycle-recovery repairs, then exposed a SurfaceAdapter current-page violation.
After `tab_focus`, BrowserGym's observation getter correctly read the newly active tab, but `_causal_step` still used
the pre-dispatch Playwright page for DOM-quiet waiting, private physical-property enrichment, and `after_url`. The
result joined the new tab's DOM/AX facts to the old tab's physical state, removed a valid text-entry action from the
next `ActionSpace`, and led to a tab/read cycle that Monitor eventually blocked. This was not missing task context,
history, progress memory, or a Monitor gap.

The SurfaceAdapter now gives the pre-dispatch page only navigation-watcher ownership. Immediately after BrowserGym
returns, its current `unwrapped.page` becomes the sole post-action page for quiet tracking, stable acquisition,
private enrichment, and transition `after_url`. A real Playwright two-tab owner test proves that observation,
enrichment, and trace use that same current page. No alternate observation, retry, browser-state projection, action
owner, or control loop was added. Run13 remained failed pre-repair evidence; run14 below crossed this boundary.

Task266 run14 crossed that current-page repair: tab focus, fresh World identity, current controls, and browser-global
actions remained correct; all 18 completed model calls were valid, with zero stale bindings, invalid arguments,
`wait`, or fallback. The model also retained Portland's coordinates and the unresolved OSRM requirement. The case
nevertheless reached its enclosing timeout after about 1,001 seconds. Provider latency accounted for about 164.5
seconds. Exact PydanticAI message timestamps showed that each local read on the 6,002-target / 4,096-fact Wikipedia
World consumed another 67--72 seconds before the next provider request, and the 19-step trace grew to about 505 MB.

The shared cause was repeated derivation of one immutable fresh World, not another action, cursor, or evidence defect.
`current_findings_digest` rebuilt the complete target-semantic map once per fact (`O(facts * targets)`); an unchanged
local result rebuilt two `WorldDeliveryIndex` values for a no-change delta; the next turn rebuilt the same current
index again; and trace serialization ignored the existing `serialize=False` declarations and copied both canonical
World projections. On run14's persisted observation, the first two costs measured 44.78 and 10.35 seconds.

The converged contract is now:

```text
fresh World
-> one current ActionSpace / WorldDeliveryIndex / CanonicalPublicWorldProjection
-> any number of same-World local reads reusing those values
-> Monitor digest from one target map plus one fact pass
-> one bounded step lineage and one exact provider transcript in Trace
```

`WorldTransitionProjector` returns a typed empty delta immediately for the identical World object; `RunState`'s
existing current index is reused when its observation and exact action IDs still match; and the already computed
delivery transition is committed once. Trace keeps the full observation in its deduplicated observation event and
the exact provider request/response in `generation_attempts.transcript`; a step keeps only typed outcome/receipt and
bounded transition counts plus lineage. It does not copy policy snapshots, canonical Worlds, or the same provider
attempt under multiple keys. Honest truncation metadata accompanies bounded changed-region refs.

This follows the mature separation in the
[BrowserGym ecosystem](https://openreview.net/forum?id=5298fKGmv3): the environment supplies the current observation
and receives the next action, while experiment tooling observes the trajectory. AgentLab's official
[`StepInfo`](https://github.com/ServiceNow/AgentLab/blob/main/src/agentlab/experiments/loop.py) persists one step's
observation/action/agent information with profiling timestamps, saves screenshots separately, and stores the fixed
goal once. [AgentOccam](https://proceedings.iclr.cc/paper_files/paper/2025/hash/f2c6e459b95694a24ac69c469a4ee746-Abstract-Conference.html)
likewise compresses page observations and selectively replays relevant history; it does not require a second
Runtime-owned evidence or cursor system. The project keeps its typed World for grounding, but no longer recomputes or
re-serializes that authority per local tool result.

Task266 runs 15--19 exposed one history-ownership defect. PydanticAI already carried exact results, but the bridge
discarded earlier fresh-World prompts and initially discarded model reasoning as well. The attempted repair then added
a second, source-covered `ProgressCheckpoint` producer with knowledge-specific triggers. Run19 falsified that design:
14 reducer calls added latency, seven timed out, irrelevant results retriggered forever, and a summary of selected
read/search records omitted the action--observation trajectory that explained the task's real progress.

The converged owner is the official PydanticAI message history, using Harness
[`SummarizingCompaction`](https://pydantic.dev/docs/ai/harness/compaction/) directly:

- every accepted turn initially persists the SDK-produced fresh-World `UserPromptPart`, ordinary `TextPart`,
  `ThinkingPart`, provider metadata, every proposed `ToolCallPart`, and the next same-ID `ToolReturnPart`;
- one current task/plan prompt part is preserved as the only historical anchor. All historical World prompt parts,
  including historical media, are removed; the one current fresh World and its media are supplied separately on the
  physical request. After an older response is closed by its ToolReturn, the projection removes private thinking only
  when that response contains its own non-empty public text conclusion. Public text, ToolCalls, ToolReturns, tool-only
  reasoning, and the unresolved response remain exact;
- the existing `RequestAdmission` breakdown triggers the capacity arm at 80% of effective provider input. A second
  size-only arm triggers when history itself reaches 50% of its available capacity and at least 15% is reclaimable
  outside the recent exact suffix. That same breakdown already counts SDK history, pending ToolReturn, fresh World,
  tools, and protocol overhead; read/search type, Monitor recovery, task revision, semantic novelty, and the provider
  usage anchor do not schedule another model call. The current-World delivery soft target is not history capacity;
- Harness targets a 30% post-compaction history budget and keeps the newest pair-safe suffix fitting 12% of history
  capacity at full fidelity. Its plain `SystemPromptPart` summary retains at most three completed user outcomes plus the
  eight task-critical verified facts, and two failed strategies. It does not retain current stage, remaining work,
  next intent, an action-by-action log, old URLs, or stale current-state references;
- Harness 0.25's formatter does not render `ThinkingPart`. The history owner therefore maps eligible remaining
  thinking to ordinary text only in the throwaway summarizer input, then restores Harness's preserved suffix from the
  exact projected messages. Raw provider responses and reasoning remain exact in Trace; the pending exchange is never
  rewritten before its same-ID ToolReturn is delivered;
- the fresh current World remains the sole current-state authority. The summary is explicitly historical and cannot
  act, authorize, terminate, bind controls, advance cursors, or determine task truth;
- summary failure or timeout leaves the exact raw history unchanged. Request admission then either fits that honest
  history or returns the existing typed capacity failure; no lossy fallback rewrites it.
- one absolute policy deadline covers compaction, action, and the existing bounded provider retry. Compaction and
  ActionPolicy each have role caps, but no static partition: after compaction actually returns, the provider boundary
  subtracts elapsed time, the existing retry-delay reserve, and the safety margin, then divides the real remainder
  across the two possible action attempts. The shared model client's default timeout admits the compactor cap, while
  each canonical ActionPolicy or representation-repair envelope carries its recalculated official PydanticAI
  `ModelSettings.timeout`. This is ordinary deadline propagation inside one provider port, not an additional model,
  retry loop, scheduler, or control path.

The custom `checkpoint_reducer.py`, `progress_checkpoint.py`, source-coverage gate, knowledge batching, Monitor trigger,
dedup memo, and pinned checkpoint were removed. The configured ActionPolicy model is reused only when real pressure
requires a summary. There is no Manager/Worker, memory service, retrieval index, evidence projection, cursor path, or
second Runtime state.

Runs 20--22 refined only this capacity contract. A fixed message-count tail and a 10-second timeout failed on variable
GUI Worlds; both were replaced by a token-bounded suffix and the existing policy-deadline partition. Harness's
provider-usage-aware context estimate then caused false per-turn pressure, so the bridge now uses Harness's
message-only estimator. Finally run22 showed that the 8,000-token current-World delivery target is not a history
capacity: one large page can exceed it. History pressure is now computed from the provider's effective input capacity
after reserving one current-turn soft target. This remains one stateless calculation at the PydanticAI boundary, with
no reducer schedule, cooldown, retry loop, or additional memory state.

Run23 showed why the final pressure decision must use that complete canonical request rather than a second history
estimate: immediately before the rejected turn, RequestAdmission counted 53,712 history tokens and 67,022 total input
against a 62,904-token effective limit. The Harness message estimator still put the raw messages below its independent
threshold because it does not include the pending result/current request representation. The bridge now preflights
the exact normal TurnPacker/RequestAdmission path, calls Harness only when that owner reports pressure, and reuses the
already admitted packed request when no compaction is needed. This adds no estimator, capacity authority, or alternate
provider envelope.

Run24 crossed that scheduling repair and retained the Portland/Acadia facts through compaction, then reached the OSRM
route and began reading its distance. It exposed one provider-boundary budget propagation defect: the Harness call's
outer 30-second deadline reused an `AsyncOpenAI` client configured with the ActionPolicy's 27.25-second transport
timeout. Three pressured summaries were therefore cut off at about 27.8 seconds. Raw history remained usable after
the first two failures, then correctly failed admission at 68,081 tokens against the 62,904-token effective limit.
The repaired boundary gives the single shared client the longer compactor deadline and puts the shorter action
deadline in the canonical per-request model settings, so neither role can silently override the other's declared
budget.

Run25 crossed the compactor-client repair: every summary completed, no request reached context capacity, and the agent
retained relation ID `2176999` plus OSRM distance `287km` through 50 policy turns. It exposed that the replacement
budget was still statically partitioned: after the final summary completed in 23.0 seconds, both ActionPolicy attempts
were still capped at 21.125 seconds and timed out at about 21.7 seconds. The boundary now propagates the absolute
deadline and recomputes the request timeout after actual compaction elapsed; the same run25 timing yields 30.75 seconds
per remaining attempt while keeping the original 90-second total closed.

Run27 crossed the dynamic-deadline repair and exposed a different history-fidelity mismatch. The exact `read_region`
ToolReturns at steps 11 and 14 contained Portland's and Acadia's coordinate rows, and the ActionPolicy concluded both
values correctly. Harness 0.25's internal prose formatter exposes only the first 500 characters of each summarized
`ToolReturnPart`; both coordinate rows lay after that generic clip. Our verification-oriented summary prompt then
downgraded the explicit conclusions to unverified claims, the expired exact results were replaced, and the policy
spent later turns reading both wiki pages again. The 900-second watchdog was only the terminal mechanism: eleven
successful compactions consumed about 266 seconds, and the final exact suffix had already retained the independently
confirmed `287km` result while the policy was locating the still-unknown relation link.

That revision temporarily supplied Harness a throwaway summary-only view so owner-bounded public ToolReturns appeared
past Harness's generic prose clip. Task7 run1 later falsified the approach: replacing typed `ToolReturnPart` values in
the view hid call/result pairing from Harness's cutoff. The current boundary therefore gives Harness the original
typed PydanticAI history, lets its official cutoff select a pair-safe expired prefix, restores the exact suffix, and
validates the entire compacted topology before acceptance. A provider error, timeout, or invalid topology restores the
exact typed input history. The summary prompt still preserves a later explicit ActionPolicy conclusion unless later
trajectory content contradicts or retracts it, and treats coverage/pagination as scope metadata rather than evidence
that a returned complete record is absent. Because Harness invokes the configured model directly rather than the
canonical ActionPolicy envelope, that same model has a bounded compaction role cap; normal action and repair requests
continue to use their existing request-scoped role settings. No synthetic part, checkpoint, fact store, cursor,
Monitor trigger, scheduler, or second model state enters canonical history.

Run28 crossed that history-fidelity repair: the model retained both city coordinates and obtained the route distance,
but chose a direct external OSRM URL rather than the already-open WebArena map. BrowserGym's official post-step
validator loaded the URL and then returned `terminated=True, reward=0`. Two independent contract gaps turned that one
terminal mistake into repeated control activity: the WebArena evaluator ignored provider terminal state until an
agent STOP, and the same-call result projection omitted `ExecutionReceiptBatch.terminal_failure`, rendering a typed
`NOT_SENT/stale_binding(task_done)` as running success.

The positive contract is now singular. Every browser profile receives the registry's generic HTTP(S) `goto` schema.
A restricted environment supplies configured URLs; Surface projection derives BrowserGym-compatible netlocs and
keeps them only in the current private browser-context binding. World exposes only that the scope is restricted, not
the allowed hosts. After normal Catalog resolution and binding, BrowserGym execution rejects an unauthorized URL as
typed `NOT_SENT/destination_outside_environment` before dispatch. Independently, every WebArena native
`terminated|truncated|done` snapshot is classified immediately; only voluntary successful completion remains
gated by agent STOP. The ordinary ToolReturn projection now marks any failed execution result as failed and exposes the typed
non-dispatch terminal failure plus bounded currentness reason. No retry, navigation wrapper, evaluator oracle, or
benchmark task branch is added.

Run29 crossed those terminal and navigation-scope repairs and reached the final answer stage, but its last DeepSeek
response exhausted the provider's real completion budget as a long text response with no ToolCall. Two existing
provider/observation fields were not being carried through their owners. The installed PydanticAI DeepSeek profile
left the generic `max_tokens` setting mapped to `max_completion_tokens`, which the endpoint did not enforce, and the
BrowserGym projection consumed `open_pages_urls` while discarding the positionally paired `open_pages_titles`. The
model therefore saw a bare local route for the inactive map tab and could legally return prose instead of the offered
`tab_focus`/final tool contract.

The positive owner contract is now:

- BrowserGym's `open_pages_urls[i]` and `open_pages_titles[i]` form one current tab record with public `index`,
  `active`, bounded `title`, and sanitized `route`. The title is the semantic hint, the route is stable location
  identity, and the index is the `tab_focus` argument. Credentials, query, and fragment never enter the route;
- restricted navigation locations remain solely in the Runtime-private BrowserGym binding. Neither World nor the
  ActionBinding/Catalog schema exposes them as a service directory, and local benchmark routes are not rewritten into
  invented public domains;
- title changes do not change the browser-context binding identity; current URL/index still own currentness;
- the DeepSeek model profile explicitly tells PydanticAI to send the existing generic output budget as
  `max_tokens`. The canonical provider envelope also maps the already-selected per-call reasoning profile into
  PydanticAI's DeepSeek `thinking` setting: ordinary and representation-repair calls remain disabled, while the first
  call for one typed recovery event is enabled. PydanticAI owns the corresponding `reasoning_effort` wire field and
  typed `ThinkingPart` parsing/replay;
- every canonical ActionPolicy envelope disables parallel calls and starts with `tool_choice=auto`, allowing the one
  ActionPolicy response to retain its bounded text/reasoning together with one ToolCall. If output validation rejects
  a text-only response, PydanticAI increments `RunContext.retry`; the same SDK per-step settings callable strengthens
  only that one bounded retry to `thinking=false + tool_choice=required`, because DeepSeek rejects required tool choice
  with thinking enabled. The SDK still owns `DeferredToolRequests`, argument validation, call IDs, reasoning/tool
  history, and retry history;
- the existing ActionPolicy Agent uses a PydanticAI output validator: a text-only response receives one same-context
  SDK output retry, while an exhausted pair returns typed `no_tool_call` or `output_budget_exhausted`. A pre-existing
  representation-repair request gets no nested output retry, so the output-validation sequence is bounded to two
  model responses. The existing transport retry remains independently bounded by the same absolute policy deadline.

Rejected prose and its SDK retry prompt remain in the exact provider transcript but do not enter accepted canonical
history. CoreLoop, Monitor, World authority, execution, compaction, and evaluator behavior are unchanged; there is no
tab recognizer, URL remapper, provider parser, fallback action, or second control path.

Task266 run31 accepted with native `verified_success`, closing the live correctness witness for this causal line. Its
46 policy calls also made the remaining efficiency coupling measurable: the public restricted `goto` schema exposed
six authorized localhost netlocs, which the model treated as candidate services, while the final Harness summary spent
1,888 tokens on action narration, stale refs, incidental facts, and all guessed URLs. The current optimization restores
the generic public URL shape and retains location authorization only in the existing private BrowserGym binding. It
also tightens the same Harness summary to conclusion-oriented task progress, reduces its output cap to 1,024 tokens,
and keeps a 12% exact pair-safe tail. Fresh World, exact ToolReturns, the compaction trigger, CoreLoop, Monitor, and
execution remain unchanged; no new memory, retrieval, cursor, planner, or control-flow owner is introduced.

Run21 independently exposed that canonical target ordering had discarded a source fact it already possessed. Two
identically named executable links on the Maine article occupied distinct structural paths but were each assigned the
same region-local occurrence. `WorldDeliveryIndex` now preserves source structural occurrence in one document-scoped
public order before the canonical E-ref projection. Identical controls with distinct structural positions remain
individually executable; only controls lacking any public structural distinction retain the typed ambiguous failure.
No URL, page text, site, task, selector, or model-side disambiguation was introduced.

Task266 run17 crossed the checkpoint-content repair: the accepted checkpoint retained Portland's coordinates and the
next Acadia intent, and ActionPolicy reached the Acadia search. It then exposed two independent owner defects. First,
the reducer was invoked on 16 of 21 turns—five immediate knowledge calls, three recoveries, and eight calls caused by
the arbitrary `completed_exchange_count > 4` condition; 13 calls consumed their full 18-second timeout. Second, the
final Enter dispatch carried a valid BrowserGym `stable_navigation` trace and a fresh post-capture World, but the
selected `press_key` binding had semantic verification, so `ProductionActionOutcomeProjector` ignored the transition
and emitted `UNKNOWN`. Monitor then correctly blocked the false no-effect trajectory. The durable failed witness is
[`run17`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run17/run.json).

The execution repair adds one generic typed `ExecutionTransition.STABLE_NAVIGATION` to the existing `ActionResult`.
BrowserGym produces it only from its already-validated typed transition trace. The Projector uses it to select the
existing navigation-context verification independent of the pre-action binding family, but confirmed change still
requires current structural or screenshot evidence resolvable in the fresh post-action World. Private adapter trace
data remains Trace-only and cannot promote an outcome. Monitor, CoreLoop, World, and BrowserGym transition state are
unchanged. This is one conversion at the execution contract, not a second currentness path.

The final scheduling repair remains entirely within `PydanticAIGroundedDecisionPort`, the existing SDK-history owner.
It removes all semantic and event triggers: one deterministic token-pressure check gates Harness, and Harness alone
chooses the pair-safe prefix. There is no queue, cooldown, coverage inventory, asynchronous reducer, or another loop.

Provider-free verification and the post-repair fresh Task266 witness are recorded in `docs/benchmark.md`. Historical
run results below remain failure evidence rather than claims about the current implementation.

Overall project closure remains **open only at the broader held-out campaign level**. The former named open claims have
later evidence:

- Task266 run37 is the accepted post-budget live witness after run19 for stable navigation, action delivery,
  changed-World Monitor reset, document-scoped structural grounding, and the TaskGoal-owned turn budget;
- Task7 run2 crosses two accepted age/size-triggered Harness compactions with exact typed call/result topology;
- the former Planner lexical-admission defect was the C12 privacy-by-field-name filter. Current typed intake,
  GoalCompiler request construction, and `AgentContext.task` projection preserve bounded public TaskGoal values
  losslessly, including route-shaped business key names.

BrowserGym's supported acquisition algebra is also bounded rather than open-ended: ordinary dispatched actions return
one causal post-action acquisition; typed stable navigation reaches the same fresh-World StepResult path; a dispatched
action whose normal acquisition returns `acquisition_unstable` receives at most one independent read-only recapture,
as live-verified by Task27 run2; and uncommitted `navigation_pending` remains typed fail-closed. These witnesses do not
establish breadth or repeated-run stability across the untouched benchmark set, so the next evidence is a held-out
campaign rather than another production repair.

The first untouched Task8 run reached the native evaluator without a Runtime, provider, grounding, currentness, or
history failure, but exposed an external response-contract contradiction. The installed WebArena-Verified public
`FinalAgentResponse` schema tells the model that an empty retrieval uses an empty array; the official Task8 evaluator
reference instead requires `NOT_FOUND_ERROR` with null data. The model had correctly excluded the approximately 32 km
CMU-to-Pittsburgh-International route from a 5 km result and followed the public empty-array instruction, so the native
failure does not reopen Planner lexical admission, BrowserGym acquisition, or typed history.

The WebArena-Verified benchmark profile now publishes one unambiguous zero-result rule through its existing
`TaskBoundary`: after a completed RETRIEVE finds zero qualifying items, the model must emit `NOT_FOUND_ERROR` with null
data; a nonempty completed retrieval emits `SUCCESS` with the result list. This is projected through the ordinary
`TaskGoal.constraints -> AgentContext.task.constraints` path. The BrowserGym goal remains unchanged and the upstream
Pydantic response codec remains validation-only, so no private evaluator answer, task identity, response rewrite,
alternate prompt, or new Agent/Runtime authority was introduced. Task8 run6 is the accepted native witness for this
benchmark-owner clarification.

Task8
[`run2`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run2/run.json) and
[`run3`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run3/run.json) crossed the public zero-result rule but
did not reach STOP. Run2 ended after a text-only ActionPolicy response and its one SDK retry both exhausted their
output budgets. Run3 acquired the decisive CMU, Pittsburgh International Airport, and approximately 32.8 km OSRM
facts, then continued searching; its last policy invocation again emitted two output-limited text responses instead
of a ToolCall. The positive provider-boundary repair above prevents that legal-but-invalid wire choice rather than
adding a repetition recognizer or Monitor control path. These two runs remain failed pre-repair evidence. Task8 run6
later accepted with one STOP, one post-STOP capture, and one native evaluation after the provider boundary restored
optional native text and the existing Harness compactor remained the only low-frequency progress-summary owner.

Task266 run18 crossed the reducer scheduling repair: only two reductions ran and both completed. It then exposed one
shared action-delivery minimum and one Monitor lifecycle defect. The fresh World contained a focused Wikipedia search
textbox with a legal `press_key` binding, while the soft-packed model view retained only the task-ranked Wikipedia
home link. After two empty `find_controls` calls, the model therefore bound `ArrowDown` to that visible unrelated
link. BrowserGym sent the action and captured a different fresh public World, but Monitor inherited the two discovery
recovery attempts, labeled the real receipt `not_sent`, and blocked it as attempt three because the semantic key
postcondition was mechanically unknown.

The converged action minimum no longer chooses between the two known counterexamples. On ordinary turns TurnPacker
hard-admits one task-ranked target and the first direct focused target, then uses the soft target for optional breadth;
an explicit discovery result still hard-admits its complete bounded route set. Direct focus precedes same-container
siblings inside the existing interaction inventory. If the provider hard capacity cannot hold both small ordinary
anchors, packing fails typed instead of guessing one. Monitor now derives recovery `dispatch` from the typed receipt,
keeps ineffectual same-World actions in the episode, and starts a new same-World episode only when a causal GUI
dispatch reaches a changed fresh public World. No second ranker, action authority, state machine, or projection was
added. Task266 run18 remains failed pre-repair evidence; run37 is the later accepted live witness.

Task266
[`run19`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run19/run.json) crossed the action-minimum,
stable-navigation, and Monitor lifecycle repairs. All 30 policy decisions were valid; 12 GUI requests were dispatched,
each acquired a fresh World, and the one control-stall recovery at step 20 was cleared by the causally changed World at
step 21. There was no stale binding, invalid argument, false `not_sent`, or Monitor terminal decision. The run instead
ended at `turn_budget_exhausted` while the public task still reported `loop_budget.max_turns=100`.

The conflicting limit came from `CoreAgentLoop.initialize`: it took the minimum of the TaskGoal budget and
`EpisodeMonitor.profile.max_policy_decisions=30`. This made a no-progress observer a second total-budget authority and
counted zero-dispatch `read_region`, `search_page_content`, and `find_controls` decisions against that hidden cap. The
owner repair removes total decisions from `AgentLoopProfile`; `TaskGoal.loop_budget.max_turns` is now the only total
turn budget installed in `RunState`. The Monitor profile contains only its same-World observation-stall threshold and
the number of alternate recovery retries, and that retry field now drives the existing bounded transition instead of
being dead configuration. This removes duplicated authority; it does not special-case WebArena or raise an arbitrary
case threshold.

Run19 also falsifies closure of the current checkpoint scheduler independently of the terminal-budget defect. Across
30 turns it invoked the reducer 14 times: seven calls timed out at ten seconds, while only four accepted replacements
became visible checkpoints. Because scheduling treats every successful-shaped read/search result as uncovered
knowledge even when the reducer intentionally cites no durable fact from it, irrelevant or empty results remain
permanently uncovered and retrigger reduction. The reducer also receives read/search evidence but ordinarily omits
the action-observation trajectory; it therefore promoted the ambiguous `relation/2176999 -> Not Found` episode into
a durable claim that the relation ID was invalid even though the ActionPolicy had explicitly noticed that the result
URL itself supplied the ID. This is context pollution and excess latency, not a World, cursor, Monitor, or dispatch
failure. This pre-repair witness motivated the direct Harness owner contract above; live closure still depends on the
fresh post-repair run rather than the provider-free gates alone.

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

ordinary packed action minimum
-> one task-ranked target + one direct fresh focused target

remaining task-ranked + focus-container routes
-> optional bounded model-visible breadth

find_controls(query)
-> bounded current E-ref matches when the visible prefix is insufficient
```

Neither focus nor the ranker is entitled to displace the other ordinary anchor, and neither can remove a legal current
action from the resolver. A syntactically valid but unavailable
or stale E-ref fails as a typed grounding gap before Binder/Executor.
Monitor also renders recovery from the typed producer: action-discovery loops tell the model to use a returned control
or materially change route, while an exact read/search replay points to the same tool's `next_cursor`, a different
relevant region, `find_controls`, or browser navigation. No new action authority, retrieval index, cursor type,
history store, recovery state, or model role was introduced. Run5 remains failed pre-repair evidence; a fresh live
witness is required.

Task266 run6 live-verified that the intended `Portland, Maine` result remained callable outside the bounded
presentation prefix: the model typed the query, submitted it, used `find_controls`, activated the exact current `E2`
route, and read the article infobox containing `43°39′36″N 70°15′18″W`. It then tried to navigate to the next source.
Although the model-visible catalog contained `goto`, its schema still required an undisplayed current browser-context
ref. The compact World showed only `[R1] Browser navigation`, so the model searched for an address-bar control. The old
query matcher expanded long tokens with four-character prefixes/suffixes, causing `navigation` to collide with large
numbers of unrelated page controls. Monitor correctly blocked the resulting discovery/read loop after nine policy
calls; run6 is failed pre-repair evidence, not acceptance.

The owner contract now follows BrowserGym's published action shape: browser primitives resolve the unique current
browser-context action without a public target argument, while page primitives continue to resolve an explicit
current `E-ref`. `find_controls` remains an optional current-page lookup and uses bounded literal word/phrase matches,
not stemming, prefix/suffix expansion, fuzzy recall, BM25, dense retrieval, or a benchmark-specific vocabulary. See
[BrowserGym action space](https://browsergym.readthedocs.io/latest/core/action_space.html) and
[AgentOccam](https://arxiv.org/abs/2410.13825). A fresh authorized live witness is still required.

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

Within one repeated item, the same producer joins adjacent stateless AX `StaticText` fragments into one ordered text
block and removes only an exact accessible-label echo immediately following an interactive element. It does not drop
links, controls, state, fields, record order, or completeness metadata. This is representation compaction at the
ToolResult owner, not retrieval, summarization, or another evidence projection.

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

`find_controls(query)` applies one deterministic explicit-query filter to the complete current `ActionSpace`, then
returns only bounded matching routes. For each candidate, tokens already expressed by its real role/operation describe
the requested control kind; remaining query terms must overlap its public label or discriminative local functional
path. Tokens shared by every page-control path are structural context and cannot establish candidate membership.
Target-term coverage orders the matches, while the model still chooses among the bounded relevant set. Focus and viewport break
otherwise equal ordering; they do not turn unrelated controls into matches, and the remaining ActionSpace is not
appended behind the query result. It has no generic continuation tool and no private public-result inventory. If
matching routes exceed the page bound, the model issues a narrower natural-language query. Action discovery never
executes a control and never turns readable `N/F/R` refs into executable `E` refs.

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

Within the BrowserGym boundary, the action target page before dispatch owns only dispatch/navigation observation.
After `environment.step`, BrowserGym's current active page owns every field of the causal post-state: stability wait,
URL, DOM/AX/screenshot acquisition, and private physical-property enrichment. Tab focus/open/close therefore changes
the observation owner atomically rather than joining facts from two pages.

Browser-global navigation uses that same route. When the caller explicitly selects a BrowserGym web-navigation
profile (the WebArena runner does so), the adapter projects one current `browser_context` subject and the official
BrowserGym primitives
`goto`, `go_back`, `go_forward`, `new_tab`, `tab_focus`, and `tab_close`. `tab_focus` is offered only with a current
alternative tab; its public schema accepts a non-negative index and the current resolver enforces the exact available
tab domain. The same compact current World renders `browser_context`, `viewport`, and `focused_context` from the
non-entity action subjects already present in Actor World, including the public active-tab and tab-route state, so the
model can choose dynamic parameters without a browser-only observation channel. The other actions are offered by the
profile and validated by their ordinary schemas. MiniWoB receives no browser-global additions. These are ordinary ActionSpace options that
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
policy invocations, including the fresh-World prompt that belongs to each turn. It does not invent a parallel history
type or keep a second pending exchange in `ObservationDeliveryStore`.

The physical next request must contain one or more completed proposal/result exchanges:

```text
zero or more completed:
  assistant ToolCallPart(call_id=A)[, ToolCallPart(call_id=B), ...]
  -> ToolReturnPart(call_id=A, content=owner_result)
  -> ToolReturnPart(call_id=B, outcome=failed, content=not_executed)
then current pending:
  assistant ToolCallPart(call_id=X)[, exact unselected proposals, ...]
  -> ToolReturnPart(call_id=X, content=current_committed_result)
  -> same-ID failed returns for unselected proposals
-> fresh current context
```

Each call ID occurs in exactly one call/result pair. The Runtime executes only the first proposal; the other exact
proposals remain visible long enough for PydanticAI to close them as not executed, but they never become an execution
queue. The next ActionPolicy call alone decides whether to reissue one after seeing the fresh World. PydanticAI
Harness performs pair-safe semantic compaction before provider invocation only when the complete canonical request's
existing admission breakdown reaches pressure. Neither the provider's cumulative usage anchor nor the current-World
soft target is treated as history capacity. Before that pressure test, the same history owner retains one task/plan
anchor and removes every historical World prompt. This structural projection does not change responses or call/result
pairs. Harness then replaces an expired prefix
with one historical `SystemPromptPart` summary and retains the newest pair-safe token-bounded suffix exactly. Summary
failure preserves raw history and lets the existing hard-capacity gate fail closed. The unresolved response and all
its calls remain present. A terminal decision consumes the last results and clears transport history so it cannot leak
into another episode.

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
| task anchor, historical-World removal, typed call/result history, correlation, and Harness compaction | PydanticAI boundary | Store, Workspace, Monitor |
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
- current typed control feedback;
- at most one Harness-produced, visible, non-authoritative historical summary;
- bounded completed owner-produced `ToolCallPart/ToolReturnPart` pairs, including same-ID failed returns for proposals
  not selected for execution, plus one task/plan anchor. Harness additionally preserves its newest exact pair-safe
  suffix, including `ThinkingPart`; only the current request supplies a World prompt and image.

The boundary first persists each accepted model response exactly, including `ThinkingPart`, ordinary text, provider
reasoning metadata, and all tool proposals. The response stays exact while its ToolReturn is pending. On later turns,
private thinking can expire only after closure and only when the same response already has a public text conclusion;
tool-only thinking remains until Harness can summarize it. Raw ActionPolicy and compactor provider exchanges remain
exact in Trace. This is same-actor history projection and semantic compaction, not Runtime fact authority or Workspace
memory. ActionPolicy responses may contain provider-native optional reasoning/text, but they are not instructed to
emit a progress artifact per step. Harness alone replaces an expired pair-safe history prefix with one cumulative
summary under its existing low-frequency pressure schedule; no Runtime progress reducer is present.

The benchmark runner registers the already frozen `WA_W2_COHORT_CASES` as the formal `webarena-verified-w2` suite.
This is benchmark composition only: every case reuses the same BrowserGym environment, ActionPolicy, GoalCompiler,
Runtime, native evaluator, and acceptance metrics as W1b; cohort identity never reaches production Agent behavior.

`TurnPacker` budgets the already-compacted history but does not summarize, edit, or rebuild ToolReturn content.
Harness removes only a pair-safe expired prefix and produces the one replacement summary. The bridge verifies that the
unresolved call suffix is unchanged and restores raw history on any summary failure. No dedicated summary model is
required initially; Harness reuses the configured provider through the existing Pydantic boundary.

`ObservationDeliveryStore` now retains only:

- a bounded sequence of local-result digests used for Monitor novelty/repetition.

It is owned by `RunState` and is absent from `AgentContext`. It does not retain public result bodies, result prefixes,
result cursors, action-query inventories, provider pending calls, or continuation capabilities, and it never retains
or projects GUI effects.

`AgentWorkspace` keeps bounded semantic receipts and activity summaries. It has no working-fact inventory and does not
receive exact local-result bodies. `EpisodeMonitor` consumes typed `InformationDelta` and bounded digests; it cannot
decide how a ToolReturn is serialized or make information persist in model context. Control discovery is capability
lookup, not task evidence, so `ObservationDeliveryStore` emits no novelty delta for it. Monitor allows one same-World
discovery step and recovers on the second consecutive discovery. In addition, the same Monitor keeps at most sixteen
ref-free public signatures for dispatched GUI attempts and recognizes every exactly repeated suffix representable in
that window across fresh Worlds. Candidate periods are derived from the actual window length rather than a second
semantic threshold. Local read/search steps without new public information do not erase that effectful-action sequence. The
first occurrence emits the existing typed `STATE_OSCILLATION` recovery; partial continuation retains that identity,
and recurrence of the same phase-independent cycle blocks. Typed `NEW_INFORMATION` or detection of a different cycle
replaces it. A cycle is sequence-level feedback, so Monitor does not incorrectly blacklist the last action that
happened to close it. This bounded operational detection never reads TaskGoal, GoalPlan,
ToolReturn bodies, URLs, task IDs, or site names. The outer episode step limit remains the generic long-loop fallback.

## W2 Task267 delivery and rejection convergence

The first frozen W2 Task267 run is a failed pre-repair witness, not an accepted benchmark result:
[`run1`](../evidence/live/w2-task-267-deepseek-v4-flash-20260826-run1/run.json) ended after 33 ActionPolicy calls with
`policy_failure_code=tool_grounding_gap`, no STOP, and no native evaluation. The model had already recovered Acadia's
relation ID and reached the correct OpenStreetMap page. Its final fresh World contained one focused search textbox
whose current verbs were `type_text` and `press_key`, but route-oriented delivery spent both the task-ranked and focus
minimum on separate routes for that same E-ref. The compact observation consequently printed the same target twice
and omitted a different useful control. The model proposed `activate` on the textbox; the PydanticAI bridge then sent
that already parsed semantic mismatch to representation repair, which repeated the call and terminated the run.

The repaired contract keeps one authority for each concern:

- complete current `ActionSpace` plus the Catalog's private resolver table own all executable
  `(operation, target[, destination])` routes;
- `ActionDeliveryPlan` is presentation only. Every admitted prefix groups selected private routes by target and emits
  one public target descriptor with the union of all current verbs. Focus and task-ranked minimum groups use distinct
  target subjects, so a multi-verb focused target cannot consume both visibility anchors;
- a wire/schema failure still receives the one bounded representation repair. A schema-valid registered operation
  rejected by the current resolver with `tool_grounding_gap` instead becomes the existing `ToolRejectedResult` under
  the original call ID and is returned to the next ordinary ActionPolicy turn. Binder and Executor are not reached;
- BrowserGym environment authorization remains private. A rejected `goto` now reports the precise typed
  `NOT_SENT/destination_outside_environment` result and permits ordinary reselection, while malformed parameters
  remain `invalid_parameters`.

No World projection, history/cursor path, Monitor rule, fallback action, URL recognizer, task branch, second catalog,
or alternate Runtime loop is added. Provider-free gates cover every admitted delivery prefix, multi-verb target
coalescing, Catalog independence from visible-prefix size, same-call rejection pairing through a second Recording
FunctionModel turn, and zero-dispatch URL-scope rejection.

The first post-repair launch,
[`run2`](../evidence/live/w2-task-267-deepseek-v4-flash-20260826-run2/run.json), failed before Agent construction with
`environment_factory_exception`: an unrelated top-level package installed into the dedicated BrowserGym virtual
environment had upgraded `beartype` to `0.22.9`, conflicting with `libwebarena==0.0.5`'s declared
`beartype==0.12.0`. It made zero model calls and zero executions, so it is an environment diagnostic rather than an
Agent counterexample. Removing that unrelated package and restoring WebArena's declared version made the unmodified
environment factory importable again.

The subsequent authorized
[`run3`](../evidence/live/w2-task-267-deepseek-v4-flash-20260826-run3/run.json) kept Agent code at commit `f20712bc`,
completed in 41 single-call policy turns and 18 GUI executions, and submitted Acadia relation `2176999` with OSRM
duration `01:32:00`. BrowserGym's native evaluator returned `verified_success`; the run recorded zero grounding gaps,
representation repairs, fallbacks, waits, invalid tool arguments, and multiple-call responses. This closes the live
Task267 witness for the exercised delivery path. It does not establish stability across the remaining frozen W2
cohort.

## W2 Task97 generation-local reference convergence

The first untouched Task97 run crossed both Task267 repairs: one current-Catalog semantic mismatch returned the
existing same-call `ToolRejectedResult`, and one restricted destination returned
`NOT_SENT/destination_outside_environment`; both reached the next ordinary policy turn without representation repair
or browser dispatch. The run then identified MIT as the 2019 SCImago target and selected its Wiki result. Construction
of the resulting fresh World failed before the next step with `ValueError: public reference capacity exceeded`.
[`run1`](../evidence/live/w2-task-97-deepseek-v4-flash-20260826-run1/run.json) therefore records
`failed / harness_projection / case_projection_failed` after about 441 seconds. Its zeroed aggregate metrics are the
harness's projection of an absent CoreLoop result; the exact trace retains 50 completed policy steps and the owner
exception.

This reopens the same generation-local identity subsystem that Task266 run3 exercised, but at a different cardinality
boundary. `WorldObservation` and the lossless Actor projection admit the complete current finite target/structure
inventory, while `CanonicalPublicWorldProjection` also assigns public refs to canonical facts and current public
labels. `PublicRefCodec` nevertheless imposed an independent four-decimal-digit maximum. The Task266 alias repair
removed duplicate target/structure identities but could not make every later valid page fit that unrelated ceiling.

The positive contract is one generation-local namespace over positive ordinals:

```text
one accepted finite current World
-> one deterministic E/N/F/R ordering of its supported public records
-> every generated ordinal is representable

model-supplied E/N/F/R ref
-> exact current Catalog/Manifest resolution
-> unknown ref returns typed grounding rejection
```

`PublicRefCodec` now owns both the anchored schema pattern and the reusable token pattern and no longer imposes a
smaller cardinality than its source World. History sanitization, benchmark fixtures, and test recorders consume that
one grammar instead of embedding four-digit variants. This does not make refs durable, expose private IDs, widen a
current Catalog, or change World, evidence, cursor, Binder, Executor, BrowserGym, Monitor, or harness control flow.
A full-owner test projects 10,001 semantic targets, linked structure records, and public-label facts losslessly;
Catalog tests separately prove a well-shaped `E10000` absent from the current resolver still fails with
`GROUNDING_GAP`.

Task97 run2 crossed that identity repair, but timed out after 60 policy calls, 23 observations, and 22 valid GUI
executions without reaching STOP or native evaluation. This reopened the earlier large-page claim at a lifecycle the
Task266 replay had not exercised: one large fresh World followed by several policy and `find_controls` turns. The
27.2-second Task266 measurement proved one construction chain, but did not prove that the resulting derivations were
retained for the lifetime of that observation.

The trace's final World contains 11,766 targets, 4,083 bindings, and 12,404 structure nodes. Exact replay showed two
shared mechanisms. First, `WorldDeliveryIndex` looked up source order by scanning the complete structure for every
candidate and repeated-item comparison; `_source_order` ran 618,890 times and consumed about 73.4 of 78.6 profiled
seconds. Second, transition projection and later action discovery could independently reconstruct that index and the
lossless model/grounding/actor projections, while `StepResult -> RunState` discarded the already constructed
after-World index.

The positive generation-lifecycle contract is now:

```text
fresh World + current ActionSpace
-> one source-order map per source
-> one WorldDeliveryIndex + canonical projection + observation context projection
-> same-World policy/read/search/find turns reuse those immutable derivations
-> next fresh World atomically replaces them
```

`WorldObservation` remains the only current environment authority. `ObservationContextProjection` is a disposable,
non-serialized bundle of pure derivations keyed by the exact observation, ActionSpace, canonical lineage,
capabilities, and Runtime controls; it is neither another World nor a progress or execution state machine.
`WorldTransitionProjector` accepts the exact before/after indexes already owned by the transition, and `StepResult`
carries the after index into `RunState`. Action discovery consumes the current context's index and grounding instead
of rebuilding them.

Source-order lookup is now a single O(N) map per source. On the exact run2 World, the full 4,083-action replay retains
all 644 functional regions while `WorldDeliveryIndex` falls from about 71.9 to 1.7 seconds. Canonical projection takes
1.7 seconds, the one-time static observation projection 2.7 seconds, and a subsequent same-World context turn 2.2
seconds. No page cap, task/site rule, VLM, cursor, evidence path, fallback, retry, or alternate observation was added.
Task97 remains empirically open until a fresh run crosses this repaired lifecycle and reaches native evaluation.

Task97 run3 crossed the large-World lifecycle repair: the case completed in about 116 seconds with 29 policy calls,
12 observations, 11 executions, zero waits, zero grounding gaps, and zero representation repairs. It then exposed a
pre-existing contradiction in Monitor recovery semantics. The policy had already received one exact replay recovery,
made a different current-page discovery, and `find_controls("search")` returned the current Wikipedia textbox with
both `press_key` and `type_text`. The committed result was nevertheless changed to `blocked / control_stalled` before
the next ActionPolicy turn because `d7546ba4` had made every different no-information attempt increment the same
`recovery_count`; the third distinct attempt crossed `max_recovery_retries + 1` even though
`same_attempt_streak == 1`.

That counter is operational recovery phase, not a semantic plan budget. A different public attempt signature now
replaces the current recovery attempt and retains the same typed recovery feedback; it cannot cause `BLOCK` merely by
being the third distinct query, region, control lookup, or GUI route. The existing exact-signature branch still blocks
an immediately repeated attempt after recovery, typed prohibited-call rejection remains bounded, and the bounded
ref-free GUI sequence still blocks recurrence of a proven cycle. `TaskGoal.loop_budget` remains the sole generic total
turn bound. This is one Monitor-owner rule for every tool and action, not a `find_controls`, task, site, or result-shape
exception. Generated tests cover up to twenty distinct same-World attempts, and a CoreLoop vertical test covers
no-result recovery -> nonempty control discovery -> next ActionPolicy turn -> dispatch -> fresh completed World.
At that checkpoint Task97 remained empirically open: the repair only removed the premature Runtime termination and
did not claim that the model would choose the correct remaining research strategy.

The authorized post-repair
[`run4`](../evidence/live/w2-task-97-deepseek-v4-flash-20260826-run4/run.json) crossed that exact boundary at commit
`c0158be2`. It completed after 67 valid single-call policy turns, 24 GUI executions, 26 observations, one STOP, one
post-STOP capture, and one native evaluation. The native evaluator returned `verified_success`; the run recorded zero
waits, grounding gaps, representation repairs, fallbacks, invalid arguments, stale catalogs, or context-capacity
rejections. This accepts the exercised large-World lifecycle and Monitor recovery-handoff path. It does not close the
broader W2 cohort, and its 1,142,228 aggregate tokens remain an explicit efficiency target rather than a correctness
reason to alter the now-verified control contract.

Task265 run1 is a failed pre-repair witness for the provider envelope, not evidence that the single ActionPolicy needs
a Replanner. Its formal report records 60 valid policy turns, 19 GUI executions, 13 recovery calls, zero fallbacks,
zero grounding gaps, and timeout before STOP/native evaluation. The exact provider trace contains eleven deliberate
ActionPolicy attempts whose canonical profile requested enabled thinking, but whose physical DeepSeek settings and
telemetry reported disabled thinking with no reasoning content. The shared cause was confined to the canonical
provider conversion: `zhipu` and `aliyun` mapped the existing call profile into the SDK `thinking` field, while
`deepseek` silently omitted that mapping and inherited the model's non-thinking default.

The positive contract now has one owner and no new control path. `ActionPolicyReasoningPolicy` still selects ordinary,
deliberate, or representation-repair once per invocation; `CanonicalProviderEnvelopeBinder` maps that selected value
for every supported provider; PydanticAI translates DeepSeek's enabled value to its official wire setting and retains
typed reasoning beside the ToolCall in SDK history. Attempt telemetry derives reasoning presence/tokens from the same
typed response and normalized usage rather than hard-coding `false/0`. Provider-free wire, history-roundtrip, accepted,
and output-retry tests close the implementation contract. Task265 remains empirically open until a separately
authorized fresh live witness; Planner, Monitor, progress/history compaction, World, BrowserGym, and CoreLoop are
unchanged.

Task268 run1 is the fresh post-thinking witness and fails for a different, bounded contract gap. All twenty traced
deliberate physical ActionPolicy calls requested and received enabled thinking with reasoning content, so the prior
DeepSeek wire defect is closed on this path. The Agent followed its recovered OSRM strategy, obtained the exact biking
time `10:57`, obtained relation ID `2176999`, and in policy turn 77 explicitly converted the requested duration to
`10:57:00`. In that same response it nevertheless selected navigation back to an empty directions form merely to
re-verify the already supported value. The remaining 23 turns rebuilt the same route; turn 100 returned `Time: 10:57`
again, but the outer turn budget ended before another policy call could submit. Formal acceptance is false with 100
valid single-call policy turns, 22 executions, 23 observations, zero grounding gaps, zero representation repairs, zero
waits, zero fallbacks, no STOP/native evaluation, and 1,753,888 aggregate tokens.

This is not a missing-World, missing-ToolReturn, Monitor, cursor, or execution-path defect, and a second Replanner would
only repeat a conclusion the ActionPolicy already produced. The positive owner contract is instead: before further
observation or navigation, ActionPolicy submits when every requested output field has an exact supported value;
format conversion alone is not a reason to reopen a source. Harness compaction remains the only expired-history
semantic projection, but direct final-output values outrank transient controls, form contents, selected modes,
locations, and service restrictions in its bounded fact quota. Finally, expired-prose batching uses the recent raw
suffix input budget, independently of the 1,024-token summary output cap. Run1 made seventeen compactor calls because
those two units had been conflated. The implementation changes only the existing ActionPolicy prompt, Harness summary
prompt, and Harness schedule; it adds no Replanner, progress store, mutable plan, second evaluator, or Runtime branch.
Provider-free owner tests passed; at that checkpoint Task268 remained empirically open pending a fresh run.

Task268 run2 failed before any browser execution and exposes an independent representation-repair lineage defect.
The first real DeepSeek response called `search_page_content` with the valid `query`/`cursor` operands plus an
unsupported `region_ref`. The existing bounded repair correctly removed only `region_ref`, but—as every separate
provider response normally does—returned a new ToolCall ID. `_repair_preserves_rejected_semantics` incorrectly required
the repair response to reuse the rejected response's call ID, a behavior only the scripted test double provided. The
Runtime therefore reported `invalid_tool_arguments` after two accepted physical provider calls, one observation, zero
executions, and zero valid ToolCalls.

Call ID is wire lineage, not a semantic operand. The positive contract now preserves operation and every
schema-declared argument across representation repair, accepts the repair response's own provider-generated call ID,
and uses that same new ID for the pending PydanticAI exchange and subsequent ToolReturn. A vertical test uses distinct
initial and repaired IDs and verifies the accepted local-tool decision plus pending SDK history. No normalizer,
Catalog, resolver, ToolReturn projection, CoreLoop, or provider-specific branch changed.

Task268 run3 is the accepted post-repair witness at commit `966fe598`. Formal acceptance is true and the native
evaluator returned `verified_success` after 69 valid single-call policy turns, 25 executions, 28 observations, one
STOP, one post-STOP capture, and one native evaluation. The submitted result was relation ID `2176999` and biking
duration `10:57:00`. The run recorded zero invalid tool arguments and successfully crossed one real representation
repair with a new provider call ID. Harness compaction ran once rather than run1's seventeen times. Wall time fell from
about 585 seconds in run1 to 361 seconds, while aggregate tokens fell from 1,753,888 to 1,631,827. This live-validates
the exercised completion-priority, exact-output retention, expired-prose scheduling, and repair-call-lineage paths. It
does not by itself close the broader W2 cohort or the remaining aggregate-token efficiency target.

Task740 run1 is the first unseen frozen W2 witness after those repairs. At commit `1ee18bfa`, it completed the distinct
navigation workflow `Wiki destination -> Wiki origin -> OSRM directions -> STOP` with formal acceptance and native
`verified_success`. Its 29 valid policy turns made 11 GUI executions, seven bounded page reads, zero recovery calls,
zero waits, and zero grounding, stale-catalog, fallback, invalid-argument, or context-capacity failures. One initial
multi-call response crossed the existing single-action representation-repair boundary; the repaired first call used
normal provider lineage and the next ActionPolicy turn continued from its same-ID result. No later call repeated that
shape, and the Agent did not return to either Wiki page after the OSRM route was displayed.

This witness exercises the intended single authority chain without another progress, evidence, cursor, or replanning
path: official SDK history carries completed calls/results, fresh World carries current browser state, the one
ActionPolicy selects the next semantic action, and the native evaluator owns terminal success. Its approximately
216-second wall time and 706,384 aggregate tokens remain efficiency evidence rather than a correctness failure. One
unseen accepted case broadens the empirical surface beyond Task268 but does not yet satisfy the multi-case held-out
campaign exit criterion.

The post-run efficiency repair keeps that control path intact and changes only three existing owners. The repeated
record producer coalesces lossless AX text fragments and interactive-label echoes. The Catalog publishes the stable
registry parameter family for browser-context tools while the current private binding still validates exact tab
domains. The PydanticAI history processor removes every historical World before adding the one fresh current World,
and uses the 50% high-water / 15% minimum-reclaim / 30% target schedule described above. Offline replay of the exact
Task740 provider transcripts finds 100 stale historical World prompts (about 213k conservative tokens) and about 122k
additional conservative tokens removable from repeated ToolReturn AX wrappers. These disjoint reductions are a
43.4% lower bound against run1's 772,712 accumulated history tokens; they do not predict a live provider total or
claim a wall-time improvement.

The authorized post-optimization Task740
[`run2`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run2/run.json) at commit `e758adf9` confirms that the
bounded representation is active but is not a correctness witness. Although it made 44 policy turns rather than
run1's 29, formal prompt tokens fell from 702,419 to 629,414 and accumulated history tokens fell from 772,712 to
663,642. Provider transcripts report a 60.0% ActionPolicy cache-hit ratio rather than 49.5%, with uncached
ActionPolicy input falling from about 355k to 252k tokens. The identical initial World required 6,142 provider prompt
tokens rather than 9,282. These are efficiency observations across different trajectories, not an aggregate closure
or wall-time claim.

Run2 ended `blocked` before STOP because ActionPolicy retained both exact Wiki coordinate pairs but replaced their
source ordering with a presumed backend OSRM HTTP convention before entering them into the OSM GUI fields. No route
result was therefore produced. It then interpreted `active=false` as disabled even though the current E ref's verbs
and `find_controls` result made the control executable. Monitor emitted the expected control-stall recovery; the
deliberate DeepSeek response exhausted its bounded reasoning output without a ToolCall, which was a downstream typed
failure rather than the initiating cause. Prompt version `grounded-agent-context.v39` closes the two general
ActionPolicy contract ambiguities: exact GUI values retain their supported representation unless the task or fresh UI
requires conversion, and E-ref verbs—not `active`—own executability (`disabled=true` owns unavailability). This adds
no formatter, site rule, memory, cursor, or recovery path. A fresh live correctness witness remains required.

The authorized v39 Task740
[`run3`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run3/run.json) verifies those two repaired semantics:
ActionPolicy entered the Wiki coordinates into the OSM GUI in their supported `lat, lon` representation, treated the
returned controls as executable, produced the real route region `R9`, and read both pages of its 38 records. It did
not revisit the failed route strategy. The run nevertheless ended `failed` before STOP because the task's advisory
GoalPlan said that route details should be delivered in the final response. ActionPolicy allowed that advice to
override the authoritative navigation objective, classified the task as `RETRIEVE`, and attempted to serialize all
37 turn instructions into `submit_final_response`; the bounded 1,024-token ordinary response ended with truncated
tool arguments. Increasing that output cap would mask the incorrect finalization semantics. The remaining owner gap
is bounded to the existing GoalCompiler/ActionPolicy task boundary: a generic final-response envelope is not a user
outcome, GoalPlan must not turn it into one, and ActionPolicy must derive final response classification and requested
payload from TaskGoal rather than intermediate evidence or advisory plan prose. No World, history, ToolReturn,
Monitor, executor, or evaluator change is implicated; the final-response ToolSpec is the existing model-facing
projection of that output boundary.

At that checkpoint the post-run3 owner repair was implemented locally as prompt version
`grounded-agent-context.v40`, pending a fresh live witness later supplied by run6. The pinned BrowserGym
WebArena-Verified task appends its `FinalAgentResponse` schema to
the semantic intent inside one `goal` string. `WebArenaVerifiedFinalResponseCodec` now recognizes and removes only
that exact pinned suffix at the BrowserGym `external goal -> public instruction` conversion boundary; an absent
suffix remains a valid plain semantic goal, while a recognized but changed suffix fails closed. Consequently
`TaskGoal`, GoalCompiler, GoalPlan, and the model-facing task projection contain only the semantic instruction.

The same existing codec remains the sole final representation authority. Its bounded model guidance is derived from
the pinned upstream Pydantic schema and projected
directly into the existing `submit_final_response` ToolSpec, participates in Context/ToolCatalog identity, and is
never projected as a task objective, public input, progress item, finalizing turn, or Supervisor request. The tool
contract tells ActionPolicy to derive `task_type` and requested payload from TaskGoal rather than GoalPlan; Runtime
still applies the codec once before the existing STOP/native-evaluation path. Focused verification passes 440 tests
with 11 skips; the full suite passes 1,809 tests with 19 skips except for the pre-existing documentation-governance
failure caused by the unmaintained `docs/interaction-shell.md`. No World, history, cursor, ToolReturn, Monitor,
Workspace, evaluator, or additional model role changed.

The first formal post-repair attempt, Task740
[`run5`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run5/traces/webarena-verified-w2-task-740/trace.jsonl),
crossed that GoalCompiler boundary: the policy recovered both Wiki coordinate pairs, opened the OSM directions form,
filled both fields, and dispatched `Go`. The initial dispatch changed the identity-free World digest. The next 41
completed steps did not: both identity-free World digests and the screenshot SHA-256 remained identical, while OSM's
DOM reconstruction changed 583 public target identities and 1,042 identity-keyed facts on each capture. The policy
repeated the same `activate(E10)` response 43 times, and Monitor emitted zero recoveries. The run was deliberately
interrupted after 66 completed steps and is failed diagnostic evidence, not a benchmark result; an earlier `run4`
stdin/multiprocessing launch error never started a case and is not a witness.

This reopening has one causal explanation shared by outcome projection and Monitor. `PublicWorldDelta.changed`
correctly represented complete identity/fact churn, but `ProductionActionOutcomeProjector` promoted any such churn to
`ObservedChange.CHANGED`; Monitor then treated that typed outcome as an operational effect and cleared the exact-action
streak. Raw public identity/fact delta and identity-free World meaning are distinct existing views, not competing
authorities. `PublicWorldDelta.semantic_changed` is now derived solely from its existing before/after semantic
digests. Action outcome projection, visual evidence applicability, model-visible step projection, and Workspace
no-effect classification consume that one derived meaning, while Trace continues to retain the raw identity counts
and now reports the semantic-change bit explicitly. A semantically equivalent target reappearing under a new public
ID is compared by identity-free target semantics; it is not action evidence. Monitor itself gains no state, model,
retry, or task rule: after a true effect it still resets, while two subsequent same-semantics/same-screenshot attempts
reach its existing recovery path.

This is the thin ReAct boundary used by current GUI-agent work: a grounding ID belongs to one observation, and the
next observation/screenshot verifies the preceding action. UI-TARS-2 models each step as thought/action/observation;
AgentOccam improves a single policy by aligning and compacting observations/actions rather than treating DOM identity
allocation as progress; Agent S2's optional reflection likewise evaluates the latest screenshot trajectory. None
requires a second World, Replanner, evidence ledger, or cursor for this failure. Generated identity-rekeying tests and
the full BrowserGym/Agent/Evaluation owner surface protect the repaired invariant. The focused owner surface passes
`551 tests / 3 skipped`; the full suite passes `1,813 / 19 skipped` with only the previously recorded unrelated
`docs/interaction-shell.md` governance failure.

The fresh post-repair Task740
[`run6`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run6/run.json) closes this reopened invariant with
native benchmark evidence. The first coordinate-result activation changed the page; the next equivalent activation
was typed `UNCHANGED`, and the following repeat reached the existing `control_stall` recovery instead of resetting
Monitor on DOM identity churn. Six recovery turns remained ordinary ActionPolicy calls with typed feedback; no second
policy or control loop was involved. The same policy then found the browser's directions control, filled both
coordinate fields, activated `Go`, read the route result, and submitted `NAVIGATE/SUCCESS`. The native evaluator
returned `terminal_success / verified_success`; the suite reports `accepted=true` with no acceptance errors. This
fresh witness restores closure for identity-free action-effect projection and Monitor delivery, while broader
held-out benchmark coverage and efficiency remain separate non-closed concerns.

The subsequent provider/history repair stays inside the existing PydanticAI history owner. Initial ActionPolicy
requests remain `tool_choice=auto`, so one response may carry public progress plus one call. Only PydanticAI's bounded
output-validation retry uses `thinking=false + tool_choice=required`, matching DeepSeek's wire constraint. After a
same-ID ToolReturn closes an older response, private thinking may expire only when that response retains its own public
text conclusion; pending and tool-only reasoning remain exact. Task740
[`run7`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run7/run.json) verified the temporal ordering in the
physical transcript and completed native evaluation in 28 policy calls and 403,528 total model tokens. Task740
[`run8`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run8/run.json), after the final-response owner repair
below, independently completed native evaluation with zero waits, fallbacks, or grounding gaps. No progress state,
second policy, memory, or alternate delivery path was introduced.

A held-out Task759 witness then exposed a representation-owner omission, not another task-planning path. The Agent
completed a Boston-to-NYC route but submitted `MUTATE`, because the model-facing codec listed the available task-type
enum names without the installed WebArena-Verified schema's definitions. `WebArenaVerifiedFinalResponseCodec` now
derives bounded task-type/status guidance from that pinned upstream Pydantic schema and projects it through the same
existing `submit_final_response` ToolSpec. The generic ToolSpec description bound is 1,024 characters so the composed
upstream contract remains bounded without being truncated; one integration test crosses codec, Context, Catalog, and
ToolSpec construction. Task759
[`run3`](../evidence/live/w2-task-759-deepseek-v4-flash-20260827-run3/run.json) then submitted
`NAVIGATE/SUCCESS` and received native `verified_success`. This changes neither TaskGoal nor GoalPlan semantics and
adds no finalizer, evaluator rule, benchmark branch, or second owner.

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

## SOTA alignment checked 2026-08-25

Current primary sources converge on a thin loop rather than a result-conservation subsystem:

- [BrowserGym/AgentLab](https://arxiv.org/abs/2412.05467) defines the research interaction as current observation ->
  agent action -> environment step -> next observation, with BrowserGym delegating browser execution to Playwright and
  exposing standardized observation/action spaces. BrowserGym preserves raw DOM/AX observations with minimal
  alteration; AgentLab applies configurable token fitting at prompt-component/page scope rather than silently clipping
  every readable node at a control-label limit. This project reuses BrowserGym's installed `nav`/`tab` primitives
  instead of inventing navigation tools.
- BrowserGym's official [BID action functions](https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/core/src/browsergym/core/action/functions.py)
  resolve the current element through Playwright, whose
  [Locator/actionability contract](https://playwright.dev/docs/actionability) re-resolves the DOM and checks whether
  the requested action can actually run. The project therefore retains only semantic stale protection needed to
  prevent acting on a changed subject; it does not make CSS, color, geometry, or a copied availability snapshot a
  parallel physical-action authority.
- [AgentOccam (ICLR 2025)](https://proceedings.iclr.cc/paper_files/paper/2025/file/f2c6e459b95694a24ac69c469a4ee746-Paper-Conference.pdf)
  reports that aligning the observation and action spaces—removing redundant structure while retaining informative,
  usable page elements—substantially improves a plain single web agent without extra roles or online search. The run5
  repair follows that boundary: it changes which already-legal current route is visible first; it does not add a
  planner, retriever, or Runtime semantic rule.
- [UI-TARS-2](https://arxiv.org/html/2509.02544) formalizes recent high-fidelity working memory plus semantically
  compressed episodic intentions/outcomes. Its ordinary control remains one ReAct policy; the verifier described in
  the report is primarily a training-reward mechanism, not a second online Runtime authority. This project uses the
  thinner inference-time equivalent: recent exact SDK exchanges plus the latest explicit same-policy progress
  checkpoint.
- [Agent S2](https://arxiv.org/html/2504.00906) is the explicit heavier alternative: a Manager updates subgoals after a
  Worker completes each one. That is a deliberate Manager/Worker architecture, not a Monitor feature. This project
  retains its declared single ActionPolicy and static GoalPlan rather than partially importing that hierarchy.
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
- PydanticAI's current [`Agent.model_settings`](https://ai.pydantic.dev/api/agent/) contract accepts a `RunContext`
  callable before every physical request and exposes the output-validation retry count. The ActionPolicy therefore
  keeps its ordinary thought+action response shape and strengthens only a rejected text-only retry; it does not need a
  parallel progress channel or custom provider loop.
- [VLAA-GUI](https://arxiv.org/html/2604.21375) reports loop breaking as a post-action trajectory check that feeds one
  strategy-change directive back to the same Manager policy. The bounded `EpisodeMonitor` is the deterministic,
  provider-free subset of that pattern: exact ref-free cycle recurrence only, without importing its extra judge model.
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
10. a unique semantic/structure occurrence has one public identity, every accepted finite World public record has a
    representable generation-local ordinal, every accepted World fact/artifact remains resolvable, and large-World
    derivation does not rescan complete entity/action inventories per item.
11. queried control discovery returns only query-qualified current routes, and same-World discovery loops cannot create
    information novelty that clears Monitor.
12. WebArena-family browser navigation is published only through the existing ActionSpace/BrowserGym route, while
    MiniWoB remains unchanged.
13. proactive SDK history processing preserves exact call/result pairs and unique model conclusions across tool-only
    turns without requiring a per-step progress artifact, and a partial PageMap remains aggregate-bounded and
    recoverable through the existing read tools.
14. dispatched GUI attempts have one bounded ref-free Monitor history; every repeated cycle representable in that
    window recovers once and blocks only on recurrence. Different public attempt signatures retain recovery feedback
    but never accumulate into a hidden semantic-attempt budget; exact replay still blocks after one recovery, and the
    TaskGoal turn budget remains the only total-loop bound.
15. every current non-entity `InteractionSubjectKind` present in Actor World reaches the same compact observation;
    adding an action for an existing kind does not require a renderer or history-path change.
16. BrowserGym element currentness consumes only the selected interaction offer's declared semantic fields and private
    binding domain; unrelated presentation drift reaches Playwright, while a typed pre-dispatch stale result performs
    one fresh capture, zero replay, and returns to the same ActionPolicy.
17. when a BrowserGym action changes the active page, post-action stability, observation, private enrichment, and
    transition `after_url` all use that one current page; the pre-dispatch page remains only the navigation watcher.
18. Monitor findings are derived in one target pass plus one fact pass; same-object local tools build no transition
    region index, reuse the current RunState index, and commit one already-produced delivery transition.
19. Trace persists each full observation and exact provider attempt once, while step events contain bounded typed
    outcomes and transition lineage with honest truncation metadata rather than duplicate canonical Worlds.
20. BrowserGym open-tab titles and routes are paired by position into one current browser subject; title-only changes
    do not stale the binding, and navigation allowlists are not duplicated in the public World.
21. DeepSeek receives the declared output budget through its supported wire parameter, disabled thinking for
    ordinary/representation-repair calls, and enabled thinking for the existing deliberate recovery profile. The
    initial request uses `tool_choice=auto` so exact model text/reasoning can accompany one ToolCall, while only a
    text-only output retry uses `thinking=false + required`. A repeated provider violation still ends in a typed
    terminal failure, with no nested representation retry or historical response miscount, and Trace records the
    physical settings and returned reasoning observation of both requests.
22. GoalCompiler thinking control follows the selected provider capability, and ActionPolicy and Harness compaction
    receive one prompt-owned evidence-status rule without Runtime parsing summary prose into fact state.
23. Explicit control discovery cannot lose an exact label because the same token names another current operation, and
    exhausted output-retry tracing cannot count responses from the supplied official history as new physical calls.
24. SDK history exposes the current task/plan exactly once and no historical World/media prompts, while retaining
    model progress, calls, returns, exact pending/tool-only thinking, and the unresolved suffix; closed private
    thinking expires only behind its own retained public conclusion. The physical request supplies exactly one fresh
    World and current media.
25. Exact values that directly fill requested final-answer fields outrank transient execution setup in Harness
    compaction, ActionPolicy submits rather than re-verifying when all requested fields are supported, and history
    compaction requires the declared high-water plus minimum-reclaim hysteresis independent of summary output size.
26. A separate representation-repair provider response may own a new call ID while preserving the rejected operation
    and every schema-declared semantic operand; the accepted response and subsequent ToolReturn pair under that new ID.
27. Public identity/fact churn remains available as exact transition lineage but cannot become `semantic_change` or
    `ObservedChange.CHANGED` when both identity-free World meaning and screenshot are unchanged; repeated equivalent
    GUI attempts must therefore reach the existing Monitor recovery independent of target-ID reallocation.

These gates and the later Task27 run2, Task266 run37, and Task7 run2 live witnesses prove the bounded implementation
paths they exercise. They do not establish breadth or repeated-run stability across the broader held-out benchmark
campaign.

# Architecture

## Current status

The current production target is a thin, single-loop GUI agent. The former generic evidence-delivery system is no
longer part of the architecture: local tool results are not copied into a Store-owned public inventory, repacked as an
admitted prefix, or exposed through generic continuation tools.

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

### External interaction shell real-execution profile

Phases 0–2 of the separately packaged external interaction shell are now
implemented. `interaction_shell.api:app` remains fail-closed and the Demo
remains synthetic; real local execution starts only through
`interaction_shell.deployment_app:app`. Each Web session creates its own
TargetRuntime, PydanticAI ActionPolicy/history, Unified World environment,
BrowserGym browser context, public Runtime session handle, event epoch, and
per-session trace directory. The Shell manager retains only the opaque handle,
TTL, command lock/idempotency admission, and bounded conversation, and directly
forwards Runtime-owned `events(after)`.

The real BrowserGym witness found that BrowserGym 0.14.3's nominally global
synchronous Playwright cache cannot be shared by per-session owner threads. The
BrowserGym integration boundary now installs owner-thread-local driver access
at every cached BrowserGym import site before reset; browser contexts remain
independent, and closing one real session leaves the other alive. The deployed
TaskEvaluator consumes the surface-owned native task-state classifier with
fresh World lineage; benchmark code projects that same result into its legacy
benchmark types instead of owning a second classifier. Same-origin SSE declares
an identity, non-transforming, non-buffered response so asynchronous Runtime
events reach the Next.js UI incrementally.

A held-out local real-execution run opened one Web session, made one real
BrowserGym dispatch, captured two observations, terminated from native
`verified_success`, updated the Shell to `done` through SSE, accepted explicit
close, and completed application shutdown. The subsequent control milestone
adds one Runtime-private SQLite WAL checkpoint store: a cooperative pause first
closes policy/dispatch/history truth, then atomically commits the checkpoint and
pause-command outcome, and only then changes the sole `RunState` to `PAUSED`
and projects `checkpoint_id`. A failed commit rolls back both rows, reports
typed `pause_persistence_failed`, refreshes current World when execution was
active, and continues the original task revision. Checkpoints retain bounded
task/plan/run counters, last receipt, pending interrupt identity, official
PydanticAI history, and an opaque environment reference; they exclude complete
Worlds, Shell events/conversation, Viewer/trace projections, tasks, locks, and
clients. Reconnectable deployments can now hydrate that checkpoint under a new
event epoch, capture fresh World, and wait for explicit `ResumeRun`; a lost
environment fails typed rather than opening a replacement browser. Bounded
`ReviseTask` reuses the same cooperative pause, validates one complete
consecutive `TaskGoal`, revises the same environment, captures fresh World,
compiles one new GoalPlan, atomically commits revision `n+1`, and remains
paused. Runtime also owns revision command identity: the existing outcome row
stores a canonical complete-command digest plus bounded result/message, exact
retries replay before current-state validation, and changed payload under one
ID fails as `command_identity_reused`. Shell forwards complete revision
commands and only suppresses duplicate conversation turns; it owns no durable
revision result. Prior GUI effects still return
`effect_reconciliation_required`; Viewer, compensation, and takeover remain
unavailable. These deployment/control tests are not benchmark witnesses and do
not alter the reopened overall project status.

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
The latest repair keeps the generic BrowserGym browser profile unrestricted, while an environment may explicitly
provide a navigation scope. WebArena is the only current selector of that restricted profile: its runner reads the
official BrowserGym `ENV_VARS` URL set once and gives the normalized locations to the existing private browser-context
binding. World publishes only `navigation_scope=environment_restricted`, while the ordinary ActionSpace/Catalog keeps
the registry's generic HTTP(S) `goto` shape. BrowserGym execution checks the selected destination against the private
scope before `step` and returns the existing typed `NOT_SENT/invalid_parameters` outcome on rejection. There is no
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

- every accepted turn persists the SDK-produced fresh-World `UserPromptPart`, ordinary `TextPart`, `ThinkingPart`,
  provider metadata, every proposed `ToolCallPart`, and the next same-ID `ToolReturnPart`;
- only a canonical request whose existing `RequestAdmission` breakdown reaches 80% of effective provider input can
  trigger compaction. That same breakdown already counts SDK history, pending ToolReturn, fresh World, tools, and
  protocol overhead; read/search type, Monitor recovery, task revision, semantic novelty, and the provider usage
  anchor do not schedule another model call. The current-World delivery soft target is not a history capacity;
- Harness summarizes only a pair-safe expired prefix and keeps the newest pair-safe suffix fitting 12% of that history
  capacity at full fidelity. This token-bound tail adapts to variable-size GUI Worlds instead of assuming that eight
  messages are small. Its plain `SystemPromptPart` summary retains at most three completed user outcomes plus the
  current stage, eight task-critical verified facts, three remaining questions, one next intent, and two failed
  strategies. It does not retain an action-by-action log, old URLs, or stale current-state references;
- Harness 0.25's formatter does not render `ThinkingPart`. The history owner therefore maps accepted thinking to
  ordinary text only in the throwaway summarizer input, then restores Harness's preserved suffix from the exact
  official messages. Provider reasoning metadata and signatures are never rewritten in persisted or replayed history;
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

The existing PydanticAI boundary now supplies Harness a throwaway summary-only view in which completed, already
owner-bounded public ToolReturns are rendered in full, alongside the accepted reasoning already exposed there.
Harness still selects the pair-safe expired prefix and produces the sole non-authoritative summary; the bridge still
restores its preserved suffix from the exact official messages. The summary contract preserves a later explicit
ActionPolicy conclusion drawn from a completed result unless later trajectory content contradicts or retracts it,
and treats coverage/pagination as scope metadata rather than evidence that a returned complete record is absent.
Because Harness invokes the configured model directly rather than the canonical ActionPolicy envelope, that same
model now has a default 1,024-token, temperature-zero, thinking-disabled compaction cap; normal action and repair
requests continue to override it with their existing request-scoped role settings. No synthetic part enters canonical
history, and no checkpoint, fact store, cursor, Monitor trigger, scheduler, or second model state is introduced.

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
typed `NOT_SENT/invalid_parameters` before dispatch. Independently, every WebArena native
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
  `max_tokens`;
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

Overall project closure is still **open**:

- run19 live-validates stable navigation, action delivery, and the changed-World Monitor reset, but the single
  TaskGoal-budget repair requires a post-repair live witness;
- provider-capacity-triggered Harness compaction and document-scoped structural grounding require a fresh post-repair
  Task266 witness;
- Planner lexical admission still has a known gap.

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
added. Task266 run18 remains failed pre-repair evidence; a fresh live witness is required.

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
the requested control kind; remaining query terms must overlap its public label or functional path. Target-term
coverage orders the matches, while the model still chooses among the bounded relevant set. Focus and viewport break
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
soft target is treated as history capacity. Harness replaces an expired prefix
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
| bounded typed call/result history, correlation, and Harness compaction | PydanticAI boundary | Store, Workspace, Monitor |
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
  not selected for execution, plus the newest exact pair-safe suffix including fresh Worlds and `ThinkingPart`.

The boundary preserves each accepted model response exactly, including `ThinkingPart`, ordinary text, provider
reasoning metadata, and all tool proposals. Only the summarizer's throwaway input maps thinking to ordinary text
because Harness 0.25 otherwise omits it; persisted and replayed messages remain exact. Raw ActionPolicy and compactor
provider exchanges remain in Trace. This is same-actor semantic compaction, not Runtime fact authority or Workspace
memory.

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
discovery step and recovers on the second consecutive discovery. In addition, the same Monitor keeps at most six
ref-free public signatures for dispatched GUI attempts and recognizes repeated period-2/3 suffixes across fresh
Worlds. Local read/search steps do not erase that effectful-action sequence. The first occurrence emits the existing
typed `STATE_OSCILLATION` recovery; recurrence of the same phase-independent cycle blocks. Only a proven effectful GUI
transition or a causal dispatch that reaches a different fresh public World starts the next same-World no-progress
episode; an arbitrary same-World dispatch does not. This bounded operational detection never reads TaskGoal, GoalPlan, ToolReturn bodies, URLs,
task IDs, or site names. The outer episode step limit remains the generic long-loop fallback.

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
13. proactive SDK history processing preserves exact call/result pairs and exactly one latest cumulative progress
    note across tool-only turns, and a partial PageMap remains aggregate-bounded and recoverable through the existing
    read tools.
14. dispatched GUI attempts have one bounded ref-free Monitor history; repeated period-2/3 cycles recover once and
    block only on recurrence, without task-progress interpretation or a second policy.
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
21. DeepSeek receives the declared output budget through its supported wire parameter, and a text-only ActionPolicy
    response is retried once by PydanticAI before a typed terminal failure, with no nested representation retry.

These gates prove this bounded implementation. They do not close the BrowserGym transition without its post-repair
live witness, Planner lexical admission, or the broader benchmark campaign.

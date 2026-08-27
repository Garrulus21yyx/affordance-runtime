# Benchmark

## Current status

Task426
[`route-regression-run3`](../evidence/live/w2-task-426-deepseek-v4-flash-20260827-route-regression-run3/run.json)
is the current failed pre-repair witness for generation-local grounding. The run made 31 policy calls, 18 executions,
19 observations, and no STOP/native evaluation. A prior search ToolReturn exposed `E6` as `More results`; after a
fresh navigation World reused `E6` for an undelivered `Go` button, the model called `activate(E6)` while describing
the old link. Because Catalog resolver rows still came from every `complete_action` instead of the sibling
`DeliveryManifest`, Runtime legally but incorrectly bound the call to `Go`. This explains the wrong dispatch without
reopening BrowserGym execution, task context, Monitor, or cursor design.

The implemented repair makes manifest admission and callability identical. Generated zero/partial/full delivery
tests verify that compiled private action routes equal manifest routes, including destination actions; an omitted ref
of an otherwise offered operation now returns typed `tool_grounding_gap`, and its rejection feedback cannot reveal the
undelivered control or verbs through `complete_actions`. A same-World search-result test proves an
explicitly returned current E-ref/verb is first intersected with the current ActionSpace, added to the same manifest,
and then resolves normally. The environment-profile test also verifies that all six authorized browser-context
primitives survive the required base delivery together, without a URL/site branch. PydanticAI history tests preserve
call IDs, pairing, labels, factual results, current
grounding, and the unresolved suffix while removing refs/cursors/attached verbs from closed exchanges belonging to a
noncurrent World. Raw source messages remain unchanged. Focused action/catalog/BrowserGym/provider verification
reports 188 passed and 1 skipped; the direct delivery/history set reports 131 passed. A fresh authorized live witness
is still required, so broader benchmark status remains non-closed. The fixed BrowserGym Python full suite reports
1,827 passed and 19 skipped; its sole failure is the already tracked documentation-governance rejection of
`docs/interaction-shell.md`, not a product or grounding failure.

The first untouched four-case W2 batch after the Task740/759 witnesses is failed pre-repair evidence, not a closure
batch:

- Task424 blocked after 59 policy calls while repeatedly trying OSM Pittsburgh routes;
- Task681 blocked after 60 calls despite having identified `eriklindernoren/PyTorch-GAN`, 193 commits, the technology
  forum, and the exact post fields;
- Task672 blocked after 18 calls at the same Postmill create-post boundary;
- Task556 reached the GitLab Web IDE and extracted all 12 Nolan feature titles, but activated an IMDb link and received
  native terminal task failure.

Tasks 681/672/556 expose one observation/action-alignment reopening. In Task681 the fresh observation contained the
executable `Submit` link and `ActionPager` reported 32 visible actions out of 347 complete actions, while the physical
request admitted only the task-ranked `Forums` link and current focus. In Task556 `read_region` returned the exact
`Christopher Nolan filmography` text without its current executable ref. The existing literal `find_controls`
contract and Monitor repeat rejection both behaved as designed; neither can compensate for a projection owner that
drops the already-bounded current action page or splits readable text from its fresh grounding.

The implemented owner repair consumes the existing `base_actions` argument, hard-admits that bounded capability set
together with at most five task-ranked suggestions, and removes the duplicate complete-ActionSpace presentation
inventory. Read/search results now attach the existing current E-ref and verbs only to interactive targets they
actually return. The complete current Catalog resolver, `find_controls`, PydanticAI call/result history, cursor,
Monitor, Binder, Executor, and BrowserGym capture paths are unchanged. Focused property/vertical tests cover bounded
base-set hard admission, hard-capacity failure, permutation, destination routes, duplicate readable labels, and
same-World read-result E-ref execution. The live witness and fresh held-out results below validate the repaired
grounding invariant but keep the broader benchmark status non-closed for a separate provider-history recovery gap.

Post-repair Task681
[`action-grounding-run1`](../evidence/live/w2-task-681-deepseek-v4-flash-20260827-action-grounding-run1/run.json)
crosses the original witness and ends with native `verified_success`: 28 policy calls, 345,929 total tokens, zero
grounding gaps, zero waits, zero fallbacks, one STOP, one post-STOP capture, and one native evaluation. The model used
the current `Submit` action, filled the Postmill form, and published the requested technology post. The pre-repair run
had blocked at 60 calls and about 1.187 million total tokens.

Task672
[`action-grounding-run1`](../evidence/live/w2-task-672-deepseek-v4-flash-20260827-action-grounding-run1/run.json)
also crossed its old Postmill boundary, entered `/submit/gaming`, visited the required OneStopShop product, and
returned to the create form with zero grounding gaps. It then blocked after repeatedly reading the same first region
page instead of consuming the returned continuation; a deliberate policy response later exhausted its output budget.
This is a failed independent strategy/provider-recovery witness, not a failure of the repaired grounding invariant.

Fresh untouched Task426
[`action-grounding-heldout1`](../evidence/live/w2-task-426-deepseek-v4-flash-20260827-action-grounding-heldout1/run.json)
therefore keeps broader status non-closed. It correctly inferred Shanksville and executed the fresh Wikipedia search
textbox, but repeated `ArrowDown` instead of the offered `Enter`. Its first deliberate recovery used all 2,048 output
tokens as thinking and returned no ToolCall. The following calls then failed before provider dispatch because the
PydanticAI history still ended in the last accepted pending call while the immediate Runtime step was the typed
invalid response; the recorder also projected an historical response as a current attempt. These traces reopen the
ActionPolicy/provider-history recovery and transcript-accounting lifecycle, not observation projection. No new
projection or task-specific repair was inferred from the case.

The shared provider-history repair uses PydanticAI's own message and `run_id` identities. An accepted ActionPolicy
call may remain pending until its exact Runtime result is delivered, or it may be closed by that exact SDK request
when the following model output is rejected. In the latter state, the rejected response/retry prose is not retained,
the already-delivered ToolReturn is not requested from a later Runtime step, and the next fresh-World call continues
the same canonical SDK history. Failed-run transcript accounting filters by the current SDK `run_id` rather than
assuming the response retry allowance was fully consumed. No CoreLoop fallback, Workspace lookup, Store, cursor,
Monitor rule, or alternate retry path was added.

The vertical regression reproduces the live shape—one historical accepted response plus one current thinking-only
length response—then proves the next call succeeds with every earlier ToolCall paired to its exact ToolReturn. The
PydanticAI/history/request-admission focused set reports 97 passed; the fixed BrowserGym Python full suite reports
1,819 passed and 19 skipped, with only the pre-existing `docs/interaction-shell.md` governance failure. A Task426
same-witness rerun and another fresh held-out case remained required before broader closure.

Task426
[`history-recovery-run2`](../evidence/live/w2-task-426-deepseek-v4-flash-20260827-history-recovery-run2/run.json)
is the post-repair lifecycle witness but not a task-success witness. Three separate physical responses ended
`output_truncated`; later ActionPolicy calls still reached the provider, and the run recorded 81 valid calls, zero
grounding gaps, zero invalid arguments, and no recurrence of the old `invalid_response -> internal_error` history
dead end. The policy navigated from Wikipedia to OSM, searched Shanksville, and repeatedly activated the exact current
`Shanksville, Somerset County, 15560, United States` result. That result consistently routed to
`/relation/189076`, where the current site returned `Not Found`; the policy returned to search and retried the same
failed route instead of abandoning it. The run blocked after 84 policy calls, 1,556,528 total tokens, two final typed
invalid responses, and no STOP/native evaluation. Canonical history recovery is live-verified; broader benchmark
closure remains open for long-horizon failed-route convergence and a new untouched task-success witness.

The provider-free failed-route repair now recognizes the first bounded ref-free `A -> ... -> A` GUI excursion as
typed `route_regression`, even when the visited branch produced new public text. It sends that mechanical fact through
the existing recovery feedback into one deliberate ActionPolicy call; Runtime neither judges task relevance nor
chooses the alternate route. The exact outbound replay is rejected before dispatch, one bounded fallback remains
available, and a different current route executes normally. Focused owner/consumer verification reports 331 passed
and 3 skipped; PydanticAI/grounded-tool verification reports 137 passed. This is implementation evidence only:
Task426 and one fresh held-out long task remain the live acceptance gate.
The fixed BrowserGym Python full suite reports 1,822 passed and 19 skipped, with only the pre-existing
`docs/interaction-shell.md` documentation-governance count failing.

The local benchmark Console foreground has been replaced with the agent-shell information architecture: a central
task/status thread, a verified read-only browser-frame pane, and a Labs workspace for launch configuration, bad cases,
raw evidence, and runner output. Focused Console verification covers bounded newest-first run summaries, public
activity projection and private-field exclusion, trace-root confinement and digest verification for browser frames,
desktop/mobile rendering, Labs navigation, and hidden-drawer focus isolation. No live benchmark was launched for this
UI change, so it contributes no new task witness and does not alter any benchmark acceptance or closure claim.

The thin tool-result/history cutover, accepted-response repair, owner-level action-discovery/catalog repair,
readable-AX completeness repair, single-current-World cutover, atomic PageMap/Manifest repair, and bounded post-action
recapture repair, and BrowserGym large-page liveness, viewport-grounded media, canonical public-identity, and linear
fresh-World projection repairs are implemented. The current convergence patch additionally filters control discovery,
publishes only profile-supported BrowserGym navigation, detects same-World discovery loops, retains official SDK
history, bounds the PageMap directory while retaining the complete recoverable region index, orders the ordinary
model-visible action minimum with both one task-ranked target and one direct fresh focused target, and gives Monitor
producer-specific recovery guidance for action discovery versus local-result replay. The current owner repair further
decouples action callability from that prefix: stable registry action schemas accept current E-ref syntax and the
existing complete current `ActionSpace` resolver performs exact route/domain validation.
The post-Task740 efficiency repair changes no control path: repeated read records fold adjacent AX text fragments at
their producer, browser-context tools expose the registry's stable parameter family while private current bindings
validate exact domains, and PydanticAI history removes every historical World before supplying the one fresh current
World. Closed private reasoning expires only behind its own retained public conclusion; pending/tool-only reasoning,
public progress, call/result pairing, semantic values, and current-World handles remain exact; expired closed
exchanges retain semantics without generation-local handles. Harness uses an 80% complete-request capacity arm plus a
50% history high-water arm gated by a 15% minimum-reclaim batch; accepted compaction targets 30% history and retains a
12% exact pair-safe suffix. Initial ActionPolicy requests remain `tool_choice=auto`; only the bounded PydanticAI
output retry uses `thinking=false + required`. No memory, replanner, result-specific scheduler, or second
current-state channel was added.
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
The repository-wide mypy command still reports its pre-existing baseline errors in unchanged modules.

The latest full code suite reports `1817 passed / 19 skipped`; its sole failure is the pre-existing tracked
`docs/interaction-shell.md` exceeding the repository's five-maintained-document governance set. That document was not
modified or removed; every other collected test passed. The current final-response/history owner surface reports
`426 passed`; the PydanticAI integration file reports `80 passed`. Ruff, compileall, and `git diff --check` pass.

Overall project status remains **non-closed at the broader held-out benchmark level**. The former named implementation
gaps are stale after later evidence:

- Task266 run37 is accepted after the TaskGoal-budget, stable-navigation, action-minimum, Monitor lifecycle, and
  document-scoped grounding repairs;
- Task7 run2 accepts two live age/size-triggered stable-only Harness compactions and completes native evaluation;
- C12 already removed privacy-by-field-name TaskGoal filtering and current generated tests conserve route-shaped
  public business keys through GoalCompiler and ActionPolicy;
- Task27 run2 live-verifies the one bounded read-only recapture after `acquisition_unstable`; ordinary stable
  acquisition and typed stable-navigation paths are covered vertically and exercised by accepted runs;
- the first unseen frozen W2 case after the Task268 repairs, Task740 run1, independently completed the full
  Wiki-coordinate to OSRM-directions workflow with native `verified_success`.

The remaining gate is generalization and stability across untouched cases. A typed `navigation_pending` remains an
intentional fail-closed unsupported acquisition state, not a missing retry or alternate currentness path.

Held-out Task8 run1 did not pass, but it does not reproduce any of the former Agent-chain gaps. The run completed 34
valid single-call policy turns, 18 executions, one STOP, one post-STOP capture, and one native evaluation, with zero
fallbacks, invalid tool arguments, stale catalogs, grounding gaps, context-capacity rejections, or waits. The model
read the CMU-to-Pittsburgh-International route, correctly concluded that roughly 32 km exceeds the requested 5 km,
and submitted `SUCCESS` with an empty list. The installed WebArena-Verified public `FinalAgentResponse` description
says that a retrieval with no items returns an empty array, while the same official Task8 evaluator reference requires
`NOT_FOUND_ERROR` with null data. The native evaluator therefore returned `verified_terminal_task_failure` solely on
the status classification. This was a benchmark public-response-contract/reference conflict at the installed
WebArena-Verified owner, not evidence for changing GoalCompiler, Runtime, World, BrowserGym currentness, history,
cursor, or ToolReturn.

The benchmark profile now resolves that ambiguity at its existing `TaskBoundary`: every WebArena-Verified task carries
one generic public rule that a completed RETRIEVE with zero qualifying items uses `NOT_FOUND_ERROR` and null data,
while a nonempty completed retrieval uses `SUCCESS` and the result list. The original BrowserGym goal remains
byte-for-byte unchanged, `TaskGoal.constraints` projects the rule through the normal `AgentContext`, and the existing
upstream Pydantic response codec remains validation-only. There is no evaluator lookup, task-ID/text branch, response
rewrite, alternate prompt, or production Agent change. Task8 run6 below is the accepted native-evaluator witness.

Task8
[`run2`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run2/run.json) made 16 policy calls and eight
executions but no STOP or native-evaluator call. Its final ordinary ActionPolicy response and the one PydanticAI
output retry both selected text and exhausted the output budget. Task8
[`run3`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run3/run.json) made 45 policy calls and 27 executions.
It found CMU, Pittsburgh International Airport, and an OSRM route of approximately 32.8 km, but continued searching;
the final invocation again exhausted two text-only responses and ended `invalid_response` with no STOP. These are
failed pre-repair witnesses for one provider-boundary mismatch: the local ActionPolicy contract required a tool, but
the physical provider request still allowed text.

The first attempted repair forced `tool_choice=required` on every ActionPolicy request. Task8
[`run4`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run4/run.json) falsified that contract: all 100 policy
responses contained a ToolCall, but none contained model text. PydanticAI compaction never triggered, the explicit
workspace tail retained only four steps, and the policy repeatedly executed the six-action semantic cycle
`E5 -> back -> E6 -> back -> E7 -> back` until the outer turn budget. The provider fix had therefore removed the
same-policy progress text that earlier runs carried alongside their calls, while the existing Monitor supported only
period-2/3 cycles and cleared its active cycle identity on an incomplete longer recurrence.

The converged ActionPolicy request now starts with `tool_choice=auto` and `parallel_tool_calls=false`, so one accepted
response can contain both exact model text/reasoning and one ToolCall. Its existing PydanticAI output validator still
rejects text-only output; the SDK's dynamic per-request settings use `RunContext.retry` to set only that one retry to
`tool_choice=required`. The actual setting of each physical request is recorded in its provider transcript. No
progress store, separate checkpoint, second policy, or custom retry loop was added. The ActionPolicy prompt asks for
no per-step progress artifact; provider-native optional text remains ordinary recent trajectory input, while the
existing Harness compactor alone produces a low-frequency cumulative replacement for an expired pair-safe prefix.
The same `EpisodeMonitor` now
keeps sixteen ref-free signatures, detects every exact repeated suffix representable in that window, retains a recovered identity through a partial
recurrence, and blocks the same phase-independent cycle when it continues. Typed new public information or expiry of
the episode clears that identity.

Task8 [`run5`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run5/run.json) falsified an intermediate v36
prompt that asked the ActionPolicy to state progress in the same response whenever a conclusion, unresolved
requirement, or strategy changed. DeepSeek treated ordinary atomic steps as such changes: 100 policy turns produced
verbose repeated narration, which scheduled nineteen `expired_model_prose` compactions and ended at the outer step
limit despite a correct cumulative summary. That summary retained the two rejected airport candidates, their OSRM
distances, and the known Nominatim limitation, so run5 is not evidence loss or a compactor-content failure. Run1 had
already reached the sufficient `international airport Pittsburgh -> Aerodrome region -> empty qualifying set`
strategy without a per-step progress instruction. The v36 instruction is therefore removed; optional native model
text and low-frequency Harness compaction remain separate existing concerns.

Task8 [`run6`](../evidence/live/w1b-task-8-deepseek-v4-flash-20260826-run6/run.json) is the accepted post-repair
witness at commit `c53d496e`: Runtime ended `done`, issued one STOP and one post-STOP capture, and the native evaluator
accepted `NOT_FOUND_ERROR` with null data. It completed in 45 policy turns and 236.9 seconds. Eight Harness
compactions retained cumulative historical conclusions while recent reasoning/call/result messages remained exact;
there was no per-step progress producer. Run6 closes the Task8 zero-result/provider/progress witness, but one accepted
case does not establish held-out cohort stability.

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
Task266 run8 crossed the repaired recall path, activated the exact article, recovered the official coordinates, and
then used `goto` for an unauthorized external API instead of switching to the benchmark-provided map in tab 0.
BrowserGym correctly terminated the task at that dispatch; the later `stale_binding` report was a downstream
`task_done` symptom. The run's fresh World contained both open tab routes and the active index, while the physical
model input contained only the folded `Browser navigation` region heading. This is failed pre-repair evidence for the
compact action-subject projection, not acceptance. The browser-only direct-observation patch has been removed: the
sole renderer now keeps every current non-entity action subject already present in Actor World, including the browser
tab state. It does not relax WebArena URL authorization or add tool/task/site-specific routing.

Task266 run9 crossed that compact-observation boundary. Across ten valid policy calls it focused the correct tabs,
read the official coordinates, returned to the map, discovered the real directions control, and selected it. The
adapter returned `NOT_SENT/stale_binding` before Playwright because the project's currentness comparator equated the
control's whole canonical `public_state` and availability snapshot. Dynamic presentation drift therefore overruled
the still-matching BID/role/label/click contract, and CoreLoop terminated instead of using its existing fresh-binding
capture. Run9 is failed pre-repair evidence, not acceptance.

The repair makes the interaction profile's existing `currentness_fields` the sole state-drift declaration. Page and
episode lineage, BID, role, accessible label, select option values, and drag topology remain strict; CSS, color,
geometry, incidental active/focus state, and equal-executability availability changes do not become a second binding
identity. BrowserGym/Playwright still owns locator resolution and physical actionability. If that boundary returns a
typed pre-dispatch stale result, CoreLoop performs one `BINDING_REFRESH` capture and lets the same policy choose again
from the fresh World. It records zero executions and never replays the action.

Task266 run10 crossed that currentness boundary without a stale-binding recurrence, but failed after exposing two
control-contract defects. Four of eight raw ActionPolicy responses contained two ToolCalls despite
`parallel_tool_calls=false`; the bridge silently selected the first and the formal `multiple_tool_call_count` remained
zero. After an exact `read_region(R9)` replay activated recovery, a different empty `read_region(R10)` was then
immediately classified as `control_stalled`. Run10 is failed pre-repair evidence, not acceptance.

The first repair rejected every multi-call envelope and made one same-context `single_action_retry`. Task266 run11
falsified that contract after 74.9 seconds: the first turn recovered, but both physical requests on turn two returned
two `read_region` calls. The gate correctly executed neither, recorded three total multi-call envelopes across four
provider attempts, and terminated typed `invalid_tool_arguments` before native evaluation. BrowserGym completed its
one tab-focus dispatch and cleanup normally; this is failed provider-compliance evidence, not an environment or report
failure.

The revised Catalog boundary serializes ordered proposals: it normalizes and resolves only the first call, while
retaining every exact proposed `ToolCallPart` in canonical PydanticAI history. After one Runtime step, the next
physical provider input pairs the first call with its real same-ID result and every later call with PydanticAI's native
same-ID `ToolFailed(not executed)`, followed by the fresh World. The ActionPolicy can therefore reissue an important
later proposal, but Runtime never queues or automatically executes it. An invalid first call never falls through to a
later one. Raw output remains in Trace, formal metrics count every multi-call envelope, and invocation diagnostics
record proposals discarded from execution. Monitor recovery still prohibits only one exact typed attempt. No second
action queue, reflection model, evidence path, cursor state, or non-SDK history was added. At that checkpoint a fresh
live Task266 witness was still required; run37 later supplied it.

Task266 run12 crossed that revised boundary: all fourteen produced calls were valid, the first proposal executed, and
every later proposal received a same-ID native not-executed result. The next physical input contained both exact
official coordinate results and the unexecuted `tab_focus` proposal, so this was not renewed call/result loss. The
ActionPolicy nevertheless revisited Portland and Acadia after reasoning that OSRM was next. Monitor caught exact
repeated reads but not the intervening fresh-World `Portland -> Acadia -> Portland -> Acadia` action cycle; large Wiki
World processing amplified each extra turn until the 957-second case watchdog timed out.

The then-current repair did not add milestones, a summary model, or a second control loop. PydanticAI history retained
one latest model-authored visible text across tool-only responses: a new visible text replaced the old one, while a
tool-only response carried forward the exact previous text and removed only duplicate historical `TextPart` values.
Completed call/result pairs remain untouched and the existing `ProcessHistory` path still drops only oldest complete
exchanges. Run15 later proved that treating every visible text as progress was underspecified. `EpisodeMonitor` now
uses its existing `STATE_OSCILLATION` algebra over at most sixteen dispatched public
attempt signatures to recognize every repeated suffix representable in that window across fresh Worlds. It reads no task text, URL, site,
GoalPlan status, or ToolReturn body. Run12 remains a failed pre-repair diagnostic; run13 below crossed these two
repairs before exposing the independent SurfaceAdapter defect.

Task266 run13 crossed those repairs and terminated normally as `blocked` after ten policy calls and six dispatched
actions. Its trace showed that a `tab_focus` changed BrowserGym's active page, but the custom causal-step wrapper kept
the pre-dispatch page for post-action physical enrichment and transition URL while BrowserGym `_get_obs()` supplied
the new page's DOM/AX facts. The mixed observation marked the Wikipedia search field unavailable, removed its text
entry operation from the complete `ActionSpace`, and caused later tab/read oscillation. Monitor correctly recovered
once and blocked recurrence; history and task information were present.

The owner repair now reacquires BrowserGym's current page immediately after dispatch and uses it consistently for
post-action quiet tracking, observation, physical enrichment, and `after_url`; the old page is retained only by the
dispatch/navigation watcher. A real Playwright two-tab regression proves the new-page observation and enrichment
identity. This adds no fallback, second World, browser-state side channel, tool branch, or Monitor behavior. Run13 is
failed pre-repair evidence.

Task266 run14 crossed that repair and is the failed pre-performance-repair witness. It ran for about 1,001 seconds,
made 19 policy calls, completed 18 valid tool calls and eight effectful dispatches, and recorded zero invalid
arguments, stale bindings, `sent_unknown`, `wait`, or fallback. No STOP/native evaluation occurred because the
enclosing case deadline cancelled policy turn 19. Model-provider latency was about 164.5 seconds; the remaining time
was predominantly synchronous same-World derivation. Exact request timestamps show 67--72 second gaps after local
reads on the Portland article, while a local read on the small map World took about 0.5 seconds before the next
request. The durable trace is
[`run14`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run14/run.json); its JSONL is about 505 MB for 64
events because step projection copied canonical Worlds despite their non-serialization metadata.

Offline profiling against run14's exact persisted 6,002-target / 4,096-fact World closes the timing model:
`current_findings_digest=44.78s`, unchanged `WorldTransitionProjector=10.35s`, next-turn
`WorldDeliveryIndex=4.57s`, `ContextBuilder=2.05s`, and `TurnPacker=1.10s`. The Monitor digest was quadratic because
it rebuilt every target's public semantics once for every fact. The repaired digest builds one target map and makes
one fact pass; it measures about `0.122s` with the identical digest. Identical-World delta projection now measures
about `0.452s`, and the bounded local-step trace projection measures about `0.0001s / 1.3KB` before ordinary receipt
content. Run14 remains failed evidence; a post-repair live witness is required.

Task266 run15 showed that arbitrary action narration could replace a prior progress note. The v1 response-side XML
contract did not converge: the later authorized
[`run16`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run16/run.json) made 30 valid policy/tool calls but
zero STOP/native-evaluator calls and ended `blocked`. It accumulated 154,260 history tokens, emitted no checkpoint
`TextPart`, spent its first 21 turns rediscovering Wikipedia controls, later recovered Portland and Acadia facts, and
then lost the intended OSRM transition. Ten recovery calls all restarted from attempt 1 because different empty/no-match
operations cleared Monitor's episode. Run16 is failed pre-repair evidence, not acceptance.

The current owner repair removes both the v1 co-output requirement and the later custom checkpoint/reducer. Exact
accepted `ThinkingPart`, ordinary text, provider metadata, ToolCalls, same-ID ToolReturns, and each fresh-World user
prompt remain in official PydanticAI history. Harness 0.25 `SummarizingCompaction` runs when either the complete
canonical request reaches 80% of effective provider input or expired unsummarized model prose fills one bounded
age/size batch. It receives the original typed history, replaces a pair-safe expired prefix with one ordinary
`SystemPromptPart` summary, and retains the newest pair-safe suffix at full fidelity. The summary keeps bounded
completed task outcomes, exact task-critical facts, and failed strategies rather than an action log or prospective
task state. Provider failure, timeout, or invalid compacted topology leaves the exact typed raw history unchanged.
There is no synthetic summary view, knowledge-specific trigger, source-coverage inventory, Monitor trigger, Workspace
projection, or additional Runtime memory state. Runs20--24 are live failure witnesses for successive pre-repair
contracts; Task7 run2 is the later accepted live-pressure witness.

The authorized Task266
[`run17`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run17/run.json) proved that the checkpoint now
preserves Portland's coordinates and the next Acadia intent, then exposed two different owner failures. Reducer
scheduling invoked 16 calls in 21 policy turns; 13 reached the 18-second reducer deadline. The final Enter action was
sent once and BrowserGym established `stable_navigation` plus a completed fresh capture, but
`ProductionActionOutcomeProjector` ignored it because the admitted `press_key` verification family was semantic. It
returned `UNKNOWN`, and Monitor correctly blocked the resulting false no-effect episode. Run17 is failed pre-repair
evidence, not acceptance.

The provider-free repair gates now require:

- BrowserGym maps only typed `STABLE_NAVIGATION` to the generic existing `ActionResult.causal_transition`; unstable and
  no-navigation outcomes do not produce that fact;
- the Projector accepts that typed causal fact for any admitted action family, but produces confirmed change only with
  current public structural/screenshot evidence; a matching private adapter-evidence string alone remains `UNKNOWN`;
- the vertical fake-BrowserGym route proves `dispatch -> stable navigation -> fresh World -> CHANGED` without Monitor,
  CoreLoop, or Trace parsing;
- Harness compaction is not called below 80% complete canonical-request pressure and has no
  knowledge/result/Monitor trigger;
- above pressure, only a pair-safe expired prefix is summarized, the token-bounded recent suffix and unresolved call
  remain exact, accepted reasoning is visible to the summarizer, and a summary-provider failure restores the entire
  raw history;
- the exact compaction request/response is recorded as a `history_compactor` provider attempt while the summary itself
  remains a standard non-authoritative PydanticAI `SystemPromptPart`.

At that checkpoint no passing post-repair Task266 witness existed; run37 later supplied it.

The authorized Task266
[`run18`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run18/run.json) crossed the reducer scheduling
repair: only the bootstrap and first-recovery reductions ran, both completed, and no reducer timeout occurred. The
fresh Wikipedia World contained a focused search textbox with a legal `press_key` binding, but the soft-packed request
retained only the task-ranked Wikipedia home link. After two empty discovery attempts, the model chose the correct
keyboard strategy but could ground `ArrowDown` only to that unrelated visible link. BrowserGym sent it and captured a
different fresh public World. Monitor then inherited the discovery recovery count, rendered the real receipt as
`not_sent`, and blocked the action as recovery attempt three because a semantic key press has no universal mechanical
postcondition. Run18 is failed pre-repair evidence, not acceptance.

The provider-free repair now requires one complete explicit discovery set when present; otherwise the hard packing
minimum contains both one task-ranked target and the first direct fresh focused target. Optional candidates still use
the existing soft token target. This closes both the earlier run5 counterexample (focus alone displaced the ranked
target) and run18 (rank alone displaced focus). Monitor derives `sent|sent_unknown|not_sent` from the typed receipt,
does not clear an ineffectual same-World action, and starts a new same-World recovery episode when a causally dispatched
action reaches a changed fresh public World even if its semantic postcondition remains unknown. No alternate action
view, recovery state machine, model, or retry was added. Run37 is the later accepted live Task266 witness.

The authorized Task266
[`run19`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run19/run.json) live-validates those action and
Monitor repairs but remains a failed witness. It completed 30 valid policy/tool decisions, 12 effectful dispatches,
13 observations, and one successful recovery, with zero invalid arguments, stale bindings, waits, fallbacks, STOPs,
or native evaluator calls. The last control termination was `turn_budget_exhausted`, not a Monitor recommendation:
the task declared 100 turns, while Core silently capped it at the Monitor profile's 30 policy decisions.

The repaired acceptance contract is now: `TaskGoal.loop_budget.max_turns` alone determines `RunState.remaining_steps`;
Monitor configuration cannot shorten the run and only bounds same-World stall detection and recovery retries. Focused
tests include a behavioral 37-turn TaskGoal witness with a stricter Monitor profile and prove all 37 turns remain
available. Run19 predates this repair, so it is not post-repair acceptance and another authorized live witness is
required.

Run19 separately reopens checkpoint scheduling. Fourteen reducer attempts occurred in 30 turns, seven timed out, and
the surviving checkpoint turned an ambiguous relation-page episode into a durable invalid-ID conclusion. The raw
trace shows the ActionPolicy itself had already observed that `/relation/2176999` supplied the relation ID, then
vacillated; the read/search-only reducer omitted the action-observation context and amplified one side of that
uncertainty. This open defect must not be hidden by a larger turn cap. Closure requires replacing result-count-driven
reduction with pressure-driven compaction of an expired complete trajectory prefix plus a recent raw tail, using the
installed PydanticAI Harness rather than a new Store, milestone state, or evidence path.

Task266
[`run20`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run20/run.json) and
[`run21`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run21/run.json) are failed pre-repair witnesses for
the first direct-Harness integration. Run20 proved that a fixed eight-message suffix is not a token bound on variable
GUI Worlds and that a 10-second summary timeout can restore raw history into a later capacity failure. Run21 crossed
both repairs: every compaction completed and ActionPolicy inputs remained bounded. It then showed that Harness's
`estimate_context_tokens()` uses the latest provider usage anchor, which includes current prompt/tools rather than
history alone, so the bridge incorrectly summarized on every subsequent turn. The history owner now gates on
Harness's message-only `estimate_token_count()`.

The aborted diagnostic
[`run22`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run22/run.json) falsified one remaining scheduling
assumption before acceptance: a large Portland World alone exceeds the 8,000-token delivery soft target, so treating
that target as history capacity still caused back-to-back summaries; the second took about 25.9 seconds. Follow-up
run23 then showed that a separate history-only estimator still cannot see the pending ToolReturn and fresh current
request: RequestAdmission counted 53,712 history tokens and 67,022 total input against a 62,904-token effective limit,
while the pre-pack gate remained below its independent threshold. The current bridge therefore preflights the exact
normal TurnPacker/RequestAdmission path and invokes Harness when that existing owner reports 80% complete-request
pressure. This is a stateless capacity decision at the existing PydanticAI boundary, not a cooldown, reducer frequency
counter, alternate estimator, or scheduler.

The authorized
[`run24`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run24/run.json) crossed that exact-request pressure
repair: the ActionPolicy retained Portland and Acadia, entered both coordinates in OSRM, computed a route, and began
reading the total distance. Its 29 accepted calls included 13 effectful dispatches and zero invalid arguments, stale
bindings, waits, fallbacks, or grounding gaps. The final failure was provider-boundary timeout coupling, not task
progress: three compactor calls ended at about 27.8 seconds because Harness's 30-second outer deadline reused the
ActionPolicy client's 27.25-second default timeout. Raw history was honestly restored twice; on the third failure the
complete canonical request reached 68,081 tokens against the 62,904-token effective limit and returned the typed
`context_capacity` failure. The repair keeps one configured model/provider, gives its client the compactor deadline,
and carries the shorter action deadline through official PydanticAI per-request model settings. The 90-second policy
budget remains closed over one optional compaction, one bounded retry delay, and at most two action attempts.

The authorized
[`run25`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run25/run.json) crossed that client-timeout repair.
All ten pressure-triggered summaries completed; there were zero context-capacity, invalid-argument, stale-binding,
wait, fallback, or grounding-gap events. The agent retained `relation_id=2176999` and OSRM distance `287km`, then used
the final turns to verify the relation by coordinate search. The terminal `provider_unavailable` came from the static
replacement partition: after a successful 23.0-second compaction, both ActionPolicy attempts retained the fixed
21.125-second timeout and ended at about 21.7 seconds. The current repair propagates one absolute policy deadline and
recalculates the canonical per-request timeout after actual compaction elapsed. With run25's measured timing, both
remaining attempts receive 30.75 seconds while compaction, retry reserve, attempts, and safety margin still fit the
same 90-second outer deadline. A vertical test proves the post-compaction envelope receives the recalculated value;
the pure budget test covers the run25 numeric witness.

The authorized
[`run27`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run27/run.json) crossed the dynamic-deadline repair:
all 57 completed policy calls were valid, there were zero capacity rejections, invalid arguments, stale bindings, or
grounding gaps, and the agent reached the final Acadia OSM search results. It still failed at the 900-second case
watchdog after 58 policy calls. This is not evidence that a longer watchdog closes the task. Eleven compactions used
about 266 seconds, and their content exposed a causal fidelity defect: the original Portland and Acadia infobox
ToolReturns contained their coordinate rows, but Harness 0.25's summary formatter clipped each old ToolReturn to 500
characters before the summary model saw it. The resulting summary falsely called both coordinates unverified and
caused the later wiki rereads. The later OSRM `287km` conclusion remained in the exact recent suffix and was not
repeated; the relation ID had not yet been obtained when the watchdog cancelled the policy turn immediately after a
correct `find_controls` result placed the Bar Harbor national-park link first.

The post-run repair keeps Harness as the only compaction implementation but gives its throwaway summarizer view the
full owner-bounded public ToolReturn instead of the dependency's generic 500-character prose preview. Exact canonical
history and the preserved suffix remain byte-for-byte PydanticAI messages. The reused model also carries a default
1,024-token, temperature-zero, thinking-disabled limit for Harness's direct summary call; request-scoped ActionPolicy
settings continue to override that default. A focused regression places an exact coordinate after 700 irrelevant
characters in a partial, paginated result and proves it reaches the compactor request, while the pending call and exact
suffix remain unchanged. The full provider-free suite passes; run27 remains failed pre-repair evidence and a fresh live
witness is required.

The authorized
[`run28`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run28/run.json) crossed that compaction-content
repair. The model retained Portland `43.66,-70.255`, Acadia `44.35,-68.2167`, and obtained the direct OSRM result
`261523.9m`; history loss was not the failure. It used `goto` for `router.project-osrm.org` instead of the benchmark's
already-open map tab. BrowserGym correctly returned terminal failure after that external page loaded. The Runtime then
made eleven more policy calls because the native evaluator hid pre-STOP terminal state and the same-call ToolReturn
omitted the `NOT_SENT/stale_binding(task_done)` terminal failure. Run28 ended `blocked` after 23 policy calls and is
failed pre-repair evidence for navigation-scope publication and terminal propagation, not evidence for another memory,
cursor, or Monitor mechanism.

The provider-free repair leaves the generic BrowserGym browser profile unrestricted. Only the WebArena runner reads
BrowserGym's official configured URL set and supplies it as the explicit environment navigation scope. The current
World browser subject exposes only that the scope is restricted, and the current `goto` ActionBinding keeps the
registry's generic HTTP(S) shape. The existing private BrowserGym binding retains the normalized locations and rejects
external, lookalike, userinfo, and wrong-port URLs as typed `NOT_SENT/destination_outside_environment` before dispatch. Provider
terminal state is classified on the same post-action World without waiting for an agent STOP, and
the normal ToolReturn projection exposes typed non-dispatch terminal failures. A vertical fake-BrowserGym test proves
that terminal failure ends the CoreLoop after the one dispatched action with no second policy turn. This adds no
WebArena tool, task/site branch, fallback, or alternate browser state.

The authorized
[`run29`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260825-run29/run.json) crossed both repairs and failed at the
final ActionPolicy generation after ten ordinary calls and three effectful dispatches. The provider returned almost
30,000 characters of prose with `finish_reason=length` and no ToolCall even though the canonical request reserved
1,024 output tokens and offered `tab_focus(index=0)`. Its input also showed the inactive map only as
`route=http://localhost:3000/`; BrowserGym's available `open_pages_titles` value (`OpenStreetMap`) had been discarded.
This is failed pre-repair evidence for provider budget transport and open-tab semantic projection, not a reason to add
a URL recognizer, site rule, memory path, or larger case timeout.

The current repair pairs BrowserGym `open_pages_urls` and `open_pages_titles` by index into the one browser-context
subject. It retains bounded title plus sanitized route and removes the duplicated navigation allowlist from public
World state and Catalog; the private BrowserGym binding remains the environment-authorization owner. DeepSeek's
existing output budget is sent through `max_tokens`. Ordinary and representation-repair ActionPolicy requests use
disabled thinking; the existing deliberate recovery profile uses enabled thinking. Every invocation starts with
`tool_choice=auto`, and PydanticAI's output validator changes only its one text-only retry to `required` without
changing the initial thought+text+action response. On that bounded retry it disables thinking because DeepSeek rejects
`tool_choice=required` with thinking enabled. Exhaustion is typed as `no_tool_call` or `output_budget_exhausted`;
rejected prose does not enter canonical history. Representation repair is not nested with this retry. Focused tests
cover title/URL
pairing and sanitization, title-independent binding currentness, private navigation authorization, accepted retry,
typed exhaustion, exact retry history, and the DeepSeek model profile. Run31 below supplies the live witness.

The authorized
[`run31`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run31/run.json) crossed those repairs
and accepted with native `verified_success`: 46 policy calls, 22 executions, 23 effectful dispatches, zero fallback,
zero multi-call envelopes, and zero context-capacity failures. It is the first live Task266 success for this causal
line, while also exposing a bounded efficiency defect. Nine pressure-triggered compactions consumed 213,703 tokens;
the last 1,888-token summary retained an action log, incidental page facts, stale refs, and every guessed local URL.
Separately, the restricted `goto` schema printed all six permitted localhost netlocs to the model, which treated the
authorization list as a service directory and spent six turns probing four unrelated ports.

The optimization keeps the successful control path unchanged. The existing Harness compactor now retains a 12%
pair-safe exact tail and produces at most 1,024 tokens of conclusion-oriented history: bounded completed task outcomes,
task-critical verified facts, and failed strategies, without remaining work, next intent, action narration, or stale
current-state data. The public `goto` contract returns to the registry's generic HTTP(S) shape; only the existing
Runtime-private BrowserGym binding retains environment locations and rejects an unauthorized destination before
dispatch. The actor prompt removes duplicated static rules but keeps the complete fresh World and current ToolReturn.
No checkpoint, memory owner, URL recognizer, service directory, cursor, Monitor trigger, or second Runtime path is
introduced. A fresh post-optimization live witness remains required.

Runs33--36 then separated four remaining contracts rather than just extending the case timeout. Run33 showed that a
typed pre-dispatch `invalid_parameters` result was reselectable at execution authority but CoreLoop still terminated;
the generic NOT_SENT algebra now re-enters the same ActionPolicy only for explicitly reselectable failures. Run34
crossed that repair and showed that the final public tool schema still required ephemeral current-World evidence refs;
the model-visible final call now owns only `content`, while internal evaluator evidence remains unchanged. Run35
proved that the conclusion-oriented compaction prompt alone could still emit relation `2176999` under both verified
and remaining sections and that an exact prohibited local replay had no enforceable alternate-step boundary. Run38
later proved that interpreting repeated numeric text as a deterministic contradiction causes repeated compactor
calls. Summary prose therefore remains non-authoritative model context governed by the shared prompt; the history
owner validates typed messages and exact suffix conservation, while the existing typed Monitor recovery budget
handles a same-call replay rejection. No checkpoint reducer or second policy was added.

The authorized
[`run36`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run36/run.json) crossed the GoalCompiler,
identifier-retention, final-call, and replay contracts. Its last failure was distinct: the fresh World and private
bindings contained an executable button labeled `Go`, but `find_controls("Go button")` returned empty. Inventory-wide
facet inference had interpreted `go` as an operation because the same ActionSpace contained `go_back/go_forward`,
then removed that token from the button's own exact label. Repeated discovery was a consequence; the final text-only
provider exhaustion was secondary. The action-discovery owner now lets an exact candidate label claim colliding
tokens before role/operation constraints, without any site, URL, task, selector, or unique-control branch.

The fresh authorized
[`run37`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run37/run.json) is accepted with native
`verified_success`. It returns `[{"relation_id":2176999,"distance":"287km"}]`, makes one GoalCompiler call, 39 ordinary
ActionPolicy calls, zero recovery calls, and exactly one STOP, post-STOP capture, and native evaluator call. Sequence
84 returns the current `Go` capability for `find_controls("Go submit directions")`, sequence 86 executes it, and the
formal run ends `done` in about 325 seconds. The two reported gaps were therefore real root causes, but not a complete
explanation of run36: the independent exact-label/operation collision also had to be closed at control discovery.

Run37 also supplies the pre-optimization token witness. Its 39 ActionPolicy calls accumulated 870,289 history tokens
and 1,008,148 prompt tokens; 135 historical user prompts repeated the same task/plan and expired Worlds, compared with
39 current-turn prompts. The repair stays in the PydanticAI history owner: it keeps exactly one current task/plan
anchor, makes all other historical user prompts World-only, and removes only expired World prompt parts outside an
admission-derived 12% recent tail before applying the existing 80% Harness pressure gate. Model-authored progress,
thinking, and all result-bearing messages remain raw in that recent tail. Outside it, only whitespace-equivalent
repeated model prose is removed, with the newest occurrence retained; unique conclusions, ToolCalls, and ToolReturns
retain pair identity and semantic content, while only current-World handles remain executable. Retained multimodal
Worlds keep their media, and Harness preserves the anchor when semantic compaction
is needed by full-request pressure or when expired unsummarized model prose fills an age/size batch bounded by the
smaller of the recent-tail target and existing maximum summary-output budget. This is not semantic matching or a
reducer. Generated history tests cover 5--12 turns, call/result pairing and stable-conclusion conservation, bounded
repeated prose, one task anchor, a bounded recent raw tail, provider-boundary equality, and multimodal grounding.
Task7 [`run1`](../evidence/live/w1b-task-7-deepseek-v4-flash-20260826-run1/run.json) is the failed pre-repair witness
for incremental pair conservation. The project's summary-only view had changed each `ToolReturnPart` into a
`SystemPromptPart`, so Harness's official token cutoff could not see one completed pair. Its third compaction retained
the old return without its call; the wrapper checked only the newest pending identity, and canonical projection
rejected the orphan before Catalog construction. Production now passes original typed messages directly to Harness,
validates the complete compacted topology at the history owner, and restores the exact input history on invalid
output. Generated regression coverage uses a prior summary, six completed exchanges, large expired Worlds, and the
same adverse token boundary; every retained completed call ID equals its return ID and the newest pending call remains
exact.

Task7 [`run2`](../evidence/live/w1b-task-7-deepseek-v4-flash-20260826-run2/run.json) is accepted with native
`verified_success`: 16 valid policy calls, two accepted age/size compactions, zero invalid arguments, grounding gaps,
stale bindings, or waits, and exactly one STOP, post-STOP capture, and native evaluator. Both compacted turns retained
an 18-tool Catalog and continued into ActionPolicy. The final result is
`[{"name":"Pittsburgh International Airport","state":"Pennsylvania","postcode":"15231"}]`, supported by the
explicit 33 km OSRM route. Aggregate prompt/history/completion tokens were 215,510 / 200,355 / 4,790; no cross-run
efficiency claim is made because run1 followed a different failed trajectory.
[`run38`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run38/run.json) passed native evaluation with 43
valid policy calls, zero waits, zero invalid calls, and one STOP, so the observation/action path remained correct. It
failed the efficiency objective: six Harness calls consumed 198,783 input tokens and all six summaries were discarded
by the Runtime's numeric-section consistency regex. Ordinary ActionPolicy input remained roughly 35--43k late in the
run, but the rejected compactor calls raised aggregate prompt tokens to 1,379,172 and latency to about 472 seconds.
The shared cause is not missing task or progress context. A non-authoritative prose summary can mention the same
number in different claims; Runtime cannot infer claim identity from numeric intersection. The owner repair removes
that semantic parser and accepts Harness output after typed message and exact suffix validation. Prompt guidance,
recent raw Worlds, model conclusions, and exact call/result history remain unchanged. A post-repair live efficiency
witness was still required.

[`run39`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run39/run.json) accepted the first pressured summary
and persisted it: compactor input was 28,734 tokens once, later ActionPolicy requests dropped from about 33k to
13--20k, and native evaluation again returned `verified_success`. But the summary's prospective fields caused eleven
extra policy turns: it simultaneously recorded relation `2176999` as verified and under `Remaining questions`, then
set re-verification as `Next intent`. The run finished in 50 turns with 1,209,104 prompt tokens, so it is a successful
scheduling witness but not an efficiency closure. The post-run contract removes `Remaining questions`, `Next intent`,
working hypotheses, and current stage from long-term compaction. Harness now preserves only stable completed outcomes,
verified facts, and failed strategies; the one ActionPolicy recalculates prospective work each turn from the current
task/plan/World and recent exact suffix. A fresh live witness for that final contract was required; Task7 run2 later
crossed it twice under age/size pressure.

[`run40`](../evidence/live/w1b-task-266-deepseek-v4-flash-20260826-run40/run.json) is accepted with native
`verified_success`: 34 valid policy calls, zero waits, zero invalid arguments, one STOP, and no compactor invocation.
The cheap history projection kept the complete request below pressure, so Harness correctly made no semantic call.
After obtaining relation `2176999`, the policy computed the route, found the exact `Distance: 287km` result, and
submitted without reopening relation verification. Prompt tokens were 847,397 versus run37's 1,008,148, a reduction
of 160,751 (15.9%); model latency fell from about 127.7s to 98.9s. Overall wall time was about 350s versus 325s because
BrowserGym transition latency varied, so the evidence supports token/model-call efficiency, not a wall-time claim.
Trace-reported provider cost fell from about 0.05937 to 0.05698 (4.0%), less than the token reduction because much of
run37's repeated prefix was served from the provider cache. Provider-boundary tests cover the stable-only summary path
for genuinely pressured histories, and Task7 run2 later exercised it twice live.

Run21's final `PublicGroundingAmbiguousError` was also reproduced without the model on the exact Maine page. Two
legitimate executable links named `List of counties in Maine` had distinct source structural paths `(94, 1)` and
`(102, 1)`, but the region index reduced each to the same region-local order `2`. The target-context owner now ranks
source structural occurrences document-wide. Structurally distinct identical controls receive distinct current
E-refs; genuinely indistinguishable executable targets without a structural occurrence still fail closed.

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

After direct call/result history was restored, the same trace exposed another owner defect: the bridge reconstructed
the accepted response as a new `ModelResponse` containing only `ToolCallPart`, so the model's own conclusion existed in
Trace but not in the next turn. The then-current response-side progress-note repair was later falsified by run16. The
current contract instead keeps a bounded exact recent suffix—including thinking—and lets Harness replace only an
expired pair-safe prefix with one ordinary historical summary. No Runtime evidence memory is introduced.

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

The earlier Task21 run16 trace passed the agent-side task. It made 16 valid policy/tool calls, issued no invalid arguments,
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
when another current tab exists and enumerates its current tab index. The generic browser profile keeps the registry's
unrestricted `goto`; the WebArena runner separately supplies BrowserGym's own configured site URL set, so its current
`goto` schema admits only those environment locations.

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
committed results. Exactly one prompt part anchors the current task/plan; historical World prompt parts are removed
without changing the completed pairs, and the physical request supplies exactly one fresh current World. A terminal
response clears the bridge history. The Store contains only bounded digest receipts and no result body/inventory.

A second Recording PydanticAI gate emits `ThinkingPart + N ToolCallPart`. Exactly the first current call is resolved;
later calls are not executed, queued, or used as fallback. Canonical history first preserves the exact response,
including thinking and every proposal. The next physical input pairs the first with its owner result and the rest with
same-ID native failed returns. After that exchange is closed and a newer response is pending, private thinking may
expire only if its own public text conclusion remains; pair identities, semantic values, tool-only reasoning, and the
unresolved response remain exact, while noncurrent operational handles expire. A generated 1..8-call property verifies
complete call/result pairing, a longitudinal gate
verifies reissue, and an invalid first call cannot fall through to a valid later call.

Before semantic compaction, generated 5..12-turn properties verify one task/plan anchor, no historical World prompts,
model conclusions and call/result pairing, exact pending and tool-only reasoning, degrounding only of closed
noncurrent exchanges, expiry only of closed private reasoning with its own public conclusion, bounded equivalent
repeated prose, and canonical provider projection. The
same final `RequestAdmission` breakdown counts history, pending ToolReturn, the one fresh World,
tools, and overhead. PydanticAI Harness pair-safe compaction runs at 80% complete-request pressure, or at 50% history
pressure only when at least 15% of history capacity is reclaimable outside the exact suffix. It targets 30% history
and retains the newest pair-safe 12% suffix. The task anchor and unresolved call remain byte-for-byte unchanged.
Compaction is accepted only after the complete canonical history algebra passes; a provider error, timeout, or invalid
compacted topology returns the exact raw history. Source-coverage, knowledge bootstrap/batching, result-kind triggers,
semantic matching, and failed-input memos are absent from production.

Monitor gates prove a different empty discovery/read attempt remains in the same recovery episode, while typed
`NEW_INFORMATION` clears it. A generated property over every period representable by the fixed window proves GUI cycle identity is phase-independent; a
vertical period-6 case recovers once and blocks continued recurrence even when every action reaches a changed fresh
World.

### G4 — R-ref follow-up

The `read_region` schema accepts the public `R` syntax for the current canonical World, and the resolver validates the
actual current ref. This avoids building a schema enum from a previously admitted result prefix while preserving
currentness at the correct owner.

Search results continue to return a direct `read_region(region_ref)` follow-up for readable matches.

### G5 — action discovery remains bounded and separate

`find_controls(query)` returns only bounded query-qualified current matches and never dispatches a browser action. It
has no public generic continuation capability and no private public-result inventory. Partial coverage tells the model
to refine the query.
Common tokens present in every page-control functional path are structural ancestry rather than candidate-local
evidence; they cannot make the inventory a genuine match set. Discriminative local paths, public labels, and real
role/operation facets remain available without any site/task vocabulary.
The same recall owner reports query terms that none of the returned controls actually support; a candidate-local
partial match cannot silently turn the whole query into `unmatched_terms=[]`.
Every `(operation, E-ref[, destination])` route returned in that result is resolved against the next same-World
complete current `ActionSpace`. The public schema stays independent of result count and candidate packing; exact
operation membership, destination adjacency, target-specific parameter domains, and private action identity remain in
the existing resolver. A corrupted, unavailable, or stale ref fails closed before Binder/Executor.

Property and Monitor gates prove that focused/unrelated controls remain excluded, permutations do not change match
membership, discovery creates no `InformationDelta`, and the second consecutive same-World discovery produces typed
recovery rather than an unbounded query loop.

The explicitly authorized W1b Task0
[`run4`](../evidence/live/w1b-task-0-deepseek-v4-flash-20260826-run4/run.json) is accepted with native
`verified_success`. It made 28 policy calls with 28 valid tool calls, zero invalid arguments, grounding gaps, stale
bindings, or waits; one age/size-triggered Harness compaction ran, the policy reached the real Period control and
submitted `Quest Lumaflex™ Band`. This live witness closes the two contracts above for the exercised path, while the
broader untouched-case campaign remains open.

For an ordinary turn without an explicit discovery result, one vertical gate sets the soft target to the cost of only
one visible route and proves that both the first task-ranked target and the direct fresh focused target enter the
Manifest and resolve through the same Catalog. A property gate makes inability to fit both inside the hard capacity a
typed capacity failure rather than a Runtime choice. A second gate gives the delivery zero visible routes and proves that its action schema is unchanged and
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
media and public-identity projection; run37 is the later accepted complete repaired large-page witness.

The current vertical gate additionally forces a second Recording FunctionModel call after a GUI action and verifies
that its observation comes from the fresh `WorldDeliveryIndex` PageMap with no retained effect/currentness block.

Browser-global action gates verify profile isolation and the official BrowserGym action strings for all six navigation
operations. The unrestricted profile accepts ordinary HTTP(S) URLs. The restricted WebArena-profile property admits
configured locations while rejecting external, deceptive-suffix, userinfo, and wrong-port URLs at the private
BrowserGym execution boundary before dispatch; World and Catalog do not reveal the allowlist. These gates do not add
a local navigation tool or bypass normal currentness and capture.

A real Playwright two-tab causal-acquisition gate changes the active page during `environment.step` and proves that
the returned observation, private enrichment input, and trace `after_url` all belong to BrowserGym's post-action
current page. It also proves that the pre-dispatch page remains only the navigation watcher and that tab focus does
not create a second World or action path.

Currentness gates enumerate every executable BrowserGym element offer and prove that only its declared semantic fields
can invalidate the binding. A BrowserGym execution witness proves presentation-only drift reaches the official action
path. The CoreLoop vertical witness then injects a physical `NOT_SENT/stale_binding` after the cheap World check and
proves one fresh capture reaches the next policy turn, with the terminal non-dispatch fact retained, zero execution,
and no hidden replay. A second WebArena vertical witness proves an upstream terminal post-action snapshot is classified
in that same step and prevents another policy turn. The ToolReturn projection gate proves a non-dispatched terminal
failure cannot be rendered as successful/running or leak arbitrary adapter evidence.

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

Every `DeliveryManifest` ref must occur in the same admitted text, exact media, or current same-call ToolReturn. The
gate covers oversized optional region descriptions, hidden/de-duplicated node facts, zero-candidate delivery, partial
prefixes, and ordinary full delivery. It does not allow TurnPacker or the provider bridge to ignore missing refs, and
the Catalog's private action routes must equal the manifest route set.

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

Result: `1743 passed / 19 skipped`; Ruff, compileall, and `git diff --check` pass. One pre-existing
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
The already frozen `WA_W2_COHORT_CASES` are exposed unchanged through the formal target-loop suite
`webarena-verified-w2`; `--case-id` selects one member without constructing an ad-hoc manifest or changing the cohort.

The first frozen Task267 execution is a failed pre-repair diagnostic:
[`run1`](../evidence/live/w2-task-267-deepseek-v4-flash-20260826-run1/run.json) recorded 33 policy calls,
`policy_failure_code=tool_grounding_gap`, zero STOP sends, and zero native evaluator calls. Its final current World had
144 targets. The failure was not absent task/history evidence: the policy had already recovered Acadia relation
`2176999`. The final compact delivery duplicated one focused textbox as two route candidates (`type_text` and
`press_key`), displaced a different control, and then treated the model's schema-valid `activate(textbox)` semantic
rejection as JSON representation repair.

The provider-free repair changes only the owners of those meanings. Delivery now emits one target subject per E-ref
with complete current verbs while retaining every private route for Catalog resolution. A resolver-produced
`tool_grounding_gap` becomes the existing same-call `ToolRejectedResult` and reaches the next Recording FunctionModel
turn without repair or GUI dispatch. Restricted `goto` rejection is now
`NOT_SENT/destination_outside_environment`, distinct from malformed parameters. Prefix/property tests prove target
uniqueness and verb completeness; vertical tests prove same-call pairing and zero dispatch.

Task267
[`run2`](../evidence/live/w2-task-267-deepseek-v4-flash-20260826-run2/run.json) is an environment-only diagnostic:
`libwebarena==0.0.5` declares `beartype==0.12.0`, but an unrelated top-level package had upgraded the dedicated
BrowserGym environment to `beartype==0.22.9`. WebArena failed during import before Agent construction, with zero model
calls and zero executions. The unrelated package was removed and WebArena's declared dependency restored; no Agent
code or benchmark semantics changed.

Task267
[`run3`](../evidence/live/w2-task-267-deepseek-v4-flash-20260826-run3/run.json) is the accepted post-repair witness at
commit `f20712bc`. It completed 41 valid single-call policy turns, 18 GUI executions, 20 observations, one STOP, and
one native evaluation. The submitted result was relation `2176999` with duration `01:32:00`; the native evaluator
returned `verified_success`. It recorded zero grounding gaps, representation repairs, fallbacks, waits, invalid tool
arguments, multiple-call responses, and context-capacity rejections. Aggregate total tokens were `735,955` and wall
latency was about 516 seconds. Task267 is therefore accepted, while the broader W2 cohort remains open until untouched
cases pass without case-specific production changes.

Task97
[`run1`](../evidence/live/w2-task-97-deepseek-v4-flash-20260826-run1/run.json) crossed the Task267 owner repairs in an
untouched case. A schema-valid current-Catalog mismatch returned a same-call `ToolRejectedResult`, and a restricted
destination returned `NOT_SENT/destination_outside_environment`; neither entered representation repair or dispatched
the rejected action. The policy then identified MIT as the 2019 SCImago target and selected its Wiki result. The next
fresh World failed during canonical projection with `ValueError: public reference capacity exceeded`. Formal status
is `failed / harness_projection / case_projection_failed` after about 441 seconds. The trace contains 50 completed
steps; zeroed case metrics are an unmeasured-result projection after the CoreLoop exception, not zero preceding work.

The shared root was an algebra mismatch at the one public-ref owner. The lossless current World admits a finite
inventory without a 9,999-record limit, while `PublicRefCodec` accepted only four-digit E/N/F/R ordinals. Task266's
earlier semantic/structure alias repair reduced duplicate identities but did not make that independent ceiling valid
for all accepted pages. The codec now represents every positive generated ordinal and owns one reusable token grammar
consumed by history sanitization, benchmark support, and test recorders. Current Catalog resolution remains closed:
`E10000` is schema-valid, but when absent from the current resolver it returns typed `GROUNDING_GAP` and cannot reach
Binder or Executor. A full-owner regression projects 10,001 semantic targets, linked structure records, and public
labels without truncation. No page-size branch, larger arbitrary threshold, World cap, evidence/cursor path, harness
fallback, or task/site special case was added. Task97 remains empirically open until an authorized post-repair run
crosses the original Wiki transition and completes native evaluation.

Task97
[`run2`](../evidence/live/w2-task-97-deepseek-v4-flash-20260826-run2/run.json) crossed the public-ref repair and retained
ordinary typed control flow: 60 policy calls, 23 observations, 22 executions, zero grounding gaps, zero waits, and zero
representation repairs. It nevertheless reached the 1,204-second case timeout before STOP or native evaluation and
consumed 951,547 aggregate tokens. This is the failed pre-lifecycle-repair witness for the large-page subsystem, not
evidence of a provider or BrowserGym hang.

The final traced World has 11,766 targets, 4,083 actions, and 12,404 structure nodes. Exact profiling found
`WorldDeliveryIndex._source_order` performing 618,890 complete-source scans, consuming about 73.4 of 78.6 seconds.
The same index and the lossless model/grounding/actor projections could then be reconstructed in transition,
same-World discovery, and fallback page paths because the constructed after-World index was not retained by
`RunState`. The earlier Task266 local replay measured one full chain only and therefore did not verify this
one-observation/many-turn lifecycle.

The owner repair builds one source-order map and one immutable observation-scoped derivation bundle, carries the exact
after index through `StepResult`, and reuses both for all same-World policy and local-tool turns. Fresh World identity
atomically invalidates the bundle. On the exact run2 World with all 4,083 actions, index construction falls from about
71.9 to 1.7 seconds while preserving 644 regions; canonical projection is 1.7 seconds, one-time static projection 2.7
seconds, and a subsequent context turn 2.2 seconds. Lifecycle, discovery, and transition tests forbid redundant
reconstruction. No threshold, truncation, VLM, cursor, evidence inventory, retry, or benchmark branch was introduced.
Task97 remains open pending a fresh live witness.

Task97
[`run3`](../evidence/live/w2-task-97-deepseek-v4-flash-20260826-run3/run.json) crossed that performance boundary and
completed normally in about 116 seconds. It recorded 29 policy calls, 12 observations, 11 executions, 447,639 aggregate
tokens, zero waits, zero grounding gaps, zero representation repairs, and no STOP or native evaluation. The model did
repeat its research strategy despite retained history: Harness compaction preserved that the SCImago article lacked
the 2019 list, both failed search strategies, and the still-untried `College and university rankings` candidate. That
semantic planning weakness is not evidence loss or a Runtime fact to infer.

The terminal `blocked / control_stalled` was nevertheless a Runtime counterexample. After the repeated article reads,
the final `find_controls("search")` returned the current Wikipedia textbox with both executable verbs, but Monitor
blocked the producing step with `same_attempt_streak == 1` and `recovery_attempt == 3`. The shared cause was the
alternate-attempt accumulation introduced in `d7546ba4`: different no-information queries and routes preserved the
episode, but also consumed a hidden `max_recovery_retries` budget. That let Monitor judge a multi-step semantic recovery
without understanding it and prevented the ToolReturn from reaching the next ordinary policy turn.

The owner repair keeps recovery active across different public attempt signatures without incrementing a semantic
attempt budget. Exact attempt replay, typed prohibited-call replay, and recurrence of a proven GUI cycle remain
bounded; the existing TaskGoal turn budget remains the generic fallback. A generated property covers arbitrary unique
query sequences and a CoreLoop vertical gate covers two empty results -> nonempty current control discovery -> next
ActionPolicy turn -> dispatch -> fresh native-complete World. No tool-specific branch, threshold increase, World,
history, cursor, ToolReturn, PydanticAI, BrowserGym, or benchmark behavior was added. At that checkpoint Task97
remained open pending a fresh post-repair witness.

Task97
[`run4`](../evidence/live/w2-task-97-deepseek-v4-flash-20260826-run4/run.json) is the accepted post-repair witness at
commit `c0158be2`. Formal acceptance is true and the case ended `done / verified_success` after about 583 seconds. It
made 67 valid single-call policy turns, 24 GUI executions, 26 observations, one STOP, one post-STOP capture, and one
native evaluation. It recorded zero waits, grounding gaps, representation repairs, fallbacks, invalid arguments,
stale catalogs, and context-capacity rejections. Aggregate total tokens were 1,142,228. This live-validates the exact
run3 handoff that had been cut short: different recovery attempts no longer form a Runtime semantic budget, while the
Agent remains bounded and reaches native completion. The exercised Task97 path is accepted; broader W2 correctness
and efficiency remain open.

Task265
[`run1`](../evidence/live/w2-task-265-deepseek-v4-flash-20260826-run1/run.json) is a failed pre-repair provider-boundary
witness. It timed out after 60 valid policy calls, 19 executions, 20 observations, 13 recovery calls, zero waits,
fallbacks, grounding gaps, invalid arguments, and context-capacity rejections, without STOP or native evaluation. Its
exact provider trace contains eleven deliberate ActionPolicy attempts. Each requested enabled thinking, but every one
was physically admitted and recorded as disabled with no reasoning content/tokens. The selected recovery profile was
therefore not reaching DeepSeek; this run does not establish that a second planner, progress channel, memory, or
Monitor semantic judgment is required.

The owner repair adds DeepSeek to the existing canonical per-call thinking mapping. Ordinary and representation-repair
calls stay non-thinking; the existing first-call-per-recovery-event deliberate profile reaches PydanticAI as
`thinking=true`, which the installed SDK maps to DeepSeek's `reasoning_effort` wire field. PydanticAI continues to own
typed reasoning/tool parsing and paired history replay. Trace observation now reads `ThinkingPart` and normalized
reasoning usage instead of hard-coding `false/0`, including the bounded output-validation retry path. Mock-wire,
history-roundtrip, profile-algebra, accepted-response, and retry-response tests cover the positive contract. No
Task265-specific code, Replanner, Runtime branch, new state, or history/World/Monitor change was introduced. Task265
remains open pending separately authorized live validation.

Task268
[`run1`](../evidence/live/w2-task-268-deepseek-v4-flash-20260827-run1/run.json) is a failed fresh long-horizon witness
at commit `3a2820c8`. Formal acceptance is false and the case ended `blocked / incomplete` at the 100-turn budget. It
recorded 100 valid single ToolCalls, 22 executions, 23 observations, 40 no-progress increments, zero invalid tool
arguments, zero grounding gaps, zero representation repairs, zero waits, zero fallbacks, and zero context-capacity
rejections. There was no STOP, post-STOP capture, or native evaluator call. The 117 provider attempts comprise 100
ActionPolicy calls and seventeen Harness compactor calls. Aggregate total tokens were 1,753,888, including 1,654,113
history tokens, and wall time was about 585 seconds.

The trace separates this failure from the earlier DeepSeek wire defect. Twenty deliberate physical ActionPolicy calls
all recorded enabled thinking and returned reasoning content. The Agent recovered from the unavailable external OSRM
route, used the provided OpenStreetMap directions UI, and obtained `Distance: 169km. Time: 10:57`. It later resolved
the Acadia result link to `/relation/2176999`. Policy turn 77 explicitly stated both final values and converted the
duration to `10:57:00`, but then navigated back to a fresh empty directions form solely to verify the exact duration
again. It rebuilt the route and received `Time: 10:57` once more on turn 100, when the task turn budget terminated the
run before a subsequent submission call.

The same trace exposes an independent efficiency defect in the existing history owner. Its seventeen
`expired_model_prose` compactor calls compared expired input prose against the 1,024-token summary *output* cap, so a
few ordinary responses retriggered a provider summary of nearly the same prefix. Several summaries used their
eight-fact quota for current controls, form state, and environment restrictions while omitting the exact requested
duration even though the compactor input contained `Time: 10:57`.

The bounded repair stays inside the existing owners. ActionPolicy now gives supported finalization priority over
uncontradicted re-verification. Harness compaction now prioritizes exact values that fill final-answer fields over
transient execution setup, and its expired-prose arm waits for one complete recent-suffix input budget rather than
reusing the output cap. No Replanner, mutable progress state, Monitor semantic rule, World projection, cursor,
ToolReturn path, or Runtime branch was added. Provider-free focused tests pass. This repair is implementation-complete
but was not yet live-accepted at that checkpoint.

Task268
[`run2`](../evidence/live/w2-task-268-deepseek-v4-flash-20260827-run2/run.json) failed immediately after one
observation, one ordinary ActionPolicy call, and one representation-repair call, with zero executions and zero valid
ToolCalls. The ordinary DeepSeek response proposed `search_page_content(query="Vinalhaven", cursor="",
region_ref="R3")`; the repair response correctly pruned only the unsupported `region_ref` and returned
`search_page_content(query="Vinalhaven", cursor="")`. It was nevertheless rejected as `invalid_tool_arguments`.

The defect was the representation-repair semantic guard requiring the second physical provider response to reuse the
first response's call ID. Real providers generate a new ID for the new response; the prior Recording model's
`repeat_last_gui_call` fixture reused the old ID and hid the gap. The owner repair treats call ID as wire lineage while
requiring operation and every schema-declared argument to remain unchanged. The accepted repaired response and its
future ToolReturn use the new ID. A provider-free vertical test covers distinct initial/repair IDs through local-tool
resolution and pending PydanticAI history. No search, normalizer, Catalog, resolver, ToolReturn, or CoreLoop behavior
changed. Run2 is a failed pre-repair witness, not evidence about the Task268 semantic-completion repair.

Task268
[`run3`](../evidence/live/w2-task-268-deepseek-v4-flash-20260827-run3/run.json) is the accepted post-repair witness at
commit `966fe598`. Formal acceptance is true; the case ended `done / complete`, cleanup succeeded, and the native
evaluator returned `verified_success`. It completed after 69 valid single-call policy turns (59 ordinary and ten
recovery), 25 executions, 28 observations, one STOP, one post-STOP capture, and one native evaluator call. The final
submission was `[{"relation_id":2176999,"duration":"10:57:00"}]` under the required public envelope.

Run3 crossed both fresh counterexamples. Its one representation-repair response used a valid new provider call ID and
continued with zero invalid-argument failures. ActionPolicy retained the exact final values and submitted instead of
reopening the completed route. Harness compaction ran once rather than run1's seventeen times. Wall time fell from
about 585 seconds to 361 seconds; aggregate tokens fell from 1,753,888 to 1,631,827. The exercised Task268 paths are
live-accepted. The broader W2 cohort and aggregate-token efficiency remain open; this single success does not
authorize case-specific code or claim campaign stability.

Task740
[`run1`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run1/run.json) is the first unseen frozen W2
post-repair witness, run at commit `1ee18bfa`. Formal acceptance is true; Runtime ended `done / complete`, cleanup
succeeded, and the native evaluator returned `verified_success` after one STOP and one post-STOP capture. The Agent
identified Madison Square Garden, read its official Wiki coordinates, read Carnegie Mellon University's official Wiki
coordinates, switched to the provided OpenStreetMap tab, entered both decimal coordinate pairs into the OSRM
directions form, submitted it, read the resulting route, and finalized. The 29 valid policy turns comprised 11 GUI
executions and seven bounded page reads, with zero recovery calls, waits, grounding gaps, fallbacks, invalid arguments,
stale catalogs, or context-capacity rejections.

The first provider response proposed two content searches. The existing single-action boundary executed neither
envelope directly; one representation repair retained the first supported search with its own call ID and normal
same-ID result history. All later responses contained one accepted ToolCall. The semantic trajectory did not revisit
Wiki pages after entering OSRM and did not repeat a failed route. The reported `no_progress_count=8` reflects local
read/discovery steps that intentionally leave the fresh World unchanged, not eight repeated semantic attempts; Monitor
never entered recovery. Wall time was about 216 seconds and aggregate tokens were 706,384. This independent success
falsifies a Task268-only explanation for the repaired control path, but one unseen case still does not establish the
declared multi-case held-out cohort or close aggregate-token efficiency.

Run1 is also the frozen pre-optimization efficiency baseline. Its formal estimator accumulated 772,712 history tokens
across 29 ordinary calls. Offline replay of the exact provider inputs under the post-run owner contracts removes 100
stale historical World prompts, about 213,428 conservative tokens, and reduces repeated ToolReturn AX representation
from about 422,526 to 300,666 conservative tokens, another 121,860. These disjoint reductions total 335,288 tokens,
or a 43.4% lower bound against the old accumulated history count; earlier high-water compaction can reduce the live
total further. The tab-domain schema change merges one of seven observed Catalog variants but does not remove other
legitimate current-capability variants. This is offline replay, not a post-change live result, cost promise, or
wall-time claim.

The authorized post-change Task740
[`run2`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run2/run.json), at commit `e758adf9`, is a failed
correctness witness and a useful bounded-context measurement. It ended `blocked` after 44 policy turns, 18
executions, seven page requests, five recovery turns, one wait, and zero STOP/native-evaluator calls. Despite 15 more
policy turns than run1, formal prompt tokens were 629,414 rather than 702,419 and accumulated history tokens were
663,642 rather than 772,712. The first identical World used 6,142 provider prompt tokens rather than 9,282. Unique
ActionPolicy provider responses report about 378k cached and 252k uncached input tokens (60.0% cache hit), versus
about 348k cached and 355k uncached (49.5%) in run1. Different semantic trajectories prevent treating those numbers
as an aggregate-token closure.

The trace rules out lost progress or compaction corruption. The compaction summary retained Carnegie Mellon
University as `40.4425, -79.9433`, and the continuing ActionPolicy still stated both exact Wiki values. It nevertheless
reordered them to `lon,lat` based on a presumed OSRM backend convention before filling OSM's GUI search fields. The
route never appeared; later turns also treated `active=false` as non-executable despite current supported verbs. The
general owner-level repair is prompt version `grounded-agent-context.v39`: preserve an exact source representation
for GUI entry absent an explicit task/current-interface conversion contract, and use E-ref verbs as executability
authority while reserving `disabled=true` for unavailability. No task/site/coordinate branch, new state, or alternate
tool path was added. Focused prompt/PydanticAI integration tests pass; a fresh authorized live run remains required
before restoring correctness acceptance for the optimized cutover. The post-repair focused suite passed 310 tests;
the full suite passed 1,807 with 19 skips and only the pre-existing documentation-governance failure caused by the
unmaintained `docs/interaction-shell.md` file outside the five-document allowlist.

The authorized v39 Task740
[`run3`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run3/run.json), at commit `33241be8`, crossed the
repaired GUI semantics but is not accepted. It preserved the two Wiki coordinate pairs as `lat, lon`, filled the OSM
directions form, submitted it, produced route region `R9`, and read records 1–20 and 21–38. Formal context use remained
below run1 despite four additional policy turns: prompt tokens were 526,977 versus 702,419, accumulated history was
524,062 versus 772,712, and aggregate tokens were 531,429 versus 706,384. Different paths and 355.8-second wall time
still preclude an aggregate efficiency or latency closure.

Run3 failed on policy turn 33 with zero STOP/native-evaluator calls. GoalCompiler's advisory final item said to deliver
route details in the final response even though the authoritative task asks to view the route on the map. ActionPolicy
therefore selected `RETRIEVE` rather than `NAVIGATE` and attempted to place all 37 route instructions in
`retrieved_data`; the physical `submit_final_response` call exhausted the existing 1,024-token output bound before its
JSON arguments closed. This is not missing evidence—the route was already complete—and not a reason to enlarge the
output cap. It reopens the existing GoalCompiler/ActionPolicy finalization contract: response-envelope text must not
be compiled as a user outcome, and advisory GoalPlan prose cannot override TaskGoal classification or requested final
payload. No task-specific repair is authorized by this witness.

At that checkpoint the corresponding owner repair was implemented locally but was not yet a live acceptance claim. The
WebArena-Verified response codec removes the exact upstream response-schema suffix before BrowserGym publishes the
public task instruction, so GoalCompiler and ActionPolicy receive the original semantic intent rather than a mixture
of task and provider envelope. The codec's bounded, upstream-schema-derived `FinalAgentResponse` guidance is delivered
through the existing `submit_final_response` ToolSpec and included in its Context/ToolCatalog identity; it does not
enter TaskGoal, GoalPlan, history summary, or a separate finalizer episode. Prompt `grounded-agent-context.v40` makes the remaining
authority explicit: response protocol controls representation, while TaskGoal alone determines task type and
requested payload. Focused tests pass 440/440 with 11 skips. The full suite has 1,809 passes and 19 skips with only
the previously recorded unrelated `docs/interaction-shell.md` governance failure. Task740 run6 below subsequently
supplied the required bounded `NAVIGATE/SUCCESS` native-evaluation witness.

Task740 `run4` was an invalid launch attempt: Python multiprocessing could not spawn the BrowserGym child from a
`<stdin>` main module, so no benchmark case began and it supplies no behavioral evidence. The file-backed `run5` did
begin normally at commit `7bf34249` and crossed the GoalCompiler/final-response repair. The Agent found CMU and
Madison Square Garden, retained both exact coordinates, opened the OSM directions page, filled both inputs with
postcondition-satisfied actions, and dispatched `Go`. This rules out the run3 task/envelope conflation as run5's
failure.

Run5 was stopped after 67 model turns and 66 completed steps once its exact loop was proven. From the first `Go`
response onward, the model emitted the same semantic action text and call 43 times. The first click produced a real
fresh semantic World; every later completed click kept the same identity-free World digest and the same screenshot
SHA-256. Nevertheless each OSM capture reconstructed enough DOM/AX nodes to produce 583 raw public target changes and
1,042 identity-keyed fact changes. `ProductionActionOutcomeProjector` selected 521 current structural refs and
reported `ObservedChange.CHANGED`; Monitor consequently reset its attempt streak on every step and emitted zero
recoveries. The final `run_error` records the manual interruption and is not an environment or provider diagnosis.

The owner repair keeps both meanings explicit without another state channel. Raw `PublicWorldDelta.changed` continues
to conserve identity/fact lineage. Its derived `semantic_changed` compares the existing identity-free before/after
digests. ActionOutcome structural promotion is now gated by that semantic fact, and the visual verifier treats a
semantically equivalent re-keyed target as unchanged. Step history and Workspace use the same derived bit; Trace
reports both raw churn and semantic change. Monitor is unchanged and therefore receives `UNCHANGED/UNKNOWN` for the
repeated attempts, recovers on the second equivalent replay, and can reject another exact attempt through the existing
typed recovery contract. Generated re-keying properties plus focused BrowserGym/Agent/Evaluation tests cover the
full owner/consumer chain (`551 passed / 3 skipped`); the full suite reports `1,813 passed / 19 skipped` plus only the
known documentation-governance failure above. No OSM/task/label branch, Replanner, cursor, evidence inventory, retry,
or additional model role was added.

The authorized fresh Task740
[`run6`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run6/run.json) is accepted. It completed in 56 policy
calls, 33 executions, 35 observations, and about 443.5 seconds. The trace records six existing `control_stall`
recoveries: after the first real coordinate-result transition, equivalent repeat clicks were no longer promoted from
raw ID/fact churn to progress. ActionPolicy left that route, found `Find directions between two points`, filled CMU
`40.4425, -79.9433` and Madison Square Garden `40.7506, -73.9936`, activated `Go`, read the route, and submitted the
typed final response. Native evaluation is `terminal_success / verified_success`; cleanup succeeded and suite
acceptance is true with no errors. This is fresh closure evidence for the repaired effect/Monitor invariant, not an
efficiency claim: the run still used 896,290 total model tokens (873,335 prompt and 22,955 completion), including
572,288 prompt-cache-hit tokens recorded in the provider transcripts.

Run6 is the frozen pre-repair witness for the provider/history efficiency defect. Four deliberate responses
generated long private reasoning while retaining short public text conclusions; replay of the surviving reasoning
accounts for roughly 120k conservative prompt tokens. Six ordinary text-only output truncations also entered the
existing PydanticAI retry, while a deliberate retry with `thinking=true + tool_choice=required` is rejected by the
DeepSeek wire contract. The owner repair keeps every initial request at `auto`, changes only an output-validation retry
to `thinking=false + required`, and expires private reasoning only after its response has a same-ID ToolReturn and its
own public text conclusion. The pending exchange, public progress text, calls, returns, raw Trace, and existing Harness
50%/15%/30%/12% schedule remain; later closed noncurrent exchanges retain pair identity and semantic content without
operational handles. A real OpenAI-compatible wire test and generated 2--12 turn history properties
exercise these invariants.

The authorized Task740
[`run7`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run7/run.json) is the first fresh live witness. It
completed native evaluation as `terminal_success / verified_success` in 28 policy calls, 11 executions, 13
observations, and about 221.4 seconds, with zero waits and zero output retries. Total model use fell from run6's 896,290
tokens to 403,528. Its deliberate response retained private thinking through the immediate same-ID ToolReturn delivery;
the following request omitted only that closed thinking while retaining its public text, call, and return. This verifies
the temporal history contract without forcing the initial call or deleting progress.

Task759
[`run1`](../evidence/live/w2-task-759-deepseek-v4-flash-20260827-run1/run.json) then supplied a genuinely held-out
failure witness at another existing owner. The Agent completed the requested Boston-to-NYC map route but classified
the overall work as `MUTATE`; the pinned `webarena_verified.types.FinalAgentResponse` schema defines showing a
page/location as `NAVIGATE`. The codec had reduced that upstream definition to enum names, leaving the model to infer
meaning from unrelated allowed effects. `WebArenaVerifiedFinalResponseCodec` now derives its bounded ToolSpec guidance
from the installed upstream Pydantic schema itself; TaskGoal, GoalPlan, Runtime, evaluator, and control flow are
unchanged. The first rerun (`run2`) failed locally before a provider call because the real composed ToolSpec exceeded
the former 500-character generic description bound. The description remains bounded at 1,024 characters, and a new
codec-to-Context-to-Catalog integration test compiles the real `submit_final_response` ToolSpec so this cross-owner
composition cannot regress silently.

Task759
[`run3`](../evidence/live/w2-task-759-deepseek-v4-flash-20260827-run3/run.json) completed the same held-out task as
`NAVIGATE/SUCCESS`, with native `verified_success`: 29 policy calls, 12 executions, 14 observations, about 146.0
seconds, and 272,963 total model tokens. A final Task740
[`run8`](../evidence/live/w2-task-740-deepseek-v4-flash-20260827-run8/run.json) after that schema-owner repair also
completed `NAVIGATE/SUCCESS` with native `verified_success`, 43 policy calls, zero waits, zero fallbacks, and zero
grounding gaps. Its 713,559 total tokens are below run6 but above run7, so correctness/history closure is supported
while per-run efficiency variance remains real; no stronger universal token-reduction claim is made.

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
5. Does physical PydanticAI history preserve bounded completed accepted call ID/result pairs and their semantic
   values, append the current same-call result, exclude old World prompts and noncurrent operational handles, and
   clear on terminal completion?
6. Does a multi-call response retain every exact proposal in raw Trace and its paired identity in model history,
   resolve and dispatch only its first call, pair later calls with same-ID native failed returns on the next turn,
   and create no Runtime queue or fallback?
7. Does every route explicitly returned by a same-World `find_controls`, `read_region`, or `search_page_content`
   ToolReturn enter the same frozen manifest/catalog only after intersecting the current ActionSpace, including when
   the soft target cannot admit unrelated optional inventory?
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
15. Are browser-global actions selected explicitly by the environment profile and executed through BrowserGym's
    existing ActionSpace/Binder/Executor path, with unrestricted generic navigation and WebArena's configured netlocs
    preserved identically through World, ActionBinding, Catalog, and resolver?
16. Does SDK history preserve exact pending/tool-only thinking, call/result pairing, and semantic values; remove
    operational handles only from closed noncurrent exchanges; expire closed private thinking only behind its own
    retained public conclusion; use the complete RequestAdmission capacity arm plus the declared history
    high-water/minimum-reclaim arm for Harness pair-safe compaction; and restore raw projected history on summary
    failure?
17. Can a large PageMap report honest partial coverage within one aggregate bound while the existing `list_regions`
    tool recovers the complete current region index?
18. Does every current non-entity `InteractionSubjectKind` already present in Actor World reach the same compact
    observation—including authoritative active-tab and public index-to-route state—without a per-tool renderer branch
    or second browser-state channel?
19. Does element currentness ignore state outside the selected offer's declared semantic contract, leave physical
    actionability to BrowserGym/Playwright, and turn typed pre-dispatch stale into one fresh capture with zero replay?
20. Does Monitor issue bounded recovery for no-information families and every dispatched GUI cycle representable in
    its fixed window, persist the episode across different empty/no-match and ineffectual same-World attempts without
    turning their count into a semantic budget, block exact replay or proven cycle recurrence, project dispatch from
    the real receipt, and start a new same-World episode only on typed new information, a proven GUI effect, or a
    causal GUI dispatch reaching a changed fresh public World?
21. When a BrowserGym action changes the active tab, do post-action stability, observation, physical enrichment, and
    transition URL all come from BrowserGym's one current page rather than joining pre- and post-action tabs?
22. On a large unchanged World, does Monitor findings derivation scale with targets plus facts, avoid region-index
    construction for the empty transition, reuse the current index on the next turn, and preserve the exact digest?
23. Does Trace store one deduplicated full observation and one exact provider transcript while excluding policy
    snapshots/canonical projections from step payloads and reporting honest counts/truncation for transition summaries?
24. Does a typed BrowserGym stable navigation cross the generic execution contract into Projector verification while
    private trace strings remain non-authoritative and confirmed change still resolves against the fresh World?
25. Does a WebArena provider terminal snapshot stop the loop before another policy call regardless of agent STOP, and
    can any typed non-dispatch terminal failure still be projected as `failed=false` or omitted from its ToolReturn?
26. Are BrowserGym tab titles and sanitized routes paired by their native index in the one current World, with route
    identity retained, title-only drift excluded from binding identity, and navigation legality owned only by Catalog?
27. Does DeepSeek receive the declared output limit as `max_tokens`, map ordinary/repair calls to disabled thinking and
    the existing deliberate recovery profile to enabled thinking, allow exact model text/reasoning with a ToolCall on
    the initial `auto` request, and change only a text-only PydanticAI retry to `thinking=false + required`; and does
    current pending reasoning/tool history round-trip while closed private reasoning expires only behind a retained
    public conclusion, retry exhaustion remains a typed bounded failure without polluting accepted history,
    miscounting historical responses, or nesting a representation-repair retry?
28. When a query token is both one control's exact label and another control's operation, does `find_controls`
    preserve the exact-label match while still enforcing explicit role/operation constraints and returning every
    genuine current match?
29. Do ActionPolicy and Harness compaction consume one prompt-owned evidence-status rule without Runtime converting
    summary prose into claim state, and does GoalCompiler disable thinking only through the selected provider's
    declared wire capability?
30. Does physical SDK history contain exactly one current task/plan anchor and no historical World/media prompts,
    while retaining model progress, ToolCall/ToolReturn pairing and semantic results, exact pending/tool-only thinking,
    and the unresolved suffix; deground only closed noncurrent exchanges; and supply exactly one fresh World with
    current media?
31. Does every admitted action-delivery prefix render each E-ref once with the complete current verb set while leaving
    the Catalog resolver with exactly the manifest's route set?
32. Does a schema-valid operation/target mismatch return the existing `ToolRejectedResult` under the original call ID
    to the next ordinary PydanticAI turn, without representation repair, Binder/Executor dispatch, or terminal policy
    failure?
33. Does restricted BrowserGym navigation reject an out-of-scope destination as
    `NOT_SENT/destination_outside_environment`, preserve zero dispatch, and allow the same policy to reselect?
34. Can every record in an accepted finite current World receive one generation-local E/N/F/R ordinal without an
    independent smaller codec capacity, while an unknown well-shaped ref still fails at the current Catalog resolver?
35. When exact supported values fill every requested final-answer field, does ActionPolicy submit without reopening a
    source solely for formatting or confirmation; does Harness retain those values ahead of transient execution setup;
    and can history compaction trigger only after the declared high-water and minimum-reclaim hysteresis rather than a
    result kind, semantic event, or summary-output cap?
36. Can representation repair keep the operation and every schema-declared operand unchanged while accepting the new
    provider-generated call ID of its own physical response, with the later ToolReturn paired under that same new ID?
37. When a dynamic page re-keys DOM/AX targets while preserving identity-free World meaning and the screenshot, do
    ActionOutcome, model-visible step history, Workspace, Trace, and Monitor agree that no semantic effect occurred,
    while a genuine semantic or visual transition remains `CHANGED`?

## Exit statement

Passing this document's provider-free gates plus the recorded Task27 run2, Task266 run37, and Task7 run2 live witnesses
permits describing the exercised thin result, bounded recapture, stable-navigation, TaskGoal projection, and typed
history-compaction paths as verified. It does not permit describing the whole GUI agent or benchmark campaign as
stable across untouched cases. That status changes only after the declared held-out cohort passes without
case-specific production branches.

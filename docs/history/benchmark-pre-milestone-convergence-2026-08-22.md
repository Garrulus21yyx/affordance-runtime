# Benchmark history: pre-milestone convergence (archived 2026-08-22)

> Non-normative archive. This file preserves the former benchmark document and its chronological run evidence.
> Current gates and execution order are maintained only in [`../benchmark.md`](../benchmark.md).

## Normative current gate (2026-08-22)

This section is the sole normative benchmark gate. The dated material below is a historical evidence appendix. Current
status is **pre-live convergence gate passed; W1b non-closed; live Task-7 not run**.

Runtime-to-benchmark product flow is exactly:

```text
committed RunState → EpisodeSnapshot → BenchmarkCaseResult → SQLite commit
                                          └→ harness-only cleanup/persistence/watchdog/native-evaluator facts
```

Benchmark projection must not inspect decision class names, maintain a decision whitelist, split atomic and compound
counting, use instrumentation or trace as a Runtime-state fallback, or read Mission/Run result objects to recover facts
absent from `EpisodeSnapshot`. Physical environment instrumentation remains an independent conservation oracle only.
Cleanup, JSON export and remote viewer finalization occur after the preliminary durable result and cannot erase it.

Pre-live exit properties are:

| Property | Required evidence |
|---|---|
| decision closure | every `DecisionKind` traverses StepResult → RunState → history → trace → snapshot → benchmark |
| receipt conservation | atomic/compound complete, partial, cancelled and sent-unknown dispatch counts equal committed receipt, snapshot and benchmark counts |
| state matrix | generated legal/illegal StepResult combinations, including rejection of `RUNNING + yield_reason` |
| budget | ordinary 8 and explicit 15 accepted; mission 16 rejected before policy/evaluator; standalone budget unaffected |
| viewer isolation | Full, ValueError, BrokenPipe, EOF/OSError, dead/hung child and repeated close cannot change or delay outcome |
| held-out behavior | compound form, non-form, partial/cancellation, non-Task-7 route regression and independent fresh-context audit |
| provider parity | every supported profile passes the PydanticAI path before compact-JSON deletion |

Unit/full-suite success is necessary but not closure. All declared ActionPolicy profiles now use the sole PydanticAI
product path; `json_single_command` is rejected and the local HTTP benchmark uses native tool calls. G6 held-out and
the repeated independent audit passed. This permits a separately requested live witness; it does not convert the
provider-free gate into task-success evidence.

The first independent fresh-context audit was **FAIL**. It produced held-out counterexamples for open local-tool
decision labels, malformed receipt completion combinations, policy cancellation escaping the commit boundary,
delivery-index construction without the complete ActionSpace, and benchmark reconstruction from mission fields.
Those repairs subsequently passed the repeated held-out audit; the earlier green suite alone was not closure evidence.

A second held-out pass found and reopened post-dispatch evaluator receipt loss, overlapping PARTIAL/CANCELLED batch
shapes, and Abort snapshot projection. The corresponding owner repairs and conservation regressions pass, and the
independent auditor replayed the exact stable-tree counterexamples successfully. No live run was performed in this
verification cycle.

## Purpose

Benchmarks are the final evidence for task capability, generalization, robustness, and adaptive-observation value.
Unit, property, and architecture tests protect contracts; they do not substitute for live GUI execution.

## Primary questions

1. Does the agent complete supported GUI tasks?
2. Can ActionPolicy infer task-relative advance, regression, and readiness from fresh World plus bounded local
   transitions, without a Runtime-owned progress state?
3. Does adaptive observation preserve or improve success relative to structured-only observation?
4. Does it reduce visual calls, model tokens, latency, or unnecessary acquisition?
5. Can it recover when evidence is insufficient, an action has an unknown effect, or a long task changes regime?
6. Can it preserve complete current-episode history, exact cross-page values, and evidence-backed cross-episode working outcomes
   without exposing stale GUI refs, hidden evaluator state, or another completion authority?
7. On complex real pages, does full World preserve source truth, does lossless public Actor normalization conserve the
   supported public algebra, and does bounded `WorldDeliveryView` preserve or recover every offered target,
   decision-relevant state, and required structural context?

## Required report

Every live run records, per case:

- task and seed from a predeclared manifest;
- terminal status and official environment success;
- action, observation, and model-call counts;
- source selections by modality;
- visual supplementation and recovery counts;
- tool-capability reachability from registry definition through surface support, current eligibility, direct exposure
  or paging/search, selection, and dispatch, including a typed absence/hidden reason;
- for every real-page observation: source/World/Actor structural counts, coverage state, offered-action target count,
  offered targets missing from Actor View, action-decision-state coverage, semantic-group/structural-closure failures,
  action-page or read-recovery use, and the selected screenshot route;
- for long-horizon runs: mission rounds, episode boundaries, compact-history/fold counts, pinned/promoted facts,
  every ManagerReview/optional-Auditor trigger kind, semantic-verifier outcomes, skipped mechanical-verification
  counts, FinalResponseBoundary admission/rejection, STOP/send/post-capture/native-evaluation counts, and role-specific
  model costs (with Finalizer model calls required to remain zero in manager-guided mode);
- complete provider-request tokens split where available across stable instructions, task/plan, Actor View, episode
  memory, native tool schemas, and images; repair amplification, completion tokens, and elapsed time;
- typed environment, provider, Runtime, and task failures.

Published reports must not contain prompts, model responses, selectors, coordinates, credentials, hidden state,
oracle values, expected answers, or benchmark reward payloads exposed to the model.

Local per-case evidence additionally contains a private complete `traces/<case-id>/trace.jsonl` plus
content-addressed media artifacts. This operational trace is not copied into the public report: it records the exact
public model context and tool catalog, typed decision, provider diagnostics, execution, local outcome, and formal
task-evaluation facts, plus causal IDs needed to diagnose a failure. `ModelInvocationResult` is the formal source for
model metadata, all physical attempts, repair diagnostics, and lineage. Each provider attempt contributes its complete
OpenInference-shaped local transcript, including retry, repair-phase, failure, and cancellation input/output where a
physical request began; screenshot payloads remain content-addressed. Trace-write failure
invalidates benchmark evidence but never changes Runtime behavior. The optional official Langfuse/OTel sink receives
a bounded view only after local JSONL recording and never replaces the local trace.

Every core-loop run must additionally record the prompt version, typed-context protocol version, tool-catalog schema version,
Runtime engine, and model-adapter choice as metadata. These values support reproducibility but cannot alter product
behavior. During cutover, `compact-json` and `pydantic-ai` are compared only where the same model supports both wire
contracts, with the same provider, prompt, context, catalog, cohort, seed, and step budget. A model change is reported
as a separate cohort and is not attributed to the adapter.

## Current evidence

### 2026-08-20 BrowserGym run9 uncertain-dispatch counterexample

Run9 is not evidence that the agent needed more steps or another read tool. The first relevant environment fault was a
BrowserGym action dispatch whose `gym_environment.step()` raised after dispatch may have crossed. The old adapter
collapsed the exception to `sent_unknown / execution_failed` without retaining its type, phase, duration, sanitized
message, or traceback reference. Post-action acquisition then failed, and a later cleanup `TimeoutError` was projected
as `case_failure_code=cleanup_exception`, erasing the temporal primary fault from the formal report.

The repaired provider-free contract records one typed dispatch diagnostic and preserves the control result unchanged.
The existing loop consumes the normal post-action acquisition before escalating, permits one additional independent
fresh capture, and asks the existing action-outcome projector whether current public World proves the effect. Proven
effects continue normally. Unknown effects yield recovery; session loss becomes a typed operational failure. Only
registry-declared state-setting actions may be freshly rebound and replayed once after an explicitly unsatisfied
postcondition; generic activation remains zero-replay.

`target-loop-case.v9` records causal order rather than one lossy bucket:

```yaml
primary_failure:
  code: action_dispatch_uncertain
  phase: dispatch_wait
  diagnostic_ref: execution-diagnostic:...
recovery_failures:
  - post_action_acquisition_failed
secondary_failures:
  - cleanup_exception
terminal_failure: environment_unresponsive  # only when fresh capture and health cannot recover
```

The cleanup exception also has a typed cleanup-phase diagnostic. Legacy `case_failure_code` keeps the earlier uncertain
dispatch as primary even if cleanup subsequently times out. Provider-free verification passes (`1329 passed,
19 skipped`; Ruff and `git diff --check` pass), including the internal-safety benchmark projection. No real provider,
live BrowserGym/WebArena task, or live witness has been run. Run9 is historical failure evidence, live
re-verification is pending, and this work remains non-closed.

### 2026-08-20 DeepSeek run7 role-frequency counterexample

Live evidence at `evidence/live/w1b-one-task-0-deepseek-v4-flash-staged-timeout-run7/` reached the correct task result:
the agent set the 2022 filters, observed `Quest Lumaflex™ Band` with order quantity `5`, completed six GUI dispatches,
and made ten ActionPolicy calls that all succeeded on their first provider attempt. The longest policy call was
`19.46s`; there were no timeouts or retries.

The official run failed only after that work. One episode Auditor had already returned `audited_satisfied`; Manager
then requested a second final audit, whose initial and schema-repair outputs both ended `output_truncated`. This
falsifies the current role cadence, not the GUI loop: mandatory Manager/Auditor use on a short single-subtask task and
an unconditional second final Auditor add cost and a new failure surface after sufficient evidence exists.

The attempted replacement made W1b standalone with Manager/Auditor calls `0/0`. Run8 below falsified that choice and
the associated final-response composition. The convergence target defined at that point expected one initial Manager call and one
episode-boundary ManagerReview call for a normal one-episode W1b retrieval, no Auditor, no separate Finalizer model
call, one mechanical FinalResponseBoundary admission, one STOP/send, and one native evaluation. Additional
ManagerReview calls require a meaningful new episode exit;
an independent Auditor requires an explicit strict-verification policy for a high-risk or durable ambiguous claim.
The former provider-free role-frequency result remains historical local evidence but is superseded. Run10 then
reopened terminal composition; the direct ManagerReview response path was subsequently implemented and provider-free
verified at expected role frequency `2/0/0` (Manager/Auditor/Finalizer). Run5 separately reopens the mode-specific
Manager output/reasoning and teardown contracts; W1b/W2 remain blocked/non-closed on those gates.

### 2026-08-20 DeepSeek run8 Manager/final-response counterexample

Run8 at `evidence/live/w1b-one-task-0-deepseek-v4-flash-staged-timeout-run8/` was manually stopped after the model had
already reached the correct filtered result but entered repeated `read_region(R4/R7)` calls. Removing the initial
Manager made route discovery slower than the manager-guided successful GUI traces. More importantly, every final
model turn advertised `runtime_controls=["final_response"]`, while the JSON-single-command provider path still
offered only ordinary GUI/read tools and accepted only `GroundedToolCommandPayload`. No actual final-response tool
existed in the catalog. The model's final JSON was rejected, and the only legal fallback was to keep reading.

Run8 established that execution turns cannot merely advertise a response capability absent from the actual terminal
contract. The first attempted fix—a final-response-only tool catalog—is now itself superseded by run10. The active
contract is that ManagerReview carries the direct public response object only with `request_finalization`, after which
a mechanical FinalResponseBoundary validates and sends it. This evidence does not justify a larger prompt, another
Auditor, another Finalizer role, or another GUI loop.

### 2026-08-20 DeepSeek run10 finalizer-envelope counterexample

Run10 completed the GUI work and DeepSeek produced the correct public response object:

```json
{
  "task_type": "RETRIEVE",
  "status": "SUCCESS",
  "retrieved_data": ["Quest Lumaflex™ Band"],
  "error_details": null
}
```

The one-turn Finalizer prompt asked for `submit_final_response`, while the compact-json model boundary still required
the generic `{name, arguments}` tool envelope. The direct, schema-correct business object was therefore rejected as
`json_invalid` (`name` missing/invalid and `arguments` missing), after which the mission became blocked and the
official result failed. GUI navigation, date filtering, answer extraction, provider behavior, and answer content were
all correct.

Run10 falsifies the separate LLM Finalizer/tool-envelope architecture. The replacement contract is:

```text
ManagerReview(review_and_route)
  -> route=request_finalization
  -> final_response=<direct public schema value>
  -> final_response_evidence_refs=[...]
  -> mechanical FinalResponseBoundary
  -> one STOP/send -> one fresh capture -> one native evaluation
```

There is no finalizer prompt/model call, finalizing CoreAgentLoop episode, `submit_final_response` catalog entry, or
JSON/native ActionPolicy tool envelope on this path. Provider-free verification now proves the normal W1b synthetic
frequency Manager/Auditor/Finalizer `2/0/0`, one boundary admission, one STOP, one post-STOP capture, and one native
evaluation, plus typed zero-send schema/evidence/latch rejection. This is local implementation evidence only; the
fresh official W1b witness remains pending and the gate remains non-closed.

### 2026-08-20 DeepSeek run4 provider-recovery witness

Live evidence at `evidence/live/w1b-one-task-0-deepseek-v4-flash-recovery-chain-run4/` isolates a provider recovery
gap after successful GUI work. The run made six effectful dispatches with no multi-call, representation, or stale-ref
failure: it opened Reports and Bestsellers, selected `Year`, filled `1/1/2022` through `12/31/2022`, and activated
Filter. The resulting complete current World contained the ranked table headed by `2022 / Quest Lumaflex™ Band /
$19.00 / 5`. The following ActionPolicy call failed before response with `provider_capacity`, `retryable=true`, one
physical attempt, retry count zero, and public projection `policy_provider_unavailable`. The trace did not retain an
HTTP status or safe underlying transport category and reported zero attempt latency. The formal run therefore failed
operationally; it was not a task, GUI, World-read, or turn-budget failure.

The first local repair enabled one aggregate JSON ActionPolicy retry and added safe transport observability. Accepted
and exhausted calls report physical attempts, whether a second request began, retry counts, real elapsed latency,
HTTP status when known, safe exception class, and the closed transport category. Properties covered retry success,
mixed 429-to-503 exhaustion without a third request, remaining-deadline propagation, and terminal failure metadata.
Run5 and run6 below progressively falsified only the timeout composition; supported HTTP/transport retry and its
observability remain owned by the same provider boundary.

The first post-repair run at `evidence/live/w1b-one-task-0-deepseek-v4-flash-provider-retry-run5/` again completed the
same six GUI dispatches and reached the filtered report. Its final failure was now accurately retained as
`timeout / TimeoutError / 30451.054 ms / physical_attempts=1 / second_request_sent=false`, but no retry began. This
falsified the first timeout composition: the 30-second per-request timeout was also the whole provider deadline.

The first corrected composition separated per-request and total deadlines but still repeated the same 4,096-token,
reasoning-enabled request twice at a 30-second cutoff. Run6 at
`evidence/live/w1b-one-task-0-deepseek-v4-flash-provider-deadline-run6/` is the decisive live counterexample. The run
again made six GUI dispatches and its current World contained `2022 / Quest Lumaflex™ Band /
$19.00`. The following ActionPolicy call lasted `61624.115 ms`, made two physical requests, and recorded
`second_request_sent=true`, `transient_retry_count=1`, and benchmark `provider_retry_count=1`. Both requests timed out,
with `http_status=null`, at approximately the configured 30-second client limit. It supplies no HTTP evidence that
DeepSeek was unavailable; it instead falsifies the equal-timeout retry budget.

The new provider-free contract keeps the 90-second semantic deadline but assigns 55 seconds to the initial
reasoning-enabled 4,096-token request and 33 seconds to one 512-token, thinking-disabled fast retry. Both attempts use
the same admitted messages, World, delivery, and catalog; the retry adds no GUI step or semantic re-planning. Timeout
is no longer retried identically inside `_post_json`, and exhausted recovery projects typed `provider_timeout` rather
than `provider_unavailable`. Properties also prove that an explicit region lens keeps navigation controls out of the
executable manifest while retaining their PageMap region summary. Streaming TTFT and idle-timeout observability are
not implemented in this increment. No post-change live run has been performed; the honest status is `staged timeout
recovery implemented and locally verified / live effectiveness pending / end-to-end task closure non-closed`.

### 2026-08-20 ActionPolicy output-budget classification and recovery

The latest DeepSeek task-0 evidence is not a stale-ref, missing-read-tool, or insufficient-total-step witness. Policy
calls at sequences 8, 31, 33, 35, and 39 each reported exactly 2,048 completion tokens and empty final content. This
matches provider output-budget exhaustion: reasoning consumed the configured completion allowance before the compact
single-command JSON was delivered. Increasing GUI turns alone cannot recover a wire configuration that repeats the
same 2,048-token cutoff.

The local repair records `finish_reason`, configured and actual token usage, final/reasoning content presence, and safe
response field names at the provider boundary. The previous generic `representation_error` outcome is removed;
provider output is classified as `output_truncated|empty_final_content|json_invalid`, while native multi-call remains
`multiple_tool_calls`. Only confirmed truncation receives one same-policy-turn retry. The normal request keeps provider
default reasoning with `max_tokens=4096`; the retry is bounded to 512 and requests disabled thinking only through a
declared provider capability. Provider-free properties prove one policy call can contain two provider attempts while
creating no extra GUI step, and that empty or invalid non-truncated output never enters the retry.

Manager capability projection now uses semantic descriptions instead of `read_current_world|search_current_world`.
Manager prompt forbids ActionPolicy tool prescriptions. The typed output boundary rejects only unambiguous protocol
forms—code-style names, backticks, call syntax, and explicit tool/command/operation labels—using vocabulary projected
from `InteractionCapabilityRegistry` and the single fixed-name owner in `GroundedToolCatalog`. It deliberately does not
guess whether ordinary words such as `read|focus|scroll` are tools, preserving legitimate page fields such as
`order_id`. The ordinary episode default and hard upper bound are 15 turns, with prompt guidance of 5–8 for a simple
read-only episode and no 20-turn loop. The existing three same-kind protocol-stall bound remains intact.

The fresh six-page read-only diagnostic at
`evidence/w1b-world-t32-output-budget-recovery-run1/` passes 6/6 with `ready=true`, `failure_origin=none`, no acceptance
errors, provider attempts zero, and zero-dispatch metrics unchanged. It performed no model call or GUI mutation. This
is provider-free contract evidence only: no DeepSeek/live WebArena witness has been run, task-0 live verification is
pending, and the milestone remains non-closed. Focused owner/cross-owner tests pass (`170 passed`), the full suite
passes (`1397 passed, 19 skipped`), and Ruff plus diff-check pass.

### 2026-08-20 T3.2 recovery-scope and wire-capability repair

DeepSeek run2 is a progressive failure witness rather than a return to the original defect. Current `E19` and `E45`
entered Catalog and dispatched; current `E59` was rejected only because `activate` was not one of its offered
operations; no stale hidden ref was executed. Multi-call responses produced typed zero-dispatch feedback, and repeated
feedback yielded `protocol_stall` directly to Manager with Auditor calls zero. The later failure was caused by Manager
receiving no application/page/capability scope, DeepSeek's native wire repeatedly returning multiple calls, and the
benchmark closed decision vocabulary rejecting `ProtocolFeedback` during report projection.

The local repair adds one bounded `MissionEnvironmentView` to Manager, removes `<expired-ref-N>` from model history,
selects ActionPolicy transport through `NATIVE_SINGLE_TOOL|JSON_SINGLE_COMMAND` provider capability, declares DeepSeek
as JSON single-command, and adds `ProtocolFeedback` to benchmark projection without changing Runtime outcome. Both wire
forms still converge on the same ToolCall/DeliveryManifest/Catalog/resolver/admission/Binder/Executor chain. The
existing multi-call protocol feedback and Manager recovery path remains the exceptional fallback.

Provider-free properties cover semantic history without ref aliases, bounded Manager scope without complete World or
screenshots, current application/page/route-family projection, DeepSeek factory selection of the compact one-command
transport, provider capability override validation, repeated protocol feedback with zero dispatch/Auditor calls zero,
and successful formal `run.json`/`summary.json`/case-report serialization. No real provider, live WebArena task, or GUI
mutation was run for this increment. The honest state is
`T3.2 next-layer recovery implementation converged locally / provider-free verification passed /
live success witness pending / non-closed`.

Focused owner/cross-owner verification passes (`166 passed`); the full suite passes (`1348 passed, 19 skipped`), and
Ruff/diff-check pass. The fresh six-page read-only diagnostic at
`evidence/w1b-world-t32-next-layer-recovery-run3/` passes 6/6 with `ready=true`, `failure_origin=none`, no acceptance
errors, request estimates `5171 / 5835 / 6679 / 6775 / 7075 / 11549`, and median `6727`. It loaded the repository
WebArena URL environment but did not instantiate a model/provider or dispatch a GUI action. Run1 is retained as a
failed environment witness: the first invocation omitted those URL settings, so all six cases failed before
environment construction; it is not counted as product or projection evidence.

### 2026-08-20 T3.2 single-turn contract convergence

The current provider-free increment closes four locally reproduced shared contract gaps without changing task
semantics. One immutable `ModelTurnDelivery` is constructed from the fresh World and complete ActionSpace; its exact
`WorldDeliveryView.text`, `DeliveryManifest` object, `delivery_id`, and lineage are shared by ActionPolicy context,
ToolCatalog, resolver/admission, and trace. ToolCatalog no longer renders World independently or discovers refs from
strings/regex.

ActionPolicy transport explicitly lowers `parallel_tool_calls=false`. A returned multi-call envelope produces zero
GUI dispatch and same-episode `multiple_tool_calls` feedback; repetition becomes `protocol_stall` and routes to
Manager. The old tool-call/argument/intent repair and semantic-reselection paths are removed. Implemented Supervisor
routing is total but over-frequent: terminal and operational/stall paths bypass Auditor, while `ready_for_audit` and
final-audit requests invoke it. Run7 falsified that cadence; the target is optional commit/final-uncertainty
verification. `AuditorRoleRequest` carries a
narrow typed task projection, so neither the role port nor trace sees `TaskGoal.inputs`; Auditor has only the
`AuditDeltaModel` output contract. The WebArena public final-response schema is visible only to
`ManagerReview(review_and_route)` and the mechanical FinalResponseBoundary, never ActionPolicy or Auditor.

Focused owner/cross-owner tests passed (`110 passed`) and the full provider-free suite passed (`1339 passed, 19
skipped`); Ruff passed. The fresh six-page read-only diagnostic is stored at
`evidence/w1b-world-t32-contract-convergence-run1/`: `ready=true`, six of six cases have no acceptance errors,
request estimates are `5,171 / 5,836 / 6,676 / 6,775 / 7,076 / 11,546` tokens (median `6,725.5`), Tool Schemas are
`1,598..1,885`, provider-reported prompt tokens are zero, and every case's recoverability check reports unchanged
zero-dispatch metrics. This run did not instantiate an ActionPolicy provider and did not execute a live task witness.

Deleted paths include the ToolCatalog renderer/ref mirror, parallel Manifest cache, semantic call repair/reselection,
operational-failure-to-Auditor fallback, shared role `_task_payload`, and unused repair diagnostics/metrics. Explicit
non-goals remain `SemanticTargetSelector`, `fill_form`, arbitrary multi-action execution, VLM fallback, and a second
Binder/ActionSpace/Executor/GUI loop. Current state is
`T3.2 semantic delivery implementation converged locally / single-turn contract and audit routing repaired /
provider-free verification passed / live W1b witness pending / non-closed`.

The retained R2-era MiniWoB-60 runs are negative baselines, not performance claims:

| Frozen run | Task success |
|---|---:|
| historical breadth | 6 / 60 |
| post-attribution rerun | 4 / 60 |
| later diagnostic | 8 / 60 |
| simplified-core capability-covered structured-only | 13 / 15 |
| simplified-core capability-covered adaptive | 13 / 15 |

Those runs used different exact source revisions and must not be merged into a trend. They show that architecture
verification was ahead of demonstrated task capability.

The two 15-case simplified-core arms used the same GLM-4.1V model and completed with valid evidence, but the adaptive
arm acquired no visual source and sent no image to the model. Their equal success count therefore validates the shared
Runtime path only; it does not establish an adaptive-observation benefit.

### 2026-08-18 W1b projection and provider diagnostic

The stopped W1b run is retained at
`evidence/live/w1b-one-task-0-aliyun-glm52-900s-20260818T173159Z/`. It made no physical GUI dispatch, but the first
ActionPolicy call was semantically informative: the model received the task, `REPORTS`, and the Bestsellers table,
then selected `activate(E59)` for the Reports navigation entry. Runtime rejected the call because the current catalog
had exposed E59 only as `draggable`. The adapter had treated the browser DOM property's default
`element.draggable=true` as authored drag semantics; the correction requires explicit `draggable="true"` evidence.
This is a reusable SurfaceAdapter/action-capability classification defect, not evidence that task-relevant World
content was missing. The bounded repair then failed to produce an admitted call, so no browser action occurred.

The same request exposes a separate delivery problem. Its Actor View retained 512/583 structure nodes with partial
coverage and included many empty generic wrappers, duplicate text descendants, icon glyphs, and presentation
metadata. The first provider input was about 11.6k prompt tokens and the repair request reached about 23.4k. This is
not evidence of context-window exhaustion; it is material attention/cost noise and repair amplification. Correctness
must be judged by target/state/structure conservation and recoverability, while complete-request token measurements
govern efficiency. A later task-0 run ended in a Manager `StructuredModelError` before ActionPolicy, so it cannot be
used to assess the repaired World/Actor path.

Repository-wide review found two shared defects. First, the flat dynamic tool schema exposed open string refs for
drag source/destination and allowed invalid refs to reach bounded repair; finite current enums were added as a
containment step. T3.2 supersedes those broad enums with stable ref patterns plus typed DeliveryManifest/current
ActionSpace validation so ref inventory is not repeated in every Tool Schema. Second, model World projection retained only eight target-state fields without prioritizing
action-decision state. On real `choose-list`, BrowserGym executed `Gibraltar -> China`, fresh history retained that
transition, and fresh World exposed `selected_options=[China]`, but current ActionSpace omitted `value`; the policy
therefore repeated selection until its step budget. The projection now preserves supported decision fields under
metadata pressure and explicitly renders partial node-state coverage.

Fresh local gates after the projection repair are 211 unit/conformance/integration tests and Ruff, plus 12 real-Chromium tests
against the fixed MiniWoB source. The real adapter cases completed `click-button` in one step, `enter-text` in two,
and `choose-list` in two with official success; unchanged-currentness probes passed for the six declared pages. This
is evidence for the current four-action semantic algebra and post-action lineage, not a claim that all BrowserGym
interactions are supported or that real-page projection is adequate. The real-web World/Actor gate and all six W1b
site smokes remain required before W2.

### Goal-feedback negative evidence

Two fresh held-out runs of `miniwob-60-17` failed after the observation fixes had passed 106 focused tests, 1,104 full
tests with 18 skips, and Ruff. The task was “Click the Like button on all posts by @nibh and then click Submit.” In the
second trace, the Runtime correctly exposed `Like: active false -> true` and the fresh world showed `active=true` with
`selected=unknown`. The policy nevertheless toggled the same Like off and on repeatedly, activated Retweet and Reply,
and never submitted.

Evidence:

- `evidence/live/2026-08-16-goal-feedback-heldout-v1/report.json`;
- `evidence/live/2026-08-16-goal-feedback-heldout-v2/report.json`;
- `evidence/live/2026-08-16-goal-feedback-heldout-v2/traces/miniwob-60-17/trace.jsonl`.

A third formal run after the Simple GoalPlan replacement is stored at
`evidence/live/2026-08-17-g2-like-simple-goal-plan-v1/`. Local gates were 86 focused tests, 1,154 full tests with
15 skips, Ruff, and diff-check. The GoalCompiler made one `glm-4.7-flash` provider attempt; it returned
`rate_limit_transient` before any model output, so disposition was Failed/unavailable with no schema or contract
repair and no Ready plan. The ordinary loop continued as designed, but ActionPolicy activated the same Retweet six
times, alternating its `active` class true/false, then failed its repaired JSON response on turn 7. Submit was never
activated and official success was 0. The report is marked invalid for a generalization claim because the implementation
worktree was dirty. This is valid diagnostic evidence for trace/failure containment, not a Ready GoalPlan witness.

After adding one bounded compiler-boundary retry for `rate_limit_transient`, the explicitly authorized follow-up run
is stored at `evidence/live/2026-08-17-g2-like-simple-goal-plan-retry-v1/`. Local gates were 53 focused tests and
1,157 full tests with 15 skips, plus Ruff and diff-check. GoalCompiler succeeded on its first `glm-4.7-flash` call and
produced a Ready three-item plan; the same plan version/digest appeared in all ten policy contexts. ActionPolicy first
activated three different Like controls, then reversed the second and third active Likes repeatedly. It never touched
Retweet/Reply/Share and never submitted. The ten-step limit ended with native verifier `verified_running`, official
success 0, and report outcome `runtime_rejected`; no Runtime failure object or watchdog failure was present. This
isolates the witnessed defect to ActionPolicy current-state reasoning. The dirty-worktree flag still prohibits a
generalization claim.

The action-only model diagnostic is stored at `evidence/live/2026-08-17-g2-like-action-glm46-v1/`. The official
`glm-4.6` native Function Calling transport (`pydantic-ai`) was used while GoalCompiler remained
`glm-4.7-flash`; the provider-cohort runner was generalized to accept either grounded transport without weakening the
frozen Mistral A/B gate. The compiler's initial call and bounded retry both returned `rate_limit_transient`, so this
episode had unavailable plan guidance. GLM-4.6 then produced four valid decisions—action paging, one Like activation,
and two further page requests—without reversing the newly active Like. Its fifth call returned typed
`provider_unavailable`; only one GUI execution occurred, Submit was not attempted, and official success was 0. The
PydanticAI adapter did not persist the failing exception/transcript, so rate limiting, capacity, and connection failure
cannot be distinguished. This run is inconclusive for the 4.6-versus-4.1V behavior question and exposes a separate
provider-failure observability gap.

That gap is now repaired at the PydanticAI provider-call owner. SDK retries remain disabled; each semantic phase may
make one explicit retry for `429`, timeout/transport, `409`, or `5xx`, using `Retry-After` when present and otherwise
exponential backoff, capped at five seconds. `401/403` and other non-retryable `4xx` fail immediately. Each physical
attempt records its own input projection, status, safe provider code, HTTP status, retry hint, exception class, latency,
tokens, and output. Public ActionPolicy failure wording stays bounded, but evidence no longer folds these categories.
The total policy deadline is budgeted as two 42.25-second transport attempts plus at most five seconds of backoff;
only a retry that actually begins increments `provider_retry_count`.

The first post-repair witness at
`evidence/live/2026-08-17-g2-like-action-glm46-provider-retry-v1/` exposed an initially unreachable retry: the old
89-second transport timeout consumed the 90-second policy deadline before the second request. It ended as
`provider_timeout`, with one failed physical attempt. After splitting the deadline, the fresh V2 witness at
`evidence/live/2026-08-17-g2-like-action-glm46-provider-retry-v2/` made seven physical policy attempts across five
policy turns, including one retry that actually began. Four completed decisions paged twice, waited once, and activated
one Like without undoing it. The 180-second case watchdog then cancelled the fifth turn; the result was `case_timeout`,
one execution, no Submit, and official success 0. GoalCompiler independently exhausted its rate-limit retry, so plan
guidance was unavailable in V2. Both dirty-worktree reports prohibit a generalization claim. Cancellation now projects
already-captured attempts before propagating, preventing the final in-flight turn from disappearing in future traces.

The next narrow patch explicitly disables GLM-4.6 thinking on the PydanticAI action path, caps output at 512 tokens,
and sets temperature to zero. PydanticAI's unified `thinking=False` is verified to lower to Z.AI
`extra_body.thinking.type=disabled`. In-flight cancellation now emits a `cancelled` generation attempt with elapsed
latency and `network_dispatched=true`, then propagates cancellation unchanged. Successful `ModelMetadata.latency_ms`
now covers the whole semantic call, including provider attempts, repair, and backoff, so cohort reports no longer
project zero latency.

A one-call latency probe reused the V2 first-turn system prompt, 9,867-token user context, and exact six-tool schema.
It returned one native `activate` call in 3,891 ms with 53 output tokens, zero reasoning tokens, and zero thinking
parts, versus the earlier 29.8-second/819-output-token call with thinking enabled. The subsequent single formal run is
stored at `evidence/live/2026-08-17-g2-like-action-glm46-thinking-disabled-v1/`. GoalCompiler returned Ready on one
attempt; all ten action calls completed without retry or thinking, totaling 26,746.6 ms model latency and 606 output
tokens. Runtime completed the case in 76.8 seconds, but the policy alternated `next_actions` and `wait`, executed no GUI
action, exhausted ten steps, and received official success 0. This removes provider latency as the proximate failure
while showing a material behavior regression with thinking disabled. Because the prior thinking-enabled episode had
different compiler availability, it is not a clean A/B. That run originally suggested a same-guidance thinking on/off
pair; the convergence plan below supersedes it. Model-setting A/B work resumes only after G2/G3 and the G4 Like gate.

The requested no-compiler diagnostic is stored at
`evidence/live/2026-08-17-g2-like-action-glm46-no-goal-compiler-v1/`. It used the same GLM-4.6 thinking-disabled action
profile and set only `LLM_GOAL_COMPILER_MODE=disabled`. Trace confirms `goal_compiler_not_configured`, zero compiler
provider attempts, and unavailable guidance. The policy paged once, activated one relevant @nibh Like, paged twice
more, then emitted an invalid `request_evidence` target; its one tool-call repair repeated the same invalid call. The
run ended after five policy turns with one GUI execution, `structured_output_failure`, no Submit, and official success
0. Compared with the Ready-plan run's zero executions and repeated page/wait loop, removing guidance changed behavior
and allowed immediate task progress, but one stochastic case cannot establish that the plan caused the regression.
The report correctly records 13,070.3 ms successful-call model latency. The earlier schema-repair metric projection
defect is addressed by the model invocation boundary convergence: policy attempts now come only from
`ModelInvocationResult.attempts`, while role repair count is tracked separately and no longer double-counts as a
transport attempt.

This is a short-loop task-semantics failure, not a demonstrated memory-window failure. The retained runs expose two
different mechanisms: one Ready plan described an internal locating activity and the policy treated ordering as a
current-screen gate, producing a zero-action page/wait loop; another policy reached three relevant Like controls but
received the same `effect_confirmed` class for both activation and reversal. The convergence target is therefore a
compact advisory-plan prompt plus direction-aware local-outcome feedback where evidence supports it and explicit
unknown elsewhere, not more history, a progress store, or case wording.
The second run used the `structure-first.v1` profile but recorded zero model image inputs, zero acquired visual sources,
and zero visual-provider calls. That absence is an adaptive-vision coverage finding, but vision would not have repaired
this case because the required `active` facts were already present and correct. A known-state policy/progress failure
must not be relabeled as a perception failure.

## Simplification acceptance

Run the same predeclared supported cohort against the R2 checkpoint and the simplified core with identical provider,
model, seed, step budget, and pacing. Accept the simplified core when:

- every case produces a valid terminal result and cleanup succeeds;
- no benchmark identifier or oracle data enters product context;
- success does not regress beyond the predeclared tolerance;
- failures are attributable without a control ledger;
- the report contains source, cost, and recovery metrics needed for the adaptive-observation claim.

The paired observation experiment is retained but deferred to architecture Phase 14, after the frozen
WebArena-Verified structured-observation baseline:

```text
A: structured source only
B: structured source first, visual supplement on typed need
```

The portfolio claim should report task success together with visual-call, token, and latency deltas. A useful result
may be either higher success at similar cost or similar success at lower observation cost.

## Goal-plan convergence and evidence plan

Repeated Ready-path reopenings invalidate the former G1/G2 closed framing. The previous external `edge_path` bound was
not closed under recursive internal lowering, and an otherwise harmless surplus field could reject the entire
proposal. More importantly, deterministic snapshot progress duplicated the ActionPolicy's open-world interpretation.
This is an architecture/acceptance defect, not evidence that the configured model lacks semantic planning ability.

The standalone/inner-episode chain is:

```text
TaskGoal -> GoalCompiler(start/revision once) -> Simple GoalPlan
TaskGoal + GoalPlan + fresh World + recent steps + current tools
  -> single ActionPolicy -> SelectAction + optional local-intent description
  -> Binder conserves one binding-selected verification contract -> Executor -> fresh World
  -> non-authoritative local outcome projection (transition + optional postcondition; unknown is valid)
TaskEvaluator/native verifier -> formal completion
```

G5 wraps repeated instances of this same GUI chain with the bounded ManagerReview/MissionState episode boundary and
an exceptional optional SemanticAuditor
defined below. It does not extend Simple GoalPlan into cross-episode progress.

| Gate | Scope | Implementation output | Falsifiable exit evidence |
|---|---|---|---|
| G0. Reopened contract convergence | two maintained authority documents and owner map | one five-field plan contract; no symbolic progress path; explicit non-goals | docs, production types, tests, and trace projection agree; independent fresh-context review remains required |
| G1. Simple GoalPlan implementation | compiler, boundary, lifecycle, transcript trace | `id/objective/done_when/depends_on/final`; 1..8 items; unique acyclic IDs; at most one final; tolerant unknown fields | property/unit/integration tests pass; initial/schema/contract repair attempts survive independently; compiler failures remain advisory |
| G2. Advisory prompt/context convergence | compact GoalCompiler and ActionPolicy prompts in the existing five-kind context | no internal locate/inspect items; dependency is semantic order, not a visibility gate; typed World delivery and ref-free semantic history remain bounded; current tools stay searchable | MiniWoB delivery witness passes, but complex-page semantic overview/discoverability is explicitly deferred to the G5 real-web gate and cannot be closed by the 16.2%-size witness |
| G3. Local transition projection — local verification passed | binding-selected verification contract, typed parameters, fresh evidence, Recent Steps | dispatch stays in ActionResult; supported before/after transition and optional local postcondition are projected; TaskGoal criteria remain in TaskEvaluator | family is selected once; after-only evidence can prove a postcondition; target-scoped evidence rules hold; unresolved semantics stay unknown and non-blocking |
| G4. Short-loop live proof — witness passed / cohort deferred | the predeclared Like witness; frozen cohort retained as regression | official case evidence through the existing runner | witness reaches official success without old refs, reversal, unrelated controls, or case logic; no broad MiniWoB generalization claim until its cohort runs |
| Model invocation boundary convergence — run9 implementation active / non-closed | shared provider/model invocation exit for current model roles | `ModelInvocationResult[T]` carries typed output/failure, metadata, every physical attempt, validation-retry diagnostics, role diagnostics, and lineage; ActionPolicy and Manager/Auditor use PydanticAI; compact-json remains only the declared compatibility shim | focused/unit/integration tests prove attempts are retained, PydanticAI output retry stays distinct from provider retry, instrumentation reads the explicit result, and GUI Runtime authority is unchanged; fresh audit and W1/W2 evidence remain pending |
| G5. WebArena-Verified long horizon — run12 governance architecture frozen / implementation pending / non-closed | episode history/working set; bounded Manager interaction scopes; grounded entry admission; typed recovery/route trail; role-specific bounded retry; exceptional independent Auditor; mechanical evidence/final-response boundaries; official BrowserGym integration | one governed World/ActionSpace -> ActionPolicy -> existing Binder/Executor; ordinary W1b uses event-driven ManagerReview, zero Auditor/Finalizer calls, typed evidence admission, one terminal send, and lifecycle-isolated observability/cleanup | implement the frozen L0-to-recovery sequence, pass provider-free properties and fresh-context audit, then run one predeclared task-7 regression plus held-out non-map route-cycle witness |
| G6. Adaptive-observation value | paired structured-only/adaptive cohort after G5 baseline | the same Runtime and action policy differ only by typed visual supplementation | report success, visual calls, tokens, and latency; zero visual acquisition cannot support an adaptive-observation claim |
| G7. Desktop long horizon — later | OSWorld-Verified smoke, then release-pinned OSWorld V2 | desktop/window/file/clipboard surfaces and reproducible harness | setup verification passes and infrastructure failures remain separate |

### G1: Simple GoalPlan contract

A `ready` response contains 1..8 items. Each item has only:

```text
id | objective | done_when | depends_on | final
```

Runtime checks field types and text bounds, unique IDs, existing acyclic dependencies, and at most one final item.
Unknown descriptive fields are ignored. It does not validate or lower entity kinds, predicates, relations, paths,
selectors, current refs, or GUI steps. `NotRequired`, `NeedsInput`, `Unsupported`, and `Failed` retain their typed
lifecycle meanings; only missing user-owned goal facts may cause `NeedsInput`.

Required properties include:

- model JSON schema is fixed-depth and contains no world-query or helper-node types;
- harmless surplus fields do not invalidate a valid plan;
- duplicate, dangling, self, cyclic, oversized, or multiple-final plans fail typed;
- the same admitted proposal and version produce the same immutable plan/digest;
- user revision invalidates the old plan before recompilation;
- no layout change, repeated action, ambiguity, or provider failure triggers automatic recompile;
- initial, schema-repair, and contract-repair transcripts remain individually observable;
- compiler attempts are not counted as ActionPolicy provider attempts.

### G2: advisory prompt and context convergence

G2 keeps exactly five context kinds: Task, Current Observation, Current Goal Plan, Recent Steps, and Current Tools.
A Ready plan is projected directly and contains no item status, frontier, per-subject result, binding, or completion
claim. GoalCompiler must emit user-meaningful outcomes rather than internal activities such as locating, inspecting,
reading, scrolling, clicking, or selecting the next control. ActionPolicy re-evaluates those outcomes against task,
fresh World, and Recent Steps every turn. Dependencies express semantic precedence, not current visibility or action
permission; the policy may skip, revisit, or adapt items and emits exactly one currently offered tool call.

The delivery contract no longer truncates the World at 64 targets or the structure at 128 nodes. It uses the enclosing
serialized-byte budget and retains repeated sibling structures only as complete semantic groups. Current executable
refs and verbs are printed together on exact Observation nodes; there is no separate model-visible affordance map.
Stable operation schemas use compact ref patterns, while the current DeliveryManifest and ActionSpace provide actual
validation. The normal short-task path has one current catalog; folded actions remain available through
`find_actions(query,exact_target,cursor)`, which exposes an
objective-relative role filter only when a current objective exists. Recent Steps
contains older action/result summaries followed by the latest four ref-free semantic target/action/local-transition
records. DOM/BrowserGym retains no historical screenshots; only the current screenshot may accompany the current
World. A visual-only typed need still acquires and fuses a
structural baseline, so visual evidence supplements rather than replaces public structural facts.

The current pre-T3.2 provider expression is `compact_ax.v1`, rendered after the bounded typed `ActorWorldSnapshot` is
finalized with explicit coverage. T3.2 moves model-budget omission out of that snapshot: the supported public Actor
algebra becomes a lossless normalization, while WorldDeliveryView alone owns fold/expand decisions.
Runtime, binding, currentness, evaluation, and trace continue to use typed facts; ActionPolicy receives indented public
text with E-ref, role/name, useful state, hierarchy, relations, coverage, and current verbs. The renderer drops only
presentation scaffolding such as N-refs, state-evidence dictionaries, source-ref repetition, empty arrays, low-value
appearance fields, and redundant inline text. It imports no surface or benchmark implementation and cannot create a
second observation authority. The old `state_coverage=retained/total` signal remains historical regression evidence;
under T3.2 any supported-field Actor deficit is a normalization violation, while delivery folding is reported only by
WorldDeliveryView coverage/recovery.

The live seed-7 Context snapshot for `browsergym/miniwob.social-media-all` retained 260/260 structural nodes, 177
targets, all 41 actions in one non-paged catalog, seven `@nibh` mentions, ten Like controls with explicit
`active=false`, and Submit. The typed observation was 71,723 UTF-8 bytes; the compact rendering was 11,611 bytes
(16.2%). Renderer properties and all repository gates pass: 1,175 tests passed with 15 skips, and Ruff passed.
This proves a small regular page can be delivered compactly and completely. It does not prove source semantics,
structural closure, signal-to-noise, or omission recovery on WebArena pages; those properties belong to W1b below.

The follow-up formal run used the same official MiniWoB entry, case, seed, and model roles in a fresh evidence
directory. Compiler tracing and all six external-breadth compiler metrics were present, Ready guidance reached every
turn, and no compiler repair was needed. It therefore evaluates the new context path and falsifies the claim that the
current ActionPolicy reliably preserves satisfied local outcomes. No single case can declare the convergence closed.

### G3: local transition projection

Before another Like run, binding construction selected one verification family/digest and conserves it through
ActionOption, AdmittedActionSelection, and BoundActionRequest. Downstream contracts only copy and validate this
identity; they do not silently select a fallback. `ActionOutcomeProjector` is observational: architecturally, only
TaskEvaluator/native verifier is an evaluator.

Combined StepResult evidence projects ActionResult-owned dispatch alongside supported target before/after values, a
derived changed/unchanged/unknown summary, an optional mechanically closed local postcondition, and evidence method.
Current after evidence may prove `satisfied` or `unsatisfied` even when before evidence leaves the transition summary
unknown. Generic activation may expose structural or visual change while its semantic outcome remains unknown or not
applicable. Screenshot or unrelated-target change never becomes task progress.

`expected_outcome` is narrowed to one optional natural-language intent description for later ActionPolicy reflection.
It does not create a predicate or artifact-observation obligation; exact local postconditions come from typed action
parameters and the selected contract. TaskGoal criteria and requested outputs remain exclusively in TaskEvaluator or
the native verifier. Phase 11 adds no semantic progress evaluator. A later named benchmark gap may add a typed semantic
evidence provider through SurfaceAdapter/Fusion, never as a repetition or long-task fallback.

The bounded local gate passed locally and covers:

- dispatch remains owned only by ActionResult;
- GoalPlan and TaskGoal criteria cannot change a local action outcome;
- the selected family/digest is conserved without downstream defaulting;
- after-only exact evidence can prove a local postcondition while observed change remains unknown;
- target/value families reject unrelated evidence, while navigation contracts may admit page-level transition;
- unresolved semantic intent remains unknown and does not block the ordinary loop;
- Recent Steps exposes supported before/after transition but no goal advance, plan-item status, count, or readiness;
- `expected_outcome` cannot create an artifact obligation; and
- TaskEvaluator/native verifier remains the only formal termination authority.

### G4: randomized Like cohort

Current status: Phase 11, compact current-World delivery, and ref-free model-facing Recent Steps rendering are
implemented. Raw `AgentTurnView.expected_outcome` sanitation before the record is shared with a future Auditor remains
W1 work. The predeclared GLM-5.2 Like witness reached official success after the temporal E-ref fix. The work remains non-closed
because this one dirty-worktree witness is diagnostic, not the required frozen held-out cohort. The final local gate
is 1,173 passed with 18 skipped, plus repository-wide Ruff.

The post-renderer witness is stored at
`evidence/live/2026-08-18-g4-like-compact-context-v1/`. The first provider input contained
`compact_world format=compact_ax.v1`; GLM-5.2 correctly enumerated all seven `@nibh` groups and their Like refs on its
first turn. Six accepted action decisions executed. On turn four, the selected grounding was already `active=true`,
so the toggle reversed a satisfied local outcome. By turn seven the current compact World contained four active target
Likes, but the model associated the former ref `E77` with a current Like even though that ref was not currently
actionable. Runtime rejected it; the single tool-call repair repeated `E77`, producing `schema_error` before another
GUI dispatch. The case therefore ended `structured_output_failure`, official success 0, with no environment,
grounding, dispatch, or watchdog failure. The report remains invalid for a generalization claim because the worktree
was dirty, but its private trace is valid diagnostic evidence of the temporal E-ref scope defect.

The Context delivery witness is stored at
`evidence/live/2026-08-18-g4-like-context-closure-v1/`. Before the run, a live snapshot of the same task and seed
contained all 260 structural nodes, 177 targets, 41 actions in one non-paged catalog, all seven `@nibh` post groups
with their Like control and explicit `active=false`, and Submit. The official runner then produced six valid action
decisions: five distinct Like activations followed by Submit. It did not reverse an already active Like and recorded no
provider, grounding, dispatch, or Runtime failure, but Submit was premature because two required groups remained;
native verification returned task failure and official success 0. The dirty-worktree report is diagnostic evidence,
not a generalization claim. This falsifies behavioral closure without falsifying the Context delivery invariants.

The ref-free semantic-history witness is stored at
`evidence/live/2026-08-18-g4-like-semantic-history-v4/`. Across all eight GLM-5.2 provider turns, public Recent Steps
contained zero E-refs, zero prior observations, zero generic `task=incomplete` fields, and zero historical images.
Historical targets contained only role, semantic label, and the nearest post-local text; no neighboring post text was
mixed in. GoalCompiler returned two semantic outcome items (`all @nibh posts liked`, then `submitted`) and did not
hardcode a count of seven; ActionPolicy derived the seven matching posts from the fresh complete World. The policy
selected seven distinct canonical Like targets whose fresh pre-action state was `active=false`,
then selected Submit. There were eight executions, no schema repair, invalid argument, stale catalog, grounding gap,
provider, dispatch, or Runtime failure. The native verifier returned terminal success and official success was 1/1.
The report is still marked invalid for a generalization claim solely because the worktree was dirty or changed during
the arm. The earlier Zhipu 4.1V v3 attempt was manually interrupted when the user required the established GLM-5.2
profile and is not an official comparison result.

The predeclared witness has now passed. The held-out Like cohort remains required before any broad short-loop
generalization claim, but is deferred as a regression gate and does not block the WebArena-Verified long-horizon
mainline. Do not add a benchmark-specific production branch.

Retain current runs as causal witnesses, not a statistical baseline. Freeze a generated cohort before treatment and
vary usernames, post counts/order, unrelated controls, initial active states, and collection visibility. Generator
values and official verifier state remain private. Report:

- official success and whether a Ready plan reached ActionPolicy;
- compiler disposition, item count, attempts, and repairs;
- every policy action, unrelated-control activation, and repeated/undoing toggle;
- fresh-world state and Recent Steps transition visible before each decision;
- local postcondition when mechanically closed, or explicit unknown otherwise;
- whether `local_postcondition=unknown` is paired with concrete false-to-true transition evidence rather than counted
  as a Runtime failure;
- premature final-action attempts and steps from supported prerequisite outcomes to final action;
- grounding, local-transition, provider, and official-verification failures.

The predeclared `miniwob-60-17` witness reached official success once; it remains diagnostic rather than a
generalization claim. When the regression cohort is scheduled, freeze eight held-out generated cases and run the
pre-Phase-11 checkpoint and Phase-11 treatment on the same cases, seeds, model settings, pacing, and budgets. The
short-loop capability gate requires:

- treatment official success of at least 6/8 and strictly more successes than the checkpoint;
- zero treatment actions on a target whose immediately preceding fresh World already showed the task-requested
  `active=true` state;
- zero unrelated Reply/Retweet/Share activation; and
- no production branch keyed by case, task text, username, selector, or expected action.

Submit timing and official verifier outcome remain reported diagnostics rather than Runtime action bans. Failure of
this gate keeps the behavioral capability open but does not reopen GoalPlan or local-outcome ownership by itself. If
the trace contains correct fresh state and transition feedback but the policy still reverses a satisfied outcome, the
failure is ActionPolicy/model competence unless new cross-case evidence falsifies the boundary.

### G5: WebArena-Verified long-horizon proof

#### Decision and reuse boundary

The active long-horizon benchmark is WebArena-Verified through the existing official BrowserGym integration. Do not
run the legacy WebArena agent loop, do not adopt AgentLab's agent implementation, and do not call WebArena-Verified a
second time from project reporting. Reuse the mature owners exactly once:

| Concern | Reused owner | Project responsibility |
|---|---|---|
| sites, accounts, initial data, reset images | official WebArena/WebArena-Verified environment distribution | pin versions/digests and configure URLs/headers without logging credentials |
| task dataset, hard subset, task ID, template ID, revision, expected result | `webarena-verified` package | freeze only public task identity and selection metadata; never expose expected values to the model |
| Gym registration, login, start URLs, tabs, Playwright tracing, STOP and evaluator invocation | `browsergym-webarena-verified` | import/configure the package and pass its registered task ID to the existing BrowserGym surface |
| DOM/AX/screenshot acquisition and BrowserGym actions | existing `BrowserGymSurfaceAdapter` | generalize composition, not observation or execution semantics |
| episode-level history | Qwen3-VL/Glass design signal, existing `project_step_result()` and `AgentTurnView` | remove generation-local refs in the existing projection, then retain those semantic records for the episode; the request renders older views compactly and the latest four in detail; deterministic folding occurs only on byte overflow |
| cross-stage planning and accepted state | LongHorizon-Harness evidence discipline plus Agent S2's combined completion/failure-to-replan cadence | one Manager role performs initial planning and episode-boundary review/replanning; independent Auditor is exceptional; do not import a generic Environment/orchestrator or make MEA mandatory |
| exact values required after navigation | project `pin_fact` local control contract | resolve current public evidence immediately; model never supplies the value or persists call-local refs |
| task understanding and rolling GUI decisions | single existing ActionPolicy | long-horizon baseline deterministically projects SubtaskContract to one GoalPlan item; model GoalCompiler is disabled in this mode |
| action legality, binding, execution, fresh observation, local transition | existing Runtime owners | no WebArena selector, label, site, or case branch |
| official success/failure | BrowserGym-integrated WebArena-Verified evaluator | map its native terminal result into the existing TaskEvaluator/RunStatus result once |
| scheduling, evidence, trace, model metrics, git identity, report | existing `BenchmarkManifest -> run_suite -> BenchmarkCaseResult` | add one WebArena manifest/composition projection; do not add another runner |

The official BrowserGym integration is the dependency contract. It already provides Gym IDs of the form
`webarena_verified.<intent_template_id>.<task_id>.<revision>` and invokes the WebArena-Verified evaluator using its
Playwright trace. Project code must not copy the 812-task dataset, hard-subset list, login implementation,
`FinalAgentResponse` schema, expected backend/UI state, response normalization, network-trace replay, or evaluator.

#### One execution and evaluation chain

```text
frozen official Gym task ID/revision
  -> browsergym.webarena_verified
  -> existing BrowserGymSurfaceAdapter
  -> existing Unified World
  -> Manager(initial_plan: accepted MissionState + bounded environment view) -> one SubtaskContract
  -> deterministic one-item GoalPlan
  -> existing CoreAgentLoop episode
       -> fresh World + selected carry facts + episode working set
       -> compact renderings of earlier AgentTurnViews + latest four detailed turns + current tools
       -> single ActionPolicy
       -> existing SelectAction -> Binder -> BoundActionRequest -> Executor
       -> BrowserGym action -> fresh World -> ActionOutcomeProjector
  -> outcome/stall/failure -> fresh bounded MissionReviewBundle
       -> Manager(review_and_route) returns assessment + next route together
       -> request_finalization also carries direct final_response + evidence refs
       -> working-state proposals -> mechanical EvidenceBoundary
  -> repeat bounded episodes without resetting the BrowserGym case
  -> request_finalization -> mechanical FinalResponseBoundary -> existing FinalResponse
  -> environment-owned send_msg_to_user/STOP
  -> BrowserGym-integrated WebArena-Verified evaluator
  -> existing TaskEvaluator/native outcome mapping
  -> existing RunStatus and benchmark report
```

W1b and W2 use manager-guided composition selected explicitly by the manifest, never inferred from task text. W1b
normally has one initial Manager call and one episode-boundary review; W2 permits further reviews only after meaningful
typed episode exits. The outer supervisor is not a second GUI
execution/evaluation chain. It has no browser tools, Binder, SurfaceAdapter,
or alternate final evaluator. WebArena-Verified evaluates only after STOP. Therefore the environment-specific product
seam remains terminal delivery: when an
environment advertises finalization capability, the existing `FinalResponse` branch sends its content through that
environment, reacquires fresh World, and evaluates the returned native terminal result. This replaces neither
`SelectAction` nor `TaskEvaluator`, creates no second Binder, and adds no second GUI action/evaluation loop.
Environments without an explicit STOP capability do not enter this finalizing phase and retain their ordinary native
TaskEvaluator lifecycle.

Before STOP, the native WebArena state is running/incomplete and is not model-visible semantic progress. After STOP,
the integrated evaluator is the sole official authority. The public instruction and official final-response schema
may enter TaskGoal; expected answers, evaluator configuration, backend state, and private task metadata may not. The
final-response schema and bounded admitted candidate evidence enter only `ManagerReview(review_and_route)`, never an
ActionPolicy turn. Only `request_finalization` may carry a direct response value and supporting evidence refs.
FinalResponseBoundary re-resolves cited evidence against the same fresh ManagerReview bundle/version, validates the public schema and
one-send latch, and constructs the existing FinalResponse; W1b task 0 does not call Auditor or a separate Finalizer.
Official success remains solely with the native evaluator.

#### W0: pin and prove environment readiness

Before any model run, record in a frozen manifest and report:

- project commit and clean/dirty status;
- Python, Playwright, BrowserGym, `browsergym-webarena-verified`, and `webarena-verified` versions/commits;
- WebArena-Verified dataset revision and hard-subset checksum;
- configured site names and container/image digests, without URLs containing credentials or private headers;
- ActionPolicy, Manager, and Auditor provider/model identities; confirmation that GoalCompiler is disabled in
  long-horizon mode; role prompt identities, perception profile, temperatures, token limits, episode/mission budgets,
  timeouts, and retry policies; and
- reset strategy and whether every case starts from an official clean environment snapshot.

Use the environment/reset tooling supplied by WebArena-Verified or the referenced official WebArena deployment.
Do not create a project-owned Docker topology, login script, fixture database, site health protocol, or data resetter.
Environment readiness must verify package import, task registration, all configured site health checks, login, reset,
start URLs, trace creation, and one evaluator invocation. A setup failure blocks the run as `environment`, not as an
agent failure.

Each existing benchmark `_run_case` scope allocates one evidence namespace and one `BrowserGymSurfaceAdapter`. The
adapter opens the environment, performs the one official reset, reuses the same underlying environment across
executor episodes, and closes it from the existing `finally` path on success, official failure, provider failure,
cancellation, or environment error. The next case gets a new official clean reset. No new `CaseSession` owner is
introduced, no checkpoint resumes against a newly reset environment, and cleanup status is persisted before
aggregation.

#### W1a: long-horizon capability gate

The former plan to use static GoalPlan plus eight recent turns as the W2 baseline is withdrawn. Before a WebArena
model smoke, implement and verify these product contracts without task-specific logic:

1. **Episode boundary foundation — implemented locally.** `RunStatus.YIELDED`, initialization from a supplied fresh
   World/GoalPlanResolution, and the no-second-reset lifecycle witness are implemented. The explicit `yield_subtask`
   control belongs with the thin mission-role increment and is not silently emulated in CoreLoop. Reuse the same
   `BrowserGymSurfaceAdapter` opened by the existing `_run_case` scope. Later episodes initialize from a fresh capture
   without another reset. User/confirmation pauses resume the same episode; cancellation closes the case. This typed
   exit exists before history overflow can route to it.
2. **Episode Context — implemented locally.** The existing `RunState.recent_steps -> project_step_result() -> AgentTurnView ->
   GroundedPolicyContextBinder` path beyond eight turns. Keep the latest four views detailed, render older views
   compactly within a frozen 16 KiB history budget, and deterministically fold only repeated wait/search/no-effect
   runs. Make `project_step_result()` sanitize generation-local refs in every stored string/nested value so ActionPolicy
   and Auditor share the same safe record. No old World, screenshot, E/F ref, duplicate history record, or model
   summary enters the baseline; overflow yields `context_capacity` instead of silently discarding causal history.
3. **Working facts — implemented locally.** `AgentContext.private_fact_bindings` is one private, non-serialized
   F-ref-to-canonical-fact mapping, then add `pin_fact`
   to the current local ToolCatalog/resolver. It closes one current public scalar F ref through that mapping and
   `WorldEvidenceIndex.resolve_record()`, then stores only a bounded
   `WorkingFact` wrapper around that immutable `EvidenceRecord`. The model cannot supply the value and the tool causes
   no BrowserGym dispatch. Test current/public/scalar admission, bounds, idempotence, conflicts, and later retrieval.

The 2026-08-18 W1a implementation checkpoint initially passed local mission contracts, episode lifecycle,
audit/admission, finalization/native mapping, model invocation boundary, MiniWoB/CoreLoop regressions, repository-wide
Ruff, and `git diff --check`, but fresh-context audits found Runtime closure gaps. The current local repair preserves
the same owners and adds counterexample coverage: contradictory AuditDelta/outcome verdicts are rejected, stored
AuditedOutcome status is derived from the accepted top-level delta, final audit rejection returns to Manager while
budget remains, terminal budget exhaustion maps to `blocked` instead of leaked `yielded`, finalized cases map from
post-STOP native evaluation rather than inner episode status, oscillation uses the existing public semantic World
digest, accepted carry facts are filtered by relevant fact keys, failed episode or final-audit capture cannot write
MissionState from an old World, `SENT_UNKNOWN` with acquired post-STOP World evidence invokes native evaluation once
without retrying STOP, and Manager/Auditor `ModelInvocationResult` events enter the existing trace recorder with role
requests. This remains local contract evidence. A task-0 W1b diagnostic was subsequently allowed to expose the next
shared boundary, but it did not close W1a or W1b: the real-page World/Actor gate and the complete six-site smokes remain
pending before W2.

4. **Combined ManagerReview outer routing and mode-specific model schema implemented; live verification pending.** The existing
   Manager role has two request modes. `initial_plan` reads original TaskGoal, accepted MissionState, remaining budget,
   and a bounded ref-free environment view and must use an initial-only output without assessment. Runtime derives
   internal `not_applicable`. `review_and_route` additionally reads the active contract, typed episode exit/recovery,
   candidate outputs, fresh bounded public evidence, and allowed refs; its review-only output contains both a working
   assessment and the next route/optional replacement contract. Both lower to one internal ManagerDecision. W1b and
   W2 use this manager-guided path; provider-free implementation is complete and live W1b verification remains pending.
5. **Evidence-backed working state — implemented and provider-free verified.** Operational stall/oscillation rules may yield but never
   infer semantic completion. Exact current public scalar facts go through the conceptual mechanical
   `EvidenceBoundary`; the historical `AuditBoundary` source symbol and export were removed without an alias.
   ManagerReview may propose cited semantic working outcomes; the boundary validates lineage/version rather than
   semantic truth. An independent Auditor is disabled by default and admitted only by a strict high-risk/durable-claim
   policy. Unsupported claims leave MissionState unchanged.
6. **One terminal authority and direct finalization protocol — implemented and provider-free verified after run10.** Ordinary episodes cannot offer
   STOP/FinalResponse. `ManagerReview(review_and_route)` receives the public response schema and may carry a direct
   response value only with `request_finalization`. A mechanical FinalResponseBoundary validates route/value/schema,
   evidence lineage against that same fresh review bundle/version, and one case latch, then constructs the existing
   FinalResponse. It uses neither the
   ActionPolicy ToolCatalog nor JSON/native tool-call envelopes. Reuse
   `DispatchStatus.NOT_SENT|SENT|SENT_UNKNOWN`, reacquire fresh state once, and accept only the integrated
   WebArena-Verified result. Quarantine the offline `eval-tasks` helper from W1b/W2 composition.
7. **Isolation and bounded failures — existing foundation retained.** Every official reset starts with empty in-memory MissionState, working facts,
   and episode history; none crosses a case boundary and W2 performs no checkpoint resume. ManagerReview/optional SemanticAuditor use the
   existing provider bridge, bounded repair/retry, and typed failure routing; exhaustion returns control or fails the
   case without an implicit state write or unbounded role loop.
8. **Reuse constraint — preserved.** Do not import or fork LongHorizon-Harness's generic Environment/orchestrator. Reuse
   its bounded routes/evidence discipline selectively while following Agent S2's combined review/replan cadence. Do not add
   `CompactStep`, `HistoryProjector`, `CaseSession`, another provider, another GUI loop, or another evaluator.

Required focused evidence includes: a synthetic episode longer than eight actions with the first action still visible
through the existing `AgentTurnView` compact rendering; a navigation scenario that pins an exact value and uses it
later; a two-episode scenario proving old
trajectory exclusion and accepted fact promotion; an evidence-boundary rejection that leaves MissionState unchanged; a stale
or hidden evidence pin rejection; one oscillation-triggered yield and Manager recovery; and final native evaluation
remaining the only success authority. Also prove that premature FinalResponse is unavailable in an ordinary episode,
`YIELDED` never becomes a benchmark outcome, user wait resumes without replanning, cancellation does not audit, and
the same BrowserGym adapter survives episode boundaries without a reset. Also prove: normal W1b task 0 invokes
Manager exactly twice (initial + review), Auditor zero times, and Finalizer zero times; review returns assessment,
next route, and—only for `request_finalization`—the direct schema-valid response plus supporting evidence refs in one
result; budget/stall reaches one review call without silently repeating the same contract; deterministic
pinned-fact promotion invokes no Auditor; exceptional strict verification invokes Auditor at most once; finalizing
admission invokes no ToolCatalog or ActionPolicy provider call; malformed final output cannot fall back to
read/search; one mechanical boundary constructs one FinalResponse. Cover bounded role failure, FinalResponseBoundary
rejection, and EvidenceBoundary rejection; a composition test
must fail if the offline evaluator helper is wired into W1b/W2.

#### W1b: compatibility smokes

The pinned dataset has single-site tasks for shopping, shopping admin, Reddit, GitLab, and Map, but none for
Wikipedia. Freeze the lowest task ID for each available single-site category and the lowest Wikipedia-bearing task
that is not in W2. This produces the following executable, non-proof smoke set:

| Coverage | Task ID | Template ID | Revision | Sites |
|---|---:|---:|---:|---|
| shopping admin | 0 | 279 | 2 | shopping_admin |
| Map | 7 | 79 | 2 | map |
| shopping | 21 | 222 | 2 | shopping |
| Reddit | 27 | 33 | 2 | reddit |
| GitLab | 44 | 303 | 2 | gitlab |
| Wikipedia | 266 | 85 | 4 | wikipedia, map |

These cases are excluded from the W2 proof cohort. They prove only the shared adapter boundary:

W1b-Agent is explicitly manager-guided but bounded: composition calls Manager once at task start, runs the existing
CoreAgentLoop against the resulting one-item GoalPlan, and calls the same Manager once in `review_and_route` mode when
the episode proposes an outcome or stalls. A normal one-episode retrieval permits no additional Manager call and no
Auditor. This retains useful semantic route guidance without converting the smoke into a mandatory MEA pipeline.
GoalCompiler remains disabled in this mode because Manager already owns subtask decomposition.

- reset returns the official instruction and a usable BrowserGym observation;
- model delivery preserves exact expanded AX/DOM structure, exposes a complete region directory, and recovers folded
  public facts through `inspect_world` without leaking private task/evaluator data;
- current action compilation and at least one official BrowserGym dispatch work, with no eligible action silently
  absent from both direct tool exposure and `find_actions`;
- ref-free Recent Steps remain temporal-safe across navigation and tab changes;
- `FinalResponse` reaches BrowserGym STOP in the official schema; and
- native result, cleanup, trace, and report persist without a special runner.

W1b is executed in two ordered parts. **W1b-World** is a read-only diagnostic over fresh official pages and captured
post-navigation pages; **W1b-Agent** is the six model smokes above. A MiniWoB pass cannot waive W1b-World, and a model
failure before ActionPolicy cannot be counted as a World/Context result.

T0 W1b-World passed on 2026-08-18 under `evidence/w1b-world-t0/` using the fixed BrowserGym Python and existing
WebArena-Verified W1 cases. All six site categories reported `status=ok`, zero offered targets missing from Actor View,
complete action-decision-state retention, zero structural-closure violations, zero private/evaluator leaks, and
`find_actions` recovery for the two partial action inventories (GitLab and Wikipedia/map). This is a World/Actor
contract gate only; it did not call ActionPolicy, GoalCompiler, Manager, Auditor, or any provider, and it did not
mutate the GUI after official reset.

T1 BrowserGym capability installation is now implemented and locally verified. `scroll` and `press_key` are installed
through the surface profile, primitive translators, private bindings, current ActionSpace, action paging/tool catalog,
admission/binding/execution route, fresh World acquisition, outcome projection, and benchmark instrumentation. The real
MiniWoB conformance dispatches viewport scroll and button Enter press through the product target loop with
`provider_attempts=0`. The follow-up six-site W1b-World read-only diagnostic passed under `evidence/w1b-world-t1/`;
it again did not call ActionPolicy, GoalCompiler, Manager, Auditor, or a provider and did not perform GUI mutation
beyond official reset/navigation acquisition.

T3 complete-request accounting/admission is implemented and locally verified. The model-delivery boundary measures
the full request, including stable system prompt, task/GoalPlan, WorldDeliveryView, episode history, working set, current
native tool schemas, image estimate, repair payload, and provider-envelope overhead. Initial and repair requests are
admitted independently; over-budget requests return typed `context_capacity` with `provider_attempts=0`. The
repeated-failure breaker is owned by `EpisodeMonitor` and yields `repeated_failure_limit` only on the third identical
ref-free typed failure/no-change key; public World progress, changed operation/target/arguments, satisfied local
postcondition, terminal formal evaluation, public criterion/output progress, and user revision reset the streak. Stable
`INCOMPLETE` task evaluation is not progress and does not clear the streak. T2 hover/focus remains deferred pending
benchmark evidence.

T3 semantic-safe compression is not complete. Its retired soft-target `action_focused` branch conserved current offered
targets and action-decision state but explicitly omits non-action roots with no recovery route. A provider-free
counterexample can place an exact issue ID or destination code in one non-action subtree and a `Continue` button in
another: the focused projection retains only the button. This is a delivery-contract defect, not a policy failure and
not evidence that the full World lacks the fact. This evidence triggered T3.1 recoverable region delivery. Its
provider-free round-trip gate subsequently passed, but that result is now explicitly scoped to recovery mechanics. It
did not close functional PageMap quality, first-view discoverability, search-to-action promotion, or model-visible
ref/tool deduplication; those shared gaps are the active semantic-delivery gate below.

The T3 W1b-World provider-free rerun passed on 2026-08-19 under `evidence/w1b-world-t3/` using the fixed BrowserGym
Python. It did not call ActionPolicy, GoalCompiler, Manager, Auditor, or any provider.

On 2026-08-19 the WebArena BrowserGym currentness gate was repaired and verified separately from model behavior.
BrowserGym read-only probes now treat MiniWoB task globals as optional native facts: present valid `ready/done/episode`
values remain authoritative, malformed present values fail as typed `currentness_unavailable`, and missing values use
the adapter lifecycle for executable-session currentness. The shared resolver covers element/drag, viewport/focused
keyboard, and visual bindings, and `ActionResult.adapter_evidence` records typed currentness status, reason, task-state
source, episode source, probe count, and effectful dispatch count. A provider-free scripted smoke on W1 shopping-admin
task 0 selected the public `REPORTS` link through `ActionSpace -> Binder -> BrowserGymSurfaceAdapter.execute` and
returned `currentness_status=current`, `currentness_reason=current`,
`currentness_task_state_source=lifecycle_fallback`, `dispatch_status=sent`, `effectful_dispatch_count=1`,
`step_calls=1`, and a fresh post-action World. This closes the WebArena mutation-path currentness gap only; W1b-Agent
and W2 remain blocked on the declared delivery/recoverability gates and model smokes.

The subsequent W1b task-0 failure is therefore recorded as long-horizon audit delivery, not currentness or second-turn
context growth. The first episode completed the Reports -> Bestsellers -> Year -> date -> Show Report GUI path and
yielded with the answer table visible, but Auditor admission failed before provider dispatch because it serialized the
same visible evidence three ways: compact World F refs, full `audit_world.facts`, and full `audit_bundle.evidence`.
The local repair makes Auditor reuse the same `AgentContext`/`compact_ax.v1` public delivery path, exposes only
model-visible `F#` refs/counts in `audit_evidence`, retains the 4096-record World evidence authority internally in
the bounded evidence bundle, resolves F refs privately before `EvidenceBoundary`, and records resolver rejections as
`invalid_tool_arguments` or `tool_grounding_gap` rather than `schema_error`. Targeted local verification passed, but
this historical gate is superseded: a short W1b compatibility task must not prove the mandatory
`Manager -> Auditor -> Manager -> final Auditor` cadence. Run8 later showed that removing Manager entirely was also
counterproductive. Run10 then rejected a correct answer at the generic tool envelope. The current gate is
`Manager(initial) -> CoreAgentLoop -> Manager(review_and_route + final_response) -> FinalResponseBoundary -> native
evaluator`, with Auditor and Finalizer calls fixed at zero for task 0.

A second 2026-08-19 W1b task-0 diagnostic reached an earlier inner-loop failure. After `REPORTS` opened, the fresh
World contained `Bestsellers`, but that structure-visible link did not enter the current `ActionSpace` or model-visible
tool catalog on that observation. The local repair keeps the fix at the observation/projection owners: BrowserGym
capture performs a bounded owner-thread re-sample until the executable inventory stabilizes, projection records
`action.why_not_eligible` and a `browsergym_action_eligibility` artifact for structure-visible targets with no binding,
and episode history stores public semantic World fingerprints so Monitor can detect `A -> B -> A` oscillation using the
same identity domain it compares against fresh worlds. No prompt, GoalPlan, Manager, or new stop rule was changed.
Targeted verification passed; the user explicitly deferred the same-case model rerun, so W1b-Agent remains non-closed.

The next run under `evidence/live/w1b-one-task-0-aliyun-glm51-watch3-20260819T023003Z` made the success/failure split
sharper. The first episode reached `yield_subtask:ready_for_audit` after the Reports -> Bestsellers -> Year -> date ->
Show Report path, and the model text identified `Quest Lumaflex™ Band`. Auditor then failed locally with
`context_capacity` and `provider_attempts=0` because the supposedly compact episode history still serialized large
transition/fact-change payloads into the then-8 KiB audit budget. The follow-on Manager episode and later
`policy_failure:schema_error` were downstream symptoms. The local repair bounds episode history, indexes retained
target/structure labels such as table cells as current public scalar `fact:` evidence, and makes episode audit
provider/context failure terminal instead of feeding an empty MissionState back to Manager for a duplicate GUI subtask.
No same-case model rerun is claimed after this repair.

##### W1b task-0 watch4: action/recovery convergence reopened

The later run at
`evidence/live/w1b-one-task-0-aliyun-glm51-watch4-20260819T083223Z/` did not reproduce currentness or provider-schema
failure. It exposed a shared inner-loop contract gap and must not be summarized as successfully opening
Products/Bestsellers. The trace shows this exact causal sequence:

```text
activate REPORTS                                      # dispatched
policy selects E114 "Bestsellers"                    # E114 has no verbs; not in activate enum
Runtime rejects the target                            # correct local admission
same-call tool repair substitutes E14                 # semantic target changed
E14 dispatches "Close menu"                          # Dashboard restored
inspect_world(find "Bestsellers")                    # relevant readable/actionable nodes exist
find_actions(query + exact target + relevance_role)   # strict AND -> empty ActionPage
inspect restores base inventory -> repeated empty search
EpisodeMonitor observes no GUI ActionOutcome and misses the control oscillation
```

The Dashboard ActionSpace already contained executable `Bestsellers` actions (`E90`/`E96` in that generation), so
this is not evidence that another GUI capability or site-specific selector is required. It is also not evidence that
generic repetition should enable VLM. Four existing owners require one coordinated repair:

| Gap | Owner | Required repair | Explicit non-goal |
|---|---|---|---|
| readable `E114` looked executable | Actor projection + ActionSpace/ToolCatalog | reserve `E*` for executable targets, use `N*` for read-only nodes, print verbs inline, record typed `why_not_eligible` | label/task special case |
| repair changed `Bestsellers` to `Close menu` | ActionPolicy protocol boundary | delete model repair/reselection; preserve the original invalid call as typed feedback with no dispatch | hidden second policy decision |
| recovery results were hard to act on | `inspect_world`/`find_actions` owners | inspect returns actionable/verbs/action refs; `exact_target` and AND semantics are explicit; omit `relevance_role` without an objective; empty search preserves base page and reports applied filters/relaxations | second action registry or automatic execution |
| local tools oscillated without recovery | EpisodeMonitor + existing ActionPolicy | include ref-free LocalToolResult/ActionPage result keys; second stable no-information signature emits one `RECOVER(control_stall)` turn that restores the base page/lens and forbids the same immediate signature; third/failing recovery yields | direct VLM, a new Recovery Agent, or semantic task-failure inference |

Visual grounding is a separate binding completion route inside the same admitted action. An ActionOption may be
offered when it has a structural or bounded visual binding route. After policy selects that executable target,
`VISUAL_ONLY_TARGET`, `GROUNDING_GAP`, or `GROUNDING_AMBIGUOUS` may call the visual grounder once in the same CoreLoop
step, producing a typed private binding for the existing Binder and one BrowserGym dispatch. Invalid `N*` refs,
control stalls, policy indecision, stale/disabled targets, and no-effect execution cannot trigger it directly. They
first enter typed recovery routing. A stall classified as `grounding_stall` may then use the admitted visual route;
state oscillation, discovery loops, uncertain external effects, and semantic strategy failure may not. The grounder
does not choose a replacement action, mutate the GUI itself, or declare completion.

Recovery is deliberately bounded rather than being another model role:

```text
first same no-progress signature -> exact feedback
second                            -> one RECOVER turn in existing ActionPolicy
third or failed recovery          -> YIELD(failed_strategy/control_stall)
```

An `A -> B -> A` transition enters recovery immediately because it already proves both repetition and successful
state-changing execution; VLM would not repair that semantic reversal. A pre-dispatch grounding failure can use VLM
in the same step. A post-dispatch visual retry additionally requires a retry-safe/idempotent action contract and fresh
mechanical evidence that the local outcome was not reached; unknown-effect or irreversible event actions are never
auto-repeated. In long-horizon mode, the first stalled episode returns its typed failed-strategy evidence to Manager
for a changed route instead of becoming terminal `REPEATED_FAILURE_LIMIT`; the same failure signature recurring in a
subsequent episode may exhaust the mission recovery budget.

The same trace also invalidates the current provider token aggregate. Its physical inputs were 15,598 tokens for the
initial call and 15,844 for repair. The repair attempt stored the cumulative 31,442 and diagnostics added the initial
15,598 again, publishing 47,040. Until repaired, this metric must be labeled invalid. Correct accounting records
per-network-call deltas, sums them once into `invocation_input_tokens=31,442`, separates cached input, and sums
invocations once at case/run level. Request-admission estimates remain a separate diagnostic and are never added to
provider usage.

Implementation is intentionally one convergence increment, not four independent patches:

1. finish the `E executable / N read-only / F evidence / R region` contract by making the renderer return a typed
   `DeliveryManifest`, removing full-ref Tool enums, and checking current-generation closure at Runtime admission;
2. constrain role repair to representation equivalence and project typed grounding rejection into the next normal
   policy context;
3. close inspect/action-search response semantics and preserve the base action page on empty search;
4. add same-turn `BindingRouter -> VisualGroundingPort -> existing Binder` with the bounded trigger/outcome algebra;
5. extend EpisodeMonitor to zero-dispatch control turns and `CONTINUE -> RECOVER once -> YIELD`, projecting one
   `RecoverySignal` into the existing ActionPolicy rather than adding a recovery model;
6. fix physical-attempt delta, semantic-invocation, and run-level token aggregation; and
7. rerun provider-free invariant/property tests, then exactly one same-case W1b witness before six-site smokes.

The predeclared exit properties are:

- every model-visible `E*` has at least one current verb, exists in the typed DeliveryManifest, and resolves through
  the current ActionSpace; no `N*` is executable;
- repair cannot change operation, target identity, or semantic arguments;
- zero-result action search cannot erase current action authority, and all recovery responses state actionability;
- only an already-admitted grounding gap/ambiguity, including a stall classified as grounding, can invoke VLM, at
  most once per observation/operation/target; oscillation/control/strategy stalls cannot;
- repeated local-tool results and action-page alternation receive one strategy-changing recovery turn and then yield
  `control_stall` within the bounded threshold if no new evidence appears;
- `attempt -> invocation -> run` token totals count every physical request exactly once; and
- the same W1b case either advances through an executable Bestsellers target or returns one truthful typed failure,
  without Close-menu substitution, empty-page oscillation, or false token amplification.

Current implementation status is now
`W1b action/recovery convergence implemented and locally verified / Auditor AuditView evidence projection repaired
locally / final-response contract delivery implemented locally / previous W1b task-0 witness reached final response
but official native outcome remained blocked / T3.2 semantic delivery reopened / W1b-Agent blocked`. The
provider-free watch4 synthetic witness proves that read-only
`Bestsellers` remains non-executable, repair cannot swap it to an unrelated executable target, current executable
matches are exposed, empty action search does not erase the base page, and repeated local discovery results route
through `CONTINUE -> RECOVER -> YIELD`. The official same-case witness at
`evidence/live/w1b-one-task-0-aliyun-glm51-convergence-20260819T102415Z/` advanced through executable refs to the
Bestsellers report, set the 2022 filters, observed `Quest Lumaflex™ Band` as the top row, and yielded
`ready_for_audit`; the case reports `status=failed` because Auditor admission rejected the request with
`context_capacity` before any provider attempt. The root cause was model-facing evidence duplication: compact World
already carried visible `F#` facts, then `audit_world.facts` and `audit_bundle.evidence` each serialized the same
visible canonical `EvidenceRecord` set. The repaired Auditor request keeps the full `AuditBundle` internal, deletes
both full evidence lists from provider payloads, exposes only visible public F refs/counts in `audit_evidence`,
resolves returned F refs privately before `EvidenceBoundary`, and records role admission diagnostics plus the
`auditor_context_capacity` subreason. This remains separate from action refs, repair, visual grounding, and
control-stall recovery.

The post-repair same-case witness at
`evidence/live/w1b-one-task-0-aliyun-glm51-auditview-20260819T111504Z/` removed the Auditor capacity failure:
Auditor admission was `admitted` with `estimated_total_tokens=13008`, `evidence_tokens=476`,
`admission_limit=61880`, and `provider_attempts=1`. Auditor accepted the cited `top1_bestseller_2022` fact and
Manager requested final audit; final response delivery returned `Quest Lumaflex™ Band`. The official case still
reports `status=blocked` with `verified_terminal_task_failure`, so the remaining gate is finalization/native-evaluator
compatibility, not GUI action selection, repair, Auditor context capacity, or provider dispatch.

The final same-case run on the completed worktree at
`evidence/live/w1b-one-task-0-aliyun-glm51-auditview-final-20260819T112859Z/` followed a different 10-step route with
`inspect_world` control-stall recovery and then failed before provider dispatch because the same deterministic compact
history was 13,812 bytes, above the local 8 KiB Auditor history cap but still far below the provider admission limit.
The local Auditor history cap is therefore 16 KiB while full-request admission remains the hard authority.

The current local repair removes unconditional final LLM audit and restores public final-response contract delivery:
WebArena intake preserves the marker-delimited public final schema in `public_final_response_contract`, ordinary GUI
turns hide it, finalizing turns expose it, and Supervisor validates/one-shot wraps plain retrieved text into the public
JSON response shape before `send_msg_to_user`. No benchmark rerun has been performed after this final-response contract
repair. The next run is not authorized until T3.2's paired provider-free cost/recoverability gate passes; after that,
one same-case provider witness jointly checks finalization/native-evaluator compatibility and the declared request-cost
measurements before the six-site W1b-Agent smokes.

| Site category | Tool schemas | Offered targets | Missing Actor targets | State retained/total | Closure leaks | Projection | Prefit tokens | Admitted tokens |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| shopping_admin | 11 | 34 | 0 | 69/69 | 0/0 | full | 14,695 | 14,695 |
| map | 10 | 36 | 0 | 75/75 | 0/0 | full | 8,283 | 8,283 |
| shopping | 10 | 42 | 0 | 88/88 | 0/0 | full | 15,590 | 15,590 |
| reddit | 10 | 16 | 0 | 36/36 | 0/0 | full | 6,350 | 6,350 |
| gitlab | 10 | 36 | 0 | 75/75 | 0/0 | action_focused | 22,955 | 9,378 |
| wikipedia/map | 10 | 36 | 0 | 75/75 | 0/0 | full | 13,925 | 13,925 |

All six request budgets were admitted under the derived 62,904-token hard cap with `image_estimated_tokens=0` and
`provider_reported_prompt_tokens=0` because this diagnostic is provider-free. GitLab crossed the approximate 16k soft
cost target and was re-rendered through action-focused delivery compaction. The run proves offered-target,
action-decision-state, and retained-subtree closure only. Because the projection reported
`non_action_content=omitted recovery=none`, its 9,378-token result is recorded as an unsafe diagnostic and cannot count
as semantic-safe compression evidence. The uncompressed 22,955-token request remained under the hard cap.

##### T3.1: historical recoverability skeleton — implemented, not semantic-delivery closed

T3.1 replaces action-only omission with one recoverable model-delivery path:

```text
full current WorldObservation
  -> deterministic ActorWorldSnapshot
  -> deterministic WorldRegionIndex
  -> current WorldDeliveryLens
  -> complete region directory + exact expanded subtrees
  -> ActionPolicy
       |-> find_actions(query) # searches complete current ActionSpace
       `-> open_region/find_content/list_regions over complete public World
```

The full World remains the sole environment authority. `WorldRegionIndex` and `WorldDeliveryLens` are disposable
projections. Region descriptions are extractive—landmark/role, exact heading or labels, item/action counts, bounded
state badges, changed flag, and coverage. They never replace exact prices, IDs, dates, values, status, or user-authored
text. Expanded regions preserve exact public values, relations, current refs, and structural closure. The split
read-only tools perform zero BrowserGym dispatch and support:

- `open_region(region_ref)`: exact structurally closed, semantically paged subtree;
- `find_content(query)`: exact current public text/role/label/value/fact matches with region location;
- `list_regions()`: exact paged fallback when the directory is insufficient;
- dynamically offered `read_next_page()`: continuation with Runtime-private paging state; and
- structural inspection only in the verified baseline. Typed current screenshot crop/visual zoom remains a later
  declared gate through the existing perception/image-admission path; it is not claimed by T3.1.

Every read call is bound to current World/context/catalog identity. Fresh acquisition invalidates old R/E refs,
private paging state, query results, and lens state. Direct tool targets must be present in exact delivered content;
actions in folded regions remain reachable through `find_actions`. No region selector may alter the complete ActionSpace or
private bindings.

The historical T3.1 gate covered the following round-trip properties. Passing them remains regression evidence, not
the exit condition for the reopened semantic-delivery contract:

1. every public fact/entity/relation is delivered exactly or belongs to a visible region recoverable through one
   `inspect_world` operation;
2. sampled folded prices, IDs, dates, values, statuses, table cells, repeated items, and user text round-trip exactly
   from the same World, without model paraphrase;
3. every current ActionOption is directly exposed or reachable through `find_actions`, and every directly exposed
   target appears in an exact expanded subtree with the required state and closure;
4. `open_region`, `find`, `view_all`, paging, and optional crop perform zero GUI dispatch and never change the full
   World semantic digest;
5. old World/context/catalog/region refs typed-fail after fresh acquisition; no resolver guesses a replacement;
6. provider input records directory/expanded/search/crop coverage plus complete prefit/admitted token composition;
7. a directory plus one useful exact page that cannot fit the hard cap returns `context_capacity`; it never prefix
   slices, breaks a row/card, or falls back to `recovery=none`; and
8. full-view and region-delivery paired diagnostics report token reduction and recovery latency, without treating a
   soft cost target as a correctness gate.

The first implementation uses deterministic AX/document landmarks, dialogs, forms, tables, lists/feeds,
heading-associated sections, and bounded repeated-sibling groups. Region4Web's learned partition/summary and
FocusAgent's LLM line selector remain predeclared later A/Bs only if this deterministic held-out gate or W1b-Agent
demonstrates a retrieval failure. They cannot be silently added during the baseline run.

##### T3.2: functional PageMap, exact ActiveView, and stable tools — reopened

T3.1 proved bounded current-World round-trip recovery when a caller already knew which operation/query to use. It did
not prove that an ActionPolicy could understand the first view, discover an omitted target, or carry a search result
into an executable next turn. The current cost-first implementation is smaller but still fails that semantic gate: on
the task-0 first page it produced one giant generic region, several empty/icon regions, viewport/focused-context
expansions, model-visible facet member refs, a separate affordance map, and broad dynamic ref enums. The renderer then
used a regex over its own text to decide which refs were directly delivered. A roughly 7.5k-token request can therefore
be cheap and still be confusing. Capacity, cost, recoverability, and discoverability are separate measurements.

The `watch3` trace remains the frozen cost counterexample. Its ten initial ActionPolicy calls consumed
119,524 provider prompt tokens and two repair calls consumed another 48,111; 28.7% of total prompt input was repair.
The largest initial/repair pair was 15,050/30,336 tokens. This is not an accounting defect: the initial call repeatedly
sent a full compact Magento page, cumulative episode history, and broad current Tool Schemas, while PydanticAI repair
replayed the original message history. Later history projection reduced transition payload, but the post-repair
`auditview` witness still used 90,368 input tokens across eight ActionPolicy calls, about 11.3k per call, with no action
repair. Therefore the primary remaining cost defect is delivery selection, not Auditor or the history byte cap.

The combined causal chain is explicit:

```text
shallow AX-root partition
  -> giant generic + empty/icon regions
  -> no usable functional page map

Actor facets/member refs + separate affordances
  -> rendered text contains hidden E refs and repeated verbs
  -> regex _delivered_refs treats any textual E ref as exact delivery
  -> dynamic Tool enums repeat or expose that inventory

inspect_world(find)
  -> exact local result
  -> no persistent same-World find lens
  -> sanitized history removes its refs before the next action

find_actions
  -> ActionPage count/filters
  -> model lacks one compact exact labeled SearchResults view

stateless provider call t
  -> republishes compact history[1..t-1]

historical representation repair (retired)
  -> result.all_messages() + same ToolSet + repair request
  -> replaced by local normalization or same-episode typed feedback
```

T3.2 changes only model delivery. Full `WorldObservation`, complete `ActionSpace`, private bindings, execution,
ActionOutcome, TaskEvaluator/native authority, trace, and the single ActionPolicy loop remain unchanged.

| Owner | Required change | Must not become |
|---|---|---|
| current `WorldRegionIndex` owner | replace the shallow-root output with one `WorldDeliveryIndex`: meaningful landmark/heading/menu/table/form/list regions, complete content/action indexes, exact extractive descriptors, and no model-visible member refs; merge empty/icon fragments and split giant generic regions | a second World, learned summary authority, remembered page, or progress model |
| compact renderer | return one typed `WorldDeliveryView(text, DeliveryManifest)` containing an always-visible PageMap plus exact ActiveView/SearchResults; remove model-visible facets/member refs and the separate affordance map | string parsing as ref authority or another Actor snapshot |
| `WorldDeliveryLens` | support one same-World `region | find | view_all` selection by private region key/query/cursor; fresh World clears it; no public E/N/F refs are stored | memory, stable page state, MissionState, or task progress |
| `PerTurnToolCatalog` | use compact stable per-operation ref schemas; validate selected refs against DeliveryManifest + current ActionSpace/evidence/region authority; keep folded actions searchable through `find_actions` | a second ActionSpace, giant dynamic ref enums, or provider-side legality authority |
| `GroundedPolicyContextBinder` | always build a functional PageMap candidate, exact ActiveView, manifest and stable tools; compare full only when it satisfies the same clarity/recovery invariants | silent task-specific pruning or a token-only quality decision |
| episode-history renderer | latest four bounded semantic transitions; older one-line actions; remove World/context/catalog IDs, fingerprints, screenshots, unchanged state, full fact changes, DOM/CSS metadata, and prior tool menus | mutable progress summary or LLM memory |
| ActionPolicy protocol owner | local normalization first; otherwise typed same-episode representation/multiple-call feedback and zero dispatch | replay of World/history/images, target substitution, or another policy decision |
| historical optional SemanticAuditor manual role repair (superseded by run9) | no production behavior; retained only to explain the retired T3.2 proposal | a supported invocation path; current Auditor uses the same strict PydanticAI ToolOutput adapter as Manager |
| request instrumentation | record full-candidate, admitted-candidate, per-component, repair-amplification, recovery-turn, and provider physical-attempt tokens | control authority or sums that mix estimates with usage |

The implementation remains within the existing owners. Evolve or rename
`agent/context/world_region_index.py` in place; change `agent/context/compact_world_renderer.py` to return the typed
view/manifest; consume it in `model/policy/grounded_policy_context.py` and
`model/policy/grounded_tool_catalog.py`; keep lens lifecycle in `agent/context/world_delivery_lens.py`; keep complete
request fitting in `model/policy/request_admission.py`; and extend the existing WebArena diagnostic in
`benchmarks/webarena_verified.py`. No new ContextBuilder, ActionSpace, Tool Registry, browser adapter, or model role is
created.

The fixed implementation order is:

1. replace shallow region seeds with deterministic functional boundaries: landmarks, dialogs, forms, tables/lists,
   heading sections and bounded top-level menu groups; merge empty/icon fragments and split giant generic roots;
2. change the renderer result from `str` to typed `WorldDeliveryView(text, DeliveryManifest)`; delete regex ref
   recovery, public facet member refs, and the separate affordance projection;
3. make every first view a complete extractive PageMap plus exact ActiveView. List bounded top-level navigation in the
   PageMap and render its controls exactly in ActiveView; rank at most one or two additional regions by public
   task/subtask/GoalPlan/recovery text without removing
   any PageMap entry or recovery route;
4. replace full dynamic ref enums with stable per-operation patterns and Runtime Manifest + ActionSpace validation;
5. close `inspect_world(find/open_region/view_all)` and `find_actions` so exact results install a same-World lens/page
   and appear as labeled SearchResults with current state/verbs in the next request;
6. compare the valid PageMap view with normalized full on every ordinary call; retain full only when it is smaller and
   satisfies the same semantic-overview/discoverability contract;
7. narrow `AgentTurnView` delivery to semantic action plus changed predicates/results, while leaving complete
   `StepResult` and evidence in trace;
8. delete ActionPolicy provider repair/reselection; use local normalization or same-episode typed feedback, while
   keeping Auditor's one narrow role-owned schema repair;
9. add paired provider-free PageMap/full diagnostics on the six W1b pages and held-out synthetic structures;
10. after separate future authorization, run a task-0 provider witness on the completed tree, jointly checking
   first-view discovery, search-to-action closure, finalization and cost; no provider witness is part of the current
   provider-free convergence increment.

The semantic-delivery properties take precedence over cost:

- every functional region descriptor satisfies the frozen `DeliveryLimits.v1` grammar and 160-token bound; fragments
  with zero normalized alphanumeric public text/actions/values/state are merged, while an unlabeled generic with at
  least two heading/landmark descendants or more than 4,000 estimated descendant tokens is split;
- every current public fact/relation is exact in ActiveView/SearchResults or indexed by a visible PageMap region and
  recoverable through `inspect_world`;
- every ActionOption is exact/direct or reachable through `find_actions`; every retrieved result appears in the next
  exact SearchResults/DeliveryManifest and resolves through the ordinary action path;
- folded PageMap entries contain no E/N/F refs; exact refs come only from the typed renderer manifest; there is no
  separate model-visible affordance map, facet member-ref list, or full-ref Tool enum;
- bounded top-level navigation is listed in PageMap and its exact controls are actionable in the first ActiveView;
  large repeated content exposes headers/schema/count/state plus an explicit recovery operation;
- page/lens change and fresh acquisition preserve currentness and invalidate stale E/N/F/R refs;
- current state for direct controls, exact table/header/row structure, and changed regions survive;
- protocol feedback preserves the rejected operation/target identity, performs zero provider repair calls and zero GUI dispatch;
- compression never reads benchmark identity, expected answer, evaluator state, selector, coordinate, or private
  binding.

The cost gates are diagnostic but falsifiable:

| Request class | T3.2 pass rule |
|---|---:|
| six frozen new-page requests | every request <=12k provider input tokens and median <=9k |
| task-0 steady same-page requests | every ordinary request <=9k and p95 <=12k |
| model-facing episode history | every request <=1.5k |
| current Tool Schemas | every request <=2k; no full current-ref enums |
| ActionPolicy representation/protocol feedback | zero repair-provider input and zero GUI dispatch |
| paired full/delivered observation | on every frozen page whose valid normalized-full request exceeds 12k, delivered request is at least 30% smaller; on other pages it is no more than 5% larger |
| task-0 total ActionPolicy input | at least 40% below the 90,368-token `auditview` baseline |

The 2026-08-19 T3.2 provider-free implementation run is recorded under
`evidence/w1b-world-t32-semantic-delivery-run3/`. All six pages completed the production World/Actor/index/view/catalog
projection with zero provider calls and unchanged BrowserGym dispatch metrics. New-page request estimates were
`5,031 / 5,803 / 6,460 / 7,847 / 9,039 / 9,046` tokens (median `7,153.5`); corresponding normalized-full estimates
were `10,117 / 21,181 / 6,925 / 20,551 / 38,846 / 21,254`, and model-facing history was 35 tokens on every page.
The cost gate therefore passed, but the combined semantic gate did not: frozen probes reported role-kind mismatch for
shopping-admin `Orders` and reddit `Search`, plus missing initial page identity/action on shopping. The shared causes
found during the run—three-digit F-ref exhaustion, missing public route identity, and an ActiveView with no executable
region—were repaired at their owners and covered locally; the frozen role-kind mismatches were not changed or patched
per site. No fresh-context audit or live task-0 witness is authorized from this evidence. Honest status remains
`T3.2 implementation in progress / provider-free semantic delivery gate failed / live verification pending /
W1b-Agent blocked / non-closed`. This run remains failed evidence and was not overwritten.

Probe v2 corrects the evaluator rather than the product path. One recovered item must jointly satisfy the expected
label, role, required operation, and next exact `DeliveryManifest`; a label on one item and a role/action on another
cannot pass. Task 0 is frozen as `Bestsellers + tab|link + activate`, and task 27 as
`Search + searchbox + type_text`. Task 21 was independently diagnosed on the official product page before its witness
was revised to the task-related `Reviews + link|tab + activate`; task 44 was likewise revised from the unrelated
`Projects` heading to `Todos -> To-Do List + link + activate`. These values are evaluator-only public UI witnesses and
never enter production Context, ranking, ActionSpace, or Binder.

The 2026-08-20 probe-v2 run1 at `evidence/w1b-world-t32-probe-v2-run1/` is retained as a failed contract witness: five
pages passed, while GitLab correctly rejected the unrelated `Projects` heading under the new same-item rule. After the
task-44 read-only diagnosis and probe correction, run2 at `evidence/w1b-world-t32-probe-v2-run2/` passed all six pages:
`ready=true`, `acceptance_errors=[]`, and zero provider attempts. New-page estimates were
`4,677 / 5,510 / 6,106 / 7,499 / 8,685 / 8,717` tokens (median `6,802.5`); complete Tool Schema estimates were
`1,739` or `1,879` tokens. The schema reduction only removes repeated current-ref/currentness/outcome prose; it does
not merge tools or change Registry, Resolver, Binder, Executor, or TaskEvaluator authority. Fresh-context audit is the
next gate. That audit found one P1: a deliberately bounded ContextBuilder profile could still shrink public Actor facts
after initial lossless projection, while DeliveryIndex used the full World and allowed recovery probes to pass. The
repair removes whole-context Actor fitting, leaves delivery capacity to WorldDeliveryView/request admission, and adds a
property witness retaining 64 nodes plus 256 public facts under an 8-KiB legacy budget. The post-repair six-page run at
`evidence/w1b-world-t32-probe-v2-lossless-run3/` again passed 6/6 with equal retained/total Actor node counts, zero
provider attempts, requests `4,677 / 5,510 / 6,106 / 7,498 / 8,692 / 8,718` (median `6,802`), and Tool Schemas
`1,739 / 1,879`. The independent re-audit passed with no P0/P1/P2. Per explicit user direction, no task-0 live/provider
witness is run in this increment. Live behavior remains unverified and requires separate future authorization;
W1b-Agent/W2 receive no new evidence from this provider-free result.

The 2026-08-20 direct-action-promotion increment then changed only delivery ranking/closure, the grounded prompt, and
the existing BrowserGym capability conformance. It promotes task-related current ActionOptions into the first exact
view, preserves E=executable/N=read-only/R=expandable, and adds no navigation macro or second policy/runtime loop.
Provider-free `run1` and `run2` under `evidence/w1b-world-t32-direct-action-promotion-run*/` are retained failed
diagnostics: recoverability constructed a region lens but its benchmark rerender call omitted that lens, so the 1-byte
atomic stress view selected the initial DirectActions block rather than the explicitly opened region. After correcting
that diagnostic call site, `run3` passed 6/6 with `ready=true`, no acceptance errors, zero provider attempts, estimated
requests `5,031 / 5,229 / 5,594 / 6,668 / 7,762 / 8,615` tokens, and Tool Schemas `1,739` or `1,879` tokens. This is
provider-free delivery evidence only; the existing live policy failure remains non-closed and no new live witness was
run in this increment.

The following structural-convergence increment corrects the later task-0 attribution: the five product rows were
present in Actor but split from old `R14 table` into sibling `R15 rowgroup`. The production fix makes table/grid/list
regions atomic, pages headers with complete rows, separates source/membership/page coverage, publishes bounded page and
ancestor scope plus current filter-control count, keeps top navigation ahead of lexical read-only data, and collapses
only fully proven nested native wrapper/anchor aliases. Monitor local-result signatures are now canonical digests with
bounded evidence, so 100 KiB and 1 MiB results follow `CONTINUE -> RECOVER(control_stall) -> YIELD` without an
exception. One generic prompt rule asks the policy to verify scope, filters, and evidence; no site, task, year, route,
or benchmark string entered production logic.

Provider-free replay of the retained old projected World proves that its Bestsellers table now resolves as one region
with schema plus five complete rows, scope `Dashboard / Magento Admin > Bestsellers`, zero filter controls, no top-level
rowgroup, and the executable REPORTS entry ahead of that read-only table. The immutable old World cannot be run back
through pre-World AX canonicalization, so native alias behavior is verified both by owner properties and a fresh
provider-free six-page acquisition. Run1 exposed and localized one audit-only inventory defect: deliberately collapsed
aliases still counted as recognized omissions. After correcting that canonical inventory count,
`evidence/w1b-world-t32-structural-convergence-run2/` passed 6/6 with `ready=true`, no acceptance errors, and zero
provider attempts. Task 0 returned three readable `Bestsellers` matches
but exactly one joint model action (`E22`) satisfying label, role, `activate`, and Manifest membership; actionable
targets fell from the old capture's 36 to 32 as the four native tab/link aliases collapsed, while canonical inventory
now truthfully reports `recognized=projected=365` and `omitted=0`. New-page estimates were
`5,313 / 5,835 / 6,675 / 6,775 / 7,077 / 11,695` tokens (median `6,725`). The full local gate passed with `1,329`
tests and `19` skips, plus Ruff and `git diff --check`. No live/provider witness was run.

These targets do not permit dropping evidence. An exact atomic table or dialog may exceed a target and remain
truthfully admitted, but the cost gate then remains failed; it is not an unbounded exception. Only the existing hard
cap returns `context_capacity`. Provider caching may be reported separately but cannot satisfy the gate because cached
full pages still consume attention and preserve the same distraction. No model selector,
summarizer, embedding index, second World, second Tool Registry, or provider-specific cache becomes part of T3.2.

##### T3.3: automatic current-action candidates and read/action interface separation — provider-free passed

The successful task-0 run12 proves the GUI route and final response, but it also falsifies the claim that the current
first-view promotion is efficient enough. After `REPORTS` was opened, the complete ActionSpace contained the
Reports-path `Bestsellers` action. The current shallow lexical promotion emphasized a same-label Dashboard
`Bestsellers` tab instead; the policy then called `read_region` three times before `search_actions("Bestsellers")`
recovered the intended executable target. The immediate read results also repeated `actionable`, `action_refs`, and
`verbs`, making content inspection look like a second action-discovery interface. This is an action-candidate ranking
and tool-presentation defect, not missing World authority, Manager planning, or Binder execution.

Run12's first request is retained as the cost/presentation baseline: it delivered 13 PageMap regions, seven exact
expanded regions, 61 visible actions, no screenshot or history, approximately 7,847 World tokens and 1,685 Tool-Schema
tokens (9,904 provider-reported prompt tokens). It did contain the executable `REPORTS` control and the policy selected
it correctly. It also expanded detailed Orders/Search/Dashboard-Bestsellers tables that were unnecessary for that
navigation decision. T3.3 must improve the post-navigation candidate ranking and first-view signal density without
misreporting this successful first step as a missing-action failure.

T3.3 evolves the existing delivery owner rather than adding another registry or planner:

```text
TaskGoal + current GoalPlan objectives
+ fresh complete ActionSpace
+ WorldDeliveryIndex functional paths
+ recent semantic outcomes
  -> deterministic ActionCandidateProjection(top_k=5)
  -> ActionCandidates + exact structural closure in DeliveryManifest
  -> existing stable operation tools

complete ActionSpace
  -> the same ranker
  -> find_actions(query) fallback
```

Mission mode does not expose `SubtaskContract` as another ranking input: its active objective is already projected by
the existing deterministic one-item GoalPlan boundary.

The implementation owners are fixed before code changes:

| Owner | Required change | Forbidden shortcut |
|---|---|---|
| `agent/context/world_region_index.py` | expose deterministic functional paths and region ownership for every current ActionOption without adding task state | site menu rules, selectors, expected routes, or another World |
| `agent/context/compact_world_renderer.py` plus the existing model-turn delivery seam | replace shallow `_preferred_action_refs`/DirectActions output with typed Top-5 ActionCandidates and exact candidate closure | parsing rendered strings, a second candidate store, or an LLM selector |
| `actions/paging.py` / existing action-search owner | make `find_actions` reuse the same rank features/order over the complete ActionSpace | a separate fuzzy-search truth or search-time execution |
| `model/policy/grounded_tool_catalog.py` and current local-result contracts | perform one breaking rename to `open_region`/`find_content`/`find_actions`, remove the old names without aliases, and remove immediate region/content-result `actionable/action_refs/verbs` duplication while preserving next-view promotion | merging read/content/action tools, retaining aliases, or silently choosing an E-ref |
| existing request/benchmark instrumentation | record candidate count, Recall@k/rank witnesses, observation-only calls before target action, repeated region-version reads, request tokens, and candidate/search provenance | benchmark values entering production ranking |

No CoreLoop, Manager, GoalCompiler, ActionSpaceBuilder, Binder, SurfaceAdapter, browser session, or task verifier owner
changes in T3.3.

The model uses semantic labels, roles, paths, state, and match reasons to reason, but every actual GUI call still
submits a current E-ref. T3.3 introduces no pure-semantic execution target and no `A*` namespace. Ranking is advisory:
it may fold lower-ranked detail but cannot delete PageMap entries, facts, actions, or recovery routes, and it cannot
authorize a call. Candidate refs must exist in the same `DeliveryManifest` and current ActionSpace before the existing
resolver/admission/Binder path accepts them.

The tool scopes are frozen as follows:

| Tool | Question answered | Result contract |
|---|---|---|
| `open_region(region_ref)` | what exact content is inside this known PageMap region? | content/table/status/result plus coverage/version; no immediate duplicate `action_refs` or `verbs`; legal controls appear through the next exact ActiveView |
| `find_content(query)` | where is this readable fact/value/text in the complete current World? | read-only N/F evidence with region location; no executable candidate merely because text belongs to a control |
| `find_actions(query)` | which current legal controls can perform this intent? | ranked current E-ref candidates from the complete ActionSpace, installed into the next SearchResults/Manifest |

This is one breaking cutover. No aliases are added. Historical evidence retains the old names as factual trace data;
production code, prompt contracts, current tool-schema tests, and post-cutover evidence use only the new names.

The provider-free T3.3 gate is property-based and includes held-out duplicate-label/path fixtures rather than a
Magento-specific branch:

- every candidate is a current executable ActionOption, is printed once with label/role/functional path/current
  decision state, and appears in the same Manifest;
- with two same-label controls under different functional paths, the objective/path-compatible option ranks above the
  unrelated overview control; the declared target has `Recall@5=1` and rank at most 3;
- rank input may use normalized lexical/BM25/fuzzy match, path, role/operation compatibility, newly-revealed state,
  already-satisfied state, typed no-progress history, and declared effect risk, but never case identity, an answer,
  selector, private binding, or an LLM/embedding call;
- all non-promoted actions remain recoverable through `find_actions`, which uses the same ranker and currentness
  algebra rather than a second filtering implementation;
- when a target is already present in ActionCandidates, a scripted policy can execute it without `open_region`; a
  live cohort separately reports observation-only calls before the first target action rather than making one model
  trajectory the provider-free oracle;
- `open_region` and `find_content` return no duplicate executable inventory, while controls in a successfully opened
  region still enter the next normal ActiveView/Manifest;
- `ActionCandidateProjection` changes neither World/ActionSpace digests nor GUI dispatch counters and cannot bypass
  resolver/admission/Binder.

The implementation and provider-free verification completed on 2026-08-20. The shared deterministic ranker now owns
both automatic Top-5 projection and explicit `find_actions` ordering; the renderer receives a typed
`ActionCandidateProjection`, and `ModelTurnDelivery` rejects any candidate absent from its own current Manifest. The
breaking public cutover leaves only `open_region(region_ref)`, `find_content(query)`, and `find_actions(query)` for
these scopes. Current `src/` and `tests/` contain none of the three old public names, `DirectActions`, or
`_preferred_action_refs`. Focused T3.3/semantic/tool/paging/integration tests passed `153`; the full suite passed
`1,343` with `16` skips; Ruff and `git diff --check` passed. The first bounded independent fresh-context audit exposed
one P1: destination-required actions could project a source candidate without closing their current destination
E-refs into the same Manifest. The candidate projection owner now carries typed destinations, the renderer closes
them, and both `AgentContext` and `ModelTurnDelivery` reject incomplete destination authority; a generic `drag_to`
property verifies the unchanged Resolver, Admission, and Binder chain. The second fresh-context audit confirmed that
repair but exposed an evidence P1: the task-0 witness did not distinguish same-label functional paths. The evaluator
now requires declared path tokens and persists matched paths, while the evidence statement below bounds the initial
Dashboard capture separately from the pending live post-Reports state. The final independent re-audit found no P0/P1.

The successful persisted six-page diagnostic is
`evidence/w1b-world-t33-provider-free-run4/w1b-world-summary.json`. Each row used local BrowserGym capture and
deterministic projection only; no provider or GUI action dispatch occurred:

| task | auto count | Recall@5 | rank | candidate∈Manifest | candidate∈ActionSpace | auto/find identity | observation-only calls | repeated reads | schema tokens | request tokens | discovery dispatch |
|---:|---:|---:|---:|:---:|:---:|:---:|---:|---:|---:|---:|---:|
| 0 | 5 | 1 | 2 | yes | yes | yes | 0 | 0 | 1,701 | 7,893 | 0 |
| 7 | 5 | 1 | 1 | yes | yes | yes | 0 | 0 | 1,614 | 5,966 | 0 |
| 21 | 5 | 1 | 1 | yes | yes | yes | 0 | 0 | 1,902 | 7,703 | 0 |
| 27 | 5 | 1 | 1 | yes | yes | yes | 0 | 0 | 1,683 | 6,221 | 0 |
| 44 | 5 | 1 | 1 | yes | yes | yes | 0 | 0 | 1,902 | 7,309 | 0 |
| 266 | 5 | 1 | 2 | yes | yes | yes | 0 | 0 | 1,749 | 7,650 | 0 |

All six cases recorded `provider_attempts=0`, empty acceptance errors, and the unchanged World/ActionSpace/execution
properties. The task-0 row is explicitly an initial-Dashboard witness and its probe now requires the `dashboard`
page-scope token. That token binds the witness to the captured initial Dashboard but does not disambiguate functional
paths within the same page. This six-page capture does not replay the later post-Reports World and does not claim to
prove that live route. The generic held-out duplicate-label fixture proves the bounded path-ranking property without
adding a site rule; the real post-Reports behavior remains part of the pending W1b-Agent live falsification. This is
provider-free candidate/read-action evidence, not a W1b-Agent live success claim.

Only after this gate and fresh-context review may the project run the next W1b-Agent breadth evidence. T3.3 does not
reopen T3.2 lossless World/recoverability evidence; it replaces the insufficient `DirectActions` ranking/presentation
layer above it.

The T3.3 cutover gate also checks removal, not only addition:

- production and contract tests contain no `DirectActions`, `_preferred_action_refs`, or separate automatic-candidate
  ordering beside the shared ranker;
- current product schemas contain no `read_region`, `search_world`, or `search_actions` aliases; immediate
  `open_region` and `find_content` results contain no `actionable`, `verbs`, or `action_refs`; a control
  discovered while reading becomes executable only through the next current Manifest/ActiveView;
- `find_actions` and automatic Top-5 delivery produce the same ordering for the same objective/query inputs and
  differ only in their declared search scope;
- the removed finalizer prompt, finalizer ActionPolicy episode, and `submit_final_response` ToolCatalog path remain
  absent;
- `native_single_tool` and `json_single_command` remain supported wire adapters and are verified to converge on the
  same Catalog/resolver/admission/Binder path. Their coexistence is not counted as a second GUI chain.

After the provider-free T3.3 gate, the frozen implementation order is:

1. one bounded fresh-context review of the candidate/read-action boundary;
2. W1b-Agent breadth evidence using the existing explicit manager-guided benchmark composition;
3. product-facade convergence so callers can explicitly select `standalone|manager_guided` without entering through
   the benchmark runner, plus one mechanical public result envelope for standalone `TaskOutcome` and admitted mission
   final responses;
4. T3.4 guarded same-form batching only if measured W1b turns/tokens justify it.

The third step does not introduce task-text mode inference, a routing model, another Manager, another CoreLoop, or a
second completion authority. It exposes an already existing composition choice and normalizes its public return shape.

##### T3.4: guarded same-form batch — deferred efficiency gate

`set_form_fields` is not part of candidate-recall repair. It may be implemented only after T3.3 and a held-out form
slice show that repeated policy calls, rather than candidate discovery, dominate cost. The proposed operation accepts
one current form E-ref and two-to-four distinct current field assignments using only installed `type_text` or
`select_option` primitives. Every child must belong to that form and be non-destructive; Filter/Submit, navigation,
dialog opening, upload, and any declared observation-barrier action are forbidden. Runtime stops the sequence on the
first currentness, URL, focus, validation, binding, or action-inventory change and reports completed/remaining fields.
Every physical primitive remains visible in dispatch metrics. Failure to preserve the existing
ActionSpace/Binder/Executor/currentness path leaves this operation unsupported; no generic multi-action queue or hidden
menu/navigation workflow is an acceptable substitute.

The initial-overview policy is explicit. Every profile receives the semantic PageMap. `structure-first.v1` sends no
image by default. `screenshot-ax.v1` may attach one resized current viewport image when the model/profile supports it;
Canvas/maps/charts, incomplete AX coverage, visually encoded state, or an admitted grounding/evidence need justify the
image or a later typed crop. Page size, long-horizon duration and policy repetition do not. Historical screenshots and
base64-in-JSON local results remain prohibited.

SOTA alignment is architectural where no pinned drop-in exists. BrowserGym remains the direct acquisition/execution
dependency. AgentLab supplies reusable BrowserGym-backed flattening, modality/SoM and token-fit behavior, but its
bottom-line truncation is not a semantic recovery contract. browser-use supplies reusable deterministic cleanup ideas
for wrappers, duplicate text/attributes, obscured content and inline interactive indices, but its browser tree and
selector map are not imported. Glass informs old-snapshot/tool-result compaction, not current functional regions.
Region4Web/PageDigest motivates the PageMap + selected exact regions + `view_all` shape, but its advertised learned
repository is not currently a pinned dependency. FocusAgent motivates a later task/history-aware selector A/B; its
retriever is not the baseline authority. Qwen3-VL OSWorld motivates older textual actions with only a bounded recent
rich image window. Learned line/region selection is added only if the deterministic PageMap/search gate still fails a
frozen cohort, and it must select existing region IDs while failing open to directory/`view_all` recovery.

The reuse decision is fixed for this increment:

| Source | Reuse form | Excluded form |
|---|---|---|
| BrowserGym | direct installed dependency for DOM/AX/rendering/screenshot/geometry, session and execution | another DOM walker, selector map, session or executor |
| AgentLab | reuse compatible token/image estimation and BrowserGym preprocessing utilities directly where their input contract fits | bottom-line/prefix truncation as semantic compression |
| browser-use | port only pure wrapper/text/attribute cleanup rules with attribution and tests over existing public World nodes | its DOM tree, browser, selector index, tools or Agent loop |
| Glass Browser | copy the already-adopted history/tool-result elide-then-fold shape | its JavaScript DOM snapshot, browser session or current-page region authority |
| Region4Web / FocusAgent | use as design and later A/B references because no compatible pinned implementation is currently available | claiming code reuse, trained-selector parity, or making an LLM selector part of baseline correctness |

W1b-World uses the single production acquisition and projection chain. It does not create a second renderer or an
offline oracle view for the model. T3.2 evolves the existing projection/delivery seam without changing acquisition or
World authority:

```text
BrowserGym raw observation
  -> BrowserGymSurfaceAdapter
  -> full WorldObservation
  -> lossless public ActorWorldSnapshot
  + current ActionSpace
  -> WorldDeliveryIndex -> WorldDeliveryLens
  -> WorldDeliveryView(PageMap + ActiveView/SearchResults) + DeliveryManifest
  -> compact stable PerTurnToolCatalog
  -> complete request admission
  -> diagnostics
```

For each page it persists these paired diagnostics:

| Diagnostic | Required interpretation |
|---|---|
| raw source, World, Actor structure/entity/fact counts and coverage | distinguish upstream absence, World loss, and any violation of lossless supported World-to-Actor normalization |
| PageMap/ActiveView/Manifest quality | every region satisfies the frozen descriptor grammar/thresholds; every Manifest ref is printed exactly once with role/label/context/state; folded descriptors contain no E/N/F refs |
| verb and action-decision-state coverage | current verbs and supported value/selected/checked/active/expanded/required/domain/grid state required for the action must survive |
| capability reachability census | for each registry operation and current option record `registry_defined`, `adapter_supported`, `currently_eligible`, `model_exposed` or `paged_searchable`, typed absence reason, selection, and dispatch |
| structural-closure violations | no retained control without label/ancestor context; no retained table cell without its row and headers; no dialog/form/card target detached from its container |
| collapsed presentation counts | empty wrappers, duplicate inline text, icon glyphs, redundant text, and low-value appearance metadata are measured rather than silently guessed absent |
| omission and recovery | partial source/projection/action coverage is explicit; every public fact/action is exact or indexed; `inspect_world`/`find_actions` results promote into the next exact SearchResults/Manifest; neither route changes World authority |
| perception route | record `TEXT_ONLY`, `STRUCTURE_FIRST`, or `SCREENSHOT_AX` and why an image/visual provider was or was not attached |
| request budget | PageMap, ActiveView/SearchResults, tool-schema, episode-memory, image and total tokens; full-vs-delivered comparison; repair amplification and recovery turns |
| authority isolation | no BID, selector, coordinate, credentials, expected answer, evaluator state, reward, or hidden task metadata enters WorldDeliveryView or provider input |

The W1b diagnostic keeps one public-only `DeliveryProbe` per six site categories. Probe v1 was frozen before the first
implementation run, and its failures remain evidence. Probe v2 was explicitly revised only after read-only diagnosis
showed that several v1 witnesses were unrelated to the public task (`Orders`, shopping `Search`, and GitLab
`Projects`) or allowed label/role evidence from different items. Probe v2 was then frozen before run2 and requires one
item to jointly satisfy public label, role, required operation, and next `DeliveryManifest` membership—not a hidden
answer or full action sequence. The semantic discoverability gate passes only when all 6/6 probes satisfy page identity,
required PageMap regions, exact one-step recovery, and the ordinary ActionSpace path, while no probe value is available
to production ranking or model context. The task-0 live witness tests whether the configured policy uses that route;
it cannot redefine the provider-free oracle after run2.

The hard correctness gate is invariant-based:

- 100% of current DeliveryManifest E refs have a canonical current ActionOption with the verb and state needed to
  choose that operation; stable Tool Schemas do not enumerate the full ref inventory;
- retained forms, dialogs, cards, and representative tables are structurally closed;
- an explicitly partial view says what is partial and exposes the owning current recovery route;
- `inspect_world` covers success, empty, invalid-region, invalid-cursor, stale-context, and capacity outcomes; only
  successful non-empty outcomes change the same-World lens, and all outcomes perform zero GUI dispatch;
- source semantics do not infer action capability from browser-default properties—for example, drag requires the
  adapter's explicit supported evidence rather than `element.draggable` alone;
- model-visible `semantic.dom.*` uses only the frozen `type|role|title|alt|placeholder|aria-label|aria-description`
  allowlist; DOM id/class/name/data/event/selector fields stay in source trace and never become fallback labels;
- every `ActionOption` in the complete current ActionSpace is present in the exact ActiveView/SearchResults or
  reachable through `find_actions`, and every exposed current reference resolves to exactly one current option before
  admission;
- every public target/fact is exact or recoverable from a visible PageMap entry; every non-empty search result appears
  as exact next-turn content rather than only as a ref-bearing history record;
- after a mutation on a dynamic page, every model-visible and interaction-eligible structure target appears in the
  stabilized current ActionSpace/tool catalog; targets that remain structure-visible but unbound carry typed
  `why_not_eligible` diagnostics in trace evidence;
- Auditor episode history fits the declared local budget without full transition evidence, every model-visible precise
  table/result text needed across stages has a current public scalar evidence ref, and audit provider/context failure
  is a typed terminal audit failure rather than evidence of incomplete GUI progress;
- a semantic registry entry is not reported as installed for BrowserGym unless the surface offer, primitive
  translator, private binding, executor route, fresh capture, and real conformance evidence all exist;
- projection changes neither private bindings nor the full World semantic digest and never reads task/benchmark
  identity; and
- trace and published metrics distinguish source omission, World projection loss, Actor-normalization violation, WorldDeliveryView folding, tool-capability
  absence, policy error, and provider failure.

The earlier 3k–8k observation / 16k complete-request targets were capacity-oriented and are superseded by the T3.2
request-class gates above. An atomic relevant region may remain truthfully admitted above a target, but T3.2 cost then
remains failed. The required correctness behavior is measured paging/retrieval or typed `context_capacity`, never
prefix slicing or loss of an offered target. Provider tokenization is used when available, with a conservative
estimator and existing byte cap as fallbacks.

The current BrowserGym support baseline is explicit rather than inferred from the ten-entry semantic vocabulary:

| Status | Operations | W1b treatment |
|---|---|---|
| installed now | `activate`, `type_text`, `select_option`, `drag_to`, `scroll`, `press_key` | preserve and run real click/fill/select/drag plus T1 scroll/key conformance |
| first missing tranche | none | complete as of T1; site smoke failures on these operations can now be attributed past capability installation |
| second missing tranche | `hover`, `focus` | install through the same owner chain and exercise on representative real controls |
| evidence-triggered only | `set_value` | add only when a declared page exposes a value control not honestly covered by existing operations |
| observation-owned by default | `read` | use current World/evidence; add at most one read-only recovery route only after a measured non-action retrieval gap |

For each newly installed operation, the focused and live gate must prove one continuous path:

```text
real BrowserGym observation
  -> truthful surface capability offer and private binding
  -> current ActionSpace option
  -> direct or find_actions-retrieved ToolSpec
  -> exact resolution/admission/binding
  -> one official BrowserGym primitive dispatch
  -> fresh World
  -> typed local outcome (unknown/not_applicable is valid for open semantics)
```

The completed foundation order was source-semantics correction, `scroll`/`press_key`, capability census, measured
`find_actions` filtering, complete-request token admission, the T3.1 recovery skeleton, the provider-free T3.2
PageMap/ActiveView/DeliveryManifest contract, and T3.3 automatic ActionCandidates/read-action separation with its
held-out properties and fresh-context review. W1b-Agent breadth evidence is active next. T3.4 guarded same-form
batching is evaluated only afterward. `hover`/`focus` remains evidence-triggered rather than blocking these delivery
gates.
No W1b failure authorizes one tool per element, a second registry/executor, raw Playwright, `search_tools`, or an LLM
tool-legality evaluator. Large external MCP/WoT/SaaS discovery remains outside G5.

Use deterministic cleanup and region partition inside the existing projection/delivery owner first. BrowserGym
remains the raw acquisition owner; AgentLab/BrowserGym token fitting, browser-use serializer ideas, Glass targeted
reads, Region4Web region overview/`view_all`, and FocusAgent soft line retrieval are reference signals only. Do not
import another browser/session/tree/selector/agent loop. Do not add a model-backed region selector before the
deterministic PageMap/search gate and W1b-Agent expose a held-out retrieval failure. If that happens, the selector is a
predeclared A/B behind the same projection port, selects existing public region IDs, reports coverage, and fails open
to deterministic directory/`view_all` delivery.

Only shared environment/composition, T3.2 semantic delivery, or already-declared W1a contract defects may be repaired
before W1b-Agent. Do not add a
site/task branch, change the frozen ActionPolicy prompt/model, enable model GoalCompiler, or introduce model history
summary/RAG from smoke behavior. W1b-Agent begins only after the PageMap/discoverability gate passes on all six site
categories. Its model
smokes then establish that at least one legal BrowserGym dispatch, ref-safe navigation history, STOP, native result,
cleanup, and reporting work through the same projection; they do not redefine the World invariants.

#### W2: frozen proof cohort

The planning snapshot pins BrowserGym commit `9e779f087de9a65668b6974d11f9ce9816026e96`, WebArena-Verified commit
`6473f72db5dcefc97b5725b59e734504edc28a21`, and official hard-subset checksum
`d20872f9894e4e8ffc250155fe0ad5c797c640f40d3094404654a8b1dab14e68`. Implementation must either use these exact
sources or revise the manifest and rerun selection before any model sees a task; it may not silently reuse the IDs
against another dataset revision.

Select the proof cohort only from that official 258-task WebArena-Verified Hard subset. The frozen algorithm filters
to two-site tasks with one official task type, sorts by task ID, creates `Random(20260818)`, and processes strata in
`retrieve, navigate, mutate` order. Within each shuffled stratum it first selects distinct intent-template IDs, then
fills any remaining slots without replacement. It does not inspect expected values or execute a model. The resulting
12 tasks are:

| Type | Task ID | Template ID | Revision | Sites |
|---|---:|---:|---:|---|
| retrieve | 267 | 85 | 4 | wikipedia, map |
| retrieve | 97 | 120 | 2 | map, wikipedia |
| retrieve | 265 | 85 | 4 | wikipedia, map |
| retrieve | 268 | 85 | 4 | wikipedia, map |
| navigate | 740 | 94 | 2 | wikipedia, map |
| navigate | 759 | 42 | 2 | map, shopping_admin |
| navigate | 424 | 371 | 2 | wikipedia, map |
| navigate | 426 | 371 | 2 | wikipedia, map |
| mutate | 681 | 116 | 2 | reddit, gitlab |
| mutate | 672 | 101 | 2 | shopping, reddit |
| mutate | 556 | 87 | 3 | gitlab, wikipedia |
| mutate | 554 | 84 | 2 | gitlab, reddit |

The cohort therefore has these strata:

```text
4 retrieve
4 navigate
4 mutate
```

Require distinct task IDs and, where the dataset permits, distinct intent-template IDs within each stratum. Select
without looking at expected answers or running GLM-5.2 on candidate tasks. Persist task ID, intent-template ID,
revision, sites, public intent digest, subset checksum, and selection seed. Official expected values and evaluator
details stay private. Run order is deterministic and mutate cases receive an official clean reset so one case cannot
prepare or corrupt another.

The baseline is one arm only:

```text
ActionPolicy: GLM-5.2
Execution mode: manager-guided for W1b/W2; standalone remains available outside this proof campaign
ManagerReview: frozen configured model/role prompt; initial plan once, then one call per meaningful episode outcome/stall/failure
Auditor/SemanticVerifier: disabled for W1b; optional in W2 only under a predeclared strict high-risk/durable-claim policy
GoalCompiler: disabled in long-horizon mode
Context: grounded-agent-context.v13
GoalPlan: deterministic one-item projection of current SubtaskContract
Observation: structured BrowserGym source; no newly added visual fallback
Episode history: compact renderings of earlier AgentTurnViews within 16 KiB + latest four detailed views; fold, then typed yield
Working set: at most 16 Runtime-resolved WorkingFacts backed by canonical EvidenceRecords / 4 KiB
MissionState: accepted evidence-backed working outcomes/carry facts + evidence lineage/version only
SupervisorState: phase + active contract + last exit/failure/audit ref + role/case budgets
Episode action limit: frozen during W1; multiple episodes share one BrowserGym case without reset
Mission round limit: frozen during W1
Prompt/model/settings: frozen for all 12 cases
```

Each role call records `trigger_kind`, request mode, semantic subtask ID, input/output tokens, latency, and outcome.
Acceptance requires W1b task 0 Manager/Auditor/Finalizer counts `2/0/0`, one FinalResponseBoundary admission, and at
most one STOP/send. It rejects a ManagerReview call caused only by
an action, page change, local read/search, or context rollover; rejects an Auditor call caused by budget, stall,
ordinary outcome proposal, exact fact, or finalization; rejects any finalizer provider call or finalizing ToolCatalog;
and rejects a response whose cited evidence is not current/admitted. W2 does not require a fixed Manager count—it
requires every call to have one admitted episode event trigger.

Infrastructure-only timeout may be calibrated during W1, then must be frozen before cohort selection. No prompt,
model, budget, pacing, tool, or context change is allowed within the proof cohort. A changed variant is a new arm with
a new manifest and cannot overwrite the baseline.

#### Evidence and acceptance

Persist one private case-evidence record before aggregation. It may contain full model exchanges under the existing
local evidence policy and is never the published report described at the top of this document. The published aggregate
contains only bounded metrics, classifications, identities, and redacted summaries. Each private case record includes:

- official task identity/revision/sites/type and official score;
- exact terminal status and WebArena-Verified evaluator status, with private expected values omitted;
- goal compiler disposition, attempts, item count, and plan text delivered to policy;
- every `ModelInvocationResult`, provider request/response attempt, selected tool, action target semantics, dispatch,
  fresh transition, and control repair;
- every ManagerDecision, SubtaskContract, episode boundary/yield reason, WorkingStateProposal, accepted/rejected MissionState
  update, selected carry-fact key, and role-specific model identity/cost;
- every pin request and Runtime-resolved public value/evidence lineage, with sensitive values redacted in aggregate
  reports but preserved under the case evidence policy;
- steps, pages/tabs/sites visited, repeated actions, stale/invalid calls, request-evidence/action-page calls, final
  response attempt plus the existing `DispatchStatus` and case final-delivery latch, post-STOP
  acquisition/native-evaluation outcome,
  prompt/completion tokens, provider latency/retries, and wall time;
- ActionPolicy Context size, retained `AgentTurnView` count, compact/detailed view counts, deterministic fold events,
  working-set size,
  mission rounds, and confirmation that no previous-episode trajectory or cross-case memory entered a request; and
- for each ActionPolicy turn, World/Actor coverage, offered-target conservation, decision-state coverage,
  structural-closure violations, projection/retrieval mode, perception profile, complete request-token composition,
  and repair-token amplification; and
- failure origin separated into environment/setup, provider/schema, observation, grounding/action capability,
  policy reasoning/loop, terminal-response format, and official verification.

The bounded project claim is **WebArena-Verified Hard cross-site capability**, not SOTA parity or full-benchmark
coverage. It passes when:

- environment readiness and all six site smokes pass before the cohort;
- the W1b-World gate passes across all six site categories, with every offered target/state conserved, retained
  structures closed, partial coverage truthful and recoverable, source semantics explicitly supported, and no
  private/evaluator data leak;
- at least 6/12 cases receive official score `1.0`, with at least one success in each retrieve/navigate/mutate stratum;
- every reported success comes from the integrated official evaluator after one valid STOP;
- no `sent`/`sent_unknown` terminal delivery is retried automatically, and missing post-STOP evidence never counts as
  success;
- every episode boundary has one typed ManagerReview transition; any proposed MissionState update is lineage-valid,
  no executor self-report directly mutates MissionState, and an episode with no accepted proposal may leave
  MissionState unchanged without invoking SemanticAuditor;
- no stale reference is dispatched, no expected answer/evaluator state enters Context, and no production branch is
  keyed by task ID, template, site, instruction text, label, selector, or expected action;
- every case persists raw evidence and cleanup status even when the agent/provider fails; and
- implementation, tests, both maintained documents, frozen manifest, and report identity agree under an independent
  fresh-context audit.

Report mean official score, exact-success count, stratum/site-pair results, median successful steps, token/latency
cost, and failure categories. Partial evaluator scores remain diagnostics and do not count as exact successes.

#### Failure-driven capability policy

Do not change architecture after one failed task. Aggregate shared mechanisms across the frozen cohort:

| Repeated evidence | Correct owner/action | Prohibited reaction |
|---|---|---|
| relevant fact is absent from BrowserGym source or full World | fix/reuse BrowserGym acquisition or SurfaceAdapter/Fusion semantics, or run a declared structured/adaptive observation A/B | Actor-View prompt hint, site selector, task rule, or always-on VLM |
| fact exists in full World but is absent from the supported lossless Actor algebra | fix the existing World-to-Actor normalization owner and conservation property across real pages | mutate World, add a second DOM tree/selector owner, or hide the gap in delivery |
| lossless Actor normalization contains the fact but WorldDeliveryView drops/orphans it or request tokens remain noisy/repair-amplified | fix DeliveryIndex partition/closure, fold/search recovery, and duplicate presentation; evaluate any learned selector only as a frozen A/B after the deterministic gate | silently prefix-truncate, use `recovery=none`, remove offered targets/facts, or call a per-step selector model by default |
| adapter exposes the wrong verb because a browser-default property was mistaken for authored semantics | fix source-local capability classification and conformance across element kinds/sites | blame Context/model intelligence, add a label exception, or bypass Binder with raw Playwright |
| offered control lacks a reusable interaction | add one generic semantic capability only if BrowserGym exposes a stable primitive and multiple tasks require it | raw Playwright escape or WebArena-only tool |
| fresh World and complete episode context are correct but policy loops | EpisodeMonitor emits one typed recovery turn to the existing ActionPolicy; a failed recovery yields a failed-strategy report and Manager chooses a different bounded route; compare a stronger policy only in a declared arm | direct generic VLM fallback, case prompt, mutable GoalPlan status, Recovery Agent, or another GUI loop |
| an exact value is needed after navigation but was never pinned | improve general `pin_fact` tool description/admission and classify policy failure; do not reconstruct it from trace | task keyword extraction, hidden state, or arbitrary model memory |
| compact `AgentTurnView` history exceeds the byte budget in held-out episodes after deterministic folding | run a predeclared model-summary/offload A/B with full trace retained | silently drop oldest steps or make free-form summary authority |
| Manager repeatedly creates unsuitable subtasks despite correct MissionState | compare Manager prompt/model or narrower SubtaskContract in a new arm | per-step Manager, site skills, or moving planning into CoreLoop |
| optional SemanticAuditor accepts unsupported claims or misses a semantic commit | fix the bounded semantic-verifier evidence/prompt or EvidenceBoundary lineage contract across cases | invoke it after every subtask, expose native-evaluator oracle data, or permit direct state writes |
| a historical carry fact is insufficiently current for a later decision/finalization | Manager assigns an explicit refresh subtask or optional verifier returns missing evidence; record policy/verification failure if omitted | pretend Runtime can detect implicit fact use or treat historical evidence as current World truth |
| final response is malformed | repair the provider/tool representation or official response-schema projection | local evaluator or hard-coded answer formatter |
| official score disagrees with visible behavior | preserve the official result and classify evaluator/environment evidence; upstream the issue where appropriate | project-owned alternate success authority |

Any model summary, cross-task experience, RAG, generic memory/offload, every-step reflection, or adaptive-vision
variant must preserve the same inner GUI chain and win a frozen paired cohort on official score or cost. Until then,
it remains off by default.

#### Explicit non-goals

G5 does not implement or import an AgentLab/WebArena baseline agent, generic mutable todo/workflow engine, per-step
Manager/Auditor/GoalCompiler/reflection/summarizer, cross-task experience, RAG/vector recall, TencentDB control state,
custom HAR/network recorder, copied task dataset, custom site containers, site-specific selectors, benchmark skills,
private API shortcuts, second Binder/GUI Runtime, or alternate success evaluator. The former taxi scenario may later
be shown as a portfolio demonstration, but it is not a parallel capability gate and cannot replace WebArena-Verified
evidence.

### Memory and larger benchmarks

W2 includes only the memory required by its declared long-horizon contract: the existing deterministic
`AgentTurnView` history with compact/detailed rendering, Runtime-resolved `WorkingFact` wrappers over canonical
`EvidenceRecord`s, and evidence-admitted cross-episode MissionState. This is not optional
after-the-fact complexity; without it the former eight-turn baseline loses causal history and cross-stage values before
the benchmark it claims to test.

W2 does not include free-form model history summaries, embeddings, vector stores, cross-task recall, SOP learning, or
generic memory frameworks. TencentDB Agent Memory may be evaluated afterward only through a fail-open
`HistoryOffloadPort` for very long real-task logs/operator retrieval. It cannot write MissionState, alter a trajectory,
or recall between benchmark cases. A model summary enters only after byte metrics show deterministic compact history
overflowing, and only as a paired arm whose raw trace remains complete.

WebArena-Verified is the active web long-horizon gate. WorkArena/WorkArena++ are not a second active route. They may be
considered later as another BrowserGym dataset only if WebArena evidence identifies an enterprise-workflow gap that
cannot be measured by the current cohort. OSWorld enters only after the Runtime can honestly observe and act across
desktop windows, files, clipboard, and native applications. As of 2026-08-16, OSWorld V2 recommends release
`v2026.08.08`; the exact release, VM image, setup checks, model, and action budget must be pinned in every report. Do
not mix original OSWorld, OSWorld-Verified, and V2 scores.

## Local MiniWoB runtime

For interactive one-case experiments, start the local flight recorder with the pinned BrowserGym interpreter after
loading `.env`:

```bash
export PYTHONPATH=src:tests
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m affordance_runtime.benchmarks.console.server
```

The console selects only frozen manifest cases and delegates to the same `external_breadth.cli run-case` composition.
ActionPolicy and GoalCompiler model choices become role-specific environment configuration for that subprocess; the
GoalCompiler can also be explicitly disabled for an ablation. The UI incrementally reads owner-emitted trace events
and final report evidence. Subprocess state is display-only and never becomes task progress, completion authority, or
a parallel agent loop. The default loopback binding and single-active-run rule keep this an experiment console rather
than a remotely exposed orchestration service.

Use the pinned project configuration and interpreter:

```bash
set -a
source .env
set +a
export MINIWOB_URL=http://127.0.0.1:18888/miniwob/
export PYTHONPATH=src:tests
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest <focused-tests>
```

Before a live run, verify `http://127.0.0.1:18888/miniwob/click-button.html`. Reuse the existing project server when
it returns 200. Raw run output belongs under an artifact directory, not in maintained documentation.

The historical 120-second selection manifest remains at
`docs/benchmarks/miniwob-60-seed7-v1-manifest.json`. The current 180-second watchdog contract is frozen separately as
`docs/benchmarks/miniwob-60-seed7-v2-manifest.json`; v1 evidence must never be relabeled as v2. The v2 validator
reserves explicit pacing, per-turn execution, reset, and finalization time instead of treating the pacing schedule as
the only watchdog consumer.

## Local deterministic fixtures

`environments/mock_web/` contains reset-by-reload browser tasks. `environments/smart_room/` exposes the same devices
through DOM and WoT; start it with `docker compose -f environments/smart_room/docker-compose.yml up --build`.
Its dashboard, WoT servient, failure control, and directory use ports 3000, 8080, 8081, and 8082 by default. Override
them with the `SMART_ROOM_*_PORT` variables defined by the compose file when parallel fixtures need distinct ports.
These black-box fixtures never define Runtime recovery, authorization, or completion policy.

## Current executable gate

The public Runtime, CLI, and target benchmark harness now exclusively run `CoreAgentLoop`; there is no second
legacy-engine path. Every serialized run identity records `runtime=core`. This establishes runtime provenance but
makes no new live MiniWoB performance claim until the paired cohorts below have run. The outer mission layer described
for G5 is now an executable W1a product path for local contracts: thin mission roles, accepted MissionState, bounded
episodes, `yield_subtask`, official BrowserGym finalization, and native terminal mapping are implemented and verified
locally. The direct ManagerReview -> FinalResponseBoundary replacement for run10 is implemented and provider-free
verified. Run5 separately reopens the mode-specific Manager output/reasoning contract and bounded teardown. The real-page T0
W1b-World gate is passed, T1 BrowserGym `scroll`/`press_key` installation is verified
through real conformance plus the T1 W1b-World rerun, and T3 complete-request admission/repeated-failure breaker is
verified locally with the T3 W1b-World budget rerun. That rerun also invalidated the `action_focused recovery=none`
branch as semantic-safe compression evidence. T3.1 subsequently passed a six-page provider-free round-trip gate, and
T3.2 now passes the stricter semantic/cost gate for the single
`World + ActionSpace -> DeliveryIndex -> PageMap/ActiveView/SearchResults -> DeliveryManifest -> stable tools` chain.
The repaired T3.2 fresh-context audit passed with no P0/P1/P2. A later authorized task-0 GLM-4.6 attempt reached policy but
made no GUI dispatch: the old polymorphic `inspect_world(action, region_ref?, query?, cursor?)` contract invited the
model to put natural-language search text into an opaque cursor. The run was stopped on request and is retained as a
schema-clarity failure, not a task failure. The pre-T3.3 replacement contract used `read_region(region_ref)`,
`search_world(query)`, `list_regions()`, and `search_actions(query)`; T3.3 supersedes the first, second, and fourth
public names with `open_region`, `find_content`, and `find_actions`. Runtime-private continuation state is exposed only
by dynamically offering zero-argument `read_next_page()` or `action_results_next_page()`. Semantic action schemas no
longer expose advisory `expected_outcome`, and `wait(reason)` uses a Runtime-owned five-second bound. CoreLoop, Binder,
Executor, ActionSpace authority, and browser dispatch semantics are unchanged.
T3.3 now passes its six-page provider-free candidate/read-action gate and independent bounded audit; W1b-Agent is the
active next gate, live verification is pending, and the work remains non-closed.

The 2026-08-21 task-7 follow-up withdrew the autocomplete hypothesis. A provider-free official BrowserGym witness
recorded `fill From -> fill To -> From change/blur -> first geocode request`, then `click Go -> To change/blur ->
second geocode request`. Both browser requests targeted `localhost:8080` and failed with `net::ERR_FAILED` before any
response; a bounded wait, second formal Go activation, and fresh capture produced no OSRM request and no non-scale
distance content. Map-service access logs contained neither browser request. A concurrent replay of each exact,
query-redacted URL returned 404 without CORS on emitted port 8080, while the identical request returned 200 with CORS
on healthy IPv4/IPv6 port 3000. Container configuration supplies `localhost:8080` as the browser-visible Nominatim and
OSRM endpoint even though Docker publishes container port 8080 as host port 3000. This deployment endpoint mismatch,
not service unavailability, prevents geocoding and route creation. The run therefore cannot test valid-route
World/Delivery recovery; it proves `provider_attempts=0`, formal BrowserGym execution, and that autocomplete was not
the missing lifecycle step.

The W0 environment correction regenerated the stale Brotli browser assets as well as gzip, retained the Map
container's server-internal port 8080, and exposed Nominatim/OSRM to Chromium through relative URLs on page origin
port 3000. A fresh provider-free rerun recorded four browser XHRs (two geocodes and two bounded route requests), four
HTTP 200 responses, no request failures or console errors, Chromium entries in the Nominatim/OSRM access logs, and
fresh BrowserGym source text `Distance: 33km. Time: 0:32.`. Query values and route coordinates are stored only as
redacted values plus stable URL hashes. This is W0/environment evidence, not a Runtime modification or a live-model
witness. The Map image was subsequently rebuilt as `706822fbfb5a`, the container was recreated with the existing data
volumes, and `provider-free-browser-network-witness-after-w0-rebuild.json` reproduced four HTTP 200 responses and the
same 33 km public result, enabling the subsequent bounded Runtime World/Delivery check.

That bounded check now passes. `provider-free-runtime-world-delivery-witness.json` dispatched four actions through the
formal Runtime ActionSpace/Admission/Binder/Executor chain. The Go post-action `WorldObservation` contained both a
public route-result target and `StaticText "Distance: 33km. Time: 0:32."`; no follow-up capture was required. The same
observation ID entered the production text-only `ModelTurnDelivery`, where the 33 km result remained model-visible.
The witness made zero provider attempts and used no raw Playwright/JavaScript execution path. This falsifies an
independent RegionIndex/Delivery-loss root cause for task 7; W1b-Agent live verification remains pending and the work
is non-closed.

The confirmed Runtime defect is separately repaired at `EpisodeMonitor`: screenshot/focus-only `CHANGED` with an
unknown or not-applicable postcondition is operational no-progress. Monitor uses only existing `ActionOutcome` facts:
`satisfied`, or `changed + structural`, is progress; it does not re-project World semantics. Focused properties cover continue on the first
attempt, recover on the second, yield with the same typed `RecoverySignal` after recovery, reset on satisfied
postcondition/navigation/new structural result, semantic-target separation, deterministic bounded ref-free evidence,
and unchanged `ManagerRecoveryView` passthrough. T3.3 ActionCandidate/find-actions remains a regression gate. No Task
21 or live-model witness was run. Current status is `W1b-Agent blocked / non-closed`.

The task-7 run-validity audit classifies
`evidence/live/w1b-task-7-deepseek-v4-flash-run1/` and
`evidence/live/w1b-task-7-deepseek-v4-flash-run3/` as externally interrupted, invalid runs: each has a trace ending on
an ordinary event but no formal case, run, or summary report. Only
`evidence/live/w1b-task-7-deepseek-v4-flash-run2/` completed the reporting boundary, so its typed `blocked` outcome is
the sole valid task-7 Agent result. Host PTY reclamation after a silent interval is the high-confidence causal
explanation from the available host/process timeline; because neither interrupted process reached a signal/reporting
boundary, it is not a directly recorded Runtime fact.

The benchmark harness now emits a flushed 30-second CLI heartbeat, handles `SIGHUP`/`SIGTERM`/`SIGINT`, and produces a
failed partial case with `interrupted_external` distinct from `case_timeout`. Each completed or interrupted case is
atomically persisted immediately; the suite report is still written at return and fails acceptance when planned cases
are missing. Focused target-loop and breadth regression verification passes 133 tests, and Ruff passes for every
changed source/test file. This change improves run validity and evidence durability only; it does not alter or improve
the task-7 Agent outcome, and W1b-Agent remains blocked/non-closed.

Run4 at `evidence/live/w1b-task-7-deepseek-v4-flash-run4/` falsifies the preceding heartbeat mitigation. Despite
30-second flushed heartbeats, the host ended the PTY at approximately 420 seconds. The trace file spans about 395
seconds from creation to its final write, consistent with the independently observed approximately 419-second total
wall time after including startup. Run4 has only `traces/webarena-verified-w1b-task-7/trace.jsonl`; it has no case,
run, or summary report and is therefore another invalid, externally terminated run. The supported operational claim
is now an absolute PTY lifetime cap, not silent-session reclamation.

The run's product evidence is still a valid non-terminal counterexample. After 15 ActionPolicy turns, fresh trace
observations contain `Distance: 33km. Time: 0:32.`, CMU, and Pittsburgh International Airport with postcode `15231`.
The policy does not promote that result and instead continues local reads until the episode budget yields. The second
Manager call (`subtask_budget_exhausted`) then records two historical attempts—`manager_initial` and the now-retired
`manager_schema_repair`—and
both have the typed violation `output_truncated`; the call ends `schema_error: role output invalid`. Thus “OSRM result
never reached World” is falsified. The live gaps are ActionPolicy use of already-visible evidence and repeated
ManagerReview structured-output truncation. W1b remains blocked/non-closed.

Long runs must now use the target-loop CLI's `--detach` mode. It creates a new POSIX session, writes stdout/stderr to
`benchmark.log`, and stores `run.pid` plus `launch.json`; `--status` monitors the PID identity and formal evidence
without holding a PTY open. A detached deterministic smoke verified `PPID=1`, `SID=PID`, live trace visibility, atomic
case persistence, and final `run.json`/`summary.json`. The heartbeat and signal path remain diagnostic/containment for
short foreground runs, not long-run liveness proof. No new task-7 live run was started.
The first post-migration provider-free attempt at
`evidence/w1b-world-t32-readable-tool-schema-run4/` passed all functional recovery checks but failed the existing 2k
Tool Schema cost gate on five pages. The correction retained each intent/scope/authority statement and removed only
duplicated prose, rather than merging tools or re-exposing cursor fields. Run5 at
`evidence/w1b-world-t32-readable-tool-schema-run5/` passed all six pages with no acceptance errors. Tool-schema token
estimates were `1,819 / 1,732 / 1,885 / 1,666 / 1,885 / 1,733`; complete new-page estimates were
`8,541 / 5,519 / 7,719 / 5,240 / 6,674 / 5,062` (median `6,096.5`). The diagnostic made zero provider attempts and
its recoverability checks preserved the BrowserGym zero-dispatch snapshot.
The already implemented action-reference/repair/discovery/visual-binding/control-stall and token-accounting contracts
remain regression requirements. T2 hover/focus remains deferred pending benchmark evidence. W1b-Agent site smokes and
W2 frozen cohort evidence still precede any long-horizon capability claim.

The stopped GLM-4.6 task-0 diagnostic then exposed an outer recovery information-loss defect. EpisodeMonitor correctly
detected the unchanged-World repeated empty `search_world("2022")` loop, emitted one ActionPolicy recovery hint, and
yielded `control_stall`. Auditor also produced useful report/date-filter guidance, but Supervisor collapsed it to the
string `evidence_gap`; Manager therefore saw neither attempted modes nor the prohibited repeat and emitted the same
SubtaskContract again. This is not a clean GLM-4.6 versus GLM-5.x comparison because the renderer, tools, history, and
provider profiles differed.

The local convergence repair keeps the existing roles and state owners. Monitor now carries its bounded typed signal
through the final yield. Supervisor routes `control_stall|grounding_stall|capability_gap` directly to Manager, projects
one non-authoritative recovery view, and preserves Auditor `missing_evidence/recovery_hint` only when an actual audit
returns repeated `unknown`. An unchanged subtask gets one Manager revision request; a second unchanged strategy blocks
as `strategy_not_changed` before another episode. Focused owner/property tests pass, including zero Auditor calls for
control stall, empty-result/query evidence delivery, one-revision convergence, audit-guidance preservation, and
total outcome mapping. No Manager/ActionPolicy prompt, provider profile, or model was changed. No provider or live benchmark was called for this repair; live policy behavior remains
non-closed pending an explicitly authorized rerun.

The current executable gate is:

```bash
pytest -q
ruff check src tests
git diff --check
```

The first paired live run must use the frozen JSON manifest above, write raw per-case JSON under an artifact directory,
then aggregate only after all case records exist. The paired tolerance and A/B observation profiles must be recorded
alongside that run rather than embedded in product code.

Prompt or context changes are admitted only as predeclared cohort variants. A prompt must remain stable within a run;
benchmark case names, expected actions, labels, selectors, or answers may never be injected into it. Diagnose failures
by shared categories such as observation insufficiency, grounding, invalid tool use, action effect, progress, or
completion—not by adding per-case prompt instructions.

## 2026-08-21 task-7 evidence-handoff provider-free component gate

The follow-up does not run task 7 or a real model. It implements the provider-free component path that the run4 trace exposed:
an exact current public scalar search match now carries one `N` node ref and one real `F` ref resolving to the same
`WorldEvidenceIndex` record, exact Runtime-owned value, region/source context, current observation lineage, source
coverage, and evidence method. `pin_fact` accepts only an offered manifest `F` ref and a bounded key/purpose, performs
zero BrowserGym dispatches, and stores the record value itself. It is an evidence-backed episode bookmark, not a
mutable progress/todo mechanism or completion authority.

The focused evidence properties cover:

- exact current DOM and visual scalar search results use the same unified World evidence and pin path;
- the returned `N` text/value and `F` record have the same source result and lineage;
- the model cannot submit or override a pinned value;
- `search A -> pin A -> search B` retains WorkingFact A even though the old public `F` handle is not callable in the
  fresh view;
- stale, private, missing, and non-scalar evidence fail with typed rejection;
- same key/same evidence is idempotent, conflicting evidence is typed, and `pin_fact` causes no BrowserGym dispatch;
- ManagerReview can cite a pinned episode fact through a fresh review-local public ref and propose promotion without
  supplying its value; the mechanical `EvidenceBoundary` preserves the original observation/fact lineage in
  MissionState.

The ordinary episode frequency remains `Manager calls = 2`, `SemanticAuditor calls = 0`, and `Finalizer model calls = 0` for
the normal one-episode W1b path. ManagerReview performs ordinary semantic assessment and routing. The production code
class is `EvidenceBoundary`, the mechanical evidence admission boundary; the historical `AuditBoundary` symbol and
export were deleted without a compatibility alias. Independent SemanticAuditor
is disabled by default and may run at most once only under a predeclared strict-verification policy; ordinary
retrieval, pinning, stall, budget exhaustion, outcome proposal, and finalization do not select it.

The Manager prompt retains its identity, routes, authority, and schema while defining one subtask as one dominant,
independently reviewable outcome. It allows several tightly coupled GUI actions but excludes combining candidate
discovery, every per-candidate verification, aggregation, and finalization. A missing prerequisite yields one most
important prerequisite; 4–8 ActionPolicy turns is preferred; `done_when` must identify a fresh observable state or
evidence packet. Generic held-out prompt-contract checks preserve these examples:

- Too small: "Type the first form field."
- Appropriate: "Submit the related form fields and obtain one observable result panel containing the requested record."
- Appropriate: "Verify one candidate against the stated constraint and capture one evidence packet containing the candidate identity and measured value."
- Too large: "Discover every candidate, verify all candidates, compare them, produce the final answer, and submit it."

No production keyword granularity validator, new phase machine, task/site specialization, or larger episode budget was
added. The ActionPolicy prompt adds only the instruction to pin an offered exact evidence ref before replacing the
view when later use is expected.

Run4 proves `output_truncated` for both recovery Manager attempts, with stored input estimates of about 4,783 tokens
for initial and 426 for repair. It does not contain truthful provider finish reason, configured attempt output limit,
reasoning presence, token usage, or transcript metadata, so it cannot support a reasoning-setting or output-cap
change. The role keeps the existing explicit 2,048-token cap and provider route. Future initial/repair attempts now
snapshot actual provider metadata and transcript into `ModelGenerationAttempt`; focused tests prove a compact valid
decision succeeds, a truncated initial plus compact repair records both attempts, repair changes representation only,
and provider/schema failures remain typed. Adapter-private observation fields remain trace inputs, not authority.

The honest task-7 root cause at this point was: the 33 km value reached World/Delivery but had no pin-capable evidence
handoff; the Manager contract admitted an episode spanning discovery through finalization; and recovery Manager
initial/repair both truncated. The component `find_content -> F-ref -> pin_fact` path and prompt-level granularity
guidance are provider-free tested, but this is not proof that the expected outputs reach ActionPolicy or that a real
episode makes the pin path reachable. Run6 below later falsifies that composed-closure interpretation. Task 7 and W1b
remain non-closed.

## 2026-08-21 task-7 run5 Manager/cleanup counterexample

The isolated causal evidence requested after run4 arrived as the first call of the subsequent official run rather
than as a browser-free probe. Run5 at `evidence/live/w1b-task-7-deepseek-v4-flash-run5/` failed before ActionPolicy:

| Attempt | Result | Provider evidence |
|---|---|---|
| `manager_initial` | `output_truncated` | `finish_reason=length`; configured and consumed completion budget `2048/2048`; reasoning present; final content absent |
| historical `manager_schema_repair` (superseded by run9 PydanticAI output retry) | provider/schema accepted, phase-contract invalid | `finish_reason=stop`; 778 completion tokens; final content present; returned `assessment=unknown` for `initial_plan` |

This closes the run4 causal uncertainty: reasoning exhausted the Manager's shared output budget. It also falsifies a
single universal model-visible `ManagerDecisionModel`. Requiring the model to return the mechanically predetermined
`assessment=not_applicable` created a redundant failure surface, and the generic repair schema did not retain the
initial/review phase distinction. Supervisor correctly returned `manager_failure`; policy calls and GUI executions
were both zero.

The implemented provider-free role gate now enforces:

- `initial_plan` uses `InitialManagerDecisionModel`, which contains no `assessment`, evidence/state proposal,
  invalidation, or final-response fields;
- Runtime lowers a valid initial response to internal `assessment=not_applicable`;
- `review_and_route` uses `ReviewManagerDecisionModel`, where assessment is
  `satisfied|unsatisfied|unknown|blocked` and `not_applicable` is impossible;
- initial and repair calls use the same mode-selected schema and cannot change phase;
- only Manager requests disable thinking on providers that explicitly support the control; the 2,048-token output
  allowance remains bounded, and ActionPolicy/SemanticAuditor settings are unchanged;
- valid initial, truncated-initial-to-valid-repair, invalid cross-mode output, provider without thinking control,
  and typed provider/schema failure are covered without a real provider.

The code symbol migration is part of the same clarity gate. The mechanical state writer is named
`EvidenceBoundary`; the historical `AuditBoundary` export/alias and current report vocabulary are removed. This does not add an
Auditor. Ordinary W1b remains `Manager initial -> Executor -> ManagerReview -> optional EvidenceBoundary write ->
finalization/next route`, with expected Manager/SemanticAuditor/Finalizer model frequency `2/0/0`. A SemanticAuditor
is exceptional and at most once under a predeclared strict-verification policy.

Run5 then entered teardown. The mission watchdog had already ended, but cleanup had no runner-owned deadline. The
formal files eventually appeared and record `mission_outcome=manager_failure`, `cleanup_failures=1`, and the
compatibility `case_failure_code=cleanup_exception`. This is incorrect causal precedence: cleanup did not cause the
Manager failure and must not replace it. Run5 therefore narrows and reopens the earlier run9 cleanup claim: preserving
an uncertain-dispatch primary code was insufficient to prove bounded cleanup and primary-failure precedence for all
terminal mission outcomes.

The implemented teardown gate is provider-free and adversarial:

1. a fake synchronous close that never returns cannot block the event loop or prevent durable case output;
2. a separate bounded cleanup deadline produces typed `cleanup_timeout` and elapsed time;
3. a cleanup exception is secondary while the earlier Manager/provider/task failure remains primary;
4. successful cleanup preserves existing reports and counts;
5. cleanup begins only after the primary mission result/snapshot is captured;
6. heartbeat/status identifies `cleanup` and `reporting` rather than implying continued Agent execution;
7. no cleanup timeout retries GUI actions, STOP, Manager, ActionPolicy, or provider calls.

Do not run another task-7 live witness to validate these changes. Required evidence is focused role/teardown tests,
the full local suite, Ruff, `git diff --check`, and an independent fresh-context audit. Only after those pass may one
new predeclared W1b witness run. Current status is `run5 Manager-mode and bounded-cleanup convergence implemented /
provider-free verification passed / fresh-context audit passed / superseded by run6 composed-contract reopening /
non-closed`.

## 2026-08-21 task-7 run6 composed-contract counterexample and frozen repair gate

> Historical/superseded implementation note (2026-08-21): the run6 references below to
> `candidate_output_keys`, incomplete subtask projection, and thinking-enabled truncation retry describe the frozen
> pre-Phase-13.1 baseline. Phase 13.1 removed those production contracts without aliases; its provider-free result is
> recorded after the frozen acceptance table.

Run6 at `evidence/live/w1b-task-7-deepseek-v4-flash-run6/` was manually stopped and has no valid official terminal
outcome. It remains valid local causal evidence. The trace records three Manager calls and 19 ActionPolicy semantic
calls. ActionPolicy made 24 physical provider attempts; five initial attempts exhausted the configured 4,096-token
output allowance without a final command, while the corresponding thinking-disabled recovery calls returned legal
commands in 13--148 completion tokens. Manager calls were comparatively bounded (186, 305, and 298 completion
tokens). The fresh World and an `open_region(R2)` result contained `Distance: 33km`, airport identity/address text,
and postcode `15231`, but the policy called `find_actions("airport")`/`find_actions("search")`, never pinned a fact,
and exhausted the episode. MissionState remained empty. ManagerReview then received a `Not Found` title/route summary
without the useful route evidence and regressed to the home/search strategy.

This evidence supersedes three earlier interpretations:

- `4096` is not a provider or context-window requirement; it is the current application output cap shared by
  reasoning and final content. The failure does not justify raising it or globally disabling all model reasoning.
- T3.3 ActionCandidates/`find_actions` is implemented and its empty result is correct for readable airport text. The
  remaining defect is typed cross-domain recovery and evidence delivery, not action-search recall.
- `pin_fact` and exact `find_content` F-ref production exist, but ActionPolicy cannot see the Manager's
  `candidate_output_keys`; `SubtaskContract` lowering passes only `objective/done_when`. Component availability is
  therefore not end-to-end reachability.

The frozen implementation arm is **Phase 13.1: role-budget and subtask-evidence delivery convergence**. It contains no
live witness and no benchmark-specific route rule.

### Frozen product changes

1. Replace `candidate_output_keys` with a closed subtask outcome contract:

   ```text
   outcome_kind = state_change | evidence_packet
   required_evidence = [{key, description}, ...]
   ```

   Remove the old field without a compatibility alias. Project objective, done-when, constraints, outcome kind, and
   a required-evidence checklist under the existing Task section consumed by ActionPolicy.
2. Keep the public names `open_region`, `find_content`, and `find_actions`. Do not perform a second rename after the
   T3.3 cutover. Add machine-readable result-domain metadata and preserve the base action page on an empty action
   search; an empty executable-control search points to `find_content` for readable evidence.
3. Add bounded `EvidenceCandidates` alongside automatic Top-5 ActionCandidates. Candidates must be existing current
   public scalar EvidenceRecords with F refs, source/region context, coverage, and lineage. Reuse the existing bounded
   lexical/structural delivery ranker over requirement descriptions and changed-result regions; do not add an LLM
   selector or evidence authority. Exact scalar records read through `open_region` retain their F refs; arbitrary
   labels are not promoted and every omitted public fact remains recoverable through `find_content`.
4. Admit `yield_subtask(outcome_proposed)` mechanically for both outcome kinds. Required evidence is a
   `missing|currently_visible|retained` inspection hint, not a permission gate. Supervisor fresh-captures the review
   World and attaches the existing EvidenceBundle; Manager may cite multiple current F refs for one composite outcome.
5. Project admitted WorkingFacts and newly changed relevant result evidence into ManagerReview before document title
   or generic navigation summaries. Preserve route/title conflicts explicitly.
6. Replace the universal thinking assumption with mechanically triggered role profiles: ordinary ActionPolicy is
   fast/low-thinking; one typed ambiguity/stall may purchase one bounded deliberate call; representation repair is
   thinking-disabled; Manager is low-frequency and may use bounded deliberate reasoning only when the provider keeps
   reasoning separate from its structured-output allowance. Record requested/effective mode and reasoning/final
   token usage.

### Provider-free acceptance

The arm cannot proceed to live evidence until all properties pass:

| Gate | Required witness |
|---|---|
| complete execution-relevant subtask delivery | ActionPolicy sees objective, done-when, constraints, outcome kind, every required evidence description/status, and selected WorkingFacts; Runtime-only budget, carry selector, and audit lineage remain private and owner-consumed; old `candidate_output_keys` is absent |
| state-change outcome | fresh observable state permits yield with zero pins |
| evidence outcome | a natural-language proposal yields without pins; fresh current evidence reaches ManagerReview; one composite WorkingOutcome may cite multiple F refs; pinning remains optional and zero-dispatch |
| evidence reachability | exact fresh result is present in EvidenceCandidates or recoverable through `find_content`, carries one current F ref, pins without model-supplied value, survives lens replacement, and appears in ManagerReview |
| search-domain recovery | empty `find_actions` preserves base actions and returns `searched_domain=executable_controls` plus content-search guidance; it never returns readable content as an action |
| review identity | current route/primary visible result and pinned evidence cannot be overwritten by a conflicting stale document title |
| reasoning routing | normal, deliberate, and repair configurations have distinct typed triggers; at most one deliberate escalation occurs per recovery event; no schema repair changes semantic choice |
| authority/removal | no second World, ActionSpace, Binder, evaluator, memory store, tool alias, or task/site keyword branch; obsolete field and identical thinking-enabled truncation retry are removed |

Required validation order is focused owner/property tests, full `pytest -q`, Ruff, `git diff --check`, and an
independent fresh-context architecture audit. Only then may one predeclared task-7 W1b witness run. The live report
must split prompt/final/reasoning tokens per role and record ActionCandidates, EvidenceCandidates, content/action
search outcomes, optional pins, required-evidence hints, outcome proposals, ManagerReview evidence, and mission-state promotions.

### Phase 13.1 provider-free result

The implementation now projects the complete model-relevant state/evidence execution view under the existing Task section, keeps
the five-field GoalPlan unchanged, and delivers bounded current public EvidenceCandidates in parallel with executable
ActionCandidates. Mechanical yield admission accepts bounded natural-language outcome proposals regardless of pin
state; Supervisor attaches fresh review evidence and both outcome kinds follow the existing ManagerReview and
EvidenceBoundary path. Empty
action-domain search preserves the base ActionPage and returns typed content-search recovery. MissionReview gives
WorkingFacts and changed relevant result evidence precedence over route/heading and a conflicting document title.

Reasoning routing is bounded and typed: ordinary ActionPolicy is thinking-disabled at 1,024 output tokens; one first
grounding/evidence/operational/control stall per recovery event can use a 2,048-token deliberate call; representation
repair is thinking-disabled at 512 tokens and cannot change the parsed semantic operation/target. Manager is invoked
only at start or a meaningful episode boundary and uses thinking disabled with a 2,048-token shared allowance because
the current provider interface shares reasoning and structured final output. SemanticAuditor remains exceptional and
has zero calls on the ordinary provider-free path.

The provider-free gate passed: `206 passed` focused owner/property tests; full suite `1405 passed, 19 skipped`; Ruff
passed; and `git diff --check` passed. These tests include zero extra BrowserGym dispatch, zero ordinary Auditor calls,
both outcome kinds, complete execution-relevant subtask delivery, evidence reachability and retention, typed wrong-domain recovery,
review identity conflict, disjoint reasoning triggers/budgets, once-per-event deliberate admission, and
semantic-preserving representation repair. Fixtures are generic synthetic data. No real provider, WebArena/task-7
live witness, or W2 cohort was run.

The first bounded fresh-context audit returned `FAIL`, but its first finding used the wrong acceptance boundary.
`relevant_fact_keys`, `episode_turn_budget`, and `related_audit_ids` are intentionally private to carry selection,
Supervisor admission, and Auditor scope; the ActionPolicy view is complete for model execution without them. The
second finding was valid: compact-provider failure attempts lost the selected call profile. The owner correction now
projects the actual thinking/output configuration into both the failure attempt and transcript. Provider-free
re-verification and a new independent audit remain required; no live run was started.

The new bounded fresh-context re-audit passed the code, owner, authority, reasoning, and focused provider-free checks,
but returned `FAIL` because two maintained overview phrases still used the rejected complete-internal-contract
wording. Both overview phrases are now corrected. No new product or architecture gap was found; the independent audit
has not been rerun and no live execution occurred.

Current status: `Phase 13.1 owner correction implemented / focused provider-free verification passed /
documentation audit findings corrected / fresh-context re-audit not rerun / W1b-Agent blocked / non-closed`.

### Run7 mandatory-pin contraction

Run7 demonstrated successful World acquisition, EvidenceCandidates delivery, and ActionPolicy semantic extraction,
then failed because a composite required-evidence key could not be represented by one scalar WorkingFact and yield was
rejected before ManagerReview. The active repair deletes that permission gate rather than adding multi-pin tools or a
packet builder. `outcome_proposed(reason=...)` is a non-authoritative natural-language proposal; Supervisor attaches a
fresh World and current EvidenceBundle; Manager aligns the proposal with offered F refs and may form one composite
WorkingOutcome from multiple records; EvidenceBoundary remains the only MissionState writer. `pin_fact` is optional
retention for impending view replacement or later reuse.

The secondary run7 failure was representational: Manager's cited semantic result was valid but its non-authoritative
reason exceeded 500 characters and schema repair repeated it. The provider envelope now accepts a bounded 4,000-char
reason and Runtime mechanically trims only that field to 500 during lowering. No assessment, route, evidence, outcome,
subtask, or final-response semantics are altered.

Provider-free verification passed: `119 passed` focused owner/contract tests, full suite `1408 passed, 19 skipped`,
Ruff, and `git diff --check`. Removal scans found no mandatory yield gate, old missing-evidence rejection, packet
builder, multi-pin tool, second evaluator, or product specialization.

The bounded fresh-context audit passed all owner and authority checks and independently reran `104 passed` focused
tests plus the full `1408 passed, 19 skipped` suite; Ruff and `git diff --check` passed. It found no second loop/store,
evaluator, packet builder, multi-pin tool, or product specialization. No live execution occurred.

Current status: `run7 mandatory-pin overconstraint removed / natural-language proposal handoff implemented /
Manager reason narrowing implemented / provider-free verification passed / fresh-context audit passed /
W1b-Agent blocked / non-closed`.

### Run7 terminal checkpoint repair gate

The observed run completed final-answer dispatch, post-STOP acquisition, and one native evaluator call, then stopped
before the former in-memory primary snapshot and cleanup phases. This is classified as a harness finalization and
durability defect. It does not reopen World, ActionPolicy, Manager, Auditor, or browser-close behavior.

The bounded repair commits the official outcome immediately when the post-STOP native evaluator returns through a
thin SQLite `RunResultStore` using `synchronous=FULL`. The checkpoint contains typed evaluation status, canonical
outcome kind/code when present, public evidence refs, and task/observation lineage. SQLite owns transaction commit,
atomicity, and crash recovery; no project-owned file fsync/rename protocol remains. Trace must contain the same
formal outcome fields. Only after commit may the runner enter cleanup and full reporting. Case evidence exposes
`cleanup_status=failed` independently; cleanup failure cannot overwrite the committed official outcome.

If checkpoint commit fails, the runner must not project the in-memory candidate as a durable official result or
emit `primary_persisted`. It reports typed `harness_persistence /
official_checkpoint_persistence_failed`, performs bounded best-effort cleanup, and
reports failure; this is the explicit exceptional path to the normal checkpoint-before-cleanup order.

After cleanup, the complete case-report payload is committed to SQLite before JSON export. Export failure updates
the separate report lifecycle status but leaves the official outcome and report payload queryable and regenerable;
the suite payload is also committed before run/summary export. JSON is never the primary result store. No DBOS,
Temporal, Prefect, workflow-resume layer, or automatic GUI-effect retry is introduced by this gate.

`report_payload_commit_failed` and `json_export_failed` are separate outcomes. Only the latter claims that a stored
payload can be re-exported. A committed official checkpoint also takes precedence over any conflicting in-memory
terminal candidate during case projection.

The 900-second case watchdog retains its existing task deadline, while cancellation completion now has an independent
two-second grace deadline. Exceeding that grace is traced and the runner proceeds to checkpoint-backed reporting
instead of awaiting cancellation indefinitely. Heartbeats must expose `finalizing`, `primary_persisted`, `cleanup`,
and `reporting` after `running`.

Provider-free acceptance requires: checkpoint-before-cleanup ordering; exact evaluation status/outcome/evidence in
checkpoint and trace; SQLite commit failure mapped to typed `HARNESS_PERSISTENCE`; report recovery from a checkpoint
after watchdog timeout; bounded cancellation grace; cleanup failure recorded only as lifecycle-secondary evidence;
JSON-export failure leaving a regenerable stored report; and unchanged policy/provider/GUI/evaluator call counts. No
task-7 live witness or W2 cohort is authorized by this repair.

The final gate passed: 11 terminal lifecycle/fault-injection tests; full suite `1415 passed, 19 skipped`; Ruff; and
`git diff --check`. The bounded fresh-context re-audit passed 96 focused tests plus both static gates and found zero
blockers. No provider, BrowserGym/WebArena/task-7 live witness, or W2 cohort ran. Current status:
`terminal SQLite result-store implementation complete / provider-free verification passed / fresh-context audit
passed / W1b-Agent blocked / non-closed`.

### Run7 two-chain observability repair gate

The terminal-result gate is narrowed to three owners: SQLite owns official-result durability, JSONL owns complete
local diagnostics, and Langfuse owns remote visualization only. Formal benchmark execution uses:

```text
native evaluator return
  -> deterministic OfficialOutcomeCheckpoint ID
  -> SQLite commit
  -> bounded primary_result_available event
  -> cleanup status commit
  -> case/run payload commit
  -> rebuildable JSON export
```

There is no evaluator recovery in `finally`; standalone completion reaches the checkpoint recorder from its actual
terminal evaluator call. The deleted `benchmark_primary_snapshot` is not replaced by another bulk event. Persistence
failure is typed `HARNESS_PERSISTENCE`; cleanup and JSON export remain secondary lifecycle facts and cannot overwrite
a committed official outcome. JSON export uses a temporary replace only to prevent partial reads, not as durability.

The historical run7 observability gate required `RunTraceRecorder` to have no exporter authority and used PydanticAI
OpenTelemetry instrumentation plus a synchronous Langfuse sink. That SDK path and synchronous sink are superseded by
the run11 authority repair below. The maintained design uses already-recorded typed ModelInvocationResult attempts and
project-owned events behind a bounded daemon-worker queue. One case maps to one trace and the suite run ID maps to one session. Public model
prompt/response content may be captured, while binary content is disabled. Project event projections recursively
reject private binding/selectors/implementation-private IDs and bulk World/screenshot/trajectory data. Root task
input and child events share the same 16 KiB total bound. Langfuse v4 session correlation must use the official
`propagate_attributes` context so the root and all native/custom children carry the suite session ID.
Viewer failures must leave local JSONL and benchmark control unchanged.

Provider-free acceptance is: focused checkpoint/lifecycle/fault-injection tests; bounded remote-projection privacy;
JSONL-before-viewer ordering; an installed official SDK no-network API witness; full pytest; Ruff; diff-check; and one
fresh-context audit. A live case may run only after those gates pass and Langfuse credentials are actually configured;
SDK installation alone is not evidence of remote ingestion.

Provider-free acceptance passed: 20 focused observability/conformance tests; full suite `1424 passed, 16 skipped`;
Ruff; `git diff --check`; dependency checks; and one no-network official SDK/OTel witness with one native PydanticAI
generation and one case root sharing a trace. The fresh-context re-audit passed 33 gates with zero blockers. After
credentials were configured, provider-free trace `4bf823812fac0727d4ed4085dcbf980c` was sent and fetched via the v2
observations API: five observations form one rooted hierarchy and share session
`provider-free-suite-final-277a52a2d00a` plus environment `development`; the native generation records model
`provider-free` and input/output/total usage
`56/3/59`; secret/private/binary probes are absent. The live case remains unrun. Current status: `two-chain
implementation complete / provider-free verification passed / fresh-context audit passed / remote trace audit passed
/ live case not run / W1b-Agent blocked / non-closed`.

### Run9 shared role/lifecycle/trace repair gate

The run9 Manager output was not a semantic failure. The old role adapter requested free-text JSON through
`ModelPort.generate_structured`, reduced malformed output to generic `json_invalid`, and issued a hand-written repair.
At the same time, the benchmark trace root depended on later CoreLoop `run_started`. A Manager failure before CoreLoop
could therefore be locally recorded but absent from Langfuse, while the runner lacked durable owner-boundary phases
proving when the case body returned.

The repair gate uses one shared seam:

```text
benchmark_case_started -> case trace root
Manager/Auditor -> one strict PydanticAI ToolOutput -> ModelInvocationResult
Supervisor terminal result -> preliminary SQLite case payload
bounded cleanup -> final payload/export -> benchmark_case_finished -> bounded viewer flush
```

Provider-free acceptance requires:

- valid Manager and Auditor output tools pass in one physical request;
- invalid tool arguments receive exactly one PydanticAI validation retry, while two invalid responses produce typed
  `schema_error` with both attempts retained;
- Manager initial failure returns within a bounded test deadline with one Manager call, zero Auditor calls, and no
  CoreLoop episode;
- SQLite records each applicable closed phase and commits `RESULT_PERSISTED` before `CLEANUP_STARTED`;
- non-returning cleanup is bounded at ten seconds and cannot overwrite the task outcome;
- report payload commit and JSON export have distinct failure codes; report and viewer flush have five-second bounds;
- a case root exists before Manager, closes without CoreLoop, and treats `run_started` as an episode child;
- Langfuse unavailability leaves SQLite, JSONL, and benchmark truth unchanged;
- removal scans find no Manager/Auditor free-text JSON normal path, manual role repair prompt, or role-side reads of
  `last_call`/`last_transcript`.

This gate changes no Runtime, World, Binder, native TaskEvaluator, GUI dispatch, mission EvidenceBoundary, or ordinary
Auditor policy. It authorizes only provider-free/fault tests and one bounded fresh-context audit. No provider,
BrowserGym/WebArena live witness, task-7 witness, or W2 cohort may run before those gates pass.

Provider-free verification passed: 83 focused role/lifecycle/fault/observability tests, the full `1428 passed,
19 skipped` suite, Ruff, and `git diff --check`. Remote provider-free trace
`beca6780f8588e0ff9ea2ebd3595b04e` used only `FunctionModel` and contains the benchmark root, Manager agent, two
native generation spans for initial/output-retry, Manager boundary, and case finish. A bounded fresh-context audit
passed 85 gates with zero blockers, including held-out 503 recovery, local JSONL failure, and oversized root-input
cases. No real model provider, BrowserGym/WebArena live witness, task-7 witness, or W2 cohort ran.

Current status: `run9 convergence implementation complete / provider-free verification passed / fresh-context audit
passed / live not run / W1b-Agent blocked / non-closed`.

### Run10 partial working outcome and bounded replan gate

The run10 Manager output is not intrinsically contradictory when the previous subtask is `unsatisfied` while one
named partial WorkingOutcome is `satisfied`. The former evaluates the whole subtask; the latter records one supported
local conclusion. The old `working_assessment_conflict` rejection was an EvidenceBoundary ownership defect and is
deleted. The state proposal field is now only `working_outcomes`; `completed_outcomes` has no production or contract
alias.

The gate freezes the non-competing paths:

```text
evidence-backed partial result
  -> ManagerReview WorkingOutcomeProposal
  -> mechanical EvidenceBoundary
  -> MissionState version + 1

clearly misaligned advisory subtask
  -> ActionPolicy needs_replan (zero GUI dispatch)
  -> typed subtask_misaligned recovery
  -> one Manager replan opportunity
  -> changed subtask, or second unchanged strategy -> STRATEGY_NOT_CHANGED
```

Every Manager subtask now carries bounded `task_link` explaining one unresolved user requirement that it advances.
Manager is prompted to prefer the shortest directly observable GUI outcome and to justify any intermediate.
ActionPolicy still sees authoritative TaskGoal, the model-relevant subtask view, and fresh World together; it may
request replanning but cannot mutate MissionState or declare completion. Supervisor compares only objective,
done_when, task_link, outcome kind, and required-evidence descriptors. No keyword classifier judges whether a plan is
good, and Auditor remains limited to exceptional evidence support.

Provider-free acceptance requires: both opposite overall/local assessment combinations admit when evidence is legal;
invalid, stale/private, empty, duplicate, conflicting, or wrong-version evidence still rejects; task_link reaches the
existing Task section while budget/audit/carry selectors remain private; needs_replan dispatches no BrowserGym action,
writes no MissionState, and calls no Auditor; the first unchanged Manager response receives one distinct bounded
replan invocation and the second unchanged response blocks; recoverable no-op proposal feedback reaches the next
ManagerReview without a write; removal scans find no old field/equality branch or product specialization. Full pytest,
Ruff, diff-check, and a bounded fresh-context audit must pass before live. No provider, BrowserGym/WebArena live case,
task-specific witness, or W2 cohort is authorized by this gate.

Provider-free verification passed: 151 focused owner/property tests before the final held-out addition, 121 focused
tests for the final changed surface, the full `1435 passed, 19 skipped` suite, Ruff, and `git diff --check`. A bounded
fresh-context audit passed 10 held-out owner invariants and all removal scans after correcting an initial shell-only
`PYTHONPATH` import error. No real provider, BrowserGym/WebArena live witness, task-specific witness, or W2 cohort ran.

Current status: `run10 implementation complete / provider-free verification passed / fresh-context audit passed /
live not run / W1b-Agent blocked / non-closed`.

### Run11 observability authority repair gate — live-reopened

Run11 has two independent outcomes: the task already terminated with a Manager `provider_unavailable` attempt, while
the harness subsequently blocked because synchronous Langfuse projection occupied the Supervisor/runner call stack.
Waiting longer cannot change the task result. The live run is stopped and does not count as closure evidence.

The historical provider-free gate attempted one-way ownership:

```text
typed Runtime event -> local JSONL -> bounded put_nowait queue -> daemon viewer worker -> Langfuse
official task result -> SQLite checkpoint/report payload -> rebuildable JSON
```

Only local JSONL and SQLite are synchronous evidence authorities. The queue capacity is 256. Full queue, unreachable
client, record error, or worker failure opens a per-case circuit and drops subsequent remote events without changing
case latency or result. Terminal flush means signal plus bounded daemon join; only the worker may call the SDK flush.
A timeout produces a local `viewer_flush_timeout` event and process/report completion continues.

`Agent.instrument_all()` and the second PydanticAI-to-OTel path are deleted. Existing typed generation attempts are
projected in the worker as one Langfuse generation each; Manager retry and ActionPolicy attempts retain model, token,
latency, trigger, validation, and finish data without duplicate generations.

Provider-free acceptance requires:

- a forever-blocking record call cannot delay `CASE_BODY_RETURNED`, case report, or process return;
- queue-full enqueue remains bounded and increments only viewer-drop metrics;
- a forever-blocking flush returns control within the configured five-second outer deadline and preserves task status;
- an unreachable viewer leaves `provider_unavailable` as the task failure evidence;
- a healthy worker produces one case root, Manager and ActionPolicy generations, Runtime step, and terminal outcome,
  with no duplicate PydanticAI generation;
- removal scans find no synchronous `_emit -> sink.record`, main-thread client flush, `Agent.instrument_all`, or second
  remote model path.

Historical provider-free verification passed: 46 focused observability/lifecycle fault gates, full `1440 passed, 19 skipped`,
Ruff, and `git diff --check`. A fresh-context authority audit passed 12/12. Remote provider-free trace
`144820f19bfc3d2e1d4d4aa90ff41601` in session `provider-free-run11-a88dea840cc9` was fetched through the official
observations API and contains exactly one root, one Manager generation, one ActionPolicy generation, one Runtime tool
step, native evaluation, and terminal event, with no duplicate PydanticAI generations. No real provider,
BrowserGym/WebArena live witness, task-specific witness, or W2 cohort ran.

Later live evidence showed that a daemon thread containing the SDK does not prove parent process exit when SDK-owned
exporter resources remain live. Current status: `run11 thread-isolation skeleton present / provider-free verification
passed historically / live process-exit isolation failed / observability convergence reopened / W1b-Agent blocked /
non-closed`.

### Run12 lifecycle, grounded-entry, and route-recovery convergence gate

Run12 is the frozen live regression witness for one shared governance gap, not a map-specific test oracle. The trace
shows that Manager received only generic application capabilities, generated an oversized coordinate/candidate
subtask, ActionPolicy entered a plausible but weakly grounded search route, interleaved local/rejected steps evicted
the original page from the four-turn oscillation window, and a natural-language prohibited-repeat message could not
match the CoreLoop's JSON action representation. A later side-effect-free Manager call failed at transport, while
viewer/cleanup lifecycle behavior still prevented a clean, trustworthy process boundary.

This gate supersedes earlier present-tense acceptance claims for daemon-thread viewer isolation, generic-only Manager
environment projection, recent-step world oscillation, free-text repeat comparison, and exact-text global strategy
identity. Their old evidence remains useful for regression history but cannot satisfy the new exit gate.

The implementation order is frozen. A later step may not use a live case to compensate for a failed earlier gate.

| Phase | Owner and change | Provider-free exit gate | Explicit non-goal |
|---|---|---|---|
| R12-0 | Observability: replace in-process/thread-confined Langfuse SDK with a disposable viewer process behind bounded non-blocking IPC | black-holed record/flush and SDK-created non-daemon-thread fixtures cannot delay owner return, report persistence, or process exit; queue full/broken child only increments viewer metrics | no second trace authority, remote acceptance input, or synchronous fallback |
| R12-1 | Runner/environment lifecycle: classify cleanup `TargetClosedError` as typed `already_closed` success only during close/shutdown | repeated close is idempotent; runtime-time TargetClosed remains a failure; primary mission/checkpoint/report status is unchanged | no retry of GUI action, STOP, evaluator, or provider during cleanup |
| R12-2 | Mission role invocation: one retry for retryable Manager transport failure before an accepted typed output | timeout/connection reset/provider retryable/429/5xx gets exactly two physical attempts and one logical Manager call; both attempts are traced; schema repair remains separate | no retry for semantic disagreement, boundary rejection, accepted poor plan, or ActionPolicy expansion |
| R12-3 | Resolver/Admission and CoreLoop: one shared typed AttemptSignature plus typed operation mismatch feedback | producer and consumer compare the same typed value; exact rejected repeat is blocked; changed operation/target is admitted; old string comparison is absent | no natural-language legality parser or Monitor-owned action authority |
| R12-4 | EpisodeMonitor/World projection: bounded route trail plus page/result/progress/fact digests for every StepResult | interleaved local tools and rejected calls cannot hide A→B→A; visible unpinned result suppresses false regression; first no-progress cycle RECOVER, repeated cycle YIELD | no model-history reconstruction, site route rule, or task-progress interpreter |
| R12-5 | Mission environment projection: bounded ref-free interaction scopes from existing World/ActionSpace/RegionIndex | form/search/navigation scopes preserve role/label/operation, carry coverage, contain no refs/selectors/action IDs, and do not alter ActionSpace | no second DOM parser, screenshot Manager, or duplicated action catalog |
| R12-6 | Supervisor: same-World SubtaskAdmissionBoundary and recovery-kind-specific failed-scope policy | missing/stale scope and invalid budget fail typed before ActionPolicy; delivery-not-observable requires a different next scope; successful same-scope candidate work remains legal | no semantic feasibility scorer, keyword blacklist, or universal paraphrase detector |
| R12-7 | ActionPolicy/Supervisor: typed needs_replan reason and `8` default / `15` hard episode cap | failed scope is derived from active admitted subtask; zero GUI dispatch/MissionState write on replan; recovery never expands cap | no longer episode, second planner, or per-turn Manager |

#### R12-0 observability acceptance

The final observable path is:

```text
typed event -> local JSONL -> bounded IPC put_nowait -> viewer process -> Langfuse SDK/network
```

Acceptance requires all SDK imports, client construction, exporter threads, record, and flush to occur in the child.
Parent shutdown sends one sentinel, waits a bounded interval, and terminates the child if necessary. The test must use
an SDK-shaped fixture that starts a non-daemon child thread and never returns, not merely a blocking `record()` method
inside an already-daemon parent thread. After the bound, the benchmark process exits and SQLite/JSON reports retain
the original task result. Removal scans must find no daemon-thread Langfuse client, parent SDK call, direct/synchronous
fallback, or acceptance consumer of viewer state.

#### R12-1 cleanup acceptance

The cleanup outcome vocabulary is `not_run|succeeded|already_closed|timeout|failed`. Required tests cover synchronous
and asynchronous `close`/`shutdown`, first close, repeated close, Playwright `TargetClosedError`, unrelated close
exception, timeout, and a TargetClosed raised during capture/execution. Only the close/shutdown case maps to
`already_closed`; it is reported separately but accepted as cleanup success. Preliminary/official result persistence
must precede cleanup and cleanup evidence cannot replace the primary case outcome.

#### R12-2 Manager transport acceptance

The Manager invocation's retry classifier must cover HTTP 429/5xx, provider-declared retryable failures, timeout, and
connection/reset exceptions without a response. It must reject retries for Pydantic schema/output errors and accepted
Manager decisions. One logical request may produce at most two transport attempts plus the separately bounded output
validation retry permitted by PydanticAI; phase/trigger fields must make those causes distinguishable. No Supervisor
transition, subtask admission, EvidenceBoundary write, or GUI dispatch may occur between transport attempts.

#### R12-3 typed attempt/rejection acceptance

Property tests generate operations, duplicate labels, semantic neighborhoods, destinations, parameter orderings, and
page changes. Canonicalization must be deterministic, ref-free, stable for the same public attempt, different for a
meaningfully different target/context/parameter set, and scoped to the current page digest. An operation mismatch
must return attempted operation, target role/label/context, supported operations, and `must_change`, while preserving
the existing Resolver/ActionSpace authority.

#### R12-4 route-trail acceptance

Required generic state-machine cases are:

```text
A -> B -> local-read -> C -> empty-search -> rejected-operation -> A
  => route regression still detected

A(Search="") and A(Search="CMU", focused=true)
  => same page identity

A -> B(new public result, not pinned) -> A
  => no false regression

A -> B(pin/retain useful fact) -> A
  => no false regression

A -> B -> A with no progress
  => RECOVER

same cycle after recovery
  => YIELD
```

The page digest excludes transient/ref identity while the separate public-result evidence digest observes fresh
result/status facts. Tests must include local tools and no-dispatch failures because those were absent from the old
model-history fingerprint path.

#### R12-5/R12-6 Manager scope and subtask admission acceptance

At least two unrelated real-web snapshots must expose distinct bounded interaction scopes without leaking E/N/F/R
refs or private bindings. For a synthetic page with `Search` and `Directions`, Manager receives both scopes; admission
accepts only a scope from the exact environment-view/World lineage used for that Manager request. A stale or omitted
scope fails before CoreLoop. The boundary must also prove its limit: a semantically poor objective attached to a real
scope is mechanically admitted, then can only be rejected through typed ActionPolicy/Manager semantic recovery. This
negative test prevents the admission boundary from silently becoming a second evaluator.

Recovery tests distinguish:

- `delivery_not_observable(scope=X)`: the immediately replacement subtask must use a different scope;
- operation mismatch/effect stall: the same scope remains available while the exact attempt is prohibited;
- successful candidate verification: the same scope can be reused for another candidate;
- evidence already visible: the explicit current-evidence scope is legal without a fabricated GUI entry.

#### R12-7 run12 and held-out gates

The provider-free run12 replay must satisfy:

```text
default episode target = 8 turns
hard episode cap = 15 turns
no automatic cap expansion
no second CMU search after detected home-page regression
Manager receives typed route/subtask recovery
replacement subtask uses a currently offered different entry scope
zero coordinate-specific production rule
```

This witness is necessary but insufficient. One held-out non-map A→B→A workflow must show that returning to a hub with
new evidence remains legal, and one same-scope multi-candidate workflow must show that repeated use of a successful
form scope is not treated as repeated failed strategy. Production-source scans must find no `CMU`, airport, OSRM,
Directions-label, map-route, task ID, or frozen output specialization.

After R12-0 through R12-7 pass focused/property/state-machine tests, run full pytest, Ruff, `git diff --check`, and one
fresh-context architecture audit. Only then may one predeclared live task-7 witness run. A successful task-7 case does
not close W1b; the remaining frozen site smokes and held-out cohort remain required.

Provider-free implementation verification passed on 2026-08-21. The focused gates include disposable viewer-process
hang/flush/queue faults; synchronous and asynchronous `TargetClosedError` cleanup; Manager HTTP/timeout/connection
retry with Auditor non-expansion; typed attempt producer/consumer equality; route regression across interleaved local
and rejected steps; transient page-state equivalence; retained-result suppression; ref-free Search/Directions scope
projection; paraphrased failed-scope rejection; legal same-scope candidate reuse; and a synthetic run12 replay that
switches `scope:search` to `scope:directions` with default budgets `[8, 8]` and no GUI dispatch. The final full suite
passed `1451 passed, 19 skipped`; Ruff, Python compilation, removal/specialization scans, and `git diff --check` also
passed. No real model provider, live BrowserGym/WebArena case, task-7 witness, or W2 cohort ran.

Current status: `run12 R12-0..R12-7 implementation complete / provider-free verification passed / independent
fresh-context audit pending / live prohibited / W1b-Agent blocked / non-closed`.

### Run13 chained regression gate

Run13 supersedes the R12 budget and observability details where they conflict. The actual first episode used four
ActionPolicy turns because Manager still owned `episode_turn_budget`; it did not exercise the intended ordinary
eight-turn budget. The accepted contract removes this output field from Manager entirely: Supervisor passes exactly
8 for every ordinary executor episode and retains 15 only as the non-expandable hard Runtime cap.

The new pre-live gates are:

| Gate | Mechanical acceptance |
|---|---|
| R13-IPC | Persist the full event locally, project in the parent, and enqueue at most 16 KiB with `put_nowait`; a 1 MiB Manager event, full queue, dead child, blocked child, or child network `CLOSE_WAIT` cannot block case-body return |
| R13-PROVIDER | One typed classification drives Manager retry and terminal failure; statusless `ModelAPIError`, timeout, and connection reset receive one retry; after the second failure the terminal result is non-retryable; schema repair and Auditor policy remain unchanged |
| R13-BUDGET | Manager schema rejects `episode_turn_budget`; ordinary episodes receive 8; 15 is a hard Runtime bound only; recovery cannot expand either value |
| R13-FORM | One `set_form_fields` call admits 2–4 distinct editable fields in one current explicit form/search scope, permits only type/select, binds all before dispatch, returns ordered typed receipts/partial failure, and performs one final capture; submit/navigation remain separate |
| R13-REPLAN | The provider-free Search-delivery witness reaches typed `delivery_not_observable`, derives `scope:search` from the active admitted subtask, and requires a currently available different scope before another policy episode |

The form tool is now measured mainline work, not deferred T3.4 speculation. It is a bounded composite command inside
the existing one-tool-call protocol. It does not permit several independent provider tool calls and does not batch
Go, Filter, Submit, navigation, downloads, or unrelated controls. The correct generic route family can therefore use
`activate(Directions) -> set_form_fields(From, To) -> activate(Go) -> read/yield`, while Manager remains responsible
only for choosing the grounded observable scope and milestone.

No new live Task-7 run is part of this implementation gate. Provider-free verification passed with 170 focused
convergence tests, full `1460 passed, 19 skipped`, Ruff, Python compilation, specialization/removal scans, and
`git diff --check`. An independent fresh-context audit must still complete before a live rerun. Current status:
`run13 implementation complete / provider-free verification passed / independent fresh-context audit pending /
live prohibited / W1b-Agent blocked / non-closed`.

### R13 independent-audit remediation gate

The first independent fresh-context audit failed the pre-live gate on five composition properties. The remediation
adds owner-to-consumer witnesses rather than benchmark-specific behavior:

| Property | Provider-free witness |
|---|---|
| Formal capability reachability | CoreLoop executes one sealed two-field command through CountingEnvironment and the formal WebArena facade; two physical dispatches produce one post capture without a second policy call |
| Failed-scope recovery | `route_regression` carries the active admitted scope; a paraphrased subtask with the same scope but a changed outcome shape is rejected before a second policy episode |
| Additive provider budget | invalid schema, then retryable transport failure during repair, then terminal invalid output uses exactly three physical calls; a fourth prepared response is untouched |
| Total viewer isolation | an alive child plus a queue raising `BrokenPipeError` produces a typed drop/disable and cannot escape after the authoritative local write |
| Compound exceptional semantics | dispatch cancellation and post-capture cancellation retain ordered receipts and typed cancellation state; `SENT_UNKNOWN` and physical execution counts include compound members |

Verification on 2026-08-22: full pytest `1469 passed, 19 skipped`; Ruff passed; Python compilation passed; production
specialization scan for the run13 witness terms returned empty; `git diff --check` passed. The repository-wide mypy
command remains a non-gate historical baseline with 295 errors across 45 files; the new command/recovery contracts
were checked separately and the newly introduced direct annotation/callability defects were removed.

No provider call, BrowserGym run, or live Task-7 rerun was performed. A second independent fresh-context audit is the
remaining pre-live condition. Current status: `run13 audit findings remediated / provider-free verification passed /
independent re-audit pending / live prohibited / W1b-Agent blocked / non-closed`.

#### Second independent audit: FAIL

The 2026-08-22 fresh-context re-audit passed the formal compound facade path, typed failed-scope rejection, legal
same-scope reuse, additive three-call provider bound, normal compound receipts, and production-specialization scans.
It independently falsified four remaining gates: `max_turns=16` is accepted despite the declared hard cap; invalid
`RUNNING + yield_reason` StepResult state is accepted because validation is unreachable; `SetFormFields` is absent
from the benchmark decision vocabulary and compound cancellation receipts do not reach terminal execution/unknown
metrics; and viewer close leaks `ValueError` for an already closed queue. Focused tests passed `118`, full pytest
passed `1469 passed, 19 skipped`, Ruff/compile/diff checks passed, but these counterexamples keep the gate failed.
No live provider or Task-7 run occurred. Current status: `independent re-audit failed / live prohibited /
W1b-Agent blocked / non-closed`.

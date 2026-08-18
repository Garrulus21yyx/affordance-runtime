# Benchmark

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
6. Can it preserve complete current-episode history, exact cross-page values, and audited cross-episode outcomes
   without exposing stale GUI refs, hidden evaluator state, or another completion authority?

## Required report

Every live run records, per case:

- task and seed from a predeclared manifest;
- terminal status and official environment success;
- action, observation, and model-call counts;
- source selections by modality;
- visual supplementation and recovery counts;
- for long-horizon runs: mission rounds, episode boundaries, compact-history/fold counts, pinned/promoted facts,
  audit outcomes, and role-specific model costs;
- tokens and elapsed time;
- typed environment, provider, Runtime, and task failures.

Published reports must not contain prompts, model responses, selectors, coordinates, credentials, hidden state,
oracle values, expected answers, or benchmark reward payloads exposed to the model.

Local per-case evidence additionally contains a private complete `traces/<case-id>/trace.jsonl` plus
content-addressed media artifacts. This operational trace is not copied into the public report: it records the exact
public model context and tool catalog, typed decision, provider diagnostics, execution, local outcome, and formal
task-evaluation facts, plus causal IDs needed to diagnose a failure. Each provider attempt contributes its complete
OpenInference-shaped local transcript, including repair-phase input and output; screenshot payloads remain
content-addressed. Trace-write failure
invalidates benchmark evidence but never changes Runtime behavior. Langfuse export is optional and projects these
same spans rather than replacing the local trace.

Every core-loop run must additionally record the prompt version, typed-context protocol version, tool-catalog schema version,
Runtime engine, and model-adapter choice as metadata. These values support reproducibility but cannot alter product
behavior. During cutover, `compact-json` and `pydantic-ai` are compared only where the same model supports both wire
contracts, with the same provider, prompt, context, catalog, cohort, seed, and step budget. A model change is reported
as a separate cohort and is not attributed to the adapter.

## Current evidence

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
The report correctly records 13,070.3 ms successful-call model latency; its schema-repair metric remains zero despite
the visible PydanticAI tool-call repair and is therefore a separate benchmark-metric projection defect.

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

G5 wraps repeated instances of this same GUI chain with the bounded Manager/Auditor/MissionState episode boundary
defined below. It does not extend Simple GoalPlan into cross-episode progress.

| Gate | Scope | Implementation output | Falsifiable exit evidence |
|---|---|---|---|
| G0. Reopened contract convergence | two maintained authority documents and owner map | one five-field plan contract; no symbolic progress path; explicit non-goals | docs, production types, tests, and trace projection agree; independent fresh-context review remains required |
| G1. Simple GoalPlan implementation | compiler, boundary, lifecycle, transcript trace | `id/objective/done_when/depends_on/final`; 1..8 items; unique acyclic IDs; at most one final; tolerant unknown fields | property/unit/integration tests pass; initial/schema/contract repair attempts survive independently; compiler failures remain advisory |
| G2. Advisory prompt/context convergence | compact GoalCompiler and ActionPolicy prompts in the existing five-kind context | no internal locate/inspect items; dependency is semantic order, not a visibility gate; semantic groups are byte-bounded atomically; typed World renders as compact AX text; older summaries plus four ref-free semantic turns; stable tools with searchable overflow | real snapshot is complete at 16.2% of typed bytes; provider history contains no old E-ref, old World, generic incomplete progress, or old screenshot; generalization remains non-closed pending the G4 cohort |
| G3. Local transition projection — local verification passed | binding-selected verification contract, typed parameters, fresh evidence, Recent Steps | dispatch stays in ActionResult; supported before/after transition and optional local postcondition are projected; TaskGoal criteria remain in TaskEvaluator | family is selected once; after-only evidence can prove a postcondition; target-scoped evidence rules hold; unresolved semantics stay unknown and non-blocking |
| G4. Short-loop live proof — witness passed / cohort deferred | the predeclared Like witness; frozen cohort retained as regression | official case evidence through the existing runner | witness reaches official success without old refs, reversal, unrelated controls, or case logic; no broad MiniWoB generalization claim until its cohort runs |
| G5. WebArena-Verified long horizon — episode foundation/context implemented, mission layer pending | episode history/working set; outer Manager/Auditor/AuditBoundary; official BrowserGym integration; site smokes; frozen 12-case cohort | `YIELDED` no-reset episode lifecycle, all-turn `AgentTurnView` history, 16 KiB compact/detailed rendering, private F bindings and evidence-backed `pin_fact` are implemented; thin Supervisor/Auditor/MissionState and official long-horizon composition remain next | ownership gates and fresh-context audit pass, then official evaluator success on at least 6/12 including each stratum; no benchmark-specific branch or cross-case memory |
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
serialized-byte budget and retains repeated sibling structures only as complete semantic groups. Current E-refs and
verbs are projected in Observation/affordances, while operation schemas remain stable. The normal short-task path has
one current catalog; a byte-bound overflow exposes `find_actions(query,target,relevance_role,cursor)`. Recent Steps
contains older action/result summaries followed by the latest four ref-free semantic target/action/local-transition
records. DOM/BrowserGym retains no historical screenshots; only the current screenshot may accompany the current
World. A visual-only typed need still acquires and fuses a
structural baseline, so visual evidence supplements rather than replaces public structural facts.

The provider expression is now `compact_ax.v1`, rendered only after the complete typed `ActorWorldSnapshot` is closed.
Runtime, binding, currentness, evaluation, and trace continue to use typed facts; ActionPolicy receives indented public
text with E-ref, role/name, useful state, hierarchy, relations, coverage, and current verbs. The renderer drops only
presentation scaffolding such as N-refs, state-evidence dictionaries, source-ref repetition, empty arrays, low-value
appearance fields, and redundant inline text. It imports no surface or benchmark implementation and cannot create a
second observation authority.

The live seed-7 Context snapshot for `browsergym/miniwob.social-media-all` retained 260/260 structural nodes, 177
targets, all 41 actions in one non-paged catalog, seven `@nibh` mentions, ten Like controls with explicit
`active=false`, and Submit. The typed observation was 71,723 UTF-8 bytes; the compact rendering was 11,611 bytes
(16.2%). Renderer properties and all repository gates pass: 1,175 tests passed with 15 skips, and Ruff passed.

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
| episode-level history | Qwen3-VL/Glass design signal, existing `project_step_result()` and `AgentTurnView` | close expired-ref sanitation in the existing projection, then retain those semantic records for the episode; the request renders older views compactly and the latest four in detail; deterministic folding occurs only on byte overflow |
| cross-stage planning and accepted state | LongHorizon-Harness MEA reference | adapt its Manager/Executor/Auditor role split, bounded rounds, route-pattern separation, repair policy, and human-gate patterns with attribution; do not import its generic Environment/orchestrator or textual task-state owners |
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
  -> outer Manager(accepted MissionState) -> one SubtaskContract
  -> deterministic one-item GoalPlan
  -> existing CoreAgentLoop episode
       -> fresh World + selected carry facts + episode working set
       -> compact renderings of earlier AgentTurnViews + latest four detailed turns + current tools
       -> single ActionPolicy
       -> existing SelectAction -> Binder -> BoundActionRequest -> Executor
       -> BrowserGym action -> fresh World -> ActionOutcomeProjector
  -> yield/budget/stall -> conditional read-only audit -> AuditBoundary -> MissionState
  -> repeat bounded episodes without resetting the BrowserGym case
  -> existing FinalResponse decision
  -> environment-owned send_msg_to_user/STOP
  -> BrowserGym-integrated WebArena-Verified evaluator
  -> existing TaskEvaluator/native outcome mapping
  -> existing RunStatus and benchmark report
```

The outer supervisor is not a second GUI execution/evaluation chain. It has no browser tools, Binder, SurfaceAdapter,
or alternate final evaluator. WebArena-Verified evaluates only after STOP. Therefore the environment-specific product
seam remains terminal delivery: when an
environment advertises finalization capability, the existing `FinalResponse` branch sends its content through that
environment, reacquires fresh World, and evaluates the returned native terminal result. This replaces neither
`SelectAction` nor `TaskEvaluator`, creates no second Binder, and adds no second GUI action/evaluation loop.
Environments without an explicit STOP capability retain the present final-response behavior.

Before STOP, the native WebArena state is running/incomplete and is not model-visible semantic progress. After STOP,
the integrated evaluator is the sole official authority. The public instruction and official final-response schema
may enter TaskGoal; expected answers, evaluator configuration, backend state, and private task metadata may not.

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

The 2026-08-18 implementation checkpoint for the no-reset/YIELDED lifecycle foundation plus items 2–3 passes
`1189 passed, 18 skipped`, repository-wide Ruff, and `git diff --check`. This is local contract evidence only:
`yield_subtask`, the outer mission roles, audit/state promotion, and WebArena smokes remain unimplemented.

4. **Thin mission roles — next implementation gate.** Manager reads original TaskGoal, accepted MissionState, last typed exit/audit/failure, and
   remaining budget; it emits one bounded SubtaskContract. Long-horizon mode deterministically projects that contract
   to one GoalPlan item and disables the optional model GoalCompiler. ActionPolicy continues to own rolling GUI
   progress and receives only selected carry facts, current-episode history, fresh World/screenshot, and current tools.
5. **Audit and accepted state.** Operational stall/oscillation rules may yield but never infer semantic completion.
   Existing typed criteria close what they can; otherwise a read-only Auditor proposes a cited AuditDelta from a
   bounded AuditBundle. AuditBoundary alone admits cited public `EvidenceRecord`s into versioned MissionState. One
   UNKNOWN may request one extra read-only capture; unsupported claims leave MissionState unchanged.
6. **One terminal authority.** Ordinary episodes cannot offer STOP/FinalResponse. Only an accepted global-final route
   may deliver once through BrowserGym's official `send_msg_to_user` capability. Reuse
   `DispatchStatus.NOT_SENT|SENT|SENT_UNKNOWN` plus one case latch, reacquire fresh state, and accept only the integrated
   WebArena-Verified result. Quarantine the offline `eval-tasks` helper from W1b/W2 composition.
7. **Isolation and bounded failures.** Every official reset starts with empty in-memory MissionState, working facts,
   and episode history; none crosses a case boundary and W2 performs no checkpoint resume. Manager/Auditor use the
   existing provider bridge, bounded repair/retry, and typed failure routing; exhaustion returns control or fails the
   case without an implicit state write or unbounded role loop.
8. **Reuse constraint.** Do not import or fork LongHorizon-Harness's generic Environment/orchestrator. Adapt only its
   MEA role prompts, bounded routes/rounds, repair/failure routing, and human-gate pattern with attribution. Do not add
   `CompactStep`, `HistoryProjector`, `CaseSession`, another provider, another GUI loop, or another evaluator.

Required focused evidence includes: a synthetic episode longer than eight actions with the first action still visible
through the existing `AgentTurnView` compact rendering; a navigation scenario that pins an exact value and uses it
later; a two-episode scenario proving old
trajectory exclusion and accepted fact promotion; an auditor rejection that leaves MissionState unchanged; a stale
or hidden evidence pin rejection; one oscillation-triggered yield and Manager recovery; and final native evaluation
remaining the only success authority. Also prove that premature FinalResponse is unavailable in an ordinary episode,
`YIELDED` never becomes a benchmark outcome, user wait resumes without replanning, cancellation does not audit, and
the same BrowserGym adapter survives episode boundaries without a reset. Cover bounded Manager/Auditor failure and
AuditBoundary rejection; a composition test must fail if the offline evaluator helper is wired into W1b/W2.

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

- reset returns the official instruction and a usable BrowserGym observation;
- compact World preserves the relevant AX/DOM structure without leaking private task/evaluator data;
- current action compilation and at least one official BrowserGym dispatch work;
- ref-free Recent Steps remain temporal-safe across navigation and tab changes;
- `FinalResponse` reaches BrowserGym STOP in the official schema; and
- native result, cleanup, trace, and report persist without a special runner.

Only shared environment/composition or already-declared W1a contract defects may be repaired during W1b. Do not add a
site/task branch, change the frozen ActionPolicy prompt/model, enable model GoalCompiler, or introduce model history
summary/RAG from smoke behavior.

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
Manager: frozen configured model/role prompt, episode boundaries only
Auditor: frozen configured model/role prompt, only after typed UNKNOWN
GoalCompiler: disabled in long-horizon mode
Context: grounded-agent-context.v13
GoalPlan: deterministic one-item projection of current SubtaskContract
Observation: structured BrowserGym source; no newly added visual fallback
Episode history: compact renderings of earlier AgentTurnViews within 16 KiB + latest four detailed views; fold, then typed yield
Working set: at most 16 Runtime-resolved WorkingFacts backed by canonical EvidenceRecords / 4 KiB
MissionState: accepted AUDITED outcomes/carry facts + audit/evidence lineage/version only
SupervisorState: phase + active contract + last exit/failure/audit ref + role/case budgets
Episode action limit: frozen during W1; multiple episodes share one BrowserGym case without reset
Mission round limit: frozen during W1
Prompt/model/settings: frozen for all 12 cases
```

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
- every model request/response, selected tool, action target semantics, dispatch, fresh transition, and control repair;
- every ManagerDecision, SubtaskContract, episode boundary/yield reason, AuditDelta, accepted/rejected MissionState
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
- failure origin separated into environment/setup, provider/schema, observation, grounding/action capability,
  policy reasoning/loop, terminal-response format, and official verification.

The bounded project claim is **WebArena-Verified Hard cross-site capability**, not SOTA parity or full-benchmark
coverage. It passes when:

- environment readiness and all six site smokes pass before the cohort;
- at least 6/12 cases receive official score `1.0`, with at least one success in each retrieve/navigate/mutate stratum;
- every reported success comes from the integrated official evaluator after one valid STOP;
- no `sent`/`sent_unknown` terminal delivery is retried automatically, and missing post-STOP evidence never counts as
  success;
- every case that crosses an episode boundary has a lineage-valid MissionState update and no executor self-report
  accepted without audit;
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
| relevant current DOM/AX fact is absent | fix/reuse BrowserGym SurfaceAdapter projection, or run a declared structured/adaptive observation A/B | site selector, task hint, or always-on VLM |
| offered control lacks a reusable interaction | add one generic semantic capability only if BrowserGym exposes a stable primitive and multiple tasks require it | raw Playwright escape or WebArena-only tool |
| fresh World and complete episode context are correct but policy loops | EpisodeMonitor yields; Manager chooses a new bounded route; compare a stronger policy only in a declared arm | case prompt, mutable GoalPlan status, or another GUI loop |
| an exact value is needed after navigation but was never pinned | improve general `pin_fact` tool description/admission and classify policy failure; do not reconstruct it from trace | task keyword extraction, hidden state, or arbitrary model memory |
| compact `AgentTurnView` history exceeds the byte budget in held-out episodes after deterministic folding | run a predeclared model-summary/offload A/B with full trace retained | silently drop oldest steps or make free-form summary authority |
| Manager repeatedly creates unsuitable subtasks despite correct MissionState | compare Manager prompt/model or narrower SubtaskContract in a new arm | per-step Manager, site skills, or moving planning into CoreLoop |
| Auditor accepts unsupported claims or misses visible completion | fix Auditor evidence bundle/prompt or AuditBoundary lineage contract across cases | native-evaluator oracle exposure or Auditor direct state writes |
| a historical carry fact is insufficiently current for a later decision/final audit | Manager assigns an explicit refresh subtask or Auditor returns missing evidence; record policy/audit failure if omitted | pretend Runtime can detect implicit fact use or treat historical evidence as current World truth |
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
`EvidenceRecord`s, and audited cross-episode MissionState. This is not optional
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
for G5 is not yet an executable product path; the no-reset/YIELDED lifecycle foundation and W1a items 2–3 are
implemented locally, while explicit `yield_subtask`, items 4–8, and their ownership tests still precede any W2 run. The current
executable gate is:

```bash
pytest -q tests/unit tests/integration tests/conformance
```

The first paired live run must use the frozen JSON manifest above, write raw per-case JSON under an artifact directory,
then aggregate only after all case records exist. The paired tolerance and A/B observation profiles must be recorded
alongside that run rather than embedded in product code.

Prompt or context changes are admitted only as predeclared cohort variants. A prompt must remain stable within a run;
benchmark case names, expected actions, labels, selectors, or answers may never be injected into it. Diagnose failures
by shared categories such as observation insufficiency, grounding, invalid tool use, action effect, progress, or
completion—not by adding per-case prompt instructions.

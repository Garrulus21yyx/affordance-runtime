# Benchmark

## Purpose

Benchmarks are the final evidence for task capability, generalization, robustness, and adaptive-observation value.
Unit, property, and architecture tests protect contracts; they do not substitute for live GUI execution.

## Primary questions

1. Does the agent complete supported GUI tasks?
2. Can it distinguish local UI effect from task-relative advance, regression, and readiness to finalize?
3. Does adaptive observation preserve or improve success relative to structured-only observation?
4. Does it reduce visual calls, model tokens, latency, or unnecessary acquisition?
5. Can it recover when evidence is insufficient, an action has an unknown effect, or a long task changes regime?

## Required report

Every live run records, per case:

- task and seed from a predeclared manifest;
- terminal status and official environment success;
- action, observation, and model-call counts;
- source selections by modality;
- visual supplementation and recovery counts;
- tokens and elapsed time;
- typed environment, provider, Runtime, and task failures.

Published reports must not contain prompts, model responses, selectors, coordinates, credentials, hidden state,
oracle values, expected answers, or benchmark reward payloads exposed to the model.

Local per-case evidence additionally contains a private complete `traces/<case-id>/trace.jsonl` plus
content-addressed media artifacts. This operational trace is not copied into the public report: it records the exact
public model context and tool catalog, typed decision, provider diagnostics, execution and evaluation facts, and
causal IDs needed to diagnose a failure. Each provider attempt contributes its complete OpenInference-shaped local
transcript, including repair-phase input and output; screenshot payloads remain content-addressed. Trace-write failure
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
different compiler availability, it is not a clean A/B; a predeclared same-guidance thinking on/off pair is the next
falsifiable model-setting test, not a larger watchdog.

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

This is a short-loop task-semantics failure, not a demonstrated memory-window failure. Action evaluation proved UI
change but no owner related that change to the quantified user goal, protected already-satisfied targets, or exposed
when Submit became ready. More raw history or stronger prompt wording is not accepted as closure evidence.
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

Then run a paired experiment:

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

The replacement production chain is:

```text
TaskGoal -> GoalCompiler(start/revision once) -> Simple GoalPlan
TaskGoal + GoalPlan + fresh World + recent steps + current tools
  -> single ActionPolicy -> Binder -> Executor -> fresh World
TaskEvaluator/native verifier -> formal completion
```

| Gate | Scope | Implementation output | Falsifiable exit evidence |
|---|---|---|---|
| G0. Reopened contract convergence | five maintained documents and owner map | one five-field plan contract; no symbolic progress path; explicit non-goals | docs, production types, tests, and trace projection agree; independent fresh-context review remains required |
| G1. Simple GoalPlan implementation | compiler, boundary, lifecycle, transcript trace | `id/objective/done_when/depends_on/final`; 1..8 items; unique acyclic IDs; at most one final; tolerant unknown fields | property/unit/integration tests pass; initial/schema/contract repair attempts survive independently; compiler failures remain advisory |
| G2. Single-context integration | direct plan projection into the existing five-section context | no lowering, evaluator, snapshot, frontier, status store, Binder change, or second loop | ActionPolicy receives Ready plan and fresh World; context identity changes on plan revision; external-breadth metrics retain compiler counters |
| G3. Short-loop live proof | one predeclared Like witness, then held-out cohort | official case evidence through the existing runner | first witness is run once after local gates; later held-out evidence is required before closure |
| G4. Flagship workflow | tomorrow 06:30 to Beijing Capital Airport T3; fastest vehicle at or below CNY 100; confirm before order | benchmark-driven capability additions only | held-out layout/value variants succeed; no over-budget selection; no commit without current confirmation |
| G5. Web long horizon | WorkArena atomic smoke, then WorkArena++ L2/L3 | mechanisms justified by measured failures | compositional success/partial progress improve without site logic in adapters |
| G6. Desktop long horizon | OSWorld-Verified smoke, then release-pinned OSWorld V2 | desktop/window/file/clipboard surfaces and reproducible harness | setup verification passes and infrastructure failures remain separate |

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

### G2: single-context integration

G2 keeps exactly five context sections: Task, Current Observation, Current Goal Plan, Recent Steps, and Current Tools.
A Ready plan is projected directly and contains no item status, frontier, per-subject result, binding, or completion
claim. ActionPolicy re-evaluates the plan against fresh World every turn. The stable prompt requires it to preserve
already active toggles unless undo is requested, advance the earliest visibly unsatisfied dependency-ready item, defer
a final item until prerequisites visibly hold, and emit exactly one action.

The follow-up formal run used the same official MiniWoB entry, case, seed, and model roles in a fresh evidence
directory. Compiler tracing and all six external-breadth compiler metrics were present, Ready guidance reached every
turn, and no compiler repair was needed. It therefore evaluates the new context path and falsifies the claim that the
current ActionPolicy reliably preserves visibly satisfied toggles. No single case can declare G1/G2 closed.

### G3: randomized Like cohort

Retain current runs as causal witnesses, not a statistical baseline. Freeze a generated cohort before treatment and
vary usernames, post counts/order, unrelated controls, initial active states, and collection visibility. Generator
values and official verifier state remain private. Report:

- official success and whether a Ready plan reached ActionPolicy;
- compiler disposition, attempts, repairs, and benchmark-side semantic-plan adequacy;
- every policy action, unrelated-control activation, and repeated/undoing toggle;
- fresh-world evidence visible before each decision;
- premature final-action attempts and steps from visibly satisfied prerequisites to final action;
- grounding, action-effect, provider, and official-verification failures.

The primary behavioral target is no final action while a required outcome is visibly unresolved. This is an
ActionPolicy capability metric, not a Runtime action ban. A held-out same-seed improvement is required for a capability
claim; one successful replay of `miniwob-60-17` remains only a Ready-path witness.

### G4: flagship taxi workflow

This is the minimum long-task portfolio demonstration even if time does not permit a full benchmark suite:

```text
schedule tomorrow 06:30 -> Beijing Capital Airport T3
filter current vehicle offers to price <= CNY 100
choose minimum ETA among eligible offers
present pickup + destination + absolute time/timezone + vehicle + price + ETA
wait for confirmation -> commit once
```

Phase two may add `CandidateSet`, numeric comparison, filtering, and `ArgMin`; selection is `unknown` unless candidate
coverage is complete. Confirmation is a digest over the accumulated facts and intended final effect; a changed time,
destination, vehicle, price, ETA, or action invalidates it. The task's general risk level must not force confirmation
on every preparatory action.

Instrument responsibility as well as success: one compiler attempt establishes optional semantic guidance; each
ordinary turn contains one action-policy call; later choices change after fresh World observations without per-step compiler calls or stored item status. Report
compiler outcomes, policy interpretation changes, enabling versus direct actions, and typed evidence requests.

The task boundary supplies the request-time clock and timezone so “tomorrow 06:30” normalizes once to an absolute
zoned time. Pickup must come from the task or a verified current UI default; if pickup, timezone, terminal, or another
required booking field cannot be established, the compiler returns `NeedsInput` and the existing user-pause path
revises `TaskGoal`. The agent never invents a pickup. Price and ETA are dynamic World facts and must be refreshed in
the confirmation snapshot immediately before commit.

Use held-out price/ETA combinations, layout changes, delayed loading, initially selected vehicles, and one value change
after confirmation. Required invariants are zero unconfirmed commits, zero commits from a stale confirmation, and zero
selection of a vehicle known to exceed CNY 100. Report official success separately from `needs_input`, provider,
grounding, and environment failures.

### When memory and larger benchmarks enter

Do not add model-authored memory for MiniWoB or the first taxi implementation. First measure whether a required fact
disappears across page or application boundaries and cannot be reconstructed from the current world, static goal plan, recent steps,
task evaluation, or confirmation snapshot. Only then add a typed achievement/receipt record with provenance,
currentness, and invalidation, followed by deterministic truncation. Free-form LLM compression is a last resort and
must win a paired long-horizon cohort before becoming default.

WorkArena precedes OSWorld because it exercises realistic compositional web tasks while reusing the browser surface.
OSWorld enters only after the Runtime can honestly observe and act across desktop windows, files, clipboard, and native
applications. As of 2026-08-16, OSWorld V2 recommends release `v2026.08.08`; the exact release, VM image, setup checks,
model, and action budget must be pinned in every report. Do not mix original OSWorld, OSWorld-Verified, and V2 scores.

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
makes no new live MiniWoB performance claim until the paired cohorts below have run. The current executable gate is:

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

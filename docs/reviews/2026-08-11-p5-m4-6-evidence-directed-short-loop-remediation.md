# P5-M4.6 evidence-directed short-loop remediation

> Current remediation record. The immutable trigger attribution is
> [P5-M4.5-C MiniWoB-60 diagnostic at `4924ce6`](2026-08-11-p5-m4-5-miniwob-60-diagnostic.md).
> This file may record later implementation and verification identities; the
> baseline JSON and baseline classifications must never be edited or backfilled.

## Trigger identity

```text
trigger_run_id: miniwob-60:e9551acfcd31466e91481ee5923fc9af
trigger_git_sha: 4924ce61748d8efdec4fcc6de494acf8a9f224cc
trigger_result: 60/60 complete; 8/60 success; evidence valid
archive_commit: 5f8d6acf3700831a05d73f93a5c66488a6298fd7
archive_commit_role: docs-only evidence archive, not implementation or run SHA
generalization: NOT_CLAIMED
```

The 6/60 run at `b3b64a2`, rerun-v3 4/60 at `83dc4fa`, and this 8/60
diagnostic are independent records. They are not merged into a trend claim.

## Current queue

```text
M4.6 overall: IN_PROGRESS
M4.6-A canonical AX semantics/currentness: COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE
M4.6-B verifier/task-terminal truth: COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE
M4.6-C semantic inventory truth: COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE
M4.6-D bounded control feedback/repair/no-gain: REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED
M4.6-E stable target identity and semantic breadth: BLOCKED_BY_M4_6_D_CONVERGENCE
M4.7 supported-subset multi-seed: BLOCKED_BY_M4_6_GATES
P5-E verified long-horizon frontier: BLOCKED_BY_BREADTH_GATES
```

Only one M4.6 product slice is implemented before its focused properties and
targeted evidence are recorded. This preserves attribution and avoids changing
currentness, verifier, observation breadth and liveness in one unmeasurable
patch.

## Remediation ledger without event-sourcing semantics

This table is documentation tracking only. It is not Runtime state, an event
ledger, a replay source or execution truth.

| Remediation | Trigger run / Git SHA | Observed cohort | Source mechanism | Claim limit | Implementation SHA | Verification run ID | Exit property |
|---|---|---|---|---|---|---|---|
| M4.6-A canonical AX semantics/currentness | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | no-step cases 18, 35, 48, 50, 55, 58; post-run review found 41 false + 1 terminal stale | AX projection and DOM heuristic probe independently owned role/name/state; whole-page select options and incomplete availability were adjacent same-owner defects | immutable JSON proves the 42 no-step shape, not the per-attempt 41/1 probe payload or a future success-rate gain | `896508eaf7737cd86289f93a30e5737c6b1cdf76` | `NONE` | unchanged canonical binding is current; any bound drift is typed `NOT_SENT` with zero step; probe/accounting identity remains exact |
| M4.6-B verifier/task-terminal truth | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | previous verifier-unknown cases 01, 03, 08, 10, 11, 21, 22, 32, 35, 41, 42, 46, 54, 59 | three-state verifier collapses non-success/non-ongoing combinations into unavailable/task unknown | the baseline does not reveal how many cases are negative terminal, ongoing, malformed or unavailable; the targeted run does not claim performance or generalization | `880e65fef0c2541be9f4b5af121e610f858685db` residual closure; original/run SHA `07895ede392bdff065ba3b4c0a6384ba18904143` | `miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015` | supported verifier algebra is total; raw probe facts preserve presence/type; nonterminal task facts do not erase cross-domain control truth |
| M4.6-C semantic inventory truth | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | zero-target/action cases 04, 05, 07, 14, 17, 26, 28, 33, 34, 36, 38, 43, 44, 47, 49, 52, 57 | executable-role filtering preceded target creation and projection-only coverage calculation; diagnostics separately rescanned raw AX | the accepted no-model run proves only `browsergym-ax-target-inventory.v1` counts, not task-relative completeness, success, performance or generalization | `e6c410021d8b9bf11b52f24520a6258ede5d2027` | `miniwob-inventory-17:6220967c47a24532b4140728627e4950` | projection coverage and semantic inventory are distinct; recognized omission cannot be reported as represented/empty; ActionSpace remains the only action-availability authority |
| M4.6-D bounded control feedback/repair/no-gain | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | direct repair witness 37 plus page/observation cohorts; post-closure review additionally falsified request/result and projection-view equivalence | request filters and page results shared a digest; the active page also entered the liveness scope, so request/view churn could fabricate gain | the valid targeted run proves bounded feedback/correction facts for this exact profile, not task success, performance, generalization, independent held-out closure or M4.5-B closure | `9e92bd2d3b55a696f06ae77fd029b4bc6db9a903` | `miniwob-control-feedback-25:98e8fff597d94badb82a44f6ed1a4c44` | request key, request-echo-free page result and control epoch have distinct owners; unseen result gains once per epoch; different requests with the same result and page/observation view churn terminate under the shared budget; sent/terminal precedence and zero-replay remain intact |
| M4.6-E stable identity/breadth | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` (source-only adjacent risk) | no direct baseline cohort for ordinal identity; zero-target cohort remains breadth witness | target ID includes ordinal; observable and executable roles are coupled | neither ordinal identity nor a particular unsupported role was shown to cause a baseline failure | `NONE` | `NONE` | identity survives irrelevant AX order changes; read-only semantics cannot grant unsupported execution; quotas preserve actionable controls |

`Implementation SHA` is filled only after a clean product commit exists.
`Verification run ID` is filled only for a new immutable targeted or full run.
Neither column ever points to the docs-only archive commit.

## Authority and dependency direction

| Owner | Responsibility |
|---|---|
| `browsergym_semantics` | immutable canonical AX control, computed role/name/typed state, availability, owner-scoped public/private option domain, public/private fingerprints, exact deduplication and typed conflict rejection |
| `browsergym_semantic_profile` | finite current BrowserGym observable/executable role algebra, semantic action, primitive, currentness fields and primitive availability conditions |
| `browsergym_currentness` | pure canonical binding/live comparison and bounded adapter-local reason |
| BrowserGym backend | owner-thread pinned observation and frame-safe BID physical reads plus step; no AX role/name inference and no public capture ownership |
| BrowserGym projection | bounded target/fact/binding assembly only |
| BrowserGym binding | immutable private canonical binding and public-label-to-native-value dispatch mapping only |
| BrowserGym verifier | pure external verifier fact classification |
| evaluation contracts | generic canonical `TaskOutcomeFact` and status/evidence matrix |
| task-evaluation control policy | the only `TaskEvaluation`-to-loop disposition owner |
| world semantic projection | generic inventory summary and identity-free public digest |
| typed admission/page validators | produce public-safe issue facts directly; no `ValueError`/message parsing and no feedback-owned duplicate schema |
| action evaluation/progress | retain ownership of no-effect/already-satisfied facts and existing local repetition semantics |
| agent control-feedback/liveness | envelope canonical repairable/no-gain/strategy-transition facts, consume a frozen two-distinct-issue budget and enforce exact-repeat/shared-scope bounds; no policy reasoning or action choice |
| `AgentLoopState` | current task evaluation and bounded repair/no-gain state authority |
| `ControlTransition` | preserve the canonical feedback fact on the accepted-decision root; never become a repair log or state-reconstruction source |
| model control-feedback projection | one-way public-safe `AgentControlFeedbackView`; no inference from reason text, benchmark outcome or raw exception |
| `AgentPolicy` | use current AgentContext and feedback to correct parameters or change strategy in the next ordinary decision; no completion/effect authority |
| AgentResult/session snapshot/CaseFacts | current-epoch bounded one-way task-outcome projection |
| external breadth classification | unique benchmark outcome precedence |
| codec/legacy/model/telemetry projections | downstream-only copies, never inference owners |

No file is split or retained because of a line-count threshold. Responsibility,
authority, cohesion and change coupling decide ownership. Projection,
`ContextBuilder` and benchmark classification must not become god owners.

## Cross-slice non-goals

- no durable ledger, replay, event sourcing or state reconstruction;
- no new StateKernel, transaction platform or generic recovery engine;
- no planner, VerifiedTaskState or TaskProgressAuditor under M4.6;
- no Runtime parameter autocorrection, substitute-action selection or separate
  reflection/critic model call under M4.6-D;
- no task-specific role aliases or relaxation of semantic/currentness checks;
- no Langfuse/OpenTelemetry authority over Runtime or benchmark facts;
- no rewriting of the 64 baseline JSON files or their typed outcomes;
- no full MiniWoB-60 rerun until the targeted gates identify remaining gaps.

## M4.6-D convergence contract

Two post-closure defects shared one semantic-owner cause, so D is
`REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED` and E is
`BLOCKED_BY_M4_6_D_CONVERGENCE`. Implementation and valid run identities are
recorded below, but closure still requires independent held-out review.

### SOTA calibration as of 2026-08-11

Primary sources show a shared feedback trend, not one standardized Runtime
contract:

- BrowserGym's official
  DemoAgent builds the
  [current-page description](https://github.com/ServiceNow/BrowserGym/blob/main/demo_agent/agent.py#L156-L224)
  and puts it with a
  [turn history containing prior actions/errors](https://github.com/ServiceNow/BrowserGym/blob/main/demo_agent/agent.py#L248-L329)
  into the next ordinary policy prompt and asks the model to reflect before its
  next action; the environment observation also exposes
  [`last_action`](https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/core/src/browsergym/core/env.py#L625-L630)
  and
  [`last_action_error`](https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/core/src/browsergym/core/env.py#L681-L686).
  This supports recurrent feedback, but copying a raw exception is not an
  acceptable privacy/authority boundary for this project.
- [UI-TARS-2](https://arxiv.org/abs/2509.02544) formulates every ReAct step as
  reasoning/action/environment observation, with self-reflection inside model
  reasoning and recent steps in working memory. It supports feedback-conditioned
  policy improvement but does not define a typed admission-repair standard.
- [Qwen-UI-Agent](https://arxiv.org/html/2607.28227#S2.SS2.SSS3) makes CLI stdout, stderr and
  exit status structured observations alongside the post-action screenshot;
  non-zero exits and timeouts become error observations rather than aborting the
  episode, allowing recovery in the same trajectory. Separately, confirmed
  environment failures update the health-aware scheduler. This supports keeping
  policy-correctable input separate from adapter/environment failure authority.
- [Agent S2](https://arxiv.org/abs/2504.00906) provides the alternative of an
  optional per-step reflector and hierarchical replanning. Its
  [reflector/worker implementation](https://github.com/simular-ai/Agent-S/blob/bffdb59c60cbbb38c3a190b2e91da12039e4063c/gui_agents/s2/agents/worker.py#L157-L194)
  flags failed actions or repeated cycles, while the
  [reflection contract](https://github.com/simular-ai/Agent-S/blob/bffdb59c60cbbb38c3a190b2e91da12039e4063c/gui_agents/s2/memory/procedural_memory.py#L103-L116)
  deliberately does not choose the replacement action; the Worker does. A failed subtask returns to the Manager
  with the latest observation for replanning.
- [LongHorizon-Harness](https://arxiv.org/abs/2608.01964) externalizes unresolved
  failures into independently audited task state and gives a fresh executor the
  remaining work. That mechanism is relevant to P5-E VerifiedTaskState, not a
  reason to add a task-state platform to short-loop M4.6-D.

The bounded project inference is therefore: treat sanitized typed feedback as a
result observation, not a corrective instruction; expose it through a dedicated
one-way AgentContext channel and let the ordinary policy turn reflect and choose
the correction. A separate reflector remains an evidence-gated
policy extension only if targeted/full benchmark results show that the policy
receives correct feedback but still repeats; it cannot become Runtime truth or
action authority.

The convergence boundary is also consistent with the underlying environment
interfaces: [Gymnasium `Env.step`](https://gymnasium.farama.org/api/env/)
accepts an action and returns the resulting observation/reward/termination
facts; BrowserGym's official
[agent loop](https://github.com/ServiceNow/BrowserGym/blob/main/README.md)
keeps `action` separate from the observation returned by `step`; and
[WebArena](https://arxiv.org/abs/2307.13854) models an action through the
environment transition to the next state and observation. The bounded inference
is not that these systems prescribe this project's repair budget, but that a
request/action is not itself evidence of a new result/world state.

### Reopen causal model and closed supported algebra

The casefold defect and the later different-query/same-result defect are not
independent. Both came from one ambiguous `public_action_page_semantics` owner:
it mixed request filters, full action-contract facts and visible result facts,
then the feedback scope reused that mixed digest as progress authority. The
first patch aligned one request representation but left the authority mixing in
place; the old example-only gate therefore missed cross-request and
cross-projection equivalence classes.

The supported algebra is now:

```text
PageRequestKey = canonical query + semantic target/relevance + semantic offset
PageResult = visible option/destination semantics + result count + continuation
ControlEpoch = task revision + public world + full public action contract
             + validated task-progress fingerprint
InformationGain = effectful SENT, new ControlEpoch, or a PageResult not yet
                  seen in the current epoch
```

Request echoes, active filters, cursor/page/context/action identities and
projection-view switches are excluded from result and epoch truth. Each epoch
stores at most 64 result digests. A result grants page gain once; a previously
seen result is no-gain. Capacity exhaustion fails closed as no-gain rather than
evicting history and regranting progress. The existing two-distinct-issue budget
remains shared by admission, page and policy-observation issues. Effectful
`SENT`, world/action-contract/task-progress change starts a new epoch; terminal
and `SENT_UNKNOWN` precedence remain unchanged.

The exact `4924ce6` diagnostic contains ten cases whose final outcome is
`runtime_rejected`: four `action_outside_current_page`, three
`destination_outside_current_page`, one `invalid_action_parameters` and two
`invalid_completion_claim`. This does not mean every whole case had zero prior
dispatch: cases 06, 12 and 53 each recorded an earlier step. Case 37 is the
direct repair witness—one policy call, zero execution/step and three current
options. Exact source preserves its canonical parameter-admission reason in the
terminal transition/result but does not invoke policy again, so the same Agent
cannot use it to repair the decision. The seven final current-page action/
destination rejections are adjacent public-selection witnesses; invalid
completion claims remain outside D. None proves that an added repair opportunity
will improve task success.

M4.6-D introduces a canonical `ControlFeedback` envelope on the same root
`ControlTransition` and a bounded, model-safe projection in the next ordinary
AgentContext. The owning ActionSpace/page validator must first produce a typed,
public-safe issue; feedback may report its kind, stable code, public subject/
field paths, next-decision disposition and `strategy_transition_required`, but subject
is optional for page/observation feedback and the model view never receives
internal scope/issue/request/result digests. Feedback may not
parse exception strings. Current ActionSpace/page owners retain their schemas
and domains; feedback references them rather than copying a second contract.
Raw exception text, private binding/native values, selectors, routes, provider
payload and benchmark labels never enter feedback.

The supported transition algebra is:

```text
first current zero-dispatch public-contract rejection in one public semantic scope
→ record REPAIRABLE_REJECTION with zero bind/probe/execute
→ close exactly one root ControlTransition
→ project feedback into one fresh AgentContext
→ one ordinary AgentPolicy decision chooses correction or another strategy

same typed issue fingerprint before effectful dispatch or public gain
→ NO_PROGRESS_CONTROL_REPETITION typed terminal; zero dispatch

second distinct repair/no-gain issue in the same scope
→ one final bounded feedback opportunity
third distinct repair/no-gain issue in the same scope
→ NO_PROGRESS_CONTROL_REPETITION typed terminal; zero dispatch

first exact action-page/policy-observation no-gain
→ typed feedback and continue
same request + same identity-free public result again
→ NO_PROGRESS_CONTROL_REPETITION
```

The semantic scope is defined from task revision, identity-free public-world
semantic digest, public action-contract/page digest and task-progress
fingerprint. It explicitly excludes observation/action-space/page/context IDs,
context generation, invalid parameter values, free-form reason text and every
private identity. The initial M4.6-D profile freezes one shared budget of two
distinct repair/no-gain issue fingerprints per scope. An identical issue repeat
terminates immediately; a third distinct issue terminates, so alternating
invalid action/page/observation cannot enumerate forever. Only an effectful
`SENT` or relevant public semantic/task-progress/action-page gain clears repair
state; a merely admitted no-gain control decision does not. The value two is a
falsifiable initial benchmark choice, not a claimed SOTA constant. Risk or
safety block, terminal task/session, cancellation, budget exhaustion,
`SENT_UNKNOWN`, evaluator/component invalid output, capability/integrity failure
and an adapter parameter mismatch after successful ActionSpace admission remain
non-repairable. The last case is an adapter-contract failure, not a request for
the model to guess private adapter semantics. No sent or uncertain request is
ever replayed. Existing validated `NO_EFFECT_CONFIRMED` and already-satisfied
feedback continues through ActionEvaluation/ProgressEvent/ProgressController;
D makes its strategy-transition meaning unambiguous to policy but does not add a
universal effectful-action retry controller.

Primary verification is property/state-machine based: one root per accepted
decision; every rejected decision remains zero bind/probe/execute/capture while
its feedback is visible once in the next ordinary policy context; identical
issues terminate on repeat and a third distinct same-scope issue terminates, so
alternate bad parameters/control requests cannot enumerate indefinitely; typed
admission issues
are never reconstructed from messages; private/raw data never projects;
identity-only refresh cannot reset the scope; semantic gain permits a new
decision; task terminal and unknown-effect precedence remain absorbing; Runtime
refresh is exempt. Targeted live evidence includes case 37, the declared
current-page selection witnesses and page/observation cohorts under a new run
ID. Success improvement is measured but is not required to prove the bounded
feedback contract; no result is backfilled into the trigger archive.

## M4.6-A focused evidence

The product implementation is
`896508eaf7737cd86289f93a30e5737c6b1cdf76`. No new immutable targeted run
artifact was produced, so the ledger Verification run ID remains `NONE`.
These focused commands are verification evidence, not a campaign run ID:

- canonical/currentness/execution/projection properties: `40 passed`;
- all BrowserGym-focused tests: `236 passed, 18 skipped`;
- Python 3.12 pinned real gate with command-scoped local fixture URL:
  `18 passed` in 31.62 seconds, covering click-tab, click-tab-2,
  click-tab-2-hard, click-tab-2-easy, book-flight, choose-list and the
  login-user-popup terminal path;
- focused physical-probe latency witness: six probes, 205.80 ms minimum,
  332.58 ms median and 427.49 ms maximum;
- full repository suite: `2091 passed, 23 skipped` in 76.48 seconds;
- `ruff check .`, `mypy src` (431 source files), main and pinned clean-process
  forward/reverse imports, `git diff --check`, and immutable evidence digest
  `7a3f60c10896fc2f458afc11874bce866987fb9f1e752c8d164ae4b05d80b318`
  all passed.

Fresh-context adversarial review generated held-out duplicate/conflicting BID
and node identity, option-owner/domain, availability, AX order, malformed probe,
terminal re-entry and private-projection variants. It found shared-owner gaps
for option ownership, bidless conflict handling, duplicate native option
values, semantic node identity and explicit BID comparison; each was repaired
in the shared canonicalizer/comparator with no task-specific branch. The final
fresh-context verdict was `VERIFIED`.

This attests only canonical currentness on the declared non-default scope. It
does not claim a MiniWoB success-rate, performance improvement, generalization,
M4.5-B closure, or completion of M4.6-B through M4.6-E or P5-E.

## M4.6-B focused and targeted evidence

The clean product implementation is
`07895ede392bdff065ba3b4c0a6384ba18904143`. The accepted immutable targeted
run is `miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015` under
`docs/evidence/runs/p5-m4-6-b-miniwob-verifier-14-seed7-07895ed-targeted/`.
It is the frozen previous-verifier-unknown cohort, not a full MiniWoB-60 run or
a negative-terminal cohort selected after observing results.

- source-aware verifier properties cover exact bool/numeric validation,
  bool-as-number, NaN/infinity, arbitrary shapes and held-out exact integers
  through `10**10000`; RESET cannot prove terminal status and malformed or
  unsupported combinations fail closed;
- evaluation/evidence properties separate completion proof from neutral
  negative-status proof and reject stale-epoch evidence;
- loop/reducer properties preserve actual Runtime failures, make pure task
  terminal failure absorbing and exactly-once, and produce no synthetic
  `RuntimeFailure(CONTROL, REJECTED)`;
- CaseFacts v8, v6/v7 read-only decoding and classification precedence
  properties prevent status/message/latest-operation or metric inference;
- the command-scoped Python 3.12 pinned real gate passed `13` tests, including
  deterministic `login-user-popup` seed 7 with exactly one SENT and backend
  step, `BLOCKED` terminal task outcome, current neutral evidence, empty
  completion proof, no RuntimeFailure and zero-call terminal re-entry;
- the final full repository suite passed `2115` tests with `26` skipped;
  `ruff check .`, `mypy src` over 433 source files, clean-process imports,
  architecture/documentation gates and `git diff --check` passed;
- fresh-context review generated held-out source/evidence/timing/legacy/privacy
  variants. It found shared exact-large-int and legacy-emission gaps; both were
  fixed in the common classifier/codec, and the final verdict was `VERIFIED`.

The targeted run completed 14/14 with valid evidence, zero acceptance or
harness-integrity errors, zero unclassified outcomes and a clean privacy scan.
Canonical verifier distribution was 12 `TERMINAL_TASK_FAILURE` and 2
`INCOMPLETE`; benchmark distribution was 13 `TASK_FAILED` and 1
`RUNTIME_REJECTED`. All 12 terminal-task-failure cases classified as
`TASK_FAILED` from `canonical_task_outcome` with no RuntimeFailure. The extra
`TASK_FAILED` was an independent canonical session RuntimeFailure after a
running-incomplete fact, so precedence remained orthogonal.

The old diagnostic remains exactly 64 JSON files with digest
`7a3f60c10896fc2f458afc11874bce866987fb9f1e752c8d164ae4b05d80b318`.
No old result or classification was rewritten. M4.6 remains `IN_PROGRESS`,
M4.6-C is `COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE`, M4.6-D is
`REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED`, M4.6-E is
`BLOCKED_BY_M4_6_D_CONVERGENCE`, and M4.5-B reviewed closure SHA remains `NONE`. No
performance, success-rate or generalization claim is made.

## M4.6-C focused no-model evidence

Implementation `e6c410021d8b9bf11b52f24520a6258ede5d2027` establishes one generic
frozen semantic-inventory summary, one BrowserGym AX analysis owner and a
one-way model-safe source projection. `projection_coverage` retains the old
quota-only meaning; inventory status is relative only to
`browsergym-ax-target-inventory.v1`. ActionSpace remains the sole authority for
action availability, and C adds no target role, binding, primitive or action.

The immutable run `miniwob-inventory-17:6220967c47a24532b4140728627e4950`
completed the fixed 17-case seed-7 cohort with 13 `EMPTY`, 3 `REPRESENTED` and
1 `PARTIAL`. All 17 acquisitions, projections and cleanups completed; schema,
count, privacy, harness-integrity and unclassified errors were zero. Policy,
provider, token, step, currentness-probe and independent-capture totals were
all zero. Campaign SHA-256 is
`3666c465f26b66e7626aace12dce81ff2ccaccd6d4ea6a5d63a141e2f1ceb07f`;
summary SHA-256 is
`3f486ebdf00311bbbc87ae4befee16ed0e5586dc771ebcb63374774bf7c54841`.
Fresh-context review found one shared evidence-identity validation gap; forged
campaign identity and recomputed false aggregates now fail closed in the shared
validator, after which the new exact-SHA run and held-out re-review passed.

## M4.6-B residual shared-contract closure

The original M4.6-B implementation and targeted evidence remain bound to
`07895ede392bdff065ba3b4c0a6384ba18904143`. Residual contract implementation
`880e65fef0c2541be9f4b5af121e610f858685db` closes two shared seams without
reinterpreting that run or creating a replacement campaign ID:

- the BrowserGym owner-thread producer preserves the presence and raw type of
  `ready`, `done` and raw-reward facts; `browsergym_verifier` remains the only
  validation and four-state classification owner;
- `post_action_policy` owns cross-domain precedence, so supported terminal task
  truth is absorbing while `SENT_UNKNOWN` or an actual action failure remains
  authoritative over nonterminal task facts; `control_reducer` validates that
  final disposition and constrains only canonical terminal task outcomes.

The producer and AgentLoop witnesses failed before the shared-owner change and
passed afterward. Focused verifier/control/benchmark properties passed 184
tests. The command-scoped Python 3.12 pinned BrowserGym/Playwright gate passed
18 tests, including raw missing/wrong-type producer facts, valid official
ongoing/success/terminal facts and the deterministic terminal task path. The
full repository suite passed `2119` tests with `27` skipped; Ruff, mypy over 433
source files, main and pinned clean-process imports, documentation/architecture
governance and `git diff --check` passed.

An independent fresh-context review generated all seven missing-key subsets,
13 undefined/wrong-type facts, three non-finite values, 12 valid typed truth
states, six malformed containers and 29 task-outcome/dispatch/action/control
stopping combinations. It verified terminal absorption, unknown-effect
no-replay, independent failure precedence and finalized re-entry without a new
production branch. Verdict: `VERIFIED`.

No new targeted run ID was produced. The accepted ID remains
`miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015`, explicitly at the
original implementation SHA. Its evidence directory remained byte-identical
(sorted file-manifest digest
`7c80e6c0533f396268b2531587b27d5420db3fbd72500ad6ebf9a0071df433ae`).
The old diagnostic remains 64 JSON files with digest
`7a3f60c10896fc2f458afc11874bce866987fb9f1e752c8d164ae4b05d80b318`.

## M4.6-D convergence implementation and evidence

Implementation `9e92bd2d3b55a696f06ae77fd029b4bc6db9a903` separates the
request key, request-echo-free page result, full action contract and control
epoch. `AgentLoopState` owns a bounded same-epoch set of seen page results in
addition to the existing shared two-distinct-issue budget. Different requests
with the same result, identity churn and page/observation view alternation can
no longer reset the budget. A genuinely unseen result grants page gain once;
effectful `SENT` or a public-world/action-contract/task-progress change starts a
new epoch. Runtime still performs no parameter correction, replacement action,
request replay or extra model call.

The valid immutable run
`miniwob-control-feedback-25:98e8fff597d94badb82a44f6ed1a4c44`
completed 25/25 at seed 7 with profile `mistral-format-only-v1`, provider
`mistral`, model `mistral-medium-3-5` and grounding `format-only.v1`.
Outcome distribution was 12 `NO_PROGRESS_CONTROL_REPETITION`, nine
`PROVIDER_UNAVAILABLE`, two `TASK_FAILED`, one `RUNTIME_REJECTED` and one
`SUCCESS`. It recorded 27 feedback facts, 15 context deliveries, 15 issue
consumptions and 12 bounded control terminations. Across the run it recorded 41
policy/provider attempts, four executions/steps/probes, zero independent
captures and 25 resets. Provider retry/fallback,
privacy, schema, harness-integrity, cleanup, duplicate-unknown,
stale-zero-call, forbidden-effect and repair-zero-call violations were zero.
Campaign, summary and attestation SHA-256 values are respectively
`20bbd6eedb846ba89fd6118bf4f542d73097ca4e31f4317e91ebc46e8fdca676`,
`39351275a12e6fed4de76c4a2dbcaa27b2213eca92c76a96507c200f84a819d7` and
`3b383d918f7b304c7e91bde87fde085d1883f8798bdb9e4093c24e9d4625f50e`.

Focused D and affected regression gates passed 221 tests; the generated
request/view-churn and once-only page-result properties passed within that
gate. The full suite passed 2196 with 27 skipped. Ruff, mypy over 442 source
files, architecture/documentation gates, compose validation, clean-process
imports and `git diff --check` passed. The command-scoped pinned Python 3.12
BrowserGym gate passed 17 tests. Clean-SHA full-validation was accepted with
SHA-256
`8ea097422eebca0af7a1273a533c8a3c11ceb116cbdca37336e036e2601bb4f1`.
This evidence measures bounded feedback delivery and admission correction; it
does not prove a success-rate, performance or generalization improvement.

The earlier `ccb682a` and `8b92d13` implementations and their runs remain
immutable historical evidence. Neither validates the convergence patch. The
new run is valid implementation evidence, but D remains implemented-not-verified
until an independent fresh-context held-out review confirms the frozen algebra;
therefore this section does not attest closure or admit E.

## Promotion gate

After M4.6-A through M4.6-E have independent implementation identities and
focused evidence, create a new immutable same-profile MiniWoB-60 record. Only
then may the project decide whether M4.7 receives a predeclared supported-subset
multi-seed manifest and thresholds. M4.5-B remains independently reopened and
implemented-not-verified until its own property, held-out and clean-attestation
gate passes; M4.6 product work must not be reported as B closure evidence.

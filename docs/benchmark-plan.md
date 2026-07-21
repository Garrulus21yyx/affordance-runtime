# Benchmark Plan

Affordance Runtime should be evaluated as a GUI execution runtime, not only as
a browser task solver. The benchmark asks whether the runtime can bind actions
to current environment state, avoid unsafe side effects, verify effects, recover
from drift, and turn failures into regression-gated harness improvements.

## Evaluation Layers

The generalist path is evaluated in three separable layers:

| Layer | Input -> output | Primary diagnosis |
| --- | --- | --- |
| Intent compilation | raw request -> canonical `TaskSpec` | goal, constraint, ambiguity, provenance, and authority errors |
| Planner/runtime | canonical `TaskSpec` + environment -> verified result | planning, grounding, execution, verification, and recovery errors |
| End to end | raw request -> verified result | actual standalone user experience |

BrowserGym normally starts at the second layer so official task failures are not
silently attributed to intent compilation. A separate paraphrase suite evaluates
the compiler. Full schemas, metrics, and safety gates are in
[Task Intake and Generalist Planner](task-intake-and-planner.md).

## Scenario Priority

The benchmark plan should make the project's generalization story concrete
without letting the old smart-room demo define the project. The flagship path is
realistic Web GUI work; device/WoT is retained only as a non-web adapter proof.

| Module | Keep? | Role |
| --- | --- | --- |
| Web GUI Runtime | Must keep and lead | Main project surface and first runnable gold path |
| MiniWoB++ | Keep | Atomic action benchmark for click/type/select/form sanity |
| WebArena-style mock env | Keep | Controlled multi-step workflows plus failure injection |
| SaaS/pricing/invoice demo | Must add | Flagship realistic demo for harness/eval/evolve value |
| Visual/SoM fixtures | Keep | Visual fallback and mark-level grounding checks |
| WoT smart-room | Downgrade and keep | Non-web adapter proof; not the project main story |
| OSWorld/mobile | Do not do in MVP | Future expansion after the web harness is stable |

The main demo should therefore look like a realistic web workflow, not an IoT
room-control demo. Good flagship tasks include pricing extraction with evidence,
invoice or receipt download, reversible admin setting updates, support portal
case creation, and report export with explicit approval. These tasks expose the
runtime's real value: stale affordance rejection, capability gates, verifier
receipts, recovery from modals or selector drift, trace replay, benchmark
scoring, and harness evolution.

## MVP Scenario Matrix

| Scenario | Purpose | Spec | Perturbations | Oracle |
| --- | --- | --- | --- | --- |
| Local SaaS Pricing | read-only evidence extraction | `docs/scenarios/pricing-extraction.md` | async loading, layout shift, modal banner | fixture canonical pricing JSON |
| Reversible Settings | controlled write path | `docs/scenarios/settings-update.md` | selector drift, stale target, confirmation modal | fixture DB/API persisted value |
| Approval-Gated Export | approval and receipt handling | `docs/scenarios/approval-gated-report-export.md` | delayed download, stale approval target, duplicate export button | approval log plus file/hash receipt |
| MiniWoB++ | atomic action sanity | M8 pinned curated adapter | official seeded episodes | official done/raw reward |
| WebArena-style Mock | long-horizon web workflow | future | distractors, multi-tab state | programmatic verifier |
| Visual Grounding | SoM and screenshot fallback | M8 screenshot-pixel path | distinct training/held-out positions | detected target box and visual receipt |
| Device/WoT | non-web affordance proof | M8.1 optional `wot-proof` profile | stale device state, rate limit | state source receipt |

Visual tasks should avoid vague labels such as `vibe` unless the oracle can be
programmed. Prefer concrete targets such as color, icon, badge, relative
position, or fixture mark id.

## Cross-Surface Conformance Gate

The project must preserve the old action system's useful proof that different
environment surfaces can enter one runtime, while evaluating the stronger
harness semantics added here.

The optional `wot-proof` fixture exposes one reversible device state through:

1. a DOM dashboard control;
2. a control grounded from real screenshot pixels through SoM;
3. a WoT Thing Description operation.

All three runs use the same semantic goal, capability, expected effect, and
independent device-state oracle. Each run must pass through the shared
Coordinator and emit:

- a common Action Contract envelope with a typed surface payload;
- policy/preflight evidence;
- an execution receipt;
- independent postcondition verification;
- the common trace schema and evaluator metrics.

The test fails if a surface calls its executor directly, if visual grounding
receives DOM coordinates, or if WoT reuses a read form as a write operation.
Reports show backend-specific latency/failures separately. Passing this gate
demonstrates cross-surface harness compatibility; it does not claim that the
controlled visual and WoT paths have the same deployment maturity as DOM.

## Baselines

Every benchmark report should include at least:

| Baseline | Meaning | Purpose |
| --- | --- | --- |
| Direct Playwright | scripted stable selectors, no runtime harness | shows task difficulty floor |
| Primitive Browser Agent | planner calls click/type/wait primitives directly | shows value of contracts, preflight, and verification |
| Full Affordance Runtime | all enabled runtime layers | target system |

The baseline is not expected to be safer than the runtime. It exists to answer
what the runtime abstractions add beyond ordinary browser automation.

## Ablations

Core abstractions should be tested by disabling them:

| Ablation | Disabled Layer | Expected Signal |
| --- | --- | --- |
| no lease/preflight | snapshot and target validity checks | more stale executions under drift |
| no structural verifier | independent postcondition evidence | more false success judgments |
| no capability gate | task policy and approval enforcement | unsafe or unauthorized side effects |
| no recovery | bounded recovery strategies | lower completion under modal/drift |
| DOM-only | visual fallback disabled | exposes where visual grounding is needed |

## Metric Schema

Each metric must declare:

```text
name
definition
numerator
denominator
direction
unit
ground_truth_source
aggregation
acceptance_threshold
```

## Runtime-Specific Metrics

These are the metrics that differentiate the project from a normal browser-use
wrapper:

| Metric | Definition | Direction | Ground Truth |
| --- | --- | --- | --- |
| `task_success_rate` | successful tasks / total tasks | higher better | scenario oracle |
| `constraint_violation_rate` | explicit constraint violations / evaluated constraints | lower better | policy log + oracle |
| `stale_detection_recall` | blocked injected-stale actions / injected-stale actions | higher better | perturbation label |
| `false_stale_block_rate` | valid actions incorrectly blocked / valid actions | lower better | perturbation label |
| `effect_receipt_coverage` | effectful actions with structural receipts / effectful actions | higher better | receipt schema |
| `verifier_false_accept_rate` | failed ground-truth outcomes judged successful / failed outcomes | lower better | independent oracle |
| `unsafe_side_effect_rate` | unsafe side effects / side-effect opportunities | lower better | audit log |
| `recovery_success_rate` | successful recoveries / recovery attempts | higher better | trace + oracle |
| `semantic_replay_success_rate` | semantically replayed tasks / replayable tasks | higher better | resettable fixture |
| `cost_per_success` | total cost / successful tasks | lower better | run accounting |

Do not use total primitive actions as the denominator for every metric. Stale,
verification, and side-effect metrics need their own opportunity sets.

## Ground Truth Sources

| Scenario | Ground Truth |
| --- | --- |
| pricing extraction | fixture server canonical JSON plus evidence refs |
| settings update | server-side persisted value and history |
| report export | approval event log, file receipt, file hash, audit record |
| stale action | injected perturbation label |
| modal recovery | fixture state machine |
| visual grounding | fixture mark id or deterministic visual target |

The acting model is never the sole grader. Model judgment may appear as weak
verification evidence, not as final benchmark truth.

## Experimental Protocol

Each report should record:

- suite version and fixture commit
- runtime version and contract schema version
- model/provider/version when a model is used
- temperature and decoding configuration
- seeds and number of repetitions
- timeout, retry, and recovery budgets
- cache policy
- whether failures are retried
- mean and standard deviation where repeated runs are used
- links to traces and artifacts

## Current M8 Generalization Gate

The `generalization-v1` gate complements the 63-run local matrix with:

- six held-out local scenario runs using unseen control IDs and distractors;
- five real PNG screenshot-grounding runs over distinct training and held-out
  positions, with no DOM coordinates supplied to the visual executor;
- 18 official MiniWoB++ episodes from pinned Farama commit
  `eb59fed60fabe8951350275ba8650633b740013b`, covering click, type, select,
  dialog, sequence, and form over seeds 0, 1, and 2.

The official MiniWoB result is reported as a curated runtime subset. It is not
presented as a full-suite MiniWoB++ score.

## Public Benchmark Ladder

The 18-episode M8 result is a compatibility smoke test. It is not sufficient as
external generalization evidence because the current adapter covers six task
templates and its solver contains task-specific parsing and selectors.

| Gate | Coverage | Purpose |
| --- | --- | --- |
| PR smoke | current 6 task types x 3 seeds | fast adapter/browser regression |
| Nightly | at least 30 task types x 10 seeds | task-family variance and unsupported actions |
| Release | every task supported by pinned BrowserGym x 5 seeds | broad reproducible coverage |

The scored path must not use per-task regexes or hardcoded selectors. Every
episode must traverse:

```text
observe -> affordance -> proposal -> contract -> preflight
        -> execute -> post-state/reward -> trace
```

Report supported/unsupported tasks, action-family coverage, seed variance,
official reward/success, runtime errors, and artifacts. Unsupported cases must
not be silently excluded.

| Order | Suite | Planned use |
| --- | --- | --- |
| 1 | [ScreenSpot](https://github.com/njucckevin/SeeClick) | full offline screenshot grounding |
| 2 | [WorkArena](https://github.com/ServiceNow/WorkArena) | L1 tasks, then stratified WorkArena++ |
| 3 | [WebArena-Verified](https://github.com/ServiceNow/webarena-verified) | 30-50 task subset, then hard subset |
| 4 | [WASP](https://github.com/facebookresearch/wasp) | browser-agent security subset |
| 5 | [VisualWebArena](https://github.com/web-arena-x/visualwebarena) | after multimodal routing is stable |
| Future | OSWorld | after the Web harness is mature |

### ScreenSpot Offline Harness

`affordance-runtime benchmark-screenspot` is the first public-ladder adapter.
It consumes the unmodified ScreenSpot annotation JSON and an explicit prediction
artifact rather than embedding a benchmark solver. The annotation fields are
`img_filename`, `instruction`, and pixel `bbox=[x, y, width, height]`; a
prediction is a `sample_id` plus `point_xy` (or `x`/`y`), with an explicit
`normalized` flag when coordinates are in `[0, 1]` image units.

The report scores only whether the predicted point is inside the ground-truth
box, verifies image dimensions, splits results by `data_type` and
`data_source`, and fails closed on missing, duplicate, or unexpected
predictions. It is a reproducible offline evaluation harness, not an official
ScreenSpot score until the complete official assets and a versioned prediction
artifact are supplied.

### WorkArena L1 Deployment Gate

`affordance-runtime benchmark-workarena-preflight` verifies the isolated
`browsergym-workarena` / Playwright 1.44 environment, the official 33-task L1
registration, and one permitted ServiceNow instance source. It reports only
the source category (`explicit_instance`, `custom_instance_pool`, or
`gated_instance_pool`), never an URL, username, password, token, or pool
contents. It also records `oracle_used=false`: the WorkArena `cheat` helper is
not a valid scored execution path.

The preflight must pass before an L1 matrix can be run through the existing
BrowserGym observation → proposal → contract → preflight → execution path.
The current default Web runtime intentionally does not satisfy this gate because
it uses Playwright 1.61; WorkArena must run in a dedicated BrowserGym 1.44
environment with authorized ServiceNow access.

### WASP Security Baseline

Before a WASP subset is attached, the general planner marks every page-derived
label, DOM/accessibility/OCR string, and screenshot as an untrusted observation.
Such content can ground an already-authorized affordance only; it cannot alter
the `TaskSpec`, grant a capability, supply approval, or become planner policy.
This is enforced by the `generalist-planner-v7` prompt boundary together with
the existing deterministic proposal schema, contract capability gate, and
approval binding. A future WASP run must exercise this baseline against the
official malicious-page cases and report the result separately; this statement
is not an official WASP score.

`affordance-runtime prepare-wasp-subset` prepares that run from the official
WASP configuration. It uses a digest-bound, environment/exfiltration
round-robin selection and exposes only opaque case indices plus evaluator-type
metadata; malicious instructions and their parameters remain in the upstream
source configuration. The resulting manifest is preparation evidence, never a
security score.

### WebArena-Verified Subset Manifest

`affordance-runtime prepare-webarena-verified-subset` accepts the official
WebArena-Verified dataset JSON and emits a deterministic 30--50 task manifest.
It round-robins task IDs over their primary sites and stores the input dataset
SHA-256, task revision, template ID, selected IDs, and resulting site
distribution. The manifest deliberately has `official_score_claimed=false`.

Once an isolated WebArena environment and agent logs are available, those exact
task IDs must be evaluated by upstream `webarena-verified eval-tasks`, which
uses its deterministic response and network-trace evaluators. Affordance
Runtime must retain the upstream results rather than replacing them with a
local score approximation.

`affordance-runtime evaluate-webarena-verified` supplies that boundary. It
passes the digest-bound manifest IDs to upstream without a shell, retains every
upstream `eval_result.json`, computes only a transparent aggregate of upstream
scores, and fails if any requested task lacks an official result.

[BrowserGym](https://github.com/ServiceNow/BrowserGym) is the preferred adapter
for suites it exposes. Reuse official reset, registration, action, and grading
semantics; keep contracts, policy, verification, recovery, trace, and
diagnostics inside Affordance Runtime.

The pinned `browsergym-miniwob==0.14.3` package requires Playwright 1.44 while
the default runtime profile uses Playwright 1.61. Run it in an isolated Python
3.11/3.12 environment via the `browsergym` extra. The bridge accepts only a
typed action whitelist and an external JSON-lines policy process; arbitrary
BrowserGym Python action code is not a valid Action Contract. The one-task CI
bridge smoke validates integration only and is never reported as an official
benchmark score.

Official unmodified results and harness fault-injection results are separate
tracks. A high official score must not hide safety or verification failures,
and injected tasks must not be presented as leaderboard scores.

## Replay Levels

1. Offline evidence replay: inspect trace events, screenshots, receipts, DOM
   hashes, and verifier outputs without reopening the environment.
2. Semantic replay: rerun the same task in a resettable local environment and
   compare postconditions rather than exact coordinates.
3. Live best-effort replay: rerun against a live site where content and layout
   may drift; treat this as debugging evidence, not a deterministic grade.

## Acceptance Gate

A runtime release or evolution artifact can be accepted only when it passes:

- the original failed trace or fixture,
- the task family regression suite,
- safety and approval checks,
- trace schema validation,
- the small global smoke suite.

Failed or partially supported artifacts stay quarantined in the evolution
registry with negative examples and rollback notes.

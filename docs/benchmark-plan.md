# Benchmark Plan

Affordance Runtime should be evaluated as a GUI execution runtime, not only as
a browser task solver. The benchmark asks whether the runtime can bind actions
to current environment state, avoid unsafe side effects, verify effects, recover
from drift, and turn failures into regression-gated harness improvements.

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
| MiniWoB++ | atomic action sanity | future | randomized layout | task oracle |
| WebArena-style Mock | long-horizon web workflow | future | distractors, multi-tab state | programmatic verifier |
| Visual Grounding | SoM and screenshot fallback | future | similar labels, layout shifts | mark-level target match |
| Device/WoT | non-web affordance proof | future | stale device state, rate limit | state source receipt |

Visual tasks should avoid vague labels such as `vibe` unless the oracle can be
programmed. Prefer concrete targets such as color, icon, badge, relative
position, or fixture mark id.

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

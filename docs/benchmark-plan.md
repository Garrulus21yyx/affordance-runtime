# Benchmark Plan

Affordance Runtime should be evaluated as a GUI execution runtime, not only as
a browser task solver. The benchmark asks whether the runtime can bind actions
to current environment state, avoid unsafe side effects, verify effects, recover
from drift, and turn failures into regression-gated harness improvements.

## MVP Benchmark Matrix

| Suite | Purpose | Example task | Perturbations | Oracle |
| --- | --- | --- | --- | --- |
| Local SaaS Ops | Resume-friendly end-to-end demo | Extract pricing limits with screenshots and URLs | async loading, lazy content | structured evidence required |
| Reversible Settings | Controlled write path | Toggle notification setting and verify persistence | modal, selector drift, stale affordance | API/DOM receipt plus postcondition |
| External Side Effect | Approval and receipt handling | Export report after approval | navigation delay, download race | approval log plus file receipt |
| MiniWoB++ | Atomic action sanity | click/type/select/form tasks | randomized layout | task oracle |
| WebArena-style Mock | Long-horizon web workflow | shopping/email/forum/admin tasks | distractors, multi-tab state | programmatic verifier |
| Visual Grounding | SoM and screenshot fallback | choose item by visual appearance or vibe | similar labels, layout shifts | mark-level target match |
| Device/WoT | Non-web affordance generalization | thermostat/projector/lights | stale device state, rate limit | state source receipt |

## Runtime-Specific Metrics

These are the metrics that differentiate the project from a normal browser-use
wrapper:

- `task_success_rate`: completed tasks / total tasks.
- `constraint_retention_rate`: runs that preserved all task constraints / total
  tasks.
- `stale_action_block_rate`: stale affordance actions rejected by preflight /
  attempted primitive actions.
- `effect_receipt_coverage`: primitive actions with structural receipts /
  attempted primitive actions.
- `verifier_false_accept_rate`: incorrect success judgments / attempted
  primitive actions.
- `unsafe_side_effect_rate`: unsafe side effects / attempted primitive actions.
- `recovery_success_rate`: successful recoveries / recovery attempts.
- `semantic_replay_success_rate`: tasks that replay semantically in resettable
  environments / total tasks.
- `regression_delta`: new accepted score minus previous accepted baseline.
- `cost_per_success`: total runtime cost / successful tasks.

The initial implementation lives in `src/affordance_runtime/benchmarks`.

## Replay Levels

1. Offline evidence replay: inspect trace DAG, screenshots, receipts, DOM
   hashes, and verifier outputs without reopening the environment.
2. Semantic replay: rerun the same task in a resettable local environment and
   compare postconditions rather than exact coordinates.
3. Live best-effort replay: rerun against a live site where content and layout
   may drift; treat this as debugging evidence, not a deterministic grade.

## Acceptance Gate

An evolution artifact can be accepted only when it passes:

- the original failed trace or fixture,
- the task family regression suite,
- safety and approval checks,
- trace schema validation,
- a small global smoke suite.

Failed or partially supported artifacts stay quarantined in the evolution
registry with negative examples and rollback notes.


# M8.2A PR breadth rerun after V-PRB-5A

This run is the clean committed PR breadth rerun after the V-PRB-5A
requested-effect sequence repair.

## Identity

- revision: `0565e2ef3f5d082cdc13652b8ca399a393ef4074`
- output directory: `/tmp/affordance-pr-breadth-0565e2e-20260728-005603`
- profile: `pr`
- planner profile: `strict-generalist`
- selected tasks: `click-button`, `enter-text`, `choose-list`,
  `click-dialog`, `click-button-sequence`, `form-sequence`
- seeds: `0`, `1`
- local provider: Ollama `qwen2.5:7b`
- BrowserGym MiniWoB: `0.14.3`
- Playwright: `1.44.0`
- Python: `/home/yang/.venvs/affordance-browsergym-py312/bin/python`
- working tree clean: `true`
- official_score_claimed: `false`

## Artifacts

- `browsergym-report.json`
  - sha256:
    `bd2e4b213df0e2b031d1257be0e029a6773122d1e3ed5891224a8b0dc7a2414b`
- `matrix-metadata.json`
  - sha256:
    `684d349afadb98ebbc0ac1c0433b1600d0c126986e33ad7a6759caf05b503a19`

## Result

The run is complete and comparable, but remains negative evidence:

- expected: 12
- observed: 12
- missing: 0
- unrun: 0
- invalidated: 0
- batch status: complete
- provider failures: 0 observed in the report's provider/runtime accounting
- official success: 7/12
- official failure: 5/12
- runtime failures: 6/12
- mean official reward: `0.5833333333333334`
- official success rate: `0.5833333333333334`

Failure clusters:

| Cluster | Episodes | Layer |
| --- | ---: | --- |
| `planner_waiting_clarification` | 2: `click-button-sequence` seeds 0 and 1 | INTENT / PLANNING |
| `entry_action_family_unavailable` | 2: `form-sequence` seeds 0 and 1 | INTENT / PLANNING |
| `schema_incompatible` | 1: `click-button:seed-1` | CONTRACT / FIELD_BINDING |
| `planner_proposal_rejected` terminal guard | 1: `enter-text:seed-1` | CONTRACT / FIELD_BINDING |

## Impact of V-PRB-5A

The compiler-local V-PRB-5A repair passed its non-BrowserGym tests, but this
PR breadth rerun does **not** close the button-sequence mechanism. Both
`click-button-sequence` seeds still reach `planner_waiting_clarification`
after one click action.

Trace classification:

- the generated TaskSpec now preserves dependency and terminal boundary:
  `button TWO` depends on `button ONE`, the first obligation is non-terminal,
  and the second is terminal;
- the remaining defect is relation/evidence semantics: both generated
  obligations are still `predicate / is_available` because the provider's
  requested effects use `operation_class=navigation` and targets
  `button ONE` / `button TWO`;
- after clicking ONE, Runtime correctly rejects weak execution/state-delta
  evidence as insufficient independent evidence for the first subgoal;
- the next planner context therefore still exposes active subgoal
  `button ONE is available`, and the model returns an empty clarification.

This means the next V-PRB-5A step should target requested-effect
relation/evidence semantics for clicked/activated effects. It must not repair
the symptom by completing subgoals from `ExecutionReceipt.success`, by
Coordinator special-casing, or by StateKernel auto-advance.

The `form-sequence` action-family failures remain V-PRB-5B. The
`enter-text:seed-1` terminal guard remains V-PRB-6. The new/remaining
`click-button:seed-1` `schema_incompatible` cluster must be classified before
any PR breadth completion claim.

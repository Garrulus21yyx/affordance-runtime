# M8.2A PR breadth rerun after V-PRB-5A clicked navigation repair

This directory records the clean local PR breadth rerun for
`e4795c1f25aeebeda63c715829e188e052acdab5`
(`fix: canonicalize clicked sequence effects`).

## Run identity

- Source revision: `e4795c1f25aeebeda63c715829e188e052acdab5`
- Working tree: clean
- Source tree digest:
  `sha256:c11350365b9295e9ae2f281cf5bc129f0b405f87750bd5f042dc6b34bf163749`
- Evaluation identity digest:
  `sha256:ab01b55958a4942745d0c8faa8a6857357581e56a5d6daaecb2faa57578f1cda`
- Local output directory:
  `/tmp/affordance-pr-breadth-e4795c1-20260728-010712`
- Runtime Python:
  `/home/yang/.venvs/affordance-browsergym-py312/bin/python`
- BrowserGym MiniWoB: `0.14.3`
- Playwright: `1.44.0`
- Model provider/profile: local Ollama `qwen2.5:7b`
- Planner profile: `strict-generalist`
- Matrix: PR profile, six tasks, seeds 0 and 1
- `official_score_claimed`: `false`

## Result

- Expected episodes: 12
- Observed episodes: 12
- Missing / unrun / invalidated: 0 / 0 / 0
- Batch status: complete
- Official reward passed: 8
- Official reward failed: 4
- Runtime verification passed: 7
- Runtime verification failed: 5
- Official success rate / mean reward: `0.6666666666666666`
- Provider failures: none recorded

The run remains negative PR breadth evidence. It is not a promoted score,
nightly result, release claim, or M8.2B completion claim.

## Failure clusters

- `click-button-sequence`, seeds 0 and 1:
  `planner_waiting_clarification`, root layer `INTENT / PLANNING`.
- `form-sequence`, seeds 0 and 1:
  `entry_action_family_unavailable`, root layer `INTENT / PLANNING`.
- `enter-text`, seed 1:
  `planner cannot finish before verifier-backed subgoal completion`,
  root layer `CONTRACT / FIELD_BINDING`.

Compared with the previous clean PR breadth rerun at `0565e2e`,
`click-button:seed-1` no longer appears as `schema_incompatible`.

## V-PRB-5A trace classification

The second V-PRB-5A repair is present in the clean traces:

- `click-button-sequence` now creates `effect / is_completed` obligations for
  `button ONE` and `button TWO`.
- The first obligation remains non-terminal and the second terminal.
- Dependency and terminal boundaries remain Runtime-owned canonical compiler
  output.

The mechanism is still not closed:

- After clicking `button ONE`, Runtime rejects weak
  `last_action_error` and `state_delta_or_terminal` evidence because mandatory
  progress evidence is incomplete.
- `PlannerContextBuilt` still reports active subgoal
  `button ONE is completed`.
- The strict planner then produces `ask_user`, resulting in
  `waiting_clarification`.

The next V-PRB-5A owner is therefore progress evidence / observer-verifier
binding for completed click effects, not provider graph authority, not
Coordinator/StateKernel, and not receipt-driven progress.

## Artifact hashes

```text
64f548a72917dd18a5d375040cec88b4bf6d416a1507d130af27d283009bd843  browsergym-report.json
cb93c89becf900d2c8f6d82e9b5604fb263435b4add1f0188bf5afb26a47f80d  matrix-metadata.json
```

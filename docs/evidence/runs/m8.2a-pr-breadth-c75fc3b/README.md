# M8.2A PR breadth rerun after completed-click progress evidence repair

This directory records the clean local PR breadth rerun for
`c75fc3b32b737180a3bf39d948811ad5e7730724`
(`fix: bind completed click progress evidence`).

## Run identity

- Source revision: `c75fc3b32b737180a3bf39d948811ad5e7730724`
- Working tree: clean
- Source tree digest:
  `sha256:181b87aa96b53ed61f0a4de107ae33db84ef39ea18b54f78ea375e0fca3aea65`
- Evaluation identity digest:
  `sha256:4e18645ef397ecabbe95f8df12db958b1df6086cbb40012792666d761d74f144`
- Local output directory:
  `/tmp/affordance-pr-breadth-c75fc3b-20260728-011621`
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

## V-PRB-5A trace classification

This rerun proved the first completed-click progress evidence repair was still
too narrow:

- `click-button-sequence` still builds the first contract with only
  `evidence:last_action_error` and `state_delta_or_terminal`.
- The expected `observation_metadata(active_control == bid)` active-subgoal
  verifier is absent from the contract.
- The active subgoal context reports `button ONE is completed`, but the active
  subgoal action family is empty in this real path.
- Runtime therefore still rejects weak receipt/state-delta evidence and the
  strict planner asks for clarification.

The next V-PRB-5A repair keeps the same owner but relaxes the declaration
precondition: a present action family must match, but absent action-family
metadata must not prevent a typed `IS_COMPLETED` click outcome with a matching
target from declaring independent post-observation progress evidence.

## Artifact hashes

```text
5c4dd324482a132d28429fdfaf4c2ce196d0db2eb3317f2737b34520f0d64ee1  browsergym-report.json
3bdc66bd1fc1377f9c2e94c5d4fd82063887339ac22752778cddafc071158650  matrix-metadata.json
```

# M8.2A PR breadth rerun after refined completed-click progress repair

This directory records the clean local PR breadth rerun for
`151fbefc3470b7893eb9f92d4b85c75133bd6750`
(`fix: allow completed click progress without action family`).

## Run identity

- Source revision: `151fbefc3470b7893eb9f92d4b85c75133bd6750`
- Working tree: clean
- Source tree digest:
  `sha256:47f69996ff03452e23fa59c136ebec829873d4e7d84ed8fa1cb92c8210a26e25`
- Evaluation identity digest:
  `sha256:fdb88ad7648d97023fbc0dab92cf4ac67f05192aa0fcc8c014ae684a3f1cb785`
- Local output directory:
  `/tmp/affordance-pr-breadth-151fbef-20260728-012127`
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
- Official reward passed: 10
- Official reward failed: 2
- Runtime verification passed: 9
- Runtime verification failed: 3
- Official success rate / mean reward: `0.8333333333333334`
- Provider failures: none recorded

The run remains negative PR breadth evidence because acceptance errors remain.
It is not a promoted score, nightly result, release claim, or M8.2B completion
claim.

## Closed mechanism

V-PRB-5A is closed for this PR breadth matrix:

- `click-button-sequence:seed-0` passed.
- `click-button-sequence:seed-1` passed.
- Each episode executed two click actions and reached Runtime `done`.
- The refined completed-click progress repair allowed typed `IS_COMPLETED`
  click outcomes to declare independent post-observation progress evidence
  even when active action-family metadata is absent.

## Remaining failure clusters

- `form-sequence`, seeds 0 and 1:
  `entry_action_family_unavailable`, root layer `INTENT / PLANNING`.
- `enter-text`, seed 1:
  `planner cannot finish before verifier-backed subgoal completion`,
  root layer `CONTRACT / FIELD_BINDING`.

These remain separate from V-PRB-5A:

- `form-sequence` remains V-PRB-5B entry action-family resolution.
- `enter-text:seed-1` remains V-PRB-6 terminal-completion guard
  classification.

## Artifact hashes

```text
7a76b65b6be817e4afca73562cd5276470f71a06025b1c84d8075e17a459fca4  browsergym-report.json
adb7d7e978a853c5da35c639c8042e57507ad47dae2c9a38c092c22fe1c2b4c0  matrix-metadata.json
```

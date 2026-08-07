# M8.2A PR breadth rerun — `3daf779`

This diagnostic reran the same PR breadth 6-task x 2-seed matrix after the
V-PRB-5B textbox fallback follow-up repair.

## Run identity

- Revision: `3daf779bb8d1b6fb6c4e8a73c31fd00c514668fd`
- Worktree: clean
- Runtime Python: `/home/yang/.venvs/affordance-browsergym-py312/bin/python`
- Python: 3.12.3
- BrowserGym MiniWoB: 0.14.3
- Playwright: 1.44.0
- Model provider: local Ollama
- Model: `qwen2.5:7b`
- Planner profile: `strict-generalist`
- Profile: `pr`
- Seeds: `0`, `1`
- Output directory: `/tmp/affordance-pr-breadth-3daf779-20260728-013951`
- Official score claimed: false
- Evaluation identity digest: `sha256:4569d4d4d8cf46b5462eca4680aa421ba6d0ad32582bf541694a7d3a69f8fce4`

## Result

- Expected episodes: 12
- Observed episodes: 12
- Missing/unrun/invalidated: 0/0/0
- Official reward passed: 10
- Official reward failed: 2
- Runtime failures: 3
- Provider failures: 0
- Rate-limit retries: 0
- Transient retries: 0

## Failure classification

V-PRB-5B is closed for action-family resolution in this matrix:

- the original `form-sequence` `entry_action_family_unavailable` rejection does
  not reproduce;
- `enter-text:seed-0` is restored to an observed pass after textbox
  value-entry inference;
- `form-sequence` now reaches an accepted TaskPlan with `press_key` permitted
  before the strict planner returns an empty `ask_user` proposal.

Remaining failures:

- `form-sequence:seed-0`
- `form-sequence:seed-1`
- `enter-text:seed-1`

The two `form-sequence` failures are now a distinct strict-planner
empty-clarification/proposal-generation issue, not an entry action-family
availability issue. `enter-text:seed-1` remains the separate Runtime terminal
completion guard case. This run remains negative PR breadth evidence and does
not authorize promotion, nightly, release, or an official benchmark score
claim.

## Artifact hashes

```text
7f037e730828f5c45d02173d6b9221f8b9639f6e22c970e164f5d2a214014d3f  browsergym-report.json
ace05c1e278bdd1987177e7b6cd15b58dd21b04ab92058b0cb54ccc900b8a754  matrix-metadata.json
```

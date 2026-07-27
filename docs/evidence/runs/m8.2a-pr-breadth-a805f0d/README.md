# M8.2A PR breadth rerun — `a805f0d`

This diagnostic reran the same PR breadth 6-task x 2-seed matrix after the
V-PRB-5C slider `press_key` empty-clarification repair.

## Run identity

- Revision: `a805f0dfd1b58b76951003b9d12b9561b19d40e1`
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
- Output directory: `/tmp/affordance-pr-breadth-a805f0d-20260728-014828`
- Official score claimed: false
- Evaluation identity digest: `sha256:62c995ed644b3987632c0650c484f440864680440141715006f16addf72bcfd0`

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

This run is negative PR breadth evidence and does not close V-PRB-5C.

The V-PRB-5C repair did enter the real `form-sequence` path: the trace shows
the strict semantic action resolver producing a deterministic `press_key`
proposal for a focused slider with a requested numeric value, and the
corresponding route can verify successfully. The residual failures now occur
after subsequent replan/progress cycles, where the active subgoal has been
normalized to a generic `slider_value has changed` form and the model again
returns an empty `ask_user` proposal.

Remaining failures:

- `form-sequence:seed-0`
- `form-sequence:seed-1`
- `enter-text:seed-1`

The two `form-sequence` failures remain V-PRB-5C, but their next repair must
target the post-replan slider value/progress semantics rather than the already
closed V-PRB-5B action-family availability problem. `enter-text:seed-1` remains
the separate V-PRB-6 Runtime terminal-completion guard case. This run does not
authorize promotion, nightly, release, a fresh diagnostic, or an official
benchmark score claim.

## Artifact hashes

```text
c6c7b62ca23933e4123218262dfb09b63cc490521387cea989c12beb03fc5f0d  browsergym-report.json
202a85e7a060ee63295e02ced09ece7348e72cfc25fd77ae110085aa94adcdc9  matrix-metadata.json
```

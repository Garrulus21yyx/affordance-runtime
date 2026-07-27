# M8.2A PR breadth rerun — `5c7a2ab`

This diagnostic reran the same PR breadth 6-task x 2-seed matrix after the
V-PRB-5B entry action-family resolution repair.

## Run identity

- Revision: `5c7a2abf17c6e15f497cb613856730ddd9080242`
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
- Output directory: `/tmp/affordance-pr-breadth-5c7a2ab-20260728-013253`
- Official score claimed: false
- Evaluation identity digest: `sha256:d3bac2770551205d314804f5937c7d8fff88c78a4cab8d491477bcaa17402d81`

## Result

- Expected episodes: 12
- Observed episodes: 12
- Missing/unrun/invalidated: 0/0/0
- Official reward passed: 8
- Official reward failed: 4
- Runtime failures: 4
- Provider failures: 0
- Rate-limit retries: 0
- Transient retries: 0

## Failure classification

The prior V-PRB-5B `entry_action_family_unavailable` rejection for
`form-sequence` no longer reproduces. Both `form-sequence` episodes now accept
their TaskPlan, expose `press_key` as a permitted action kind, and then fail in
the strict planner proposal layer by producing an empty `ask_user` proposal.

Remaining failures:

- `form-sequence:seed-0`
- `form-sequence:seed-1`
- `enter-text:seed-0`
- `enter-text:seed-1`

All four remaining failures are `planner_waiting_clarification` in
`INTENT / PLANNING`. This is negative PR breadth evidence: the run does not
close the breadth gate and does not authorize promotion, nightly, release, or
an official benchmark score claim.

## Artifact hashes

```text
bafb6c409351218c9b117f5f55a9438c5148c3a690f9057b530f63075b778a22  browsergym-report.json
4255606fb169ebe17dc4064390c35cbb91224b1847066a1ce372b0676ed28021  matrix-metadata.json
```

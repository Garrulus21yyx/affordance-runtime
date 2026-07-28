# M8.2A PR breadth rerun — `9c1b58c`

This diagnostic reran the same PR breadth 6-task x 2-seed matrix after the
second V-PRB-5C verified-form follow-up repair.

## Run identity

- Revision: `9c1b58c33f20e2690221516a953ce96f910ef2d3`
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
- Output directory: `/tmp/affordance-pr-breadth-9c1b58c-20260728-020037`
- Official score claimed: false
- Evaluation identity digest: `sha256:82db36259f0c2d81cc0b29bad028961e2cd545b9ad7c89dd4dbb1450c04ccfd4`

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

The second V-PRB-5C repair changed the `form-sequence:seed-0` trace by
advancing from the verified slider effect to the requested third checkbox. The
episode then stopped at empty clarification before terminal submit. The
`form-sequence:seed-1` trace still repeatedly emitted slider `press_key`
actions through the negative target boundary and then stopped at clarification.

Remaining failures:

- `form-sequence:seed-0`
- `form-sequence:seed-1`
- `enter-text:seed-1`

The next V-PRB-5C residual is split more narrowly:

1. terminal submit after verifier-backed requested checkbox completion;
2. negative slider target stop/direction semantics at the requested value.

`enter-text:seed-1` remains the separate V-PRB-6 Runtime terminal-completion
guard case. This run does not authorize promotion, nightly, release, a fresh
diagnostic, or an official benchmark score claim.

## Artifact hashes

```text
bdc0fc89473a027ee2911ebb562515dd989d25a6bb0b3d0c0cc6b6d2abec8e91  browsergym-report.json
6c8ee81d609a0ac82b48eefd78237f0a8c19c2d236f7e939a502324c206cad12  matrix-metadata.json
```

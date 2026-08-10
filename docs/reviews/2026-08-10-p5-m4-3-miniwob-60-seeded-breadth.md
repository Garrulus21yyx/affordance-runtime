# P5-M4.3 — MiniWoB-60 Seeded In-Family Breadth

Status before formal execution: `READY / NOT_RUN`.

## Scope

This profile measures short-horizon breadth inside the pinned MiniWoB family.
The actual BrowserGym 0.14.3 registry is censused and bound by digest. Static
inspection of the reviewed MiniWoB source classifies every registered task as
current-primitives, unsupported-primitives, or unknown before model execution.
Only the current `activate`, `fill`, and `select` candidate pool is eligible.

Selection uses:

```text
sha256("miniwob-60-seeded-breadth.v1" + "\0" + task_id)
```

The first 60 `(selection_key, task_id)` entries form the frozen manifest in
`docs/benchmarks/miniwob-60-seed7-v1-manifest.json`. Environment seed 7 does
not influence task selection.

## Execution contract

- `browsergym-miniwob==0.14.3`, reviewed source commit
  `7fd85d71a4b60325c6585396ec4f48377d049838`;
- Mistral `mistral-medium-3-5`, one-stage policy, `format-only.v1`;
- fixed global 7.5-second inter-policy-call pacing;
- seed 7, ten turns, 120 seconds, serial fresh sessions;
- official environment mechanical completion only;
- zero retry, fallback, resume, replay, rerun, backfill, or prompt tuning.

Task success is not campaign evidence validity. A valid campaign needs all 60
typed outcomes, complete measured metrics, a clean exact SHA, consistent report
hashes, clean privacy scan, successful cleanup, and zero safety violations.
Provider and infrastructure failures remain separate from semantic failures.

## Authority boundary

Registry task IDs and capability profiles remain benchmark-private. They do
not enter TaskGoal, AgentContext, model requests, ActionSpace, or Runtime.
Atomic progress cannot resume or skip work. Reports contain no prompt,
response, entered value, oracle, expected answer, reward, hidden state, bid,
selector, coordinate, credential, URL, or endpoint.

## Interpretation

The only formal classification is
`MINIWOB_60_SEEDED_BREADTH_PROFILE`. It is one-seed evidence within one
synthetic benchmark family. GUI generalization, seed robustness, full MiniWoB,
long-horizon planning, multi-tab, visual-only, desktop, WebArena, WorkArena,
and OSWorld capabilities are not claimed. Dynamic run results remain in the
external `/tmp` evidence tree and final operational report, not this document.

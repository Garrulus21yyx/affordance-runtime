# Runtime R7 Target-Scoped Perception Diagnostic Evidence

Date: 2026-07-22

Status: first frozen-nightly cycle analyzed; a generic incremental-control
repair is validated diagnostically and must run a new clean verification ladder.

## Frozen pre-repair evidence

The first R7 sweep ran from clean commit
`a0d81252d109bd6792475bb22e1f38ce3c4886ce`, source-tree digest
`sha256:4843c6cc00d0a778e8f0f426812fe82027e2756419269daae450c211784da147`,
with Python 3.12, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0, local
`qwen2.5:7b`, prompt `generalist-planner-v59`, and the fixed
165/10/15/15 episode/model-call budget.

| Layer | Artifact | Result |
| --- | --- | --- |
| Smoke | `artifacts/runtime-r7-a0d8125-smoke-20260722` | 6/6, mean official reward 1.0, 8 model calls, zero provider/retry/runtime failures |
| PR gate | `artifacts/runtime-r7-a0d8125-pr-20260722` | 18/18, mean official reward 1.0, seed-major order, 24 model calls, zero provider/retry/runtime failures |
| Diagnostic sweep | `artifacts/runtime-r7-a0d8125-diagnostic-seed0-20260722` | complete 30/30 observation, 23/30 success, no circuit break, 43 model calls, zero provider/retry failures |

The complete diagnostic retained all seven failures instead of repairing while
the batch was running: `circle-center`, `copy-paste`, `drag-box`, `drag-items`,
`drag-sort-numbers`, `scroll-text-2`, and `text-transform`. Every failure ended
at `required_evidence_missing`. The generated envelopes grouped them by action
family, while trace inspection identified one shared Runtime route-contract
cause.

## Root-layer decision

Task/subgoal `PerceptionRequirements` correctly describe what a coherent
observation epoch may need to acquire. They were incorrectly reused unchanged
as the hard evidence requirements for every later semantic target. Therefore a
spatial or visual need belonging to one target could reject a later ordinary
button, textbox, scroll handle, or DOM drag endpoint.

The correction is target scoped:

```text
task/subgoal
  -> coherent-epoch acquisition requirements
planner proposal + resolved semantic target
  -> route-specific evidence projection
candidate hard gates
  -> selected route and fresh contract
```

`POINT_ACTIVATE` retains spatial and visual evidence. `DRAG` retains spatial
evidence. A target with visual semantics, candidate evidence, or an explicitly
visual current subgoal retains visual evidence. An unrelated ordinary target
falls back to structural/textual evidence without weakening authoritative
device/API source restrictions. Opaque current drag/drop handles provide a
spatial binding without falsely claiming visual appearance.

This is a shared Runtime repair. The implementation contains no task id,
MiniWoB family name, selector, bid, coordinate, provider, or benchmark-result
branch. Non-BrowserGym tests cover visual fallback and authoritative WoT source
selection, so success is not defined solely by the seven benchmark examples.

## Repair diagnostics before freezing

The first uncommitted implementation iteration produced:

- failure reproduction: `artifacts/runtime-r7-route-requirements-repro-20260722`,
  7/7, mean official reward 1.0, DOM and SVG routes, zero provider/retry/runtime
  failures;
- corresponding families: `artifacts/runtime-r7-route-requirements-family-7x10-20260722`,
  seed-major 70/70, mean official reward 1.0, 148 routes across DOM and SVG,
  zero provider/retry/runtime failures;
- repository gates after the completed generic projection semantics: 470 tests,
  Ruff, mypy across 77 source files, and `git diff --check` pass.

Both benchmark runs above have `working_tree_clean=false`; they establish
diagnostic plausibility only. They cannot be promoted to an immutable score or
nightly result. The next gate is to commit the generic repair and restart the
verification ladder from that clean SHA.

## Clean post-repair ladder and frozen nightly

The target-scoped repair was frozen at
`f8001d9f0f15313ff23dad18bd3cea7f5ee681cd`, source-tree digest
`sha256:f3f8e6510eb9373bce22862e4dc04d614690666214cda845ccf58fc1aa9093f3`.
All runs below recorded `working_tree_clean=true` and retained the same model,
Prompt, schema, context policy, source revision, and 165/10/15/15 budget.

| Layer | Artifact | Result |
| --- | --- | --- |
| Smoke | `artifacts/runtime-r7-f8001d9-smoke-20260722` | 6/6, reward 1.0, zero provider/retry/runtime failures |
| PR gate | `artifacts/runtime-r7-f8001d9-pr-20260722` | seed-major 18/18, reward 1.0, zero provider/retry/runtime failures |
| Diagnostic sweep | `artifacts/runtime-r7-f8001d9-diagnostic-seed0-20260722` | complete 30/30, reward 1.0, DOM/SVG point and drag coverage, no failure envelopes |
| Frozen nightly | `artifacts/runtime-r7-f8001d9-nightly-30x10-20260722` | complete 300/300 observations, 298/300 success, mean reward 0.993333, no circuit break |

The nightly retained two failures, both in one semantic action family:
`use-slider` seeds 4 and 6. Provider failures, rate-limit retries, transient
retries, schema failures, missing artifacts, and version drift were all zero.
The other 29 tasks completed 10/10.

Trace comparison showed that every issued action and every postcondition passed.
Seed 4 needed to move an observed numeric control from 13 to 68; seed 6 needed
to move from 79 to 26. The typed incremental-control compiler emitted one
`ArrowRight` or `ArrowLeft` step per verified observation, so both reached the
50-effect budget before the target. The report labeled the terminal state
`EXECUTION/execution_failed`, but the causal root is a generic planning/action
granularity mismatch, not a backend dispatch failure.

## Generic bounded-step repair

The existing generic constraint path already chose `PageUp` or `PageDown` when
the numeric distance exceeded 20, but the typed compiler independently emitted
only arrow steps. Both paths now use the same backend-neutral bounded-step
selection function:

- distance greater than 20: one `PageUp` or `PageDown` semantic key action;
- remaining distance at most 20: one `ArrowRight` or `ArrowLeft` action;
- after every action: reacquire the control value and require a fresh state
  transition before selecting another step.

This does not raise budgets, batch raw backend calls, write the desired value,
or branch on a benchmark/task/seed. It improves any observed numeric incremental
control whose distance would otherwise exceed the Runtime action budget.

Dirty-tree verification is intentionally non-promotable:

- `artifacts/runtime-r7-incremental-page-step-repro-7-20260722`: seeds 0-6,
  including both frozen-nightly failures, pass 7/7; seed 4 completes in 18
  verified actions and seed 6 in 16;
- `artifacts/runtime-r7-incremental-page-step-family-10-20260722`: 10/10,
  reward 1.0, zero provider/retry/runtime failures;
- full repository gates: 471 tests, Ruff, mypy across 77 source files,
  `git diff --check`, and added-line benchmark-boundary scan pass.

Because code changed after the `f8001d9` nightly, `--resume` is prohibited. The
next revision must use a new output directory and repeat smoke, PR, cross-family
diagnostic, and 30 x 10 frozen nightly.

## Boundary result

- No prompt was changed.
- No provider/model behavior was changed.
- No benchmark task or family dispatch was added to shared Runtime code.
- The seven failures remain in the original clean diagnostic report.
- A new clean post-incremental-repair diagnostic and frozen nightly remain
  mandatory.

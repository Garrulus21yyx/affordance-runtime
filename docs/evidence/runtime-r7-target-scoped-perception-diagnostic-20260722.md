# Runtime R7 Target-Scoped Perception Diagnostic Evidence

Date: 2026-07-22

Status: diagnostic repair evidence; a clean post-repair revision must still run
the smoke, PR, breadth diagnostic, and frozen-nightly ladder.

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

## Boundary result

- No prompt was changed.
- No provider/model behavior was changed.
- No benchmark task or family dispatch was added to shared Runtime code.
- The seven failures remain in the original clean diagnostic report.
- A clean post-repair diagnostic and frozen nightly remain mandatory.


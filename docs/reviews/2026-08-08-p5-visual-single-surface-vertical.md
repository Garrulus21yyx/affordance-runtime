# P5-B3/C2 Visual-only low-risk positive vertical

> **Lifecycle:** IMPLEMENTATION RECORD
> **Semantic authority:** false
> **Branch:** `codex/migrate-world-interaction-capabilities`
> **Start SHA:** `b14e6fbbafc83f4e163bdada4a4e3750010f6a84`
> **Final revision:** the commit containing this record; exact pushed SHA is reported by Git and the final task report
> **Date:** 2026-08-08

## Result

```text
DOM_single_surface_vertical: CLOSED
Visual_single_surface_vertical: CLOSED
WoT_single_surface_vertical: NOT_STARTED
DOM_Visual_adapter_only_equivalence: PROVEN
semantic_fusion: NOT_STARTED
P5_D_confirmation: NOT_STARTED
external_benchmark: BLOCKED
default_cutover: NOT_READY
```

This non-default slice stopped after the Visual-only proof. It did not add WoT,
DOM+Visual fusion, full confirmation continuation, ActionBatch integration,
external benchmark execution, or transaction/event-platform capability. The
old default Coordinator/StateKernel/RuntimeCommitter path is unchanged.

## V0–V4 closure

- **V0:** MEDIUM/HIGH task risk is a confirmation floor; READ_ONLY cannot
  execute an effect. Result lineage is checked before `NOT_SENT` handling.
  `BoundActionRequest` retains intent, selection, schema, effect, risk, barrier,
  and eligible-binding identity.
- **V1:** immutable `VisualFrame`, `VisualViewport`, and
  `VisualRegionBinding` project into the existing World contracts. Only
  `point_activate → activate` is executable; unsupported Visual primitives
  retain targets without bindings.
- **V2:** `VisualSurfaceAdapter` observes through the typed proposer port,
  creates semantic targets/private bindings, probes once immediately before
  execution, and emits exactly one `click_xy`. It has no DOM fallback.
- **V3:** real Chromium Visual-only loop completed using the same task factory,
  policy class, action evaluator, task evaluator, and semantic action as DOM.
- **V4:** policy injection, missing action, premature Finish, stale identity,
  transform/region changes, effect legality, task-risk floor, unchanged state,
  result uncertainty, and no-replay behavior are covered.

## Owner map

| Concern | Canonical owner | Input | Output / replaced owner |
|---|---|---|---|
| task risk floor | `agent/loop.py::_admit_selection` | task + offered option | waiting/block result; no surface branch |
| request invariants | `execution/contracts.py` | admitted selection + binding | fail-closed construction |
| screenshot/viewport/region values | `surfaces/visual/contracts.py` | capture + typed region | surface-local values; no second World model |
| Visual orchestration | `surfaces/visual/adapter.py` | task + browser + proposer | ordinary SurfaceObservation/ActionResult |
| currentness | `surfaces/visual/currentness.py` | bound and live regions | boolean currentness |
| pointer primitive | `surfaces/visual/execution.py` | private current point | one `click_xy` |
| semantic classification | `world/action_classification.py` | task + role + action | Runtime effect/risk/barrier |

## Private binding and currentness

Policy-visible World data excludes raw coordinates, bbox, viewport transform,
scroll, DPR, zoom, orientation, pointer primitive, BrowserSession, and executor
objects. The private binding retains screenshot ref/digest, image dimensions,
viewport dimensions, scroll, DPR, zoom, orientation, region ID/fingerprint,
bbox, action point, source identity, revision, executor, and primitive.

One Visual currentness probe is one `capture_visual_frame` call during execute.
It captures screenshot bytes plus viewport facts and is counted separately from
full observations. The current region is proposed again from that screenshot
through the same typed port. Any screenshot, image dimension, viewport, scroll,
DPR, zoom, orientation, or region-fingerprint mismatch returns `NOT_SENT /
STALE_BINDING` with zero pointer calls. A point outside the viewport returns
`NOT_SENT / INVALID_PARAMETERS`. Pointer invocation uncertainty returns
`SENT_UNKNOWN` and is never implicitly replayed.

The full-digest check is intentionally conservative for this stable fixture;
bounded-region visual diffing remains future work. Generic business-effect
classification remains `LIMITED` to the coarse/single-effect fallback.

## Positive metrics and shared proof

```text
TaskGoal factory: shared_state_task
Policy: FirstOfferedActionPolicy
ActionEvaluator: SharedStateActionEvaluator
TaskEvaluator: SharedStateTaskEvaluator
semantic action: activate
registered adapters in Visual proof: visual only
status: DONE
full observations: 2
executions: 1
currentness probes: 1
turns: 1
DOM selector/click accesses: 0
raw coordinates in policy: 0
completion owner: TaskEvaluator
```

The fixture proposer reads only screenshot bytes and instruction from
`VisualRegionProposalRequest`; it does not read a selector, hidden target ID,
task ID, expected answer, DOM adapter, or test oracle.

## Negative and containment evidence

The matrix rejects policy `x`, `y`, `bbox`, `coordinate`, `backend`, `selector`,
and `point` parameters before execution. It also covers source replacement,
reset, screenshot and every viewport transform field, nondeterministic region
fingerprint, forbidden/unallowed effects, higher-confidence forbidden route,
MEDIUM/HIGH confirmation, successful transport without completion,
lineage mismatch, confirmed `SENT_UNKNOWN`, and unresolved `SENT_UNKNOWN`.

```text
visual adapter: 188 lines
visual contracts: 182 lines
visual currentness: 18 lines
visual execution: 19 lines
functions over 80 lines: 0
Visual imports AgentLoop: no
agent imports Visual adapter: no
Visual currentness imports DOM: no
Visual production imports benchmark fixtures: no
```

## Verification

Evidence is scoped to the final working tree of this record. Exact final
command outcomes are:

```text
pytest -q: 1170 passed
pytest -q tests/test_dom_agent_loop_e2e.py -vv: passed
pytest -q tests/test_visual_surface_adapter.py -vv: passed
pytest -q tests/test_visual_agent_loop_e2e.py -vv: passed
pytest -q tests/test_target_core_boundaries.py -vv: passed
pytest -q tests/test_local_benchmark_mainline.py::test_settings_recovery_blocks_stale_dispatch_then_retries_verified_absence --runxfail: passed
ruff check src tests: passed
mypy src: passed
git diff --check: passed
docker compose -f environments/smart_room/docker-compose.yml config: passed
external benchmark commands: not run
```

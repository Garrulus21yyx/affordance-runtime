# Runtime-first R3 Generic Perception Evidence — 2026-07-22

## Scope

This slice closes the generic Runtime perception path without adding task-family
conditions to Core, Coordinator, planning, grounding, routing, recovery, or the
generic browser observer. BrowserGym action syntax remains in its adapter.

Implemented Runtime behavior:

- `TaskSpec` plus the active typed `SubgoalSpec` derives bounded
  `PerceptionRequirements` and semantic task terms;
- Coordinator passes those requirements through the normal `BrowserSession`
  capture path independently of whether an `ArtifactStore` is configured;
- one coherent observation epoch can contain DOM, bounded accessibility data,
  SVG geometry, screenshot data, visual regions, typed candidates, leases,
  fingerprints, and property-specific `SourceAssertion` values;
- `GenericPerceptionOrchestrator` calls a bounded `VisualRegionProposerPort` and
  BrowserSession converts the result to current visual grounding candidates;
- generic `ContractBuilder` delegates semantic `POINT_ACTIVATE` geometry to the
  trusted `VisualContractBinder`; planners never receive or author coordinates;
- `capture_targeted` creates a new epoch and screenshot reference instead of
  refreshing an old candidate or contract;
- a failed grounding route with explicit `dispatched=False` is excluded by the
  generic recovery policy; the next capture can widen from DOM/accessibility to
  independent SVG/visual evidence;
- ordinary BrowserGym point-region observation now reuses the generic
  orchestrator; drag geometry normalization, backend action encoding, and
  compatibility fallback helpers remain inside the adapter.

## Non-BrowserGym acceptance evidence

`tests/test_generic_perception_coordinator.py` runs three complete Coordinator
paths through `BrowserSession`, semantic proposals, `ContractBuilder`,
`VisualExecutor`, post-action observation, and independent verification:

1. a visual-primary canvas task succeeds from a task-derived visual candidate;
2. a plain DOM-primary task makes no initial visual call, fails before dispatch,
   excludes the DOM candidate, captures a new visual epoch, binds a fresh visual
   route, and succeeds.
3. conflicting SVG and visual position assertions produce bounded targeted
   perception, a new epoch, and an explicit safe-inconclusive result without
   dispatch when disagreement remains.

`tests/test_browser_session.py` additionally proves that old visual candidates
are stale in the new epoch.

## Real Chromium proof

A local Python 3.12 run used the public `BrowserSession.launch` injection
boundary with an in-memory `data:` page containing a canvas and independently
observable DOM status:

~~~text
task: Activate the blue canvas target
browser: Chromium 125.0.6422.26
runtime status: done
selected route source: visual
visual region calls: 4 coherent captures
dispatched actions: 1
planner-authored coordinates/selectors/bids: 0
independent verifier: visible DOM status contains `activated`
result: {"activated": true}
~~~

The four region calls correspond to the initial, preflight, post-action, and
final current-state captures of a task that explicitly requires visual evidence;
plain structured tasks retain a zero visual-model budget.

## Verification

Fixed environment:

~~~text
/home/yang/.venvs/affordance-browsergym-py312/bin/python
Python 3.12.3
~~~

Results after the R3 changes:

~~~text
pytest: 433 passed
ruff check src tests: passed
mypy --ignore-missing-imports src/affordance_runtime:
  success, 73 source files
BrowserGym focused regression: 59 passed
~~~

The repository-wide `ruff format --check src tests` baseline is not a usable
gate because 60 untouched files predate formatter normalization; all files
changed by this slice are formatted.

## Remaining work

R3's Runtime exit scenarios are satisfied. BrowserGym now delegates visual
candidate generation to the generic orchestrator; adapter-local drag geometry
normalization, backend action encoding, and compatibility fallback helpers are
tracked with R5 de-specialization. R4 target-specific calibration and R5
shared-module cleanup remain open; this evidence does not claim M8.5 completion
or a new benchmark score.

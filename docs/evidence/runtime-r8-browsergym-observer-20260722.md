# Runtime R8 BrowserGym Observer Containment Evidence

Date: 2026-07-22

Status: BrowserGym observer slice complete; R8 remains in progress.

## Boundary

`benchmarks/browsergym_observer.py` now owns the complete BrowserGym
observation adapter component:

- coherent `BrowserSession.capture` with the existing two-attempt epoch-drift
  bound and immediate propagation of unrelated failures;
- screenshot path sequencing and BrowserGym episode metadata normalization;
- drag/drop bounding-box enrichment, sortable position and relative geometry,
  and fingerprint refresh;
- regeneration of DOM/accessibility grounding candidates after geometry changes;
- screenshot-bound visual fallback target creation;
- fusion of adapter-produced visual affordances into unified candidates;
- recursive JSON-safe conversion for adapter metadata.

The adapter backend identifier now has one owner in `browsergym_types.py` and is
re-exported by the bridge. `browsergym.py` remains the compatibility facade and
continues to expose `BrowserGymObserver`, `_visual_fallback_affordance`,
`_refresh_dom_grounding_candidates`, `_fuse_visual_candidates`, and
`_json_safe`. Existing callers therefore keep their import surface while the
implementation has a cohesive owner.

No generic perception, grounding, routing, Coordinator, StateKernel, planner,
contract, executor, episode scheduling, circuit breaker, checkpoint, resume,
CLI, or report code moved into this adapter module. No task or action-family
dispatch was added. BrowserGym-specific metadata and backend identity remain
inside `benchmarks/`.

## Adapter evidence

Direct and facade-level tests prove:

- facade symbols are the extracted implementation objects;
- coherent epoch drift retries once and then fails on the second attempt;
- an unrelated capture failure propagates after one attempt;
- episode metadata records the successful capture attempt;
- drag geometry updates locator boxes, target fingerprints, and grounding
  candidate fingerprints coherently;
- relative-size and containment facts derive from current geometry;
- screenshot fallback identity follows page revision and image bytes rather
  than artifact filename and contains no model-authored coordinate;
- fused visual affordances retain a current grounding candidate;
- nested non-JSON values are converted recursively without being interpreted.

The BrowserGym bridge fell from 2,197 to 1,890 lines. The extracted observer is
338 lines. This is an ownership change, not a benchmark behavior change.

No real benchmark episode was run for this containment slice. Adapter
conformance and full Runtime tests are the relevant evidence; benchmark reward
would neither prove nor replace the ownership boundary.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused observer, adapter, launcher, runtime, adaptive-metric, and boundary
  tests: 76 passed;
- full repository tests: 498 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 85 source files: passed;
- `git diff --check`: passed.

## Remaining R8 work

- extract BrowserGym action/gesture/point encoding while keeping semantic
  gesture validation in Runtime Core;
- split episode runner/process isolation from suite scheduling/checkpointing;
- isolate report aggregation and retain the exact public report schema;
- migrate selected bindings toward tagged payloads and finish the ownership and
  trace-schema audit.

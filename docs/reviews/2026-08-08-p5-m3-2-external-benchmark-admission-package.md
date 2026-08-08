# P5-M3.2 external benchmark admission package

## Scope and baseline

- start SHA: `d44066571e740927f8942341b2855fb3309facbf`
- commits: `a99f408`, `c8a4a34`, `33c72e5`, and this documentation/package commit
- default product path: unchanged old Coordinator baseline
- external benchmark run: `NOT_RUN`
- default external admission: `BLOCKED`

This slice closes internal manifest/result/attestation integrity, configures an
exact-head full regression artifact, provides an opt-in live model-policy
attestation, and prepares a reviewed external preflight package. It does not
switch Runtime ownership, create a benchmark platform, or claim model
generalization.

## Internal identity and measurement closure

`auto_confirm`, timeout, status expectations, required measurements, metric
expectations, profile, seed and manifest schema are digest-bound. Callable
implementations remain bound by exact git SHA. `BenchmarkCaseResult` stores
metrics only in `measurements`; acceptance, rates and reports read that mapping.
The inert `acceptance_profile` field was removed.

The internal attestation requires an explicit five-profile run set, a clean
exact tree, one harness schema, accepted runs, exact manifest digests, and exact
equality between `run.json`, `summary.json`, and `cases/*.json`. It records
secret-free report hashes and aggregate forbidden/duplicate/stale safety counts.
Browser and WoT owner threads must be stopped after cleanup.

## Exact-head workflows and live policy

`.github/workflows/target-loop-internal.yml` now runs full collection/full
pytest, Ruff, mypy, diff-check, smart-room Compose config, the required legacy
runxfail, target boundaries and documentation governance before the five
internal profiles. Artifacts are SHA-named:
`target-loop-full-validation-${SHA}` and `target-loop-internal-${SHA}`.
The latest previously reviewed internal workflow at `d440665...` succeeded:
run ID `31279936157`, artifact ID `9028120091`, artifact name
`target-loop-internal-d44066571e740927f8942341b2855fb3309facbf`. The new
full-validation job requires a final-head remote run after push.

The manual live workflow defaults false and uses a protected
`live-model-policy` environment. It composes the existing ModelPort-backed
policy with the internal real DOM task and deterministic mechanical evaluator.
It accepts only a clean exact head, DONE, two observations, one execution, one
provider attempt per policy call, zero retry/fallback and zero safety metrics.
Injected fixtures are test-only and cannot satisfy the live attestation. The
first external manifest is mechanical-only, so a live semantic evaluator is
`NOT_REQUIRED_FOR_FIRST_MECHANICAL_EXTERNAL_MANIFEST`.

## External manifest and boundary

The official `browsergym-miniwob==0.14.3` wheel registry was inspected. The
reviewed `external-smoke-v1` manifest contains only:

- `browsergym/miniwob.click-button`
- `browsergym/miniwob.enter-text`
- `browsergym/miniwob.choose-list`

MiniWoB source remains pinned to
`7fd85d71a4b60325c6585396ec4f48377d049838`. The package is optional under the
`external-smoke` extra. Cases contain no answer, selector, coordinate, hidden
state, successful trajectory, or action script. Native completion is visible
only to a benchmark-only mechanical TaskEvaluator and post-run acceptance.

Admission compares exact SHA, three attestation file digests, complete internal
run set, full CI and live-policy acceptance, manifest digest/schema/version,
clean tree, zero safety counters and optional dependency version. Mechanical
cases do not require a semantic evaluator. The target AgentLoop BrowserGym
`WorldEnvironment` lifecycle wrapper is not yet closed, so
`target_loop_adapter_ready=false` is an explicit admission error. This is
`external adapter package: PARTIAL`, not a placeholder integration claim.

Execution requires all three conditions: admitted evidence,
`RUN_EXTERNAL_SMOKE=1`, and explicit `--execute`. Default preflight constructs
no environment and performs no provider call. WebArena, WorkArena and OSWorld
were not run. No database, scheduler, registry, transaction/event core, retry
platform, or durable conversation store was added.

## Status

- P5-M3 / M3.1: `CLOSED_FOR_INTERNAL_FIXED_MANIFEST`
- remote exact-head internal artifact: `AVAILABLE` for reviewed `d440665...`
- remote exact-head full regression: `WORKFLOW_CONFIGURED`; final run pending
- live model-policy: exact clean-head result recorded in the final task report
- live semantic evaluator: `NOT_REQUIRED_FOR_FIRST_MECHANICAL_EXTERNAL_MANIFEST`
- reviewed external manifest: `READY`
- external adapter package: `PARTIAL`
- external admission checker: `CLOSED`
- external benchmark admission: `BLOCKED`
- external benchmark run: `NOT_RUN`
- default cutover: `NOT_READY`

# P5-M3.1 harness measurement and real-adapter closure

Date: 2026-08-08  
Branch: `codex/migrate-world-interaction-capabilities`  
Start SHA: `47115aae0538f4dacf18ed3fff8d2730655d9cde`

## Status

- P5-M3 harness architecture: `CLOSED`.
- Machine acceptance: `MEASURED_AND_FAIL_CLOSED`.
- Synthetic internal protocol matrix: `ATTESTED` and explicitly labelled synthetic.
- Real DOM, Visual-only and WoT adapter harnesses: `ATTESTED_LOCALLY`.
- Local exact-head report attestation: produced after the final clean commit.
- Remote exact-head CI artifact: `UNAVAILABLE` until GitHub runs the committed workflow for that SHA.
- External benchmark: `BLOCKED`; none was run.
- Default cutover: `NOT_READY`; the old Coordinator remains the default path.

## Owner map and authority boundary

`contracts.py` owns immutable measurements, expectations, manifests, run identity
and result contracts. `instrumentation.py` owns per-case mutable counters at
policy, provider, evaluator, confirmation and environment call boundaries.
`runner.py` owns sequential construction, timeout and exactly-once cleanup.
`acceptance.py` compares post-run results against manifest expectations.
`real_adapter_support.py` composes existing production adapters and fixture
resources. `reporting.py` serializes public results; `attestation.py` hashes those
files and exact-tree identity. None of these owners may influence Runtime action
selection, admission, risk, binding, execution or evaluation.

## Correctness closure

Semantic evidence that exists below the required assurance is INCONCLUSIVE, not
NOT_READY. A missing output no longer overwrites criterion UNKNOWN. Measurements
distinguish measured zero, unmeasured and zero opportunities. Required
measurements and EQ/MIN/MAX/ZERO/NONZERO expectations are digest-bound and fail
closed. `execution_completed` reports lifecycle completion; acceptance remains a
separate post-run result.

Stale opportunities and downstream effectful dispatches are counted at the
environment boundary, so stale zero-call is measured rather than assumed.
Provider and semantic-judge attempts count success, failure and timeout at their
ports. Confirmation increments only when a typed `ConfirmationDecision` is
submitted. Duplicate unknown identity includes semantic action, target,
destination, normalized parameters, semantic effects and effective risk; it
excludes observation, binding and route identity.

Environment, composition and loop construction sit inside one protected case
lifecycle. Timeout, exception or cleanup failure rejects that case but does not
stop later cases. Each environment is closed at most once.

## Real-adapter matrix

The DOM case launches Chromium, observes through `DomSurfaceAdapter`, probes
currentness, performs one real click and reobserves. The Visual-only case
registers only `VisualSurfaceAdapter`, proposes from screenshots, probes a fresh
frame and performs one real pointer click. The WoT case fetches a real local TD,
reads the property over HTTP, invokes one action endpoint and re-reads current
state. Typed expectations require two observations, one execution, one probe and
one effectful dispatch, plus exact surface-call counts.

These cases prove adapter/harness integration. They do not prove live-model or
cross-platform generalization and do not perform semantic fusion.

## Reporting, attestation and CI

Serialized-report tests place selector, coordinate, href, credential,
Authorization, raw-response and private-artifact sentinels in harness-owned
objects, write every JSON report, and verify none appears. Attestation records
only relative path, SHA-256 and size for reports plus exact Git SHA/dirty state,
manifest digests, suite/profile identities and acceptance.

`.github/workflows/target-loop-internal.yml` runs focused tests and all fixed
internal profiles without provider secrets, retries, fallback or external
benchmarks. It uploads `target-loop-internal-${GITHUB_SHA}` only after successful
accepted runs and attestation generation.

## Commits and evidence

1. `ffb515c` — `fix: close harness entry and measurement semantics`
2. `c840770` — `refactor: make benchmark acceptance machine verifiable`
3. `76135cb` — `test: run real adapters through target-loop harness`
4. `docs: attest target-loop harness measurements` — this record's commit; its
   exact SHA is reported by final `git log` and bound by the post-commit local
   attestation (a commit cannot contain its own final hash).

The final validation record includes collection/shard equality, full pytest,
Ruff, mypy, diff-check, Docker Compose config, required target regressions and
all final-head CLI profiles. No transaction/event core, registry, database,
scheduler, provider retry/fallback or durable benchmark service was introduced.

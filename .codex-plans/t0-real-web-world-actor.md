# T0 Real-Web World/Actor Convergence Plan

Status: done

## Data Flow / Owners

- BrowserGym raw observation: upstream source evidence, including private BID and source modality coverage.
- BrowserGymSurfaceAdapter: interprets source semantics into public World targets/facts/relations plus private bindings.
- WorldObservation: only current environment authority; no task-directed pruning.
- WorldProjection / ActorWorldSnapshot: deterministic, disposable model projection with structural closure and truthful coverage.
- compact_ax.v1: text renderer for the Actor projection; no new facts or bindings.
- ActionSpace / PerTurnToolCatalog: only current action-callability authority; tool targets must be conserved in Actor View.
- Trace: audit evidence only; can hold typed private evidence but never controls behavior.
- TaskEvaluator/native verifier: formal completion authority.

## Steps

- [done] Read AGENTS.md and requested architecture/benchmark sections.
- [done] Classify existing dirty files by owner and inspect production data flow.
- [done] Repair T0 owner gaps in source semantics, Actor projection, catalog conservation, diagnostics, and tests.
- [done] Run focused property/conformance/MiniWoB checks.
- [done] Run W1b-World read-only diagnostics or record typed environment blockers.
- [done] Run full `pytest -q`, Ruff, and `git diff --check`.
- [done] Update architecture/benchmark/evidence status and perform fresh-context audit.
- [done] Commit and push only T0-owned changes if dirty scope is safe.

## Evidence

- Focused tests: `66 passed`, `65 passed`, BrowserGym fixed-python conformance `14 passed`, MiniWoB Like context set `54 passed`.
- W1b-World diagnostic artifact: `evidence/w1b-world-t0/w1b-world-summary.json`, ready=true, six site categories passed.
- Full test/Ruff/diff-check: `1253 passed, 18 skipped`; `ruff check src tests` passed; `git diff --check`
  passed.
- Bounded fresh-context audit: no T1 execution path or model-visible private leakage found in T0 diff; evidence
  summary reports zero leaks and zero structural-closure violations.
- Commit/push: `740f9a24` pushed to `origin/codex/simplify-core-runtime`.

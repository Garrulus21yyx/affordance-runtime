# T3.2 contract convergence plan

Status: complete
Branch: `codex/simplify-core-runtime`
Started: 2026-08-20
Scope: provider-free convergence of single-turn delivery, single-tool-call protocol, Supervisor routing, and Auditor role contract.

## Baseline (before this increment)

- Worktree was already dirty with 50 tracked modified files, 4,976 insertions, and 2,056 deletions.
- Existing untracked paths: `.codex-plans/t32-probe-v2-zhipu46.md`, `output/`, and `tests/unit/agent/test_semantic_delivery.py`.
- All baseline changes are treated as existing T3.2 work. No reset, checkout, overwrite, or cleanup of unrelated changes is authorized.
- Full baseline commands captured in the active task transcript: `git status --short --branch`, `git diff --stat`, `git diff --name-status`, and `git diff --numstat`.
- Required inputs read completely: `AGENTS.md`, `docs/architecture.md`, and `docs/benchmark.md`.

## Work plan

1. [completed] Map current owners and all causal-surface hits for delivery/manifest, provider calls/repair, Supervisor routing, and role payload/schema projection.
2. [completed] Implement one immutable per-turn delivery object and route Context, ToolCatalog, resolver/admission, and trace through its manifest identity; remove duplicate render/ref discovery paths.
3. [completed] Close the single-tool-call wire/runtime protocol, bounded same-episode feedback, protocol-stall routing, and representation-only repair.
4. [completed] Make Supervisor routing total and explicit; only explicit audit boundaries invoke Auditor, and operational failures route without audit.
5. [completed] Split Manager/Auditor/Finalizer input projections and enforce one Auditor output contract without the final-response schema.
6. [completed] Delete superseded helpers, mirrors, diagnostics, fixtures, and tests; update only `docs/architecture.md` and `docs/benchmark.md`.
7. [completed] Run focused/property tests and the six-page provider-free diagnostic; then full pytest, Ruff, diff-check, and repository-wide cleanup searches.
8. [completed] Run an independent bounded fresh-context audit over code/tests/docs and repair any P0/P1/P2 findings.
9. [completed] If and only if every local gate and audit passes, create one coherent commit including existing T3.2 convergence changes and push it. Otherwise leave uncommitted and report the shared cause.

## Explicit non-goals

- No provider call, live benchmark, WebArena task witness, or W2 cohort.
- No SemanticTargetSelector, `fill_form`, arbitrary multi-action execution, action queue, `BoundActionSequence`, VLM fallback, second ActionSpace/Binder/Executor/GUI loop, workflow engine, or benchmark-specific behavior.

## Files modified by this increment

- `.codex-plans/t32-contract-convergence.md` — durable task plan and evidence index.

## Verification evidence

- Focused delivery/protocol/mission/provider transport gate: `110 passed`; post-cleanup focused gate: `125 passed`.
- Full local suite before final audit: `1339 passed, 19 skipped`.
- Ruff: passed. `git diff --check`: passed.
- Six-page provider-free diagnostic: `evidence/w1b-world-t32-contract-convergence-run1/`; `ready=true`, 6/6,
  no acceptance errors, provider-reported prompt tokens 0, and unchanged zero-dispatch recovery checks.
- Live/provider witness: not run, by scope.
- Fresh-context audit: initial P1 found complete `TaskGoal` at the internal Auditor/trace boundary; repaired with typed
  `AuditorTaskProjection`. Re-audit verdict PASS on all five requested questions, no P0/P1/P2.
- Commit/push: `732379b3 refactor: converge T3.2 model-turn contracts` pushed to
  `origin/codex/simplify-core-runtime`.

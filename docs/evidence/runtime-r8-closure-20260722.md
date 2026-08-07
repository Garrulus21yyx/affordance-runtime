# R8 Internal Module Containment Closure

Date: 2026-07-22

## Decision

R8 is complete. The containment work is structural and does not change the R7
release conclusion: M8.2B remains open because the frozen residual release
measured 402/625 successes with 223 retained failures.

## Closed module boundaries

- `TaskPlanLifecycle`, `PerceptionSession`, `ContractExecutionLoop`, and
  `RecoveryHandler` prepare typed/read-only decisions; Coordinator applies all
  task state, budgets, approvals, incidents, receipts, and trace transitions.
- `PlannerContextBuilder`, the declarative default compiler registry, and
  `PlannerModelOrchestrator` separate bounded context, rule metadata, and model
  schema/repair orchestration without changing Prompt or context-policy
  versions.
- BrowserGym observation, backend encoding, one-episode execution/process
  isolation, protocol metadata, FailureEnvelope/report publication, and matrix
  checkpoint/scheduling concerns have explicit adapter-owned modules.
- Compatibility tests bind the original facade names to the extracted objects.

## Ownership audit

An executable architecture test confirms:

- extracted Core collaborators never construct `StateKernel`;
- full task execution has one authoritative owner, `RunCoordinator`;
- extracted collaborators do not write trace nodes directly;
- Core source outside benchmark adapters/CLI contains no BrowserGym, MiniWoB,
  WorkArena, or WebArena vocabulary and imports no BrowserGym adapter;
- observer, encoder, runner, protocol schedule, FailureEnvelope, and report
  facade identities remain stable.

`AffordanceRuntime.run_contract` in `runtime.py` still constructs a local
`StateKernel` for its backwards-compatible single-contract conformance API. It
does not observe, plan, replan, recover, schedule episodes, or own a full task
run, so it is explicitly non-authoritative rather than silently counted as a
second Coordinator.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

```text
ruff check src tests: passed
mypy --ignore-missing-imports src: passed (89 source files)
pytest -q: 522 passed
git diff --check: passed
```

No GitHub Action or benchmark episode was run. The `.env` file was not read,
printed, staged, or uploaded.

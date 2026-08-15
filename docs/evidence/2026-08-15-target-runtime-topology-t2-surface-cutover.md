# Target Runtime topology T2 — BrowserGym surface cutover

Date: 2026-08-15

Status: `IMPLEMENTED / FOCUSED_VERIFIED / FULL_VERIFIED / LIVE_NOT_RUN`

## Outcome

BrowserGym reusable mechanics now have one production owner:
`surfaces/browsergym`. The benchmark namespace retains only case admission and
task construction, pinned MiniWoB verifier policy, runner/composition policy,
manifests, pacing and reporting. No compatibility import or re-export preserves
the displaced `benchmarks.external_smoke.browsergym_*` paths.

The authority split is:

```text
surfaces/browsergym
  backend lifecycle + acquisition + observation projection
  semantic profile + canonical AX analysis
  private binding + currentness + execution translation
  visual projection/disambiguation
  raw provider task-state snapshot and lineage

benchmarks/external_smoke
  reviewed task admission + benchmark TaskGoal construction
  MiniWoB reward/done success/failure interpretation
  cases + runners + pacing + reports + attestations
```

The reusable `BrowserGymEnvironment.open()` accepts a nonempty provider task ID
without consulting a benchmark manifest and returns only the environment. The
benchmark `open_browsergym_case()` validates the admitted case set, creates the
TaskGoal, and wraps the surface with benchmark verifier counters. This is a
single directed dependency from benchmark policy to surface implementation.

## Physical moves and deletions

The following old benchmark-owned implementation files were deleted after all
consumers switched:

- `browsergym_acquisition.py`
- `browsergym_backend.py`
- `browsergym_binding.py`
- `browsergym_currentness.py`
- `browsergym_diagnostics.py`
- `browsergym_entity_identity.py`
- `browsergym_environment.py`
- `browsergym_execution.py`
- `browsergym_inventory.py`
- `browsergym_projection.py`
- `browsergym_semantic_profile.py`
- `browsergym_semantics.py`
- `browsergym_visual_disambiguation.py`
- `browsergym_visual_projection.py`

Their retained behavior moved to owner-named modules below
`surfaces/browsergym`. The compatibility-only
`browsergym_action_evaluator.py` was deleted; consumers use
`ProductionActionEvaluator` directly. The former combined verifier moved to
benchmark `verifier_policy.py` only after raw task-state capture and projection
were extracted into surface `task_state.py`. The former combined benchmark
`environment.py` became `case_environment.py` after the generic WorldEnvironment
moved to the surface.

## Consumer cutover

Switched consumers include:

- external-smoke adapter conformance, live runner, reporting and CLI;
- external-breadth runner, coverage probe and targeted semantic inventory;
- all BrowserGym surface/currentness/execution/projection/visual tests;
- grounded-tools and interaction-capability conformance tests;
- import-order, semantic-inventory, set-objective and target-topology lexical
  architecture tests.

Architecture tests prove that no `browsergym_*.py` implementation remains in
the active benchmark package, no BrowserGym surface module imports a benchmark,
the benchmark package defines none of the environment/backend/binding/
projection/execution owners, and the surface cannot own reviewed task admission
or MiniWoB verifier interpretation.

## Preserved benchmark policy

The following are intentionally benchmark-owned and are not a second surface or
Runtime authority:

- reviewed MiniWoB task IDs and manifest/package attestation;
- task-specific loop budgets and benchmark TaskGoal construction;
- the pinned RESET/POST_ACTION/READ_ONLY_PROBE reward/done truth table;
- official verifier query/success counters;
- runner pacing, case classification, report and attestation formats.

They consume raw immutable surface task-state snapshots and the public target
Runtime ports. They do not create ActionBinding, ActionSpace membership,
admission, binding, execution, observation or evaluator fallback paths.

## Verification

- surface/semantic/model focused: `150 passed`;
- surface + benchmark + architecture focused: `192 passed, 18 skipped`;
- external-smoke/external-breadth/architecture: `141 passed, 7 skipped`;
- full pytest: `2539 passed, 27 skipped`;
- Ruff: passed;
- mypy: 504 source files passed;
- wheel build, package/import and removed-path negative checks: passed;
- product CLI/package entrypoints: passed;
- `git diff --check`: passed;
- live benchmark: not run, as required for this topology-only slice.

## Still open

T2 does not delete the staged Coordinator/Runtime/planning/recovery clusters;
that is T3. It does not close StateFact or effect authority, enable a new
interaction action, or make a benchmark/generalization claim. World-graph A.1
and new capability work remain blocked by the topology plan's T3 minimum gate.

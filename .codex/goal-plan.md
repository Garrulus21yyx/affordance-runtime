# Active Goal Execution Plan

Goal: advance Affordance Runtime under the current implementation plan and all
normative boundaries, with no benchmark-specialized behavior or unsupported
delivery claims.

## Constraints

- `docs/current-implementation-plan.md` is authoritative for current scope.
- Preserve Runtime-first, responsibility-containment, benchmark-governance, and
  intent-schema authority boundaries.
- Apply the horizontal architecture-governance track to every active milestone:
  growth and dependency/authority gates are synchronous change-admission gates,
  not a repository-wide rewrite prerequisite.
- The normative track is `docs/architecture-governance-track.md`; this plan
  records execution progress but does not redefine its admission semantics.
- M8.2A SG1-SG6 are locally complete. SG7 remains the next vertical intake/
  benchmark step when authorized; Coordinator containment proceeds as a
  parallel horizontal track and is not a unified-refactor prerequisite.
- Keep the three-call intake ceiling and fail closed on unsupported authority.

## Steps

1. `done` — Read authoritative plans, governance records, and repository state.
2. `done` — SG3 completed for model and parent semantic proposals: proposal
   graph IDs are untrusted, source bindings are validated, and Runtime derives
   the IDs that cross into `TaskSpec`.
3. `done` — Added regression coverage for normalized reviewer inputs and
   Runtime-owned graph IDs through the single- and multi-stage pipeline.
4. `done` — Dedicated Python 3.12 BrowserGym environment passes the full local
   quality gate (921 tests, Ruff, mypy, and diff check).
5. `done` — SG4 deterministic source-to-claim-to-terminal structural coverage
   is enforced before optional review; a model reviewer has veto-only authority.
6. `done` — SG5 canonical graph replacement: flat effects and bounded
   multi-stage semantic proposals are reconstructed by Runtime-owned compiler
   code; no proposal graph node or free-form evidence text crosses into
   `TaskSpec` directly, and model COMPLETE is advisory-only.
7. `done` — SG6 local gate: non-BrowserGym held-out intake traverses the
   canonical multi-stage boundary, with clause-omission, unknown-source,
   stale-lineage, ambiguity, and audit-veto negative controls.
8. `done` — Normal entrypoints configure concrete context-compaction and
   planner-schema repair owners with validated before/after evidence. Schema
   recovery switches subsequent candidate decoding from the action-only
   initial schema to the existing current-target/value-bound repair schema,
   without changing TaskSpec authority or Prompt identity.
9. `done` — Continued Coordinator responsibility reduction by moving
   `PlannerDecision` and `PlannerPort` into a neutral planning-contract module;
   preserved the public re-export and all existing behavior. Planner
   implementations no longer import Coordinator, and its ratchet falls from
   3520 to 3499 lines.
10. `done` — Moved explicit approval-source protocol/implementation into a
    neutral contract module. CLI and local benchmark entrypoints now consume
    neutral approval and planning contracts directly; Coordinator preserves
    compatibility re-exports while retaining task-execution commit authority.
    The line ratchet falls from 3499 to 3473; known compatibility/skill/progress
    mutation scopes remain explicit horizontal debt rather than precedent.
11. `done` — Activated an independent horizontal architecture-governance
    track in the authoritative plan/status/boundary documents and executable
    tests. Freeze growth at measured control-module/method baselines; enforce
    dependency direction and state/trace authority without blocking unrelated
    milestone work on a unified rewrite.
12. `in_progress` — Select the next named Coordinator responsibility for semantic
    ownership reduction under the horizontal gates. LOC is an auxiliary
    ratchet; the 2,000/1,500 thresholds neither select the slice nor prove it
    complete.

## Change Record

- Created this plan before implementation.
- Modified `src/affordance_runtime/intent_compiler.py` and focused intake/
  pipeline tests. `mypy --ignore-missing-imports src` passes for 112 source
  files; focused tests pass 120/120; full suite passes 909/913 in this
  environment, with the four non-code environment blockers described above.
- Added `ParentSemanticProposalCompiler`; model and parent proposal IDs are
  normalized through the same source-ledger boundary. Focused intake/pipeline
  tests pass 69/69, Ruff, and mypy pass.
- Added deterministic SourceLedger-to-claim-to-obligation-to-terminal coverage
  and made the model coverage auditor veto-only. Focused tests pass 126/126;
  full suite passes 913/917, with the same four environment prerequisite
  failures.
- Extended `CanonicalObligationCompiler` with a generic flat requested-effect
  template that derives terminal relation, typed independent evidence, ids, and
  provenance without proposal graph fields. Focused compiler tests pass 3/3;
  Ruff and mypy pass.
- Migrated the parent flat semantic-proposal entrypoint to that canonical path;
  56 relevant tests, Ruff, and mypy pass.
- Migrated the model flat semantic-proposal entrypoint to the same canonical
  path. Model review COMPLETE cannot grant admission; focused migration,
  coverage, BrowserGym, and pipeline tests pass 35/35, and Ruff/mypy pass.
  The complete suite is 915 passed and four environment-only failures: two
  Chromium tests need Playwright, and two subprocess architecture tests use an
  interpreter without the editable project installed.
- Migrated bounded multi-stage semantic proposals through
  `CanonicalObligationCompiler`; focused compiler/intake/planning tests pass
  116/116, static gates pass, and full suite is 916 passed with the same four
  environment-only failures.
- Added SG6 held-out non-BrowserGym value-flow conformance with adversarial
  omission controls; 16 focused tests and static gates pass.
- Re-ran the complete gate with
  `/home/yang/.venvs/affordance-browsergym-py312/bin/python`: 921 tests,
  Ruff, mypy over 112 source files, and diff check pass.
- Added normal-entrypoint planner-context recovery ownership. Focused recovery
  tests pass 89/89; dedicated full suite passes 922 tests, Ruff, mypy over 113
  source files, and diff check.
- Added normal-entrypoint planner-schema recovery ownership. Focused recovery/
  planner tests pass 160/160; dedicated full suite passes 923 tests, Ruff,
  mypy over 114 source files, and diff check.
- Extracted neutral Planner contracts and added an executable import boundary;
  106 focused tests and the 924-test dedicated full suite pass. Coordinator is
  3499 lines and its line ceiling is lowered accordingly.
- Extracted neutral approval-source contracts and direct entrypoint imports;
  added token-binding/TTL/no-match/order behavior regressions and executable
  neutral-ownership/import/compatibility boundaries. Twenty focused tests and
  the 930-test dedicated full suite pass. Coordinator is 3473 lines and its
  executable ceiling is lowered accordingly.
- Activated the independent horizontal architecture-governance track. Added
  control-module/method growth ratchets, full StateKernel read/mutation API
  classification, extracted-collaborator dependency/authority gates, relative
  import normalization, and legacy benchmark-edge freeze. Eighteen focused
  architecture gates and the 938-test dedicated full suite pass; Ruff, mypy
  over 116 source files, and diff check pass. Existing debt remains explicit
  and does not make a unified rewrite a vertical milestone prerequisite.

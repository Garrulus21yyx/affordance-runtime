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
12. `done` — Calibrate governance against committed revision `627b5f7`:
    remove duplicated live-status authority, separate milestone/evidence/
    promotion/admission/CI axes, record the failed remote CI without treating
    every failure as environmental, scope INV-11 to task-execution commit
    sequencing, and make the vertical/horizontal WIP policy explicit.
13. `done` — Run one vertical slice (SG7 targeted protected-family
    confirmation) beside the already closed H1 active-subgoal horizontal slice.
    The first clean `fa288af` SG7 diagnostic failed 0/4 in INTENT / PLANNING;
    the generic repair was committed as `3d44a9d` and the clean rerun of the
    same 2-task x 2-seed diagnostic passed 4/4. This is SG7 targeted evidence
    only, not PR breadth, nightly/release, or a promoted score. Immutable
    PlanningRequest / PlannerStateView remains the next horizontal boundary and
    must not be mixed into the same evidence identity.
14. `done` — Repair classified CI harness/environment failures without
    hiding the remaining benchmark runtime failure: core pytest invocation and
    BrowserGym provisioning are narrow CI fixes; coherent observation epoch
    drift stays open as the next benchmark diagnostic.
15. `done` — Close the benchmark epoch-drift crash and split diagnostic
    benchmark execution from promotion acceptance: true semantic DOM drift must
    still fail, transient affordance-state stabilization may be recaptured once,
    and release acceptance failures remain visible.
16. `pending` — Re-run the repaired workflow remotely and classify any remaining
    failures against the current diff. Local diagnostic benchmark success is not
    a release/promotion claim while benchmark acceptance remains failed.
17. `done` — Close the H1 active-subgoal hidden-mutation debt in project code:
    make `StateKernel.active_subgoal()` read-only, add explicit
    `activate_next_subgoal()`, keep production activation in Coordinator, and
    remove the planner-context hidden-mutation exception from the architecture
    gate.
18. `done` — Freeze the SG7 generic repair in a clean revision and rerun the
    exact targeted matrix (`enter-date`, `text-transform`, seeds 0 and 1)
    before protected breadth, PR/nightly/release, score, or promotion claims.
19. `pending` — Continue vertical protected cross-family / PR breadth from the
    clean `3d44a9d` evidence identity, while keeping immutable Planner input as
    the separate next horizontal lane.

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
- Calibrated the committed governance baseline and removed duplicated live
  status from the stable project plan. Added the double-track `1 + 1` WIP,
  single-production-writer policy, separate status/evidence/promotion/
  admission/CI axes, exact failed remote-run identities and classification,
  scoped INV-11 exceptions, and an executable document-drift test. The new
  test failed before the document changes and then passed; 19 focused gates,
  the 939-test full suite, Ruff, mypy over 116 source files, `uv build`, and
  diff check pass. Isolated `python -m build` remains unavailable in the
  dedicated interpreter because host `ensurepip/python3.12-venv` is absent.
- Repaired the two CI failure classes that were harness/environment problems:
  core CI now runs `python -m pytest -q`, and BrowserGym bridge uses the
  isolated BrowserGym constraints on `ubuntu-22.04`. Added a governance test
  that failed before the workflow repair and passes after it. Kept the
  Chromium/container coherent observation epoch drift classified as an open
  benchmark/runtime diagnostic rather than marking the PR green by wording.
  Verified with the focused CI workflow contract test, the generalization
  evidence import-path test, the local Chromium smoke, focused epoch-drift
  behavior tests, the full 940-test suite, Ruff, mypy, `uv build`, and diff
  check. No new remote CI run has been triggered.
- Added a bounded BrowserSession stabilization retry for transient
  affordance-state drift during multi-source capture, with semantic DOM drift
  still rejected. Added `--allow-acceptance-fail` so CI benchmark smoke can
  complete and publish all run artifacts without pretending release acceptance
  passed; default `benchmark` still returns non-zero on acceptance failures.
  The local `--seeds 3 --allow-acceptance-fail` benchmark completes 63 runs and
  exits 0 while reporting acceptance failed, preserving the settings/recovery
  promotion gap for follow-up. Verified with the full 942-test dedicated
  Python 3.12 suite, 13 focused CLI/browser/governance gates, Ruff, mypy over
  116 source files, `uv build`, and diff check. No new remote CI run has been
  triggered.
- Split active-subgoal reading from activation: `active_subgoal()` is now
  read-only, `activate_next_subgoal()` is explicit, Coordinator owns the
  production activation call, and planner-context construction no longer
  advances progress. The architecture gate now treats the old
  planner-context hidden mutation as closed rather than allowlisted. Verified
  with the RED-to-green planner-context no-mutation and debt-closure tests,
  189 focused active-subgoal/planner/context/governance gates, the full
  944-test dedicated Python 3.12 suite, Ruff, mypy over 116 source files,
  `uv build`, and diff check. No benchmark/provider/remote CI/promotion claim.
- Ran the selected SG7 strict-generalist targeted protected-family diagnostic
  on clean committed `fa288af` after restarting the existing Ollama container
  to restore NVML and 100% GPU model residency. Pre-run gates passed: 21
  horizontal architecture/responsibility tests, 40 SG1-SG6 deterministic intake
  tests, Ruff, mypy, and diff check. The 2-task x 2-seed matrix observed all
  four episodes with no provider failures, no retries, no missing/unrun/
  invalidated cases, and `official_score_claimed=false`; SG7 failed 0/4 in
  INTENT / PLANNING. Three episodes failed before TaskSpec creation with
  `unresolved_task_dependency`; `enter-date` seed 0 created a canonical
  compiler TaskSpec and accepted TaskPlan, then strict planner returned
  `ask_user` / `waiting_clarification`. No production code was changed. The
  next vertical action is a generic non-BrowserGym intent/planning repair slice,
  not a PlannerStateView migration unless new evidence ties mutable planner
  state to the failure.
- Implemented and diagnosed that generic SG7 repair candidate in the current
  dirty tree without adding task-family dispatch, selector/URL branches, Prompt
  changes, budget expansion, Coordinator changes, StateKernel changes, or
  PlannerStateView migration. The repair covers bounded unresolved-dependency
  draft repair, explicit value-entry canonicalization, non-literalized
  page-sourced text, value-entry-only text-action inference, strict planner
  exact/page-text/submit fallbacks, targeted perception request merging,
  BrowserGym targeted observation, and executor-local opaque DOM spatial
  binding. The dirty-tree SG7 run
  `/tmp/affordance-sg7-fa288af-submit-fallback-dirty-20260727-182502` observed
  all four requested episodes and passed 4/4 with no provider/runtime failure,
  no missing/unrun/invalidated cases, `official_success_rate=1.0`, and
  `official_score_claimed=false`. Because `working_tree_clean=false` and the
  source tree digest is
  `sha256:cb4dd50f8cf2376fce30673d813e1ca895f44b67a2c46860022902c163fa8403`,
  this is only validated repair-candidate evidence. The next step is commit or
  otherwise freeze the candidate, rerun the same matrix from a clean tree, then
  continue vertical protected breadth. Immutable Planner input remains the next
  horizontal lane, not this SG7 repair's prerequisite.
- Committed the SG7 generic repair as
  `3d44a9d222decd1de272d7a4d3eb14b025a8738a`, pushed it to
  `origin/agent/migrate-runtime-components`, and reran the exact clean SG7
  targeted matrix. The clean run
  `/tmp/affordance-sg7-3d44a9d-20260727-184535` observed and passed all four
  requested episodes with no provider/runtime failure, no missing/unrun/
  invalidated cases, no rate-limit/transient retries, `official_success_rate=1.0`,
  `mean_official_reward=1.0`, and `official_score_claimed=false`. Compact
  evidence is archived under `docs/evidence/runs/m8.2a-sg7-3d44a9d/`. This
  closes SG7 targeted confirmation only; protected breadth remains next and
  promotion remains held.

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
- M8.2A SG1-SG7 targeted confirmation is locally complete within its declared
  scope. Protected cross-family / PR breadth is the next vertical lane when
  authorized; Coordinator containment proceeds as a parallel horizontal track
  and is not a unified-refactor prerequisite.
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
16. `done` — Remote CI was intentionally closed after the repaired workflow
    reached GitHub billing/spending limits. The current validation channel is
    local equivalent gates, not remote-green evidence; local diagnostic
    benchmark success is not a release/promotion claim while benchmark
    acceptance remains failed.
17. `done` — Close the H1 active-subgoal hidden-mutation debt in project code:
    make `StateKernel.active_subgoal()` read-only, add explicit
    `activate_next_subgoal()`, keep production activation in Coordinator, and
    remove the planner-context hidden-mutation exception from the architecture
    gate.
18. `done` — Freeze the SG7 generic repair in a clean revision and rerun the
    exact targeted matrix (`enter-date`, `text-transform`, seeds 0 and 1)
    before protected breadth, PR/nightly/release, score, or promotion claims.
19. `in_progress` — Continue vertical protected cross-family / PR breadth on a
    clean current revision with local equivalent gates, while keeping immutable
    Planner input as the separate next horizontal lane. Clean `9b951ed` PR
    breadth now stands at 12/12 observed, 8/12 official reward passed, 4/12
    official reward failed, no provider failure, and no missing/unrun/
    invalidated episodes; this is still negative diagnostic evidence, not
    promotion. Next vertical step is V-PRB-2 provider graph proposal
    normalization for the remaining official-failed INTENT / PLANNING cluster,
    with the single runtime terminal-completion guard observation tracked
    separately.
20. `pending` — Execute the review-driven remediation sequence as separate
    slices: P1 immutable Planner input, P2 semantic fallback owner extraction,
    P3 intent semantic normalizer, and P4 protected breadth continuation. Do
    not batch these into one mixed architecture/product patch.
21. `done` — Record the follow-up review's constraint that the PR breadth
    repair packet is an umbrella diagnostic, not a production patch. Completed
    V-PRB-0 failure-attribution fidelity from local traces: 12/12 episodes now
    have exact mechanism owners, `click-button:seed-1` is classified as
    structured intent decoding / attribution projection because no TaskSpec was
    created, coverage audit invalid quotes are separated from graph
    normalization, and planner clarification cases are routed to typed semantic
    action constraints.
22. `done` — Select exactly one child production slice after non-BrowserGym
    reproduction: V-PRB-1 invalid coverage audit handling first if deterministic
    READY was blocked only by invalid optional audit; otherwise V-PRB-2 provider
    graph proposal normalization. V-PRB-1 was selected and reproduced with
    `tests/test_intent_compiler.py::test_invalid_coverage_audit_quote_cannot_veto_deterministic_ready`.
    The repair drops invalid coverage-review quotes as invalid vetoes while
    preserving valid coverage vetoes. Do not batch V-PRB-2 through V-PRB-4.
23. `done` — After local gates and commit, rerun the same PR breadth
    6-task x 2-seed matrix on the clean committed revision and classify impact;
    no promotion or official score claim. Clean `d40f8f1` rerun observed 12/12
    episodes, passed 0/12, and showed V-PRB-1 closed invalid coverage-audit
    vetoes by advancing the two affected episodes to planner clarification.
24. `done` — Select one next child slice only: V-PRB-3 typed semantic
    action constraints first if prioritizing the largest 7-episode
    `planner_waiting_clarification` cluster, otherwise V-PRB-2 provider graph
    proposal normalization for the 4 invalid graph episodes. V-PRB-3 was
    selected and implemented as a strict semantic action resolver with
    non-BrowserGym red tests for unique activation, selected-option terminal
    submit, and target-derived text entry. Do not batch.
25. `done` — After local gates and commit, rerun the same PR breadth 6-task
    x 2-seed matrix on the clean committed revision and classify impact; no
    promotion or official score claim. Clean `9b951ed` rerun observed 12/12
    episodes, passed 8/12 official reward, failed 4/12 official reward, and
    showed V-PRB-3 closed the typed semantic action constraint cluster for this
    matrix. One additional `enter-text:seed-1` runtime terminal-completion
    guard observation has `official_reward=1.0` and is tracked separately from
    official failed episodes.
26. `done` — Select one next child production slice only: V-PRB-2 provider
    graph proposal normalization for the four remaining official-failed
    `click-button-sequence` and `form-sequence` episodes. First create a
    non-BrowserGym reproduction for source-bound multi-effect provider graph
    normalization; do not batch PlanningRequest migration, terminal-completion
    guard handling, fresh diagnostic, or PR/nightly/release promotion. The
    selected slice was implemented with
    `tests/test_intent_compiler.py::test_llm_compiler_canonicalizes_multistage_requested_effects_when_provider_graph_is_incomplete`.
27. `done` — Implement V-PRB-2 as a narrow canonical obligation compiler
    boundary repair after a non-BrowserGym red test. Clean `c24b277` PR breadth
    rerun observed 12/12 episodes, passed 8/12 official reward, failed 4/12
    official reward, and showed invalid provider graph is closed. The four
    remaining official failures advanced downstream: two
    `click-button-sequence` planner clarification cases and two
    `form-sequence` task-planning `entry_action_family_unavailable` cases.
28. `done` — Select one next child slice only: V-PRB-5 downstream
    task-planning/planner constraint follow-up. First classify exact owner and
    create non-BrowserGym reproduction for either click-button-sequence
    continuation planning or form-sequence entry action family availability; do
    not batch them together and do not start immutable PlanningRequest unless
    the evidence shows mutable planner input is the root cause. V-PRB-5 was
    opened as diagnostic-only packet with two candidate mechanisms.
29. `done` — Open V-PRB-5 as diagnostic-only classification packet. Split the
    remaining official failures into V-PRB-5A button sequence progress /
    next-subgoal gating and V-PRB-5B form sequence entry action family
    availability. No production repair is admitted by the umbrella diagnostic.
30. `done` — Incorporate the latest review into governance state before any
    new production repair. Add executable manifest coverage for
    `semantic_action_resolver.py`, split V-PRB-5 into child diagnostic records
    for V-PRB-5A button-sequence effect semantics and V-PRB-5B entry
    action-family resolution, and create V-PRB-6 terminal-completion guard
    classification. Keep immutable Planner input separate unless RED evidence
    directly implicates mutable `StateKernel` input.
31. `done` — Start V-PRB-5A only: write non-BrowserGym RED tests for
    activation effect relation, explicit dependency, verifier-backed progress,
    and intermediate/final terminal flags. If the owner is compiler-local,
    continue 5A; if it requires public semantic/schema expansion, pause for an
    ADR and optionally select V-PRB-5B as the narrower next slice. Do not mix
    V-PRB-5B, V-PRB-6, H2 immutable PlanningRequest, PR/nightly/release, or
    promotion into the same patch. The RED test showed a compiler-local
    requested-effect sequence gap and was repaired without touching
    Coordinator, StateKernel, PlannerPort, Prompt, budget, task grammar, or
    benchmark-specific logic.
32. `done` — Commit V-PRB-5A after focused gates, then rerun the same
    PR breadth 6-task x 2-seed matrix on the clean committed revision. Only
    after that rerun classify whether the button-sequence mechanism closed and
    whether the next slice is V-PRB-5B, V-PRB-6, or a different owner. Clean
    `0565e2e` rerun is negative: 12/12 observed, 7/12 official passed, 5/12
    official failed, 6 runtime failures, no missing/unrun/invalidated cases,
    and `official_score_claimed=false`.
33. `done` — Classify the failed `0565e2e` rerun before the next
    production repair: inspect button-sequence traces to determine why
    `planner_waiting_clarification` remains after the compiler-local sequence
    repair, classify the then-new/remaining `click-button:seed-1`
    `schema_incompatible` case separately, and keep V-PRB-5B and V-PRB-6 separate.
    Button-sequence dependency/terminal boundaries are now present, but clicked
    targets still compile as `predicate / is_available`; verifier progress
    correctly rejects weak execution/state-delta evidence, so the next owner is
    requested-effect relation/evidence semantics rather than Coordinator,
    StateKernel, PlannerContext, or receipt-driven progress.
34. `done` — Write the next V-PRB-5A non-BrowserGym RED for
    clicked/activated relation and evidence semantics. The RED failed on
    `predicate` versus expected `effect`, then passed after a compiler-local
    canonical repair. Keep V-PRB-5B form action-family, V-PRB-6 terminal guard,
    H2 immutable Planner input, and promotion separate.
35. `done` — Commit and push the second V-PRB-5A repair, then rerun the
    same PR breadth 6-task x 2-seed matrix on the clean committed revision
    before judging button-sequence closure. Clean `e4795c1` PR breadth remains
    negative: 12/12 observed, 8 official reward passes, 4 official reward
    failures, 5 Runtime failures, no missing/unrun/invalidated/provider
    failures, and `official_score_claimed=false`. The prior
    `click-button:seed-1` schema incompatibility no longer reproduces.
36. `done` — Write the next V-PRB-5A non-BrowserGym RED for
    completed-click progress evidence / observer-verifier binding. The clean
    traces show `effect / is_completed` obligations are now present, but after
    the first click Runtime correctly rejects weak receipt/state-delta evidence,
    leaves active subgoal `button ONE is completed`, and the strict planner
    asks for clarification. The RED failed because BrowserGym only returned
    terminal-only `state_delta_or_terminal`; it now passes with an
    active-subgoal `observation_metadata(active_control == bid)` verifier for
    completed click outcomes. Generic `state_delta_or_terminal` remains weak
    and terminal-only. Do not accept receipt success alone as progress; keep
    V-PRB-5B, V-PRB-6, immutable Planner input, and promotion separate.
37. `done` — Commit and push the completed-click progress evidence
    repair, then rerun the same PR breadth 6-task x 2-seed matrix on the clean
    committed revision before judging button-sequence closure. Clean `c75fc3b`
    rerun remained negative at 8/12 official reward: the new verifier did not
    enter real button-sequence contracts because active action-family metadata
    is empty in that path.
38. `done` — Commit and push the refined completed-click progress
    evidence repair, then rerun the same PR breadth matrix on the clean
    committed revision. The refined RED/GREEN makes action-family an optional
    guard: present action-family must match, but absent metadata does not block
    typed `IS_COMPLETED` click progress evidence when target and concrete click
    action match. Clean `151fbef` PR breadth is 12/12 observed, 10/12 official
    reward passed, 3 Runtime failures, no provider/missing/unrun/invalidated
    failures, and `click-button-sequence` seeds 0 and 1 now pass. V-PRB-5A is
    closed for this matrix.
39. `done` — Implement V-PRB-5B entry action-family resolution as a
    non-BrowserGym RED/GREEN slice. The first repair made slider-like
    reversible writes use current `press_key` affordance evidence and kept
    ambiguous mappings unresolved. The clean `5c7a2ab` rerun proved the
    original `entry_action_family_unavailable` form-sequence rejection no
    longer reproduces, but exposed a textbox fallback regression. The
    follow-up `2b67ffd` repair restores textbox value-entry inference.
40. `done` — Rerun the same PR breadth matrix on the clean committed V-PRB-5B
    follow-up repair lineage. Clean `3daf779` evidence is 12/12 observed,
    10/12 official reward passed, 3 Runtime failures, no provider/missing/
    unrun/invalidated cases. V-PRB-5B is closed for action-family resolution:
    `form-sequence` no longer rejects with `entry_action_family_unavailable`
    and `enter-text:seed-0` is restored.
41. `done` — Start V-PRB-5C only: write a non-BrowserGym RED for the
    remaining `form-sequence` strict-planner empty `ask_user` proposal after an
    accepted TaskPlan with `press_key` permitted. Keep V-PRB-6
    `enter-text:seed-1`, immutable Planner input, fresh diagnostic,
    nightly/release, and promotion separate.
42. `done` — Implemented the first V-PRB-5C bounded slider `press_key`
    resolver as `a805f0d` and reran the same PR breadth 6-task x 2-seed matrix
    on a clean committed revision. Evidence is 12/12 observed, 10/12 official
    reward passed, 3 Runtime failures, and no provider/missing/unrun/
    invalidated cases. The resolver enters the real form path and verifies
    slider `press_key` actions, but V-PRB-5C remains open because both
    `form-sequence` seeds later fail with empty `ask_user` after replan/
    progress normalizes the active slider subgoal. Continue V-PRB-5C with a
    new non-BrowserGym RED for that residual; keep V-PRB-6, immutable Planner
    input, fresh diagnostic, nightly/release, and promotion separate.
43. `done` — Implemented the second V-PRB-5C verified-form follow-up repair as
    `9c1b58c` and reran the same PR breadth matrix on a clean committed
    revision. Evidence remains 12/12 observed, 10/12 official reward passed,
    3 Runtime failures, and no provider/missing/unrun/invalidated cases. Seed
    0 now advances from the verified slider effect to the requested checkbox,
    but still stops before terminal submit; seed 1 still repeats slider
    keypresses through the negative target boundary. Continue V-PRB-5C with
    narrower REDs for terminal submit after verified checkbox completion and
    negative slider stop/direction. Keep V-PRB-6, immutable Planner input,
    fresh diagnostic, nightly/release, and promotion separate.
44. `done` — Implemented the third V-PRB-5C repair as `d50a631` and reran the
    same PR breadth matrix on a clean committed revision. Evidence is 12/12
    observed, 12/12 official reward passed, 3 Runtime failures, and no
    provider/missing/unrun/invalidated cases. The prior form-sequence official
    failures no longer reproduce, so V-PRB-5C is closed for this matrix. PR
    breadth acceptance remains held because `enter-text:seed-1` and both
    `form-sequence` seeds still abort after external reward succeeds with
    `planner cannot finish before verifier-backed subgoal completion`.
45. `done` — Continue V-PRB-6 diagnostics and the selected V-PRB-6B
    child production slice only. Compact trace
    projection is archived at `docs/evidence/runs/v-prb-6-compact-d50a631/`.
    V-PRB-6A now has a strict-xfail executable RED for dependent checkbox
    `HAS_CHANGED` evidence remaining `task_terminal` instead of
    `active_subgoal`. The same projection reclassifies V-PRB-6B before RED:
    `enter-text:seed-1` has two subgoals, not one; the completed unit is the
    text-change subgoal and the incomplete unit is independent read-only
    `submit_button is available`. V-PRB-6B now has child production packet
    `docs/change-admission/v-prb-6b-read-only-availability-cardinality.yaml`;
    TaskPlan current-state/cardinality handling is the selected owner, and the
    former strict-xfail RED in `tests/test_task_planning.py` passes locally
    without xfail after generic symbolic subject-to-affordance matching.
    Focused gate is `147 passed, 1 xfailed`; the remaining xfail is V-PRB-6A.
    The clean `17f2e50` PR breadth rerun is archived at
    `docs/evidence/runs/m8.2a-pr-breadth-17f2e50/` and is negative: 12/12
    observed, 11/12 official reward, 4 Runtime failures. V-PRB-6B changed
    shape but is not closed: `enter-text:seed-1` now fails earlier with
    `task_planning ... entry_outcome_already_satisfied`, then exhausts the
    repair loop. Follow-up 6B child slice
    `docs/change-admission/v-prb-6b-current-state-discard-replacement.yaml`
    is implemented locally: TaskPlanFlow prepares an accepted replacement that
    preserves verified prior subgoals and discards an already-current read-only
    availability/visibility subgoal through the existing replacement-plan
    commit path. Focused gate is `155 passed, 1 xfailed`; static gates pass.
    Clean `9ad1288` PR breadth rerun is archived at
    `docs/evidence/runs/m8.2a-pr-breadth-9ad1288/` and is still negative:
    12/12 observed, 11/12 official reward, 4 Runtime failures. The local
    6B discard replacement is safe but insufficient: `enter-text:seed-1` still
    fails Runtime completion, both `form-sequence` seeds remain V-PRB-6A
    terminal-guard failures, and `click-button:seed-1` remains a separate
    JSON-invalid/schema robustness cluster. Runtime success, verifier success,
    and BrowserGym reward remain separate; no breadth completion, fresh
    diagnostic, nightly/release, promotion, immutable Planner input, or
    official score claim is made.
46. `in_progress` — Reclassify the post-`9ad1288` PR breadth residuals before
    any new production repair. The next slice must start from compact trace /
    root-owner evidence and choose exactly one owner: V-PRB-6A progress-scope
    binding, V-PRB-6B residual Runtime completion for `enter-text:seed-1`, or
    the separate click-button JSON-invalid schema/provider robustness cluster.
    Compact classification now exists at
    `docs/evidence/runs/v-prb-6-post-9ad1288-classification/` with diagnostic
    packet
    `docs/change-admission/v-prb-6-post-9ad1288-residual-classification.yaml`.
    Do not batch these and do not start immutable Planner input unless evidence
    directly implicates mutable Planner state.
47. `in_progress` — Selected the smallest next RED: V-PRB-6B HAS_CHANGED text
    progress binding for `enter-text:seed-1`, recorded at
    `docs/change-admission/v-prb-6b-has-changed-text-progress-binding.yaml`.
    The RED failed with task-terminal-only evidence and now passes after
    BrowserGym exact typed text postconditions declare active-subgoal evidence
    for `HAS_CHANGED` when the concrete value equals the Runtime-owned typed
    outcome. Focused regression is `49 passed, 1 xfailed`. Clean `c382592`
    PR breadth rerun is archived at
    `docs/evidence/runs/m8.2a-pr-breadth-c382592/` and is still negative:
    12/12 observed, 11/12 official reward, 4 Runtime failures. This repair is
    safe but insufficient; TaskPlan/progress replacement accounting was then
    narrowed to active-empty ready read-only convergence. Child production
    packet
    `docs/change-admission/v-prb-6b-ready-read-only-discard-after-progress.yaml`
    adds a non-BrowserGym RED/GREEN for the trace shape where verified text
    progress clears active projection and the ready `submit_button is available`
    subgoal is already current-state satisfied. The local RED/GREEN and
    adjacent replacement controls pass. Clean committed PR breadth rerun at
    `66dae07` is archived at
    `docs/evidence/runs/m8.2a-pr-breadth-66dae07/`: 12/12 observed,
    12/12 official reward, 3 Runtime failures. This is partial positive
    evidence, not PR breadth acceptance. Next slice must choose either the
    `enter-text:seed-1` `obligation_subgoal_missing` accounting residual or the
    separate V-PRB-6A form-sequence progress-scope cluster.

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

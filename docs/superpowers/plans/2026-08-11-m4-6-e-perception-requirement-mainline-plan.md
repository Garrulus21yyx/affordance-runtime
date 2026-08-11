# Task-Grounded Perception and Frontier Convergence Plan

Status: `IN_PROGRESS / IMPLEMENTED_DIAGNOSTIC_NOT_VALIDATED`.

Goal: remove irreversible loss between acquired GUI observations and bounded
model presentation, then add incremental non-authoritative requirement
hypotheses without creating a second observation, task, action or completion
authority.

## Frozen constraints

- Screenshot bytes are observation evidence, never execution authority.
- `WorldObservation`/`SurfaceObservation` remain the sole observation truth.
  Their bounded full `EntityInventory` is projected by `ObservationPager`; no
  parallel `ObservationSpace` authority is introduced.
- `ObservedEntity`, `CandidateTarget`, `ActionTarget` and `VerifiedSubject` are
  roles over one canonical public `entity_id`, not four duplicated entity
  records. Hypotheses, actions and evidence reference that identity.
- Stable entity identity and current execution are separate: an
  `EntityObservationRef` binds entity + snapshot/revision, while every
  `ActionOption`/binding remains strictly current-epoch and stale use is
  zero-dispatch.
- `ActionSpace` remains the only legal-action authority; visual/AX aliases can
  only reference current public targets/actions and expire with the context.
- Model transport must carry real typed image content; artifact summaries are
  not a substitute for image transport.
- Public semantic breadth may expose read-only structure without making every
  observed role executable.
- Requirement proposal produces bounded hypotheses only. Runtime assigns
  hypothesis IDs and owns admission/revision/retirement; verifier assessment
  owns only predicate `SATISFIED/CONTRADICTED/UNKNOWN`. Only `TaskGoal`, user
  input or existing criteria define authoritative task requirements, and only
  `TaskEvaluator` owns terminal task truth.
- Losslessness is scoped to the finite acquired snapshot, declared semantic
  profile and hard inventory cap. Capacity exhaustion/partial acquisition fail
  typed; infinite GUI, canvas and scroll-space completeness is not claimed.
- Source acquisition coverage, inventory completeness and model-presentation
  traversal are separate axes. Negative-claim coverage gates never overwrite
  authoritative source/evaluator facts.
- No static full-task DAG, task-name production branches, hidden benchmark
  answers, selectors, coordinates, credentials, or oracle state.
- Benchmark reports separate `capability_covered`, `unassessed` and
  `declared_gap` cohorts; mixed-denominator success is prohibited.

## Steps

| Step | Status | Work | Files |
|---|---|---|---|
| 0 | completed | Freeze revised terminology, authority split, scoped completeness and honest implementation statuses. | this plan; implementation status; current queue |
| 1 | completed | Replace role/label/ordinal identity with run/page-incarnation-scoped opaque entity identity while keeping action bindings epoch-bound. | `browsergym_entity_identity.py`; BrowserGym projection/environment; identity/execution tests |
| 2 | completed | Retain a bounded full entity/state/fact/relation/option-domain inventory inside `SurfaceObservation`; hard-cap overflow returns typed partial/capacity outcomes. | world contracts and BrowserGym projection |
| 3 | completed | Add `ObservationPager` and bounded traversal state over one frozen snapshot, with pinned header plus fair exploration slots. | model boundary and loop state |
| 4 | completed | Add `NegativeClaimCoverageGate` for absence/no-progress/infeasible/unsupported/unsupported-ProposeDone claims only; authoritative success and normal actions bypass it. | decision/progress control |
| 5 | in_progress | Run a clean current-SHA text-only versus screenshot+AX baseline on the intersection capability-covered cohort, separating run validity, comparison validity and inconclusive pairs. | benchmark profile and fresh evidence |
| 6 | pending | Add bounded instruction-first incremental `RequirementHypothesis` proposals with optional candidate entity references and unknown set completeness. | model/task hypothesis contracts |
| 7 | pending | Add Runtime hypothesis admission/lifecycle plus verifier predicate assessment without creating task requirements or terminal truth. | task frontier/runtime admission/evaluation |
| 8 | pending | Add bounded hypothesis pinning to existing rolling objectives while preserving fair cursor enumeration and ActionSpace authority. | context projection/action relevance |
| 9 | pending | Run separated capability-covered, unassessed and declared-gap cohorts; decide viewport/OCR/SoM/scroll work only from fresh failure evidence. | benchmark reports/evidence |

## Exit criteria

- A provider receives actual screenshot image content plus the same bounded
  public context, and text-only mode remains deterministic and compatible.
- Missing/oversized/unsupported image content fails typed before a provider
  call; private capture can retain exact exchanges outside public evidence.
- Observable roles and structural nodes can inform policy without silently
  becoming executable actions.
- Finite-snapshot losslessness: within the declared profile/cap, every retained
  entity is reachable through bounded paging or traversal ends typed unknown.
- Scoped stable identity: irrelevant AX order changes do not change an entity
  ID, while old action bindings remain stale after epoch change.
- Non-amplification: observation/hypothesis/pinning never creates or legalizes an
  ActionOption.
- Negative-claim coverage safety: incomplete model traversal cannot justify an
  absence/no-progress/infeasible/unsupported conclusion.
- Hypothesis non-authority: predicate assessment cannot define task necessity,
  hypothesis-set completeness or terminal success.
- Bounded traversal liveness: every traversal terminates complete or typed
  unknown within declared page/byte/policy-call budgets.
- A/B manifests declare perception profile and readiness cohort before model
  execution; reports do not conflate supported and challenge success rates.

## Progress log

- 2026-08-11: plan created after the 25-case diagnostic showed 8 terminal
  zero-target/zero-action cases, 5 one-target/one-action terminal failures, and
  only 2 declared-supported cases in the reviewed-rule inventory-v2 profile.
  The prior task-frontier implementation remains useful verified memory, but is
  not treated as a substitute for perception or requirement production.
- 2026-08-11: implemented the first perception vertical: BrowserGym screenshots
  are encoded as bounded typed PNG evidence, excluded from public semantic JSON,
  and sent as standard multimodal message parts under `screenshot-ax.v1`.
  Expanded AX v2 projection with checkbox/radio/tab/menuitem actions and bounded
  read-only table/list/heading/static-text relations. Targeted tests passed;
  the first full run was 2215 passed with only this new plan missing from the
  documentation lifecycle manifest, which is now corrected.
- 2026-08-11: same-model A/B on the two inventory-v2 declared-supported cases
  completed with valid public evidence and private raw exchanges. Text-only was
  0/2 control repetition; screenshot+AX was 0/2 with one control repetition and
  one provider exhaustion after one actual dispatch. The run falsified success
  improvement but exposed a shared adapter gap: `click-link` used BrowserGym
  `generic` nodes with `clickable=true`, producing zero actions. Added a bounded
  normalization to public `clickable` targets with descendant text labels. A
  fresh live reset now projects 22/22 targets, 7 actionable and 15 read-only,
  with zero omissions. Full validation after this repair is 2218 passed and 27
  skipped; Ruff and mypy pass. A fresh A/B remains required for this new SHA.
- 2026-08-11: fresh A/B on clickable-normalization SHA `b853a5e` is valid and
  privacy-clean. Both arms reached 1/2: `click-link` succeeded in text-only and
  screenshot+AX, proving candidate projection was the gating change. Text-only
  `click-tab-2` repeated already-satisfied `target_present` objectives;
  screenshot+AX received three rate-limit attempts before provider exhaustion.
  The screenshot arm carried one image part on every recorded request and
  completed `click-link` in one policy call/one execution. This does not show a
  screenshot success-rate advantage on the two-case cohort.
- 2026-08-11: corrected the `click-tab-2` objective-repair diagnosis. The model
  projection already carried `recovery.strategy_change_required=true`, but the
  benchmark trace mislabeled the top-level transition flag as that recovery
  field. More importantly, objective issue identity omitted the rejected typed
  predicate, so two different already-satisfied predicates collided and the
  second repair was terminated as repetition. Issue identity now includes the
  public predicate, the trace records both flags plus `must_change_fields`, and
  the feedback contract requires predicate replacement for this code. Paired
  regression properties prove that a changed predicate receives the next
  bounded repair turn while an identical predicate is still mechanically
  terminated. Full validation is 2220 passed and 27 skipped; Ruff and mypy pass.
- 2026-08-11: a clean-SHA directed `click-tab-2` rerun proved that Mistral
  received the corrected fields but repeated the exact objective/action package.
  The remaining contract gap was actionable replacement data: “change this
  predicate” did not identify a currently admissible replacement. Recovery now
  projects bounded Runtime-derived `admissible_objective_operations`: no
  objective operation, or a proposal for the current frontier with
  `task_outcome_is: complete`. The model is told to copy one complete candidate;
  Runtime still independently admits the objective and current ActionSpace
  remains the only action authority. Full validation remains 2220 passed and 27
  skipped; Ruff and mypy pass. A fresh clean-SHA directed rerun is required.
- 2026-08-11: that rerun still returned the exact rejected package despite the
  typed candidates, proving prompt compliance alone is insufficient for this
  model. The bridge now narrows only an `objective_already_satisfied` repair
  call's provider JSON Schema to the Runtime-projected objective candidates and
  revalidates the same subset locally. The canonical package schema and action
  schema are otherwise unchanged, and Runtime admission remains final. Full
  validation is 2221 passed and 27 skipped; Ruff and mypy pass. A fresh
  clean-SHA directed rerun is required to verify provider schema compatibility
  and actual dispatch.
- 2026-08-11: the clean-SHA `60e9771` directed rerun passed. Call 1 proposed an
  already-satisfied `target_present` objective and was rejected with zero
  dispatch. Call 2 received both typed repair candidates; the provider schema
  selected `objective_operation: none`, retained the legal click decision, and
  Runtime independently admitted and dispatched it. The external verifier
  returned `terminal_success/verified_success`. The run used two policy calls,
  two provider attempts and one execution, with no evidence/harness errors.
  Public trace and mode-0600 raw exchanges are retained under the local
  `artifacts/m4-6-e-objective-feedback-click-tab-60e9771` diagnostic tree.
- 2026-08-12: architecture-first convergence review froze the shared
  task-grounded perception/frontier cause while retaining separate authorities.
  Screenshot transport, first semantic breadth, diagnostic A/B and the P5-E
  rolling-objective vertical slice exist; stable entity identity, non-lossy
  bounded inventory, observation traversal/negative-claim gating and an
  incremental requirement-hypothesis producer do not. Viewport tiling, OCR, SoM
  and automatic scrolling are explicitly deferred until fresh evidence makes
  them the next blocker. Step 1 started.
- 2026-08-12: step 1 implemented. A Runtime-private keyed identity mapper now
  derives opaque `entity:*` IDs from page/episode incarnation plus stable
  private BID/node identity. AX permutation and unrelated insertion preserve
  IDs; same-label controls remain distinct; page-incarnation changes mint new
  IDs. Independent capture preserves entity identity while replacing bindings,
  and replaying the old binding remains zero-dispatch. Modified files:
  `browsergym_entity_identity.py`, BrowserGym projection/environment and focused
  identity/execution tests. Validation: 71 focused tests passed, Ruff and mypy
  passed, and the full suite passed 2224 with 27 skipped. Step 2 started.
- 2026-08-12: steps 2-4 implemented as one bounded observation slice. BrowserGym
  now retains up to 512 canonical entities and 4096 facts before any model
  projection; option domains, relation counts and typed capacity reasons are
  conserved by `EntityInventorySummary`. The 64-target model limit is now a
  page size only. `ObservationPager` binds opaque cursors to one frozen
  snapshot, preserves current action targets in a bounded header and reserves
  fair exploration slots. A `RequestObservation.cursor` advances only the
  in-memory page and consumes no acquisition. `NegativeClaimCoverageGate`
  intercepts absence/no-progress/unsupported and evidence-free completion
  claims while traversal is partial; incomplete acquisition/inventory becomes
  typed unknown. Ordinary actions and authoritative evaluator success bypass
  the gate. Adversarial tests put 70 distractors before a critical action target
  and retain both the target and a usable exploration cursor. Validation:
  Ruff passed, mypy passed across 451 source files, the full suite passed 2229
  with 27 skipped, and all 15 documentation-governance checks passed. The
  current-SHA perception A/B is the next gate.

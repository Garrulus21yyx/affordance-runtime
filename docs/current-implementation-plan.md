# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Execution-table revision:** 2026-08-05 granular cutover plan
> **Target:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Migration authority:** [Architecture evolution plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
> **Implementation truth:** [Implementation Status](implementation-status.md)

## 1. How to use this plan

This is the only maintained implementation scheduler. It expands the P0–P5
architecture phases into independently reviewable cutover slices. It does not
create another architecture authority and does not claim that a pending target
already exists in production.

A slice moves to `done` only when its canonical owner is wired into the default
path, the displaced owner is deleted or explicitly isolated, the minimal
failure-localizing checks pass, and `implementation-status.md` is updated.

At most one vertical authority migration and one independent horizontal
containment slice may write production behavior at a time. No slice may create
a shadow owner merely to postpone deletion.

## 2. Target identity

```yaml
authoritative_architecture: docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md
authoritative_evolution_plan: docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md
documentation_manifest: docs/documentation-manifest.yaml
execution_table: granular_P0_through_P5
migration_mode: substitutive_no_bidirectional_legacy_coupling
default_source_target: SourceEnvelope_plus_selective_SourceAnchor
material_binding_target: effect_specific_risk_proportionate_typed_coverage
optional_audit_target: SemanticAudit_veto_or_clarify_only
semantic_context_target: bounded_read_only_SourceContextView
semantic_write_owner: TaskSpecAuthority_only
requirement_identity_target: canonical_TaskRequirement_refs
planning_target: observation_grounded_TaskPlan_of_StepSpec
choice_target: full_Runtime_ActionChoiceCatalog_before_ChoicePage
choice_presentation_target: bounded_semantic_context_without_execution_bindings
catalog_realization_target: logical_complete_eager_or_lazy_indexed
observation_realization_target: immutable_epoch_ref_plus_read_only_indexes
authority_realization_target: modular_monolith_in_process_policy_composition
criterion_rollout_target: canonical_vocabulary_with_phased_provider_coverage
task_planner_invocation_target: typed_trigger_with_reuse_and_direct_fast_paths
feature_profile_target: risk_derived_optional_machinery_without_gate_bypass
cross_surface_target: DOM_AX_Visual_SVG_WoT_API_Device
verification_target: loop_native_typed_LoopEvaluator
completion_semantics_owner: TaskCompletionEvaluator
required_output_target: materialized_and_source_bound_before_completion
completion_commit_owner: RuntimeCommitter_only
test_strategy: failure_localizing_minimal_gates
```

## 3. Delivery laws

1. **Substitutive cutover:** add the canonical owner, migrate every in-scope
   caller, switch default composition, then remove/isolate the old owner in the
   same slice.
2. **One responsibility per module:** split by contract/decision ownership, not
   by arbitrary class count or framework layer.
3. **Coordinator only sequences:** it starts the run, invokes typed stages,
   follows `LoopDirective`, and returns a result. It does not classify domain
   failures, build choices/contracts, evaluate criteria, or write state.
4. **RuntimeCommitter only commits:** it applies admitted transitions/events;
   it does not calculate completion, recovery, evidence, or planning results.
5. **Stage façade stays thin:** a phase may compose collaborators, but domain
   algorithms live with the contract they own.
6. **No service forest:** a logical authority may be a pure function or small
   in-process policy object. A new process/store/model call needs measured need.
7. **No test-driven architecture:** tests locate a declared failure and protect
   a boundary; they do not define production semantics or justify keeping a
   legacy owner.
8. **No old/new round-trip:** canonical data may not be projected into a legacy
   type and converted back; no dual read, dual write, shadow comparison owner or
   fallback from canonical semantics to legacy prose is allowed.
9. **Compatibility is edge-only and one-way:** when an external caller cannot
   migrate in the same slice, an explicitly named adapter may translate old
   input into the canonical API. Canonical modules never import that adapter or
   legacy models, and every adapter has a last-allowed slice.

## 4. Anti-God-File ownership map

Line count is a review trigger, not a correctness metric. A file above roughly
600 lines, or a slice adding a second domain responsibility to a file, requires
an explicit split decision before merge. Existing oversized files are debt to
remove inside their owning migration slice, not through an unrelated rewrite.

| Physical owner | Allowed responsibility | Must not absorb | Planned split/cutover |
|---|---|---|---|
| `coordinator.py` | serial stage ordering and typed directives | recovery classification, semantic parsing, contract construction, evaluation, state mutation | P1-C1 complete; Coordinator only invokes typed RecoveryStage results |
| `runtime_committer.py` | authoritative transition and trace commit | run-session lifecycle, read projections, evaluator/recovery policy | P1-C2 complete; it consumes precomputed RuntimeTransition/events/completion only |
| `execution_phase.py` | compose one admitted action attempt | Catalog construction, planner logic, completion logic | P0-C4 action admission extracted; later phase-containment cleanup remains |
| `choice_contracts.py` / `action_choice_catalog.py` | immutable semantic choice contracts / logical full Catalog | model projection policy or backend route selection | P0-C complete |
| `action_contract_builder.py` | selected-choice validation and current binding materialization | execution, approval grant or completion | P0-C4 complete |
| `task_planner.py` / `step_choice_planner.py` | strict typed task-planning / closed step-choice provider ports | Runtime authority objects, hidden Catalog entries or action dispatch | P4-2 complete; `generalist_planner.py` is an isolated historical compatibility profile used only by the generalization comparison and expires at P5-3 |
| `progress_phase.py` | thin post-action stage façade and route-outcome composition | observation repair, task completion evaluation or TaskSkill algorithms | P1 closure complete; focused collaborators own each algorithm |
| `intent_compiler.py` / `task_spec_authority.py` | untrusted minimal proposal interpretation / sole accepted TaskSpec admission | source graphs, planning, capability grant or observation-derived authority | P0-E complete |
| `material_contracts.py` / `material_binding_policy.py` | typed material binding vocabulary / deterministic per-effect field coverage and provenance-form admission | graph/store/model call, SemanticAudit policy, capability/approval/grounding/contract decisions | P0-E5 complete; P3 folds values into canonical requirements without a second registry |
| `verification/mechanical.py` | mechanical verifier reports used as admitted evidence input | root completion, progress decisions or commit | P0-A package cutover complete; further provider/evidence-policy refinement remains in `P1-E1`/`P2` |

New files are justified only when they own one durable contract or decision.
Do not create one file per dataclass, provider instance, gate result, or surface.

### 4.1 Legacy deletion protocol

Every migration row follows this order:

```text
canonical contract
→ canonical implementation
→ migrate callers
→ switch composition/default route
→ delete legacy owner, conversion and tests
```

The default route never contains both owners. A compatibility adapter may exist
only at an external ingress boundary, must be one-way old-input→canonical-input,
and cannot expose legacy state to canonical planners, evaluators or committers.

| Legacy surface | Last allowed slice | Required deletion evidence |
|---|---|---|
| `verification.py` implementation / `verification/legacy.py` | `P0-A4` | no production import of legacy verifier or Boolean/synthetic completion API |
| `runtime_terminal.py::TaskCompletionVerifier` latest-report authority | `P0-A4` | only typed TaskCompletionEvaluation reaches RuntimeCommitter |
| `UnifiedObservation.from_planner_observation` and reverse projection | `P0-B4` | canonical builder is the only production constructor |
| algorithm/presentation/selection ownership in `action_choice.py` | `P0-C5` | callers import focused canonical modules; temporary re-exports removed |
| `planning.py::ContractBuilder` | `P0-C4` | ActionContractBuilder owns canonical observation/catalog binding |
| default SourceLedger/claim/obligation intake route | `P0-E4` | ordinary composition cannot import or invoke ledger graph construction |
| default StepSpec→SubgoalSpec→StepSpec and completed-subgoal carry-forward | `P1-P3` | **deleted** — current TaskPlan stores StepSpec directly and progress survives by facts/bindings/verified records |
| external model provider `subgoals` wire schema in `legacy_task_plan_provider.py::LegacyTaskPlanProviderAdapter` | `P3-4` | **deleted** — strict task planning emits canonical PlanProposal/StepSpec contracts |
| strict planner StateKernel/BrowserSnapshot/ActionChoiceBuilder signature and `planner_compatibility.py` | `P4-2` | **deleted** — strict ports accept only typed TaskPlanningRequest or ChoicePlanningRequest |
| historical `generalist_planner.py` / `compatibility_planner_algorithms.py` comparison profile | `P5-3` | isolated from strict/default construction; sole production consumer is `benchmarks/generalization_rollout.py::_run_compatibility_pair`; delete after that comparison migrates |

P5 is not a dumping ground for deletion deferred from earlier slices. Only a
documented external/public adapter with a consumer and expiry may survive to P5.

## 5. P0 correctness cutovers

### P0-A — Completion authority

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-A0` | Convert `verification.py` to `verification/__init__.py` + `verification/legacy.py`; list and migrate production callers toward focused package APIs | canonical contracts/modules never import `legacy.py`; the package root may expose a one-way temporary external compatibility surface only until A4 | none | existing verification/contract imports plus one canonical-does-not-import-legacy sentinel | done |
| `P0-A1` | Add `verification/contracts.py` with typed `CriterionEvaluation`, `LoopEvaluation`, `TaskCompletionEvaluation`, evidence metadata and `ObservationContinuation`; add the narrow typed `TaskSpec.success`/required-output references needed for P0-A closure without performing the full P3 TaskSpec-v2 cutover | prohibit Boolean/synthetic-PASSED types from new APIs; missing typed success remains UNKNOWN and is never recovered from prose | `P0-A0` | contract construction/immutability checks; reuse criteria tests | done |
| `P0-A2` | Add `verification/task_completion.py`; recursively evaluate `TaskSpec.success`, constraints, unresolved effects, final rechecks and required outputs | `runtime_terminal.py::TaskCompletionVerifier` becomes adapter-only and cannot inspect latest report as root authority | `P0-A1` | one parametrized closure test covering receipt/report/plan/prose rejection and output absence | done |
| `P0-A3` | Wire typed completion through `progress_phase.py`, `planning_phase.py`, `runtime_terminal.py` and `runtime_committer.py` | remove direct `TaskCompleted` construction outside RuntimeCommitter | `P0-A2` | reuse progress/planning/coordinator vertical tests; one initial-already-satisfied case | done |
| `P0-A4` | Remove disabled-verification PASSED and receipt/latest-report/plan-exhausted fallbacks from `contract_execution_loop.py`, `runtime_terminal.py` and compatibility call sites | delete `verification/legacy.py`, temporary package re-exports, superseded fallback branches and their dedicated tests after all production callers migrate | `P0-A3` | affected verification suite + one external-effect final-recheck sentinel + legacy-import absence scan | done |

### P0-B — Canonical observation

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-B1` | Complete immutable capture/coverage contracts in `perception_session.py` and `unified_observation.py` for DOM/AX/Visual/SVG/WoT/API/Device | BrowserSnapshot remains acquisition DTO only | none | reuse perception/DOM/WoT/visual tests | done |
| `P0-B2` | Add `canonical_observation_builder.py` and `observation_store.py`; build target/binding/fact/coverage indexes and immutable epoch ref | no model presentation settings in builder/store | `P0-B1` | one multi-binding/conflict/coverage builder test | done |
| `P0-B3` | Wire canonical build/ref through `perception_phase.py`, `active_perception.py`, `execution_phase.py`, `progress_phase.py`, `composition.py`, `runtime_committer.py` and `state_kernel.py` (the repository has no `runtime_loop_phase.py`; these are the actual phase/commit owners) | no Runtime semantic consumer reads long-lived BrowserSnapshot facts; StateKernel accepts only typed observation commits/refs | `P0-B2` | one normal + targeted + post-action epoch continuity test | done |
| `P0-B4` | Change `planning_request_builder.py` to one-way bounded projection from canonical observation; migrate strict/default planner and trace descriptors to the supplied canonical epoch | delete production `UnifiedObservation.from_planner_observation`, reverse reconstruction, the legacy converter test, and the raw-observation StateKernel compatibility owner | `P0-B3` | one projection-budget invariance sentinel; reuse request-builder/generalist/coordinator tests | done |

### P0-C — Runtime-owned action space

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-C1` | Move immutable choice/request/result types from `action_choice.py` to `choice_contracts.py`; migrate canonical callers and keep only an edge-only temporary re-export list | canonical choice modules never import `action_choice.py`; no algorithms in contracts | `P0-B2` | existing serialization/equality tests plus canonical-import direction scan | done |
| `P0-C2` | Add `action_choice_catalog.py` for deterministic eager/lazy/indexed membership, digest, rejections and surface-neutral semantic choices | presentation/page size and backend preference cannot alter membership | `P0-C1`, `P0-B4` | one parametrized count/order/digest invariance test | done |
| `P0-C3` | Add `choice_presentation.py` and `action_selection.py` for bounded pages, continuation, validation and `UNPRESENTED_CHOICE_ID` | remove presentation and selection branches from `action_choice.py` | `P0-C2` | reuse action-choice tests; add one hidden-ID rejection vertical test | done |
| `P0-C4` | Move `planning.py::ContractBuilder` to `action_contract_builder.py`; add `action_admission.py` for ordered Task/Capability/Approval/Freshness policies; shrink `execution_phase.py` to composition | no contract binding from planner/model views; no gate decides completion | `P0-C2`, `P0-B3` | reuse contract/preflight tests and one DOM→visual/WoT fresh-contract reroute case | done |
| `P0-C5` | Wire Catalog-before-model in `planning_phase.py`; strict `generalist_planner.py` only receives `ChoicePlanningRequest` | delete strict planner ownership of ActionChoiceBuilder, BrowserSnapshot, StateKernel and dispatcher; remove temporary `action_choice.py` re-exports after callers migrate | `P0-C2`–`P0-C4` | one 0/1/N vertical test using the normal Coordinator path + legacy-import absence scan | done |

### P0-E — Thin source and single semantic admission

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-E1` | Add `source_envelope.py` with immutable SourceEnvelope, selective SourceAnchor and deterministic builders | ordinary path performs no clause/claim/obligation graph work | none | one low-risk envelope test and one exact material-anchor case | **completed (2026-08-05)** — immutable hash/length/ref envelope plus whole-request and exact material anchors; no clause parsing or raw trace payload |
| `P0-E2` | Add `task_spec_authority.py`; make `intent_compiler.py` emit untrusted MinimalIntentProposal only | compiler cannot admit TaskSpec or derive steps | `P0-E1` | one admission/rejection test; reuse intake cases | **completed (2026-08-05)** — compiler exposes proposal-only `propose`; `TaskSpecAuthority` alone validates/admit revisions and binds Envelope identity |
| `P0-E3` | Add `source_context.py` and `semantic_audit.py` with consumer allowlist and risk-triggered pass/veto/clarify contract | no audit repair/write authority; execution receives no source context | `P0-E2` | one low-risk no-audit path and one high-risk veto/clarify path | **completed (2026-08-05)** — three-consumer bounded read set; ordinary audit skipped; triggered audit is PASS/VETO/CLARIFICATION_REQUIRED only |
| `P0-E4` | Cut default `task_intake.py`/`task_pipeline.py` to Envelope→Proposal→Authority; move reusable high-risk audit capability behind `semantic_audit.py` rather than wrapping the default SourceLedger route | delete default SourceLedger/claim/obligation prompt, schema, converters, call paths and graph-only tests | `P0-E2`–`P0-E3` | one default-path import/call sentinel and one optional-audit entry test | **completed (2026-08-05)** — default pipeline is Envelope→Proposal→optional Audit→Authority; SourceLedger/coverage/obligation compiler owners and graph-only tests deleted |
| `P0-E5` | Add `material_contracts.py` + `material_binding_policy.py`; extend `source_envelope.py` with prevalidated external exact-anchor ingress; make proposal/effect IDs carry risk-proportionate typed bindings and make TaskSpecAuthority validate SEND/PAYMENT/DELETE/SHARE field groups | remove SemanticAudit's “any material exact anchor passes” shortcut; exact SourceAnchor remains provenance-only; no graph/store/service or second semantic owner | `P0-E2`–`P0-E4` | three focused regressions: direct explicit send without span admitted; indirect attachment recipient clarifies; amount-only payment clarifies; page-authority and operation-downgrade rejection reuse the same suite | **completed (2026-08-05)** — direct/indirect/typed/confirmed binding forms, per-effect coverage, binding digest and typed clarification/policy failures are on the default authority path |

### P0-D — Required redlines without a test-building project

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-D1` | Add one data-driven `tests/architecture/test_runtime_redlines.py` covering omitted target/state fields, presentation invariance, conflict, multi-binding, raw-text execution read-set, output closure and lazy/index equivalence | consolidate equivalent scattered architecture assertions; do not create one test file per invariant | `P0-A4`, `P0-B4`, `P0-C5`, `P0-E4` | one parametrized matrix plus existing vertical behavior suites | **completed (2026-08-05; P1 boundary row added 2026-08-06)** — the shared matrix replaces the 3,935-line historical/source-count governance suite and now also guards recovery/committer/provider ownership without a second architecture test file |

## 6. P1–P5 execution table

### P1 — Direct plan, loop evaluation and control-plane containment

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P1-P1` | Make `task_plan_contracts.py::TaskPlan` store typed StepSpec directly and migrate canonical consumers | delete default StepSpec→SubgoalSpec→StepSpec converters; no canonical plan passes through SubgoalSpec | P0-B | one composite criterion/value round-trip sentinel + conversion absence scan | **completed (2026-08-05)** — canonical TaskPlan stores immutable StepSpec tuples directly; binder/projector round-trip and their path-only tests are deleted |
| `P1-P2` | Strengthen `TaskPlanAuthority` in `task_plan_contracts.py`; move planner policy to `task_planner.py` | binder/projector cannot admit or invent plan semantics | P1-P1 | reuse plan validation tests; one stale-observation rejection | **completed (2026-08-05)** — TaskPlanAuthority alone validates identity/DAG/budgets/current observation and state basis, then binds version/supersession; planner policy is authority-free in `task_planner.py` |
| `P1-P3` | Refactor `task_plan_flow.py` and `task_plan_progress.py` to facts/bindings/verified step records | delete completed-subgoal carry-forward and internal Subgoal progress ownership; any external adapter is one-way and expiry-bound | P1-P2 | one replan-preserves-facts vertical case + legacy progress import scan | **completed (2026-08-05)** — progress namespaces are facts/bindings/recent outcomes/durable evidence/VerifiedStepRecord; replan preserves records without reinserting steps |
| `P1-E1` | Add `verification/loop_evaluator.py` and `verification/step_completion.py`; integrate typed action/step/task results in `progress_phase.py` | mechanical provider/report cannot own root completion | P0-A, P1-P1 | one receipt≠effect≠step≠task vertical case | **completed (2026-08-05)** — pure LoopEvaluator produces distinct action-effect, step-completion and task-completion results; RuntimeCommitter remains the only writer |
| `P1-E2` | Implement four-state ObservationContinuation in `active_perception.py` and `perception_phase.py` | remove unconditional recapture/repeat paths | P0-B, P1-E1 | one parametrized continuation decision test | **completed (2026-08-05)** — REUSE/AUGMENT_TARGETED/RECAPTURE/WAIT_AND_RECAPTURE are perception-owned; fresh reusable captures flow into the next loop without immediate duplicate capture |
| `P1-C1` | Move `_available_action_recovery_kinds` and other failure classification from `coordinator.py` to `recovery_owner_dispatcher.py`/`recovery_phase.py` | Coordinator contains no domain failure policy | P1-E1 | existing recovery vertical suite; one forbidden-import/AST boundary | **completed (2026-08-06 closure)** — RecoveryStage owns classification, handoff exhaustion/error mapping and typed routing; RecoveryObservationEvaluator/RecoveryActionEvaluator own outcome verification and settlement; RuntimeCommitSession is lifecycle-only |
| `P1-C2` | Move RuntimeCommitSession lifecycle to `runtime_loop_phase.py` and read projections to new `runtime_state_projection.py`; leave writes in `runtime_committer.py` | RuntimeCommitter contains no evaluation/session/view algorithms | P1-E1 | existing coordinator/committer suite; no new scenario unless a failure is exposed | **completed (2026-08-06 closure)** — RuntimeCommitter's handoff/action recovery algorithms were deleted; it only validates and applies typed transitions/events/completion. ProgressStage is a 458-line façade over observation/repair, completion evaluation and TaskSkill collaborators; the 1,486-line legacy task_planning owner was deleted in favor of a 207-line edge adapter |

### P2 — Criterion and evidence

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P2-1` | Freeze canonical AST/operators in `criteria.py` and policy types in `verification/contracts.py` | no source-specific criterion subclasses or prose fallback | P1-E1 | one parametrized operator/policy matrix | **completed (2026-08-06)** — immutable Predicate/AllOf/AnyOf/Not/OpenSemantic contracts, registered vocabulary, orthogonal satisfaction/validity/assurance policy and pure typed recursive evaluation are canonical; unsupported/no-evidence remain UNSUPPORTED/UNKNOWN without model or prose fallback |
| `P2-2` | Add `verification/predicates.py` and focused providers under `verification/providers/` for structural, API/device/WoT, artifact and external evidence | providers return facts/metadata only | P2-1 | one provider contract suite with shared cases | **completed (2026-08-06)** — one provider contract is grouped into structural/resource/artifact modules; providers only select typed facts/metadata, material conflict remains CONFLICT, insufficient/policy-rejected evidence is typed UNKNOWN/STALE, and weak/model-only evidence cannot satisfy authoritative final recheck |
| `P2-3` | Add bounded recent causality and durable evidence contracts in `runtime_evidence.py`; expose logical namespaces through `task_plan_progress.py` | current observation facts do not become durable automatically | P2-1 | one STATE_HOLDS vs ACTION_CAUSED and one epoch-validity case | **completed (2026-08-06)** — current facts are epoch refs, recent causal outcomes require exact contract/receipt/pre/post/effect evidence and use a bounded index, and only typed artifact/resource/transaction/human records enter the small durable store; TaskProgress stores these records without observations or plan history |
| `P2-4` | Add optional `verification/providers/model.py` and human evidence adapter only after mechanical gaps are measured | high-risk external effect cannot complete with model-only evidence | P2-2 | only add tests when a real open-semantic use case is admitted | deferred |

### P2 authoritative crosswalk (2026-08-06)

The architecture plan uses seven P2 capability IDs; the execution table above
groups implementation slices and therefore is not a renumbering of those
capabilities.

| Architecture-plan ID | Execution-table row | Current status |
|---|---|---|
| `P2-1` Criterion AST | `P2-1` | implemented for step completion; strict `StepSpec` stores only canonical `CriterionExpr` and rejects legacy criteria, which are canonicalized at dated provider/benchmark ingress |
| `P2-2` CriterionPolicy | `P2-1` | implemented; current-contract and latest-final-recheck admission are enforced |
| `P2-3` causal evidence | `P2-3` | implemented and wired to the current contract; subject, before/after value, source, assurance and effect identity survive projection |
| `P2-4` three evidence locations | `P2-3` | implemented and consumed by `LoopEvaluator` |
| `P2-5` mechanical providers | `P2-2` | implemented and owned by `PredicateEvaluator`; surface and artifact admission are fail-closed |
| `P2-6` model/human providers | execution `P2-4` | deferred until a measured mechanical gap exists |
| `P2-7` OpenSemanticResolver | no execution row yet | demand-gated; `UNSUPPORTED` now routes to typed `OPEN_SEMANTIC_UNRESOLVED` clarification/gap without model fallback |

Overall **P2 core is complete**: the canonical mechanical step-completion
cutover and strict canonical ingress are closed. Action/task evaluation retain
their prior owners; P2-6 and the full P2-7 resolver remain demand-driven
extensions rather than core closure gates.

### P3 — Stable TaskSpec v2

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P3-1` | Define canonical TaskRequirement/InputBinding/OutputSpec and TaskSpec v2 in `task_intake.py`; fold P0-E5 material values into the canonical requirement/input payloads while retaining stable MaterialBinding refs/digest; admission remains in `task_spec_authority.py` | remove execution steps/action family/current UI facts and the temporary standalone `TaskSpec.material_bindings` bridge; do not add a second material registry or projector round-trip | P0-E, P2-1 | one lossless material requirement/output/binding schema case | **completed (2026-08-06; redline closure reverified)** — TaskSpec v2 owns only flat typed requirements, stable input bindings, output binding requirements, authorization refs and risk policy; all parallel legacy semantic fields and production readers are absent, and every material required output has an independent canonical `requirement:output:*` identity |
| `P3-2` | Add requirement/effect refs to StepSpec and authority validation in `task_plan_contracts.py` | reject steps with no TaskSpec trace or observation-grounded enabling need | P3-1, P1-P2 | one read-only and one effectful traceability case | **completed (2026-08-06)** — every StepSpec carries admitted requirement refs; effectful steps additionally require admitted effect authorization refs |
| `P3-3` | Bind SourceContextView to admitted requirement/material-binding/anchor IDs in `source_context.py`; return typed TaskSpecGap | no downstream patch/reinterpret path; direct explicit bindings do not acquire synthetic spans | P3-1 | one allowed planner context and one prohibited execution read-set case | **completed (2026-08-06; redline closure reverified)** — every requested anchor must belong to the requested admitted requirement, criterion, effect or input binding, the view returns `TaskSpec.source_binding_digest`, and execution consumers remain denied |
| `P3-4` | Delete the remaining compatibility-only `TaskSpec.source_claims`/`obligations` schema fields (the old IntentDraft/validator writer is already deleted; default P0-E production no longer populates, serializes or plans from graph fields) | keep optional audit storage isolated from planning/progress | P3-1–P3-3 | delete superseded compatibility schema tests; run retained intake suite | **completed (2026-08-06)** — compatibility fields, obligation owners, legacy criterion adapter and legacy task-plan provider are deleted; corrective P3/P4 final checkpoint: 866 tests passed |

### P4 — Rolling task planning and strict step choice

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P4-1` | Separate `task_plan_flow.py` from new `step_choice_flow.py`; define distinct typed requests/responses | neither flow accepts the other's authority object | P1, P3 | one import/signature boundary and one two-horizon vertical case | **completed (2026-08-06)** — TaskPlanFlow and StepChoiceFlow own separate typed horizons; boundary and two-stage reuse tests pass |
| `P4-2` | Move strict provider implementation from `generalist_planner.py` to focused `task_planner.py` and `step_choice_planner.py` | delete internal StateKernel/BrowserSnapshot/ActionChoiceBuilder signatures and converters; any external planner adapter translates one-way into typed requests and has an expiry | P4-1, P0-C | reuse planner behavior tests; delete legacy signature tests; add import-direction scan | **completed (2026-08-06; redline closure reverified)** — strict providers accept only TaskPlanningRequest/ChoicePlanningRequest; `PlanningStage` and default composition have no proposal fallback or duck-typed `select` compatibility, strict BrowserGym constructs `StrictTaskPlanner` plus `StrictStepChoicePlanner`, and the isolated historical comparison profile expires at P5-3 |
| `P4-3` | Add typed planning trigger/reuse/direct fast paths in `planning_phase.py` | no TaskPlanner call while current active step remains feasible | P4-2 | one parametrized trigger decision test | **completed (2026-08-06)** — typed initial/reuse/exhausted/infeasible/assumption/environment/task-revision triggers are explicit; active feasible plans reuse without a planner call and completed steps cannot be reinserted |
| `P4-4` | Make `planning_request_serializer.py` pure; stage deterministic narrowing, then paging, then typed retrieval only if measured | no request/context projector reconstructs authority | P4-2 | one serializer snapshot plus one page continuation case; no OpenResolver tests until enabled | **completed (2026-08-06)** — pure serializers expose only admitted/displayed IDs; 0/1/N choice behavior is deterministic, hidden IDs are rejected, and oversized truncated pages fail closed with CHOICE_SPACE_TOO_LARGE while paging remains disabled |

### P5 — Bounded state and legacy deletion

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P5-1` | Add lightweight `run_ledger.py` namespaces for facts, bindings, recent outcomes and durable evidence; keep distinct lifetimes | no separate database/service per namespace | P1–P3 | one lifetime/invalidation matrix | pending |
| `P5-2` | Finish `observation_store.py` + Catalog refs; shrink StateKernel to current identities and committed progress | no copied presentation or full observation graph in StateKernel | P0-B/C, P5-1 | one epoch/catalog stale-reference case | pending |
| `P5-3` | Remove only documented external/public compatibility adapters whose consumers have migrated; verify earlier slices already deleted all internal legacy owners | P5 cannot accept internal deletion debt from P0–P4; no parallel owner remains importable from production composition | all prior | adapter consumer inventory, architecture import scan and normal product vertical suite | pending |
| `P5-4` | Final containment pass over `coordinator.py`, `runtime_committer.py`, `execution_phase.py`, planners and builders | any remaining multi-owner file must split or carry a dated removal gate | P5-3 | reuse boundary tests; no test added for line count alone | pending |

## 7. Test portfolio policy

### 7.1 Current evidence and decision

Audit baseline on 2026-08-05:

| Measure | Current observation | Decision |
|---|---:|---|
| collected tests | 1476 | high count alone is not a deletion reason |
| test files | 130 | consolidate only where ownership/failure signal is duplicated |
| full local runtime | 14.62 seconds | currently acceptable; no performance-driven rewrite |
| test/source LOC | about 54k / 55k | maintenance concentration requires active retirement |
| `test_horizontal_architecture_governance.py` | 4044 lines / 124 tests / extensive source-text assertions | first cleanup target; it is itself a God test file |

The suite is not too slow, but parts are too historical and text-coupled. Test
cleanup therefore follows owner cutover and failure-localization value, not an
arbitrary target count.

### 7.2 Test admission rule

A new test is allowed only when all are named:

1. the concrete failure it localizes;
2. the canonical owner whose behavior failed;
3. why an existing test cannot cover it;
4. the cheapest useful level: contract, focused behavior, or vertical path;
5. its retirement condition if it protects a compatibility seam.

Default per production slice: reuse the affected suite, add at most one
contract/boundary sentinel and one vertical behavior case. More requires a
specific uncovered failure matrix, not a desire for exhaustive permutations.

Do not add tests solely to freeze prose, line counts, call-site counts, current
class names, or historical admission wording when an import boundary, typed
contract, manifest rule, or real behavior test can locate the same failure.

### 7.3 When to run what

| Checkpoint | Required checks |
|---|---|
| inner edit loop | the one focused test that exposes the current failure |
| task row complete | focused owner suite + relevant boundary sentinel |
| slice cutover | affected contract/vertical/safety suites, deletion/import scan, then full pytest once after the default-route switch |
| phase checkpoint, commit or push | reuse the fresh cutover result when no file changed; otherwise rerun full pytest, Ruff and diff checks |

Full pytest is not required after every small edit. Repeated green runs without
a changed failure surface are test activity, not delivery evidence.

### 7.4 Cleanup queue

| ID | Scope | Action | Exit |
|---|---|---|---|
| `T0` | `tests/test_horizontal_architecture_governance.py` | keep current authority/import/write boundaries; remove archived-record prose checks; consolidate amendment text checks into one data-driven current-authority matrix; split remaining tests by runtime/planning/documentation ownership only after pruning | no active test fails solely because immutable historical prose changed; no replacement test explosion |
| `T1` | tests bound to SourceLedger, Subgoal, old completion and planner compatibility | delete in the same slice that removes the owner; retain only explicit adapter contract until its dated removal | every compatibility test names a live adapter and removal gate |
| `T2` | repeated model-port local HTTP fixtures | share transport fixture/fake clock; keep one real local transport sentinel; remove fixed shutdown/backoff cost from unit cases when this module is next touched | retry semantics remain covered without repeated wall-clock waits |
| `T3` | large behavior test files | consolidate shared setup and parameterize equivalent failure matrices during the owning production slice, not as a standalone rewrite | fewer duplicated fixtures/assertions with unchanged boundary coverage |

`T0` is time-boxed and may run as the one independent horizontal containment
slice. `T1`–`T3` are performed only while their production owner is already
being changed; they must not delay a correctness cutover to chase test count.

## 8. Slice admission and completion checklist

Before starting:

- canonical owner, input and typed output are named;
- exact files to create/modify/delete are listed in the row;
- legacy owner and same-slice deletion/isolation gate are named;
- canonical modules do not import legacy modules or compatibility adapters;
- no new→old→new conversion, dual read/write or shadow owner is introduced;
- no target file receives a second unrelated responsibility;
- test action is `REUSE`, `ADD-SENTINEL`, `ADD-VERTICAL`, `CONSOLIDATE`, or
  `DELETE-WITH-OWNER` rather than an open-ended “add tests”.

Before marking done:

- default composition calls only the canonical owner;
- legacy code and its tests are deleted or behind an explicit adapter/removal gate;
- every surviving adapter is external-ingress-only, one-way and before its last-allowed slice;
- TaskSpec authorization, approval binding and completion authority did not expand;
- receipt, effect, step, plan and task results remain distinct;
- Planner/Executor/Evaluator do not write StateKernel;
- Coordinator and RuntimeCommitter contain no new domain algorithm;
- focused and slice-level checks identify failures at the owning boundary;
- full suite ran once at the cutover checkpoint;
- implementation status and immutable evidence bind the exact revision.

## 9. Current execution order

| Order | Slice | Reason |
|---:|---|---|
| 1 | `P0-A` | close false-completion authority first |
| 2 | `P0-B` | establish canonical current state before rebuilding choices |
| 3 | `P0-C` | establish Runtime-owned legal action space and contract binding |
| 4 | `P0-E` | replace extraction-heavy default intake without coupling it to planning |
| 5 | `P0-D` | freeze the completed P0 boundaries in one compact matrix |
| 6 | `P1`–`P5` | follow dependency order in §6 |

P0-A and P0-B may be prepared independently, but only one vertical authority
cutover is admitted at a time. `T0` may run beside one vertical slice because it
does not change production behavior.

## 10. Historical detail

The pre-consolidation 3,203-line queue is preserved at
[current-implementation-plan-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/current-implementation-plan-pre-consolidation.md).
It is implementation history, not the active scheduler.

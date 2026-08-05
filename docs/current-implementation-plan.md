# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Target:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Migration authority:** [Architecture evolution plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
> **Implementation truth:** [Implementation Status](implementation-status.md)

## 1. Queue rule

This file contains only active and next work. Completed/historical slices belong
to immutable change-admission/evidence records or the archive. A slice can move
to `done` only with code, focused tests, deletion/isolation evidence, and an
updated implementation-status entry.

At most one vertical authority migration and one independent horizontal
containment slice may write production behavior at a time.

## 2. Current documentation authority

```yaml
authoritative_architecture: docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md
authoritative_evolution_plan: docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md
documentation_manifest: docs/documentation-manifest.yaml
default_source_target: SourceEnvelope_plus_selective_SourceAnchor
optional_audit_target: SemanticAudit_veto_or_clarify_only
semantic_context_target: bounded_read_only_SourceContextView
semantic_write_owner: TaskSpecAuthority_only
requirement_identity_target: canonical_TaskRequirement_refs
planning_target: observation_grounded_TaskPlan_of_StepSpec
choice_target: full_Runtime_ActionChoiceCatalog_before_ChoicePage
choice_presentation_target: bounded_semantic_context_without_execution_bindings
verification_target: loop_native_typed_LoopEvaluator
completion_semantics_owner: TaskCompletionEvaluator
required_output_target: materialized_and_source_bound_before_completion
completion_commit_owner: RuntimeCommitter_only
```

## 3. Documentation baseline

The 2026-08-05 authority consolidation is complete. Current documents are
classified by `documentation-manifest.yaml`; superseded prose is indexed under
`docs/archive/`; evidence and change-admission records remain immutable; and
the deliberately simple gate checks only lifecycle/path coverage, authority
uniqueness, redirects, and maintained relative links.

This documentation-only baseline changed no Runtime behavior and claims no
target implementation.

## 4. Next production migration queue

| Order | Slice | Current state | Required exit |
|---:|---|---|---|
| 1 | `P0-A` completion correctness | pending substitutive cutover | full TaskSpec.success + required OutputSpec closure; no receipt/latest-report/plan-exhausted/prose completion |
| 2 | `P0-B` canonical observation | pending substitutive cutover | Runtime semantic consumers read one canonical observation built from capture |
| 3 | `P0-C` Runtime-owned full Catalog | pending substitutive cutover | Catalog exists before model request; presentation limits do not change digest |
| 4 | `P0-E` thin source path | pending substitutive cutover | ordinary intake builds SourceEnvelope without claim/obligation coverage |
| 5 | `P0-D` combined redlines | pending | OBS/SOU/VER plus NLI raw-text read-set, TaskSpecGap, requirement traceability, ChoicePresentation and output-closure regressions |

`P0-A`, `P0-B`, `P0-C`, and `P0-E` are separate authority cutovers. They may be
developed independently only when they do not create simultaneous owners.

## 5. Subsequent queue

1. `P1`: direct TaskPlan<StepSpec>, requirement refs/dependency cleanup, loop-native evaluation, observation continuation.
2. `P2`: typed semantic AST, bounded OpenSemanticResolver, minimum CriterionPolicy, bounded evidence providers.
3. `P3`: TaskSpec v2 admission/revision, canonical TaskRequirement identity, required OutputSpec, selective source binding and SourceContextProjector write barrier.
4. `P4`: rolling Task Planner, bounded SourceContextView exception, semantic ChoicePresentation and strict ChoicePlanningRequest port.
5. `P5`: bounded stores and legacy deletion.

## 6. Admission checklist for every slice

- canonical owner and legacy owner are named;
- one-in/one-out deletion or isolation gate is explicit;
- TaskSpec authorization cannot expand;
- source-assisted reasoning references existing canonical IDs and returns TaskSpecGap for missing meaning;
- action construction/gates/execution/evaluation receive no raw request or SourceContextView;
- required structured outputs are not replaced by Planner prose;
- Runtime candidate semantics do not depend on model presentation limits;
- receipt, effect, step, plan, and task results remain distinct;
- Planner/Executor/Evaluator do not write StateKernel;
- uncertain external effects are never blindly retried;
- benchmark identifiers do not enter production logic;
- status claims bind to an immutable revision and reproducible evidence.

## 7. Historical detail

The pre-consolidation 3,203-line queue is preserved at
[current-implementation-plan-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/current-implementation-plan-pre-consolidation.md).
It is implementation history, not the active scheduler.

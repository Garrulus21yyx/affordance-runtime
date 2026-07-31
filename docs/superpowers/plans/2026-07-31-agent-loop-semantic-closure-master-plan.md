# Agent Loop Semantic and Architecture Closure Master Plan

> **For Codex:** This is the controlling implementation plan. Execute replacement/deletion units in order, keep the conformance ledger current, and stop a unit when a blocking invariant fails.

**Goal:** Reach the reviewed optimized Agent Loop—not merely improve the current BrowserGym score—by completing canonical diagnostics, progress liveness, typed interaction semantics, generic grounding/choice coverage, plan repair, and final compatibility deletion while preserving five stages and one State/Trace writer.

**Normative inputs:**

- `docs/reviews/2026-07-31-coordinator-slimming-and-behavior-priority.md`
- `docs/reviews/2026-07-31-optimized-agent-loop-target-review.md`
- `docs/change-admission/sar-9-phase-architecture-closure.yaml`

## 1. Ambiguity resolution

The reviews contain historical names and one responsibility conflict. They are resolved once here; implementations may not exploit both interpretations.

| Topic | Canonical decision |
|---|---|
| `ActionStage` vs `ExecutionStage` | The existing `ActionStage` is the single canonical stage. “ExecutionStage” in the review denotes this same contract/preflight/execute boundary. No alias, wrapper, or sixth stage is added. |
| Recovery routing | `RecoveryStage` accepts only `FailureOwner.RUNTIME_RECOVERY`. AgentLoop's single owner router handles Progress, Step Planner, Task Planner, User, and Terminal handoffs. |
| Five-stage consolidation timing | The structural five-stage cutover already present at the calibrated HEAD is preserved. Remaining purity/compatibility deletion happens after semantic clusters; old phase facades are not recreated. |
| Stage result | Reuse `stage_protocol.StageResult`. A second canonical result, compatibility projection, or facade result is forbidden. |
| Diagnostics | `PlanningTurnEvaluated` and `PostActionEvaluated` are canonical runtime events, not benchmark-only telemetry. Reports are projections of them. |

## 2. Permanent loop invariants

Every implementation unit must prove:

1. Coordinator directly knows exactly five stages plus committer/result infrastructure.
2. Stage-to-stage import edges are zero.
3. Stages receive immutable input objects and do not import/mutate live `StateKernel` or write `TraceDag`.
4. `RuntimeCommitter` is the only State/Trace writer.
5. Strict planning remains 0 typed failure / 1 Runtime auto-select / N model choice-id selection.
6. Effect, active-step progress, and task completion are independent evaluations.
7. Same step + relevant state + semantic choice + effect result permits at most one ordinary attempt.
8. Budget exhaustion is never the first detector of a repeated verified-effect loop.
9. Core behavior contains no benchmark task id, seed, title, or BrowserGym import.
10. A new canonical owner deletes or disconnects the previous default owner in the same unit.

## 3. Anti-specialization proof

A fix is inadmissible when its only evidence is a named benchmark episode. Each behavioral unit requires all of:

- one generic non-BrowserGym integration fixture;
- one renamed/reordered/metamorphic variant or property test;
- invariant assertions on typed inputs/outputs rather than trace string matching alone;
- a gate proving `src/affordance_runtime` outside `benchmarks/` contains no MiniWoB task identifiers or seed branches;
- targeted BrowserGym episodes only as external behavioral confirmation;
- clean 6x2 after the generic tests pass.

Task names may appear in tests, matrices, commands, and evidence documents. They must not influence production dispatch.

## 4. Execution units

### M0 — Current-HEAD baseline and canonical diagnostics

- Recalibrate LOC, imports, stage edges, writer count, compatibility paths, StateKernel history fields, clean 6x2, and fresh failure clusters at the exact implementation revision.
- Implement `PlanningTurnEvaluated` and `PostActionEvaluated` through the existing `StageResult.events`/committer path.
- Replace stale PlannerContext-derived report metrics; separate `root_failure_phase` and `terminal_status`.
- Acceptance: all scheduled episodes have a first owner; provider and unclustered counts are explicit; no benchmark-only event schema.

Detailed first-unit plan: `docs/superpowers/plans/2026-07-31-progress-credit-liveness-diagnostics.md`.

### M1 — Progress credit and liveness

- Resolve and bind the active progress target before execution.
- Preserve active-step criterion/requirement IDs independently of task-terminal outcome.
- Reconcile post-action facts against the known active step.
- Replace the current `PlannerProgressBlocked -> REPEAT_OBSERVATION` loop with a typed Progress-owner invariant failure when no legitimate state change/reconciliation path remains.
- Acceptance: generic invariants pass; the three known episodes dispatch no repeated successful action and do not exhaust budget; clean 6x2 is 12/12.

### M2 — Canonical InteractionIntent cutover

- Add one immutable typed semantic union for Element, Collection, Relation, Region, and ValueExpr; add `StepSpec.interaction`.
- New PlanCandidate admission must produce typed intent.
- Migrate ActionChoiceBuilder to typed intent and `GroundingResult`.
- In the same production cutover, remove the default import/call of the compatibility subject-string target resolver. Old artifact replay may use an isolated adapter not imported by the default composition root.
- Acceptance: deterministic roundtrip, source provenance retained, one canonical resolver, no parallel TargetIntent view, default subject parser absent.

### M3 — Element semantics

- Implement generic identity, role/label, focus, editable value, date/value binding and direct element actions from typed facts.
- Cover renamed and reordered controls, not named tasks.
- Acceptance: all choices reference grounded targets, supported actions, and fully bound parameters; one choice never invokes the model.

### M4 — Collection and dynamic/enabling semantics

- Implement scoped ordinal/cardinality, collection membership, pagination/reveal/scroll/tree expansion as typed direct or enabling choices.
- Enabling action must expose a missing target/capability and be invalid once its enabling fact is already satisfied.
- Acceptance: deterministic grounding; ambiguous collections remain typed ambiguous; repeated enabling action is liveness-blocked.

### M5 — Data/read and information actions

- Implement ValueExpr and information choices for visible data extraction, copy/transform/read relationships and typed value transfer.
- Information actions may acquire facts but cannot claim task completion.
- Acceptance: no arbitrary page text becomes an executable target; sensitive/bounded-value rules remain enforced.

### M6 — Relation semantics

- Implement typed source/destination relation grounding and drag/drop choices without task-family conditionals.
- Acceptance: both endpoints come from GroundingResult, capability is explicit, swapped/ambiguous relations fail typed and closed.

### M7 — Spatial semantics

- Implement RegionIntent only behind an explicit spatial capability/profile and calibrated coordinates/evidence.
- No DOM-only fallback may pretend a spatial target was resolved.
- Acceptance: capability missing remains distinct from absent; default non-spatial profile does not fabricate choices.

### M8 — TaskPlan and Intent admission repair

- Enforce outcome-based steps; action instructions are repaired/rejected at admission rather than interpreted as hidden free actions.
- Ensure every source unit is covered by a typed criterion/interaction or a typed clarification/failure.
- Acceptance: deterministic admission, preserved provenance, no model finish/ask-user authority leakage.

### M9 — Final purification and deletion

- Confirm Coordinator imports only the canonical five stages and at most seven direct collaborators.
- Delete default PlannerDecision/reflection/three-argument Planner compatibility, PlannerContext provider path, default ODG shadow, legacy subject resolver import, StateKernel history collections/aliases, and legacy public exports listed by SAR-9.
- Keep complete history in Trace/ArtifactStore only.
- Require negative orchestration LOC and dependency-edge deltas; no new facade/module unless the replacement/deletion rule is met.

## 5. Per-unit verification order

1. RED unit/invariant tests.
2. Focused subsystem tests.
3. Generic non-BrowserGym integration and metamorphic/property tests.
4. Architecture/import/writer/anti-specialization gates.
5. Targeted two-seed external replay for the affected semantic cluster.
6. Clean 6x2; stop unless 12/12.
7. Full pytest for a completed production cutover with physical deletion.
8. Ruff, core mypy, `uv build`, `git diff --check`.
9. Fresh 30x2 only after M1, M4, M8, and M9, or when a new systemic cluster must be measured.

## 6. Continuous conformance ledger

Update this table with exact revision and evidence after every completed unit. “Partial” cannot be promoted.

| Gate | Baseline | Required exit | Current status |
|---|---:|---:|---|
| top-level stages | 5 | 5 | verify each unit |
| stage-to-stage imports | measure M0 | 0 | pending |
| mutable State/Trace writers | measure M0 | 1 | pending |
| default compatibility adapters | measure M0 | 0 | pending |
| core benchmark/task specializations | measure M0 | 0 | pending |
| progress-credit liveness cycles | 3 known | 0 | pending |
| clean 6x2 | 12/12 at prior clean candidate | 12/12 same revision | pending |
| fresh 30x2 | 12/60, 48 failures at prior clean candidate | DoD in review archive | pending |

## 7. Stop conditions

Stop and diagnose before proceeding when any of these occurs:

- clean 6x2 falls below 12/12;
- a change requires a task id/seed branch or benchmark import in core;
- a new default fallback masks typed absent/ambiguous/capability-missing state;
- a stage writes State/Trace or imports another stage;
- old and new canonical paths both remain active;
- a reported success depends only on terminal string mapping or forbidden-token assertions;
- targeted success cannot be reproduced by a generic or metamorphic test.

## 8. Final promotion gate

Promotion remains held until the same immutable revision passes full pytest, Ruff, core mypy, build, architecture/import/LOC gates, clean 6x2, and fresh 30x2 under the declared policy. No official score is claimed without explicit authorization.


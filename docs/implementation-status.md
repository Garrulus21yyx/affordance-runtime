# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-07
> **Reviewed baseline:** `agent/migrate-runtime-components@8d7cfd6b7d43c72f9b45bb4144a62553d90c23a8`
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Active queue:** [Current Implementation Plan](current-implementation-plan.md)

## 1. Executive status

The new unified-world/short-loop target is **not implemented**. Current code is
a stable transactional GUI Runtime baseline whose control path is centered on:

```text
SourceEnvelope
→ TaskSpecAuthority / TaskSpec
→ mandatory TaskPlan and action catalog
→ ActionContract materialization and gates
→ PreparedDispatch / permit / ExecutionAttempt
→ executor receipt
→ fresh observation and LoopEvaluator
→ RuntimeDelta family
→ RuntimeCommitter / StateKernel / TraceDag
→ typed recovery protocol
```

This description is current code truth, not the desired architecture.

The documentation target has now moved to:

```text
TaskGoal
→ unified observe
→ optional milestones / LocalObjective
→ Runtime-owned ActionSpace
→ semantic ActionIntent
→ human confirmation when needed
→ current BoundActionRequest
→ execute once (or admitted local batch) → ActionResult
→ fresh observation
→ independent action/task evaluation
```

The docs-only P5-A0 slice is complete in the current working tree and changes
no production behavior.

## 2. Valuable foundations already implemented

| Foundation | Current truth | Target use |
|---|---|---|
| `UnifiedObservation` | canonical targets, bindings, state facts, coverage, conflicts, freshness, predicate evidence | evolve into `WorldObservation` plus compact `AgentWorldView` |
| `GroundingCandidate` | represents DOM, AX, SVG, SoM/Visual, WoT, API, and Device payloads with executor/freshness/actions/evidence | retain as surface binding foundation; add CLI adapter contract later |
| semantic entity fusion | multiple source candidates can resolve to one canonical target | retain as `WorldFusion` core |
| route planning | current bindings can be selected by backend support and route policy | simplify behind unified world interface |
| active perception | current/targeted capture and evidence-gap handling exist with budgets | prioritize and generalize across surfaces |
| executor routing | DOM, Visual, and WoT executors share a routed execution entry | narrow to `BoundActionRequest → ActionResult` |
| post-action observation | the loop can acquire fresh evidence after execution | make unconditional target invariant |
| evaluation separation | receipt is not effect evidence; step and task completion are separately evaluated | retain and simplify into action/task evaluators |
| output materialization | local required artifacts must exist and match SHA/content expectations | retain as optional strict evaluation behavior |

## 3. Existing baseline guarantees to preserve

At the reviewed branch, the P4 MVP baseline has evidence for:

1. finalized immutable action identity before execution;
2. approval/execution identity equality on the current contract path;
3. stale snapshot/page/target rejection with zero Executor calls;
4. verifier-backed completion rather than receipt-only completion;
5. no blind retry after an uncertain effectful execution;
6. required local artifact existence and digest matching;
7. backend-neutral semantic choice before concrete route binding.

These guarantees are retained as migration regression properties. Their current
implementation through ActionContract hashes, permits, deltas, or commit
ordering does not make those mechanisms target contracts.

## 4. Target gaps

| Area | Current code | Missing for target |
|---|---|---|
| task entry | mandatory admitted TaskSpec and source-authority path | lightweight TaskGoal; optional strict EvaluationSpec/ingestion |
| planning | TaskPlan is part of the normal authority flow | optional TaskPlan<Milestone>, LocalObjective, fact-driven full replacement |
| model view | catalog/choice protocols carry authority and revision machinery | compact observation-bound ActionSpace |
| action | ActionContract combines semantic action, binding, proof, approval, verification, recovery, and audit data | ActionIntent separated from small observation-bound BoundActionRequest |
| state | StateKernel plus many typed deltas and central committer | small serial AgentLoopState |
| recovery | broad failure-owner/kind/dimension transaction protocol | continue/reobserve/replan/ask/confirm/done/failed loop decisions |
| trace | ordered trace participates in dispatch/commit semantics | optional TurnRecorder telemetry |
| adapters | BrowserSession is a special perception path; WoT/device often use custom glue; CLI has no symmetric target path | symmetric DOM/AX/Visual/SVG/WoT/API/Device/CLI SurfaceAdapter sessions |
| evaluation | correct separation exists inside a large progress/control path | focused ActionEvaluator, TaskEvaluator, LoopPolicy |
| confirmation | configured tokens/grants can emulate approval and current baseline binds exact contract hash | semantic ActionIntent/risk/consequence confirmation; fresh binding may change without semantic re-confirmation |
| action batch | no target bounded-batch contract | later max-three, low-risk, same-surface, no-observation-barrier optimization |
| long horizon | rich planning/recovery machinery but no new target-style bounded context proof | optional milestones, LocalObjective, recent turns/evidence summary, 20–50 turn acceptance |
| memory/skill | historical System-1/TaskSkill ideas exist | currentness-checked BindingCache and offline-evaluated Skill sidecars |
| generalization proof | several tests prove shared old pipeline entry; some visual/WoT coordinator cases end FAILED/ABORTED | same-task positive DOM/AX/Visual/SVG/WoT completion matrix plus API/Device/CLI conformance |

## 5. P5-0E baseline disposition

P5-0E added further commit protocol, dispatch lifecycle, artifact/receipt
lineage, and owner-boundary hardening up to the reviewed HEAD. It is retained as
baseline code and historical evidence; it is **not** the next implementation
direction. Frozen read-view closure, more typed deltas, durable ledger,
checkpoint/resume, and broader transaction recovery are no longer admission
requirements.

Do not interpret “frozen” as “deleted” or “new path implemented.” Code removal
starts only after positive short-loop vertical slices and a default-path cutover.

## 6. Validation evidence at the reviewed baseline

The latest committed P5-0E review reports:

- `1036 passed`;
- Ruff passed;
- mypy passed over 192 source files;
- `git diff --check` passed.

Earlier P4 closure evidence recorded a 21-run local core profile and stable Task
API 3/3 at earlier exact revisions. Those results remain historical evidence and
must not be promoted to the reviewed HEAD without rerunning them. In particular,
the exact reviewed HEAD does not yet have a freshly recorded complete official
21-run benchmark and stable Task API 3/3 result.

Evidence records are revision/profile scoped. Documentation consolidation does
not refresh test or benchmark evidence.

## 7. Current status summary

```text
P4 safety baseline: retained
P5-0E transaction work: frozen; no further expansion
P5-A0 documentation consolidation: complete in current working tree
P5-A1–A4 new contracts/code: not started
Unified SurfaceAdapter cutover: not started
E2E AgentLoop default path: not started
Positive DOM/AX/Visual/SVG/WoT matrix: not complete
Long-horizon/ActionBatch/Memory-Skill target work: not started
Old transactional core deletion: not started
```

Historical detailed ledgers remain under [archive](archive/) and
[evidence](evidence/README.md); they do not define current target semantics.

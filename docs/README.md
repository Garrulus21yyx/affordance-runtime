# Documentation Index

> **Lifecycle:** CURRENT DISCOVERY ENTRYPOINT
> **Machine-readable index:** [documentation-manifest.yaml](documentation-manifest.yaml)
> **Lifecycle policy:** [Documentation Governance](documentation-governance.md)

Use this page as the starting point for human maintenance and AI retrieval.
Search ranking, filename recency, or the word “architecture” does not establish
authority.

## 1. Current target authority

Exactly two documents define the target and its migration:

1. [Task Contract-Centered Authoritative Runtime Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
2. [Task Contract-Centered Runtime Architecture Evolution Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

Authority is unique per question: the first document alone owns target
semantics/invariants; the second alone owns migration order and exit gates;
[Implementation Status](implementation-status.md) alone owns current code
truth; [Current Implementation Plan](current-implementation-plan.md) alone owns
the active scheduler. Historical rationale in the evolution plan never
overrides current implementation truth.

Core target order:

```text
SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpec
→ canonical observation → semantically admitted TaskPlan<StepSpec>
→ full ActionChoiceCatalog → validated ActionSelection
→ capture fresh preflight O1
→ materialize and freeze complete executable ActionContract H
→ Task/Policy/Capability admission over H
→ exact Approval of H when required
→ snapshot/page/target/expiry preflight
→ serial Execute of H with approved_hash == executed_hash
→ typed transport receipt → independent effect settlement
→ post-action observation → LoopEvaluator
→ actual OutputMaterialization when required → TaskCompletionEvaluator
→ RuntimeCommitter
```

Current MVP scope is one process, one run, one coordinator, one browser
session, and one active ActionContract; trusted in-process components serialize
state mutation, approval consumption, and effectful execution. This is a
GUI-agent research Runtime with complete vertical loop and limited horizontal
breadth, not a production-grade multi-tenant security kernel.

The TCB includes Runtime-selected/configured in-process adapter and provider
implementation code. External content observed or returned by that trusted code
is still untrusted data and cannot supply TaskSpec, capability, approval,
policy, completion, or control-flow authority.

`SourceContextView` is an optional read-only side input for the allowlisted
Task Planner/OpenSemanticResolver/ClarificationComposer semantic consumers. It
does not add a stage or authority to the production chain. TaskSpecAuthority is
the only accepted-meaning writer; execution and completion paths remain
raw-text-free.

Read the architecture in layers: §0 freezes the core laws and amendments;
contract/authority sections define normative semantics; migration and Gate
sections define rollout and verification. Logical Catalog/observation
completeness may use lazy indexes and refs, and logical authorities default to
in-process composition rather than one service/store per name.

DOM, AX, Visual, SVG, WoT, API, and Device are composable surfaces within that
single chain: one canonical target retains their current bindings/conflicts,
Planner selects the semantic action, and the route owner inside
`ActionTransactionMaterializer` selects the current backend/binding. This is an explicit surface vocabulary clarification,
not an additional authority or production-completion claim.

## 2. Current implementation truth and work

- [Project Plan](project-plan.md): durable P0–P5 product roadmap.
- [Current Implementation Plan](current-implementation-plan.md): granular P0–P5 cutover table, module/deletion ownership, Anti-God-File rules, and minimal test policy.
- [Implementation Status](implementation-status.md): factual current-vs-target state.

Target authority does not imply implementation. Status/history does not redefine
the target. The 2026-08-07 MVP reset implements five P4 code invariants: final
immutable contract, approval/execution hash equality, stale-preflight zero calls,
verifier-backed completion, and uncertain-effect no-blind-retry. The current
status is **P4 CLOSED (MVP scope)**. The core benchmark is
integrated closure evidence for those five invariants and the default route,
not a sixth invariant. Focused/full/static checks and a fresh core benchmark
now pass, so P5 admission is unblocked; P5 itself has not started.
Tenant/profile proof, revocation linearizability, global permits/fencing,
attempt-bound collateral, and immutable multi-suite attestation are future
hardening rather than P5 blockers.

## 3. Maintained normative documents

| Responsibility | Document |
|---|---|
| architecture admission and migration | [Architecture Governance Track](architecture-governance-track.md) |
| module/state ownership | [Responsibility Containment Boundary](responsibility-containment-boundary.md) |
| Runtime product boundary | [Runtime-First Architecture Boundary](runtime-first-boundary.md) |
| benchmark neutrality | [Benchmark Governance Boundary](benchmark-governance-boundary.md) |
| source intake, TaskSpec, TaskPlan, Planner | [Task Intake and Generalist Planner](task-intake-and-planner.md) |
| canonical perception and typed recovery | [Active Perception and Online Recovery](active-perception-and-online-recovery.md) |
| loop sequencing and feedback | [Orchestration and Live Feedback](orchestration-and-feedback.md) |
| trace, typed evaluation, evidence | [Trace and Evaluation](trace-and-evaluation.md) |
| external parent-agent/API boundary | [Integrations](integrations.md) |
| controlled offline evolution | [Harness Evolution](harness-evolution.md) |
| evaluation profiles and claims | [Benchmark Plan](benchmark-plan.md) |

## 4. Maintained references

- [Architecture entrypoint](architecture.md)
- [Pricing extraction scenario](scenarios/pricing-extraction.md)
- [Reversible settings scenario](scenarios/settings-update.md)
- [Approval-gated export scenario](scenarios/approval-gated-report-export.md)
- [ActionContract digest threat model](security/action-contract-digest-threat-model.md)

## 5. Immutable records

- [Evidence](evidence/README.md) records results for exact revisions/profiles.
- `change-admission/` records scoped architecture and promotion decisions.

These records remain in place even when old. They do not define current
architecture semantics.

## 6. Archive

- [Superseded records consolidated on 2026-08-05](archive/superseded-2026-08-05/README.md)
- [Earlier records superseded on 2026-07-29](archive/superseded-2026-07-29/README.md)
- `archive/sar-9-phase-extraction/`: immutable historical extraction records.

The 2026-08-05 archive includes dated audits, completed M8 logs, old
superpowers plans/specs, the fixed-baseline deep-dive report, historical
origin/comparison notes, and pre-consolidation status snapshots.

Archived documents may be cited as history but cannot be used as current
authority, active queue, or implementation status.

## 7. Maintenance rule

When the architecture changes, update together:

1. target architecture and evolution plan;
2. implementation status and active queue;
3. affected normative contract documents;
4. this index and the manifest;
5. archive pointers for replaced documents;
6. the simple documentation governance tests.

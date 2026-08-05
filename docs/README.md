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

Core target order:

```text
SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpec
→ canonical observation → TaskPlan<StepSpec> → full ActionChoiceCatalog
→ ActionContract + gates → Execute → post-action observation
→ LoopEvaluator → RuntimeCommitter
```

## 2. Current implementation truth and work

- [Project Plan](project-plan.md): durable P0–P5 product roadmap.
- [Current Implementation Plan](current-implementation-plan.md): active and next queue only.
- [Implementation Status](implementation-status.md): factual current-vs-target state.

Target authority does not imply implementation. Status/history does not redefine
the target.

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

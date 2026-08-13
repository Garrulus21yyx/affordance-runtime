# Documentation Index

> **Lifecycle:** CURRENT DISCOVERY ENTRYPOINT
> **Machine-readable index:** [documentation-manifest.yaml](documentation-manifest.yaml)
> **Lifecycle policy:** [Documentation Governance](documentation-governance.md)

This page is the single documentation discovery path. It does not duplicate
architecture contracts, migration phase state, or implementation status.
Filename dates, search rank, and historical backlinks never establish
authority.

## 1. Authority map

| Question | Sole document |
|---|---|
| What is the one target execution architecture? | [Canonical GUI Agent Execution Architecture](task-execution-authority-map.md) |
| In what order is the current implementation cut over? | [Canonical GUI Agent Authority Cutover Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md) |
| What does reviewed code do now? | [Implementation Status](implementation-status.md) |
| What is the active work queue? | [Current Implementation Plan](current-implementation-plan.md) |
| What is the durable product direction? | [Project Plan](project-plan.md) |

The target chain, summarized only for discovery, is:

```text
TaskGoal
-> admitted TaskSpec
-> initial WorldObservation
-> admitted TaskPlan<StepSpec.execution>
-> active StepExecutionState resolved against the current observation
-> current ActionChoiceCatalog
-> disposable AgentContext + action/control tools
-> action-only AgentDecision
-> admission / risk / currentness / private binding
-> execute once -> fresh observation -> evaluations
-> step/plan/task progress
```

The authoritative architecture contains the exact owners, contracts, state
transitions, exceptional outcomes, projection rules, evidence lifecycle, and
verification properties. This summary must never be used as an alternate
contract.

## 2. Bounded policies and contracts

| Responsibility | Document |
|---|---|
| architecture change admission | [Architecture Governance Track](architecture-governance-track.md) |
| documentation lifecycle and authority | [Documentation Governance](documentation-governance.md) |
| module ownership and dependency direction | [Responsibility Containment](responsibility-containment-boundary.md) |
| Runtime/model/adapter/benchmark boundary | [Runtime-First Boundary](runtime-first-boundary.md) |
| benchmark neutrality | [Benchmark Governance Boundary](benchmark-governance-boundary.md) |
| task intake, planning, and action-only Agent boundary | [Task Intake and Planner](task-intake-and-planner.md) |
| world observation and bounded recovery | [Active Perception and Online Recovery](active-perception-and-online-recovery.md) |
| serial loop sequencing | [Orchestration and Live Feedback](orchestration-and-feedback.md) |
| result/effect/task evaluation and telemetry | [Trace and Evaluation](trace-and-evaluation.md) |
| parent-agent/API integration | [Integrations](integrations.md) |
| offline adaptation | [Harness Evolution](harness-evolution.md) |
| positive cross-surface evaluation | [Benchmark Plan](benchmark-plan.md) |

Each document owns only its named bounded responsibility. It may refine that
scope but may not restate the whole execution architecture or introduce a new
authority owner.

## 3. Maintained references

- [Architecture entrypoint](architecture.md)
- [Evidence index](evidence/README.md)
- [Pricing extraction baseline scenario](scenarios/pricing-extraction.md)
- [Reversible settings baseline scenario](scenarios/settings-update.md)
- [Approval-gated export baseline scenario](scenarios/approval-gated-report-export.md)
- [Legacy ActionContract digest threat model](security/action-contract-digest-threat-model.md)

Review, plan, and evidence records under `reviews/`, `superpowers/plans/`, and
`evidence/runs/` are revision-scoped records. Their presence does not make
their design conclusions current. Use
[documentation-manifest.yaml](documentation-manifest.yaml) to distinguish
current, immutable, redirected, and archived material.

## 4. Archive

- [2026-08-05 archive](archive/superseded-2026-08-05/README.md)
- [2026-07-29 archive](archive/superseded-2026-07-29/README.md)
- `archive/sar-9-phase-extraction/` preserves extraction history.

The retired task-contract architecture filename is a redirect only. Superseded
records remain useful as evidence, but never as compatibility paths or current
owner definitions.

## 5. Maintenance rule

Before changing an owner, state, lifecycle, planning/action schema, projection,
or benchmark path:

1. compare the proposal with the canonical architecture owner table and
   invariants;
2. record the change-impact row required by that architecture;
3. change the smallest coherent owner and delete the displaced path;
4. update implementation truth and active queue without copying their state
   into this index;
5. update affected bounded contracts and manifest lifecycle;
6. run documentation, architecture, state/property, and relevant real benchmark
   gates.

No new model schema or benchmark-shaped fix is admitted as a substitute for
this comparison.

Use the [Architecture Change Admission Template](change-admission/architecture-change-template.md)
for that comparison.

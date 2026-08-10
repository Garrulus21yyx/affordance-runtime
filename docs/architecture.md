# Architecture Entry Point

> **Lifecycle:** CURRENT REFERENCE ENTRYPOINT
> **Authority:** discovery only; does not duplicate target semantics

Current target authority:

- [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
- [Unified World Interface and E2E AgentLoop Evolution Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

Current truth and scheduling:

- [Implementation Status](implementation-status.md)
- [Current Implementation Plan](current-implementation-plan.md)
- [Project Plan](project-plan.md)

Governance:

- [Documentation Index](README.md)
- [Documentation Governance](documentation-governance.md)
- [Architecture Governance](architecture-governance-track.md)

The target center is the unified world interface and a short typed
acquire–decide–execute/acquire–evaluate loop. Adapters declare independent and
post-action acquisition capabilities separately from evidence/source assurance;
unsupported and failed acquisition stay typed. AgentLoopState remains current
run-control authority, while a bounded decision-scoped ControlTransition records
what just happened without becoming a durable ledger or replay authority. P5-E
adds a run-scoped VerifiedTaskState for the validated task frontier, keeping
TaskPlan replaceable and task-level auditing separate from the local
`fill`/`select` repetition guard. Schemas and invariants remain solely in the
authoritative architecture and scoped normative contracts linked above.

TaskSpec/ActionContract/StateKernel/RuntimeCommitter documents describe the
retained implementation baseline or archive history unless the target
architecture explicitly adopts a local invariant from them.

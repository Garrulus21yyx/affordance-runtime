# Architecture Entry Point

> **Lifecycle:** CURRENT REFERENCE ENTRYPOINT
> **Authority:** discovery only; does not duplicate target semantics

Current target authority:

- [Canonical GUI Agent Execution Architecture](task-execution-authority-map.md)
- [Canonical GUI Agent Authority Cutover Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

Current truth and scheduling:

- [Implementation Status](implementation-status.md)
- [Current Implementation Plan](current-implementation-plan.md)
- [Project Plan](project-plan.md)

Governance:

- [Documentation Index](README.md)
- [Documentation Governance](documentation-governance.md)
- [Architecture Governance](architecture-governance-track.md)
- [Canonical GUI Agent Execution Architecture](task-execution-authority-map.md)

The target center is the unified world interface and the single chain defined
by the authority map: admitted TaskSpec/TaskPlan semantics, observation-bound
active-step resolution, action-only Agent decisions, current binding, one
dispatch, fresh evaluation, and plan/task progress. Adapters declare independent
and post-action acquisition capabilities separately from evidence/source
assurance; unsupported and failed acquisition stay typed. AgentLoopState remains
current run-control authority, while a bounded decision-scoped
ControlTransition records what just happened without becoming a durable ledger
or replay authority. Schemas, owners, state transitions, ordering, and
invariants are defined only in the authority map; this entrypoint does not
restate them.

TaskSpec/ActionContract/StateKernel/RuntimeCommitter documents describe the
retained implementation baseline or archive history unless the target
architecture explicitly adopts a local invariant from them.

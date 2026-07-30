# Documentation Index

This directory contains current Runtime governance documents, historical audits,
and archived architecture records. When documents conflict, use the order below.

## Current architecture authority

The current long-term production target is:

- [Affordance Runtime Authoritative Optimized Architecture](superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md)
- [Affordance Runtime Substitutive Refactor Execution Plan](superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md)
- [SAR-0 change admission](change-admission/sar-0-authoritative-architecture-freeze.yaml)
- [Failure Ownership Router admission](change-admission/for-1-failure-owner-router.yaml)

SAR-0 supersedes the earlier simplified active-step target, the TaskPlanAuthority
additive plan, and the ODG default-path architecture for future default
production work.

## Durable status

- [Implementation Status and Forward Gates](implementation-status.md) is the
  durable execution ledger.
- [Current Implementation Plan](current-implementation-plan.md) records the
  active queue and next admitted work.
- [Architecture Governance Track](architecture-governance-track.md) records
  structural admission gates and frozen control surfaces.
- [Responsibility Containment Boundary](responsibility-containment-boundary.md)
  records ownership and Coordinator-containment rules.
- [Benchmark Governance Boundary](benchmark-governance-boundary.md) records
  anti-specialization and evidence rules.

When a change updates the active architecture, plan, or evidence identity,
update these durable files in the same commit. Git owns the exact repository
HEAD identity (`git rev-parse HEAD`); `implementation-status.md` records the
reviewed closure, implementation, and evidence identities;
`current-implementation-plan.md` owns the active queue; this README owns
navigation and conflict precedence only.

## Archive

Superseded default-target architecture documents live in:

- [superseded-2026-07-29](archive/superseded-2026-07-29/README.md)

Archived documents remain useful as decision history and migration context, but
they do not define the default production architecture when they conflict with
SAR-0.

Legacy root architecture redirects remain at:

- [Architecture](architecture.md)
- [Complete Architecture Blueprint](complete-architecture-blueprint.md)
- [Design Freeze and Implementation Gates](design-freeze.md)

These files are stable redirect targets only. Their full historical content is
stored under the superseded archive.

Do not move evidence reports, narrow audit records, or change-admission records
into the archive only because they are old. Archive only documents whose default
architecture authority has been explicitly superseded.

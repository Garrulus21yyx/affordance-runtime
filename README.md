# Affordance Runtime

Affordance Runtime is a planner-neutral GUI execution Runtime. It turns bounded
user tasks and current environment observations into versioned, authorized,
observable action transactions with explicit approval, verification, recovery,
trace, and evaluation boundaries.

## Current architecture

The long-term target is defined only by:

- [Task Contract-Centered Authoritative Runtime Architecture](docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
- [Task Contract-Centered Runtime Architecture Evolution Plan](docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

```text
SourceEnvelope
→ MinimalIntentProposal
→ optional SemanticAudit
→ immutable TaskSpec
→ canonical observation
→ replaceable TaskPlan<StepSpec>
→ Runtime-owned full ActionChoiceCatalog
→ ActionContract + Authority/Capability/Approval/Preflight gates
→ Execute
→ post-action observation
→ inline LoopEvaluator
→ RuntimeCommitter
```

`TaskSpec` owns user authorization and completion semantics. `TaskPlan` is a
replaceable execution hypothesis. `ActionContract` is one grounded, gated,
expiring transaction. `TaskCompletionEvaluator` evaluates full TaskSpec success;
all required structured outputs must also be materialized and source-bound when
required; only RuntimeCommitter writes authoritative completion.

TaskSpecAuthority is the only accepted-meaning writer. Task Planner and
OpenSemanticResolver may receive bounded, source-bound, explicitly
non-authoritative context when needed; action construction, gates, execution,
evaluation, completion, and commit do not use raw request text. In short:
single semantic admission, bounded contextual rereading, no downstream
authority expansion.

The target keeps logical boundaries strict while defaulting to a lightweight
modular-monolith realization: full Catalog membership may be lazy/indexed,
canonical observations are ref/index-backed, and optional audit/model machinery
is enabled by task risk rather than for every run.

DOM, AX, Visual, SVG, WoT, API, and Device are composable observation,
grounding, execution, and evidence surfaces under this one chain. Planner
selects a backend-neutral semantic action; ActionContractBuilder selects the
current backend/binding from the canonical target's retained candidates and
conflicts.

The target is not implemented as a whole. See
[Implementation Status](docs/implementation-status.md) for current code truth.

## Product boundary

Affordance Runtime—not BrowserGym or another benchmark—is the product.
Benchmarks are external evaluators. Production logic may not depend on task ID,
seed, family, expected answer, selector, coordinate, or authored benchmark
semantics.

The Runtime owns:

- multi-source DOM/AX/Visual/SVG/WoT/API/Device perception and canonical observation;
- complete legal action construction before model presentation;
- versioned ActionContracts and exact target/binding identity;
- Task authority, capability, approval, freshness, and preflight gates;
- backend-neutral execution and typed receipts;
- loop-native typed effect/step/task evaluation;
- bounded, side-effect-aware recovery;
- authoritative state/trace commit and offline evaluation evidence.

## Documentation

Start with [docs/README.md](docs/README.md). The
[documentation manifest](docs/documentation-manifest.yaml) is the machine-readable
authority/lifecycle index.

Key current documents:

- [Project Plan](docs/project-plan.md)
- [Current Implementation Plan](docs/current-implementation-plan.md)
- [Implementation Status](docs/implementation-status.md)
- [Architecture Governance](docs/architecture-governance-track.md)
- [Documentation Governance](docs/documentation-governance.md)
- [Task Intake and Planner Contract](docs/task-intake-and-planner.md)
- [Active Perception and Recovery Contract](docs/active-perception-and-online-recovery.md)
- [Trace and Evaluation Contract](docs/trace-and-evaluation.md)

Historical audits, completed plans, and superseded designs are indexed under
[docs/archive](docs/archive/superseded-2026-08-05/README.md). Evidence and
change-admission records remain in their dedicated immutable directories.

## Repository layout

```text
src/affordance_runtime/   Runtime implementation
tests/                    unit, integration, architecture, governance tests
docs/                     current documentation and immutable records
docs/archive/             superseded prose, plans, audits, and snapshots
scripts/                  reproduction, benchmark, and maintenance entrypoints
```

Important implementation surfaces include TaskSpec/intake contracts, planning
requests and planners, canonical observation, ActionChoice/ActionContract,
safety/preflight, execution, verification/evaluation, recovery, StateKernel,
trace/artifacts, integrations, and benchmark adapters.

## Validation and reproduction

Repository-governed tests and reproduction commands are recorded in
[Implementation Status](docs/implementation-status.md) and immutable
[evidence](docs/evidence/README.md). Historical results apply only to their exact
revision/profile and do not imply current promotion.

Container entrypoints:

```bash
./scripts/reproduce_container.sh
AFFORDANCE_WOT_PROOF=1 ./scripts/reproduce_container.sh
```

## One sentence

Affordance Runtime gives agents a versioned and policy-bound GUI action layer in
which model proposals remain subordinate to Runtime-owned observation, action,
approval, verification, recovery, and commit authority.

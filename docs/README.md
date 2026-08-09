# Documentation Index

> **Lifecycle:** CURRENT DISCOVERY ENTRYPOINT
> **Machine-readable index:** [documentation-manifest.yaml](documentation-manifest.yaml)
> **Lifecycle policy:** [Documentation Governance](documentation-governance.md)

This page is the single discovery path. Filename dates, file length, search
ranking, and historical references do not establish authority.

## 1. Current target authority

Exactly two documents define the target and its migration:

1. [AgentContext Recurrent E2E Agent Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
2. [AgentContext Recurrent E2E Agent Evolution Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

The paths are retained for repository compatibility; the documents no longer
define a Task Contract-centered architecture.

Core target order:

```text
TaskGoal
→ Runtime-owned WorldObservation / Internal ActionSpace
→ disposable bounded AgentContext
→ typed AgentDecision
→ RiskPolicy / HumanConfirmation when needed
→ current BoundActionRequest
→ execute once → ActionResult
→ fresh WorldObservation
→ ActionEvaluation + TaskEvaluation
→ continue / reobserve / ask user / stop
```

The boundary rule is “responsibility-thin, semantics-strong intake” plus
“capability-thick, infrastructure-thin execution.” TaskGoal retains stable
meaning/risk/completion boundaries; current page structure, route, and action
order stay inside the observation-grounded loop.

DOM, AX, Visual, SVG, WoT, API, Device, and CLI are symmetric surface adapters under
one world interface. Internal transaction submission is not the product center.

## 2. Current implementation truth and work

- [Implementation Status](implementation-status.md) alone states what code at the reviewed baseline actually does.
- [Current Implementation Plan](current-implementation-plan.md) alone schedules the active slice.
- [Project Plan](project-plan.md) summarizes the durable product direction.

Current code still runs the older TaskSpec/ActionContract/StateKernel/
RuntimeCommitter path. It is a retained migration baseline, not the target.
The unified DOM, Visual full-digest, and WoT local HTTP JSON paths are integrated
non-default, and their shared-state adapter-only matrix is proven. The older
baseline remains the default product path. P5-D semantic confirmation, fresh
rebind, and effect certainty are integrated non-default. P5-D6.1 contract
completion is closed on the non-default path. P5-M0 model-safe
policy views and deterministic evaluator trust validation are closed. P5-M1
model policy core is closed, and P5-M1.1 connects it to the existing ModelPort
owner with hostile-JSON limits, an outer deadline, zero retry/fallback, typed
failures, metadata and a local HTTP transport proof. Live-provider attestation
is unavailable. P5-M2 production evaluation is closed for declared-minimum
criterion profiles: Runtime composes mechanical, evidence-scoped semantic,
explicit-user and hybrid results; general semantic entailment remains partial.
P5-M2.1 closes relevance-bound action verification, semantic evidence catalog
visibility, hybrid component separation and dynamic semantic readiness.
P5-M0.1 AgentContext/context identity/intent/relevance/paging/source-assurance
is implemented on the non-default target path. P5-M1 uses the same non-default
loop and retained deterministic evaluators.
P5-M0.1.1 operational closure adds one-shot context generations, fresh
acquisition-identity enforcement, traversable opaque-cursor paging, coherent
task/world/action budgets, objective-aware page invalidation, capability/result
separation and recurrent semantic history. The default Coordinator path is unchanged.

## 3. Maintained policies and contracts

| Responsibility | Document |
|---|---|
| architecture admission and one-default-path migration | [Architecture Governance Track](architecture-governance-track.md) |
| documentation lifecycle and authority | [Documentation Governance](documentation-governance.md) |
| module ownership and dependency direction | [Responsibility Containment](responsibility-containment-boundary.md) |
| Runtime/model/adapter/benchmark product boundary | [Runtime-First Boundary](runtime-first-boundary.md) |
| benchmark neutrality | [Benchmark Governance Boundary](benchmark-governance-boundary.md) |
| TaskGoal, optional milestones/LocalObjective, and AgentPolicy boundary | [Task Intake and Planner](task-intake-and-planner.md) |
| world observation and bounded recovery | [Active Perception and Online Recovery](active-perception-and-online-recovery.md) |
| short-loop sequencing | [Orchestration and Live Feedback](orchestration-and-feedback.md) |
| result/effect/task evaluation and telemetry | [Trace and Evaluation](trace-and-evaluation.md) |
| parent-agent/API integration | [Integrations](integrations.md) |
| offline adaptation | [Harness Evolution](harness-evolution.md) |
| positive cross-surface evaluation | [Benchmark Plan](benchmark-plan.md) |

These documents explain one bounded responsibility. If they conflict with the
two target-authority documents, the target authority wins; if they describe code
differently from Implementation Status, Implementation Status wins.

## 4. Maintained references

- [Architecture entrypoint](architecture.md)
- [Pricing extraction baseline scenario](scenarios/pricing-extraction.md)
- [Reversible settings baseline scenario](scenarios/settings-update.md)
- [Approval-gated export baseline scenario](scenarios/approval-gated-report-export.md)
- [Legacy ActionContract digest threat model](security/action-contract-digest-threat-model.md)
- [P5-0 entry-hardening baseline review](reviews/2026-08-07-p5-entry-hardening.md)
- [World-Interaction migration review snapshot](reviews/2026-08-08-world-interaction-migration-review.md)
- [P5-A/B/C1 Unified World and DOM implementation record](reviews/2026-08-08-p5-dom-vertical-slice.md)
- [P5-C1.1/B1.1 correctness closure](reviews/2026-08-08-p5-c1-1-correctness-closure.md)
- [P5-C1.2/B1.2 exact-selection closure](reviews/2026-08-08-p5-c1-2-exact-selection-closure.md)
- [P5 Visual single-surface vertical](reviews/2026-08-08-p5-visual-single-surface-vertical.md)
- [P5 WoT single-surface and three-surface matrix](reviews/2026-08-08-p5-wot-single-surface-and-matrix.md)
- [P5-D semantic confirmation and effect certainty](reviews/2026-08-08-p5-d-semantic-confirmation.md)
- [P5-D6.1 confirmation and evaluation contract completion](reviews/2026-08-08-p5-d6-1-contract-completion.md)
- [P5-M0 model-safe policy and evaluator boundary](reviews/2026-08-08-p5-m0-model-evaluator-boundary.md)
- [AgentContext architecture refinement](reviews/2026-08-08-agent-context-architecture-refinement.md)
- [P5-M0.1 AgentContext implementation](reviews/2026-08-08-p5-m0-1-agent-context-implementation.md)
- [P5-M0.1.1 context operational closure](reviews/2026-08-08-p5-m0-1-1-context-operational-closure.md)
- [P5-M1 model-backed policy](reviews/2026-08-08-p5-m1-model-backed-policy.md)
- [P5-M1.1 provider bridge hardening](reviews/2026-08-08-p5-m1-1-provider-bridge-hardening.md)
- [P5-M2 production evaluator composition](reviews/2026-08-08-p5-m2-production-evaluator-composition.md)
- [P5-M2.1 evidence semantics closure](reviews/2026-08-08-p5-m2-1-evidence-semantics-closure.md)
- [P5-M3 target-loop internal benchmark harness](reviews/2026-08-08-p5-m3-target-loop-benchmark-harness.md)
- [P5-M3.1 harness measurement and real-adapter closure](reviews/2026-08-08-p5-m3-1-harness-measurement-real-adapters.md)
- [P5-M3.2 external benchmark admission package](reviews/2026-08-08-p5-m3-2-external-benchmark-admission-package.md)

These scenarios and review records describe current/legacy baseline behavior or
revision-scoped findings; they do not redefine target contracts.

## 5. Immutable records and archive

- [Evidence](evidence/README.md) is revision-scoped and non-authoritative.
- `change-admission/` preserves historical scoped decisions.
- [2026-08-05 archive](archive/superseded-2026-08-05/README.md)
- [2026-07-29 archive](archive/superseded-2026-07-29/README.md)
- `archive/sar-9-phase-extraction/` preserves extraction history.

## 6. Maintenance rule

An architecture change updates together:

1. target architecture and evolution plan;
2. implementation truth and active queue;
3. affected bounded contracts;
4. root README, this index, and the manifest;
5. archive or compatibility notes for superseded material;
6. documentation and architecture governance checks.

## P5-M3.3 exact model-profile diagnostics

P5-M3.3 measures the current real-DOM model input and runs an explicit five-level
conformance ladder without changing Runtime authority. The installed exact
`qwen2.5:7b` and `llama3.1:8b` profiles formerly failed full-union grammar
initialization with a 2,000-character summary bound. With the canonical bound
set to 1,024, each passed one Level-2 format-only call and reached Runtime
destination admission at Levels 3/4. This is a compatibility confirmation, not
stable model support. The existing Mistral profile has one successful Level-4
run for format-only and compact grounding. See the
[review record](reviews/2026-08-09-p5-m3-3-model-profile-conformance.md).

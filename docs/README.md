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
- [P5-M4.2 verified progress and repeated-action containment](reviews/2026-08-10-p5-m4-2-verified-progress-repeated-action-containment.md)

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
destination admission at Levels 3/4. Re-evaluation then showed that the
provider-neutral compact contract closes destination salience for both exact
profiles. On clean HEAD `b4c04d6`, each passed L0--L4 at 20/20 under
`compact-contract` and received a per-profile accepted
`action_selection_supported` attestation. This does not establish full
recurrent AgentPolicy support. The existing Mistral profile also passed a fresh Level-4
format-only and compact no-regression cell, one call each. See the
[review record](reviews/2026-08-09-p5-m3-3-model-profile-conformance.md).
The follow-up D0–D4 destination ladder uses the same full union and reports only
typed failure shapes: Qwen passes through the real nested action-page level and
fails only full context by copying `target_id`; Llama passes D0–D2, supplies a
forbidden nonempty destination at D3 and copies `target_id` at D4.
Those format-only failures remain diagnostic facts; Runtime was not relaxed or
given destination repair. Compact grounding remains opt-in rather than the
production default, and the support evidence does not admit an external run.

## P5-M3.4 production compact grounding profile

`compact-contract.v1` is a normal explicit production profile. Factory
precedence is explicit argument, then `LLM_DECISION_GROUNDING`, then the
unchanged `format-only` default. Exact identity now binds grounding/version,
canonical schema digest, the 1,024-character summary limit, context budget and
execution profile. The seven-decision and multi-action GPU matrix blocks a
global default change: local profiles retain L0–L4 support, but compact.v1 does
not reliably choose all seven decision variants. See the
[M3.4 review](reviews/2026-08-09-p5-m3-4-compact-grounding-production-profile.md).

## P5-M3.5 decision-neutral compact grounding v2

`compact-contract.v1` is frozen for action-selection scope. The new explicit
`compact-contract.v2` guide is decision-neutral, bounded to 4 KiB, and projects
all seven public decision domains without embedding a real first-action answer.
Qwen and Llama exact GPU candidates did not pass the seven-decision 5/5 gate,
so no 20/20 recurrent support run was admitted. Format-only remains default;
the global cutover is blocked. See the
[M3.5 review](reviews/2026-08-09-p5-m3-5-decision-neutral-compact-v2.md).

## P5-M3.6 two-stage decision diagnostic

The benchmark-only two-stage harness separately measures routing-only,
fixed-route payload-only, single-stage compact-v2, and full two-stage Runtime
outcomes on identical public contexts. Scripted and local HTTP fixtures close
all seven decisions and all eight critical cases. Exact Qwen and Llama runs
both isolate strong payload filling but incomplete routing, so both candidate
gates fail and no 20/20 support gate runs. Production factory, AgentLoop,
parser, admission, defaults, and external-benchmark gates are unchanged. See
the [M3.6 review](reviews/2026-08-09-p5-m3-6-two-stage-decision-decomposition.md).

## P5-M4 BrowserGym target-loop adapter

Local-model compatibility is closed and non-blocking for the current GUI-agent
scope. The production default remains one-stage `format-only.v1`; compact v1
is action-selection-only, compact v2 is experimental/not admitted, and
two-stage remains a closed diagnostic. The pinned BrowserGym/MiniWoB adapter
uses current structural observations, Runtime-private element bindings,
single-dispatch execution, fresh post-step observations, and official
mechanical completion signals. Its fixed three-task conformance passes through
AgentLoop, the strict canonical parser, and Runtime admission. Live provider
execution remains separately opt-in and is `NOT_RUN` when unavailable. See the
[P5-M4 review](reviews/2026-08-09-p5-m4-browsergym-target-loop-adapter.md).

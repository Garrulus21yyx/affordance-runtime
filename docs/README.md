# Documentation Index

> **Lifecycle:** CURRENT DISCOVERY ENTRYPOINT
> **Machine-readable index:** [documentation-manifest.yaml](documentation-manifest.yaml)
> **Lifecycle policy:** [Documentation Governance](documentation-governance.md)

This page is the single discovery path. Filename dates, file length, search
ranking, and historical references do not establish authority.

## 1. Current target authority

Exactly two documents define the target and its migration:

1. [Target AgentLoop Authority Map](task-execution-authority-map.md)
2. [AgentContext Recurrent E2E Agent Evolution Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

The retired task-contract-centered filename is a historical pointer only and
does not define current Runtime authority.

Core target order follows. The M4.6-F P0 `last_transition` projection is locally
implemented and full-verified; live revalidation remains open:

```text
TaskGoal
→ Runtime-owned WorldObservation / Internal ActionSpace
→ disposable bounded AgentContext
→ typed AgentDecision
→ RiskPolicy / HumanConfirmation when needed
→ current BoundActionRequest
→ execute once → ExecutionOutcome(ActionResult + typed post acquisition)
→ fresh WorldObservation from execute or capability-admitted capture
→ ActionEvaluation + TaskEvaluation
→ bounded ControlTransition + AgentLoopState update
→ next context projects that same root as optional last_transition
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

M4.6-E resumed with the minimal advisory-checklist slice at `2758364`. The
prior clean `90c3997` default `glm-4.1v-thinking-flashx` evidence completed 5/5
but succeeded 1/5, with all 16 decisions admitted as structural actions and
zero image inputs, visual sources, argument violations or repairs. The new
grounded `update_checklist` control can preserve bounded model-authored task
continuity without an environment step or Runtime action authority. In the
single subsequent default-model diagnostic, raw outcomes were 3/5 but formal
evidence was invalid because the in-repository output directory dirtied the
run identity. All 15 decisions were `SelectAction`; the model never used the
checklist. No performance improvement is attributed, critic and second-planner
designs remain deferred, and implementation is paused for an architecture
choice about guaranteed policy-state initialization versus provider-native
session continuity.
See the [current implementation plan](current-implementation-plan.md) and
[checklist slice](evidence/2026-08-14-advisory-agent-checklist-2758364.md).

Current code still runs the older TaskSpec/ActionContract/StateKernel/
RuntimeCommitter path by default. The non-default target path has the unified
DOM/Visual/WoT matrix, semantic confirmation, disposable AgentContext, strict
model-policy boundary, declared-minimum evaluators, internal harness and pinned
BrowserGym adapter for their declared scopes.

Three exact MiniWoB-60 runs are current immutable evidence and must not be
combined: historical clean `b3b64a2` at 6/60, clean `83dc4fa` rerun-v3 at
4/60, and clean `4924ce6` M4.5-C diagnostic at 8/60. Rerun-v3 records 7 post-observation failures, 9 unclassified typed
failures and 11 Runtime rejections. At the P5-M4 baseline it confirmed that
BrowserGym's consume-once reset/step cache did not satisfy the public active-
observation meaning; M4.5-A has replaced that lifecycle on the non-default path.

M4.5-A typed acquisition lifecycle is complete. M4.5-B control/failure work is
integrated non-default but reopened for reducer, boundary, failure-authority and
property convergence; the earlier B.1/B.2/B.3 closure claims are withdrawn.
M4.5-C diagnostic execution is complete with valid `4924ce6` evidence, while
formal exit, performance and generalization remain unclaimed. M4.6 is
`IN_PROGRESS`: M4.6-A canonical AX semantics/currentness is
`COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE`, M4.6-B is
`COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE`; M4.6-C is
`COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE`, and M4.6-D is
`REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED`; M4.6-E is
`SINGLE_AGENT_CONTEXT_CUTOVER_IMPLEMENTED / LOCALLY_VERIFIED / PUSHED_E7F9F46 /
LIVE_NOT_RUN / GENERALIZATION_OPEN`; its earlier task-grounded perception and
non-authoritative hypothesis vertical slices remain implementation history. Grounded-tools v2
already reuses the SoM renderer and passed its single-BrowserGym-source targeted
gate. Runtime-owned source selection, provenance-preserving WorldFusion,
one-route selection, a per-frame visual evidence gate, explicit same-acquisition
DOM/visual correspondence now exist on the non-default target path. Phase 4
extends the structural plane with raw-DOM clickable SVG identity and removes
point authority from the BrowserGym target loop. Point providers remain
isolated benchmark/legacy arms; open-world region proposal is explicitly configured and may use the thin
OmniParser adapter, while ambiguous DOM candidates can resolve only to an
existing E-ref, and unmatched proposals remain observation-only. Phase-4
focused/full verification and real identity probes pass; the clean-SHA frozen
five-witness gate is evidence-valid at `3/5` and accepts the bounded
architecture/authority invariants. Follow-up remediation removes redundant
E-ref calls and closes settled-value/multi-target state projection;
`visual-addition` succeeds in the clean five-case run and focused
`click-shades` succeeds in six structural actions with no auxiliary E-ref or
point calls. The final color increment has not received another complete
five-case run. A current-observation regular-lattice enricher now derives
row/column and visible Cartesian-axis semantics without point output. The
previous five-witness closure is superseded by a de-specialization pass:
set membership/effects live in persistent Runtime state, Catalog enforces an
explicit fail-closed directive, the main Agent explicitly proposes typed set
semantics, and Vision no longer parses task keywords. Task-relative predicate
fields and repeated-leaf exact counts have been removed. Full and live
revalidation are in progress; multi-seed and broad generalization remain open;
the M4.6-B residual contract implementation is `880e65fef0c2541be9f4b5af121e610f858685db`,
while its accepted targeted run remains bound to original `07895ede392bdff065ba3b4c0a6384ba18904143`;
M4.6-C implementation `e6c410021d8b9bf11b52f24520a6258ede5d2027`
is verified by no-model run
`miniwob-inventory-17:6220967c47a24532b4140728627e4950`;
M4.6-D provides typed control feedback with a frozen two-distinct-issue
same-scope repair/no-gain budget and immediate exact-repeat containment, not
Runtime autocorrection or a mandatory reflection agent;
M4.7 multi-seed and P5-E benchmark validation remain blocked by their
targeted/breadth gates. P5-E already contains VerifiedTaskState, rolling
objective and bounded hypothesis vertical slices; general milestone planning
is still open. The local
ProgressController remains fill/select-only and is not a planner. The default
Coordinator path is unchanged.

Status mirror: M4.5-B is `INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW /
IMPLEMENTED_NOT_VERIFIED`; M4.5-C is `COMPLETE_DIAGNOSTIC /
EVIDENCE_VALID_AT_4924CE6 / FORMAL_EXIT_NOT_ATTESTED /
PERFORMANCE_NOT_CLAIMED / GENERALIZATION_NOT_CLAIMED`; M4.6 is `IN_PROGRESS /
M4.6-A COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE / M4.6-B
COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE / M4.6-C
COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE / M4.6-D
REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED / M4.6-E
prior DOM-first evidence DOM_FIRST_VISION_CONVERGENCE_FULL_VERIFIED /
LIVE_GATE_FAILED_DIAGNOSTIC; current context cutover
SINGLE_AGENT_CONTEXT_CUTOVER_IMPLEMENTED / LOCALLY_VERIFIED / PUSHED_E7F9F46 /
LIVE_NOT_RUN;
M4.6-F LATEST_TRANSITION_P0_IMPLEMENTED_LOCALLY_FULL_VERIFIED_LIVE_UNVERIFIED`.
Implementation Status is authoritative.

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
| explicit target Python/CLI entrypoints | [Target Runtime entrypoints](target-runtime-entrypoints.md) |

These documents explain one bounded responsibility. If they conflict with the
two target-authority documents, the target authority wins; if they describe code
differently from Implementation Status, Implementation Status wins.

## 4. Maintained references

- [Architecture entrypoint](architecture.md)
- [Interaction capability onboarding proposed design](interaction-capability-onboarding-design.md)
- [Actor world snapshot convergence design](actor-world-snapshot-design.md)
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
- [P5-M4.3 MiniWoB-60 seeded breadth](reviews/2026-08-10-p5-m4-3-miniwob-60-seeded-breadth.md)
- [P5-M4.4 MiniWoB breadth failure attribution](reviews/2026-08-10-p5-m4-4-miniwob-breadth-failure-attribution.md)
- [Runtime main-chain convergence audit and legacy-exit plan](reviews/2026-08-13-runtime-chain-convergence-audit.md)
- [Target default-cutover consumer map](reviews/2026-08-13-target-cutover-consumer-map.md)
- [Target Runtime entrypoints](target-runtime-entrypoints.md)

These scenarios and review records describe current/legacy baseline behavior or
revision-scoped findings; they do not redefine target contracts.

## 5. Immutable records and archive

- [Evidence](evidence/README.md) is revision-scoped and non-authoritative.
- [post-M4.4 separately authorized rerun-v3 evidence](evidence/runs/p5-m4-4-miniwob-60-seed7-83dc4fa-rerun-v3/README.md)
  is the immutable clean 4/60 exact-run record; it does not replace M4.3's 6/60.
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
execution remains separately opt-in and exact-run-scoped. See the
[P5-M4 review](reviews/2026-08-09-p5-m4-browsergym-target-loop-adapter.md).

## P5-M4.2–M4.5 short-loop closure

M4.2 implements fill/select-only local repeated-action containment; it is not a
general progress auditor. M4.3's clean historical MiniWoB-60 result is 6/60.
M4.4 added typed attribution/capability inventory, and a later separately
authorized clean rerun-v3 completed at 4/60. The evidence archives are distinct
and neither is a general capability estimate. The later `4924ce6` diagnostic
completed 60/60 at 8/60 with valid evidence and no generalization claim.

The seven rerun-v3 observation failures promoted independent acquisition from a
conditional idea into the M4.5-A correction. That slice now separates reset
initial acquisition, capability-aware capture and execute-returned post
acquisition, validates origin/fallback truth, and has real pinned active-capture
coverage. The M4.5-B candidate records bounded ControlTransition facts, but
reducer legality, attempt matrices and failure/projection ownership are still
under convergence review. This review introduces no ledger, replay or second
state authority. See the [active queue](current-implementation-plan.md) for the
completed M4.6-C inventory and M4.6-D feedback slices, the
[immutable M4.5-C attribution](reviews/2026-08-11-p5-m4-5-miniwob-60-diagnostic.md),
the [current M4.6 remediation record](reviews/2026-08-11-p5-m4-6-evidence-directed-short-loop-remediation.md),
and the [evolution plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md).

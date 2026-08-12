# Affordance Runtime：AgentContext 循环式 E2E Agent 演进计划

> **Lifecycle:** CURRENT AUTHORITATIVE EVOLUTION PLAN
> **Updated:** 2026-08-11
> **Review evidence:** none; Implementation Status owns any reviewed closure SHA
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](../specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Active slice:** [Current Implementation Plan](../../current-implementation-plan.md)

文件路径为兼容现有治理检查而保留。本文是迁移顺序、退出门和删除门的唯一
权威；旧 Task Contract/ledger/checkpoint-centered P5 队列已停止。

## 0. 迁移决议

当前 HEAD 保留为 transactional safety baseline，不回滚已完成工作；同时冻结：

```text
RuntimeDelta / RuntimeCommitter expansion
StateKernel read-view/CAS expansion
durable RunLedger/checkpoint/resume
generic recovery transaction
authorization proof/token platform
trace-as-execution-authority
```

迁移按能力纵向替换：

```text
freeze target contracts
→ symmetric SurfaceAdapter
→ positive DOM/Visual/WoT short loops
→ semantic human confirmation + unknown-effect handling
→ disposable AgentContext + context identity + paging
→ model-backed AgentPolicy + production evaluators + new-loop harness
→ observation acquisition lifecycle + lossless control-transition accounting
→ same-profile diagnostic + evidence-directed semantic/currentness remediation
→ new same-profile breadth run + supported-subset multi-seed gate
→ optional milestone planning and long-horizon loop
→ bounded ActionBatch
→ evaluated memory/skill sidecars
→ cross-surface breadth and old-core deletion
```

## 1. 迁移法律

1. 先证明新 vertical loop，再删除旧基线。
2. 新 surface/evaluator 不先转译为 delta、commit 或 recovery transaction。
3. 每个切片结束时只有一条产品 default path；兼容只在边界单向 legacy→new。
4. 行为验收优先于 hash/event/delta 数量。
5. Observation 是 current binding authority；Plan 是可丢弃假设。
6. 单动作优先；Batch 只有在无 observation barrier 时才能作为局部优化。
7. confirmation 绑定语义 intent/risk/consequences，不绑定 selector/coordinate；执行 request 仍绑定 current observation/binding。
8. acquisition capability 与 observation evidence assurance 分离；unsupported/failed acquisition typed。
9. receipt/effect/task completion 分离，UNKNOWN 不盲重试，dispatch truth 不因 acquisition 失败而降格。
10. one accepted policy decision → exactly one bounded root ControlTransition；它不 replay/reconstruct state。
11. memory/skill/route hint 必须离线评测后发布，不在线自改。
12. 每个实现切片必须保持新路径 non-default，直到 P5-H 明确完成默认切换。

## 2. 基线资产与主要债务

### 保留并提升

- `UnifiedObservation`、canonical targets、coverage/conflict/freshness；
- `GroundingCandidate` 与 DOM/AX/Visual/SVG/WoT/API/Device bindings；CLI 为目标扩展；
- active/targeted perception；
- backend-neutral semantic actions 与 route hard gates；
- executor routing 和 typed result/receipt；
- typed post-action acquisition and evaluator freshness；
- receipt/effect/completion separation；
- stale zero-call、unknown no-retry、required-output integrity；
- optional planning、System-1 cache/skill 的可复用思想。

### 冻结并迁移

- mandatory SourceEnvelope/TaskSpecAuthority/TaskPlan path；
- ActionChoiceCatalog authority/digest burden；
- god ActionContract；
- proof/capability/approval token chain；
- ProgressStage/RecoveryStage 多职责；
- StateKernel/RuntimeDelta/RuntimeCommitter；
- TraceDag 对 admission/commit 的控制作用。

### 首要验证缺口

DOM、Visual full-digest 与 WoT local HTTP JSON 的 shared-state adapter-only matrix、
AgentContext/model policy、declared-minimum evaluation、new-AgentLoop harness 和 pinned
BrowserGym adapter 已闭合在 non-default path。M4.4 后续 formal rerun-v3 在 clean
`83dc4fa` 完成 60/60、成功 4/60；它与历史 M4.3 `b3b64a2` 的 6/60 是两个不可合并的
exact-run records。新运行直接暴露 7 个 `post_observation_failure`，并保留 9 个
`unclassified_typed_failure`。随后单独授权的 `4924ce6` M4.5-C diagnostic 完成
60/60、成功 8/60；它是第三个独立 record，不形成 trend 或 generalization claim。

因此当前首要缺口不是再加 transaction/safety machinery，也不是立即进入 P5-E；而是
independent acquisition lifecycle 与 control-transition accounting 已进入当前实现；
`4924ce6` 诊断进一步将下一步收敛到 AX currentness、verifier truth、semantic
inventory 和 non-effect control liveness。M4.6 按独立切片修复并产生新 evidence，
随后才做新的 same-profile run 和 supported-subset multi-seed。所有阶段继续以
completed behavior 为主证据。

## 3. P5 阶段与切片

```text
P5-A1–A4: COMPLETE_NON_DEFAULT
P5-B1–B4: COMPLETE_FOR_DECLARED_MINIMUM_PROFILES
P5-C1–C3: COMPLETE_FOR_SHARED_STATE_DETERMINISTIC_MATRIX
P5-C4 semantic fusion: DEFERRED; not prerequisite for P5-D or D6.1
P5-C5: small AgentLoopState complete; distinct LoopPolicy / optional TurnRecorder pending
P5-D1–D4: COMPLETE_NON_DEFAULT
P5-D5 evaluator control: COMPLETE_FOR_CURRENT_NO_REQUIRED_OUTPUT_PROFILE
P5-D5 target output validation: COMPLETE_FOR_DECLARED_MINIMUM
P5-D6.1: COMPLETE
P5-M0: COMPLETE
P5-M0.1 AgentContext architecture: COMPLETE_NON_DEFAULT
P5-M0.1.1 context operational closure: COMPLETE_NON_DEFAULT
model-backed AgentPolicy: CLOSED
P5-M1 model-backed AgentPolicy: COMPLETE_NON_DEFAULT
P5-M1.1 strict decision boundary and existing ModelPort bridge: COMPLETE_NON_DEFAULT
local HTTP provider transport proof: COMPLETE
live provider profile: EXACT_HEAD_MISTRAL_ATTESTED_FOR_DECLARED_PROFILES
P5-M2 production evaluator composition: COMPLETE_NON_DEFAULT_FOR_DECLARED_MINIMUM
P5-M2.1 evidence semantics and dynamic readiness: COMPLETE_NON_DEFAULT
P5-M3 new-AgentLoop internal benchmark harness: COMPLETE_NON_DEFAULT_FOR_FIXED_MANIFEST
P5-M3.1 measurement and real-adapter attestation: COMPLETE; reviewed exact-head internal artifact available
P5-M3.2 admission package: COMPLETE_FOR_PINNED_MECHANICAL_PROFILE
P5-M4 pinned BrowserGym adapter: COMPLETE_FOR_DECLARED_PROFILE
P5-M4.2 local fill/select progress containment: COMPLETE
P5-M4.3 historical MiniWoB-60 run: COMPLETE_VALID_NEGATIVE_EVIDENCE (6/60)
P5-M4.4 failure attribution/capability inventory: COMPLETE_FOR_CURRENT_SCOPE
post-M4.4 separately authorized rerun-v3: COMPLETE_VALID_NEGATIVE_EVIDENCE (4/60)
P5-M4.5-A acquisition lifecycle: COMPLETE_NON_DEFAULT
P5-M4.5-B control/failure contract: INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED
P5-M4.5-C same-profile diagnostic: COMPLETE_DIAGNOSTIC / EVIDENCE_VALID_AT_4924CE6 / FORMAL_EXIT_NOT_ATTESTED / PERFORMANCE_NOT_CLAIMED / GENERALIZATION_NOT_CLAIMED
P5-M4.6 evidence-directed short-loop remediation: IN_PROGRESS / M4.6-A COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE / M4.6-B COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE / M4.6-C COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE / M4.6-D REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED / M4.6-E VISUAL_BINDING_IMPLEMENTED_PROPERTY_VERIFIED / LIVE_VISUAL_GATE_PENDING
M4.6-B residual contract implementation: `880e65fef0c2541be9f4b5af121e610f858685db`; accepted targeted run remains bound to original `07895ede392bdff065ba3b4c0a6384ba18904143`
P5-M4.7 supported-subset multi-seed: NOT_STARTED / BLOCKED_BY_M4_6_GATES
P5-E verified long-horizon frontier: NOT_STARTED / BLOCKED_BY_BREADTH_GATES
```

### P5-M0.1 — Disposable AgentContext architecture

| Slice | Deliverable | Exit gate |
|---|---|---|
| `M0.1a` | bounded `IntentContextView` and one-way `AgentContext` projection | raw intent is source-labelled/context-only; no private route or Runtime owner enters context |
| `M0.1b` | opaque `ContextIdentity` over task/observation/action-space/page/progress/pending revisions | every typed decision binds current context; stale decision is zero-call |
| `M0.1c` | bounded world/progress/pending/budget/history views with truthful totals/truncation | projection budgets include total serialized bytes; absence is distinguishable from truncation |
| `M0.1d` | source assurance summary, LocalObjective relevance and action paging | assurance does not grant authorization; relevance cannot change legality; only current-page action IDs are selectable |
| `M0.1e` | typed decision union and documentation/contract completeness | SelectAction/RequestObservation/RequestActionPage/AskUser/ProposeDone/Wait/Abort only; no ProposeRecovery platform |

M0.1 is implemented on the non-default target path. The closed profile includes
bounded context-only intent/world/progress/pending/budgets, opaque recurrent
identity, typed decisions, deterministic paging/relevance and DOM/Visual/WoT
source summaries. Targeted acquisition optimization and confirmation dominance
remain deferred; M0 projections remain `INTEGRATED_NON_DEFAULT`.

### P5-M0.1.1 — Context operational closure

| Slice | Deliverable | Exit gate |
|---|---|---|
| `M0.1.1a` | monotonic one-shot context generation and shared fresh-observation identity guard | page cycles/replay are zero-call; reused acquisition identity fails closed |
| `M0.1.1b` | Runtime-issued opaque cursor paging and page/world pinning | `has_more` has usable continuation; only current page is projected/admitted |
| `M0.1.1c` | truthful task/world/action budgets, objective/source/history/evidence coherence | explicit hints only; capability separate from result; bounded semantic history |

This closure remains non-default and provider-neutral. It adds no durable
context/page store, model policy/evaluator, targeted acquisition provider,
confirmation dominance, semantic fusion, benchmark admission or cutover.

### P5-M1–M3 — First model loop and evaluation gate

| Slice | Deliverable | Exit gate |
|---|---|---|
| `M1` | model-backed target AgentPolicy using typed AgentContext/Decision and deterministic evaluators | no private binding/provider SDK in policy; fixed internal tasks pass |
| `M2` | production evaluator composition, criterion adjudicators and semantic-evidence applicability | MECHANICAL/SEMANTIC/USER_ACCEPTANCE/HYBRID are explicit; Runtime owns final completion and output validation |
| `M3` | new-AgentLoop benchmark harness and fixed BrowserGym/MiniWoB smoke | exact-head remote CI, zero forbidden effects, zero duplicate unknown attempts; no generalization claim |

M1 established the injected provider-neutral structured model port:
canonical bounded AgentContext JSON, a fixed authority prompt, strict decision
schema/parser, one call without core retry, typed failure mapping, and internal
DOM/Visual/WoT proofs with retained deterministic evaluators. Production model
evaluation is closed for declared-minimum composition; general semantic
entailment remains partial. M3 harness and the pinned M4 BrowserGym profile
subsequently closed for their declared scopes.

M1.1 closes the canonical hostile-JSON boundary and connects the policy through
the existing ModelPort transport owner. The admitted profile enforces one
attempt, zero retry, no fallback, an outer deadline, typed failures and
secret-free call metadata. A local OpenAI-compatible HTTP fixture proves the
transport path; later exact-profile evidence is revision-scoped and does not
change the zero-retry/fallback boundary.

### P5-A — Target contracts

| Slice | Deliverable | Exit gate |
|---|---|---|
| `A0` | 同步权威架构、计划、状态、README 和 bounded contracts | 文档/链接治理通过；旧平台只作为 baseline/deletion target 出现 |
| `A1` | semantics-strong `TaskGoal`, risk-proportionate MaterialInput/Binding, optional `EvaluationSpec` | intake 不含 page/surface/route/TaskPlan；effect boundary fail-closed |
| `A2` | optional `TaskPlan<Milestone>` and `LocalObjective` | simple task can bypass; no GUI actions/bindings; evaluator owns completion |
| `A3` | `SurfaceObservation`, `WorldObservation`, `AgentWorldView`, `ActionBinding`, `ActionSpace` | contracts do not import StateKernel/delta/committer |
| `A4` | `ActionIntent`, `BoundActionRequest`, `ActionResult`, evaluations, bounded loop state | intent/request identities separated; one-way legacy projectors only |

`A0–A4` 已完成并集成在 non-default target path；legacy projector 仍仅是单向边界。

### P5-B — Unified SurfaceAdapter and observation

| Slice | Deliverable | Exit gate |
|---|---|---|
| `B1` | initial/current observation, `SurfaceAdapter`, `ObservationOrchestrator`, `WorldFusion`, `ActionSpaceBuilder` | truthful coverage/currentness; no BrowserSession isinstance core branch |
| `B2` | DOM adapter | observe→space→bind→execute→reobserve conformance |
| `B3` | Visual/SoM adapter | screenshot→semantic targets/options; model emits no raw coordinates |
| `B4` | WoT adapter/session | read property/invoke/reobserve without test-only observer glue |
| `B5` | AX/SVG/API/CLI/Device expansion | same contracts; adapter-only variation |

结构化 source 优先但不独占；coverage gap/conflict/layout need 触发 targeted Visual/
SoM/SVG。Not-acquired、failed、truncated、stale 与 complete absence 必须区分。
`B1–B4` 已对当前声明的 DOM、Visual full-digest、WoT local HTTP JSON minimum
profiles 完成；`B5` breadth 尚未开始。

### P5-C — Minimal short AgentLoop vertical slice

暂不引入 TaskPlan 或 Batch，只实现：

```text
initial acquisition → build ActionSpace → select ActionIntent → bind
→ execute once → typed post-action acquisition → evaluate
```

| Slice | Positive case | Exit gate |
|---|---|---|
| `C1` | DOM semantic activate/fill | same minimal AgentPolicy/evaluator returns COMPLETE |
| `C2` | Visual-only equivalent | no model coordinate; post-action visual/structured evidence confirms |
| `C3` | WoT property/action equivalent | environment-native state confirms effect |
| `C4` | same target with DOM+WoT bindings | one route executes; no effectful auto-fallback |
| `C5` | small `AgentLoopState`, LoopPolicy, optional TurnRecorder | no StateKernel/RuntimeDelta; recorder failure is behavior-neutral |

`C1–C3` shared-state deterministic matrix 已完成；`C4` semantic fusion 之前延后且
不是 P5-D/D6.1 前置条件，现在由 M4.6-E step 12 在 visual execution binding 前
显式恢复；`C5` 仅 small AgentLoopState 已完成。

### P5-D — Human confirmation and unknown effect

| Slice | Deliverable | Exit gate |
|---|---|---|
| `D1` | `ExecutorSupport + RiskPolicy` | ALLOW/CONFIRM/BLOCK only; task risk boundary applied |
| `D2` | `ConfirmationRequest` over ActionIntent + consequences | target dominance permits only covered/non-stronger current subjects; incomparable or expanded semantics re-confirm; exact equality remains the current conservative implementation; pure fresh binding changes do not re-confirm |
| `D3` | reobserve/rebind continuation | executor receives current BoundActionRequest; stale is zero-call |
| `D4` | `SENT_UNKNOWN` handling | typed fresh acquisition/evaluate; no automatic replay |
| `D5` | `ActionEvaluator + TaskEvaluator + target output validation` | evaluator control complete for no-required-output profile; output integrity pending M0 |

旧 exact ActionContract hash equality remains baseline evidence only until this semantic-confirmation
path becomes default; it is not copied into the target as binding-sensitive human confirmation.
`D1–D4` 已在 non-default path 完成；`D5` evaluator control 仅对当前
no-required-output profile 完成，target output validation 已在 M0 对声明的
path/SHA-256 minimum 闭合。`D6.1`
已补齐 effective risk、destination、presentation、session terminal、evaluation
lineage/evidence-ref fields 和 task-evaluation control。Evidence-ref fields 已强制；
对 current WorldObservation 的解析已由 M0 完成。

### P5-M4.5 — Short-loop lifecycle and accounting closure

M4.5 只修 rerun-v3 已证实的通用 short-loop contract gaps，并拆成两个可独立归因的
切片；禁止一次性混入 VerifiedTaskState、planner、prompt tuning 或通用 recovery engine。

| Slice | Deliverable | Exit gate |
|---|---|---|
| `M4.5-A` | `reset -> initial ObservationAcquisition`；capability-aware `capture()`；`execute() -> ExecutionOutcome` | BrowserGym RequestObservation、Wait、stale/currentness、confirmation refresh 不再消费空 post-step cache；unsupported/failed typed；normal action 直接消费 returned post observation；SENT_UNKNOWN/one-send invariants unchanged |
| `M4.5-B` | bounded in-memory `ControlTransition` for every accepted policy decision | action/non-action/pause/post-context-schema action-admission rejection branches retain typed admission/execution/acquisition/evaluation/progress/pending/status; exact total count + bounded suffix; pre-decision provider and stale/schema-invalid inputs do not fabricate transitions |
| `M4.5-C` | same frozen MiniWoB-60 seed-7 diagnostic | completed at clean `4924ce6`, 60/60 and 8/60, with valid immutable evidence; no formal exit, performance or generalization attestation; does not close B |

M4.5-A 与 M4.5-B 分开提交、分别跑 focused conformance，并分别保留 before/after
evidence，避免同时改 perception lifecycle 和 accounting 后无法归因。`ControlTransition`
只回答刚发生什么；AgentLoopState 仍是 authority，禁止 durable ledger、replay、global
event taxonomy 或 state reconstruction。

### P5-M4.6 — Evidence-directed short-loop remediation

M4.6 只消费 `4924ce6` 的 immutable facts 和同树源码归因；修复后不得回写旧 run。

| Slice | Deliverable | Exit gate |
|---|---|---|
| `M4.6-A` | shared canonical AX semantics/currentness；owner-scoped select options；executable availability | unchanged canonical binding is current；bound drift/probe failure is typed and zero-step；probe/accounting identities exact |
| `M4.6-B` | four-state verifier and typed task-terminal fact orthogonal to Runtime failure | supported algebra total；terminal task failure never becomes `RuntimeFailure(CONTROL, REJECTED)`；previous-unknown cohort gets a new run ID |
| `M4.6-C` | semantic inventory separate from projection coverage and ActionSpace | recognized omission cannot appear as represented/empty；model sees bounded inventory counts without task-completeness inference |
| `M4.6-D` | canonical model-facing control feedback, a frozen two-distinct-issue same-scope zero-dispatch repair/no-gain budget, explicit projection of existing validated no-effect strategy feedback, and immediate exact-repeat containment | typed source owners feed a sanitized envelope into the next ordinary AgentContext；AgentPolicy—not Runtime—chooses the correction；an identical issue repeats or a third distinct issue terminates typed；effectful dispatch or relevant semantic/task/page gain resets, but a valid no-gain decision and fresh identity do not；existing ProgressController remains local；Runtime refresh and any sent/uncertain request are never replayed |
| `M4.6-E` | stable opaque identity, referentially closed grounded tools, Unified source selection/fusion/route and staged observable/executable breadth | irrelevant AX order does not change identity；selected sources/fused facts retain provenance；one admitted action uses one route and reroutes only after proven zero-dispatch；read-only semantics grants no execution；quotas preserve controls |
| `M4.7` | supported-subset multi-seed run | immutable manifest, exact seed set, provider-capacity floor, success floor and maximum seed variance frozen before execution; all thresholds met before P5-E |

每个 M4.6 slice 独立提交、property 验收并记录 implementation SHA；targeted/full rerun 使用
新 run ID 和 immutable directory。职责、authority、cohesion 和 change coupling 决定 owner，
不得按 LOC 机械拆分或形成 projection/ContextBuilder/benchmark god file。

### P5-E — Long-horizon planning

| Slice | Deliverable | Exit gate |
|---|---|---|
| `E1` | run-scoped `VerifiedTaskState` over existing TaskPlan/Milestone contracts | milestone status/current frontier/unresolved obligations update only from validated evidence; simple tasks can bypass |
| `E2` | MilestoneEvaluator/TaskProgressAuditor and frontier-derived LocalObjective | auditor cannot choose action or mark TaskEvaluation COMPLETE; local ProgressController remains separate |
| `E3` | low-frequency TaskPlanner and fact-driven plan replacement | planner output is hypothesis; invalid plan is replaced from verified frontier, not patched through recovery history |
| `E4` | bounded context: recent 8–12 ControlTransition projections + milestone summary + evidence refs | no full transition/event/observation history in model context |
| `E5` | ask_user and intermediate verification | complete one 20–50+ accepted-policy root-ControlTransition cross-page/application task without losing constraints |

Cross-day background work, crash restore, cross-machine continuation and distributed workers remain
outside this phase and the core Runtime.

### P5-F — Bounded ActionBatch

| Slice | Deliverable | Exit gate |
|---|---|---|
| `F1` | option metadata `batchable/observation_barrier` and validator | default is barrier=true; unsafe/unknown fails closed |
| `F2` | max-three same-observation/surface/session low-risk batch | no external effect, navigation, app/page change or cross-surface action |
| `F3` | stop-on-failure execution and one typed fresh acquisition after batch | no intermediate-world dependency; each request/result lineage retained |
| `F4` | atomic adapter actions (`fill/select/replace_text/drag`) preferred | Batch is not used to emulate missing atomic affordances |
| `F5` | ablation | compare success, model calls, observations, steps, latency and batch utilization |

### P5-G — Memory, Skill and offline learning

| Slice | Deliverable | Exit gate |
|---|---|---|
| `G1` | currentness-checked BindingCache | target/fingerprint resolved in current observation; capability-aware fresh acquisition still required |
| `G2` | experience retrieval and verified Skill contract | never bypasses ActionSpace/RiskPolicy/evaluator |
| `G3` | failure attribution and candidate route/skill generation | no live policy mutation |
| `G4` | offline replay + cross-surface promotion gate | publish/reject decision bound to evaluation version |

### P5-H — Breadth, default cutover and old-core deletion

| Slice | Deliverable | Exit gate |
|---|---|---|
| `H1` | DOM/AX/Visual/SVG/WoT positive matrix | same TaskGoal/policy/vocabulary/evaluator; all COMPLETE |
| `H2` | API/Device/CLI conformance and route ablations | adapter-only variation; metrics comparable |
| `H3` | default product composition cutover | only new AgentLoop path reachable; old Coordinator edge-only |
| `H4` | Trace downgrade | only optional TurnRecorder/metrics/artifacts sidecar |
| `H5` | delete RuntimeCommitter/RuntimeDelta/StateKernel/read-view bridge | absent from product default imports/call path |
| `H6` | delete PreparedDispatch/permit/proof/token/recovery transaction/SemanticAudit core coupling | strict profiles explicit at edge |
| `H7` | delete compatibility projectors/tests/docs after last consumer | one product path and synchronized status |

## 4. Cross-phase regression laws

1. Runtime builds ActionSpace from current observation.
2. AgentPolicy cannot emit raw selector/coordinate/backend payload/path/endpoint.
3. BoundActionRequest is current or executor receives zero calls.
4. the current semantic confirmation subject must be covered by the confirmed
   subject under the target dominance order; until dominance is implemented,
   exact subject equality is the conservative gate. Private binding may fresh-rebind only.
5. result/receipt alone cannot confirm effect or task completion.
6. each action/admitted batch gets a typed post-action acquisition; evaluator freshness comes
   from that outcome or an explicitly supported independent capture.
7. SENT_UNKNOWN never replays automatically.
8. required output exists and content matches.
9. adapter reports truthful coverage/currentness.
10. TaskPlan is optional/replaceable hypothesis; evaluators own milestone/task
    satisfaction, never the plan itself.
11. Batch respects all barrier/risk/surface limits.
12. recorder failure cannot alter behavior.
13. benchmark metadata/reward cannot alter product decisions.
14. memory/skill never bypasses the loop and is promoted only offline.
15. AgentContext is one-way/disposable; all decisions bind current context ID.
16. LocalObjective changes relevance only; source assurance never grants execution authority.
17. ProposeDone is advisory; criterion-specific Runtime validation owns completion.
18. acquisition capability and evidence assurance remain distinct; expected unavailable/failed is typed.
19. one accepted policy decision produces exactly one bounded root ControlTransition;
    transition history never reconstructs AgentLoopState.
20. VerifiedTaskState accepts only validated evidence promotion; local repetition containment
    and task-frontier auditing remain separate.

Old hash/event/delta tests remain while their baseline path is default. When an old owner is deleted,
owner-specific tests are deleted rather than translated into permanent target constraints.

## 5. Stopped old queue

- frozen StateKernel read views and transition CAS/atomic delta batches；
- RuntimeCommitter shadow-copy closure；
- durable RunLedger/checkpoint/crash resume；
- generic interrupt/cancel/recovery transaction state machine；
- trace transaction ordering；
- global permit/token registry, worker fencing, revocation linearizability；
- mandatory source/proof platform for ordinary GUI tasks。

A future hard-crash, multi-writer or regulated-audit proposal must state its concrete fault model,
retention boundary and product metrics; it cannot silently return as GUI core work.

## 6. Current execution order

```text
DONE: P5-A0 documentation consolidation and target refinement
DONE: P5-A1–A4 target contracts, integrated non-default
DONE: P5-B1–B4 for DOM, Visual full-digest, and WoT local HTTP JSON simulation minimums
DONE: P5-C1–C3 shared-state deterministic-policy DOM/Visual/WoT matrix
DEFERRED: P5-C4 semantic fusion; it is not a prerequisite for P5-D
PARTIAL: P5-C5 small AgentLoopState complete; LoopPolicy and optional TurnRecorder remain
DONE: P5-D1–D4 semantic confirmation, fresh rebind, and effect-certainty continuation
DONE: P5-D5 evaluator control and declared-minimum target output validation
DONE: P5-D6.1 confirmation and evaluation contract completion
DONE: P5-M0 model-safe policy views and evidence-validated evaluation boundary
DONE: P5-M0.1 AgentContext architecture and context completeness
DONE: P5-M0.1.1 context operational closure
DONE: P5-M1 model-backed target AgentPolicy core
DONE: P5-M1.1 strict decision boundary and existing ModelPort bridge
DONE: P5-M2 production evaluator composition and criterion adjudicators
DONE: P5-M2.1 evidence semantics and dynamic evaluation closure
DONE: P5-M3 new-AgentLoop internal fixed-manifest harness; external smoke remains separately gated
DONE: P5-M3.1–M4 pinned adapter, admission, conformance and live-profile evidence for declared scopes
DONE: P5-M4.2 local fill/select progress containment
DONE: P5-M4.3 historical MiniWoB-60 seed-7 negative run (6/60)
DONE: P5-M4.4 typed attribution/capability inventory
DONE: post-M4.4 separately authorized formal rerun-v3 (4/60)
DONE: P5-M4.5-A observation acquisition lifecycle
ACTIVE_REVIEW: P5-M4.5-B bounded control/failure contract convergence; implemented, not verified
DONE_DIAGNOSTIC: P5-M4.5-C same-profile MiniWoB-60 at `4924ce6`; evidence valid, formal exit/performance/generalization not claimed
DONE_NON_DEFAULT: P5-M4.6-A canonical AX semantics/currentness — COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE
DONE_NON_DEFAULT: P5-M4.6-B verifier/task-terminal truth — COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE
DONE_NON_DEFAULT: P5-M4.6-C semantic inventory truth — COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE
COMPLETE_NON_DEFAULT: P5-M4.6-D bounded control feedback/repair/no-gain
NOT_STARTED: P5-M4.6-E staged breadth
BLOCKED: P5-M4.7 supported-subset multi-seed by M4.6 gates
THEN: P5-E VerifiedTaskState, TaskProgressAuditor and milestone planning
THEN: P5-F bounded ActionBatch
THEN: P5-G evaluated memory/skill sidecars
LAST: P5-H breadth, default cutover and old-core deletion
```

Semantic fusion 继续 deferred，且不是 M0.1/M1 前置。不得先做 Batch/Skill/大规模
删除，也不得继续旧 P5-0E commit/read-view closure。

## 7. Completion definition

1. Default product uses unified world contracts and the new AgentLoop.
2. DOM/AX/Visual/SVG/WoT positive matrix succeeds; API/Device/CLI conform.
3. A 20–50+ accepted-policy root-ControlTransition case retains constraints,
   asks when uncertain, verifies milestones and replans from facts.
4. Batch only runs admitted no-barrier local actions and measurably reduces cost without lowering success.
5. Semantic confirmation, stale zero-call, capability-aware fresh acquisition, lossless control
   accounting, no-blind-retry and output integrity pass.
6. Memory/Skill promotion is offline and cannot bypass product gates.
7. Trace is telemetry only; benchmark reward is offline only.
8. StateKernel/RuntimeDelta/RuntimeCommitter/recovery transaction are absent from default imports/call path.
9. Strict profiles remain explicit and do not tax ordinary GUI tasks.
10. README, authority, status and current queue agree.

P5-M3.3 exact model-profile conformance is complete for the tested profiles.
The Runtime parser/admission boundary remains unchanged. Exact Qwen 2.5 7B and
Llama 3.1 8B profiles pass the compact-contract L0–L4 support gate at 20/20 per
level, while the production grounding default remains format-only. External
benchmark execution remains separately gated.

P5-M3.4 admits `compact-contract.v1` as an explicit production profile while
retaining format-only as the global default and rollback setting. The pure
cutover gate is blocked by incomplete seven-decision behavior, compact Mistral
no-regression and unavailable exact-head CI. No default or external benchmark
cutover is authorized.

P5-M3.5 freezes v1 as `PRODUCTION_SUPPORTED_ACTION_SELECTION_PROFILE` and adds
decision-neutral `compact-contract.v2` as an explicit experiment that is not admitted.
The exact Qwen and Llama GPU candidates failed the seven-decision 5/5 gate, so
no 20/20 recurrent support upgrade was admitted. Format-only remains the
global default; strong-provider v2 availability, exact-head CI and full
recurrent support continue to block any separate default-cutover commit.

P5-M3.6 diagnoses the failed single-stage candidate without changing that
admission decision. The benchmark-only two-stage path separates routing from
payload generation, derives payload schemas from canonical branch models, and
replays complete parsed output through existing Runtime control. Exact Qwen
and Llama candidates both expose a routing bottleneck while fixed-route payload
generation passes 35/35. Both candidate gates fail, so no support gate or
production adoption is admitted. Parser, Runtime admission, AgentLoop,
grounding defaults, external benchmark status, and Coordinator cutover remain
unchanged.

P5-M4 re-enters the GUI-agent mainline and freezes model-compatibility work as
non-blocking. It closes the BrowserGym/MiniWoB adapter only for version 0.14.3
and the three reviewed mechanical tasks, using existing one-stage policy,
strict parser/admission, Runtime-private bindings, fresh observation and
environment-native evaluation. Compact v2 and two-stage remain not admitted.
An exact-head live smoke is a separate fixed-manifest gate and remains
`NOT_RUN/BLOCKED_WITH_REASON` when provider evidence or explicit execution
authority is absent. This milestone authorizes neither a benchmark campaign
nor a default Coordinator-path change.

P5-M4.2 closes the locally diagnosed repeated-action gap without changing that
admission boundary. Fill/select receive fresh structural effect verification;
already-satisfied exact selections are suppressed before binding; one unchanged
repeat has a typed bounded failure; model context receives bounded route-free
progress; and watchdog reports preserve partial session evidence. The fixed
simple-task budget is 10 turns within the existing 120-second timeout. The
historical `cd49b8e` fixed smoke remains failed by case timeout, and no live
provider or external smoke was run for this correction.

P5-M4.3 inserts one bounded evidence step before deciding whether P5-E is next.
It freezes 60 tasks from the pinned MiniWoB registry by static current-primitive
classification and deterministic hashing, then measures one seed through the
unchanged one-stage target loop. It adds no primitive, planner, prompt,
Runtime admission, recovery, retry, fallback, or default-path behavior.
Outcome attribution can direct a later separately authorized phase, but this
single synthetic-family run does not prove seed stability or GUI generalization.

P5-M4.4 followed the valid historical 6/60 negative result before any P5-E
work. It closed future typed failure origins, added complete-registry multi-axis
capability requirements, and performed local no-model lifecycle/projection
diagnostics without rerunning that slice or altering product behavior. A later,
separately authorized exact-profile rerun-v3 completed at clean `83dc4fa` with
valid 4/60 evidence. The two archives are immutable and cannot be merged or
reported as a trend.

Rerun-v3 retains 7 `post_observation_failure`, 9 `unclassified_typed_failure`
and 11 `runtime_rejected` cases. At the P5-M4 baseline, those observation
failures proved that public active-observation meaning and BrowserGym's
consume-once post-step cache were not interchangeable. M4.5-A and its A.1
closure now replace that lifecycle with typed, origin-validated acquisition;
M4.5-B is integrated non-default but reopened: ordered physical attempts,
terminal non-re-entry, confirmation/current-risk lifetime, evaluation epochs,
snapshot authority and benchmark Runtime/component/watchdog/cleanup/integrity
ownership must converge under one bounded reducer and property model. M4.5-C is
complete as separately authorized diagnostic evidence at `4924ce6`; it does
not close B. Its source-confirmed AX currentness, verifier, inventory and
non-effect-control gaps define M4.6-A–E. M4.7 and P5-E stay blocked by their
targeted/breadth gates. Provider/model competence remains measured rather than
repaired by Runtime machinery.

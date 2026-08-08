# Affordance Runtime：AgentContext 循环式 E2E Agent 演进计划

> **Lifecycle:** CURRENT AUTHORITATIVE EVOLUTION PLAN
> **Updated:** 2026-08-08
> **Reviewed baseline:** `codex/migrate-world-interaction-capabilities@792d327112cd72f3cb5c9bd02c273c80f626f349`
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
8. receipt/effect/task completion 分离，UNKNOWN 不盲重试。
9. memory/skill/route hint 必须离线评测后发布，不在线自改。
10. 每个实现切片必须保持新路径 non-default，直到 P5-H 明确完成默认切换。

## 2. 基线资产与主要债务

### 保留并提升

- `UnifiedObservation`、canonical targets、coverage/conflict/freshness；
- `GroundingCandidate` 与 DOM/AX/Visual/SVG/WoT/API/Device bindings；CLI 为目标扩展；
- active/targeted perception；
- backend-neutral semantic actions 与 route hard gates；
- executor routing 和 typed result/receipt；
- fresh post-action observation；
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

DOM、Visual full-digest 与 WoT local HTTP JSON 已用相同 TaskGoal、确定性
AgentPolicy 和 evaluators 证明 shared-state adapter-only matrix，通用
confirmation/evaluation 信任边界与声明的 target output minimum 已闭合。
当前下一切片是 P5-M0.1 AgentContext architecture/context completeness；随后才是
model-backed AgentPolicy、production evaluator composition 与 new-AgentLoop harness。
所有阶段继续以 completed behavior 为主证据。

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
model-backed AgentPolicy: NEXT
P5-M1 model-backed AgentPolicy: NOT_STARTED
P5-M2 production evaluator composition: NOT_STARTED
P5-M3 new-AgentLoop benchmark harness: NOT_STARTED
external benchmark: BLOCKED
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

### P5-M1–M3 — First model loop and evaluation gate

| Slice | Deliverable | Exit gate |
|---|---|---|
| `M1` | model-backed target AgentPolicy using typed AgentContext/Decision and deterministic evaluators | no private binding/provider SDK in policy; fixed internal tasks pass |
| `M2` | production evaluator composition, criterion adjudicators and semantic-evidence applicability | MECHANICAL/SEMANTIC/USER_ACCEPTANCE/HYBRID are explicit; Runtime owns final completion and output validation |
| `M3` | new-AgentLoop benchmark harness and fixed BrowserGym/MiniWoB smoke | exact-head remote CI, zero forbidden effects, zero duplicate unknown attempts; no generalization claim |

### P5-A — Target contracts

| Slice | Deliverable | Exit gate |
|---|---|---|
| `A0` | 同步权威架构、计划、状态、README 和 bounded contracts | 文档/链接治理通过；旧平台只作为 baseline/deletion target 出现 |
| `A1` | semantics-strong `TaskGoal`, risk-proportionate MaterialInput/Binding, optional `EvaluationSpec` | intake 不含 page/surface/route/TaskPlan；effect boundary fail-closed |
| `A2` | optional `TaskPlan<Milestone>` and `LocalObjective` | simple task can bypass; no GUI actions/bindings; evaluator owns completion |
| `A3` | `SurfaceObservation`, `WorldObservation`, `AgentWorldView`, `ActionBinding`, `ActionSpace` | contracts do not import StateKernel/delta/committer |
| `A4` | `ActionIntent`, `BoundActionRequest`, `ActionResult`, evaluations, Turn, `AgentLoopState` | intent/request identities separated; one-way legacy projectors only |

`A0–A4` 已完成并集成在 non-default target path；legacy projector 仍仅是单向边界。

### P5-B — Unified SurfaceAdapter and observation

| Slice | Deliverable | Exit gate |
|---|---|---|
| `B1` | `SurfaceAdapter.observe/is_current/execute`, `ObservationOrchestrator`, `WorldFusion`, `ActionSpaceBuilder` | truthful coverage/currentness; no BrowserSession isinstance core branch |
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
observe → build ActionSpace → select ActionIntent → bind
→ execute once → fresh observe → evaluate
```

| Slice | Positive case | Exit gate |
|---|---|---|
| `C1` | DOM semantic activate/fill | same minimal AgentPolicy/evaluator returns COMPLETE |
| `C2` | Visual-only equivalent | no model coordinate; post-action visual/structured evidence confirms |
| `C3` | WoT property/action equivalent | environment-native state confirms effect |
| `C4` | same target with DOM+WoT bindings | one route executes; no effectful auto-fallback |
| `C5` | small `AgentLoopState`, LoopPolicy, optional TurnRecorder | no StateKernel/RuntimeDelta; recorder failure is behavior-neutral |

`C1–C3` shared-state deterministic matrix 已完成；`C4` semantic fusion 延后且不是
P5-D/D6.1 前置条件；`C5` 仅 small AgentLoopState 已完成。

### P5-D — Human confirmation and unknown effect

| Slice | Deliverable | Exit gate |
|---|---|---|
| `D1` | `ExecutorSupport + RiskPolicy` | ALLOW/CONFIRM/BLOCK only; task risk boundary applied |
| `D2` | `ConfirmationRequest` over ActionIntent + consequences | target dominance permits only covered/non-stronger current subjects; incomparable or expanded semantics re-confirm; exact equality remains the current conservative implementation; pure fresh binding changes do not re-confirm |
| `D3` | reobserve/rebind continuation | executor receives current BoundActionRequest; stale is zero-call |
| `D4` | `SENT_UNKNOWN` handling | fresh observe/evaluate; no automatic replay |
| `D5` | `ActionEvaluator + TaskEvaluator + target output validation` | evaluator control complete for no-required-output profile; output integrity pending M0 |

旧 exact ActionContract hash equality remains baseline evidence only until this semantic-confirmation
path becomes default; it is not copied into the target as binding-sensitive human confirmation.
`D1–D4` 已在 non-default path 完成；`D5` evaluator control 仅对当前
no-required-output profile 完成，target output validation 已在 M0 对声明的
path/SHA-256 minimum 闭合。`D6.1`
已补齐 effective risk、destination、presentation、session terminal、evaluation
lineage/evidence-ref fields 和 task-evaluation control。Evidence-ref fields 已强制；
对 current WorldObservation 的解析已由 M0 完成。

### P5-E — Long-horizon planning

| Slice | Deliverable | Exit gate |
|---|---|---|
| `E1` | low-frequency TaskPlanner and TaskPlan<Milestone> | simple tasks still bypass planning |
| `E2` | MilestoneEvaluator and LocalObjective | facts/evidence own completion; LocalObjective contains no action sequence |
| `E3` | fact-driven plan replacement | invalid plan is replaced, not patched through recovery history |
| `E4` | bounded context: recent 8–12 Turns + milestone summary + evidence refs | no full event/observation history in model context |
| `E5` | ask_user and intermediate verification | complete one 20–50 turn cross-page/application task without losing constraints |

Cross-day background work, crash restore, cross-machine continuation and distributed workers remain
outside this phase and the core Runtime.

### P5-F — Bounded ActionBatch

| Slice | Deliverable | Exit gate |
|---|---|---|
| `F1` | option metadata `batchable/observation_barrier` and validator | default is barrier=true; unsafe/unknown fails closed |
| `F2` | max-three same-observation/surface/session low-risk batch | no external effect, navigation, app/page change or cross-surface action |
| `F3` | stop-on-failure execution and one fresh observation after batch | no intermediate-world dependency; each request/result lineage retained |
| `F4` | atomic adapter actions (`fill/select/replace_text/drag`) preferred | Batch is not used to emulate missing atomic affordances |
| `F5` | ablation | compare success, model calls, observations, steps, latency and batch utilization |

### P5-G — Memory, Skill and offline learning

| Slice | Deliverable | Exit gate |
|---|---|---|
| `G1` | currentness-checked BindingCache | target/fingerprint resolved in current observation; fresh observe still required |
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
6. each action/admitted batch gets fresh post-observation.
7. SENT_UNKNOWN never replays automatically.
8. required output exists and content matches.
9. adapter reports truthful coverage/currentness.
10. TaskPlan is optional/replaceable and evaluator-owned.
11. Batch respects all barrier/risk/surface limits.
12. recorder failure cannot alter behavior.
13. benchmark metadata/reward cannot alter product decisions.
14. memory/skill never bypasses the loop and is promoted only offline.
15. AgentContext is one-way/disposable; all decisions bind current context ID.
16. LocalObjective changes relevance only; source assurance never grants execution authority.
17. ProposeDone is advisory; criterion-specific Runtime validation owns completion.

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
NEXT: P5-M1 model-backed target AgentPolicy using deterministic evaluators
THEN: P5-M2 production evaluator composition and criterion adjudicators
THEN: P5-M3 new-AgentLoop benchmark harness and fixed BrowserGym/MiniWoB smoke
THEN: P5-E long-horizon planning
THEN: P5-F bounded ActionBatch
THEN: P5-G evaluated memory/skill sidecars
LAST: P5-H breadth, default cutover and old-core deletion
```

Semantic fusion 继续 deferred，且不是 M0.1/M1 前置。不得先做 Batch/Skill/大规模
删除，也不得继续旧 P5-0E commit/read-view closure。

## 7. Completion definition

1. Default product uses unified world contracts and the new AgentLoop.
2. DOM/AX/Visual/SVG/WoT positive matrix succeeds; API/Device/CLI conform.
3. A 20–50 turn case retains constraints, asks when uncertain, verifies milestones and replans from facts.
4. Batch only runs admitted no-barrier local actions and measurably reduces cost without lowering success.
5. Semantic confirmation, stale zero-call, fresh observation, no-blind-retry and output integrity pass.
6. Memory/Skill promotion is offline and cannot bypass product gates.
7. Trace is telemetry only; benchmark reward is offline only.
8. StateKernel/RuntimeDelta/RuntimeCommitter/recovery transaction are absent from default imports/call path.
9. Strict profiles remain explicit and do not tax ordinary GUI tasks.
10. README, authority, status and current queue agree.

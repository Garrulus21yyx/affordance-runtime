# Task Contract 中心化 Runtime 架构演进规划

> **文档类型：** Architecture Evolution Plan / Source-of-Truth Ledger
> **状态：** AUTHORITATIVE EVOLUTION PLAN
> **日期：** 2026-08-05（2026-08-07 corrective amendment）
> **事实基线：** `agent/migrate-runtime-components @ 26cc5bb804faa1a06e2aec4aa645ad84d3ecc73c`
> **最新范围决议：** 2026-08-07 撤回旧的“P4-C0–C5 production-security closure”口径。当前 P4 只按权威架构 §0.0 的五项 MVP invariant 调度；C2 及 C4/C5 中的 tenant/profile、revocation linearizability、global permit/fencing、attempt-bound collateral 与 immutable multi-suite attestation 转为 future hardening，不阻塞 P5。历史 `DONE` 仍只按所在台账行解释。
> **派生目标架构：** [Task Contract 中心化唯一权威目标架构](../specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **历史基线：** [2026-07-29 唯一权威优化目标架构](../specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md)
> **2026-08-05 权威修正：** active-step 链必须先从 canonical observation 建立完整 Runtime `ActionChoiceCatalog`，再投影任何 model-facing request；§10.1 对该修正逐条登记。
> **2026-08-05 Source / Verification 收口：** 默认 intake 改为轻量 `SourceEnvelope + selective SourceAnchor`，细粒度 `SemanticAudit` 按风险启用；verification 改为 loop-native typed `LoopEvaluationPhase`，完成语义仍由 `TaskCompletionEvaluator` 独立求值、只由 `RuntimeCommitter` 提交。§10.2–§10.3 逐条登记两份修正。
> **2026-08-05 Semantic Authority / Contract Closure 补充：** 第一份复核提供 requirement/dependency/choice/output 收口，第二份复核只覆盖其严格 raw-text firewall；最终采用 Task Meaning Write Barrier、bounded `SourceContextView` 与 raw-text-free execution chain。§10.4 登记合并结果。
> **2026-08-05 Physical Minimality 补充：** 复核识别的过重风险按“已覆盖、补充实现约束、明确拒绝”处理；full Catalog、canonical observation、authority、Criterion、Planner 与 optional capability 不得被机械实现成 eager copy、微服务森林或默认多模型链。§10.5 登记处理结果。
> **2026-08-05 Cross-Surface Visibility 补充：** DOM、AX、Visual、SVG、WoT、API 与 Device 显式共享同一 TaskSpec、TaskPlan、Catalog、ActionContract 与 LoopEvaluator；Planner 选择 semantic action，Runtime 在 contract 阶段选择 backend/binding。§10.6 登记处理结果。
> **2026-08-05 Material Binding 纠偏：** exact span 从通用高风险准入门降为间接非结构化来源的 provenance 形式；准入改由 `MaterialBindingPolicy/TaskSpecAuthority` 按 effect 校验 typed material field groups。SemanticAudit 不再以“存在任意一个 material anchor”代替字段完整性。§10.7 登记处理结果。
> **2026-08-06 Concrete Effect Authority / High-risk Governance 纠偏：** `8b91944` 的负向复核发现 operation mismatch、named-parameter swap、unknown DOM risk default-low 与 actual-binding-independent gate；2026-08-07 scope-reset 前复核曾证明 route/dispatch/cutover 尚未闭合，随后五项 MVP corrective closure 已完成。typed `EffectAuthorizationScope ⊒ RuntimeEffectSignature → ActionAuthorityProof` 保留为 foundation，更强 transaction/context hardening 后置。§10.8 登记修正结果。
> **2026-08-07 MVP Scope Reset：** 当前 fault model 是 one process / one run / one coordinator / one browser session / one active ActionContract，可信进程内组件串行执行 state mutation、approval consumption 与 effectful action。可信 adapter/provider 实现与 Runtime 配置属于 TCB，但其观察/返回的外部内容仍是不可信数据。P4 只要求 final immutable contract、approval/execution hash 一致、stale preflight 零调用、verifier-backed completion 与 uncertain-effect no-blind-retry；core benchmark 只是五项不变量/default route 的 closure evidence，不是第六项。更强 transaction/surface/provenance 设计保留为 future-hardening catalogue。§0.8、§6、§9.9 与 §10.9 按此解释。
> **事实时态边界：** §1.1–§1.16 保留 2026-08-05 plan-authoring / `8b91944` 阶段的问题输入；§1.17 保留 `26cc5bb804faa1a06e2aec4aa645ad84d3ecc73c` 的历史 corrective audit snapshot。它们都只解释“为什么迁移”，不覆盖 2026-08-07 scope reset；当前代码真值始终只由 `docs/implementation-status.md` 维护。

## 0. 演进决议

Affordance Runtime 的长期主线改为：

> **TaskSpec 是稳定、不可由 Planner 修订的用户授权合同；TaskPlan 是基于当前 observation 生成、可被整体替换的执行假设；ActionContract 是当前状态下唯一可执行的单动作事务；Task completion 只能由 TaskSpec 的终态表达式经独立验证后提交。**

对应工程方向是：

```text
薄 intake
    语义强：保留授权、约束、禁止效果、成功条件、来源和风险边界
    执行薄：不决定步骤、按钮、动作族、页面依赖或执行顺序

厚 execution loop
    基于当前观测规划
    Runtime 生成合法动作集合
    动作附近做能力与审批检查
    执行后重新观测并独立验证
    根据事实重规划，而不是修改 TaskSpec
```

这不是推倒 Runtime。重构重点是：

```text
UserRequest → TaskSpec → TaskPlan
```

应保留并收窄的是：

```text
SourceEnvelope + selective SourceAnchor
optional SemanticAudit (veto / clarify only)
UnifiedObservation
TaskPlanningRequest / ChoicePlanningRequest
Runtime-owned full ActionChoiceCatalog
bounded ChoicePage
PlannerProposal → ActionContract
Capability / Approval / Preflight
Execute → fresh observation → inline LoopEvaluationPhase
independent TaskCompletionEvaluator authority
bounded recovery
single sequencing Coordinator + single-writing RuntimeCommitter
```

当前演进边界明确不以生产级安全内核为目标：multi-tenant authorization、多个
worker/coordinator/agent 控制同一页面、distributed lease/fencing、hard-crash dispatch
recovery、恶意内部 permit cloning 和跨进程 policy revocation 均不在 MVP threat model。

### 0.1 Active-step authority 修正

上一版把 active-step 链写成：

```text
TaskProgress → PlanningRequest → Runtime-owned ActionChoiceSet
```

该顺序作废。它会允许 presentation budget 先裁剪 Runtime candidate space。唯一允许的顺序是：

```text
TaskProgress + Canonical UnifiedObservation
    → ActiveStepScope
    → Runtime-owned full ActionChoiceCatalog
        ├─ 0 choices → deterministic typed failure / perception / replan
        ├─ 1 choice  → Runtime direct selection
        └─ N choices → ChoicePresentationProjector
                         → bounded ChoicePage
                         → ChoicePlanningRequest
                         → StepChoicePlanner selects presented choice_id
```

正式不变量：

```text
ActionChoiceCatalog = f(
    TaskSpec revision,
    TaskPlan revision,
    active StepSpec,
    TaskProgress,
    Canonical UnifiedObservation,
    effective capabilities,
    Runtime policy
)
```

该函数不得读取 model presentation limit、provider token limit、label/state/artifact truncation 或 context compaction generation。

### 0.2 Source 默认路径采用方案 B+

旧的默认链：

```text
request → clause ledger → claim graph → obligation graph
        → model coverage audit → obligation-shaped plan
```

必须退出。唯一默认 intake 是：

```text
UserRequest
    → SourceEnvelope
    → MinimalIntentProposal with selective SourceAnchor refs
    → optional SemanticAudit for high-risk / multi-source / conflict
    → TaskSpecAuthority
    → immutable TaskSpec
```

`SourceEnvelope` 始终存在，只保存全文 identity/version、外部 source refs、caller/conversation identity 与 content digests；不做 clause splitting、dependency parsing、claim/coverage/obligation graph。直接用户明确 material value 使用 typed `DIRECT_USER_EXPLICIT` binding，无须预生成字符 offset；间接非结构化来源使用 field-matched exact excerpt，typed external ingress 使用 versioned field identity。`SemanticAudit` 只能 pass/veto/clarify，不能创建或修改 TaskSpec，也不代替 TaskSpecAuthority 的 effect-specific field coverage gate。

### 0.3 Verification 物理内化、逻辑分权

默认不建设独立 verifier service、VerifierPlanner、全量 EvidenceGraph 或长期全历史 EvidenceIndex。执行后主链固定为：

```text
TypedExecutionReceipt (transport only)
    → fresh canonical post-action observation
    → inline LoopEvaluationPhase
        ├─ external effect + collateral-safety settlement
        ├─ action effect evaluation
        ├─ active-step completion evaluation
        ├─ TaskSpec.success evaluation when triggered
        └─ observation continuation decision
    → RuntimeCommitter
```

`LoopEvaluator` 是 loop-native pure collaborator；它不执行动作、不修改 TaskProgress、不提交 terminal state。`TaskCompletionEvaluator` 只求值 TaskSpec.success 与 required constraints/final rechecks；只有 RuntimeCommitter 可以提交 `TaskCompleted`。

### 0.4 Semantic Authority Boundary 与合同闭包补充

“自然语言只理解一次”正式修正为：

```text
single semantic admission
+ bounded contextual rereading
+ no downstream authority expansion
```

只有 `TaskSpecAuthority` 可创建或修订 accepted meaning。`TaskPlanner` 可在里程碑分解确有需要时读取 bounded、read-only、`context_only` 的 `SourceContextView`；`OpenSemanticResolver` 只可读取 typed criterion 精确绑定的 SourceAnchor excerpts；`ClarificationComposer` 只可生成问题。三者的输出必须引用已有 TaskRequirement/Criterion/EffectAuthorization/SourceAnchor IDs，发现缺失语义时返回 `TaskSpecGap` 或 clarification。

ActionChoiceBuilder、Grounder/PredicateResolver、ActionSelectionValidator、ActionTransactionMaterializer、四重 gates、Executor、LoopEvaluator、TaskCompletionEvaluator 与 RuntimeCommitter 不接收 raw request 或 SourceContextView。页面、邮件、PDF、tool output 与 screen text 可用于 untrusted grounding data/evidence，不能创建用户授权、capability、approval、policy 或 control flow。

同一补充还冻结：

- flat canonical `TaskRequirement` table + one success tree；
- semantic value dependency 只在 typed refs，execution ordering 只在 `StepSpec.depends_on`；
- bounded semantic `ChoicePresentation`；
- required OutputSpec materialization/source binding 是 TaskCompleted closure 的组成部分。

### 0.5 Physical Minimality 与渐进启用

本轮不修改主链、不增加 authority，也不撤销 canonical `TaskRequirement`。它只冻结六条物理实现约束：

```text
full Catalog             → logically complete; eager/lazy/indexed/query-backed
canonical observation    → immutable epoch ref + read-only indexes
logical authority        → in-process pure policy is the MVP default
Criterion vocabulary     → separate from phase-specific provider coverage
replaceable TaskPlan     → TaskPlanner only on typed trigger
optional capability      → risk-derived profile, never correctness bypass
```

Direct/low-risk、multi-step 与 high-risk/multi-source profile 只决定 SemanticAudit、paging/refinement、ModelVerifier、open semantics 和 durable transaction evidence 等 optional machinery 是否启用。任何 profile 都不能关闭任务要求的 Task/Capability/Approval/Freshness gate、required-output closure、uncertain-effect protection 或 RuntimeCommitter single-writer。

### 0.6 Cross-Surface 显式化，不新增平行链

DOM、AX、Visual、SVG、WoT、API 与 Device 统一作为 acquisition、grounding、execution 与 evidence surfaces。它们共享一份 admitted TaskSpec、一个 current `TaskPlan<StepSpec>`、一个 logical full Catalog、同一 ActionContract admission chain 与 LoopEvaluator；任何 surface 都不拥有 task meaning、planning、completion 或 commit authority。

`Surface.WOT` 与 `WOT_DESCRIPTION / WOT_PROPERTY_STATE / WOT_ACTION_RESULT` 进入规范 vocabulary：Thing Description 只提供 capability/grounding metadata，property state 提供 fresh device-state evidence，action result 只提供 contract-bound receipt/outcome。Planner 只选择 backend-neutral semantic action；`ActionTransactionMaterializer` 编排的 route owner 才基于 current observation、evidence requirement、capability、risk、context/transform 与 policy 选择 current backend/binding。

### 0.7 Concrete effect authority 与高风险闭包

`8b91944` 的 exact identity/risk 变更保留为迁移起点，但不作为最终 contract。最终授权链固定为：

```text
TaskRequirement(kind=effect)
    → one parameterized EffectAuthorizationScope

Canonical target + actual ActionSupport/GroundingCandidate
    → Runtime-owned RuntimeEffectSignature

typed subsumption
    → ALLOW | DENY | UNPROVEN ActionAuthorityProof

ALLOW only
    → Catalog → selected choice → full Draft → actual sealed ActionContract
    → Task Gate independently rebuilds proof
    → effective capability intersection → seal exact contract
    → policy + exact approval of final immutable contract H
    → snapshot/page/target/expiry preflight for H
    → serial execute of H with approved_hash == executed_hash
```

它不采用两种错误极端：不让 Planner/label/risk score 猜 permission，也不枚举每个页面、任务或 action combination。系统只冻结少量 safety `EffectClass`、registered/versioned `OperationRef`、canonical resource scope、named parameter binding 与 risk/assurance policy。未知 classification 是 `UNPROVEN`；approval 不能补齐 proof，扩大授权只能创建新 TaskSpec revision。

### 0.8 MVP transaction chain 与 future hardening

P4/P5 只阻塞于以下最小链：

```text
fresh observation O1
→ full executable ActionContract materialization, including final payload
→ freeze and hash immutable contract H
→ policy/capability + exact approval evaluate H
→ snapshot/page/target/expiry preflight for H
→ serial Executor executes H, with approved_hash == executed_hash
→ typed transport receipt (never completion truth)
→ fresh post-action O2
→ LoopEvaluation settles effect + step/task evidence
→ actual OutputMaterialization when required
→ commit
```

在当前 one-process/one-coordinator/one-session 模型中，不要求独立
`FinalDispatchAdmission`、clone-resistant/global `DispatchPermit` registry、schema/policy
revocation linearizability、worker/lease fencing、attempt-bound collateral 或完整 run manifest。
这些合同保留为 future hardening，只有 threat model/benchmark/release claim 明确需要时才实施。

选择性吸收 SOTA 的边界固定为：

| 来源 | 吸收 | 不吸收 |
|---|---|---|
| [Qwen-UI-Agent report](https://tongyi-mai.github.io/Qwen-UI-Agent/Qwen-UI-Agent-Technical-Report.pdf) / [MAI-UI @ `30de90b`](https://github.com/Tongyi-MAI/MAI-UI/tree/30de90be4f83a0d11539adf2839da14a5755e0d3) | fresh isolated Web `BrowserContext`、environment action subset、GUI/CLI/API observation、`ask_user`/takeover、state-based intermediate verification | 把 isolated context 直接等同本地 lease；无反馈 effectful batch、裸 Bash、normalized coordinate 作为充分 identity |
| UI-TARS / AndroidWorld | typed actions、coordinate reference、logical/physical frame、orientation/stable-state handling | generic success/error、schema unavailable 时 fail open、polling 代替 effect evidence |
| GUI-Actor | candidate/verifier 作为 optional acquisition evidence | candidate 直接成为 locator/absence/authority truth |
| CaMeL | trusted control / untrusted data 在 effectful sink 的窄 typed enforcement | 全程序通用动态污点平台、prompt-only enforcement |
| AgentDojo / WASP | future release profile：benign utility、utility-under-attack、targeted ASR | 成为 P4/P5 blocker、线上依赖或单一安全证明 |
| OSWorld-V2 | future breadth/release profile：functional checkpoints、partial progress、risk-scoped collateral probes | 成为 P4/P5 blocker；reward/judge 进入 production completion authority |
| [A Modular Action System Architecture @ `5d5847e`](https://github.com/Garrulus21yyx/A-Modular-Action-System-Architecture/tree/5d5847e28cd385f7aaf02bab51d020fd46bb7f89)（private adjacent source） | 本机既有 task-scoped `BrowserSession`、mark-ID grounding、total `ExecutionResult` 与共用 benchmark adapter | 不视为公开 SOTA 或充分 authority；补强 context generation、transform digest、transport/effect/collateral，并隔离 benchmark authority |

来源事实与本地推导必须分栏理解：Qwen 的 context isolation/action subset/state verifier 不等于本文的 `SurfaceLease`、capability intersection 或 completion authority；后者是可选本地补强。物理实现保持 modular monolith。Corrective slices 只新增最小所需 refs/value objects/pure policies；不建设微服务、通用 graph/theorem prover、per-namespace DB、分布式 lease、unbounded event sourcing、batch rollback 或 general taint platform。只有声明 hard-crash dispatch recovery 时，才允许增加窄化 durable dispatch journal；它不是进入 P5 的默认前置。

## 1. 历史问题输入与最新实现复核

本节区分五类状态，禁止把历史问题输入重新解释成当前实现宣称：

- `HISTORICAL_INPUT`：§1.1–§1.16 在 plan-authoring / named revision 当时可复现的行为；只保留迁移 rationale。
- `HISTORICAL_CORRECTIVE_INPUT`：§1.17 在 `26cc5bb...` 基线复核出的当时缺口；不覆盖当前 scope reset 或 implementation status。
- `KEEP`：历史输入中识别、并由目标架构继续保留的边界；是否已实现仍查 implementation status。
- `GAP`：对应快照中的语义损失、职责混杂或权威缺口；若已迁移，不自动仍算当前 gap。
- `TARGET`：本规划要求达到、但不代表已经实现的目标。

### 1.A `HISTORICAL_INPUT`（§1.1–§1.16）

以下小节原样保留当时的代码路径、类名和“当前”措辞，以便解释替代式迁移来源。
这些陈述不得覆盖 implementation status，也不得作为旧 owner 仍存在的证据。

### 1.1 `[HISTORICAL_INPUT]` 任务语义被 intake graph 提前固化为执行计划

`PlanCandidateGeneratorRouter.generate()` 在 `task_spec.obligations` 非空时优先选择 rule generator；`_steps_from_task_spec()` 随后为每个 obligation 调用 `_step_from_obligation()`。因此当前默认链是：

```text
Intake LLM
    → obligation graph
    → one obligation / one StepSpec
    → TaskPlan shape
```

即使 `TaskPlanningContext` 已包含当前 snapshot、affordances、failures 和 budget，obligation 路径仍主要由 intake graph 决定计划粒度。问题不是 Planner 还不够智能，而是 `what / authorization boundary` 与 `how under current observation` 的职责边界错误。

### 1.2 `[HISTORICAL_INPUT]` Obligation 的语义角色不稳定

当前 `TaskObligationSpec` 同时包含 predicate/effect、blocking、terminal、dependencies、interaction、capability 与 evidence。它试图同时表达：

- action/step 前置条件；
- 局部进展效果；
- task 终态效果；
- evidence 要求；
- planning dependency。

因此 `is_available` 可能被错误放到 terminal completion。以“关闭弹窗”为例：

```text
close control is_available
```

只证明动作可执行，不证明 `dialog is_absent`。仓库 obligation audit 中 choose-list 与 click-dialog 的 `fail_closed_pending_rule` 正是这一角色漂移的证据。

角色必须由容器位置决定：

| 语义角色 | 唯一目标容器 | 能推进 Step | 能完成 Task |
|---|---|---:|---:|
| `PRECONDITION` | `StepSpec.preconditions` / `ActionContract.preconditions` | 否 | 否 |
| `PROGRESS_EFFECT` | `StepSpec.completion` | 是 | 否 |
| `TERMINAL_EFFECT` | `TaskSpec.success` | 可间接 | 是 |
| `EVIDENCE_ONLY` | criterion 的 `CriterionPolicy` + current/outcome/durable evidence | 否 | 否 |

### 1.3 `[HISTORICAL_INPUT]` 同一语义存在多套重叠图

当前至少存在：

```text
TaskSpec obligation DAG
PlanCandidate<StepSpec> DAG
TaskPlan<SubgoalSpec> DAG
TaskPlanView<StepSpec> DAG
criterion / ActionChoice IDs
```

这些结构之间发生字段裁剪、ID 重建、粒度变化和 completion semantics 重解释。复杂度增加，但语义正确性不会随 projector 数量自动增加。

目标只保留：

1. `TaskSpec.success` 的任务语义表达式树；
2. 当前 `TaskPlan<StepSpec>` 的执行 DAG；
3. Fact / Binding、bounded RecentActionOutcome、small DurableEvidenceStore 与 append-only Trace。

ActionChoiceCatalog 是当前 active-step epoch 的合法候选集合，ActionContract 是单动作事务，TaskProgress 是状态账本；它们都不是新的任务语义图。

### 1.4 `[HISTORICAL_INPUT]` `StepSpec → SubgoalSpec → StepSpec` 是真实有损往返

当前 binder 的 `_subgoal_from_step()`：

- 只读取 `completion_criteria[0]`；
- 把 expected value 转成字符串；
- 从来源引用反推 evidence requirements；
- 根据文本重新猜测 action family。

随后 legacy projection 再恢复 `StepSpec` view。复合 criterion、第二个及以后 criterion、原始值类型、evidence policy 和 interaction semantics 都可能丢失。

目标是直接替换为：

```text
PlanProposal<StepSpec>
    → TaskPlanAuthority
    → TaskPlan<StepSpec>
```

Authority 只增加 plan identity、version、supersession、observation/state binding、digest 与 admission result，不做语义形状转换。

### 1.5 `[HISTORICAL_INPUT]` Typed evidence 没有沿主链完整保留

obligation-to-step 与 provider-candidate-to-step 路径会使用默认 `dom_state` evidence source，没有完整保留 obligation 的 typed evidence requirements。目标链应为：

```text
Task / Step criterion
    → minimal CriterionPolicy
    → LoopEvaluator + available internal evidence providers
    → typed CriterionEvaluation / TaskCompletionEvaluation
```

TaskSpec 与 StepSpec 不绑定某个 DOM verifier 实现；criterion leaf 只保留 satisfaction、validity、assurance、allowed source kinds 与 model fallback。当前 observation、bounded ActionOutcome 与 durable evidence 分层提供证据，不把 provider 计划塞进 ActionContract。

### 1.6 `[HISTORICAL_INPUT]` Plan completion 与 task completion 仍未隔离

`TaskPlanLifecycle.completed()` 只检查全部 legacy subgoal ID 是否进入 `completed_subgoal_ids`。`TaskCompletionVerifier` 对 TaskSpec-backed task 主要检查是否存在 passed independent verification；它没有递归计算完整 `TaskSpec.success` closure。

错误传播链可能是：

```text
错误 obligation role
    → 错误 plan step
    → step verifier 证明了错误 predicate
    → all subgoals complete
    → latest verification passed
    → task completed
```

目标必须改为：

```text
all current plan steps verified
    → PLAN_EXHAUSTED

PLAN_EXHAUSTED
    → independently evaluate TaskSpec.success

success passed
    → TASK_COMPLETED

success failed / inconclusive
    → REPLAN / RECOVER / ASK_USER / BLOCK / FAIL
```

**`PLAN_EXHAUSTED` 永远不等于 `TASK_COMPLETED`。**

### 1.7 `[HISTORICAL_INPUT]` TaskPlanAuthority 当时更接近 binder

当前 authority admission 仍依赖 binder 产生 legacy plan，完整语义校验在 lifecycle 外部进行。目标边界是：

```text
PlanProposal
    → TaskPlanAuthority
        validate
        reject / repair-required / clarify / accept
        bind identity and observation basis
    → immutable TaskPlan<StepSpec>
```

TaskPlanAuthority 不添加步骤、不授予 capability、不修改 TaskSpec，也不把一种 step 类型转换成另一种。

### 1.8 `[HISTORICAL_INPUT]` TaskSpec 当时更像抽取结果数据库

当前 TaskSpec 同时保存 objective、operation class、task structure、targets、requested effects、entities、preferences、outputs、success strings、semantic constraints、source claims、obligations、forbidden effects、evidence strings、capabilities、ambiguity 与 field provenance。

这些内容不是都无价值，但必须迁移到职责稳定的容器：

| 当前概念 | 目标位置 |
|---|---|
| 用户授权效果、硬约束、禁止效果、终态 | `TaskSpec` |
| 来源 identity/version 与 material-field lineage | always-on `SourceEnvelope` + risk-proportionate `MaterialBinding`；exact SourceAnchor 仅为一种 provenance form |
| 高风险/多来源/conflict 的细粒度 coverage audit | optional `SemanticAudit`，veto/clarify only |
| 步骤、依赖、interaction intent、action budget | `TaskPlan<StepSpec>` |
| 已完成状态、facts、bindings、evidence instances | `TaskProgress` 与 append-only ledgers |
| 当前动作、locator、backend、TTL、evaluation requirements | `ActionContract` |
| 未解决 ambiguity | 不准入 TaskSpec，返回 clarification |

### 1.9 `[HISTORICAL_INPUT]` Canonical observation 当时先受模型预算裁剪

当前生产路径由 bounded `PlannerObservationView` 构造 `UnifiedObservation`，Runtime ActionChoiceBuilder 因而可能与模型共享同一个被裁剪的候选空间。目标是：

```text
DOM / AX / Visual / SVG / WoT / API / Device
    → PerceptionCapture (acquisition DTO; current BrowserSnapshot role)
    → CanonicalObservationBuilder
    → canonical UnifiedObservation
        ├─ full Runtime target/binding/conflict/coverage view
        ├─ bounded TaskPlanningObservationView
        └─ bounded ChoicePage
```

“full”指 Runtime 在已声明 acquisition coverage 内取得的 canonical target view，不是外部世界全集，也不是把无界 DOM 或全部页面文本塞入模型。必须区分三个预算边界：

| 预算边界 | 可以影响 Runtime choices | 必须记录 |
|---|---:|---|
| perception acquisition budget | 是 | source coverage、截断与遗漏估计 |
| Runtime semantic admission | 是 | rejection reason 与 build report |
| model presentation budget | 否 | projection policy、总数、展示数、continuation |

`BrowserSnapshot` 长期语义收缩为 `PerceptionCapture` 输入 DTO；`UnifiedObservation` 是唯一 current semantic observation authority；`TaskPlanningObservationView`、`PlannerObservationView` 与 `ChoicePage` 都是一次性 presentation view。production path 必须删除 `UnifiedObservation.from_planner_observation(...)`，且任何 Runtime choice、grounding、contract、preflight 或 verification 组件不得从 presentation view 恢复事实。

Canonical target 必须保留 all source surfaces、逐 action 的 executable bindings、typed state facts、source assertion refs、freshness，以及 `RESOLVED / NO_MATERIAL_CONFLICT / MATERIAL_CONFLICT / INCONCLUSIVE` conflict status。source 未展示、source 未采集和 target 真不存在不得编码成同一个空 tuple。

### 1.10 `[HISTORICAL_INPUT]` PlanningRequest 之后仍有重复领域投影

当前 `PlanningRequest → PlannerContext → provider messages` 会重建 task、step、progress 和 observation 视图。目标是：

```text
Canonical Runtime authority
    → explicit presentation projector
    → one immutable typed TaskPlanningRequest or ChoicePlanningRequest
    → pure provider serializer
    → provider messages
```

Serializer 可以排序、限长、脱敏和做 provider 格式适配，但不得重新解释任务、计算 active step 或修改 action scope。

Strict `StepChoicePlanner` 不再接收通用 affordance inventory，也不拥有 `ActionChoiceBuilder`、`ActiveStepScope`、`UnifiedObservation.from_planner_observation` 或 `ActionChoiceDispatcher`。它只在 supplied `ChoicePage` 上返回封闭选择/翻页/typed refinement/ask/defer 决策。

### 1.11 `[HISTORICAL_INPUT]` 最终证据需要 validity 与 causality 语义

“目标状态现在为真”与“本次动作造成了目标状态”不是同一命题。criterion 必须声明：

```text
SatisfactionMode =
    STATE_HOLDS
  | ACTION_CAUSED
```

Evidence validity 独立区分：

```text
CURRENT_OBSERVATION
RECENT_ACTION
DURABLE
FINAL_RECHECK
```

assurance 只需 `WEAK / STRUCTURAL / AUTHORITATIVE`。旧证据只有在 `DURABLE` policy 允许且未失效时复用；`RECENT_ACTION` 只允许 `ACTION_CAUSED + causal_lineage_required`，并绑定 current task/ActionContract 的 bounded ActionOutcome。它只证明过去动作造成过效果，不证明当前状态仍成立；当前状态必须由独立的 `STATE_HOLDS + CURRENT_OBSERVATION` leaf 证明。`FINAL_RECHECK` 必须使用最新且 assurance 为 `AUTHORITATIVE` 的权威 recheck。

### 1.12 `[HISTORICAL_INPUT]` 当时默认 SourceLedger 路径过重

当前实现仍默认创建 whole-request + 最多 32 个 clause units，标记 `required_candidate`，要求模型返回 source claims/obligations，并执行 deterministic/model-backed obligation coverage。clause 超限会在模型调用前 fail closed。它把 provenance correctness 与 semantic graph completeness 绑在一起，继续让 intake graph 影响 plan shape。

目标不是删除 provenance，而是拆为：

```text
always-on SourceEnvelope
+ selective SourceAnchor
+ optional SemanticAudit
```

SourceEnvelope 只拥有合法 authority source 的 identity/version；SemanticAudit 才按风险执行 span/coverage/conflict 审计。普通任务不得因未建立 clause/claim/obligation graph 而失败。

### 1.13 `[HISTORICAL_INPUT]` Verification 主线存在过重与不安全两类风险

长期能力地图中的 VerifierPlanner、provider registry、EvidenceIndex、validity/composite evaluator 不应整体成为默认生产平台；默认 GUI Runtime 只需要 loop façade、typed predicates、current observation、recent ActionOutcome 与 small DurableEvidenceStore。

同时以下 legacy 行为必须 fail closed：

- `VerifierLadder.verify()` 无 specs 时不得退化为 `receipt.success`；
- verification disabled 不得生成 `PASSED`；
- latest passed report 不得完成 task；
- description-based criteria matcher 不得拥有 completion semantics；
- `terminal_readiness` 只能保留 legacy action-admission compatibility，不能扩张为 task completion authority。

### 1.14 `[HISTORICAL_INPUT]` 修订前未成文的合同缺口（现已在目标合同补齐）

旧文档已经禁止 strict Planner/Coordinator/recovery/benchmark natural-language fallback，但没有区分“读取 source-bound context”和“写入 accepted meaning”。如果进一步扩张成 TaskSpec 后绝对禁读，会让 OpenSemanticCriterion、里程碑语用与澄清措辞丢失；如果保持无边界读取，又会让 Planner/执行链从 objective/raw text 临时恢复授权。

同时，修订前的 allowed effects、constraints、success 与 requested outputs 可能分别重述同一 material requirement；StepSpec 缺少通用 requirement traceability；ChoicePage 未完整冻结 N-choice 语义展示字段；required output 尚未明确进入 TaskCompleted closure。这些缺口现已由目标合同补齐，但不代表当前代码已完成切换。

### 1.15 `[HISTORICAL_INPUT]` 逻辑边界被物理化得过重

当前目标主链已消除重复语义图，剩余过重风险主要来自实现方式：全量物化大型 Catalog、复制巨型 observation、每个 owner 建独立服务/数据库、一次性实现全部 criterion provider、每轮重规划，以及所有任务默认启用 SemanticAudit/paging/ModelVerifier/OpenSemanticResolver。

以下风险已由现有合同覆盖：选择性 SourceAnchor、risk-triggered SemanticAudit、bounded evidence 生命周期、ModelVerifier 后置、raw-text 三层边界、ChoicePresentation 与 output closure。以下风险仍需作为实现门：logical Catalog membership 与物化策略分离、observation epoch/index、authority/部署分离、operator/provider coverage 分离、typed replanning trigger 和 risk-derived profile。

### 1.16 `[HISTORICAL_INPUT @ 8b91944]` coarse concrete-action proof

最新 push 已正确移除 keyword token overlap，并让 Runtime 而非 Planner 派生 effectful/risk；但 production proof 仍以 free-form `target_identity/destination_identity`、coarse `operation_class`、无字段 scalar value set 与 source-declared risk 为主，最终 Task Gate 复算的也是从 choice 复制到 contract 的 authority fields，而不是 actual bound grounding candidate。

针对该 revision 的四个独立负向探针均可复现：

| Probe | 当前结果 | 应有结果 |
|---|---|---|
| TaskSpec 为 NAVIGATION，同一 exact target 上构造 TYPE_TEXT | authorized | DENY / operation mismatch |
| admitted `recipient=Alice, amount=100`，choice 交换两个字段值 | authorized | DENY / named parameter mismatch |
| 普通 DOM `<button>Delete account</button>` 无自报 risk | LOW | UNPROVEN 或由 Runtime policy 分类为 destructive |
| contract 复制 Alice proof fields，但 actual `affordance_id/locator` 指向 Bob | Task gate allow | DENY / actual binding mismatch |

因此 P3 requirement traceability 与 P4 closed choice port 可以保持完成，但“concrete action legality/high-risk governance complete”的表述必须撤回。该缺口进入 P4-G corrective closure，不留给 P5 containment，也不允许保留 old proof 作为 fallback/shadow owner。

### 1.B `HISTORICAL_CORRECTIVE_INPUT`

### 1.17 2026-08-07 implementation audit snapshot：当时的 transaction 缺口

以完整 commit `26cc5bb804faa1a06e2aec4aa645ad84d3ecc73c` 为事实基线，当时代码存在以下 production gaps；它们是 corrective slices 的历史依据，不是当前状态或新的目标平台：

| 事实缺口 | 风险 | 修订落点 |
|---|---|---|
| product `RuntimeFeatures` 可关闭 safety path，disabled capability 还能合成 grants | benchmark ablation 泄漏到产品，能力 fail-open | `P4-C0` |
| approval request 可早于 committed fresh O1；preflight 对旧 contract 做 partial `replace` | fresh proof 与旧 locator/payload/verifier 混合，审批对象可变 | `P4-C3` |
| current contract 无单一 `RouteBinding` + pinned encoder closure；authorized named parameters 与 backend payload/locator 可成为平行事实 | hash 只能密封错误载荷，不能证明 proof=Alice 时 payload 也指向 Alice | `P4-C3` |
| approval wait 后无 revision-bound final-admission/revocation linearization | PF 检查与 intent/permit 间撤权仍可能 TOCTOU | `P4-C4` |
| current route/locator/payload 无 whole-contract secret-free schema 与 signed-URL late-binding gate | token/signature/credential query 可能进入 contract/trace/checkpoint | `P4-C3`–`P4-C5` |
| attempt/dispatch intent 未在 Executor 前提交 | crash/并发/重放时不能诚实判定发送边界 | `P4-C4`；hard-crash 时另需 `P4-R0` |
| receipt 仍可被 Boolean 化，transport/effect settlement 不对称 | success/exception/timeout 被误当业务效果或未发送 | `P4-C4`–`P4-C5` |
| context 只近似绑定 URL/DOM，无 account/session/window/frame/transform identity | 错账号、错 tab、旧坐标仍可能通过 | `P4-C2` |
| coverage 可由已有 candidates 推断 complete，缺失 coverage fail open | 未观察被当作不存在 | `P4-C1` |
| OutputSpec metadata 仍可被当作 final result | 声明输出冒充真实结果，trace 可能泄露敏感值 | `P4-C1` |
| TaskPlanAuthority 主要检查 ID membership | read requirement 可被包装成未授权 mutation | `P4-C1` |
| canonical materialization 路径仍存在 legacy proposal/fallback coupling | 双 owner 与局部 patch 继续存活 | `P4-C3` / `P4-C5` |
| WASP 只有 manifest/配置，尚无实际 adversarial metrics gate | 安全宣称缺少可重复 utility/ASR 证据 | `P4-C5` 的 offline gate；不进入 Runtime authority |

该表解释旧 corrective work 的来源，不是当前 P5 gate。scope reset 后只有五项 P4-MVP
invariant 是语义门；fresh core benchmark 已证明这五项在默认主线上的 closure，并未增加
第六项 invariant。因此 `P4 CLOSED (MVP scope)`，P5 准入解除但尚未开始。表中的 tenant/context、revocation
linearizability、permit/fencing、collateral 和 multi-suite 项均按 future hardening 处理。

## 2. 明确保留的项目资产

### 2.1 TaskPlan，但改变来源与身份

保留 TaskPlan 作为当前 observation 下可替换的执行假设。它可以是完整小 DAG、rolling-horizon partial plan 或单 step plan；不再机械等于 obligation graph。

### 2.2 两种 PlanningRequest 的边界

- `TaskPlanningRequest`：供低频 Task Planner 生成宏观可验证里程碑。
- `ChoicePlanningRequest`：仅在 Runtime 已建立完整 Catalog 且确有 N 个 choices 时，供高频 Step Planner 在当前 `ChoicePage` 中选下一动作或请求受控检索。

两者不能共用一个含混的 `PlanningRequest` 名称和响应协议。

### 2.3 Runtime-owned full ActionChoiceCatalog 0/1/N

- 0 个 choice：根据 source coverage、required state、conflict 与 rejection report 确定性分类，交明确 owner；
- 1 个 choice：Runtime 自动选择；
- N 个 choices：Runtime 保留完整 Catalog，模型只能选择当前 `ChoicePage` 展示的 `choice_id`，或请求下一页/typed refinement/ask/defer。

模型不能发明 selector、coordinate、backend、locator、shell/Python、任意参数、approval token、新 capability、TaskSpec revision 或 task-completed 结论。

大候选空间使用四层协议：Runtime semantic admission → full Catalog → bounded ChoicePage → sealed planner response。effectful/high-risk action 在 page 截断且不存在 Runtime 可证明的唯一授权匹配时，必须继续检索或澄清，不得仅从当前页选择后执行。

### 2.4 Planner selection → Draft / Sealed ActionContract

语义选择与具体执行继续分离。`ActionTransactionMaterializer` 只从 committed fresh O1 一次性建立 non-executable Draft；独立 Task Authority 与 capability intersection 通过后才能形成 `SealedActionContract`。sealed payload 绑定 state/observation、execution context、live surface generation、coordinate transform、target/route、parameters、backend/tool schema capability descriptor、risk/proof、expected effects/verifier requirements、TTL、idempotency 与 provenance digests。旧合同不得 partial patch。

### 2.5 动作附近审批

审批只绑定 fresh sealed contract，而不是 Draft、intake 意图、TaskPlan 或 action family。ApprovalRequest/Grant 绑定 run/session-generation nonce、contract hash、context/surface/transform/capability/proof digests、approver、expiry。existing gate owners 在 final freshness/revocation check 后签发 revision-bound `FinalDispatchAdmission`；它与 grant/state CAS、attempt/dispatch-intent commit、permit issuance 在同一同步线性化边界单次消费。状态变化、late/revoked grant、interrupt/cancel/restart 或 contract rebuild 使旧审批/admission tombstone/失效。

### 2.6 执行后独立验证

TypedExecutionReceipt 只证明 transport/执行器报告的一次尝试，不能把 SENT 当作 effect occurred。verification 作为 `LoopEvaluationPhase` 内化进 serial execution loop，但 transport、external effect/collateral、step completion、task completion 仍使用不同类型。没有适用 evidence/provider 时为 `UNKNOWN` 或 `UNSUPPORTED`，绝不因 verification disabled、provider/schema exception 或无 verifier spec 返回 passed。

默认只保留三类 evidence location：

- current-state facts 留在 canonical `UnifiedObservation`；
- action causality 留在有界 `RecentActionOutcomeIndex`；
- artifact/resource/transaction/human confirmation 等跨 epoch 证据进入小型 `DurableEvidenceStore`。

### 2.7 Grounding、Recovery、单写者与离线证据链

- Grounding 只消费 typed intent 与 current observation，不重读用户原文；
- FailureEnvelope → owner → bounded recovery decision 的骨架保留；
- Coordinator 只串行提交 typed transitions 与 trace 顺序，不实现领域算法；
- Trace、Artifact、Benchmark 与 Skill Evolution 是异步或离线消费者，不拥有当次 task completion。
- Mechanical DOM/AX/API/artifact/network providers 作为 LoopEvaluator 内部 evidence providers 保留；ModelVerifier 延后且只能产 evidence。

## 3. 目标语义与合同模型

### 3.1 TaskSpec v2

TaskSpec 只定义：

- human-readable objective；
- flat canonical TaskRequirement table；
- 用户提供或明确授权的 inputs；
- allowed-effect、hard-constraint、preference 与 forbidden-effect requirement refs；
- 唯一 task success expression；
- stable required OutputSpec + typed materialization criterion；
- capability ceiling，而非实际 capability grant；
- risk policy reference；
- source envelope identity 与 source binding digest。

Task Planner 的 semantic authority 只能来自 TaskSpec；可选 SourceContextView 只是 `context_only` 的只读语用上下文。只有用户澄清、用户修改或授权策略变化才能由 TaskSpecAuthority 创建新 revision。

### 3.2 封闭 Semantic AST 与受限开放节点

第一版必须支持：

- `ValueExpr`：Literal、InputRef、BindingRef、FieldRef、ObservationValueRef、少量 deterministic normalization；
- `PredicateExpr`：equals、contains、starts/ends with、regex、comparison、between、in-set、exists/absent、visible/available/enabled/selected/checked/expanded、ordered-as、changed、contains-entity；
- `CriterionExpr`：AllOf、AnyOf、Not、Exists、Count；
- `OpenSemanticExpr`：仅用于保真保存尚无 registered operator 的明确语义，不直接产生执行权。

`Not` 只能来自用户否定、deterministic normalization 或 source-bound TaskSpec proposal，Planner 不得用它修复已满足的 positive criterion。

### 3.3 CriterionPolicy 附着在 criterion leaf

第一版使用最小 `CriterionPolicy`：

```text
SatisfactionMode     = STATE_HOLDS | ACTION_CAUSED
EvidenceValidityMode = CURRENT_OBSERVATION | RECENT_ACTION | DURABLE | FINAL_RECHECK
AssuranceLevel       = WEAK | STRUCTURAL | AUTHORITATIVE
```

并保存 allowed source kinds 与 `model_fallback_allowed`。`RECENT_ACTION` 仅与 `ACTION_CAUSED + causal_lineage_required` 配合，表达 bounded Runtime ActionOutcome 已造成过效果；若还要求当前状态，必须增加独立 `STATE_HOLDS + CURRENT_OBSERVATION` leaf。`FINAL_RECHECK` 的 minimum assurance 固定为 `AUTHORITATIVE`。source kind 属于 evidence policy，不扩张成 DOM/API/Visual × predicate 的 criterion 类型组合。Model evidence 默认不具备 AUTHORITATIVE assurance。

### 3.4 TaskPlan、StepSpec 与 TaskProgress

TaskPlan 保存 plan identity/version、TaskSpec identity/revision、based-on state/snapshot、steps、assumptions、replan triggers 与 supersession。

Step 按以下边界拆分：

- 独立可验证里程碑；
- 数据或 binding 依赖；
- 跨页面、应用、设备或环境边界；
- 高风险动作前后的准备/审批边界；
- artifact handoff；
- 必须重新观测的边界；
- 独立 recovery 边界。

字段填写、单次 click 或每个 obligation 默认属于 active step 的 action loop，不自动升级为 task-level step。

TaskProgress 不复制 plan DAG，只保存 current plan ref、active step、verified step records、Fact/Binding ledgers、bounded recent ActionOutcomes、DurableEvidenceStore ref、failures、recovery state、budgets 和 replan count。Current-observation evidence 不复制进长期 store；只有 durable evidence 跨 epoch。Replan 不要求复用旧 step ID；已验证事实、bindings 与 durable evidence 按 policy 复用。

### 3.5 Semantic Authority Boundary 与 SourceContextView

`SourceContextProjector` 只能根据 admitted TaskSpec source binding 投影：

```text
SourceContextView(
    accepted anchored excerpts,
    linked requirement/criterion IDs,
    optional non-authoritative request summary,
    authority = context_only,
)
```

允许 consumers 仅为 TaskPlanner、OpenSemanticResolver 与 ClarificationComposer。Task Planner 输出 StepSpec requirement/effect refs；OpenSemanticResolver 只解释现有 OpenSemanticCriterion；ClarificationComposer 只生成问题。任何 consumer 发现 TaskSpec gap 都必须停止并返回 typed gap/clarification，不能创建新 requirement 或 patch TaskSpec。

### 3.6 Atomic requirement identity

每个 material user requirement 只有一个 `TaskRequirement.requirement_id` 和一个 typed `RequirementExpr`。Authorization、constraint、preference、success leaf 与 OutputSpec 引用该 identity，不各自维护 free-form semantic copy。`TaskSpec.objective` 是 explanatory summary，不是 fallback authority。

每个 StepSpec 增加 `requirement_refs`；effectful Step 另有 `effect_authorization_refs`。TaskPlanAuthority 先验证 identity，再以确定性 typed subsumption 检查 operation、subject/resource、destination、material named values、element function、task usage 与 source→sink flow。仅引用合法 ID 不能使不相容的 effect 成为合法 step；无法证明则 `REJECTED/REPAIR_REQUIRED`，不引入 theorem prover。

### 3.7 Dependency 单一落位

- semantic value dependency：`InputRef / BindingRef / ObservationValueRef / ValueExpr`；
- execution milestone ordering：current TaskPlan `StepSpec.depends_on`；
- accepted TaskSpec：不保存 claim/obligation dependency graph。

### 3.8 ChoicePresentation 与 required output closure

每个 `ChoicePresentation` 必须包含 bounded target label/role、destination、relevant current state、requirement/effect refs、evidence refs、conflict、risk 与 generation reason codes；不得包含 selector、coordinate、locator、backend handle、approval token 或 hidden IDs。

每个 required OutputSpec 必须有 stable output ID、typed materialization criterion 与 source-binding policy；实际 `OutputMaterialization` 另行携带 typed value/artifact ref、schema/content digest、source refs、task/step/observation lineage 与 privacy policy。TaskCompletionEvaluator 除 success root、constraints、external effects、collateral verdict 和 final rechecks 外，还必须证明所有 required outputs 实际 materialized，并按声明 source-bound；OutputSpec metadata/Planner prose 不能代替 structured output。

### 3.9 Physical realization contract

- `ActionChoiceCatalog` 保存 logical membership/digest/count/rejection semantics；小空间 eager materialize，大空间使用 immutable lazy/indexed/query-backed membership，model page size 永不进入 membership。
- `UnifiedObservation` 作为 immutable epoch contract，可由 ObservationEpoch + Target/Binding/Fact/Coverage indexes 物理实现；Runtime 通过 ref/read-only index 访问，不在每个阶段复制全图。
- Authority matrix 定义 owner/deny/write semantics，不要求独立服务。MVP 使用 modular monolith、pure validator、in-process policy composition 和可分 namespace 的轻量 RunLedger。
- Canonical Criterion vocabulary 可以大于当前 provider coverage；首期 mechanical baseline 稳定后再扩展，未支持 operator 返回 `UNSUPPORTED`。
- TaskPlanner 只在 typed planning/replanning trigger 上运行；current active step 仍可行时复用计划。
- `DIRECT_LOW_RISK`、`MULTI_STEP`、`HIGH_RISK_MULTI_SOURCE` profile 只渐进启用 optional machinery，不削弱 correctness/safety/closure。

### 3.10 Cross-Surface contract

- CanonicalTarget 保留 DOM/AX/Visual/SVG/WoT/API/Device 的全部 current bindings、source assertions、coverage 与 conflicts，不选择 representative surface。
- 同一 target 的无冲突多 binding 通常只产生一个 backend-neutral semantic choice。
- Planner selects the semantic action；`ActionTransactionMaterializer` 编排的 route owner selects the current backend/binding。
- route 失效时必须 fresh reobserve、rebuild contract；旧 approval/contract 不得跨 route 复用。

### 3.11 Concrete effect authority 与 high-risk contract

Effectful `TaskRequirement.semantic_payload` 内唯一保存 parameterized `EffectAuthorizationScope`：registered/versioned `operation_constraint`、canonical resource/destination scope、named input/binding slots、small safety effect class、externality/reversibility、minimum source assurance 与 risk/approval/completion policy refs。它只表达用户授权 ceiling，不保存 current action kind、backend、candidate、epoch 或 Runtime confidence。`allowed_effect_refs` 继续引用该 requirement ID，不新增 universal effect graph。

Runtime 依据 current canonical target、actual ActionSupport/GroundingCandidate/backend operation/source assertions 生成不同类型的 concrete `RuntimeEffectSignature`，并通过 typed subsumption 得到 tri-state `ActionAuthorityProof`。Runtime risk 取 effect class、externality、reversibility、resource sensitivity、amount/recipient、capability、source uncertainty 与 conflict 的保守最大值；Text/VLM 只能升风险或触发观察/澄清，不能产生 ALLOW、降风险或创建授权。Catalog 只包含 ALLOW；DENY 与 UNPROVEN 分别进入 typed rejection/recovery。`ActionTransactionMaterializer` 的 route owner 对最终 route 重新生成 signature，Task Gate 再从 TaskSpec + current observation + actual bound transaction 独立重建带 evaluator-policy version 的 proof。

Planner 只可输出 step objective、interaction intent、requirement/effect authorization refs、completion、dependencies 与 budgets。`StepSpec.effectful` 若仍存在于外部兼容输入，只能作为待删除 hint；Runtime 的 effect、risk、Catalog membership、backend route 与 approval 不读取它，canonical StepSpec 最终不保存该 authority field。

高风险策略采用少量 effect class × effect-specific field/policy matrix；不枚举网站、页面、TaskType 或 GUI action combination。未知 operation/effect/externality/reversibility/risk/assurance fail closed；approval 只批准已授权的 exact contract，并向用户显示 concrete action、resource/destination、named material parameters、reversibility、backend operation、来源与不确定性，不能代替 TaskSpec revision。uncertain external effect 不盲重试，完成需要 policy 要求的 causal outcome 与 authoritative final recheck。

### 3.12 Transaction / context / provenance extension catalogue

MVP 顶层合同只要求 final immutable `ActionContract`、其 hash、freshness identity、typed
receipt 和必要 `OutputMaterialization`。`ExecutionContextRequirementRef`、
`LiveSurfaceBinding`、`CoordinateBinding`、`ExecutorCapabilityDescriptor`、
`FinalDispatchAdmission`、`DispatchPermit` 与 `RunProvenanceManifest` 均是可选 extension
contracts，不是必须一次实现的服务/类型清单。它们只有在对应 account/coordinate/provider、
并发、恢复或 release claim 被纳入时才成为 acceptance requirement。

- durable context ref 只保存 opaque account/profile/tenant/app scope；live surface 绑定 session generation/run owner/window/tab/frame/document/focus/SurfaceLease，restart 永不复活；
- coordinate binding 覆盖 screenshot/viewport/crop/scroll/DPR/zoom/OS scale/orientation/origin/transform digest，selector/node 同样绑定 document/frame；
- effective capability 是 provider/tool schema、environment adapter、product policy、user grant 的交集；
- sealed contract 来自同一 committed O1，approval 位于 seal 之后；final admission/grant consume 与 state CAS、attempt/dispatch-intent commit、permit issuance 同步线性化且位于 Executor 之前；
- transport 与 effect 分型；风险类别只触发必要 collateral probes；
- manifest 固定 code/policy/provider/model/schema/transform/acquisition/verifier/environment，replay 无 live fallback。

## 4. 唯一目标生产链

```text
UserRequest
    → SourceEnvelope
    → MinimalIntentProposal
    → optional SemanticAudit for high-risk / multi-source / conflict (veto or clarify only)
    → TaskSpecAuthority
    → immutable TaskSpec
    → PerceptionCapture
    → CanonicalObservationBuilder
    → fresh canonical UnifiedObservation + SourceCoverage
    → pre-plan TaskSpec.success check
    → typed planning gate
        no trigger + feasible active step → reuse current TaskPlan
        direct deterministic milestone    → direct/rule PlanProposal<StepSpec>
        typed trigger                     → TaskPlanningObservationProjector
                                          → TaskPlanningRequest
                                          → TaskPlanner PlanProposal<StepSpec>
    → TaskPlanAuthority when a proposal exists
    → current TaskPlan<StepSpec> + TaskProgress
    → active StepSpec + ActiveStepScope
    → Runtime-owned full ActionChoiceCatalog + ChoiceBuildReport
    → 0 / 1 / N branch
        0 → deterministic typed failure owner
        1 → Runtime ActionSelection
        N → ChoicePresentationProjector
          → bounded ChoicePage
          → ChoicePlanningRequest
          → StepChoicePlanner sealed response
    → ActionSelectionValidator
    → fresh O1
    → ActionTransactionMaterializer builds full executable contract from O1
    → Task Authority ∩ capability intersection
    → freeze immutable ActionContract H
    → policy + exact approval of H when required
    → final snapshot/page/target/expiry Preflight for H
    → Executor serially executes H; approved_hash == executed_hash
    → TypedExecutionReceipt (transport truth)
    → fresh post-action UnifiedObservation
    → inline LoopEvaluationPhase
        → external EffectSettlement
        → Action Effect Evaluation
        → Step Completion Evaluation
        → actual OutputMaterialization from admitted evidence when required
        → triggered Task Completion Evaluation against TaskSpec.success + actual required OutputMaterialization
        → ObservationContinuation
    → RuntimeCommitter
    → continue / advance / replan / recover / clarify / block / fail / complete
```

生成 TaskPlan 前必须先验证任务是否已经满足。若 `TaskSpec.success` 在初始 observation 上成立且 satisfaction policy 允许，应无动作完成，不得制造 `implicit visible step`。

`SourceContextView` 不是上述 production authority chain 的新阶段。它只是由 accepted source bindings 单向投影给 TaskPlanner/OpenSemanticResolver/ClarificationComposer 的可选 side input；execution authority chain 不接收它。

## 5. 模块唯一职责

| 模块 | 输入 | 输出 | 明确禁止 |
|---|---|---|---|
| `SourceEnvelopeBuilder` | UserRequest refs + identity/version metadata | immutable SourceEnvelope | clause splitting、语义解释、graph 构建 |
| `SourceAnchorBuilder` | material field + authorized source | selective SourceAnchor | 为所有低风险句子强制建图 |
| `MaterialBindingPolicy` | effect kinds + typed values + source identities/anchors | field coverage / typed admission issues + binding digest | 模型调用、graph/store、capability/approval/grounding/contract 决策 |
| `MinimalIntentInterpreter` | UserRequest short-lived content + SourceEnvelope | anchor-bound MinimalIntentProposal | 提交 TaskSpec、生成步骤 |
| `SemanticAudit` | proposal + envelope/anchors | pass/veto/clarify | 添加效果、修改 success、提升授权 |
| `TaskSpecAuthority` | proposal + policy + sources | immutable TaskSpec / typed rejection | 推断步骤、静默补 submit/delete/payment |
| `SourceContextProjector` | accepted TaskSpec source bindings + SourceAnchors | bounded context_only SourceContextView | 创建 requirement、输出 unrestricted conversation、扩大 consumer allowlist |
| route-specific acquisition adapter / `PerceptionSession` | source capture policy | PerceptionCapture + adapter-owned truthful SourceCoverage + live surface/coordinate/capability refs | Builder 反推 complete；保存 credential/live handle |
| `CanonicalObservationBuilder` | PerceptionCapture | canonical UnifiedObservation | 读取 model presentation policy、修改 TaskSpec/progress |
| `ObservationStore` | canonical observation | immutable ObservationRef | 向 Planner 暴露 store handle |
| `TaskPlanner` | TaskPlanningRequest + optional SourceContextView | PlanProposal / TaskSpecGap | 修改 TaskSpec、创建 requirement、输出 concrete action |
| `TaskPlanAuthority` | proposal + typed TaskSpec requirements + observation identity | TaskPlan / reject / repair / clarify | 只检查 ID membership；忽略 action semantics 实际需要的 operation/resource/destination/value/function/usage |
| `TaskProgressService` | committed evaluation results | facts/bindings/durable evidence/step transition | 根据 receipt 直接完成 |
| `ActionChoiceBuilder` | task/plan/progress/active scope + canonical observation + capabilities/policy | full ActionChoiceCatalog + ChoiceBuildReport | 读取 presentation limit、调用 LLM、执行动作 |
| `ChoicePresentationProjector` | full Catalog + model policy | bounded ChoicePage | 改变 Catalog membership/digest |
| `StepChoicePlanner` | ChoicePlanningRequest | sealed selection/retrieval/control proposal | 发明动作、参数、locator 或选择未展示 ID |
| `ActionSelectionValidator` | proposal + current catalog/page identities | accepted ActionSelection / reject | 修复成另一个 choice |
| `ActionTransactionMaterializer` | selected choice + CatalogRef + committed fresh ObservationRef + read-only context/route/coordinate/capability indexes | full Draft / sealed result after independent gates | 旧合同 partial patch、打开 session、采集、审批、dispatch、写 state、自我授权 |
| `TaskAuthorityGate` | contract + TaskSpec | allow/deny | 用文本关键词代替 typed authorization |
| `CapabilityGate` | actual adapter support ∩ product policy ∩ user grants | allow/deny | 修改 TaskSpec；required list 反推 grant；未知 actual action support 时放行 |
| `ApprovalGate` | fresh SealedActionContract | one-shot exact request/grant/revocation | 提前批准 Draft/plan/action family；late/stale grant 复用 |
| `PreflightService` | contract + fresh observation | executable/stale | 自动重定位后继续旧合同 |
| optional hardening admission/permit | exact final contract + gate results | in-process dispatch token when demanded by fault model | 成为第五 authority；阻塞 MVP；假装提供跨进程或 malicious-insider guarantee |
| `RuntimeCommitter` serial lifecycle | typed contract/receipt/evaluation facts | committed transition | 重算 gate；吸收 session/coordinate/store I/O |
| `Executor` | final immutable ActionContract | TypedExecutionReceipt | 接收 Draft/choice；修改 approved payload；判断 external effect/step/task；uncertain blind retry |
| `LoopEvaluator` | task/step/contract/receipt/pre+post observation/recent outcomes/durable evidence | LoopEvaluation | 执行动作、写状态、提交 terminal |
| `EvidenceProvider` | typed predicate + source input | observed value + assurance/freshness metadata | 决定 task completion |
| `OpenSemanticResolver` | typed OpenSemanticCriterion + exact linked excerpts + current targets | typed resolution/evidence/gap | 修改 TaskSpec、读取 unrestricted source/page text、授予 effect |
| `ClarificationComposer` | typed ambiguity/gap + exact linked excerpts | user question | 修改 TaskSpec 或 action plan |
| `OutputMaterializer` | typed output values/artifacts + lineage/privacy policy | actual OutputMaterialization refs | OutputSpec metadata/Planner prose 冒充结果；默认复制 secret 进 trace |
| `TaskCompletionEvaluator` | TaskSpec.success + actual output refs + constraints + effect/collateral evidence | TaskCompletionEvaluation | 构造输出；根据 plan exhausted/reward/prose 自行通过、写 StateKernel |
| `EvidenceAdmissionPolicy` | CriterionPolicy + evidence metadata | admitted/rejected evidence | 重定义 criterion semantics |
| `DurableEvidenceStore` | durable records only | immutable durable evidence refs | 复制 current observation 或保存无界历史 |
| `PerceptionOwner` | post observation + next requirements | ObservationContinuation | 无理由重复 capture |
| `RecoveryPolicy` | typed failure + budgets | bounded command | 任意改 StateKernel |
| `Coordinator / RuntimeCommitter` | typed stage results | ordered calls / committed transitions and immutable checkpoint snapshot | 重解用户语义、实现领域算法；Committer 做 serialization/I/O/restore/session |
| checkpoint store / resume validator | immutable snapshot / checkpoint | atomic bytes / typed ResumeDirective or reconciliation routing | 打开 session、采集、approval、effect lookup、completion、commit |
| run manifest / offline replay | pinned code/policy/provider/schema/transform/acquisition/verifier/environment digests | immutable provenance / simulated outcomes | mismatch resume；replay miss 调 live tool/network/credential |

## 6. 迁移顺序与删除门

迁移采用 substitutive migration：每引入一个新的 canonical owner，必须在同一阶段定义旧 owner 的删除门；不接受长期 `new model + projector + checker + shadow + future cutover`。

### P0：同时封住执行环出口与入口的 correctness 缺口

| ID | 工作项 | 依赖 | 完成门 |
|---|---|---|---|
| `P0-A` | **MVP CLOSED：**保留 TaskCompletionEvaluator core 与 actual local `OutputMaterialization` closure；broader resolver/privacy breadth demand-gated | criterion/evidence compatibility foundation | latest report、receipt、plan exhausted、Planner Finish/prose/OutputSpec metadata 均不能单独完成；required output 必须存在实际 typed value/artifact ref 且 source-bind/redact；无 evidence 为 UNKNOWN |
| `P0-B` | **MVP FRESHNESS CLOSED：**保留 canonical builder core 与 adapter-owned SourceCoverage rule；broader adapter/context breadth demand-gated | 可与 P0-A 并行 | production 无 `from_planner_observation`；items/assertions/coverage 绑定一个 acquisition epoch，coverage 携带 adapter/scope/budget/model/version/threshold/count/exhaustion/termination/truncation/error；missing/error 为 UNKNOWN，Builder 不反推 complete |
| `P0-C` | 将 ActionChoiceBuilder 移出 GeneralistLMPlanner，先建 surface-neutral logical full Catalog 再建 ChoicePage；允许 eager/lazy/indexed membership | P0-B | presentation/materialization limits 与 backend preference 不进入 semantic membership；同一 canonical inputs 得到相同 count/membership/order/digest |
| `P0-E` | SourceEnvelope 成为 default source path；普通 intake 不建 clause/claim/obligation graph；material admission 使用 effect-specific typed binding coverage | 可与 P0-A 并行 | SourceLedger clause bound 不再阻塞普通任务；direct explicit 不要求 span；indirect source/page authority/缺失字段按 typed policy 拒绝或澄清；TaskSpec 使用 envelope ref + binding digest |
| `P0-D` | 写第 81 个目标、12-field state、artifact/label/context limit、conflict、multi-binding、raw-text execution read-set、TaskSpecGap、output closure 与 physical-minimality 回归红线 | P0-A/B/C/E 边界确定后 | presentation 不改变 Catalog；execution path 无 raw/SourceContextView；语义缺口不静默扩权；lazy/index layout 不改变 semantics |

### P1：直接 canonical TaskPlan，删除 legacy 往返

| ID | 工作项 | 完成门 |
|---|---|---|
| `P1-1` | TaskPlan 直接保存 typed StepSpec | 无默认 `StepSpec → SubgoalSpec → StepSpec` |
| `P1-2` | TaskPlanAuthority 单一 validation/admission/version owner | binder/projector 不再拥有 plan semantics |
| `P1-3` | obligation presence 不再控制 plan shape | 所有 TaskPlan 都读取 current canonical observation |
| `P1-4` | 新增 loop-native、cross-surface `LoopEvaluator` façade | DOM/visual/WoT/API/device providers 只产 typed evidence；action/step/task evaluation 使用不同 typed result；Evaluator 无状态写权 |
| `P1-5` | `ObservationContinuation` 四态复用协议 | REUSE/AUGMENT_TARGETED/RECAPTURE/WAIT_AND_RECAPTURE 由 Perception owner 决定 |
| `P1-6` | SourceLedger clause/span/coverage 能力迁入 optional `semantic_audit/` | 默认 compiler/prompt 不再要求 candidate_source_claims/candidate_obligations |
| `P1-7` | StepSpec 增加 canonical requirement refs；dependency 收敛到 typed value refs + StepSpec.depends_on | 无 TaskSpec claim/obligation dependency graph；TaskPlanAuthority 拒绝无 traceability step |

### P2：Criterion AST 与 typed evidence

| ID | 能力 | 权限限制 |
|---|---|---|
| `P2-1` | 封闭 Value/Predicate/Composite/OpenSemantic AST；冻结 mandatory mechanical operator baseline | 不按 DOM/API/Visual source 扩张 criterion class；registered 但未支持 operator 返回 UNSUPPORTED |
| `P2-2` | 最小 CriterionPolicy：2 satisfaction × 3 validity × 3 assurance | 不以默认 DOM 覆盖 policy；model evidence 非 authoritative |
| `P2-3` | CausalEffectEvidence + bounded RecentActionOutcomeIndex | pre-existing state 不冒充 ACTION_CAUSED |
| `P2-4` | CurrentObservation / RecentActionOutcome / DurableEvidenceStore 三层 evidence location | 只有 durable evidence 跨 epoch |
| `P2-5` | Mechanical providers 内化：DOM/AX、visual/SVG、WoT/API/device、artifact/external | provider 只提取事实与 metadata，不拥有 completion |
| `P2-6` | ModelVerifier / HumanProvider 后置扩展 | 只产 evidence；high-risk external effect 不得 model-only completion |
| `P2-7` | OpenSemanticResolver 收窄为 typed criterion + exact anchor excerpt resolver | 无 unrestricted conversation/page authority；失败返回 gap/clarification |

### P3：TaskSpec v2 稳定授权合同

| ID | 工作项 | 完成门 |
|---|---|---|
| `P3-1` | 冻结 TaskSpec v2 schema 与 TaskSpecAuthority | 只保存 source_envelope_ref/source_binding_digest；Planner 不能修改 accepted meaning |
| `P3-2` | SemanticAudit 保持 risk-triggered veto/clarify-only | 不增加用户效果、修改 success 或授权 |
| `P3-3` | Risk-proportionate MaterialBinding + selective SourceAnchor policy | direct explicit 无 span；indirect unstructured exact excerpt；typed external version/field；按 effect field groups 完整覆盖 |
| `P3-4` | Canonical TaskRequirement identity 与 requirement-ref containers | material semantics 单一 typed payload；objective 不可补字段 |
| `P3-5` | SourceContextProjector + Task Meaning Write Barrier | 只读 context_only allowlist；只有 TaskSpecAuthority 写 accepted meaning |
| `P3-6` | Stable required OutputSpec schema | output ID、materialization criterion、source-binding policy 完整 |

### P4：Observation-grounded rolling planning 与严格 StepChoice port

| ID | 工作项 | 完成门 |
|---|---|---|
| `P4-1` | `TaskPlanFlow` 与 `StepChoiceFlow` 物理拆分 | 两种 request/response/authority 不混用 |
| `P4-2` | strict planner 改为 `select(ChoicePlanningRequest)` | 无 BrowserSnapshot/ActionChoiceBuilder/StateKernel 依赖 |
| `P4-3` | logical full Catalog + small ChoicePage；deterministic narrowing 稳定后再依次加入 paging、typed retrieval | 未展示 ID 被拒；effectful 截断页遵守唯一授权规则；cursor/filter 不改变 membership |
| `P4-4` | request serializer 纯化 | 不重建 task/step/progress/observation authority |
| `P4-5` | ChoicePresentation semantic contract | target/state/requirement/effect/conflict/risk/reason 完整；无 binding/hidden ID/raw text |
| `P4-6` | typed TaskPlanningGate + direct/reuse fast path | 只有明确 planning/replanning trigger 调用 TaskPlanner；feasible active step 不重复生成 DAG |
| `P4-7` | **SUPPORTING FOUNDATION：**TaskPlanAuthority semantics-required guards | 当前 MVP 只闭合 read→mutation laundering 等已准入最小 guard；exhaustive destination/function/usage policy 不是五项 P4 invariant，按真实场景扩展 |

### P4-G：Concrete Action Authority foundation

P4-G 保留 typed scope/signature/proof 中直接服务 GUI contract 的部分；它不再把生产级
transaction isolation 当作 P5 前置。`P4-G4` 的最小目标由 P4-C3 的 final-contract hash
不变量收口，`P4-G5` 只保留 uncertain-effect no-blind-retry，`P4-G6` 只保留 default core
cutover。其余并发/manifest/adversarial 扩展进入 future hardening。

| ID | 工作项 | 完成门 |
|---|---|---|
| `P4-G1` (RETAINED; MVP EVIDENCE PASSED) | 在 focused `effect_authority_contracts.py` 定义互不混用的 `EffectAuthorizationScope`、`RuntimeEffectSignature`、ResourceScopeRef、named ParameterAuthorization、Externality/Reversibility 与带 evaluator-policy version 的 tri-state ActionAuthorityProof；TaskSpecAuthority 只准入前者 | focused mismatch/parameter/type probes 通过；不新增 effect graph/TaskType；不保留 `operation_class + label + scalar set` fallback |
| `P4-G2` (RETAINED; MVP EVIDENCE PASSED) | adapter assertions 经 pure Runtime classifier/risk policy 汇入 concrete signature | unknown/material conflict/coverage insufficient 为 UNPROVEN；Text/VLM 只能 raise risk/trigger observe；broader coverage 作为 future hardening |
| `P4-G3` (RETAINED; MVP EVIDENCE PASSED) | ActionChoiceBuilder 以 typed subsumption 建 Catalog，保留 ALLOW proof 并区分 DENY/UNPROVEN | mismatch、named parameter swap、label-only identity、unauthorized disclosure 与 UNKNOWN effect probes 通过 |
| `P4-G4` (MVP CLOSED) | final route/full contract/approval binding | 由 `P4-C3` 保证 materialize-first 与 approved hash == executed hash |
| `P4-G5` (MVP CLOSED) | dispatch/effect closure | 由 `P4-C4` 保证 typed receipt/effect separation 与 uncertain-effect no-blind-retry；transaction isolation/collateral 后置 |
| `P4-G6` (MVP CLOSED) | canonical cutover | 由 `P4-C5` 保证默认 core 无 fallback；release attestation 后置 |

### P4-C：P4-minimum closure

| ID | 工作项 | 完成门 / 删除门 |
|---|---|---|
| `P4-C0` | zero-call containment | stale snapshot/page/target、missing dependency、uncommitted/invalid contract 皆 fail closed，且 `executor_calls == 0`；benchmark safety ablation 与产品 composition 隔离 |
| `P4-C1` | verifier-backed completion | receipt/ACK/plan/prose 不能产生 DONE；required artifact/value 必须实际存在、可解析且由 verifier evidence 支撑。operation/destination/function/usage 只在 action semantics 需要时 mandatory |
| `P4-C2` | **FUTURE HARDENING — NON-BLOCKING** | tenant/profile live proof、完整 surface/coordinate currentness、provider/schema manifest 与多维 provenance 按 benchmark/部署需求启用，不阻塞 P5 |
| `P4-C3` | exact finalized contract | materialize/encode 完整 executable contract 后再执行 policy/approval；Executor 只接收该 immutable contract，并验证 `approved_contract_hash == executed_contract_hash`；禁止 approval 后追加参数与 partial patch |
| `P4-C4` | serial uncertain-effect safety | 当前可信进程内保持 one coordinator/one session/one active contract 串行执行；typed receipt 不等于 effect；uncertain effect 先 inspect/block/handoff，不盲重试。revocation linearizability、clone-resistant/global permit registry、worker fencing 与 attempt-bound collateral 后置 |
| `P4-C5` | core cutover and regression gate | default product composition 只调用 finalized-contract 主线并删除 core fallback；focused checks、full `pytest`、Ruff、mypy 与 core benchmark 通过。immutable revision + AgentDojo/WASP/OSWorld multi-suite attestation 属于 release/论文复现，不阻塞 P5 |

P4-minimum 的状态仍需区分 design、implementation、default route 与 focused negative
evidence，但只检查当前 threat model 的适用维度。Git immutable revision、并发攻击 probe 与
外部多套件是 promotion/release evidence，不是日常 `CLOSED` 或 P5 admission 的必要条件。
Core benchmark 是五项 invariant 与 default core cutover 的整体验收证据，不是额外语义门；
未通过时不得宣布闭合。当前 fresh evidence 已通过，因此 `P4 CLOSED (MVP scope)`，
P5 准入解除但尚未开始。

当前 closure evidence 还包含 stable Task API 三场景真实执行、fixture v2.1.0 held-out
pricing semantic ID、export typed OutputSpec/authoritative final evidence/file SHA/
`artifact_ref`、BenchmarkReport required-variant/denominator/expected-trace fail-closed，以及
approval 展示 final `contract.parameters`。这些证据不扩张为 exhaustive TaskPlan 字段、
所有 adapter coverage、tenant/permit 或 release-attestation closure claim；当前数值仍只由
`implementation-status.md` 维护。

### P4-R0：Optional narrow durable dispatch journal

仅当产品明确声明“process/hard crash 后仍能恢复 dispatch boundary”时实施。完成门包括 atomic/torn-write/tamper detection、state-version CAS、run/surface fencing、single-use permit recovery、generic exception 默认为 SENT_UNKNOWN，以及不保存 secret/live handle。若不实施，产品能力声明必须限定为 cooperative interruption 与进程内 lifecycle；不得让 P5 checkpoint 暗示 hard-crash guarantee。

### P5：Bounded state、interruption recovery 与 legacy deletion

进入条件：权威架构 §0.0 的五项 `P4-MVP` invariant 通过，并由 focused/full/static checks
与 core benchmark 证明它们在 default route 上闭合；benchmark 是证据而不是第六项。
`P4-C2`、production-grade C4 hardening、P4-R0 与 immutable multi-suite release
attestation 均不默认阻塞 P5；只有 P5 明确新增相应产品 claim 时才成为该 claim 的局部门禁。

| ID | 工作项 | 完成门 |
|---|---|---|
| `P5-1` | 轻量 RunLedger 物理承载 Fact/Binding/RecentActionOutcome/DurableEvidence namespaces，替代 completed-subgoal/evidence-graph carry-forward | namespace 生命周期保持独立；replan 不要求复用旧 step identity；current evidence 不持久化 |
| `P5-2` | ObservationStore + immutable epoch/index + current observation/catalog refs | StateKernel 保存 identity，不承载 presentation 内容；consumer 不复制完整 canonical graph |
| `P5-R1` | typed `RunCheckpoint` + focused checkpoint-store protocol | 只保存 TaskSpec/plan/progress refs/digests、`last_committed_observation_ref`（historical）、contract ref/hash、approval request ref/status、attempt/dispatch/effect identities、budgets、trace head、manifest digest；不保存完整 executable contract/token/credential/live handle/DOM/screenshot/selector/coordinate；物理 backend 不在此阶段预先冻结 |
| `P5-R2` | RuntimeCommitter-produced immutable committed snapshot + focused store persistence | waiting approval/clarification、effectful pre-dispatch、receipt/uncertain outcome、post-evaluation 与 terminal 均在 typed commit 后落点；Committer 不吸收 serialization/file I/O/restore policy，Coordinator 不成为第二 snapshot writer |
| `P5-R3` | pure fresh-session restore validation + effect-reconciliation routing | `runtime_resume.py` 只校验 checkpoint/authenticity/lineage/manifest/lifecycle 并输出 directive；session owner 创建新 generation，Perception 提交 fresh O1，effect owner 执行 lookup；旧 observation/catalog/contract/approval/permit 全失效；resume validator 不打开 session、采集、审批、lookup、completion 或 commit |
| `P5-R4` | separate cooperative interruption/cancellation + public lifecycle semantics | `INTERRUPT_REQUESTED → SUSPENDED` 可恢复，`CANCEL_REQUESTED → CANCELLED` 只在 safe stop 且无 unresolved effect 后终止；dispatch 中请求进入 uncertain-effect reconciliation，不把 service status 当作 `NOT_DISPATCHED` 证明 |
| `P5-3` | 删除已迁移 consumer 的 external/public compatibility adapters | internal legacy owner 不得拖入 P5；canonical production composition 无 parallel owner |
| `P5-4` | 最终 containment pass | Coordinator/Committer/Execution/BrowserGym/planner/builder 按责任拆分；不为 line count 单独造测试或服务 |

P5-R 不新增 completion、approval、execution 或 batch authority。Checkpoint 只是最后一次 committed typed state 的恢复输入，`last_committed_observation_ref` 也不是恢复后的 current authority。same-process exact approval continuation 只是受 lease/session policy 约束的优化；process restart 必须新 session generation、fresh O1、fresh materialization 与按需重新审批。物理实现保持模块化单体，不拆恢复服务、多 namespace 数据库、unbounded replay 或分布式 lease；当前不新增 BatchActionContract、batch cursor/rollback/resume。

### Deferred：核心收口后再做

Action Segment/Batch、surface expansion、跨设备 Workflow Harness、高级概率归因、并行多目标合并、通用 skill mining 与 full EvidenceGraph/EvidenceIndex platform 全部后置；它们不得进入同步 completion authority。只有并行多 Agent、异步 evidence、法规 lineage、复杂 invalidation 或跨任务证据复用出现真实需求后，才允许提升 evidence architecture。

## 7. 明确非目标

- 不让 TaskSpec 保存 selector、coordinate、backend、当前页面按钮或执行步骤。
- 不让 Planner 创建 TaskSpec revision、capability grant、approval token、ActionContract 或 TaskCompleted。
- 不用更复杂的 obligation role enum 继续维护同一张混合图。
- 不用“更保真的 converter”延长 legacy Step/Subgoal 往返。
- 不用 benchmark task ID、URL、selector、seed 或模板特例修复架构。
- 不把 SourceEnvelope、SemanticAudit、DurableEvidenceStore 或 TraceDag 变成新的 planning graph。
- 不把 ModelVerifier、reward、receipt 或 human-friendly explanation 直接升级为完成权威。
- 不为每种语义组合创建 `TaskType` 枚举。
- 不把所有 Runtime 阶段压进 Coordinator 或一个大 `Agent` 类。
- 不用提高 top-k、修改模型排序或扩充 context 代替 authority 修正。
- 不把 BrowserSnapshot、UnifiedObservation 与 PlannerObservationView 维护为三套事实权威。
- 不声称有限 acquisition 下的 canonical observation 是外部世界全集。
- 不允许 model presentation omission、排序或猜测的 hidden ID 改变 Runtime Catalog。
- 不在默认 intake 对所有句子强制 clause/claim/obligation coverage。
- 不让 TaskSpec 复制 raw request/source claims；只绑定 SourceEnvelope identity 与 material anchors digest。
- 不采用 TaskSpec 后全面禁读任何 source excerpt 的 strict raw-text firewall；采用 bounded context-only rereading 与 Task Meaning Write Barrier。
- 不允许 action construction、contract/gates、execution、evaluation、completion、commit 读取 raw request 或 SourceContextView。
- 不允许 allowed effects、constraints、success 与 outputs 各自维护同一 material requirement 的 free-form copy。
- 不允许 Planner prose 替代 required structured output materialization。
- 不默认建设独立 verifier service、VerifierPlanner、全量 EvidenceGraph 或无界历史 EvidenceIndex。
- 不让 source-specific provider 类型扩张为 source-specific Criterion 类型组合。
- 不把 full Catalog 解释为必须 eager materialize 全部 choice；logical membership 可 lazy/indexed/query-backed。
- 不在各阶段复制 canonical observation 全图；使用 immutable epoch ref/read-only index。
- 不把每个 authority、gate 或 ledger namespace 默认拆成 service/process/database/queue/model call。
- 不在无 typed trigger 时每轮调用 TaskPlanner。
- 不让 risk profile 绕过任何任务要求的安全、freshness、completion 或 single-writer boundary。
- 不把裸 Bash/任意 CLI string 作为普通 GUI action；命令执行必须是独立 typed、allowlisted capability。
- 不建设 general taint platform、theorem prover、第二 intent graph、微服务恢复平台、分布式 lease 或 per-namespace database。
- 不让 provider safety/model refusal/prompt-injection detector/benchmark reward 代替本地 authority。
- 不让 replay miss 回退 live driver/network/credential，也不让 checkpoint 暗示 global exactly-once。
- 不在 P5 顺手引入 effectful batch、batch approval/cursor/rollback/resume；当前生产只 dispatch primitive transaction。
- 不声称修订架构可以消除全部漏洞；无法证明的 effect/coverage/context 保持 UNKNOWN 并 block/handoff。

## 8. 关键场景验收

### 8.1 关闭弹窗

```text
TaskSpec.success: dialog is_absent
Step.preconditions: dialog is_visible AND close_control is_available
Step.completion: dialog is_absent
```

按钮存在不能完成 step 或 task；只有 fresh evidence 证明 dialog absent 才能提交。

### 8.2 注册表单

```text
Step 1: registration form is valid and complete
    action loop: type name → verify; type email → verify; type password → verify
Step 2: registration submission is confirmed
```

每个字段不是默认 task-level step；submit 前可形成独立 risk/approval boundary。

### 8.3 组合候选条件

```text
Exists candidate in candidates:
    starts_with(candidate.name, "An")
    AND ends_with(candidate.name, "ica")

Task success:
    cart contains_entity candidate
```

Planner 根据 observation 决定搜索、翻页、打开详情或直接加入购物车；intake 不预先决定步骤。

### 8.4 初始状态已满足

TaskSpec.success 在初始 fresh observation 上成立且 policy 为 `current_state` 时，Runtime 无动作完成；不得生成 `implicit visible step`。

### 8.5 Plan 耗尽但 Task 未完成

所有 Step 完成但 TaskSpec.success 为 failed/inconclusive 时，状态只能进入 replan/recover/clarify/block/fail，不能进入 completed。

### 8.6 高风险动作审批

approval 必须在 committed fresh O1 的完整 `SealedActionContract` 之后请求，并绑定 contract hash、run/session generation、context/surface/transform/capability/proof 与 page/document revision。任何 re-ground、参数、snapshot、account/session/coordinate/schema 或 contract rebuild 变化都要求重新审批；late grant tombstone。

### 8.7 第 81 个唯一目标与 presentation invariance

唯一合法目标位于旧 top-80 外时仍必须进入 full Catalog。对相同 task/plan/step/progress/canonical observation/capabilities/policy，改变 affordance count、state field、artifact、label 或 context compaction limits 不得改变 `catalog_digest`。

### 8.8 截断 ChoicePage、高风险与多来源冲突

- full Catalog 中存在但当前页未展示的 ID 必须以 `UNPRESENTED_CHOICE_ID` 拒绝；
- effectful/high-risk page 截断且无 deterministic unique authorization match 时必须继续检索或澄清；
- target identity 或 required state material-conflicted 时不得建立/自动选择 executable choice；
- acquisition coverage 不足走 active perception，不能伪装成 target absent 或 model grounding ambiguity。

### 8.9 SourceEnvelope 与选择性审计

- 普通低风险请求只构建 SourceEnvelope，不能因 33 个句子或没有 claim/obligation graph 而 fail；
- direct user explicit material value 可用 typed binding 且不要求 span；间接非结构化值必须 exact excerpt，typed external 值必须绑定 versioned field identity；
- SEND/PAYMENT/DELETE/SHARE 分别校验自身必需字段组，一个无关 FILE/AMOUNT anchor 不能替代 recipient/payee/account；
- high-risk/multi-source/conflict 触发 SemanticAudit，audit 只能 veto/clarify；
- 页面 observation 不能被提升为用户授权 source；
- TaskSpec 只保存 `source_envelope_ref` 与 `source_binding_digest`。

### 8.10 Loop-native evaluation 与完成权威

- “确保设置 enabled”可由初始 observation 的 `STATE_HOLDS` 无动作完成；
- “把设置从 disabled 切到 enabled”必须有 contract-bound `ACTION_CAUSED`；
- send/delete/payment 等必须 `FINAL_RECHECK + AUTHORITATIVE`，不能 model-only 或 toast-only 完成；
- verification disabled、无 provider/operator、无 evidence 分别产生显式 diagnostic、UNSUPPORTED 或 UNKNOWN，绝不能 PASSED；
- fresh post-action observation 默认可复用，Perception owner 可选择 targeted augmentation、recapture 或 wait-and-recapture。

### 8.11 Semantic context、requirement traceability 与 output closure

- “更自然但不要太随意”等 OpenSemanticCriterion 可读取精确绑定 excerpt，但 resolver 不能添加新 requirement/effect；
- Task Planner 可用 bounded SourceContextView 选择里程碑，但每个 Step 必须引用已有 requirement IDs；
- 原文暗示 X、TaskSpec 未准入 X 时，输出 TaskSpecGap/clarification，不把 X 写进 plan；
- Step Choice Planner 只比较当前 ChoicePresentation 的 target/state/requirement/effect/conflict/risk/reason；
- success state 已满足但要求返回的姓名/链接尚未 structured materialize/source-bind 时，不得 TaskCompleted。

## 9. 架构验收不变量

1. TaskSpec 只能由 TaskSpecAuthority 创建 revision。
2. Planner 只读 admitted TaskSpec semantics；可选 SourceContextView 明确 `context_only`，不得返回 TaskSpec patch 或新 requirement。
3. TaskPlan 的结构必须可随 observation 替换，且不改变 TaskSpec authority。
4. accepted TaskPlan 直接保存完整 StepSpec，无默认 SubgoalSpec round-trip。
5. Step completion criterion 不自动成为 Task completion criterion。
6. `is_available`、`visible` 等 predicate 的角色由容器决定。
7. Runtime full ActionChoiceCatalog 绑定 task/plan revision、state version、canonical observation epoch 与 active step。
8. Planner selection 必须属于当前 Catalog 且属于当前展示的 ChoicePage；未展示 choice ID 即使存在于 Catalog 也必须拒绝。
9. 所有 Step 必须追溯到 TaskSpec refs，并通过 operation/resource/destination/value/function/usage typed semantic subsumption；效果动作还必须追溯到 allowed-effect reference。
10. Capability ceiling 不等于 capability grant；approval 不等于 capability。
11. Approval 只在 committed fresh O1 的完整 SealedActionContract 后请求，绑定 context/surface/transform/capability/proof，且 one-shot；late/stale grant tombstone。
12. Preflight 失败不得 patch/re定位旧合同且 Executor 调用数为零；policy/approval 必须在 final materialization 后检查同一 immutable contract，执行 hash 与批准 hash 相同。
13. typed transport SENT 不等于 effect OCCURRED；unknown/exception 不得变 COMPLETE。
14. Effect observed 不等于 step complete。
15. Step/plan complete 不等于 task complete。
16. TaskCompleted 只能来自完整 TaskSpec.success + actual required OutputMaterialization + verifier evidence + RuntimeCommitter；receipt 不能替代。collateral 仅在已启用的 risk/release profile 中适用。
17. 无合格 evidence 时状态为 `UNKNOWN`、`UNSUPPORTED` 或其他 typed failure，不得乐观成功。
18. post-action observation 应在 freshness 允许时复用于 effect、step、task 与下一轮 planning。
19. Recovery 只能由 typed owner 在预算内产生 command；Coordinator 不猜测命令。
20. Trace、Artifact、Benchmark、Evolution 不得拥有同步完成权。

### 9.1 Observation / Choice P0 不变量

| ID | 不变量 |
|---|---|
| `OBS-01` | Canonical `UnifiedObservation` 是唯一 current semantic observation authority。 |
| `OBS-02` | `TaskPlanningObservationView`、`PlannerObservationView` 与 `ChoicePage` 只是 presentation projection。 |
| `OBS-03` | `ActionChoiceBuilder` 不得 import 或消费任何 planner observation/request view。 |
| `OBS-04` | `unified_observation.py` 不得 import `planning_request.py`。 |
| `OBS-05` | Strict Generalist Step Planner 不得构建 `ActionChoiceSet`/`ActionChoiceCatalog`。 |
| `OBS-06` | 改变 model presentation policy 不得改变 `ActionChoiceCatalog.catalog_digest`。 |
| `OBS-07` | 每个 ActionChoice 必须绑定同一明确 canonical observation epoch。 |
| `OBS-08` | 每个 ActionContract 必须绑定 current Catalog 中的 choice 与相同 pre-action observation epoch。 |
| `OBS-09` | material conflict 必须显式保留；unknown/inconclusive 不等于 no conflict。 |
| `OBS-10` | SourceCoverage 由 acquisition adapter 对明确 scope/budget/model/version/threshold/error 产生；missing/error/truncation 不得伪装成 complete 或 target absence。 |
| `OBS-11` | truncated ChoicePage 必须保存 total/included count、policy 与 continuation metadata。 |
| `OBS-12` | effectful selection 来自 incomplete ChoicePage 时，必须有 deterministic unique authorization match，或继续检索/澄清。 |
| `OBS-13` | 可复用的 fresh post-action observation 不得立即重复 capture。 |
| `OBS-14` | Perception owner 必须显式选择 REUSE、AUGMENT_TARGETED、RECAPTURE 或 WAIT_AND_RECAPTURE。 |

静态依赖门：

```text
action_choice.py       -X-> planning_request.py
unified_observation.py -X-> planning_request.py
strict generalist planner -X-> ActionChoiceBuilder / BrowserSnapshot / StateKernel
Runtime candidate construction -X-> PlanningRequestBuilder
```

行为红线必须覆盖：第 81 个唯一目标、state 第 13 个必要字段、artifact 数量、label 长度、context compaction、material conflict、multi-binding、未展示 choice 注入以及 effectful truncated page。

### 9.2 SourceEnvelope / SemanticAudit 不变量

| ID | 不变量 |
|---|---|
| `SOU-01` | SourceEnvelope 轻量、immutable、始终存在，拥有 source identity/version，不拥有语义。 |
| `SOU-02` | 默认 SourceEnvelopeBuilder 不做 clause splitting、claim graph、coverage graph 或 obligation graph。 |
| `SOU-03` | material authorization 使用 typed MaterialBinding；direct user explicit value 不要求字符级 span。 |
| `SOU-04` | indirect unstructured value 使用 field-matched exact excerpt；typed external ingress 使用 versioned field identity。 |
| `SOU-05` | SemanticAudit 只由 high-risk/multi-source/conflict/policy trigger 启用。 |
| `SOU-06` | SemanticAudit 只能 pass/veto/clarify，不能添加 effect、修改 success 或授予 capability。 |
| `SOU-07` | TaskSpec 只绑定 source_envelope_ref 与 source_binding_digest，不复制 raw source/claim graph。 |
| `SOU-08` | MinimalIntentProposal 与 TaskSpec 默认不存在 candidate_source_claims/candidate_obligations/source_claims/obligations。 |
| `SOU-09` | Runtime observation/page content 不得被提升为用户 authority source。 |
| `SOU-10` | Trace 默认只记录 source hash/length/ref，不复制 raw request content。 |
| `SOU-11` | 旧 SourceLedger 的 clause/span/coverage 能力只可作为 optional SemanticAudit implementation。 |
| `SOU-12` | TaskPlan 是 observation-grounded milestone graph，不是 intake obligation graph。 |

### 9.2.1 MaterialBinding 不变量

| ID | 不变量 |
|---|---|
| `MAT-01` | 每个 external/irreversible effect 有稳定 ID、风险一致的 operation/effect kind 和完整 required material field groups；kind 不得降级 operation class。 |
| `MAT-02` | direct user explicit value 在 request 中确定性匹配即可，不因缺少 exact span 失败。 |
| `MAT-03` | 间接非结构化 material value 使用 field-matched exact excerpt；typed external value 使用 versioned source/field identity。 |
| `MAT-04` | page/screen/current observation 不得创建 material authorization。 |
| `MAT-05` | SourceAnchor 只证明 provenance，不授予 capability、approval、grounding、contract 或 completion。 |
| `MAT-06` | Binding 按 effect + field 隔离；一个任意/无关 anchor 不能满足其他字段或 effect。 |
| `MAT-07` | completeness 归 MaterialBindingPolicy/TaskSpecAuthority；SemanticAudit 只处理冲突、异常解释和风险范围。 |

### 9.3 Loop-native Verification 不变量

| ID | 不变量 |
|---|---|
| `VER-01` | Receipt success 永不直接完成 criterion。 |
| `VER-02` | 没有 explicit criterion coverage 的 passed report 永不推进 progress。 |
| `VER-03` | TaskCompleted 只来自 TaskSpec.success root evaluation。 |
| `VER-04` | Planner FinishProposal 只转换为 FinalVerificationRequested。 |
| `VER-05` | STATE_HOLDS 可以由 current-state precheck 满足。 |
| `VER-06` | ACTION_CAUSED 必须有 contract-bound ActionOutcome evidence。 |
| `VER-07` | 只有 durable evidence 跨 observation epoch 持久化。 |
| `VER-08` | Historical evidence 只按其 validity mode 接受。 |
| `VER-09` | External transaction completion 必须通过 authoritative final recheck。 |
| `VER-10` | ModelVerifier 只能提供 evidence。 |
| `VER-11` | High-risk external effects 不能由 model-only evidence 完成。 |
| `VER-12` | No evidence means UNKNOWN；verification disabled 也不得 PASSED。 |
| `VER-13` | Conflict 保持 CONFLICT，不得退化为空 evidence set。 |
| `VER-14` | Plan exhaustion 不等于 task completion。 |
| `REC-01` | Failure owner 必须由 typed evaluation cause 决定，不使用 generic error strings。 |

### 9.4 Semantic Authority / Contract Closure 不变量

| ID | 不变量 |
|---|---|
| `NLI-01` | TaskSpecAuthority 是唯一可 admit/revise meaning、authorization、constraints、forbidden effects 与 success semantics 的 owner。 |
| `NLI-02` | Admission 后 raw/anchored source text 只能作为 read-only、explicit `context_only` view。 |
| `NLI-03` | 使用 source assistance 的 plan/resolution/clarification 必须引用已有 canonical requirement/criterion/effect/anchor IDs。 |
| `NLI-04` | 缺失语义返回 TaskSpecGap/ClarificationRequired，不得 patch/reinterpret TaskSpec。 |
| `NLI-05` | Action-space、binding、gates、execution、evaluation 与 completion 不读取 raw user language。 |
| `NLI-06` | OpenSemanticResolver 只读取 typed criterion 与 exact linked SourceAnchor excerpts。 |
| `NLI-07` | Observation、website/tool/email/PDF/screen content 不创建用户授权。 |
| `NLI-08` | Bounded repair 在 admission 前替换 untrusted proposal，不创建第二 accepted meaning。 |
| `REQ-01` | 每个 material requirement 只有一个 stable ID 与 typed semantic payload。 |
| `REQ-02` | Authorization/constraint/success/output containers 引用 canonical IDs，不独立重述。 |
| `REQ-03` | objective 是 explanatory summary，不可恢复 typed requirement。 |
| `REQ-04` | StepSpec 有 requirement_refs；effectful Step 另有 effect_authorization_refs。 |
| `REQ-05` | TaskPlanAuthority 不只验证 trace ID；它对 operation、subject/resource、destination、material named values、element function、task usage 与 source→sink flow 做 typed semantic subsumption，无法证明则拒绝。 |
| `DEP-01` | Semantic value dependency 只用 typed input/binding/value refs。 |
| `DEP-02` | Execution ordering 只用 StepSpec.depends_on。 |
| `DEP-03` | Accepted TaskSpec 无 claim/obligation dependency graph。 |
| `CHOICE-13` | Presented choice 包含 target/state/requirement/effect/conflict/risk/reason，且无 binding/hidden ID。 |
| `OUT-01` | Required OutputSpec 有 stable ID 与 typed materialization criterion。 |
| `OUT-02` | TaskCompleted 要求实际 OutputMaterialization value/artifact refs、schema/content digest、lineage 与 policy-required source binding；metadata 不能 materialize 自己。 |
| `OUT-03` | Planner prose 不替代 structured output；trace projection 必须执行 redaction/access/retention。 |

### 9.5 Physical Minimality 不变量

| ID | 不变量 |
|---|---|
| `CAT-PHY-01` | full Catalog 是稳定 logical membership；eager/lazy/indexed/query-backed 实现对相同 canonical inputs 产生相同 count/order/digest/rejection semantics。 |
| `OBS-PHY-01` | canonical observation 由 immutable epoch ref/read-only indexes 暴露；布局变化不改变 target/binding/coverage/conflict/digest。 |
| `AUTH-PHY-01` | logical authority 不要求独立部署单元；in-process composition 必须保留各 gate 的 typed result、deny 与 write boundary。 |
| `CRIT-PHY-01` | operator vocabulary 与 provider coverage 分离；未支持 operator 返回 UNSUPPORTED，不得 description/model fallback 自动通过。 |
| `PLAN-PHY-01` | TaskPlanner 只响应 typed planning/replanning trigger；active step 仍可行时复用 current plan。 |
| `PROFILE-01` | risk-derived profile 只控制 optional machinery，不关闭任务要求的 authority/safety/freshness/output/single-writer gate。 |

### 9.6 Cross-Surface 不变量

| ID | 不变量 |
|---|---|
| `SURFACE-01` | DOM、AX、Visual、SVG、WoT、API 与 Device 共享同一 TaskSpec、current TaskPlan、logical Catalog、ActionContract admission 与 LoopEvaluator。 |
| `SURFACE-02` | 一个 semantic CanonicalTarget 保留全部 current bindings、assertions、coverage 与 conflicts；不得选择 representative surface 或静默覆盖冲突。 |
| `SURFACE-03` | Planner selects the semantic action；`ActionTransactionMaterializer` 的 route owner selects the current backend/binding，并将 route 绑定 current observation、context/transform、evidence requirement、capability、risk 与 policy。 |

### 9.7 Concrete Effect Authority / High-risk 不变量

| ID | 不变量 |
|---|---|
| `AUTHZ-01` | effectful requirement 的唯一 typed payload 包含 parameterized `EffectAuthorizationScope`；TaskSpec 不保存 `RuntimeEffectSignature`，objective/label/keyword 不恢复 operation/scope。 |
| `AUTHZ-02` | target/destination 匹配 canonical source-bound resource scope，display label 不能单独授权。 |
| `AUTHZ-03` | parameters 按 named slot 绑定 InputRef/BindingRef/predicate；scalar value-set inclusion 不构成授权。 |
| `AUTHZ-04` | Runtime 从 actual current candidate/backend/binding/source assertions 构造 `RuntimeEffectSignature`，并按 Harness policy 独立推导 risk/assurance；Planner 不声明 effect/risk authority。 |
| `AUTHZ-05` | unknown operation/effect/externality/reversibility/risk、assurance 不足、material conflict/coverage gap 为 UNPROVEN，不默认 LOW；Text/VLM 只能升风险或触发观察/澄清。 |
| `AUTHZ-06` | Catalog 只接纳 ALLOW proof，并将 DENY/UNPROVEN 送入不同 typed recovery。 |
| `AUTHZ-07` | enabling action 仅允许 requirement-bound INTERACTION_ONLY/local reversible draft；observe/focus/hover/scroll/non-commit UI/allowed-domain navigation/wait 仍需 no external effect/data disclosure/domain expansion proof。 |
| `AUTHZ-08` | Contract hash 绑定 scope、route-specific signature、proof/evaluator-policy version、binding、named parameters、externality/reversibility、risk/assurance/epoch、RouteBinding 与 application-payload digest；seal/Task Gate 以 pinned schema/encoder/policy 重算，mismatch 为 DENY。 |
| `AUTHZ-09` | Task Gate 从 actual bound transaction 独立重建 proof，不复算复制字段。 |
| `AUTHZ-10` | Approval/capability 不能扩大 TaskSpec 或把 UNPROVEN 升为 ALLOW。 |
| `HRA-01` | 高风险 effect 进入 execute 前同时满足 material fields、source assurance、capability、exact approval 与 fresh preflight。 |
| `HRA-02` | uncertain external effect 不盲重试。 |
| `HRA-03` | 高风险完成需要 contract-bound causality 与 policy-required authoritative FINAL_RECHECK。 |

### 9.8 Interruption recovery 不变量

| ID | 不变量 |
|---|---|
| `RESUME-01` | RunCheckpoint 只记录 RuntimeCommitter 已提交的 TaskSpec/plan/progress refs/digests、`last_committed_observation_ref`、contract ref/hash、approval request ref/status、attempt/dispatch/effect identities、budgets、trace head 与 manifest digest；它不是观察、授权、审批或完成权威。 |
| `RESUME-02` | process restore 必须创建新 session generation、取得新 lease 并提交 fresh canonical observation；旧 observation/catalog/contract/approval/permit、DOM/page/backend handle、selector/coordinate 不可持久化或复活。 |
| `RESUME-03` | recovery names 是 canonical transport/effect pair 的只读投影：`NOT_DISPATCHED` 只来自 proven `NOT_SENT`；`MAY_HAVE_OCCURRED` 覆盖 `SENT_UNKNOWN`、missing receipt 或 `SENT + STILL_UNCERTAIN`；两个 `CONFIRMED_*` 只来自 identity-bound effect settlement。不得反向补写 canonical truth，缺失 receipt 不得自动解释为未执行。 |
| `RESUME-04` | `MAY_HAVE_OCCURRED` 必须先执行 effect-specific authoritative post-state reconciliation；在结果明确前禁止 retry、reroute 或 backend substitution。 |
| `RESUME-05` | checkpoint authenticity 与 TaskSpec lineage、schema/code/policy/provider/model/tool/profile/transform/acquisition/verifier/environment manifest 不匹配时 fail closed；stale exact approval 不得用于 rebuilt contract。 |
| `RESUME-06` | resumable interruption 与 terminal cancellation 是不同 typed lifecycle；两者只在安全边界确认，dispatch 中请求先进入 uncertain-effect recovery，不伪造安全停止。 |
| `RESUME-07` | RuntimeCommitter 是 committed checkpoint snapshot 的唯一 producer；focused store 只做原子编码/持久化，Coordinator 只顺序调用；Committer 不做 serialization/I/O/restore/session。 |
| `RESUME-08` | checkpoint-store protocol 不预先冻结文件/数据库 backend；所选实现必须有 atomic/torn-write/tamper detection 与 secret/output redaction，且无独立恢复平台、每 namespace 数据库、unbounded event replay 或第二 StateKernel owner。 |
| `RESUME-09` | `runtime_resume.py` 只做校验并输出 ResumeDirective/ReconciliationRequired；不打开 session、采集、grounding、approval、effect lookup、completion 或 state commit。 |
| `RESUME-10` | replay 只使用 pinned manifest 与 simulated adapter；miss 不得调用 live driver/network/credential，simulated receipt 与 real receipt 分型。 |
| `RESUME-11` | 当前 P5-R 不新增 batch contract/cursor/rollback/resume；checkpoint 不声称恢复 batch。 |

### 9.9 Transaction / Surface / Provenance hardening catalogue

进入 P5 只检查五项 `P4-MVP` invariant，并以 core benchmark 等 evidence 证明默认主线
闭合；evidence 不增加 invariant。`INV-01`–`INV-16` 的其余内容是 future hardening
catalogue；下表保留潜在实施归属，但不再整体充当 P5 gate：

| ID range | 实施责任 | 关键 sentinel |
|---|---|---|
| `INV-01`–`INV-03` | MVP：`P4-C0`、`P4-C3`；hardening：`P4-C4` | final materialization + approved/executed hash equality + stale zero-call；CAS/permit/fencing 后置 |
| `INV-04`–`INV-06` | `P4-C4` | transport/effect/collateral 分型；success/error/timeout/schema/process-loss 全路径 typed；identity-bound settlement |
| `INV-07`–`INV-09` | `P4-C1` | adapter-owned coverage missing=UNKNOWN；actual OutputMaterialization + privacy；semantic plan subsumption |
| `INV-10` | `P4-C3`–`P4-C5` | canonical core no legacy import/partial patch/fallback |
| `INV-11`–`INV-12` | future `P4-C2`/C4 hardening | account/session/window/frame/document/focus 与完整 coordinate transform sentinels；按场景启用 |
| `INV-13`–`INV-14` | `P4-C0`、`P4-C2` | third-party content 不扩权；provider/schema/adapter/product/user capability intersection |
| `INV-15` | `P4-C4` | 生产只 dispatch primitive；无 BatchActionContract/batch resume |
| `INV-16` | future release/replay hardening | immutable manifest、profile/ablation digest 与 resume drift；不阻塞 P5 |

## 10. 来源覆盖台账

下表保证引用对话和现有逐条审计中的每类结论都有明确落点。详细类型和流程以派生权威架构为准。

| Source ID | 来源要点 | 本文落点 | 处置 |
|---|---|---|---|
| `SRC-THIN-INTAKE` | 薄 intake、厚 execution loop、动作附近审批、执行后验证 | §0、§2、§4 | ADOPT |
| `SRC-TASK-CONTRACT` | TaskSpec 是稳定授权合同，Planner 只消费 | §0、§3.1、§9 | ADOPT |
| `SRC-PROVENANCE` | sidecar 仅在高风险/多来源时 veto/clarify | §4、§5 | ADOPT |
| `SRC-OBLIGATION-PLAN` | obligation graph 实际控制 TaskPlan | §1.1 | RETIRE |
| `SRC-ROLE-DRIFT` | PRECONDITION/PROGRESS/TERMINAL/EVIDENCE 混淆 | §1.2 | REPLACE |
| `SRC-MULTI-GRAPH` | 多套重叠语义图 | §1.3 | FLATTEN |
| `SRC-STEP-ROUNDTRIP` | StepSpec/SubgoalSpec 有损往返 | §1.4、§6 P1-1 | DELETE |
| `SRC-EVIDENCE-FIDELITY` | typed evidence 未完整传递 | §1.5、§3.3 | REPAIR |
| `SRC-COMPLETION-AUTHORITY` | Plan completion 与 Task completion 混淆 | §1.6、§9 | REPLACE |
| `SRC-PLAN-AUTHORITY` | Authority 仍主要是 binder | §1.7、§5 | STRENGTHEN |
| `SRC-FAT-TASKSPEC` | TaskSpec 是抽取结果数据库 | §1.8、§3.1 | REPLACE |
| `SRC-CANONICAL-OBSERVATION` | Runtime 不应受模型裁剪空间限制 | §1.9、§6 P0-B/C | REORDER |
| `SRC-REQUEST-PROJECTION` | PlanningRequest/PlannerContext 重复投影 | §1.10、§6 P4-1/P4-4 | FLATTEN |
| `SRC-VALIDITY-CAUSALITY` | evidence validity 与 state/effect 因果区分 | §1.11、§3.3 | ADD |
| `SRC-KEEP-PLAN` | 保留可替换 TaskPlan | §2.1 | KEEP |
| `SRC-TWO-PLANNERS` | Task planning 与 active-step action planning 分离 | §2.2、§5 | ADOPT |
| `SRC-CHOICE-SET` | 保留 Runtime-owned 0/1/N，并升级 full Catalog | §0.1、§2.3 | KEEP + STRENGTHEN |
| `SRC-CONTRACT` | 保留 Proposal → ActionContract | §2.4 | KEEP |
| `SRC-APPROVAL` | 动作附近、状态绑定、单次审批 | §2.5 | KEEP |
| `SRC-INDEPENDENT-VERIFY` | fresh post-action independent verification | §2.6 | KEEP |
| `SRC-GROUNDING-RECOVERY` | 保留 typed grounding、recovery、single writer | §2.7 | KEEP |
| `SRC-SEMANTIC-AST` | value/predicate/boolean/quantified AST | §3.2 | ADD |
| `SRC-SEMANTIC-AUTHORITY` | strict raw-text firewall 修正为 single admission + bounded contextual rereading + no authority expansion | §0.4、§1.14、§3.5、§9.4 | ADOPT CORRECTION |
| `SRC-ATOMIC-REQUIREMENT` | allowed effects/constraints/success/outputs 使用一个 canonical requirement identity | §3.6、§6 P3-4、§9.4 | ADD |
| `SRC-DEPENDENCY-SINGLE` | semantic value dependency 与 execution ordering 各自唯一落位 | §3.7、§6 P1-7、§9.4 | ADD |
| `SRC-CHOICE-PRESENTATION` | N-choice 展示完整 bounded semantics，不暴露 binding | §3.8、§6 P4-5、§9.4 | ADD |
| `SRC-OUTPUT-CLOSURE` | required structured outputs 进入 TaskCompleted closure | §3.8、§6 P0-A/P3-6、§9.4 | ADD |
| `SRC-NOT-REPAIR` | Planner 不得用 Not 反转已满足目标 | §3.2 | PROHIBIT |
| `SRC-EVIDENCE-LEAF` | CriterionPolicy 附着 criterion leaf | §3.3 | ADOPT |
| `SRC-STEP-BOUNDARY` | Step 按里程碑/依赖/环境/审批/恢复拆分 | §3.4 | ADOPT |
| `SRC-PROGRESS-LEDGER` | TaskProgress 保存事实而非复制 plan | §3.4、§6 P5-1 | ADOPT |
| `SRC-ALREADY-SATISFIED` | 规划前先检查 task success | §4、§8.4 | ADD |
| `SRC-ROLE-OWNERS` | 各模块唯一职责 | §5 | ADOPT |
| `SRC-P0-P5` | 更新后的 P0-A–P4、五项 P4-minimum、non-blocking hardening 与 P5 优先级 | §6 | ADOPT + SCOPE RESET |
| `OP-00`–`OP-08` | 入口、source、intent、semantic、TaskSpec、plan、completion | §0–§6 | COVERED |
| `OP-09`–`OP-15` | observation、context、choice、grounding | §1.9–§2.7、§6 | COVERED |
| `OP-16`–`OP-24` | contract、verification、reuse、closure、recovery、offline evidence | §1.11、§2.4–§2.7、§4–§6 | COVERED |
| `P0-1`–`P0-6` | 原审计 P0 | 按 authority dependency 重排到 §6 P0-A、P1–P3 | COVERED |
| `P1-1`–`P1-5` | 原审计 P1 | 重排到 §6 P4–P5 | COVERED |
| `P2-1`–`P2-5` | 原审计 P2 | 收敛到 §6 P2/P4；开放能力不扩执行权 | COVERED |
| `P3-1`–`P3-3` | 原审计 P3 | 进入 §6 Deferred | COVERED |
| `P0-A`–`P0-E`、`P1`–`P4`、`P4-C0`–`P4-C5`、`P4-R0`、`P5` | active-step + transaction corrective 执行顺序 | §6 | COVERED |
| `CHAIN-01`–`CHAIN-11` | 唯一生产链 11 段 | §4 | COVERED |
| `FINAL-ROUNDTRIP-01`–`04` | 四个语义往返 | §1.1、§1.3、§1.4、§1.9–§1.10 | RETIRE |

### 10.1 Active-step authority 修正覆盖台账

下表逐条对应本次附件的序言、十八个编号板块与最终结论。`Spec 落点` 指向派生权威架构；全部条目均为阻塞覆盖，不能以“总图已表达”为由省略细节。

| Amendment ID | 附件要求 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| `ACR-00` | Catalog 必须先于任何 model-facing active-step request | §0.1、§4 | §0.1、§1、§7 | COVERED |
| `ACR-01` | 完整架构与 task-planning/action-choice 双 horizon | §4 | §1、§2 | COVERED |
| `ACR-02` | PerceptionCapture、canonical authority、一次性 view 三层角色 | §1.9 | §6、§10.1 | COVERED |
| `ACR-03` | CanonicalTarget 保存 surfaces、ActionSupport、StateFact、conflict/freshness | §1.9 | §6.2 | COVERED |
| `ACR-04` | acquisition coverage 与 presentation omission 严格区分 | §1.9、§9.1 | §6.3、§11 | COVERED |
| `ACR-05` | ActionChoiceSet 升级 full Catalog，含 digest、counts、rejections | §2.3、§5 | §7.2 | COVERED |
| `ACR-06` | strict Step Planner 只消费 ChoicePlanningRequest | §1.10、§2.2 | §7.4 | COVERED |
| `ACR-07` | PlanningStage 增加 StepChoiceFlow；Coordinator 仍只编排 | §4、§5 | §7.3、§12 | COVERED |
| `ACR-08` | 大候选空间 deterministic narrowing + full Catalog + ChoicePage + sealed retrieval | §2.3 | §7.5 | COVERED |
| `ACR-09` | effectful/high-risk truncated page 的唯一授权门 | §2.3、§9.1 | §7.6、§17 | COVERED |
| `ACR-10` | permitted action kinds/admission 只从 Catalog/report 派生 | §5、§9.1 | §7.7 | COVERED |
| `ACR-11` | 多来源 conflict 的 choice/preflight 执行规则 | §1.9 | §10.3 | COVERED |
| `ACR-12` | zero-choice 与 stale/invalid selection failure ownership 重分类 | §2.3、§5 | §11.1 | COVERED |
| `ACR-13` | StateKernel 保存 observation/catalog refs，ObservationStore 保存 immutable graph | §5、§6 P5-2 | §11.4 | COVERED |
| `ACR-14` | post-action canonical epoch 直接复用并列明重捕获条件 | §6 P1-5、§9 | §9.7、§10 | COVERED |
| `ACR-15` | 六个具体文件/模块修改与 legacy deletion gates | §5、§6 | §15 | COVERED |
| `ACR-16` | P0 回归红线与 P0-A 至 P5 迁移顺序 | §6、§9.1 | §15、§17 | COVERED |
| `ACR-17` | OBS-01 至 OBS-12 与静态 import gates | §9.1 | §17.1 | COVERED |
| `ACR-18` | observation/choice correctness 与 completion authority 同为 P0 | §6 | §15 | COVERED |
| `ACR-FINAL` | Runtime 建完整合法目录，模型只在受控页面选择 | §0.1、§2.3 | §19 | COVERED |

### 10.2 SourceEnvelope B+ 修正覆盖台账

| Amendment ID | 附件要求 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| `BPLUS-00` | SourceEnvelope always-on；SemanticAudit optional；Verifier loop-native | §0.2–§0.3 | §0、§1、§9 | COVERED |
| `BPLUS-01` | 目标方向与当前 heavy SourceLedger implementation 区分 | §1.12 | §2 A、§14–§15 | COVERED |
| `BPLUS-02` | SourceEnvelope + selective SourceAnchor + MinimalIntentProposal + TaskSpec v2 | §0.2、§3.1 | §4 | COVERED |
| `BPLUS-03` | SemanticAudit triggers、合同与 veto-only 权限 | §0.2、§5、§9.2 | §4.3、§12、§17 | COVERED |
| `BPLUS-04` | 禁止 Obligation Graph 命名回流，统一 TaskPlan/Milestone Graph | §2.1、§9.2 | §3、§6 | COVERED |
| `BPLUS-05` | Verification 时序内化，完成权威保持隔离 | §0.3、§2.6 | §9、§12 | COVERED |
| `BPLUS-06` | 产品 loop feedback 与 independent grading 的折中定位 | §0.3 | §9.1 | COVERED |
| `BPLUS-07` | LoopEvaluator façade + 三层 evidence location | §2.6、§5 | §9.2–§9.4 | COVERED |
| `BPLUS-08` | 最小 validity/causality/assurance policy | §1.11、§3.3 | §5.4 | COVERED |
| `BPLUS-09` | verifier 内化后的完整主循环和触发时机 | §4、§8.10 | §1、§9.5 | COVERED |
| `BPLUS-10` | Source S1–S4 与 Verification V1–V5 最小迁移 | §6 | §15 | COVERED |
| `BPLUS-11` | 最终统一图与两条最终原则 | §0、§4 | §1、§19 | COVERED |

### 10.3 Loop-native Verification 修正覆盖台账

| Amendment ID | 附件要求 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| `LOOPVER-00` | lightweight typed evaluation + independent completion authority | §0.3 | §0、§9 | COVERED |
| `LOOPVER-01` | 最新统一 architecture chain | §4 | §1 | COVERED |
| `LOOPVER-02` | 不建设默认大 verifier platform / full EvidenceIndex / source-specific criteria | §1.13、§7 | §5、§9、§16 | COVERED |
| `LOOPVER-03` | 最小 CriterionPolicy 三个正交维度 | §1.11、§3.3 | §5.4 | COVERED |
| `LOOPVER-04` | state truth 与 action causality + CausalEffectEvidence | §1.11、§6 P2-3 | §9.3 | COVERED |
| `LOOPVER-05` | 七态 CriterionStatus + compact CriterionEvaluation | §9.3 | §9.2 | COVERED |
| `LOOPVER-06` | TaskCompletionEvaluation 唯一通过条件 | §0.3、§9.3 | §9.4 | COVERED |
| `LOOPVER-07` | completion evaluation trigger set | §8.10 | §9.5 | COVERED |
| `LOOPVER-08` | CriteriaEvidenceMatcher 退化为 EvidenceAdmissionPolicy | §6 P0-A/P2-5 | §9.6、§15 | COVERED |
| `LOOPVER-09` | ObservationDisposition 四态与复用/重捕获条件 | §6 P1-5、§9.1 | §9.7 | COVERED |
| `LOOPVER-10` | ModelVerifier evidence-only、high-risk prohibition | §2.7、§6 P2-6 | §9.8 | COVERED |
| `LOOPVER-11` | mechanical verifiers 降为 internal evidence providers | §2.7、§6 P2-5 | §9.9 | COVERED |
| `LOOPVER-12` | 禁用 receipt fallback 与 verification-disabled PASSED | §1.13、§6 P0-A | §14–§17 | COVERED |
| `LOOPVER-13` | typed recovery ownership | §5、§9.3 | §11.1 | COVERED |
| `LOOPVER-14` | 轻量 verification 模块布局与升级条件 | §6、§7 | §15.2 | COVERED |
| `LOOPVER-15` | P0–P3 verification priority | §6 | §15 | COVERED |
| `LOOPVER-16` | VER-01–14、OBS-13–14、REC-01 | §9.1、§9.3 | §17.1 | COVERED |

### 10.4 Semantic Authority / Contract Closure 补充覆盖台账

第二份复核是第一份复核的覆盖性修正：只替换严格 Semantic Firewall；第一份的 atomic requirement、dependency、choice presentation 与 output closure 继续有效。

| Amendment | 合并要求 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| `NLI-01`–`NLI-08` | single admitted meaning、bounded context-only rereading、execution raw-text prohibition、pre-admission repair | §0.4、§3.5、§5、§6、§9.4 | §0.4、§4.8、§12、§17.1 | COVERED |
| `REQ-01`–`REQ-05` | canonical TaskRequirement identity、Step traceability、TaskPlanAuthority rejection | §3.1、§3.6、§6、§9.4 | §4.4、§4.9、§5、§6、§17.1 | COVERED |
| `DEP-01`–`DEP-03` | typed value refs 与 StepSpec.depends_on 各自单一 | §3.7、§6 P1-7、§9.4 | §4.9、§6、§17.1 | COVERED |
| `CHOICE-13` | bounded semantic ChoicePresentation | §3.8、§5、§6 P4-5、§9.4 | §7.5、§17.1 | COVERED |
| `OUT-01`–`OUT-03` | stable OutputSpec 与 materialized/source-bound completion | §3.8、§5、§6 P0-A/P3-6、§9.4 | §4.4、§9.4、§17.1 | COVERED |

### 10.5 Physical Minimality 风险处理台账

| 审计风险/建议 | 决议 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| full Catalog 全量物化 | 逻辑完整与物化策略分离 | §0.5、§3.9、§6 P0-C/P4-3、§9.5 | §0.5、§7.2、§17.1 | ADOPT CONSTRAINT |
| canonical observation 巨型复制 | immutable epoch ref + indexes | §0.5、§3.9、§6 P5-2、§9.5 | §0.5、§11.4、§17.1 | ADOPT CONSTRAINT |
| authority/service/store 碎片化 | modular monolith + in-process composition | §0.5、§3.9、§7、§9.5 | §0.5、§12、§16、§17.1 | ADOPT CONSTRAINT |
| Criterion 首期范围过大 | vocabulary 与 provider coverage 分离 | §3.9、§6 P2-1、§9.5 | §5.2、§15、§17.1 | ADOPT CONSTRAINT |
| TaskPlanner 每轮重规划 | typed planning gate + reuse/direct fast path | §0.5、§3.9、§4、§6 P4-6、§9.5 | §6.6、§15、§17.1 | ADOPT CONSTRAINT |
| 所有 optional 能力默认开启 | risk-derived feature profiles | §0.5、§3.9、§7、§9.5 | §0.5、§16、§17.1 | ADOPT CONSTRAINT |
| exact SourceAnchor 扩散到所有 material fields | 采用 risk-proportionate MaterialBinding；exact excerpt 只用于间接非结构化来源，字段完整性由 TaskSpecAuthority 校验 | §0.2、§5、§6 P0-E/P3-3、§9.2.1 | §4.2–§4.4、§17.1 | CORRECTED |
| optional audit / bounded evidence / deferred ModelVerifier / raw-text boundary | 保持原 owner 与触发规则 | §0.2–§0.4、§3.5、§6、§9.2–§9.4 | §0.3–§0.4、§4.3、§4.8、§9、§17.1 | ALREADY COVERED |
| 撤销 TaskRequirement，改为分散 effect/constraint/criterion/output IDs | 会重新引入 semantic identity 漂移；保持 flat canonical TaskRequirement table | §3.6、§6 P3-4、§9.4 | §4.4、§4.9、§17.1 | REJECT |
| ChoicePresentation / required-output closure 是新缺口 | 当前目标合同已经补齐 | §3.8、§6、§9.4 | §7.5、§9.4、§17.1 | ALREADY COVERED |
| 权威文档过大 | 不新增第三 authority；同一文档保持核心法律→schema→迁移/gate→mapping 层级 | §0、§10、§11 | §0、§15–§19 | ADOPT DOCUMENT LAYERING |

### 10.6 Cross-Surface Visibility 补充覆盖台账

| 补充 | 决议 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| 主图与 vocabulary 显式列出 WoT | `Surface.WOT` 与三种 typed WoT source/evidence role 进入规范 | §0.6、§1.9、§3.10 | §9.1、§10.1–§10.5 | ADOPT CLARIFICATION |
| DOM/AX/Visual/SVG/WoT/API/Device 的 owner 关系 | 使用一条 shared authority chain，不新增 surface-specific task/planner/completion authority | §0.6、§4、§9.6 | §0.1、§10.5、§17.1 | ALREADY ARCHITECTURAL; MAKE EXPLICIT |
| semantic action 与 backend route 分离 | Planner 选 semantic action；Materializer 内 route owner 选 current binding/backend | §3.10、§5、§9.6 | §7、§10.4–§10.5、§17.1 | ADOPT INVARIANT |
| 当前代码已有跨表面基础 | DOM、visual/SVG、WoT adapter/grounding/executor/route 继续保留；canonical-first/full-Catalog/loop-provider cutover 仍属 P0-B/P0-C/P1–P2 | §1、§6、§11 | §15 | RECORD CURRENT VS TARGET |

### 10.7 Risk-proportionate Material Binding 纠偏覆盖台账

| Amendment | 附件要求 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| `MAT-01` | 不对每个高风险自然语言字段强制字符级 exact span | §0.2、§6 P0-E/P3-3、§9.2.1 | §0、§4.2、§17.1 | ADOPT |
| `MAT-02` | direct user explicit / exact excerpt / typed external / user confirmed 四种 binding | §0.2、§5、§9.2.1 | §4.2 | ADOPT |
| `MAT-03` | source type × risk policy；page/screen 不得创建授权 | §0.2、§5、§8.9、§9.2.1 | §4.2、§17.1 | ADOPT |
| `MAT-04` | TaskSpecAuthority 按 SEND/PAYMENT/DELETE/SHARE 校验必需字段组 | §5、§6 P0-E/P3-3、§9.2.1 | §4.2–§4.4 | ADOPT |
| `MAT-05` | exact anchor 只证明 provenance，不替代 approval/capability/grounding/contract | §9.2.1 | §4.2、§17.1 | ADOPT |
| `MAT-06` | 字段 completeness 从 SemanticAudit 移入小型 deterministic policy | §0.2、§5、§6 P0-E、§9.2.1 | §4.2–§4.3 | ADOPT |
| `MAT-07` | direct send、indirect attachment、amount-only payment 与 page-authority 回归 | §8.9、§9.2.1 | §17.1 | REQUIRED MINIMAL GATE |

### 10.8 Concrete Effect Authority / High-risk Governance 纠偏覆盖台账

| Amendment | 最新 push / 治理要求 | 本规划落点 | Spec 落点 | 状态 |
|---|---|---|---|---|
| `CEA-01` | 保留 `8b91944` 的 no-keyword、exact target/destination 与 Runtime risk 方向，但不得宣称 complete | §0.7、§1.16 | §0.1、§7.2.1 | ADOPT AS INTERIM |
| `CEA-02` | Task authorization 使用 parameterized `EffectAuthorizationScope`，与 Runtime concrete signature 是不同合同；不使用 coarse operation class + label/value set | §3.11、§6 P4-G1、§9.7 | §4.6.1、§17.1 | REQUIRED |
| `CEA-03` | Runtime 从 actual current bindings 构造 `RuntimeEffectSignature`，包含 operation/effect/externality/reversibility/risk/assurance | §3.11、§6 P4-G2、§9.7 | §7.2.1、§10 | REQUIRED |
| `CEA-04` | ALLOW/DENY/UNPROVEN proof；Catalog 只接纳 ALLOW，unknown 不默认 LOW | §6 P4-G2–G3、§9.7 | §7.2.1、§11、§17.1 | REQUIRED |
| `CEA-05` | Contract/Gate 独立复核 actual binding；approval 不能补 authority | §6 P4-C3、§9.7–§9.9 | §8.1–§8.4、§17.1 | MVP SUBSET CLOSED / BROADER HARDENING DEFERRED |
| `CEA-06` | high-risk effect-specific pre/post policy、uncertain effect no retry | §6 P4-C4–C5、§9.7–§9.9 | §8.5、§9、§11、§17.1 | MVP SUBSET CLOSED / BROADER HARDENING DEFERRED |
| `CEA-07` | 不陷入页面/任务枚举；small EffectClass + extensible OperationRef + named parameters | §0.7、§3.11、§7 | §4.6.1、§7.2.1、§16 | REQUIRED |
| `CEA-08` | 不新增 god file/test project；Catalog builder 拆分，复用小型 redline matrix | §6 P4-C3/C5、§7 | §15–§17 | MVP CONTAINMENT CLOSED |
| `CEA-09` | Runtime risk 取多维保守最大值；Text/VLM 只能 raise-only，不能 ALLOW、降风险或创建 scope | §3.11、§6 P4-G2、§9.7 | §0.1、§7.2.1、§17.1 | REQUIRED |
| `CEA-10` | EnablingActionPolicy 明确允许集与 local reversible draft 边界，禁止 external commit/unauthorized disclosure/UNKNOWN effect | §6 P4-G3、§9.7 | §7.2.1、§17.1 | REQUIRED |
| `CEA-11` | approval 向用户展示并绑定 reversibility、backend operation、sources/uncertainty；任何 route/parameter/classification 变化使 token 失效 | §3.11、§6 P4-G4、§9.7 | §8.1–§8.3、§17.1 | REQUIRED |
| `CEA-12` | proof 绑定 evaluator policy version；risk × source-assurance matrix 决定 high-risk execute/final evidence floor | §6 P4-G1/P4-C3/C4/C5、§9.7–§9.9 | §7.2.1、§8.5、§17.1 | REQUIRED |
| `CEA-13` | 最小行为矩阵覆盖 low-risk read/navigation、high-risk API/WoT、unknown/uncertain effect 与 mismatch/parameter/assurance/token invalidation，不建设测试平台 | §6 P4-C0–C5、§7 | §8.5、§17.1 | REQUIRED |
| `CEA-14` | 旧审计建议把 P3-2/P4-4 整行回退 partial | requirement traceability/pure presentation core 保留；semantic admission 由 `P4-7/P4-C1` 闭合；旧 production-security closure claim 撤回，五项 MVP closure 已完成 | §6 P4-G/P4-C、§9.7–§9.9 | CORRECTED BY MVP SCOPE RESET |

### 10.9 SOTA / Transaction / Surface / Provenance 覆盖台账

| 来源/风险 | 采用 | 拒绝/限界 | 落点 |
|---|---|---|---|
| Qwen-UI-Agent isolated context/environment action subset/multichannel observation/ask_user/state verifier | execution context、capability descriptor、UNKNOWN coverage、user handoff、independent completion；lease 是本地补强而非来源原生声明 | effectful batch、裸 CLI、normalized coordinate-only、benchmark score=safety | §0.8、§6 P4-C0/C1/C2/C4 |
| UI-TARS / AndroidWorld coordinate/action contracts | typed action schema、logical/physical frame、orientation、stable-state polling | generic Boolean receipt、schema fail-open、polling=effect proof | §6 P4-C0/C2/C4 |
| GUI-Actor candidate/verifier | optional acquisition evidence | candidate=locator/absence/authority | §0.8、§6 P4-C1/C2 |
| CaMeL trusted-control/untrusted-data | effectful typed source→sink enforcement | general taint platform / prompt-only security | §0.8、§6 P4-C1/C2 |
| AgentDojo / WASP | future release profile：benign utility、utility-under-attack、targeted ASR | P4/P5 blocker、online authority/single proof | §6 future hardening、§9.9 |
| OSWorld-V2 functional/collateral methods | future release profile：functional checkpoints、risk-scoped negative probes | P4/P5 blocker、reward/judge=production completion | §6 future hardening、§9.9 |
| adjacent A Modular Action System Architecture source precedent | isolated task browser、mark-ID grounding、total result、shared benchmark adapter | precedent=sufficient authority；缺失 context generation/transform digest/typed effect 时不得直接复制 | §0.8、§6 P4-C2/C4/C5 |
| overengineering risk | small refs/value objects/pure policies in modular monolith | microservices、general graph/theorem prover/taint、per-namespace DB、distributed lease、batch rollback | §0.8、§6、§7 |

## 11. 完成状态

| 步骤 | 状态 | 产物或验证 |
|---|---|---|
| 读取引用对话与现有权威文档 | DONE | 引用对话、2026-07-29 权威架构、2026-08-05 修改审计 |
| 核对当前分支关键实现与已知缺口 | DONE | HEAD、obligation audit、Plan/Progress/Completion 路径 |
| 固化完整演进决议与逐条覆盖台账 | DONE | 本文件 |
| 合入 active-step authority 修正 | DONE | `ACR-00`–`ACR-18`、`ACR-FINAL` 与 `OBS-01`–`OBS-12` |
| 合入 SourceEnvelope B+ 与 loop-native verification 修正 | DONE | `BPLUS-00`–`BPLUS-11`、`LOOPVER-00`–`LOOPVER-16`、`SOU-01`–`SOU-12`、`VER-01`–`VER-14`、`OBS-13`–`OBS-14`、`REC-01` |
| 合入 Semantic Authority / Contract Closure 补充 | DONE | `NLI-01`–`NLI-08`、`REQ-01`–`REQ-05`、`DEP-01`–`DEP-03`、`CHOICE-13`、`OUT-01`–`OUT-03` |
| 合入 Physical Minimality 风险约束 | DONE | `CAT-PHY-01`、`OBS-PHY-01`、`AUTH-PHY-01`、`CRIT-PHY-01`、`PLAN-PHY-01`、`PROFILE-01`；审计建议按 adopt/already-covered/reject 分类 |
| 合入 Cross-Surface Visibility 补充 | DONE | `Surface.WOT`、typed WoT evidence roles、`SURFACE-01`–`SURFACE-03`；不改变 P0–P5 顺序 |
| 合入 Risk-proportionate Material Binding 纠偏 | DONE | `MaterialBindingKind`、effect-specific field coverage、`MAT-01`–`MAT-07`；exact span 不再是直接明确指令的通用门禁 |
| 合入 Concrete Effect Authority / High-risk Governance 目标与实施门 | MVP CLOSED / DESIGN RETAINED | `AUTHZ` 中 final-contract/approval hash 与 `HRA-02` no-blind-retry 已通过 MVP closure evidence；更强 high-risk hardening 后置 |
| Transaction / Surface / Provenance scope reset | MVP GATE REDEFINED | 只以 `P4-MVP-1`–`P4-MVP-5` 进入 P5；`INV-01`–`INV-16` 的并发/context/collateral/manifest 扩展为 future hardening；当前实现状态见 `implementation-status.md` |
| 生成权威总图和细节板块 | DONE | 派生权威架构文档，含总图、九个板块、合同、迁移、门禁与逐条映射 |
| 旧实现基线验证记录 | HISTORICAL ONLY | 旧 P4-G review 曾记录 `930 passed` 与静态检查通过；2026-08-07 审计证明这些测试未覆盖 full O1/dispatch/coverage/output/context/provenance 缺口，不再作为 P5 准入证据 |
| 旧 corrective 实现门禁与独立读者复核 | SUPERSEDED AS P4 CLOSURE EVIDENCE | 历史 `136 passed` / `1001 passed` / static checks 只说明当时 regression health，不能证明旧 production-security gate，也不再阻塞 P5；新 MVP focused evidence 由 implementation status 记录 |

代码实现状态的唯一当前摘要仍是 `docs/implementation-status.md`，当前执行队列是
`docs/current-implementation-plan.md`。本规划不宣称 production-grade security；Git/远端
release attestation 与 P4-R0 独立于 MVP/P5 调度。

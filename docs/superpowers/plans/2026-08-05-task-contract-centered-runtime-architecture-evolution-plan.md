# Task Contract 中心化 Runtime 架构演进规划

> **文档类型：** Architecture Evolution Plan / Source-of-Truth Ledger
> **状态：** AUTHORITATIVE EVOLUTION PLAN
> **日期：** 2026-08-05
> **事实基线：** `agent/migrate-runtime-components @ 55bad91e56126269af7453913cf550cb5938108f`
> **派生目标架构：** [Task Contract 中心化唯一权威目标架构](../specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **历史基线：** [2026-07-29 唯一权威优化目标架构](../specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md)
> **2026-08-05 权威修正：** active-step 链必须先从 canonical observation 建立完整 Runtime `ActionChoiceCatalog`，再投影任何 model-facing request；§10.1 对该修正逐条登记。
> **2026-08-05 Source / Verification 收口：** 默认 intake 改为轻量 `SourceEnvelope + selective SourceAnchor`，细粒度 `SemanticAudit` 按风险启用；verification 改为 loop-native typed `LoopEvaluationPhase`，完成语义仍由 `TaskCompletionEvaluator` 独立求值、只由 `RuntimeCommitter` 提交。§10.2–§10.3 逐条登记两份修正。

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
single-writer Coordinator
```

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

`SourceEnvelope` 始终存在，只保存全文 identity/version、外部 source refs、caller/conversation identity 与 content digests；不做 clause splitting、dependency parsing、claim/coverage/obligation graph。精确 span 只用于 recipient、amount、account、file、external destination、destructive target、forbidden effect 和 approval-related constraint 等 material fields。`SemanticAudit` 只能 pass/veto/clarify，不能创建或修改 TaskSpec。

### 0.3 Verification 物理内化、逻辑分权

默认不建设独立 verifier service、VerifierPlanner、全量 EvidenceGraph 或长期全历史 EvidenceIndex。执行后主链固定为：

```text
ExecutionReceipt
    → fresh canonical post-action observation
    → inline LoopEvaluationPhase
        ├─ action effect evaluation
        ├─ active-step completion evaluation
        ├─ TaskSpec.success evaluation when triggered
        └─ observation continuation decision
    → RuntimeCommitter
```

`LoopEvaluator` 是 loop-native pure collaborator；它不执行动作、不修改 TaskProgress、不提交 terminal state。`TaskCompletionEvaluator` 只求值 TaskSpec.success 与 required constraints/final rechecks；只有 RuntimeCommitter 可以提交 `TaskCompleted`。

## 1. 当前事实与问题边界

本文区分四类状态：

- `CURRENT`：事实基线中可由代码证明的行为。
- `KEEP`：当前已有且目标架构明确保留的边界。
- `GAP`：当前存在的语义损失、职责混杂或权威缺口。
- `TARGET`：本规划要求达到、但不代表已经实现的目标。

### 1.1 任务语义被 intake graph 提前固化为执行计划

`PlanCandidateGeneratorRouter.generate()` 在 `task_spec.obligations` 非空时优先选择 rule generator；`_steps_from_task_spec()` 随后为每个 obligation 调用 `_step_from_obligation()`。因此当前默认链是：

```text
Intake LLM
    → obligation graph
    → one obligation / one StepSpec
    → TaskPlan shape
```

即使 `TaskPlanningContext` 已包含当前 snapshot、affordances、failures 和 budget，obligation 路径仍主要由 intake graph 决定计划粒度。问题不是 Planner 还不够智能，而是 `what / authorization boundary` 与 `how under current observation` 的职责边界错误。

### 1.2 Obligation 的语义角色不稳定

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

### 1.3 同一语义存在多套重叠图

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

### 1.4 `StepSpec → SubgoalSpec → StepSpec` 是真实有损往返

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

### 1.5 Typed evidence 没有沿主链完整保留

obligation-to-step 与 provider-candidate-to-step 路径会使用默认 `dom_state` evidence source，没有完整保留 obligation 的 typed evidence requirements。目标链应为：

```text
Task / Step criterion
    → minimal CriterionPolicy
    → LoopEvaluator + available internal evidence providers
    → typed CriterionEvaluation / TaskCompletionEvaluation
```

TaskSpec 与 StepSpec 不绑定某个 DOM verifier 实现；criterion leaf 只保留 satisfaction、validity、assurance、allowed source kinds 与 model fallback。当前 observation、bounded ActionOutcome 与 durable evidence 分层提供证据，不把 provider 计划塞进 ActionContract。

### 1.6 Plan completion 与 task completion 仍未隔离

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

### 1.7 TaskPlanAuthority 当前更接近 binder

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

### 1.8 TaskSpec 当前更像抽取结果数据库

当前 TaskSpec 同时保存 objective、operation class、task structure、targets、requested effects、entities、preferences、outputs、success strings、semantic constraints、source claims、obligations、forbidden effects、evidence strings、capabilities、ambiguity 与 field provenance。

这些内容不是都无价值，但必须迁移到职责稳定的容器：

| 当前概念 | 目标位置 |
|---|---|
| 用户授权效果、硬约束、禁止效果、终态 | `TaskSpec` |
| 来源 identity/version 与 material-field lineage | always-on `SourceEnvelope` + selective `SourceAnchor` |
| 高风险/多来源/conflict 的细粒度 coverage audit | optional `SemanticAudit`，veto/clarify only |
| 步骤、依赖、interaction intent、action budget | `TaskPlan<StepSpec>` |
| 已完成状态、facts、bindings、evidence instances | `TaskProgress` 与 append-only ledgers |
| 当前动作、locator、backend、TTL、evaluation requirements | `ActionContract` |
| 未解决 ambiguity | 不准入 TaskSpec，返回 clarification |

### 1.9 Canonical observation 当前先受模型预算裁剪

当前生产路径由 bounded `PlannerObservationView` 构造 `UnifiedObservation`，Runtime ActionChoiceBuilder 因而可能与模型共享同一个被裁剪的候选空间。目标是：

```text
DOM / AX / Visual / SVG / API / Device
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

### 1.10 PlanningRequest 之后仍有重复领域投影

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

### 1.11 最终证据需要 validity 与 causality 语义

“目标状态现在为真”与“本次动作造成了目标状态”不是同一命题。criterion 必须声明：

```text
SatisfactionMode =
    STATE_HOLDS
  | ACTION_CAUSED
```

Evidence validity 独立区分：

```text
CURRENT_OBSERVATION
DURABLE
FINAL_RECHECK
```

assurance 只需 `WEAK / STRUCTURAL / AUTHORITATIVE`。旧证据只有在 `DURABLE` policy 允许且未失效时复用；`ACTION_CAUSED` 必须绑定 current task/ActionContract 的 ActionOutcome，`FINAL_RECHECK` 必须使用最新权威 recheck。

### 1.12 默认 SourceLedger 路径仍然过重

当前实现仍默认创建 whole-request + 最多 32 个 clause units，标记 `required_candidate`，要求模型返回 source claims/obligations，并执行 deterministic/model-backed obligation coverage。clause 超限会在模型调用前 fail closed。它把 provenance correctness 与 semantic graph completeness 绑在一起，继续让 intake graph 影响 plan shape。

目标不是删除 provenance，而是拆为：

```text
always-on SourceEnvelope
+ selective SourceAnchor
+ optional SemanticAudit
```

SourceEnvelope 只拥有合法 authority source 的 identity/version；SemanticAudit 才按风险执行 span/coverage/conflict 审计。普通任务不得因未建立 clause/claim/obligation graph 而失败。

### 1.13 Verification 主线存在过重与不安全两类风险

长期能力地图中的 VerifierPlanner、provider registry、EvidenceIndex、validity/composite evaluator 不应整体成为默认生产平台；默认 GUI Runtime 只需要 loop façade、typed predicates、current observation、recent ActionOutcome 与 small DurableEvidenceStore。

同时以下 legacy 行为必须 fail closed：

- `VerifierLadder.verify()` 无 specs 时不得退化为 `receipt.success`；
- verification disabled 不得生成 `PASSED`；
- latest passed report 不得完成 task；
- description-based criteria matcher 不得拥有 completion semantics；
- `terminal_readiness` 只能保留 legacy action-admission compatibility，不能扩张为 task completion authority。

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

### 2.4 PlannerProposal → ActionContract

语义选择与具体执行继续分离。ActionContract 绑定 current snapshot、page revision、target fingerprint、locator、parameters、backend、TTL、risk、required capabilities、expected effects、verifier plan、idempotency 与 contract hash。

### 2.5 动作附近审批

审批绑定具体 ActionContract，而不是 intake 里的意图、TaskPlan 或 action family。ApprovalToken 继续绑定 run、contract hash、page revision、capability、approver、expiry，并单次消费。状态变化或 contract rebuild 使旧审批失效。

### 2.6 执行后独立验证

ExecutionReceipt 只证明执行器报告了一次尝试。verification 作为 `LoopEvaluationPhase` 内化进 serial execution loop，但 receipt、action effect、step completion、task completion 仍使用不同类型。没有适用 evidence/provider 时为 `UNKNOWN` 或 `UNSUPPORTED`，绝不因 verification disabled 或无 verifier spec 返回 passed。

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
- 用户提供或明确授权的 inputs；
- allowed effects，即任务可造成的最大效果范围；
- hard constraints；
- preferences；
- forbidden effects；
- 唯一 task success expression；
- requested outputs；
- capability ceiling，而非实际 capability grant；
- risk policy reference；
- source envelope identity 与 source binding digest。

Planner 只能消费 TaskSpec；只有用户澄清、用户修改或授权策略变化才能创建新 revision。

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
EvidenceValidityMode = CURRENT_OBSERVATION | DURABLE | FINAL_RECHECK
AssuranceLevel       = WEAK | STRUCTURAL | AUTHORITATIVE
```

并保存 allowed source kinds 与 `model_fallback_allowed`。source kind 属于 evidence policy，不扩张成 DOM/API/Visual × predicate 的 criterion 类型组合。Model evidence 默认不具备 AUTHORITATIVE assurance。

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
    → TaskPlanningObservationProjector
    → TaskPlanningRequest
    → PlanProposal<StepSpec>
    → TaskPlanAuthority
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
    → ActionContractBuilder
    → Task Authority ∩ Capability ∩ Approval ∩ Freshness/Preflight
    → Execute
    → ExecutionReceipt
    → fresh post-action UnifiedObservation
    → inline LoopEvaluationPhase
        → Action Effect Evaluation
        → Step Completion Evaluation
        → triggered Task Completion Evaluation against TaskSpec.success
        → ObservationContinuation
    → RuntimeCommitter
    → continue / advance / replan / recover / clarify / block / fail / complete
```

生成 TaskPlan 前必须先验证任务是否已经满足。若 `TaskSpec.success` 在初始 observation 上成立且 satisfaction policy 允许，应无动作完成，不得制造 `implicit visible step`。

## 5. 模块唯一职责

| 模块 | 输入 | 输出 | 明确禁止 |
|---|---|---|---|
| `SourceEnvelopeBuilder` | UserRequest refs + identity/version metadata | immutable SourceEnvelope | clause splitting、语义解释、graph 构建 |
| `SourceAnchorBuilder` | material field + authorized source | selective SourceAnchor | 为所有低风险句子强制建图 |
| `MinimalIntentInterpreter` | UserRequest short-lived content + SourceEnvelope | anchor-bound MinimalIntentProposal | 提交 TaskSpec、生成步骤 |
| `SemanticAudit` | proposal + envelope/anchors | pass/veto/clarify | 添加效果、修改 success、提升授权 |
| `TaskSpecAuthority` | proposal + policy + sources | immutable TaskSpec / typed rejection | 推断步骤、静默补 submit/delete/payment |
| `PerceptionSession` | source capture policy | immutable PerceptionCapture + SourceCoverage | 声称未采集内容不存在 |
| `CanonicalObservationBuilder` | PerceptionCapture | canonical UnifiedObservation | 读取 model presentation policy、修改 TaskSpec/progress |
| `ObservationStore` | canonical observation | immutable ObservationRef | 向 Planner 暴露 store handle |
| `TaskPlanner` | TaskPlanningRequest | PlanProposal | 修改 TaskSpec、输出 concrete action |
| `TaskPlanAuthority` | proposal + TaskSpec + observation identity | TaskPlan / reject / repair / clarify | 添加步骤、授予 capability |
| `TaskProgressService` | committed evaluation results | facts/bindings/durable evidence/step transition | 根据 receipt 直接完成 |
| `ActionChoiceBuilder` | task/plan/progress/active scope + canonical observation + capabilities/policy | full ActionChoiceCatalog + ChoiceBuildReport | 读取 presentation limit、调用 LLM、执行动作 |
| `ChoicePresentationProjector` | full Catalog + model policy | bounded ChoicePage | 改变 Catalog membership/digest |
| `StepChoicePlanner` | ChoicePlanningRequest | sealed selection/retrieval/control proposal | 发明动作、参数、locator 或选择未展示 ID |
| `ActionSelectionValidator` | proposal + current catalog/page identities | accepted ActionSelection / reject | 修复成另一个 choice |
| `ActionContractBuilder` | selected choice + CatalogRef + canonical ObservationRef | immutable ActionContract | 从 model view 绑定、执行、授予 approval |
| `TaskAuthorityGate` | contract + TaskSpec | allow/deny | 用文本关键词代替 typed authorization |
| `CapabilityGate` | requirements + grants | allow/deny | 修改 TaskSpec |
| `ApprovalGate` | concrete ActionContract | one-shot bound approval | 提前批准 plan/action family |
| `PreflightService` | contract + fresh observation | executable/stale | 自动重定位后继续旧合同 |
| `Executor` | admitted ActionContract | ExecutionReceipt | 判断 effect/step/task success |
| `LoopEvaluator` | task/step/contract/receipt/pre+post observation/recent outcomes/durable evidence | LoopEvaluation | 执行动作、写状态、提交 terminal |
| `EvidenceProvider` | typed predicate + source input | observed value + assurance/freshness metadata | 决定 task completion |
| `TaskCompletionEvaluator` | TaskSpec.success + constraints + admitted evidence | TaskCompletionEvaluation | 根据 plan exhausted/reward 自行通过、写 StateKernel |
| `EvidenceAdmissionPolicy` | CriterionPolicy + evidence metadata | admitted/rejected evidence | 重定义 criterion semantics |
| `DurableEvidenceStore` | durable records only | immutable durable evidence refs | 复制 current observation 或保存无界历史 |
| `PerceptionOwner` | post observation + next requirements | ObservationContinuation | 无理由重复 capture |
| `RecoveryPolicy` | typed failure + budgets | bounded command | 任意改 StateKernel |
| `Coordinator / RuntimeCommitter` | typed stage results | serialized transitions/events | 重解用户语义、实现领域算法 |

## 6. 迁移顺序与删除门

迁移采用 substitutive migration：每引入一个新的 canonical owner，必须在同一阶段定义旧 owner 的删除门；不接受长期 `new model + projector + checker + shadow + future cutover`。

### P0：同时封住执行环出口与入口的 correctness 缺口

| ID | 工作项 | 依赖 | 完成门 |
|---|---|---|---|
| `P0-A` | TaskCompletionEvaluator 递归求完整 TaskSpec.success closure；禁用无 spec receipt fallback 与 verification-disabled PASSED | criterion/evidence compatibility foundation | latest report、receipt、plan exhausted、Planner Finish 均不能单独完成 task；无 evidence 为 UNKNOWN |
| `P0-B` | `PerceptionCapture → CanonicalObservationBuilder → UnifiedObservation` 先于所有 presentation | 可与 P0-A 并行 | production 无 `from_planner_observation`；coverage/conflict/bindings 保真 |
| `P0-C` | 将 ActionChoiceBuilder 移出 GeneralistLMPlanner，先建 full Catalog 再建 ChoicePage | P0-B | presentation limits 不进入 builder；同一 canonical inputs 得到相同 digest |
| `P0-D` | 先写第 81 个目标、12-field state、artifact/label/context limit、conflict、multi-binding 回归红线 | P0-B/C 同阶段 | 改变任何 presentation 参数不改变 Catalog；错误分类不混同 |
| `P0-E` | SourceEnvelope 成为 default source path；普通 intake 不建 clause/claim/obligation graph | 可与 P0-A 并行 | SourceLedger clause bound 不再阻塞普通任务；TaskSpec 使用 envelope ref + binding digest |

### P1：直接 canonical TaskPlan，删除 legacy 往返

| ID | 工作项 | 完成门 |
|---|---|---|
| `P1-1` | TaskPlan 直接保存 typed StepSpec | 无默认 `StepSpec → SubgoalSpec → StepSpec` |
| `P1-2` | TaskPlanAuthority 单一 validation/admission/version owner | binder/projector 不再拥有 plan semantics |
| `P1-3` | obligation presence 不再控制 plan shape | 所有 TaskPlan 都读取 current canonical observation |
| `P1-4` | 新增 loop-native `LoopEvaluator` façade | action/step/task evaluation 使用不同 typed result；Evaluator 无状态写权 |
| `P1-5` | `ObservationContinuation` 四态复用协议 | REUSE/AUGMENT_TARGETED/RECAPTURE/WAIT_AND_RECAPTURE 由 Perception owner 决定 |
| `P1-6` | SourceLedger clause/span/coverage 能力迁入 optional `semantic_audit/` | 默认 compiler/prompt 不再要求 candidate_source_claims/candidate_obligations |

### P2：Criterion AST 与 typed evidence

| ID | 能力 | 权限限制 |
|---|---|---|
| `P2-1` | 封闭 Value/Predicate/Composite/OpenSemantic AST | 不按 DOM/API/Visual source 扩张 criterion class |
| `P2-2` | 最小 CriterionPolicy：2 satisfaction × 3 validity × 3 assurance | 不以默认 DOM 覆盖 policy；model evidence 非 authoritative |
| `P2-3` | CausalEffectEvidence + bounded RecentActionOutcomeIndex | pre-existing state 不冒充 ACTION_CAUSED |
| `P2-4` | CurrentObservation / RecentActionOutcome / DurableEvidenceStore 三层 evidence location | 只有 durable evidence 跨 epoch |
| `P2-5` | Mechanical providers 内化：structural/API/artifact/external | provider 只提取事实与 metadata，不拥有 completion |
| `P2-6` | ModelVerifier / HumanProvider 后置扩展 | 只产 evidence；high-risk external effect 不得 model-only completion |

### P3：TaskSpec v2 稳定授权合同

| ID | 工作项 | 完成门 |
|---|---|---|
| `P3-1` | 冻结 TaskSpec v2 schema 与 TaskSpecAuthority | 只保存 source_envelope_ref/source_binding_digest；Planner 不能修改 accepted meaning |
| `P3-2` | SemanticAudit 保持 risk-triggered veto/clarify-only | 不增加用户效果、修改 success 或授权 |
| `P3-3` | Selective SourceAnchor policy | material fields 精确 anchor；低风险字段允许 whole-request anchor |

### P4：Observation-grounded rolling planning 与严格 StepChoice port

| ID | 工作项 | 完成门 |
|---|---|---|
| `P4-1` | `TaskPlanFlow` 与 `StepChoiceFlow` 物理拆分 | 两种 request/response/authority 不混用 |
| `P4-2` | strict planner 改为 `select(ChoicePlanningRequest)` | 无 BrowserSnapshot/ActionChoiceBuilder/StateKernel 依赖 |
| `P4-3` | full Catalog + ChoicePage + paging/typed retrieval | 未展示 ID 被拒；effectful 截断页遵守唯一授权规则 |
| `P4-4` | request serializer 纯化 | 不重建 task/step/progress/observation authority |

### P5：Fact/Binding/DurableEvidence progress、epoch store 与 legacy deletion

| ID | 工作项 | 完成门 |
|---|---|---|
| `P5-1` | Fact/Binding ledgers + RecentActionOutcomeIndex + DurableEvidenceStore 替代 completed-subgoal/evidence-graph carry-forward | replan 不要求复用旧 step identity；current evidence 不持久化 |
| `P5-2` | ObservationStore + current observation/catalog refs | StateKernel 保存 identity，不承载 presentation 内容 |
| `P5-3` | PostActionObserver → LoopEvaluationPhase → ProgressTransition/RuntimeCommitter | Evaluator 纯求值；只有 Committer 写状态 |
| `P5-4` | 删除/隔离 legacy completion interfaces | `VerifierLadder.verify()` boolean、disabled PASSED、latest-report completion、description matcher、terminal_readiness authority 退出生产 |

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
- 不默认建设独立 verifier service、VerifierPlanner、全量 EvidenceGraph 或无界历史 EvidenceIndex。
- 不让 source-specific provider 类型扩张为 source-specific Criterion 类型组合。

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

approval 必须绑定完整 ActionContract hash 与当前 page revision。任何 re-ground、参数变化、snapshot 变化或 contract rebuild 都要求重新审批。

### 8.7 第 81 个唯一目标与 presentation invariance

唯一合法目标位于旧 top-80 外时仍必须进入 full Catalog。对相同 task/plan/step/progress/canonical observation/capabilities/policy，改变 affordance count、state field、artifact、label 或 context compaction limits 不得改变 `catalog_digest`。

### 8.8 截断 ChoicePage、高风险与多来源冲突

- full Catalog 中存在但当前页未展示的 ID 必须以 `UNPRESENTED_CHOICE_ID` 拒绝；
- effectful/high-risk page 截断且无 deterministic unique authorization match 时必须继续检索或澄清；
- target identity 或 required state material-conflicted 时不得建立/自动选择 executable choice；
- acquisition coverage 不足走 active perception，不能伪装成 target absent 或 model grounding ambiguity。

### 8.9 SourceEnvelope 与选择性审计

- 普通低风险请求只构建 SourceEnvelope，不能因 33 个句子或没有 claim/obligation graph 而 fail；
- recipient、amount、account、file、destructive target 等 material fields 必须绑定合法 SourceAnchor；
- high-risk/multi-source/conflict 触发 SemanticAudit，audit 只能 veto/clarify；
- 页面 observation 不能被提升为用户授权 source；
- TaskSpec 只保存 `source_envelope_ref` 与 `source_binding_digest`。

### 8.10 Loop-native evaluation 与完成权威

- “确保设置 enabled”可由初始 observation 的 `STATE_HOLDS` 无动作完成；
- “把设置从 disabled 切到 enabled”必须有 contract-bound `ACTION_CAUSED`；
- send/delete/payment 等必须 `FINAL_RECHECK + AUTHORITATIVE`，不能 model-only 或 toast-only 完成；
- verification disabled、无 provider/operator、无 evidence 分别产生显式 diagnostic、UNSUPPORTED 或 UNKNOWN，绝不能 PASSED；
- fresh post-action observation 默认可复用，Perception owner 可选择 targeted augmentation、recapture 或 wait-and-recapture。

## 9. 架构验收不变量

1. TaskSpec 只能由 TaskSpecAuthority 创建 revision。
2. Planner 只读 TaskSpec，不得返回其 patch。
3. TaskPlan 的结构必须可随 observation 替换，且不改变 TaskSpec authority。
4. accepted TaskPlan 直接保存完整 StepSpec，无默认 SubgoalSpec round-trip。
5. Step completion criterion 不自动成为 Task completion criterion。
6. `is_available`、`visible` 等 predicate 的角色由容器决定。
7. Runtime full ActionChoiceCatalog 绑定 task/plan revision、state version、canonical observation epoch 与 active step。
8. Planner selection 必须属于当前 Catalog 且属于当前展示的 ChoicePage；未展示 choice ID 即使存在于 Catalog 也必须拒绝。
9. 所有效果动作必须追溯到 TaskSpec allowed-effect reference。
10. Capability ceiling 不等于 capability grant；approval 不等于 capability。
11. Approval 只绑定 concrete ActionContract，且 one-shot。
12. Preflight 失败不得静默重定位并执行旧合同。
13. Receipt success 不等于 effect observed。
14. Effect observed 不等于 step complete。
15. Step/plan complete 不等于 task complete。
16. TaskCompleted 只能来自完整 TaskSpec.success closure + RuntimeCommitter。
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
| `OBS-10` | acquisition truncation 必须表示为 SourceCoverage，不得伪装成 target absence。 |
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
| `SOU-03` | recipient/amount/account/file/external destination/destructive target 等 material fields 优先使用精确 SourceAnchor。 |
| `SOU-04` | ordinary low-risk field 允许绑定 whole-request anchor。 |
| `SOU-05` | SemanticAudit 只由 high-risk/multi-source/conflict/policy trigger 启用。 |
| `SOU-06` | SemanticAudit 只能 pass/veto/clarify，不能添加 effect、修改 success 或授予 capability。 |
| `SOU-07` | TaskSpec 只绑定 source_envelope_ref 与 source_binding_digest，不复制 raw source/claim graph。 |
| `SOU-08` | MinimalIntentProposal 与 TaskSpec 默认不存在 candidate_source_claims/candidate_obligations/source_claims/obligations。 |
| `SOU-09` | Runtime observation/page content 不得被提升为用户 authority source。 |
| `SOU-10` | Trace 默认只记录 source hash/length/ref，不复制 raw request content。 |
| `SOU-11` | 旧 SourceLedger 的 clause/span/coverage 能力只可作为 optional SemanticAudit implementation。 |
| `SOU-12` | TaskPlan 是 observation-grounded milestone graph，不是 intake obligation graph。 |

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
| `SRC-STEP-ROUNDTRIP` | StepSpec/SubgoalSpec 有损往返 | §1.4、§6 P0-4 | DELETE |
| `SRC-EVIDENCE-FIDELITY` | typed evidence 未完整传递 | §1.5、§3.3 | REPAIR |
| `SRC-COMPLETION-AUTHORITY` | Plan completion 与 Task completion 混淆 | §1.6、§9 | REPLACE |
| `SRC-PLAN-AUTHORITY` | Authority 仍主要是 binder | §1.7、§5 | STRENGTHEN |
| `SRC-FAT-TASKSPEC` | TaskSpec 是抽取结果数据库 | §1.8、§3.1 | REPLACE |
| `SRC-CANONICAL-OBSERVATION` | Runtime 不应受模型裁剪空间限制 | §1.9、§6 P0-7 | REORDER |
| `SRC-REQUEST-PROJECTION` | PlanningRequest/PlannerContext 重复投影 | §1.10、§6 P1-1 | FLATTEN |
| `SRC-VALIDITY-CAUSALITY` | evidence validity 与 state/effect 因果区分 | §1.11、§3.3 | ADD |
| `SRC-KEEP-PLAN` | 保留可替换 TaskPlan | §2.1 | KEEP |
| `SRC-TWO-PLANNERS` | Task planning 与 active-step action planning 分离 | §2.2、§5 | ADOPT |
| `SRC-CHOICE-SET` | 保留 Runtime-owned 0/1/N，并升级 full Catalog | §0.1、§2.3 | KEEP + STRENGTHEN |
| `SRC-CONTRACT` | 保留 Proposal → ActionContract | §2.4 | KEEP |
| `SRC-APPROVAL` | 动作附近、状态绑定、单次审批 | §2.5 | KEEP |
| `SRC-INDEPENDENT-VERIFY` | fresh post-action independent verification | §2.6 | KEEP |
| `SRC-GROUNDING-RECOVERY` | 保留 typed grounding、recovery、single writer | §2.7 | KEEP |
| `SRC-SEMANTIC-AST` | value/predicate/boolean/quantified AST | §3.2 | ADD |
| `SRC-NOT-REPAIR` | Planner 不得用 Not 反转已满足目标 | §3.2 | PROHIBIT |
| `SRC-EVIDENCE-LEAF` | CriterionPolicy 附着 criterion leaf | §3.3 | ADOPT |
| `SRC-STEP-BOUNDARY` | Step 按里程碑/依赖/环境/审批/恢复拆分 | §3.4 | ADOPT |
| `SRC-PROGRESS-LEDGER` | TaskProgress 保存事实而非复制 plan | §3.4、§6 P5-1 | ADOPT |
| `SRC-ALREADY-SATISFIED` | 规划前先检查 task success | §4、§8.4 | ADD |
| `SRC-ROLE-OWNERS` | 各模块唯一职责 | §5 | ADOPT |
| `SRC-P0-P5` | 更新后的 P0-A–P0-D、P1–P5 优先级与后置项 | §6 | ADOPT |
| `OP-00`–`OP-08` | 入口、source、intent、semantic、TaskSpec、plan、completion | §0–§6 | COVERED |
| `OP-09`–`OP-15` | observation、context、choice、grounding | §1.9–§2.7、§6 | COVERED |
| `OP-16`–`OP-24` | contract、verification、reuse、closure、recovery、offline evidence | §1.11、§2.4–§2.7、§4–§6 | COVERED |
| `P0-1`–`P0-6` | 原审计 P0 | 按 authority dependency 重排到 §6 P0-A、P1–P3 | COVERED |
| `P1-1`–`P1-5` | 原审计 P1 | 重排到 §6 P4–P5 | COVERED |
| `P2-1`–`P2-5` | 原审计 P2 | 收敛到 §6 P2/P4；开放能力不扩执行权 | COVERED |
| `P3-1`–`P3-3` | 原审计 P3 | 进入 §6 Deferred | COVERED |
| `P0-A`–`P0-D`、`P1`–`P5` | active-step authority 修正后的执行顺序 | §6 | COVERED |
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
| `ACR-14` | post-action canonical epoch 直接复用并列明重捕获条件 | §6 P5-4、§9 | §9.7、§10 | COVERED |
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
| `LOOPVER-08` | CriteriaEvidenceMatcher 退化为 EvidenceAdmissionPolicy | §6 P5-4 | §9.6、§15 | COVERED |
| `LOOPVER-09` | ObservationDisposition 四态与复用/重捕获条件 | §6 P1-5、§9.1 | §9.7 | COVERED |
| `LOOPVER-10` | ModelVerifier evidence-only、high-risk prohibition | §2.7、§6 P2-6 | §9.8 | COVERED |
| `LOOPVER-11` | mechanical verifiers 降为 internal evidence providers | §2.7、§6 P2-5 | §9.9 | COVERED |
| `LOOPVER-12` | 禁用 receipt fallback 与 verification-disabled PASSED | §1.13、§6 P0-A | §14–§17 | COVERED |
| `LOOPVER-13` | typed recovery ownership | §5、§9.3 | §11.1 | COVERED |
| `LOOPVER-14` | 轻量 verification 模块布局与升级条件 | §6、§7 | §15.2 | COVERED |
| `LOOPVER-15` | P0–P3 verification priority | §6 | §15 | COVERED |
| `LOOPVER-16` | VER-01–14、OBS-13–14、REC-01 | §9.1、§9.3 | §17.1 | COVERED |

## 11. 完成状态

| 步骤 | 状态 | 产物或验证 |
|---|---|---|
| 读取引用对话与现有权威文档 | DONE | 引用对话、2026-07-29 权威架构、2026-08-05 修改审计 |
| 核对当前分支关键实现与已知缺口 | DONE | HEAD、obligation audit、Plan/Progress/Completion 路径 |
| 固化完整演进决议与逐条覆盖台账 | DONE | 本文件 |
| 合入 active-step authority 修正 | DONE | `ACR-00`–`ACR-18`、`ACR-FINAL` 与 `OBS-01`–`OBS-12` |
| 合入 SourceEnvelope B+ 与 loop-native verification 修正 | DONE | `BPLUS-00`–`BPLUS-11`、`LOOPVER-00`–`LOOPVER-16`、`SOU-01`–`SOU-12`、`VER-01`–`VER-14`、`OBS-13`–`OBS-14`、`REC-01` |
| 生成权威总图和细节板块 | DONE | 派生权威架构文档，含总图、九个板块、合同、迁移、门禁与逐条映射 |
| 完整性、链接、Mermaid 和事实状态自检 | DONE | 127 项文档/治理测试、Ruff、7 张 Mermaid、4 个相对链接、覆盖 token 与 diff 检查 |

验证使用仓库记录的 dedicated Python 3.12 环境，避免默认 `uv run` 同时求解 BrowserGym Playwright 1.44 与 web extra Playwright 1.61.0 的已知可选依赖冲突。最终结果以本次变更完成前的 fresh verification 输出为准。

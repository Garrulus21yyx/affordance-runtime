# Task Contract 中心化 Runtime 架构演进规划

> **文档类型：** Architecture Evolution Plan / Source-of-Truth Ledger
> **状态：** AUTHORITATIVE EVOLUTION PLAN
> **日期：** 2026-08-05
> **事实基线：** `agent/migrate-runtime-components @ 55bad91e56126269af7453913cf550cb5938108f`
> **最新实现复核：** 2026-08-06 P4-G concrete action authority/high-risk governance 已完成；精确不可变 revision 由 Git 记录。
> **派生目标架构：** [Task Contract 中心化唯一权威目标架构](../specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **历史基线：** [2026-07-29 唯一权威优化目标架构](../specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md)
> **2026-08-05 权威修正：** active-step 链必须先从 canonical observation 建立完整 Runtime `ActionChoiceCatalog`，再投影任何 model-facing request；§10.1 对该修正逐条登记。
> **2026-08-05 Source / Verification 收口：** 默认 intake 改为轻量 `SourceEnvelope + selective SourceAnchor`，细粒度 `SemanticAudit` 按风险启用；verification 改为 loop-native typed `LoopEvaluationPhase`，完成语义仍由 `TaskCompletionEvaluator` 独立求值、只由 `RuntimeCommitter` 提交。§10.2–§10.3 逐条登记两份修正。
> **2026-08-05 Semantic Authority / Contract Closure 补充：** 第一份复核提供 requirement/dependency/choice/output 收口，第二份复核只覆盖其严格 raw-text firewall；最终采用 Task Meaning Write Barrier、bounded `SourceContextView` 与 raw-text-free execution chain。§10.4 登记合并结果。
> **2026-08-05 Physical Minimality 补充：** 复核识别的过重风险按“已覆盖、补充实现约束、明确拒绝”处理；full Catalog、canonical observation、authority、Criterion、Planner 与 optional capability 不得被机械实现成 eager copy、微服务森林或默认多模型链。§10.5 登记处理结果。
> **2026-08-05 Cross-Surface Visibility 补充：** DOM、AX、Visual、SVG、WoT、API 与 Device 显式共享同一 TaskSpec、TaskPlan、Catalog、ActionContract 与 LoopEvaluator；Planner 选择 semantic action，Runtime 在 contract 阶段选择 backend/binding。§10.6 登记处理结果。
> **2026-08-05 Material Binding 纠偏：** exact span 从通用高风险准入门降为间接非结构化来源的 provenance 形式；准入改由 `MaterialBindingPolicy/TaskSpecAuthority` 按 effect 校验 typed material field groups。SemanticAudit 不再以“存在任意一个 material anchor”代替字段完整性。§10.7 登记处理结果。
> **2026-08-06 Concrete Effect Authority / High-risk Governance 纠偏：** `8b91944` 的负向复核发现 operation mismatch、named-parameter swap、unknown DOM risk default-low 与 actual-binding-independent gate；P4-G 已以 typed `EffectAuthorizationScope ⊒ RuntimeEffectSignature → ActionAuthorityProof` 完成替代 cutover，并在进入 P5 前删除 canonical 字符串/复制字段 proof。§10.8 登记处理结果。

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

`SourceEnvelope` 始终存在，只保存全文 identity/version、外部 source refs、caller/conversation identity 与 content digests；不做 clause splitting、dependency parsing、claim/coverage/obligation graph。直接用户明确 material value 使用 typed `DIRECT_USER_EXPLICIT` binding，无须预生成字符 offset；间接非结构化来源使用 field-matched exact excerpt，typed external ingress 使用 versioned field identity。`SemanticAudit` 只能 pass/veto/clarify，不能创建或修改 TaskSpec，也不代替 TaskSpecAuthority 的 effect-specific field coverage gate。

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

### 0.4 Semantic Authority Boundary 与合同闭包补充

“自然语言只理解一次”正式修正为：

```text
single semantic admission
+ bounded contextual rereading
+ no downstream authority expansion
```

只有 `TaskSpecAuthority` 可创建或修订 accepted meaning。`TaskPlanner` 可在里程碑分解确有需要时读取 bounded、read-only、`context_only` 的 `SourceContextView`；`OpenSemanticResolver` 只可读取 typed criterion 精确绑定的 SourceAnchor excerpts；`ClarificationComposer` 只可生成问题。三者的输出必须引用已有 TaskRequirement/Criterion/EffectAuthorization/SourceAnchor IDs，发现缺失语义时返回 `TaskSpecGap` 或 clarification。

ActionChoiceBuilder、Grounder/PredicateResolver、ActionSelectionValidator、ActionContractBuilder、四重 gates、Executor、LoopEvaluator、TaskCompletionEvaluator 与 RuntimeCommitter 不接收 raw request 或 SourceContextView。页面、邮件、PDF、tool output 与 screen text 可用于 grounding/evidence，不能创建用户授权。

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

`Surface.WOT` 与 `WOT_DESCRIPTION / WOT_PROPERTY_STATE / WOT_ACTION_RESULT` 进入规范 vocabulary：Thing Description 只提供 capability/grounding metadata，property state 提供 fresh device-state evidence，action result 只提供 contract-bound receipt/outcome。Planner 只选择 backend-neutral semantic action；`ActionContractBuilder` 才基于 current observation、evidence requirement、capability、risk 与 policy 选择 current backend/binding。

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
    → Catalog → selected choice → actual bound ActionContract
    → Task Gate independently rebuilds proof
    → capability → exact contract approval → fresh preflight
```

它不采用两种错误极端：不让 Planner/label/risk score 猜 permission，也不枚举每个页面、任务或 action combination。系统只冻结少量 safety `EffectClass`、registered/versioned `OperationRef`、canonical resource scope、named parameter binding 与 risk/assurance policy。未知 classification 是 `UNPROVEN`；approval 不能补齐 proof，扩大授权只能创建新 TaskSpec revision。

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
| 来源 identity/version 与 material-field lineage | always-on `SourceEnvelope` + risk-proportionate `MaterialBinding`；exact SourceAnchor 仅为一种 provenance form |
| 高风险/多来源/conflict 的细粒度 coverage audit | optional `SemanticAudit`，veto/clarify only |
| 步骤、依赖、interaction intent、action budget | `TaskPlan<StepSpec>` |
| 已完成状态、facts、bindings、evidence instances | `TaskProgress` 与 append-only ledgers |
| 当前动作、locator、backend、TTL、evaluation requirements | `ActionContract` |
| 未解决 ambiguity | 不准入 TaskSpec，返回 clarification |

### 1.9 Canonical observation 当前先受模型预算裁剪

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
RECENT_ACTION
DURABLE
FINAL_RECHECK
```

assurance 只需 `WEAK / STRUCTURAL / AUTHORITATIVE`。旧证据只有在 `DURABLE` policy 允许且未失效时复用；`RECENT_ACTION` 只允许 `ACTION_CAUSED + causal_lineage_required`，并绑定 current task/ActionContract 的 bounded ActionOutcome。它只证明过去动作造成过效果，不证明当前状态仍成立；当前状态必须由独立的 `STATE_HOLDS + CURRENT_OBSERVATION` leaf 证明。`FINAL_RECHECK` 必须使用最新且 assurance 为 `AUTHORITATIVE` 的权威 recheck。

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

### 1.14 修订前未成文的合同缺口（现已在目标合同补齐）

旧文档已经禁止 strict Planner/Coordinator/recovery/benchmark natural-language fallback，但没有区分“读取 source-bound context”和“写入 accepted meaning”。如果进一步扩张成 TaskSpec 后绝对禁读，会让 OpenSemanticCriterion、里程碑语用与澄清措辞丢失；如果保持无边界读取，又会让 Planner/执行链从 objective/raw text 临时恢复授权。

同时，修订前的 allowed effects、constraints、success 与 requested outputs 可能分别重述同一 material requirement；StepSpec 缺少通用 requirement traceability；ChoicePage 未完整冻结 N-choice 语义展示字段；required output 尚未明确进入 TaskCompleted closure。这些缺口现已由目标合同补齐，但不代表当前代码已完成切换。

### 1.15 逻辑边界被物理化得过重

当前目标主链已消除重复语义图，剩余过重风险主要来自实现方式：全量物化大型 Catalog、复制巨型 observation、每个 owner 建独立服务/数据库、一次性实现全部 criterion provider、每轮重规划，以及所有任务默认启用 SemanticAudit/paging/ModelVerifier/OpenSemanticResolver。

以下风险已由现有合同覆盖：选择性 SourceAnchor、risk-triggered SemanticAudit、bounded evidence 生命周期、ModelVerifier 后置、raw-text 三层边界、ChoicePresentation 与 output closure。以下风险仍需作为实现门：logical Catalog membership 与物化策略分离、observation epoch/index、authority/部署分离、operator/provider coverage 分离、typed replanning trigger 和 risk-derived profile。

### 1.16 `8b91944` 仍是 coarse concrete-action proof

最新 push 已正确移除 keyword token overlap，并让 Runtime 而非 Planner 派生 effectful/risk；但 production proof 仍以 free-form `target_identity/destination_identity`、coarse `operation_class`、无字段 scalar value set 与 source-declared risk 为主，最终 Task Gate 复算的也是从 choice 复制到 contract 的 authority fields，而不是 actual bound grounding candidate。

针对该 revision 的四个独立负向探针均可复现：

| Probe | 当前结果 | 应有结果 |
|---|---|---|
| TaskSpec 为 NAVIGATION，同一 exact target 上构造 TYPE_TEXT | authorized | DENY / operation mismatch |
| admitted `recipient=Alice, amount=100`，choice 交换两个字段值 | authorized | DENY / named parameter mismatch |
| 普通 DOM `<button>Delete account</button>` 无自报 risk | LOW | UNPROVEN 或由 Runtime policy 分类为 destructive |
| contract 复制 Alice proof fields，但 actual `affordance_id/locator` 指向 Bob | Task gate allow | DENY / actual binding mismatch |

因此 P3 requirement traceability 与 P4 closed choice port 可以保持完成，但“concrete action legality/high-risk governance complete”的表述必须撤回。该缺口进入 P4-G corrective closure，不留给 P5 containment，也不允许保留 old proof 作为 fallback/shadow owner。

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

每个 StepSpec 增加 `requirement_refs`；effectful Step 另有 `effect_authorization_refs`。TaskPlanAuthority 拒绝无法追溯到 TaskSpec requirement/effect IDs、且也不是 current observation-grounded enabling need 的 objective/completion/effect。

### 3.7 Dependency 单一落位

- semantic value dependency：`InputRef / BindingRef / ObservationValueRef / ValueExpr`；
- execution milestone ordering：current TaskPlan `StepSpec.depends_on`；
- accepted TaskSpec：不保存 claim/obligation dependency graph。

### 3.8 ChoicePresentation 与 required output closure

每个 `ChoicePresentation` 必须包含 bounded target label/role、destination、relevant current state、requirement/effect refs、evidence refs、conflict、risk 与 generation reason codes；不得包含 selector、coordinate、locator、backend handle、approval token 或 hidden IDs。

每个 required OutputSpec 必须有 stable output ID、typed materialization criterion 与 source-binding policy。TaskCompletionEvaluator 除 success root、constraints、external effects 和 final rechecks 外，还必须证明所有 required outputs materialized，并按声明 source-bound；Planner prose 不能代替 structured output。

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
- Planner selects the semantic action; ActionContractBuilder selects the current backend/binding。
- route 失效时必须 fresh reobserve、rebuild contract；旧 approval/contract 不得跨 route 复用。

### 3.11 Concrete effect authority 与 high-risk contract

Effectful `TaskRequirement.semantic_payload` 内唯一保存 parameterized `EffectAuthorizationScope`：registered/versioned `operation_constraint`、canonical resource/destination scope、named input/binding slots、small safety effect class、externality/reversibility、minimum source assurance 与 risk/approval/completion policy refs。它只表达用户授权 ceiling，不保存 current action kind、backend、candidate、epoch 或 Runtime confidence。`allowed_effect_refs` 继续引用该 requirement ID，不新增 universal effect graph。

Runtime 依据 current canonical target、actual ActionSupport/GroundingCandidate/backend operation/source assertions 生成不同类型的 concrete `RuntimeEffectSignature`，并通过 typed subsumption 得到 tri-state `ActionAuthorityProof`。Runtime risk 取 effect class、externality、reversibility、resource sensitivity、amount/recipient、capability、source uncertainty 与 conflict 的保守最大值；Text/VLM 只能升风险或触发观察/澄清，不能产生 ALLOW、降风险或创建授权。Catalog 只包含 ALLOW；DENY 与 UNPROVEN 分别进入 typed rejection/recovery。ContractBuilder 对最终 route 重新生成 signature，Task Gate 再从 TaskSpec + current observation + actual bound transaction 独立重建带 evaluator-policy version 的 proof。

Planner 只可输出 step objective、interaction intent、requirement/effect authorization refs、completion、dependencies 与 budgets。`StepSpec.effectful` 若仍存在于外部兼容输入，只能作为待删除 hint；Runtime 的 effect、risk、Catalog membership、backend route 与 approval 不读取它，canonical StepSpec 最终不保存该 authority field。

高风险策略采用少量 effect class × effect-specific field/policy matrix；不枚举网站、页面、TaskType 或 GUI action combination。未知 operation/effect/externality/reversibility/risk/assurance fail closed；approval 只批准已授权的 exact contract，并向用户显示 concrete action、resource/destination、named material parameters、reversibility、backend operation、来源与不确定性，不能代替 TaskSpec revision。uncertain external effect 不盲重试，完成需要 policy 要求的 causal outcome 与 authoritative final recheck。

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
    → ActionContractBuilder
    → Task Authority ∩ Capability ∩ Approval ∩ Freshness/Preflight
    → Execute
    → ExecutionReceipt
    → fresh post-action UnifiedObservation
    → inline LoopEvaluationPhase
        → Action Effect Evaluation
        → Step Completion Evaluation
        → triggered Task Completion Evaluation against TaskSpec.success + required outputs
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
| `PerceptionSession` | source capture policy | immutable PerceptionCapture + SourceCoverage | 声称未采集内容不存在 |
| `CanonicalObservationBuilder` | PerceptionCapture | canonical UnifiedObservation | 读取 model presentation policy、修改 TaskSpec/progress |
| `ObservationStore` | canonical observation | immutable ObservationRef | 向 Planner 暴露 store handle |
| `TaskPlanner` | TaskPlanningRequest + optional SourceContextView | PlanProposal / TaskSpecGap | 修改 TaskSpec、创建 requirement、输出 concrete action |
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
| `OpenSemanticResolver` | typed OpenSemanticCriterion + exact linked excerpts + current targets | typed resolution/evidence/gap | 修改 TaskSpec、读取 unrestricted source/page text、授予 effect |
| `ClarificationComposer` | typed ambiguity/gap + exact linked excerpts | user question | 修改 TaskSpec 或 action plan |
| `TaskCompletionEvaluator` | TaskSpec.success + required outputs + constraints + admitted evidence | TaskCompletionEvaluation | 根据 plan exhausted/reward/prose 自行通过、写 StateKernel |
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
| `P0-A` | TaskCompletionEvaluator 递归求完整 TaskSpec.success + required OutputSpec closure；禁用无 spec receipt fallback 与 verification-disabled PASSED | criterion/evidence compatibility foundation | latest report、receipt、plan exhausted、Planner Finish/prose 均不能单独完成 task；required output 未 materialize/source-bind 时不得完成；无 evidence 为 UNKNOWN |
| `P0-B` | `PerceptionCapture → CanonicalObservationBuilder → UnifiedObservation` 先于所有 presentation；显式统一 DOM/AX/Visual/SVG/WoT/API/Device | 可与 P0-A 并行 | production 无 `from_planner_observation`；所有 surface 的 coverage/conflict/bindings 保真 |
| `P0-C` | 将 ActionChoiceBuilder 移出 GeneralistLMPlanner，先建 surface-neutral logical full Catalog 再建 ChoicePage；允许 eager/lazy/indexed membership | P0-B | presentation/materialization limits 与 backend preference 不进入 semantic membership；同一 canonical inputs 得到相同 count/membership/order/digest |
| `P0-D` | 写第 81 个目标、12-field state、artifact/label/context limit、conflict、multi-binding、raw-text execution read-set、TaskSpecGap、output closure 与 physical-minimality 回归红线 | P0-A/B/C 同阶段 | presentation 不改变 Catalog；execution path 无 raw/SourceContextView；语义缺口不静默扩权；lazy/index layout 不改变 semantics |
| `P0-E` | SourceEnvelope 成为 default source path；普通 intake 不建 clause/claim/obligation graph；material admission 使用 effect-specific typed binding coverage | 可与 P0-A 并行 | SourceLedger clause bound 不再阻塞普通任务；direct explicit 不要求 span；indirect source/page authority/缺失字段按 typed policy 拒绝或澄清；TaskSpec 使用 envelope ref + binding digest |

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

### P4-G：Concrete Action Authority / High-risk corrective closure

P4-G 是 P5 前的阻塞性替代迁移，不是新旧并行平台。`P4-G1`–`P4-G6` 已在同一 cutover 中完成；canonical owner 已切换，字符串/Boolean proof fallback 已删除。

| ID | 工作项 | 完成门 |
|---|---|---|
| `P4-G1` | 在 focused `effect_authority_contracts.py` 定义互不混用的 `EffectAuthorizationScope`、`RuntimeEffectSignature`、ResourceScopeRef、named ParameterAuthorization、Externality/Reversibility 与带 evaluator-policy version 的 tri-state ActionAuthorityProof；TaskSpecAuthority 只准入前者 | 不新增 effect graph/TaskType；不保留 `operation_class + label + scalar set` 作为 authorization fallback；TaskSpec 不保存 current backend/action/binding |
| `P4-G2` | DOM/AX/Visual/SVG/WoT/API/Device adapter assertions 经 pure Runtime classifier/risk policy 汇入 concrete signature；risk 是 effect/externality/reversibility/resource/amount-recipient/capability/source uncertainty/conflict 的保守最大值 | source 未自报 risk 不再默认证明 LOW；unknown/material conflict/coverage insufficient 为 UNPROVEN；Text/VLM 只能升风险或触发观察/澄清 |
| `P4-G3` | ActionChoiceBuilder 以 `EffectAuthorizationScope ⊒ RuntimeEffectSignature` typed subsumption 建 Catalog，保留 ALLOW proof 并区分 DENY/UNPROVEN；safe enabling 仅含 requirement-bound observe/focus/hover/scroll/non-commit menu/allowed-domain navigation/wait/local reversible draft | operation mismatch、named-parameter swap、label-only identity、source-assurance shortage、external commit、unauthorized disclosure 与 UNKNOWN effect 均不能进入 Catalog |
| `P4-G4` | ContractBuilder 以 actual candidate/backend/binding 重建 route-specific signature；ActionContract hash 密封 scope/signature/proof-policy/binding；Task Gate 从 TaskSpec/current observation/actual transaction 独立重建 proof；approval 展示并绑定 resource/destination/material parameters/reversibility/backend/source uncertainty | copied label/digest + wrong affordance/locator 必须拒绝；approval/capability 不能覆盖 UNPROVEN；route/parameter/classification/epoch 变化需新 contract/token |
| `P4-G5` | 接通 risk × source-assurance 与 high-risk effect-policy matrix、exact-contract single-attempt/idempotency/transaction identity、uncertain-effect recovery、causal + authoritative final-recheck closure | send/share/payment/purchase/delete/account-security/device actuation 满足 effect-specific material/assurance/approval/preflight/evaluation policy；Visual/VLM 可定位但不能单独授权/完成 high-risk；authoritative provider 保存真实 observed state；ambiguous dispatch 不盲重试或换 backend 重放 |
| `P4-G6` | 删除旧 matcher/Boolean scope proof/Planner risk-effect fields的 authority 用途；拆分 oversized Catalog builder；同步 status/evidence | production 无 old↔new projector、dual read/shadow fallback；最小矩阵覆盖低风险 read/navigation、高风险 API/WoT transaction、unknown/uncertain effect 纵向链及 mismatch/parameter/assurance/token invalidation；无独立测试项目 |

### P5：Fact/Binding/DurableEvidence progress、epoch store 与 legacy deletion

| ID | 工作项 | 完成门 |
|---|---|---|
| `P5-1` | 轻量 RunLedger 物理承载 Fact/Binding/RecentActionOutcome/DurableEvidence namespaces，替代 completed-subgoal/evidence-graph carry-forward | namespace 生命周期保持独立；replan 不要求复用旧 step identity；current evidence 不持久化 |
| `P5-2` | ObservationStore + immutable epoch/index + current observation/catalog refs | StateKernel 保存 identity，不承载 presentation 内容；consumer 不复制完整 canonical graph |
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
9. 所有 Step 必须追溯到 TaskSpec requirement reference；效果动作还必须追溯到 allowed-effect reference。
10. Capability ceiling 不等于 capability grant；approval 不等于 capability。
11. Approval 只绑定 concrete ActionContract，且 one-shot。
12. Preflight 失败不得静默重定位并执行旧合同。
13. Receipt success 不等于 effect observed。
14. Effect observed 不等于 step complete。
15. Step/plan complete 不等于 task complete。
16. TaskCompleted 只能来自完整 TaskSpec.success + required-output closure + RuntimeCommitter。
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
| `REQ-05` | TaskPlanAuthority 拒绝无 TaskSpec traceability 或 observation-grounded enabling need 的 Step semantics。 |
| `DEP-01` | Semantic value dependency 只用 typed input/binding/value refs。 |
| `DEP-02` | Execution ordering 只用 StepSpec.depends_on。 |
| `DEP-03` | Accepted TaskSpec 无 claim/obligation dependency graph。 |
| `CHOICE-13` | Presented choice 包含 target/state/requirement/effect/conflict/risk/reason，且无 binding/hidden ID。 |
| `OUT-01` | Required OutputSpec 有 stable ID 与 typed materialization criterion。 |
| `OUT-02` | TaskCompleted 要求 required outputs materialized，并按 policy source-bound。 |
| `OUT-03` | Planner prose 不替代 structured output。 |

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
| `SURFACE-03` | Planner selects the semantic action; ActionContractBuilder selects the current backend/binding，并将 route 绑定 current observation、evidence requirement、capability、risk 与 policy。 |

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
| `AUTHZ-08` | Contract hash 绑定 scope、route-specific signature、proof/evaluator-policy version、binding、named parameters、externality/reversibility、risk/assurance/epoch。 |
| `AUTHZ-09` | Task Gate 从 actual bound transaction 独立重建 proof，不复算复制字段。 |
| `AUTHZ-10` | Approval/capability 不能扩大 TaskSpec 或把 UNPROVEN 升为 ALLOW。 |
| `HRA-01` | 高风险 effect 进入 execute 前同时满足 material fields、source assurance、capability、exact approval 与 fresh preflight。 |
| `HRA-02` | uncertain external effect 不盲重试。 |
| `HRA-03` | 高风险完成需要 contract-bound causality 与 policy-required authoritative FINAL_RECHECK。 |

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
| semantic action 与 backend route 分离 | Planner 选 semantic action；ActionContractBuilder 选 current binding/backend | §3.10、§5、§9.6 | §7、§10.4–§10.5、§17.1 | ADOPT INVARIANT |
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
| `CEA-05` | Contract/Gate 独立复核 actual binding；approval 不能补 authority | §6 P4-G4、§9.7 | §8.1–§8.3、§17.1 | REQUIRED |
| `CEA-06` | high-risk effect-specific pre/post policy、uncertain effect no retry | §6 P4-G5、§9.7 | §8.4、§9、§11、§17.1 | REQUIRED |
| `CEA-07` | 不陷入页面/任务枚举；small EffectClass + extensible OperationRef + named parameters | §0.7、§3.11、§7 | §4.6.1、§7.2.1、§16 | REQUIRED |
| `CEA-08` | 不新增 god file/test project；Catalog builder 拆分，复用小型 redline matrix | §6 P4-G6、§7 | §15–§17 | REQUIRED |
| `CEA-09` | Runtime risk 取多维保守最大值；Text/VLM 只能 raise-only，不能 ALLOW、降风险或创建 scope | §3.11、§6 P4-G2、§9.7 | §0.1、§7.2.1、§17.1 | REQUIRED |
| `CEA-10` | EnablingActionPolicy 明确允许集与 local reversible draft 边界，禁止 external commit/unauthorized disclosure/UNKNOWN effect | §6 P4-G3、§9.7 | §7.2.1、§17.1 | REQUIRED |
| `CEA-11` | approval 向用户展示并绑定 reversibility、backend operation、sources/uncertainty；任何 route/parameter/classification 变化使 token 失效 | §3.11、§6 P4-G4、§9.7 | §8.1–§8.3、§17.1 | REQUIRED |
| `CEA-12` | proof 绑定 evaluator policy version；risk × source-assurance matrix 决定 high-risk execute/final evidence floor | §6 P4-G1/G4/G5、§9.7 | §7.2.1、§8.4、§17.1 | REQUIRED |
| `CEA-13` | 最小行为矩阵覆盖 low-risk read/navigation、high-risk API/WoT、unknown/uncertain effect 与 mismatch/parameter/assurance/token invalidation，不建设测试平台 | §6 P4-G6、§7 | §8.4、§17.1 | REQUIRED |
| `CEA-14` | 审计建议把 P3-2/P4-4 整行回退 partial | 两行只分别证明 requirement traceability 与 pure presentation/selection，保持 COMPLETE；独立 P4-G 已完成 concrete action legality 闭包 | §6 P4-G、§9.7 | IMPLEMENTED |

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
| 合入 Concrete Effect Authority / High-risk Governance 目标与实施门 | DONE (IMPLEMENTED) | `AUTHZ-01`–`AUTHZ-10`、`HRA-01`–`HRA-03`、P4-G1–G6；typed production closure 已 cut over |
| 生成权威总图和细节板块 | DONE | 派生权威架构文档，含总图、九个板块、合同、迁移、门禁与逐条映射 |
| 完整性、链接和事实状态自检 | DONE | P4-G final review：`930 passed`，Ruff 与 `git diff --check` 通过；epoch/binding/coverage/enabling/uncertain-effect redline matrix 全绿 |

验证使用仓库记录的 dedicated Python 3.12 环境，避免默认 `uv run` 同时求解 BrowserGym Playwright 1.44 与 web extra Playwright 1.61.0 的已知可选依赖冲突。最终结果以本次变更完成前的 fresh verification 输出为准。

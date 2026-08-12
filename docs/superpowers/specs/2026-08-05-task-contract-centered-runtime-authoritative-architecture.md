# Affordance Runtime：AgentContext 循环式 E2E Agent 目标架构

> **Lifecycle:** CURRENT AUTHORITATIVE ARCHITECTURE
> **Updated:** 2026-08-11
> **Scope:** target semantics and invariants only
> **Implementation truth:** [Implementation Status](../../implementation-status.md)
> **Migration order:** [Architecture Evolution Plan](../plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

文件路径仅为兼容文档治理检查而保留；文件名中的
`task-contract-centered` 不再描述当前架构。本文是唯一目标语义权威，但实现状态
仍以 Implementation Status 为准：AgentContext、model policy 与 declared-minimum
criterion adjudicator 与 independent observation acquisition 已在 non-default 路径
落地。本文只定义 control/failure 的目标不变量，不覆盖 Implementation Status：
当前 M4.5-B 已集成但处于 reopened convergence review，尚未 verified closure；
长程 verified frontier 尚未落地。

## 0. 系统定位与计算模型

Affordance Runtime 是面向 GUI、Web、桌面、设备和工具环境的统一 E2E Agent
Runtime。核心不是状态事务，而是理解任务、有效观察、生成当前合法语义动作、
由 Agent 提议、由 Runtime 裁决和绑定、执行一次、重新观察并独立验证。

```text
AgentDecision_t = AgentPolicy(AgentContext_t)
ControlTransition_t = RuntimeApply(AgentLoopState_t, AgentDecision_t)

AgentDecision
→ Runtime validation
→ action branch: BoundActionRequest → execute once
                 → ExecutionOutcome(ActionResult, typed post-action acquisition)
                 → fresh WorldObservation → validated evaluations
  control branch: typed capture/page/user/wait/done/abort consequence
→ exactly one bounded ControlTransition
→ serial AgentLoopState update
```

`AgentContext_t` 是 TaskGoal、bounded IntentContext、current WorldObservation、
progress、Internal ActionSpace、bounded history、pending state 和 budgets 的一次性
投影。统一的是模型每轮看到的上下文，不是 Runtime authority。

## 1. 架构定律

1. **模型可见性不等于执行权。** Visible to model、authorized effect、executable
   route 和 verified fact 是四个不同概念。
2. **Observation 是当前 binding 的事实来源。** TaskGoal 是稳定语义，TaskPlan
   是可替换假设，WorldObservation 是当前世界事实，AgentLoopState 是当前 run control
   state，ControlTransition 只回答本次 control boundary 发生了什么。
3. **Agent 提议，Runtime 裁决。** Agent 选择 subgoal/semantic action、请求观察、
   询问、等待或建议完成；Runtime 独占 membership、binding、currentness、risk、
   confirmation、dispatch truth、evidence validation 和 task closure。
4. **Context disposable。** 每轮重建，可裁剪、分页、压缩或丢弃；不能反向成为
   Runtime state、CognitiveMap、StateKernel 或 universal provenance graph。
5. **Environment content may influence reasoning; it cannot grant authority.** 页面、
   邮件、截图和工具文本不能修改 TaskGoal、扩大 effect、降低 risk、创建合法动作
   或证明完成。

## 2. 顶层分层与 Runtime authoritative state

```text
Thin Semantic Intake
  UserRequest → TaskGoal + bounded IntentContext
        ↓
Runtime Authoritative State
  TaskGoal/revision · WorldObservation · Internal ActionSpace · AgentLoopState
  optional VerifiedTaskState
  PendingConfirmation/Question/UnknownEffect · validated evaluations
        ↓ one-way projection
Disposable AgentContext
        ↓
AgentPolicy → typed AgentDecision
        ↓ Runtime validation
RiskPolicy / semantic confirmation / current binding / execute once
        ↓
typed fresh acquisition / ActionEvaluationValidator / TaskEvaluationValidator
```

Runtime authoritative state 仅包括：`TaskGoal`、task revision、current
`WorldObservation`、current Internal `ActionSpace`、`AgentLoopState`、
以及其 optional nested `VerifiedTaskState` frontier、
`PendingConfirmation`、`PendingUserQuestion`、`PendingUnknownRequest`、current
`BoundActionRequest`、`ActionResult` 和 validated evaluations。

```python
@dataclass
class AgentLoopState:
    current_observation: WorldObservation
    recent_control_transitions: tuple[ControlTransition, ...]
    control_transition_count: int
    task_plan: TaskPlan | None
    verified_task_state: VerifiedTaskState | None
    active_objective: LocalObjective | None
    pending_confirmation: ConfirmationRequest | None
    pending_user_question: UserQuestion | None
    pending_unknown_request: BoundActionRequest | None
    task_revision: int
    progress_revision: int
    pending_revision: int
    remaining_turns: int
    remaining_observations: int
    final_result: object | None
```

它是当前 run 唯一顶层 state aggregate/control authority；nested
`VerifiedTaskState` 只专管 long-horizon frontier。`recent_control_transitions` 只是
bounded suffix；`control_transition_count` 保留准确总数。它不保存全量 observation
历史、event DAG、recovery transaction、delta log、provider token registry、durable
checkpoint 或 global approval store，也不从 transition replay 重建自身。

### 2.1 World acquisition boundary

Acquisition lifecycle capability 与已取得 evidence 的 modality/assurance 是两套概念。
前者回答 backend 能否再次读取或随 action 返回 observation；后者回答某个已取得
WorldObservation 能证明什么。任何 source assurance 都不能凭空创造 acquisition
capability，capability 为 true 也不保证本次 acquisition 成功。

```python
@dataclass(frozen=True)
class ObservationCapabilities:
    independent_capture: bool
    post_action_observation: bool
    offers: tuple[ObservationOffer, ...] = ()

@dataclass(frozen=True)
class ObservationAcquisition:
    status: AcquisitionStatus  # ACQUIRED | CAPABILITY_UNAVAILABLE | FAILED
    origin: AcquisitionOrigin  # RESET | INDEPENDENT_CAPTURE | POST_ACTION
    observation: WorldObservation | None
    reason_code: str

@dataclass(frozen=True)
class ExecutionOutcome:
    result: ActionResult
    post_acquisition: ObservationAcquisition

class WorldEnvironment(Protocol):
    observation_capabilities: ObservationCapabilities
    async def reset(self, task: TaskGoal) -> ObservationAcquisition: ...
    async def capture(
        self, request: WorldObservationRequest
    ) -> ObservationAcquisition: ...
    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome: ...
```

成功 reset 必须交付 initial `ACQUIRED` observation；因此只有 reset/step snapshot 的
backend 也能启动，而不必谎报 independent capture。`capture()` 在类型层面是 total
operation：不支持时返回 typed `CAPABILITY_UNAVAILABLE`，支持但失败时返回 typed
`FAILED`，不能用裸 `RuntimeError` 表达预期能力边界。`offers` 可进一步按 source、
modality、assurance 和 cost 限定能力；两个 aggregate boolean 只是最小 adapter-level
合同，不把所有 surface 假装成同一种传感器。

多 source 的 `WorldEnvironment` 必须把 acquisition-source selection、world fusion 和
model-presentation selection 分开。`ObservationOrchestrator` 根据 typed request、预先
声明的 offers、coverage/conflict/evidence gap 与 bounded cost 选择 reuse/select/augment/
recapture；模型只能请求公开 modality/assurance/subject，不能指定 backend 或 private
route。`WorldFusion` 保留 source-local identity/revision/provenance，将可信 correspondence
映射为一个 canonical world entity，并显式返回 conflict、reobserve 或 inconclusive；
它不执行动作，也不把同一 raw capture 派生的 AX/screenshot/visual view 当作独立确认。
未选择、失败、截断、陈旧与有覆盖的缺失保持不同状态。普通实现不得把“观察所有 adapter
并拼接 tuple”宣称为完成 fusion。

BrowserGym visual binding 只在显式配置 bounded region proposer 时声明 `visual/weak`
offer。该 offer 只表示能力可用，不构成调用证据。每次 acquisition 先取得 structural
observation；Runtime 再根据当前 typed coverage/action/ambiguity/postcondition gap，或公开
`RequestObservation(visual, weak)`，独立决定 `SKIP / VERIFY_STRUCTURED_CANDIDATES /
DISCOVER_VISUAL_ENTITIES / DIAGNOSE_POSTCONDITION / UNAVAILABLE`。provider presence、先前
visual 成功和 benchmark/task identity 不得触发本帧 visual。选择 visual 时，Runtime 使用
structural required + visual optional，并让二者共享一次 raw capture 和 acquisition root。

DOM/AX bbox 生成的 SoM mark 直接保留同一 DOM identity。外部 proposer 产生的 region 先是
source-local observed entity，再以 current shared acquisition 内的显式
`EntityCorrespondence` 合并：唯一匹配的 visual entity 映射到 DOM canonical target，且
不得保留 coordinate binding；明确 unmatched 的 current visual-only entity 才可为支持的
`point_activate` 创建 private `VisualRegionBinding` 和 public `ActionBinding`。ambiguous、
conflicting、stale、unsupported 或 low-confidence region 只可观察。所有 binding 仍经
`WorldFusion -> ActionSpace -> admission -> RouteSelector`；SoM、截图、correspondence 或
observed region 自身不创建执行权。

Vision provider role 必须分离：open-world discovery 可由 OmniParser-compatible
`VisualRegionProposerPort` 返回 observation-only regions；DOM candidate verification
由 bounded SoM/E-ref disambiguator 返回一个 supplied E-ref 或 `null`，类型上不能返回坐标；
visual-only point 由独立 `VisualGrounderPort` 完成，当前默认实现为 GLM。默认启用 point
不得隐式启用 GLM region proposer；region proposer 必须显式配置。ShowUI/GUI-Actor 未来只能
替换 point port，任何 provider 都不拥有 gate、correspondence、fusion 或 execution authority。

视觉 route 的 bbox、point、screenshot identity 和 viewport 仅在 private binding 中；公开
binding payload 和 model intent 不含坐标。dispatch 前必须重新读取当前截图，并同时验证
world epoch、page、episode、exact screenshot digest/dimensions/viewport；任一不一致返回 typed
`STALE_BINDING` 且 zero dispatch，probe 不可用返回 `CURRENTNESS_UNAVAILABLE`。只有验证后的
整数点可编码为 BrowserGym `mouse_click`。optional visual acquisition 失败保留 sufficient
structural world 并报告 typed gap；unsupported primitive 只可观察，不产生 ActionOption。

正常 action path 直接消费 `execute()` 返回的 post-action acquisition。只有
RequestObservation、Wait、stale/currentness recovery、confirmation refresh，或
execute 未提供 after observation 时，Runtime 才在 capability 允许下调用
`capture()`。如果两条路径都不能取得 evaluator 所需的新鲜证据，Runtime 返回 typed
unsupported/failure 或进入既有 UNKNOWN control policy；它不得伪造 freshness。

## 3. Thin Semantic Intake

### 3.1 TaskGoal

```python
@dataclass(frozen=True)
class TaskGoal:
    task_id: str
    instruction: str
    constraints: tuple[str, ...]
    allowed_effects: tuple[str, ...]
    forbidden_effects: tuple[str, ...]
    inputs: Mapping[str, object]
    success_criteria: tuple[SuccessCriterion, ...]
    requested_outputs: tuple[str, ...]
    risk_profile: RiskProfile
    material_bindings: tuple[MaterialBinding, ...]
    loop_budget: LoopBudget
    evaluation_spec: EvaluationSpec | None
```

TaskGoal 不包含页面、selector、坐标、surface、backend、route、GUI 操作顺序、
concrete TaskPlan、binding 或 provider object。

### 3.2 Bounded IntentContext

```python
@dataclass(frozen=True)
class IntentExcerpt:
    text: str
    source_kind: IntentSourceKind
    source_ref: str
    digest: str

@dataclass(frozen=True)
class IntentContextView:
    request_text: str | None
    relevant_excerpts: tuple[IntentExcerpt, ...]
    authority: Literal["context_only"] = "context_only"
    truncated: bool = False
```

优先级固定为：current TaskGoal revision > admitted user clarification >
IntentContext > environment/page/tool content。改变任务语义的 clarification 必须先
validation，再生成新 TaskGoal revision、递增 `task_revision` 并重建 AgentContext；
不能只追加聊天历史来扩大 effect boundary。

## 4. Disposable AgentContext

```python
@dataclass(frozen=True)
class ContextIdentity:
    task_revision: int
    observation_id: str
    action_space_id: str
    action_page_id: str
    progress_revision: int
    pending_revision: int
    context_generation: int

@dataclass(frozen=True)
class AgentContext:
    context_id: str
    task: AgentTaskView
    intent: IntentContextView | None
    progress: AgentProgressView
    world: ModelWorldView
    actions: AgentActionPageView | None
    history: tuple[AgentTurnView, ...]
    control_feedback: AgentControlFeedbackView | None
    pending: AgentPendingView
    budgets: AgentBudgetView
    decision_mode: DecisionMode
```

模型只看到内部 `ContextIdentity` 的 opaque stable digest `context_id`。所有
AgentDecision 都必须携带它。任何不等于 current context ID 的 decision 都执行零次，
被丢弃后基于 current state 重建 AgentContext。

### 4.1 Context 分区

- `AgentTaskView`：公开 task ID、instruction、constraints、effect boundary、inputs、
  criteria/output/risk 摘要；不含 private route、credential、evaluator object。
- `AgentProgressView`：active objective、milestones、evidence-linked current facts、
  unresolved evidence obligations；只有 VerifiedTaskState 中经 validated evidence
  promotion 的 frontier 才是 verified progress，模型 reflection 永远不是。
- `ModelWorldView`：bounded targets/facts/conflicts、truthful coverage 和 available
  observation modalities；不暴露 selector、coordinate、href、credential 或 route handle。
- `AgentTurnView`：只保留 decision kind、semantic action、bounded public parameters、
  dispatch/evaluation status 和短 reason。
- `AgentControlFeedbackView`：只投影最近一次 canonical control feedback 的公开错误类别、
  reason code、公开 subject/invalid-field 摘要、next-decision disposition 和
  `strategy_transition_required`；它不是第二份 Runtime truth，也不包含 raw exception、
  private binding、selector、native value 或 backend payload。
- `AgentPendingView`：只给 waiting/question/confirmation/uncertain-effect 摘要；不暴露
  private BoundActionRequest。

### 4.2 Source assurance

每个 model-visible source summary 明确：

```text
modality: structural | visual | environment_state | artifact | user
assurance: weak | structural | authoritative
coverage: complete | bounded | unknown | failed
freshness: current | aging | unknown
verification_strength: none | visual | structural | authoritative
acquisition_cost: low | medium | high
conflict_status: clear | inconclusive | material_conflict
debug_source: optional DOM/Visual/WoT label
```

`debug_source` 不决定可信度；observation assurance 不等于 execution authorization。
authoritative API read 不自动授予 API write。

每个 source 可选携带一个 profile-relative `SemanticInventorySummary`：
`recognized_target_count = projected_target_count + omitted_target_count`，且
`projected_target_count = actionable_target_count + non_executable_target_count`；
`informational_target_count` 只是 non-executable 子集。`UNASSESSED` 表示 adapter
没有安全完成评估，`EMPTY` 只表示该明确 profile 未识别 target-like unit，
`REPRESENTED` 表示 recognized 全部投影，`PARTIAL` 表示存在 recognized omission。
它与 projection `CoverageState` 正交，不是页面完整性、task requirement coverage 或
ActionSpace availability。模型 source wire 只携带 `projection_coverage` 和上述
privacy-safe counts；BID、selector、native option value、private route、raw role
distribution 不得投影。

### 4.3 Projection budgets

`ContextProjectionBudget` 至少限制 intent excerpts/chars、targets、facts、每 target
facts/relations、conflicts、action options、每 option destinations、history turns、
artifact summaries 和 total serialized bytes。每个 bounded section 必须携带
`items`、`total_count`、`truncated`，明确区分“没有更多”与“只展示部分”。

## 5. Internal ActionSpace、relevance 与 paging

构建顺序是：current WorldObservation bindings → currentness/availability → TaskGoal
legality → effect/risk classification → LocalObjective relevance → distinguishability →
ranking → paging → model projection。

TaskGoal 决定 legality、allowed/forbidden effects、read-only boundary、risk floor、
outputs 和 completion boundary。LocalObjective 仅以 `DIRECT / ENABLING /
INFORMATION / OTHER` 改变 relevance、ranking 和 paging，不能新增 effect、降低 risk、
创造 capability、修复 stale binding 或宣告 milestone 完成。

Internal ActionSpace 保留所有合法 action；模型只得到 current `AgentActionPageView`：

```python
@dataclass(frozen=True)
class AgentActionPageView:
    options: tuple[AgentActionOptionView, ...]
    total_count: int
    page_size: int
    truncated: bool
    has_more: bool
    available_filters: tuple[ActionFilterView, ...]
```

模型只能选择当前页的 `action_id`。不同 effect、destination、material parameter、
risk、consequence 或 reversibility 必须在模型投影中可区分，否则合并为同一语义
option 或补足差异。

Route 只改变实现且 action/target/destination/effect/risk/confirmation subject 相同时，
可作为一个 option 的多个 private bindings；route 改变 effect、externality、data
access 或 verification semantics 时必须成为不同 semantic option，不能作为普通 fallback。
`RouteSelector` 从一个 exact eligible-binding group 中选择一个 current private route；
`ActionBinder` 不再兼任 route policy。只有 typed `NOT_SENT` 且 fresh world 重取、融合与
semantic selection 重验证后，才可在同一 accepted decision 的 bounded continuation 中选择
一个 equivalent alternate，并保持最多一次 effectful dispatch。`SENT`、`SENT_UNKNOWN`
或 send semantics 不明的 failure 禁止 alternate execution。

## 6. Typed AgentDecision

```python
class AgentPolicy(Protocol):
    async def decide(self, context: AgentContext) -> AgentDecision: ...

AgentDecision = (
    SelectAction | RequestObservation | RequestActionPage |
    AskUser | ProposeDone | Wait | Abort
)
```

所有 variant 含 `context_id`：

- `SelectAction(action_id, parameters, destination_id)`；不得返回 selector、coordinate、
  bbox、href、backend、executor 或 credential。
- `RequestObservation(subject_id, modality, required_assurance, reason)`；Runtime 先按
  observation capabilities 选择 DOM/AX/Visual/WoT/API/provider；没有合格 independent
  capture 时产生 typed unavailable control result，不抛裸异常。
- `RequestActionPage(query, target_id, relevance_role)`；新 page 产生新 page/context ID，
  旧 decision 自动 stale。
- `AskUser(question, requested_fields)`；改变任务语义的回答必须产生 TaskGoal revision。
- `ProposeDone(claimed_criteria, evidence_refs, result_summary, unresolved_items)`；仅是建议。
- `Wait(reason, max_wait_ms)`；实际等待后请求 capability-admitted capture；不支持/失败 typed。
- `Abort(reason, category)`；不声称成功。

`ProposeTaskPlan`/`ReplaceTaskPlan` 延后到 long-horizon；不建立 `ProposeRecovery`
taxonomy，恢复用上述 observation/action/user/wait/plan/abort 表达。

## 7. Semantic confirmation

ConfirmationSubjectIdentity 是可跨 fresh private rebind 的稳定语义身份；
BoundActionRequestIdentity 是 current-observation 级、私有、短生命周期且一次性。

```python
@dataclass(frozen=True)
class ConfirmationSubject:
    action_kind: str
    semantic_target_id: str
    semantic_destination_id: str | None
    material_parameters: tuple[tuple[str, object], ...]
    effects: tuple[str, ...]
    effective_risk: ActionRisk
    consequence_class: str
    reversibility: str
```

Subject 不含 selector、coordinate、bbox、href、method、binding/option/observation ID、
screenshot/TD digest 或 backend。确认后必须 capability-admitted fresh capture、重建 ActionSpace/subject、
比较 semantic coverage、绑定 current private route，再执行一次；禁止执行旧 request。

目标 reuse 使用 semantic dominance：action/target/destination/material parameters exact；
current effects 是 confirmed effects 子集；current risk 不高于 confirmed risk；
consequence 不更强；reversibility 不更差。无法比较或语义扩大必须重新确认。
正式偏序实现前，exact subject equality 是安全的保守实现状态，不是最终唯一目标。

`NOT_SENT` 不消费确认，可 fresh rebind；`SENT`/`SENT_UNKNOWN` 消费；`DENY`
清除并取消。不建设 approval registry 或 token store。

## 8. Execution boundary

```python
@dataclass(frozen=True)
class BoundActionRequest:
    request_id: str
    context_id: str
    world_observation_id: str
    intent: ActionIntent
    selection: AdmittedActionSelection
    binding: ActionBinding
    timeout_ms: int
```

执行前验证 current context/observation、current ActionSpace membership、eligible
binding group、destination membership、schema、effect/risk consistency 和 currentness。
`ActionResult` dispatch status 只有 `NOT_SENT / SENT / SENT_UNKNOWN`；result/receipt
success 不等于 effect confirmed 或 task complete，`SENT_UNKNOWN` 永不自动 replay。
`ExecutionOutcome.post_acquisition` 明确区分 acquired、unsupported 和 failed，不能用
`WorldObservation | None` 把能力缺失与采集失败压成同一种情况。dispatch truth 先于且
独立于 after-acquisition：一次已发送但回执不确定的 action 不能因后续 capture 失败被
降格为 `NOT_SENT`，也不能被重放。

### 8.1 Lossless control-transition boundary

`ControlTransition` 是 decision-scoped、run-scoped、in-memory、immutable 且 bounded
的 control accounting value：它保留本次被接受的决策经过 admission、execution/
acquisition、evaluation、progress 和 pending/terminal control 后发生了什么。它不保留
private binding/payload，也不要求原始 provider response 或 observation body。

```python
@dataclass(frozen=True)
class ControlTransition:
    transition_id: str
    sequence: int
    before_observation_id: str
    decision: AgentDecision
    admission: AdmissionSummary | None
    execution: ExecutionSummary | None
    execution_attempts: tuple[ExecutionSummary, ...]
    acquisition: AcquisitionSummary | None
    acquisition_attempts: tuple[AcquisitionSummary, ...]
    after_observation_id: str
    action_evaluation: ActionEvaluation | None
    task_evaluation: TaskEvaluation | None
    progress: ProgressDelta
    pending_kind: PendingKind
    resulting_status: AgentLoopStatus | None
    reason_code: str
```

所有 decision-relevant identity、typed status、origin 和 reason code 必须无损保留；
“summary”只表示去除 private/raw payload，不表示丢掉 control facts。没有取得新
observation 的 actionless 分支令 `after_observation_id == before_observation_id`，并由
acquisition/pending/status 字段解释原因，不能假造一次 observation。

核心不变量是：一个通过 current context/schema boundary 并被 Runtime 接受处理的
policy decision，恰好产生一个 root `ControlTransition`。AskUser、Abort、
RequestObservation、Wait、RequestActionPage、ProposeDone 和 SelectAction 都不能只靠
分散 session 字段留下事实。confirmation/user continuation 如需单独记账，使用 typed
continuation source 引用 root transition，不能伪造成第二个 policy decision，也不能把
每个 low-level event 变成 ledger entry。pre-policy completion、provider boundary failure
或 harness watchdog 没有 accepted decision 时，不伪造 transition；它们由 typed
AgentResult/session snapshot 表达。

`AgentLoopState` 始终是 current-state authority；ControlTransition 不是 commit record、
replay source、durable ledger、global provenance graph 或 event bus。AgentContext history、
BenchmarkCaseResult、PartialEpisodeSnapshot 与 optional TurnRecorder 都是它与 current
state 的单向、privacy-bounded projection，不能反向参与 admission 或 state reconstruction。

ActionResult 返回后，decision-scoped collector 必须立即单调记录每次物理 execute 的实际
dispatch、expected/actual request lineage 与严格非负整数 probe facts；fresh after
acquisition 验证后必须立即更新 current
world 并记录 after identity。后续 evaluator exception/cancellation 只能补充同一 root 的
typed terminal reason/status，不能擦除已发生事实。confirmation continuation 的 ordered
execution/acquisition attempts、expected/actual acquisition origin、evaluation 与 progress
也只能单调合并到原 root，不能增加 root count。TaskEvaluation 只能绑定它实际评价的
observation epoch；pre-execution evaluation 不能冒充 post-action after evaluation。
`Turn` 仅是 bounded suffix 的兼容只读投影，不是事实写入容器。

### 8.2 Typed control feedback and bounded repair

Runtime 负责判定并记录已经成立的 control fact，AgentPolicy 负责在下一次普通
`decide(AgentContext)` 中选择修正参数、改选 action、请求 observation/page、改变策略或
停止。Runtime 不猜测模型原意、不自动改写参数、不替模型选择替代 action。M4.6-D 先把
下一次正常 policy inference 作为 bounded repair/replan opportunity；是否增加独立
reflector 属于后续可选 policy composition，必须由 benchmark 增益证明，且永远不取得
Runtime fact/action authority。
在模型语义上，feedback 是已发生 outcome 的 observation，不是 Runtime 生成的
corrective instruction；普通 AgentPolicy 可在自身推理中反思，但修正意图仍是新决策。
`next_decision_disposition` 只表示是否允许新 policy decision，绝不表示重放旧 request。

```python
@dataclass(frozen=True)
class ControlFeedback:
    kind: ControlFeedbackKind
    code: str
    source: ControlFeedbackSource
    next_decision_disposition: NextDecisionDisposition
    strategy_transition_required: bool
    public_subject_id: str | None = None
    public_field_paths: tuple[str, ...] = ()
    scope_digest: str | None = None    # Runtime-only
    issue_digest: str | None = None    # Runtime-only
    request_digest: str | None = None  # Runtime-only
    result_digest: str | None = None   # Runtime-only
```

Admission、ActionEvaluation/ProgressEvent 和 no-gain comparator 仍分别拥有底层事实；
`ControlFeedback` 只是同一 root `ControlTransition` 内“当前如何投递以及是否仍有 bounded policy
opportunity”的 typed envelope，不成为第二事实 owner。`AgentControlFeedbackView` 是它与
current public contract 的一次性、bounded、model-safe 投影，省略所有 digest。结构化
schema/action page/criteria 本身仍由 current AgentContext 的既有 owner 投影，feedback 只
引用这些公开 owner，不复制或重建另一套 action contract。reason message、raw exception、
历史 reason 和 benchmark classification 不能被反向解析为 feedback truth。

ActionSpace/page admission owner 必须直接返回 typed、public-safe issue（包括稳定
code 和允许公开的 field paths），而不是让 feedback owner 解析 `ValueError`/message。
invalid completion claim 保持既有 task-completion disposition，不进入 M4.6-D repair。
feedback owner 只决定投递、bounded repair consumption 和 control disposition；
ContextBuilder 只组装，独立 model-boundary projector 只做安全复制。

M4.6-D 的 supported feedback algebra 只有以下三类：

1. `REPAIRABLE_REJECTION`：current typed decision 已被 Runtime 接受处理，但在任何
   effectful dispatch 前因公开 action-selection/page/parameter/destination contract 不匹配
   而被拒绝；在 bounded issue budget 内返回下一 policy turn，且
   bind/probe/execute/capture 均为零。
2. `NO_INFORMATION_GAIN`：action-page 或 policy-origin observation 请求返回与请求键匹配的
   identity-free public result；它与 repairable rejection 共用 bounded issue budget。
3. `STRATEGY_TRANSITION_REQUIRED`：只是既有 validated `NO_EFFECT_CONFIRMED` 或
   already-satisfied ProgressEvent 的投递 envelope；底层事实和重复边界仍归
   ActionEvaluation/ProgressController，且不消耗 D 的 control issue budget。

`ControlFeedbackKind` 和 `ControlFeedbackSource` 的合法组合是 closed matrix：
admission 只能产生 `REPAIRABLE_REJECTION`，page/policy-observation comparator 只能产生
`NO_INFORMATION_GAIN`，ActionEvaluation/ProgressEvent 只能产生
`STRATEGY_TRANSITION_REQUIRED`。未支持的 kind/source 组合 typed fail closed，不得创建
repair opportunity，并保留原 source owner 的 disposition。page/observation 可以没有
public subject；每种 kind 的 required/optional 字段由该 matrix 验证。
`NextDecisionDisposition` 也是 closed：`CORRECT_OR_REPLAN` 只用于
`REPAIRABLE_REJECTION`，`CHANGE_STRATEGY` 用于两种 no-gain/no-effect feedback。
后者强制 `strategy_transition_required=true`，前者强制 `false`；未知或矛盾
disposition 不能进入 AgentContext。

validated `NO_EFFECT_CONFIRMED` 与 already-satisfied local postcondition 继续由既有
ActionEvaluation/ProgressEvent/ProgressController 拥有并投影；它们必须让下一 policy turn
看到 `strategy_transition_required=true`，但 M4.6-D 不新建 universal effectful-action retry
controller。当前 fill/select exact repetition invariant 保持不变；其它 action repetition 只有
新的运行证据出现后才扩展。

repair semantic scope 由 task revision、identity-free public-world semantic digest、public
action-contract/page digest 和 task-progress fingerprint 决定，显式排除 `observation_id`、
`action_space_id`、`page_id`、`context_id`、context generation、target/fact/evidence/binding
identity 和 private BID/route。`issue_digest` 仅由 scope、kind/source、stable code、
public subject/field paths 以及 no-gain 的 identity-free request/result 形状构成，显式排除
错误参数值、reason text 和 fresh identity。

M4.6-D 初始 benchmark profile 把同一 scope 内可投递的 distinct repair/no-gain
issue 预算冻结为 `2`：同一 `issue_digest` 第二次出现立即 typed
`no_progress_control_repetition`；不同 issue 最多各获得一次 feedback，第三个 distinct
no-progress issue typed 结束。该共享预算同时覆盖 rejection 和 no-gain，因此交替
invalid action/page/observation 不能绕过上限。只有真实 effectful `SENT` 或 relevant
public semantic/task-progress/action-page gain 才清除该 state；仅“合法接受”一个无增益
control decision、更换错误参数值或更换 ID 都不清除。数值 `2` 是可被 D targeted
run 否证的初始产品假设，不声称为 SOTA 常数；后续只能根据 correction/outcome
数据调整，不能按新反例无限扩大。

下列结果不进入 model repair：risk/safety block、task/session terminal、budget exhaustion、
cancel、`SENT_UNKNOWN`、invalid evaluator/component output、capability/integrity failure，以及
已经通过 ActionSpace admission 后才由 adapter 报告的 parameter-domain mismatch。最后一种
是 typed adapter-contract failure，不要求 Agent 猜测 private adapter contract。任何可能已
发送的请求都不得借 feedback 重放；turn budget 已耗尽时也不承诺产生 repair policy call。

AgentLoopState 只保存 bounded repair/no-gain key、streak/consumption state；
ControlTransition 保存本次 feedback envelope；AgentContext 做单向投影。旧 history feedback
不授予新的 repair opportunity。ProgressController 继续拥有 local semantic-attempt
containment，新的 control-feedback owner 不取得 planner、TaskProgressAuditor、ActionSpace、
evaluation 或 benchmark authority。

## 9. Evaluation 与 criterion-specific completion

`ActionEvaluationValidator` 处理动作是否发送及效果是否出现，至少绑定 request ID、
before/after observation ID 和 current evidence refs。after observation 必须来自该
ExecutionOutcome 的 acquired post observation，或一次 capability-admitted independent
capture。Milestone 只由 validated facts 与
milestone criteria 完成。Task completion 要求全部 required criteria、constraints、
forbidden-effect absence、required outputs 和 final authoritative checks。

```python
class CriterionAdjudicator(StrEnum):
    MECHANICAL = "mechanical"
    SEMANTIC = "semantic"
    USER_ACCEPTANCE = "user_acceptance"
    HYBRID = "hybrid"
```

- MECHANICAL：deterministic evaluator 最终裁决字段/API/file/SHA/device property。
- SEMANTIC：模型/rubric 可提出 evidence；Runtime 验证 scope、refs、rubric applicability
  和 current observation identity。
- USER_ACCEPTANCE：只有 TaskGoal 明确要求时，admitted user answer 才成为 criterion evidence。
- HYBRID：mechanical hard constraints 加 semantic/user quality judgment。

`ProposeDone` 必须重跑 TaskEvaluationValidator、output validator 和各 criterion
adjudicator，返回 DONE/CONTINUE/REQUEST_OBSERVATION/ASK_USER/BLOCKED/FAILED。
minimum output profile 继续要求 output 存在、regular file、SHA-256 和 current evidence
refs；不建设通用 artifact platform。

## 10. Long-horizon、progress、Batch、Memory 与 telemetry

长程目标限于单一活跃 episode、20–100+ control transitions、跨页面/应用/surface、
中途询问、中间验证和事实驱动 replan；不含跨天后台任务、崩溃恢复、跨机器
continuation、distributed workers 或 durable workflow engine。TaskPlan 是可替换
milestone hypothesis，LocalObjective 是由 current frontier 派生的 nearby desired world
state，不含预生成点击序列。除非明确另述，long-horizon 长度按 accepted policy
decision 产生的 root ControlTransition 计数，不按 low-level event 或 telemetry 行数计数。

```python
@dataclass(frozen=True)
class VerifiedTaskState:
    task_revision: int
    milestone_statuses: tuple[VerifiedMilestoneStatus, ...]
    current_frontier: tuple[str, ...]
    verified_evidence_refs: tuple[str, ...]
    unresolved_obligations: tuple[str, ...]
    failed_assumptions: tuple[str, ...]
```

VerifiedTaskState 是 AgentLoopState 内专门的 long-horizon frontier authority，不是第二个
state aggregate、store 或 executor context。它只接受 Runtime-validated current/durable-
profile evidence 的 promotion；planner output、模型自述、action receipt 或 plan exhaustion
不能更新 verified milestone。TaskProgressAuditor 只读 validated evaluation/evidence，
负责 criterion/milestone/frontier promotion 建议；它不能选择 GUI action、替代 policy、
降低 risk 或宣告 task completion。低频 TaskPlanner 基于 VerifiedTaskState 生成/替换
TaskPlan；ObjectivePolicy 从 current frontier 派生 LocalObjective。

现有/短环 `ProgressController` 与未来 `TaskProgressAuditor` 保持分层：前者只做
已声明 local postcondition 的重复无进展 containment（当前 minimum 是 fill/select），
是 liveness guard；后者在 P5-E 负责 milestone/task frontier。二者都不是 planner，不能
合并成修正弱 policy 的万能模块。context 只保留最近 8–12 个 ControlTransition 的
semantic projection、milestone summary、verified refs、failed assumptions 和 unresolved
obligations。

ActionBatch 是后续效率优化：最多三个、同 observation/surface/session、LOW risk、
无 external effect、navigation/app/page change 或跨 surface；前置 action 必须
`observation_barrier=False`，失败或 SENT_UNKNOWN 立即停止，batch 后 fresh acquisition。

Memory/Skill 仅是 sidecar hint；Runtime 必须重新 grounding，ActionSpace、RiskPolicy、
confirmation 和 evaluator 仍然生效。promotion 只通过 offline replay/cross-surface
evaluation 后 publish/reject。

TurnRecorder 只投影 ControlTransition 的 context revision、decision、semantic action、
result、evaluation、latency/tokens、observation cost、confirmation 和 route metrics。
recorder failure 不得改变 execution/result/completion；trace 不参与 admission 或 commit。
ControlTransition 属于 run control accounting，TurnRecorder 属于 behavior-neutral optional
telemetry；两者不能 dual-write 为两个 execution truth。

## 11. 模块责任与依赖门

```text
task/           TaskGoal, IntentContext, planning contracts, VerifiedTaskState contracts
model_boundary/ AgentContext, projection, budgets, paging, model views
world/          WorldObservation, acquisition contracts, ActionSpace, relevance, binder
agent/          decisions, loop sequencing, session/state, ControlTransition, progress guards
risk/           risk policy, confirmation subject
confirmation/   request/decision, summary, dominance
evaluation/     evidence, criterion and task/output validation
surfaces/       dom, visual, wot, accessibility, svg, api, cli, device
telemetry/      behavior-neutral recording
memory/         evaluated sidecars
benchmarks/     offline evaluation only
```

`agent/loop.py` 只编排，不拥有 prompt construction、provider SDK、model parsing、
confirmation summary、surface currentness、criterion entailment、output SHA 或 telemetry
persistence。文件/函数长度只触发 responsibility review，不是 correctness gate：拆分
必须移动完整 semantic authority 或 cohesive change reason，不能为降低 LOC 抽取随机
helper。自动化优先检查依赖方向、禁止导入、循环依赖、公共 authority、collaborator
边界与行为不变量；class public surface 或 collaborator 数量只作为 owner review 信号。

依赖红线：AgentPolicy 不导入 Binder/Executor/concrete surface；model_boundary 不导入
concrete surface；surface 不导入 AgentLoop；evaluation validator 不执行 action；
confirmation 不读取 private binding payload；telemetry 不参与 decision；benchmark 不被
production core 导入；target core 不导入 StateKernel/RuntimeCommitter/ActionContract。

## 12. Prompt injection 与不可信 context

页面、邮件、截图和工具 instruction 可以被模型看见，但不能修改 TaskGoal、扩大
ActionSpace、降低 risk、创建 confirmation 或成为 completion evidence（除非被验证为
environment state）。Agent 的可疑内容判断只能向保守方向作用：提高 risk、请求更强
observation、询问用户或停止。core 不建设通用 prompt-injection platform。

## 13. 永久验收不变量

1. AgentContext 是 Runtime state 的单向 disposable projection。
2. 所有 AgentDecision 绑定 current context_id；stale decision 零执行。
3. Internal ActionSpace 是唯一 membership authority；模型只选 current page option。
4. LocalObjective 只改变 relevance，不改变 legality。
5. private route 永不进入 AgentContext。
6. environment content 不能扩张 TaskGoal；raw intent 只能 context_only。
7. clarification 必须先产生 TaskGoal revision。
8. confirmation 绑定 semantic subject，确认后 capability-aware capture/rebind。
9. BoundActionRequest 必须 current；一个 effectful request 最多发送一次。
10. SENT_UNKNOWN 不自动 replay；ActionResult 不证明 effect。
11. Agent ProposeDone 不证明 completion；evidence 属于 current observation。
12. criterion adjudicator 决定裁决方式；required output 真实且满足 integrity。
13. TaskPlan 可替换且不是 authority；history/context 分区有界。
14. independent capture 与 post-action observation 是独立 capabilities；expected
    unsupported/failed acquisition typed，不能以裸异常或伪造 freshness 表达。
15. reset 提供 initial acquisition；effect evaluation 的 fresh after world 只来自
    ExecutionOutcome 或 capability-admitted capture。
16. dispatch truth 独立于 acquisition；SENT_UNKNOWN 不因 after-acquisition 失败而降格或重放。
17. 一个 accepted policy decision 恰好产生一个 bounded root ControlTransition；
    AgentLoopState 不由 transition replay 重建。
18. VerifiedTaskState 只由 validated evidence promotion；TaskPlan 与模型自述不是 verified frontier。
19. local ProgressController 与 TaskProgressAuditor 分离，二者都不替代 planner/policy。
20. Runtime 只投影 canonical typed control feedback；AgentPolicy 自行修正，Runtime 不自动
    改参或选替代 action；独立 reflector 是 evidence-gated policy extension，不是 D 前置或 authority。
21. M4.6-D 初始 profile 在同一 identity-free public semantic scope 内最多投递
    两个 distinct repair/no-gain issue；同一 issue 重复或第三个 distinct issue typed 结束。
    fresh identity、错误值变化、无增益 control decision、已发送或不确定请求均不能
    绕过该边界或触发重放。
22. recorder failure 不改变行为；benchmark metadata 不进入 product decision。
23. core 不依赖 event sourcing、global transaction 或 approval registry。

## 14. 明确非目标

- event sourcing、global transaction、RuntimeCommitter/StateKernel expansion；
- approval registry/token platform、universal provenance envelope；
- core prompt-injection subsystem、durable resume、distributed workflow engine；
- 每个任务必经 TaskSpecAuthority/ActionContract/TaskPlan；
- 超出当前声明 DOM/AX、Visual、WoT 最小合同的开放式概率 fusion/knowledge graph；
- 为每个合同或 context namespace 创建 service/database/store；
- 将 ControlTransition 扩张为 durable event ledger、state reconstruction authority 或
  low-level global event taxonomy；
- 用 Runtime progress guard 代替 policy competence、hierarchical planning 或 learned progress awareness。

## 15. 目标运行流程与完成定义

reset 先交付 initial acquisition。每轮基于 current observation 做 task evaluation；未完成
时构建 Internal ActionSpace 和 disposable AgentContext，校验 typed decision 的 current
context ID，再处理 observation/paging/user/wait/abort/done/action 分支。SelectAction 经
membership、risk/confirmation、current binding 后执行一次；优先消费 ExecutionOutcome
的 post-action acquisition，必要且支持时再 independent capture。Runtime 验证 action/task
evaluation，为每个 accepted decision 追加恰好一个 bounded root ControlTransition，并串行
更新 AgentLoopState。RequestObservation、Wait、stale/currentness 与 confirmation refresh
只走 capability-aware capture，不消费不存在的 post-step cache。

目标完成需要：M0.1 AgentContext/identity/paging 完成；model-backed AgentPolicy 与
production evaluator composition 完成；new-loop harness 和小型 BrowserGym/MiniWoB smoke
通过；observation acquisition lifecycle 与 lossless control accounting 闭合；长程 verified
frontier 与 breadth 按阶段证明；默认切换后旧 Coordinator/StateKernel/
RuntimeCommitter/ActionContract 不再进入 target core。上述完成定义不恢复 event core。

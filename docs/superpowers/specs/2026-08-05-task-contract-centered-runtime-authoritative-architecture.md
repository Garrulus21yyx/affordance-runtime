# Affordance Runtime：AgentContext 循环式 E2E Agent 目标架构

> **Lifecycle:** CURRENT AUTHORITATIVE ARCHITECTURE
> **Updated:** 2026-08-08
> **Scope:** target semantics and invariants only
> **Implementation truth:** [Implementation Status](../../implementation-status.md)
> **Migration order:** [Architecture Evolution Plan](../plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

文件路径仅为兼容文档治理检查而保留；文件名中的
`task-contract-centered` 不再描述当前架构。本文是唯一目标语义权威，但实现状态
仍以 Implementation Status 为准：AgentContext 的 P5-M0.1 profile 已在 non-default
路径落地；model policy、criterion adjudicator 与长程能力仍未实现。

## 0. 系统定位与计算模型

Affordance Runtime 是面向 GUI、Web、桌面、设备和工具环境的统一 E2E Agent
Runtime。核心不是状态事务，而是理解任务、有效观察、生成当前合法语义动作、
由 Agent 提议、由 Runtime 裁决和绑定、执行一次、重新观察并独立验证。

```text
AgentDecision_t = AgentPolicy(AgentContext_t)
Transition_t = RuntimeApply(AuthoritativeState_t, AgentDecision_t)

AgentDecision
→ Runtime validation
→ BoundActionRequest
→ execute once
→ ActionResult
→ fresh WorldObservation
→ validated ActionEvaluation
→ validated TaskEvaluation
→ AgentLoopState update
```

`AgentContext_t` 是 TaskGoal、bounded IntentContext、current WorldObservation、
progress、Internal ActionSpace、bounded history、pending state 和 budgets 的一次性
投影。统一的是模型每轮看到的上下文，不是 Runtime authority。

## 1. 架构定律

1. **模型可见性不等于执行权。** Visible to model、authorized effect、executable
   route 和 verified fact 是四个不同概念。
2. **Observation 是当前 binding 的事实来源。** TaskGoal 是稳定语义，TaskPlan
   是可替换假设，AgentContext 是一次性投影，WorldObservation 是当前世界事实。
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
  PendingConfirmation/Question/UnknownEffect · validated evaluations
        ↓ one-way projection
Disposable AgentContext
        ↓
AgentPolicy → typed AgentDecision
        ↓ Runtime validation
RiskPolicy / semantic confirmation / current binding / execute once
        ↓
fresh observation / ActionEvaluationValidator / TaskEvaluationValidator
```

Runtime authoritative state 仅包括：`TaskGoal`、task revision、current
`WorldObservation`、current Internal `ActionSpace`、`AgentLoopState`、
`PendingConfirmation`、`PendingUserQuestion`、`PendingUnknownRequest`、current
`BoundActionRequest`、`ActionResult` 和 validated evaluations。

```python
@dataclass
class AgentLoopState:
    current_observation: WorldObservation
    recent_turns: tuple[Turn, ...]
    task_plan: TaskPlan | None
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

它不保存全量 observation 历史、event DAG、recovery transaction、delta log、
provider token registry、durable checkpoint 或 global approval store。

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

@dataclass(frozen=True)
class AgentContext:
    context_id: str
    task: AgentTaskView
    intent: IntentContextView | None
    progress: AgentProgressView
    world: ModelWorldView
    actions: AgentActionPageView | None
    history: tuple[AgentTurnView, ...]
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
- `AgentProgressView`：active objective、milestones、verified facts、unresolved evidence
  obligations；模型 reflection 永远不是 verified progress。
- `ModelWorldView`：bounded targets/facts/conflicts、truthful coverage 和 available
  observation modalities；不暴露 selector、coordinate、href、credential 或 route handle。
- `AgentTurnView`：只保留 decision kind、semantic action、bounded public parameters、
  dispatch/evaluation status 和短 reason。
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
- `RequestObservation(subject_id, modality, required_assurance, reason)`；Runtime 选择
  DOM/AX/Visual/WoT/API/provider。
- `RequestActionPage(query, target_id, relevance_role)`；新 page 产生新 page/context ID，
  旧 decision 自动 stale。
- `AskUser(question, requested_fields)`；改变任务语义的回答必须产生 TaskGoal revision。
- `ProposeDone(claimed_criteria, evidence_refs, result_summary, unresolved_items)`；仅是建议。
- `Wait(reason, max_wait_ms)`；实际等待后必须 fresh observe。
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
screenshot/TD digest 或 backend。确认后必须 fresh observe、重建 ActionSpace/subject、
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

## 9. Evaluation 与 criterion-specific completion

`ActionEvaluationValidator` 处理动作是否发送及效果是否出现，至少绑定 request ID、
before/after observation ID 和 current evidence refs。Milestone 只由 validated facts 与
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

## 10. Long-horizon、Batch、Memory 与 telemetry

长程目标限于单一活跃 episode、20–100+ turns、跨页面/应用/surface、中途询问、
中间验证和事实驱动 replan；不含跨天后台任务、崩溃恢复、跨机器 continuation、
distributed workers 或 durable workflow engine。TaskPlan 是可替换 milestone 假设，
LocalObjective 是 nearby world state，不含预生成点击序列。context 只保留最近 8–12
个 semantic turns、milestone summary、verified refs、failed assumptions 和 unresolved
obligations。

ActionBatch 是后续效率优化：最多三个、同 observation/surface/session、LOW risk、
无 external effect、navigation/app/page change 或跨 surface；前置 action 必须
`observation_barrier=False`，失败或 SENT_UNKNOWN 立即停止，batch 后 fresh observe。

Memory/Skill 仅是 sidecar hint；Runtime 必须重新 grounding，ActionSpace、RiskPolicy、
confirmation 和 evaluator 仍然生效。promotion 只通过 offline replay/cross-surface
evaluation 后 publish/reject。

TurnRecorder 只记录 context revision、decision、semantic action、result、evaluation、
latency/tokens、observation cost、confirmation 和 route metrics。recorder failure 不得
改变 execution/result/completion；trace 不参与 admission 或 commit。

## 11. 模块责任与依赖门

```text
task/           TaskGoal, IntentContext, planning contracts
model_boundary/ AgentContext, projection, budgets, paging, model views
world/          WorldObservation, ActionSpace, relevance, binder
agent/          decisions, loop sequencing, session, state, post-action policy
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
persistence。文件超过 350 行需 fail/review，函数超过 80 行 fail，class 超过 10 个
public methods 或注入超过 8 collaborators 需 owner review。

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
8. confirmation 绑定 semantic subject，确认后 fresh observe/rebind。
9. BoundActionRequest 必须 current；一个 effectful request 最多发送一次。
10. SENT_UNKNOWN 不自动 replay；ActionResult 不证明 effect。
11. Agent ProposeDone 不证明 completion；evidence 属于 current observation。
12. criterion adjudicator 决定裁决方式；required output 真实且满足 integrity。
13. TaskPlan 可替换且不是 authority；history/context 分区有界。
14. recorder failure 不改变行为；benchmark metadata 不进入 product decision。
15. core 不依赖 event sourcing、global transaction 或 approval registry。

## 14. 明确非目标

- event sourcing、global transaction、RuntimeCommitter/StateKernel expansion；
- approval registry/token platform、universal provenance envelope；
- core prompt-injection subsystem、durable resume、distributed workflow engine；
- 每个任务必经 TaskSpecAuthority/ActionContract/TaskPlan；
- semantic fusion 在真实多源目标合并需求出现前成为主线前置；
- 为每个合同或 context namespace 创建 service/database/store。

## 15. 目标运行流程与完成定义

每轮先基于 current observation 做 task evaluation；未完成时构建 Internal ActionSpace
和 disposable AgentContext，校验 typed decision 的 current context ID，再处理 observation/
paging/user/wait/abort/done/action 分支。SelectAction 经 membership、risk/confirmation、
current binding 后执行一次；随后 fresh observe，验证 action/task evaluation，并串行更新
AgentLoopState。

目标完成需要：M0.1 AgentContext/identity/paging 完成；model-backed AgentPolicy 与
production evaluator composition 完成；new-loop harness 和小型 BrowserGym/MiniWoB smoke
通过；长程与 breadth 按阶段证明；默认切换后旧 Coordinator/StateKernel/
RuntimeCommitter/ActionContract 不再进入 target core。上述完成定义不恢复 event core。

# Affordance Runtime：统一世界接口与 E2E AgentLoop 目标架构

> **Lifecycle:** CURRENT AUTHORITATIVE ARCHITECTURE
> **Updated:** 2026-08-07
> **Scope:** target semantics and invariants only
> **Implementation truth:** [Implementation Status](../../implementation-status.md)
> **Migration order:** [Architecture Evolution Plan](../plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

文件路径为兼容现有文档治理检查而保留；文件名中的
`task-contract-centered` 不再描述当前架构。本文是唯一目标语义权威。

## 0. 核心决议

Affordance Runtime 的中心任务是：

> 让 agent 通过同一套语义接口，在 DOM、Accessibility、Visual、SVG、
> WoT、API、Device 和 CLI 等不同世界表面上，高效观察、选择动作、执行并验证。

正式设计原则是：

> **语义强、执行时绑定的职责薄 Intake；感知、grounding、动作空间、验证和
> 重规划能力厚，但状态与事务基础设施薄的闭环 Agent Runtime。**

这里的“薄/厚”描述职责和能力，不描述代码行数：

| 边界 | 必须强在哪里 | 必须避免什么 |
|---|---|---|
| Thin Semantic Intake | 稳定目标、约束、允许/禁止效果、关键输入、完成条件、输出、风险和必要来源 | 页面结构、按钮顺序、surface、selector、coordinate、TaskPlan |
| Thick Execution Loop | observation、world fusion、grounding、legal action space、route selection、post-action evaluation、fact-driven replanning | 厚 StateKernel、delta protocol、global transaction、ledger、通用 recovery platform |

目标运行链只有一个中心：

```text
TaskGoal
→ observe
→ evaluate current state
→ optionally form/replace a plan
→ generate current legal ActionSpace
→ choose one semantic action
→ bind to one current surface route
→ confirm when needed
→ execute once
→ ActionResult
→ fresh observation
→ ActionEvaluation + TaskEvaluation
→ continue / ask / stop
```

`typed delta → global atomic commit → durable ledger → recovery transaction`
不是产品主轴，也不是当前目标架构的前置条件。现有实现中的相关机制是可迁移
的历史可靠性基线；在默认短闭环切换前冻结扩张，切换后删除或降为局部实现
细节。本文不否定已取得的 P4 正确性成果，但把它们压缩为动作附近的局部不变量。

## 1. 架构法律

1. **世界接口优先。** 新设计首先回答 agent 如何观察和作用于世界，而不是内部状态如何提交。
2. **Intake 职责薄、语义强。** 它固定跨页面和跨时间仍成立的 what/boundary/done，不决定当前 how。
3. **Execution 能力厚、基础设施薄。** 厚度来自观察、grounding、动作生成、route、验证和重规划，不来自状态提交协议。
4. **语义对象独立于 surface。** Agent 选择 semantic target/action；selector、坐标、WoT form、API handle 等只属于 binding。
5. **观察是当前事实边界。** `WorldObservation` 是 Runtime 内部完整世界模型；`AgentWorldView` 是给模型的紧凑投影。
6. **动作绑定观察。** 每个 `BoundActionRequest` 绑定产生它的 `observation_id` 和 `binding_id`；stale 时零执行。
7. **一次请求只执行一次。** effectful request 结果未知时先重新观察，禁止盲重试。
8. **receipt 不证明效果。** `ActionResult`、`ActionEvaluation`、`TaskEvaluation` 三者分离。
9. **动作后必须获得新观察。** 除无副作用的纯查询优化外，不能用 executor 返回值代替 fresh observation。
10. **主动感知按信息价值调度。** DOM/AX/WoT/API 等结构化来源优先；Visual/VLM 与 targeted recapture 按 evidence gap 使用。
11. **高风险动作由人确认。** Runtime 只做 `ALLOW / NEEDS_CONFIRMATION / BLOCK`；不建设通用授权证明平台。
12. **计划是可丢弃假设。** `Plan` 帮助长任务推理，可在 fresh observation 后整体替换，不授予执行权，也不是每个 turn 的必经对象。
13. **telemetry 不控制执行。** Trace/recorder 记录已经发生的事实；记录失败不改变动作语义。
14. **复杂度由真实需求拉动。** checkpoint、durable ledger、distributed transaction、multi-writer fencing 在产品故障模型出现前均为非目标。

### 1.1 选择性吸收当前 GUI Agent 共识

本文不复刻单一系统，只吸收与项目中心一致的稳定模式：

| 吸收 | 本项目边界 |
|---|---|
| GUI/CLI/API 等多通道统一环境合同 | policy 不直接控制 driver/endpoint |
| screenshot → UI elements/marks → semantic options | 禁止 screen-to-free-coordinate 直跳 |
| optional milestones/reflection for long horizon | Plan 非权威，simple task bypass |
| `ask_user`/reobserve 作为一等 policy decision | 不确定时不猜测 |
| bounded local ActionBatch | 单动作优先，严格 observation barrier |
| experience/cache/verified Skill | Runtime 外离线评测后发布 |
| human confirmation for sensitive effects | 不建设 IAM/token registry |

不吸收当前阶段不需要的超大训练基础设施、跨设备长期 workflow、proactive
background service 或 online self-modifying Runtime。

## 2. 目标总图

```text
                         ┌──────────────────────────────┐
TaskGoal ───────────────▶│ AgentLoop                    │
                         │ observe → decide → act       │
                         │ → observe → evaluate         │
                         └──────┬───────────┬───────────┘
                                │           │
                         AgentPolicy   Evaluators
                                │           │
                                ▼           ▼
                         ┌──────────────────────────────┐
                         │ Unified World Interface      │
                         │ WorldObservation             │
                         │ AgentWorldView / ActionSpace │
                         │ Intent / BoundRequest / Result│
                         └──────────────┬───────────────┘
                                        │
                 ┌──────────┬───────────┼──────────┬─────────┐
                 ▼          ▼           ▼          ▼         ▼
               DOM/AX     Visual       SVG        WoT     API/Device/CLI
                 └──────────┴───────────┴──────────┴─────────┘
                           SurfaceAdapter contract
```

Browser 不是特殊架构主路径。每种 surface 都以对称方式提供 observe、action
binding、execute 和 reobserve 能力。一个语义实体可以同时拥有多个 binding，
Runtime 根据可执行性、freshness、confidence、cost 和历史结果选择 route。

## 3. 核心合同

以下是语义合同，不要求一类一文件或一对象一服务。

### 3.1 TaskGoal 与可选 EvaluationSpec

```python
@dataclass(frozen=True)
class TaskGoal:
    instruction: str
    constraints: tuple[Constraint, ...] = ()
    allowed_effects: tuple[AllowedEffect, ...] = ()
    forbidden_effects: tuple[ForbiddenEffect, ...] = ()
    inputs: tuple[TaskInput, ...] = ()
    success_criteria: tuple[Criterion, ...] = ()
    requested_outputs: tuple[OutputRequest, ...] = ()
    risk_profile: RiskProfile = RiskProfile.DEFAULT
    material_bindings: tuple[MaterialBinding, ...] = ()

@dataclass(frozen=True)
class EvaluationSpec:
    success_expression: object
    required_outputs: tuple[OutputSpec, ...] = ()
    authoritative_checks: tuple[CheckSpec, ...] = ()
```

`TaskGoal` 语义强：它保存跨页面/跨时间稳定的目标边界，而不保存页面结构、
动作顺序、backend 或 `Plan`。`RiskPolicy` 是执行时 evaluator；它读取
`TaskGoal.risk_profile` 和当前 `ActionIntent`，不把可执行策略对象塞入 task data。
对 effectful task，`allowed_effects` 必须由明确指令或 intake clarification 得到；
空集合不能被解释为“允许任意效果”。

Intake 按风险分层，而不是一刀切：

| Profile | Core data |
|---|---|
| 普通 GUI 任务 | lightweight `TaskGoal` |
| 高风险或结构化任务 | `TaskGoal` + explicit risk/effect boundary + selected `MaterialBinding` |
| 严格业务或 benchmark | 上述内容 + `EvaluationSpec` + exact source lineage when required |

`material_bindings` 和来源 lineage 可选、按风险启用。`SourceEnvelope`、exact
anchors 和完整来源图不能成为所有 GUI action 的固定税负。

### 3.2 SurfaceObservation、ActionBinding 与 WorldObservation

```python
@dataclass(frozen=True)
class SurfaceObservation:
    surface: Surface
    observation_id: str
    revision: str
    entities: tuple[SurfaceEntity, ...]
    facts: tuple[StateFact, ...]
    bindings: tuple[ActionBinding, ...]
    coverage: Coverage
    artifacts: tuple[ArtifactRef, ...] = ()

@dataclass(frozen=True)
class ActionBinding:
    binding_id: str
    observation_id: str
    target_id: str
    surface: Surface
    executor_id: str
    supported_actions: frozenset[str]
    payload: object
    freshness: Freshness
    confidence: float | None = None
    cost: float | None = None
```

`WorldFusion` 将多个 surface candidate 合并为稳定的 `SemanticTarget`，保留
冲突和全部可用 binding：

```python
@dataclass(frozen=True)
class WorldObservation:
    observation_id: str
    environment_revision: str
    targets: tuple[SemanticTarget, ...]
    facts: tuple[StateFact, ...]
    bindings: tuple[ActionBinding, ...]
    coverage: tuple[Coverage, ...]
    conflicts: tuple[ObservationConflict, ...]
    source_observations: tuple[SurfaceObservation, ...]
    captured_at_s: float
```

`AgentWorldView` 只暴露模型做决定所需的字段：

```text
target_id · role · label · state · supported_actions · necessary relations
unresolved conflicts · necessary screenshot/mark refs
```

它不暴露 raw selector、coordinate、URL form、backend handle 或 credential。

### 3.3 ActionSpace 与 AgentDecision

```python
@dataclass(frozen=True)
class ActionOption:
    action_id: str
    action: str
    target_id: str
    destination_id: str | None
    parameter_schema: object
    description: str
    expected_outcome: OutcomeExpectation | None = None
    batchable: bool = False
    observation_barrier: bool = True

@dataclass(frozen=True)
class ActionSpace:
    observation_id: str
    actions: tuple[ActionOption, ...]
```

AgentPolicy 输入 `TaskGoal + AgentWorldView + ActionSpace + recent turns + optional Plan`，输出
且只输出：

```text
Select(action_id, parameters)
ActBatch(action_ids, parameters)
AskUser(question)
Reobserve(reason)
Finish(result)
```

模型不能创建 binding、selector、coordinate、backend payload、approval 或
task-completion fact。

### 3.3.1 TaskPlan、Milestone 与 LocalObjective

```text
TaskGoal          = what，以及稳定的边界和 done
TaskPlan          = optional high-level how hypothesis
LocalObjective    = 当前一到数轮希望世界达到的 nearby state
ActionIntent      = Agent 选择的 current semantic action
BoundActionRequest = 当前 observation 上绑定的 executable request
```

```python
@dataclass(frozen=True)
class TaskPlan:
    plan_id: str
    milestones: tuple[Milestone, ...]

@dataclass(frozen=True)
class Milestone:
    milestone_id: str
    objective: str
    depends_on: tuple[str, ...] = ()
    completion_criteria: tuple[Criterion, ...] = ()

@dataclass(frozen=True)
class LocalObjective:
    objective: str
    completion_criteria: tuple[Criterion, ...]
    action_budget: int = 5
```

TaskPlanner 低频生成 milestone 假设；AgentPolicy 高频选择当前动作。简单任务跳过
TaskPlan，直接从 observation-bound ActionSpace 选择动作。复杂任务中，fresh
observation 使旧假设失效时整体替换 Plan，不维护复杂 mutation history。
Milestone 由 evaluator 依据事实判断；planner/Plan exhaustion 永远不能宣告完成。
`LocalObjective` 描述期望状态，不包含 GUI 动作序列。

### 3.4 ActionIntent、BoundActionRequest 与 ActionResult

```python
@dataclass(frozen=True)
class ActionIntent:
    intent_id: str
    action: str
    target_id: str
    destination_id: str | None
    parameters: Mapping[str, object]
    expected_outcome: OutcomeExpectation | None = None

@dataclass(frozen=True)
class BoundActionRequest:
    request_id: str
    observation_id: str
    intent: ActionIntent
    binding: ActionBinding
    timeout_ms: int = 5_000

@dataclass(frozen=True)
class ActionResult:
    request_id: str
    dispatch_status: Literal["NOT_SENT", "SENT", "SENT_UNKNOWN"]
    success: bool
    backend: str
    receipt: object | None
    error: ActionError | None
    started_at: float
    ended_at: float
```

`intent_id` 覆盖用户可理解的 action、target、destination、parameters 和 expected
effect。RiskPolicy 由这些语义和 TaskGoal 派生 risk/consequences；confirmation
subject identity 覆盖 intent 加派生风险。`request_id` 覆盖 intent、observation 和
binding，用于 stale check、result lineage 和 unknown-effect identification。确认后
selector/coordinate/form 等 binding 变化但 confirmation subject 未变，Runtime 可以
fresh rebind；语义或风险任一变化都必须重新确认。不再平行维护
transaction/proof/seal digest。

### 3.4.1 有界 ActionBatch

单动作是默认。`ActionBatch` 只是降低模型调用和 observation 次数的局部优化：

```python
@dataclass(frozen=True)
class ActionBatch:
    batch_id: str
    observation_id: str
    intents: tuple[ActionIntent, ...]
    stop_on_failure: bool = True

@dataclass(frozen=True)
class BoundActionBatch:
    batch_id: str
    observation_id: str
    requests: tuple[BoundActionRequest, ...]
    stop_on_failure: bool = True
```

第一版最多三个动作，必须同 observation、同 surface/session、低风险、无外部
效果、无导航/app 切换、无跨 surface，且每个 option 显式 `batchable=True`、前置
动作 `observation_barrier=False`。ActionBinder 将通过验证的 ActionBatch 一次性绑定
为 BoundActionBatch；失败立即停止，batch 后必须 fresh observe。
优先实现 `fill/select/replace_text/drag` 等 adapter 原子动作；Batch 不是弥补粗糙
adapter action 的手段，也不是预生成长轨迹。

### 3.5 Evaluation 与 Turn

```python
class ActionEvaluationStatus(Enum):
    EFFECT_CONFIRMED = "effect_confirmed"
    NO_EFFECT = "no_effect"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    ERROR = "error"

class TaskEvaluationStatus(Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"

@dataclass(frozen=True)
class Turn:
    before_observation_id: str
    local_objective: LocalObjective | None
    action: ActionIntent | ActionBatch
    result: ActionResult | tuple[ActionResult, ...]
    after_observation_id: str
    action_evaluation: ActionEvaluation
    task_evaluation: TaskEvaluation
```

`ActionEvaluator` 只判断这个动作的效果；`TaskEvaluator` 判断完整目标；
`LoopPolicy` 决定继续、重新观察、询问用户或停止。required artifact 必须真实
存在并匹配内容，不能由声明、receipt 或 trace 代替。

## 4. Unified World Interface

目标接口为：

```python
class SurfaceAdapter(Protocol):
    surface: Surface

    def observe(self, request: ObservationRequest) -> SurfaceObservation: ...

    def available_actions(
        self,
        observation: SurfaceObservation,
    ) -> tuple[ActionBinding, ...]: ...

    def is_current(self, binding: ActionBinding) -> bool: ...

    def execute(self, request: BoundActionRequest) -> ActionResult: ...
```

实现可以将 observation 与 execution port 物理拆开，但语义必须对称。

`ObservationOrchestrator`/`SurfaceRegistry` 根据 TaskGoal、LocalObjective、预算和
coverage gap 选择 adapter；`WorldFusion` 合并实体；`ActionSpaceBuilder` 生成当前
合法动作；`RouteSelector`/`ActionBinder` 为 ActionIntent 选择当前 binding；
`World.execute` 只接受 current `BoundActionRequest`。

### 4.1 Observation policy

默认按成本和信息价值分层：

1. 复用仍然 fresh 且覆盖充分的结构化 observation；
2. 优先查询 DOM/AX/WoT/API/Device/CLI state 等低成本、可验证来源；
3. 发现 coverage gap、conflict 或视觉专属信息时做 targeted capture；
4. 仅在结构化来源不足时扩大截图/VLM；
5. 动作后至少重观察受影响 target，外部效果按 evaluator 需要扩大范围。

预算记录 observations、model calls、visual calls、latency 和 fallback，而不是
只记录通用 runtime transition 数量。

### 4.2 Route policy

Route 选择考虑：

```text
executor support
freshness
semantic confidence
expected reliability
observation/interaction cost
historical route outcome
```

effectful action 执行失败后不能在同一 request 内自动切换 backend 再执行。
下一 route 只能由 fresh observation 后的新 turn 产生。

## 5. AgentLoop

```python
while state.budget.remaining:
    before = world.observe(task, state.focus)

    current = task_evaluator.evaluate(task, before, state.recent_turns)
    if current.status is COMPLETE:
        return Done(current.result)

    if plan_policy.should_plan(state, current):
        state.optional_plan = task_planner.plan_or_replace(
            task, before, state.optional_plan, state.recent_turns
        )

    objective = objective_policy.select(task, state.optional_plan, before)
    action_space = world.action_space(task, objective, before)

    decision = policy.next_action(
        task,
        objective,
        before.agent_view(),
        action_space,
        state.recent_turns,
        state.optional_plan,
    )

    if decision is AskUser:
        return WaitingUser(decision.question)

    if decision is Finish:
        # Finish is a proposal; only TaskEvaluator may return Done.
        continue

    intent_or_batch = action_validator.validate(decision, action_space, before)
    risk = risk_policy.evaluate(task, intent_or_batch)

    if risk is NEEDS_CONFIRMATION:
        return WaitingConfirmation(risk.confirmation_subject_id, risk.summary)
    if risk is BLOCK:
        return Failed(risk.reason)

    request_or_batch = world.bind(intent_or_batch, before, action_space)
    if not world.is_current(request_or_batch):
        continue

    result = world.execute(request_or_batch)
    after = world.observe(task, focus=request_or_batch.target_ids)

    action_eval = action_evaluator.evaluate(before, request_or_batch, result, after)
    task_eval = task_evaluator.evaluate(task, after, state.recent_turns)
    state.record(Turn(before.id, objective, intent_or_batch, result, after.id, action_eval, task_eval))

    directive = loop_policy.decide(action_eval, task_eval, state.budget)
    if directive is not CONTINUE:
        return directive
```

`AgentLoopState` 只保存：

```text
status
current observation ref
bounded recent turns
optional plan
pending confirmation
pending uncertain action
pending user question
current milestone status/summary
budget
final result
```

`RUNNING / WAITING_USER / WAITING_CONFIRMATION / DONE / FAILED` 是长期状态。
`PREFLIGHT / ACTING / VERIFYING / RECOVERING` 只是一次调用内部步骤。

## 6. Human confirmation

`RiskPolicy` 输出：

```text
ALLOW
NEEDS_CONFIRMATION
BLOCK
```

默认策略：读取、观察、滚动、聚焦自动允许；普通导航和局部可逆编辑由产品
策略决定；发送、分享、付款、购买、删除、外部系统写入和物理设备动作请求
人工确认；权限/账户设置和不可逆动作同样确认；影响不清楚时确认或停止。

确认绑定 `ActionIntent.intent_id`、可读语义摘要和 consequences，而不是 selector、
坐标或 backend form。确认后必须重新观察并 fresh rebind。只要 target、destination、
parameters、effect 和 risk 不变，binding/current observation 变化无需用户重新理解；
这些语义字段任一变化则旧确认失效。`ExecutorSupport` 表示 backend 能否执行；
`HumanConfirmation` 表示用户是否确认语义后果。两者不得混为 capability/token registry。

```python
@dataclass(frozen=True)
class ConfirmationRequest:
    confirmation_subject_id: str
    intent: ActionIntent
    summary: str
    consequences: tuple[str, ...]
```

LoopState 同一时刻只保存一个 pending confirmation；不需要 approval registry。

## 7. Recovery 与 telemetry

LoopPolicy 只有少数公开决定：

| 情况 | 决定 |
|---|---|
| stale / grounding failure | `REOBSERVE` |
| plan/world hypothesis invalid | `REPLAN` |
| 缺少用户信息 | `ASK_USER` |
| 等待高风险确认 | `WAIT_CONFIRMATION` |
| effect unknown | fresh observation + evaluate；不重试旧 request |
| criteria complete | `DONE` |
| 明确失败或预算耗尽 | `FAILED` |

provider schema repair 属于 model adapter；route 变化属于下一 turn 的新选择；二者
都不需要通用 recovery transaction。

`SENT_UNKNOWN` 必须先 fresh observe 再评估：EFFECT_CONFIRMED 可继续，NO_EFFECT
进入新的事实驱动决策，CONFLICT 做 targeted reobserve，仍为 UNKNOWN 时 ask_user
或停止；任何分支都不直接 replay 旧 request。

`TurnRecorder` 是可选 telemetry，推荐每 turn 记录：

```text
before_observation_id
action_request_id
action_result
after_observation_id
action/task evaluation
surface route
latency and model/visual calls
```

Recorder/trace 写入失败不得决定 action admission、execution 或 completion。

## 8. Long-horizon、Memory 与 Skill sidecars

单一 active episode 可以支持跨页面/应用/surface 的 20–100+ turns。长程上下文只
保留最近约 8–12 个 Turn、当前 milestones/摘要和已验证 evidence refs；不把全部
observation/event history 塞进模型或 active state。跨天后台运行、定时任务、进程
崩溃恢复、跨机器接续和 distributed workers 不属于当前 core。

`BindingCache`、memory 和 Skill 是可选 sidecars：cache hit 必须在当前 observation
重新解析 target 并验证 fingerprint/currentness；Skill 不能绕过 ActionSpace、
RiskPolicy、fresh observation 或 evaluator。学习链只允许：

```text
Turn records
→ failure attribution
→ candidate memory / skill / route hint
→ offline replay and cross-surface evaluation
→ publish or reject
```

Runtime 不在线修改或自动发布自己的核心策略。

## 9. 当前资产的目标归宿

| 当前资产 | 目标处理 |
|---|---|
| `UnifiedObservation` | 保留并演进为 `WorldObservation`；增加 `AgentWorldView` |
| `GroundingCandidate` / semantic fusion | 保留，作为跨 surface binding 核心 |
| active/targeted perception | 保留并重点优化 |
| DOM/AX/Visual/SVG/WoT/API/Device/CLI adapters | 统一到对称 surface contract |
| `ExecutorRouter` / executors | 保留，入口收缩为 `BoundActionRequest → ActionResult` |
| `LoopEvaluator` 原则 | 保留，拆清 action/task evaluation |
| output materialization | 保留真实存在与内容匹配检查 |
| `TaskSpec` | core 收缩为 `TaskGoal`，严格部分移入 optional `EvaluationSpec`/ingestion profile |
| `TaskPlan` | 改为 optional `TaskPlan<Milestone>`；事实驱动整体替换 |
| `ActionChoiceCatalog` | 简化为 observation-bound `ActionSpace` |
| `ActionContract` | 拆为 `ActionIntent + ActionBinding + BoundActionRequest` |
| approval/capability platform | 替换为 `ExecutorSupport + RiskPolicy + HumanConfirmation` |
| `StateKernel` | 替换为小型 `AgentLoopState` |
| `RuntimeDelta` / `RuntimeCommitter` | 默认路径切换后删除 |
| recovery taxonomy/transaction | 压缩为 loop directives |
| `TraceDag` / durable ledger | 降为 optional telemetry；不作为执行输入 |
| `SemanticAudit` / source authority graph | 从默认 GUI path 移除；仅 strict profile 按需保留 |
| `System1ReflexLibrary` / TaskSkill ideas | 降为 currentness-checked cache/verified skill sidecar |

## 10. 必须保留的局部正确性不变量

1. BoundActionRequest 绑定 current observation 和 current binding。
2. stale observation/binding 在执行前被拒绝，Executor 调用数为零。
3. 高风险动作需要真实 human confirmation。
4. confirmation 覆盖的 ActionIntent 语义、效果和风险与执行 intent 相同；纯 binding 变化可 fresh rebind。
5. ActionResult success 不等于 action effect 或 task completion。
6. 每次 action 或 admitted batch 后获取 fresh observation。
7. UNKNOWN effect 不盲重试。
8. required artifact 必须实际存在并匹配内容。
9. 模型不能直接输出 raw selector、coordinate 或 backend payload。
10. TaskPlan 可选、可整体替换且不包含 GUI action；Milestone 由 evaluator 判断。
11. Runtime 根据 current observation 生成 ActionSpace。
12. Batch 最多三个、低风险、同 surface、无 observation barrier；不得包含 external effect/navigation。
13. long-horizon loop 保留约束、会 ask_user、会做中间验证和 fact-driven replan。
14. Trace/recorder 写入失败不改变行为。
15. memory/skill 发布必须先通过 offline evaluation。

这些不变量由动作边界的局部检查实现，不要求 global transaction、event sourcing、
StateKernel CAS 或 durable commit ledger。

## 11. 明确非目标

- event-sourced execution core；
- multi-domain typed delta protocol；
- global atomic commit；
- durable run ledger/checkpoint/resume；
- distributed transaction、worker fencing 或 exactly-once 平台；
- general authorization proof/capability-token platform；
- prompt-injection classifier/monitor 作为 Runtime 主架构；
- 每个任务必经 SourceEnvelope/TaskSpecAuthority/TaskPlan；
- trace/benchmark/reward 成为在线执行权威；
- 为每个逻辑合同创建 service、database、store 或 model call。
- 跨天 proactive/background workflow、crash resume 或 distributed worker runtime；
- Runtime 在线自改或未经评测自动发布技能。

未来只有在真实产品故障模型明确要求多 writer、跨进程恢复或审计持久化时，才另行
设计局部 durable mechanism；它不能反向污染核心观察—行动接口。

## 12. 目标验收

核心能力以跨 surface 正向矩阵验收。相同 semantic task 必须使用：

```text
same TaskGoal
same AgentPolicy
same action vocabulary
same evaluator
different SurfaceAdapter only
```

至少覆盖 DOM、AX、Visual、SVG、WoT，随后扩展 API/Device/CLI。每个 case 必须真正
`COMPLETE`，不能只证明它进入了相同 contract/trace 管线。

核心指标：

```text
task success
steps
observations and targeted observations
model calls and visual calls
latency
fallback and wrong-route count
human confirmations
unknown-effect handling
batch utilization and observation barriers
binding-cache hit/currentness rejection
long-horizon constraint retention and ask-user correctness
```

当默认产品路径实现本文短闭环、正向矩阵通过、旧事务平台退出默认 imports/call
path，且十五条局部不变量仍有证据时，目标架构才算完成。

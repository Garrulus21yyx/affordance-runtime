# Runtime 主链收敛审查与旧链退出计划

> **Lifecycle:** CURRENT REVIEW / CONVERGENCE RECORD
> **Semantic authority:** false
> **Reviewed branch:** `codex/migrate-world-interaction-capabilities`
> **Reviewed HEAD:** `9663cdcdf7822462af5440845a50ed6fc3ad07f5`
> **Reviewed state:** 含 2026-08-13 未提交工作树修改；本文记录该工作树快照，不是 clean-SHA closure attestation
> **Review date:** 2026-08-13
> **Target authority:** [Target AgentLoop Authority Map](../task-execution-authority-map.md)
> **Implementation truth:** [Implementation Status](../implementation-status.md)

本文记录一次 repository-wide、architecture-first 的收敛审查，回答四个问题：

1. 当前自然语言任务实际上从哪里进入、如何走到 GUI 动作；
2. 新旧运行时为什么同时存在且容易互相回流；
3. 下一步如何得到一条唯一、可恢复、可 benchmark 的产品主链；
4. 旧运行时及其测试在什么条件下退出，而不是按日期或测试数量决定。

本文是事实复核和实施建议，不替代目标架构、当前实施状态或 active queue。本文不声明旧链已经可以删除，也不声明新链已经通过 live benchmark closure。

## 0. 审查后实施进度

2026-08-13 已完成第一个非默认收敛切片：

- 新增 target-owned `NaturalLanguageTaskRequest + TaskBoundary -> ThinTaskIntake -> TaskIntakeOutcome`；
- intake 结果闭合为 `ReadyTask / TaskInputRequired / TaskPolicyRejected / TaskUnsupported`；
- 新增生产 `TargetRuntime` composition root，统一拥有 `AgentLoop` 构造和 session start；
- BrowserGym target adapter 不再直接构造 `TaskGoal`，而是把公开 goal 与 reviewed benchmark boundary 交给 `ThinTaskIntake`；
- target benchmark runner 不再直接构造 `AgentLoop/AgentEpisodeRunner`，而是通过 `TargetRuntime`；
- model-conformance benchmark 也已迁移到 `TargetRuntime`，architecture gate 会拒绝任何 benchmark module 重新直接构造 `AgentLoop/AgentEpisodeRunner`；
- 根 Python API 增加显式 target 类型导出，但根 CLI 默认路径尚未切换；
- grounded-tools 现有门继续证明模型 wire 只含 tool/E-ref，不含 `action_id/binding_id`，adapter 在私有 catalog 内将 `ToolCall` 规范化为当前 `SelectAction`。

随后完成第二个非默认切片：

- `NaturalLanguageTaskRequest` 与 `TaskGoal` 都显式携带正整数 task revision；
- `AskUser` 的暂停结果携带 `UserInputRequest`，其中绑定 task、原 revision、context 和 accepted control-root identity；
- `TargetRuntime.submit_user_input` 先让完整的新请求重新经过 `ThinTaskIntake`，只把 `ReadyTask` 交给 session；
- `AgentRunSession.resume_user_input` 只接受同 task 的恰好下一版 revision，并对错误 pending ID、重复提交、跨 task、跳版、terminal session 和缺失环境 revision port 返回 typed rejection；
- 环境通过 `revise_task` 更新缓存的 task authority，但不 reset 物理 GUI；随后旧 task evaluation、LocalObjective、context、ActionSpace、page、feedback 和 progress projection 全部失效；
- AskUser control root 通过独立的 typed user-input continuation 恰好消费一次；`SENT_UNKNOWN` 导致的 `WAITING_USER` 没有 `UserInputRequest`，不能误走 clarification 恢复；
- 集成、reducer state-machine 与 Hypothesis 性质测试覆盖 happy path、重复/错误/跳版提交、零执行和 context revision 更新。

当前仍未实现：

- protocol `supported_decisions/required_decisions` 启动检查；
- objective `NotRequired/NeedsUserInput/Unsupported`；
- action/objective adapter 静态类型拆分；
- root CLI default cutover、legacy test inventory 或 legacy 删除。

因此下文“缺少通用 target intake”“benchmark 拥有 AgentLoop 构造”和“`WAITING_USER` 不可恢复”的诊断应作为已处理的原始缺口阅读；协议能力、objective 结果代数、更高层产品默认入口和旧链退出仍然开放。

本切片的离线验证为：Ruff、`git diff --check`、67 个 focused architecture/documentation/intake/runner/tool/decision tests，以及 full suite `2389 passed, 27 skipped in 92.15s`。工作树非 clean SHA，未运行 live benchmark，也不产生 default-cutover 或 generalization 声明。

第二个 continuation 切片的最终离线验证为：84 个 architecture/documentation/intake/continuation/session focused tests，以及 full suite `2400 passed, 27 skipped in 92.93s`。它仍是 non-default implementation evidence，不是 live benchmark、默认切换或旧链删除证据。

## 1. 审查结论

当前目标 `AgentLoop` 的内部短循环已经相对清楚：观察、生成当前合法动作、投影一次性上下文、得到类型化决策、准入、绑定、执行一次、取得新观察、独立评估、更新控制状态。核心局部合同和性质测试并非失控。

真正不清楚的是短循环外层：

- 安装后的根 CLI 和公共 Python API 仍以旧 `Coordinator` 为默认；
- 新 `AgentLoop` 没有通用自然语言 thin-intake 和产品 composition root；
- BrowserGym target adapter 直接把 benchmark goal 包装成 `TaskGoal`，并由 adapter/manifest 补充 effect 和 risk；
- benchmark runner 成了新运行时最完整的组装入口；
- `WAITING_USER` 可以产生但不能在同一 `AgentRunSession` 中提交用户答案并继续；
- 三种模型交互协议不只是编码格式不同，它们暴露的决策能力也不同；
- 配置 `LocalObjectiveProposalPort` 后，当前逻辑会在没有 active objective 时强制先调用 proposer，缺少 `not_required`；
- 旧工作流合同、共享基础设施和新 target-core 仍位于同一个根命名空间，物理边界弱于概念边界。

所以当前不是“一条很乱的链”，而是“两条各自大体自洽的链 + 一个尚未实现的目标入口合同”。清晰化工作的中心应从继续调整某个 planner/objective 类，转为建立唯一入口、唯一 composition、完整暂停恢复语义和可验证的旧链退出门。

## 2. 当前两条真实链路

### 2.1 默认旧链路

安装入口由 [`pyproject.toml`](../../pyproject.toml) 指向 `affordance_runtime.cli:main`。根 [`cli.py`](../../src/affordance_runtime/cli.py) 的 `run` 只接受 `pricing/settings/export` 三个 reference scenario，不接受任意自然语言。

旧 BrowserGym generalist 路径的完整自然语言链是：

```text
BrowserGym reset.goal
→ UserRequest
→ SourceEnvelope
→ LLMIntentCompiler.propose
→ SemanticAudit
→ TaskSpecAuthority.admit
→ AdmittedTaskSpec
→ StrictTaskPlanner / StepChoicePlanner
→ compose_run_coordinator
→ PerceptionStage
→ ProgressStage
→ PlanningStage
→ ActionStage
→ RecoveryStage
→ RuntimeCommitter / StateKernel
→ RunResult / benchmark projection
```

本地 CLI 更窄：scenario 已经预先决定 TaskSpec、effect、success 和 planner，`run_scenario` 再组装 `RunCoordinator`。公共 [`RuntimeClient`](../../src/affordance_runtime/runtime_client.py) 也只封装 `RunCoordinator`。根 [`__init__.py`](../../src/affordance_runtime/__init__.py) 导出的稳定 API 仍是 `RunRequest/RuntimeClient/ActionContract` 等旧合同。

### 2.2 非默认 target 链路

当前 BrowserGym target adapter 在第一次 reset 时读取公开 `goal`，直接创建 `TaskGoal`，同时写入 benchmark profile 决定的 `allowed_effects`、`forbidden_effects`、`risk_profile` 和 loop budget。它没有经过通用 `UserRequest -> Thin Intake -> TaskGoal` 实现。

之后实际链路是：

```text
BrowserGym reset.goal
→ adapter 直接构造 TaskGoal
→ benchmark case/task/composition factories
→ AgentEpisodeRunner.start
→ AgentLoop.start
→ WorldEnvironment.reset(TaskGoal)
→ WorldObservation
→ TaskEvaluator
→ ActionSpaceBuilder(TaskGoal + current WorldObservation)
→ optional LocalObjectiveProposalPort
→ Runtime 建立/刷新 one local_objective_state
→ ContextBuilder
→ disposable AgentContext
→ AgentPolicy.decide
→ typed AgentDecision
→ context/current-page/local-objective admission
→ risk / semantic confirmation
→ ActionBinder
→ BoundActionRequest
→ WorldEnvironment.execute once
→ ExecutionOutcome(ActionResult + post-action acquisition)
→ fresh WorldObservation or admitted capture fallback
→ ActionEvaluator + TaskEvaluator
→ ControlTransition + AgentLoopState
→ continue / reobserve / wait / ask / confirmation / terminal
→ benchmark case projection and acceptance
```

这条内部链路的主要 owner 已经明确：

| 责任 | 当前 owner | 判断 |
|---|---|---|
| 稳定任务边界 | `TaskGoal` | 合同清楚，但缺通用 intake owner |
| 当前世界 | `WorldEnvironment` / `WorldObservation` | 清楚 |
| 当前合法动作 | `ActionSpaceBuilder` | 清楚，按 TaskGoal effect 和 current binding 过滤 |
| 模型投影 | `ContextBuilder` | 清楚，一次性、带 context identity |
| 当前选择 | `AgentPolicy` | 合同清楚，但协议能力不一致 |
| rolling relevance | one `local_objective_state` | owner 已统一，触发条件仍不清楚 |
| 风险和确认 | `RiskPolicy` / confirmation contracts | 核心确认 continuation 已实现 |
| 私有执行路由 | `ActionBinder` / environment | 清楚，模型不持有 selector/binding |
| dispatch truth | `ActionResult` | 清楚，区分 `NOT_SENT/SENT/SENT_UNKNOWN` |
| effect/task truth | `ActionEvaluator` / `TaskEvaluator` | 清楚，与 receipt/model narration 分离 |
| 控制状态 | `AgentLoopState` / `ControlTransition` | reducer 性质保护较强 |
| 产品组装 | benchmark target runner | 不应由 benchmark 长期拥有 |

## 3. 自然语言目标链应该是什么

目标主链应只有一个入口代数：

```text
UserRequest
→ ThinTaskIntake.compile
→ TaskIntakeOutcome
   ├─ Ready(TaskGoal, IntentContext)
   ├─ NeedsUserInput(question, requested_fields, draft_revision)
   ├─ PolicyRejected(reason_code)
   └─ Unsupported(reason_code)
→ TargetRuntime.start
→ AgentRunSession
→ AgentLoop short loop
→ AgentResult or typed pause
```

`ThinTaskIntake` 负责从用户来源中确定稳定任务语义，但不得生成 DOM ID、E-ref、selector、坐标、当前 action ID 或执行顺序。

`TaskGoal` 是唯一稳定任务 authority，至少拥有：

- instruction 和 public inputs；
- constraints；
- allowed/forbidden effects；
- risk profile；
- success/evaluation boundary；
- requested outputs 和 material bindings；
- loop budget；
- task revision 和来源 lineage。

`IntentContext` 只提供有界来源摘录和推理帮助，不得授权 effect 或创建 GUI identity。

`LocalObjective` 只在第一次观察之后表达当前滚动执行约束，例如 sequence、set 或 aggregate。它不得成为第二份 whole-task meaning，不得扩张 `TaskGoal` legality，也不得拥有 private binding 或 terminal completion。

## 4. 根因模型与重复 reopening

近期历史中，同一 semantic-authority 子系统发生了多轮加入、撤销和 revert，包括：

```text
make task plan the sole semantic authority
→ unify observation-grounded objectives
→ require semantic objective before grounded actions
→ restore task plan authority to agent loop
→ revert restore task plan authority to agent loop
```

这些不是相互独立的局部缺陷。共同机制是：

```text
缺通用 target intake 和产品 composition root
→ TaskGoal 的来源/准入留给 benchmark 或调用者
→ whole-task semantics 在 TaskSpec、TaskPlan、VerifiedTaskState、
  policy decision、LocalObjective 之间寻找 owner
→ 某一局部 owner 通过自己的测试
→ 另一入口、协议或任务类型暴露冲突
→ reopen / revert / 再造下一种 owner
```

分类如下：

| 类别 | 诊断 |
|---|---|
| architecture defect | 没有唯一 target product ingress 和 composition root；benchmark 拥有最完整组装 |
| open contract | thin intake outcome、task revision、user-input continuation、objective need、protocol required capabilities 未闭合 |
| duplicated truth | 根 CLI/API 代表旧链；target benchmark 代表新链；文档代表未来目标 |
| verification defect | 局部性质/红线多，缺入口拓扑、协议能力、暂停恢复和 composition identity 的集成门 |
| documentation/governance | 文档诚实说明 non-default，但目标、状态、历史记录过多，读者仍需自己推断实际入口 |
| environmental failure | 未发现可解释本轮架构问题的环境故障 |
| over-strict acceptance | 不应要求生产级持久化、event sourcing 或全任务完备性；应以声明范围和 benchmark 为准 |

## 5. 已确认的具体缺口

### 5.1 target intake 已有首个显式边界，产品语义扩充仍开放

审查时文档声明 `UserRequest -> Thin Intake -> TaskGoal + IntentContext`，代码中没有对应的通用 owner。第一个实施切片已新增 target-owned `NaturalLanguageTaskRequest/TaskBoundary/ThinTaskIntake`，BrowserGym target goal 已通过该 owner 生成 `TaskGoal`。旧 `TaskSpec -> TaskGoal` one-way legacy projection 仍不是 target 产品入口。

当前 benchmark manifest/adapter 仍提供 reviewed effect/risk boundary，这是明确的调用方 authority 而非自然语言推断。后续仍需补齐用户 clarification 后的 task revision 和通用应用层 boundary 提供者；intake 不应靠关键词自行发明 effect authority。

### 5.2 target composition root 已实现非默认切片，默认产品接线仍开放

审查时 `AgentLoop` 的完整组装主要出现在 `benchmarks/target_loop/runner.py`。第一个实施切片已新增下列 `TargetRuntime` owner，并让 target benchmark 通过它构造和启动 session：

```python
TargetRuntime(
    intake=...,
    environment_factory=...,
    decision_ports=...,
    action_evaluator=...,
    task_evaluator=...,
    risk_policy=...,
)
```

benchmark 仍负责 instrumentation decorator、manifest、environment adapter、seed、测量和 acceptance，但不再直接构造 `AgentLoop/AgentEpisodeRunner`。根 Python API 已显式导出 `TargetRuntime`；根 CLI 和旧 `RuntimeClient` 默认尚未切换。

### 5.3 审查时 `WAITING_USER` 状态不可恢复；现已闭合 AskUser continuation

`AskUser` 会将问题写入 `AgentLoopState.pending_user_question` 并返回 `WAITING_USER`。`AgentRunSession` 只有 `resolve_confirmation`，没有提交用户答案、修订 `TaskGoal/IntentContext`、清除 pending question 并继续的 API。`run_until_pause` 在 `last_result` 存在时直接返回已有结果。

因此当前状态代数实际是：

```text
RUNNING → WAITING_CONFIRMATION → RUNNING/terminal
RUNNING → WAITING_USER → 无 continuation API
```

目标必须闭合为：

```text
RUNNING
  ├─→ WAITING_CONFIRMATION ── resolve_confirmation ──→ RUNNING/terminal
  ├─→ WAITING_USER ── submit_user_input(new task revision) ──→ RUNNING/terminal
  ├─→ WAITING_ENVIRONMENT ── admitted refresh/timer ──→ RUNNING/terminal
  └─→ DONE/BLOCKED/FAILED/CANCELLED
```

所有 continuation 必须一次消费、绑定原 pending identity；新 task/context revision 应使旧 context、decision、ActionSpace 和 binding 确定性 stale。

当前实现已经满足这条 bounded contract。需要特别区分两种相同外部 status：只有 accepted `AskUser` root 会产生可提交的 `UserInputRequest`；执行已发送但效果未知产生的 `WAITING_USER` 仍是 fail-closed 的未知效果状态，不接受 task-revision clarification 作为效果判定。

### 5.4 模型协议隐藏了能力差异

当前 factory 支持：

- `structured_package.v2`；
- `dynamic-tools`；
- `grounded_tools.v2`。

structured decision schema 包含 `SelectAction/RequestObservation/RequestActionPage/AskUser/ProposeDone/Wait/Abort`。dynamic/grounded action catalog 当前主要提供 action、observation 和 paging；grounded objective catalog 只提供 objective proposal。更换 protocol 因而会改变 Agent 的可达状态和控制能力，而不只是改变 JSON/tool transport。

需要显式合同：

```python
class DecisionCapability(StrEnum):
    SELECT_ACTION = "select_action"
    REQUEST_OBSERVATION = "request_observation"
    REQUEST_ACTION_PAGE = "request_action_page"
    ASK_USER = "ask_user"
    PROPOSE_DONE = "propose_done"
    WAIT = "wait"
    ABORT = "abort"

class AgentDecisionAdapter(Protocol):
    supported_decisions: frozenset[DecisionCapability]
```

manifest/composition 同时声明 `required_decisions`。启动时若有缺失，返回 typed `UnsupportedComposition`，不得运行到中途再把能力缺失归因给模型或任务。

当前视觉 benchmark 使用 `grounded_tools.v2`，可以将它定为 benchmark 主协议；其他协议保留为 compatibility/ablation，直到它们被删除或证明具有同一声明能力。不同能力集合的结果不得合并成同一主线能力声明。

### 5.5 LocalObjective proposal 缺少“不需要”结果

当前 `local_objective_complete(None)` 为 true。只要 composition 配置 proposer，初始轮和每个 objective 完成后的下一轮都会先进入独立 proposal phase、消耗一次 turn；简单 click/fill/select 任务也无法表达“不需要 objective”。proposal 失败还会在 action policy 运行前终止任务。

应使用闭合结果代数：

```text
Proposed(LocalObjective)
NotRequired(task_revision, observation_scope)
NeedsUserInput(question, requested_fields)
Unsupported(reason_code)
PolicyFailure(kind, retryable)
```

`NotRequired` 必须有 task-revision 或明确 scope，避免每轮重复询问。只有 manifest/task capability 明确声明需要 sequence/set/aggregate 时，或者一个经过验证的 `ObjectiveNeedPolicy` 判定需要时，才配置/调用 proposer。

### 5.6 action/objective adapter 的类型边界不够硬

当前 `GroundedToolDecisionAdapter` 通过 `phase` 同时服务 action 和 objective，返回 union，再由 factory 用 `cast` 声称当前实例满足相应 port。这把错误 composition 推迟到运行时。

应拆成公开静态类型：

```text
GroundedActionAdapter
  generate(ActionDecisionRequest)
  → ResolvedModelDecision | ModelFailure

GroundedObjectiveAdapter
  generate(ObjectiveProposalRequest)
  → ResolvedLocalObjectiveProposal | ModelFailure
```

两者可以共享 private transport/message/catalog utilities，但不能共享一个 phase-discriminated public return type。

### 5.7 物理命名空间仍然混合

target-core 已有 import redline，避免直接依赖 `StateKernel/RuntimeCommitter` 等主要 legacy owner，这是有效进展。但根包同时容纳：

- 旧 transactional runtime；
- 新 `agent/task/world/model_boundary/model_policy`；
- 两边共享的 immutable/schema/model transport/visual utilities；
- legacy-only projection 和 compatibility helpers。

例如 `model_boundary/projection.py` 仍保留仅测试使用的旧 `TaskPlan -> AgentPlanView` projection；target task/model/visual 模块仍从根包导入共享或历史命名的 utility。长期应区分：

```text
affordance_runtime/core/          shared value/schema/transport utilities
affordance_runtime/target/        或现有 agent/task/world 等明确 target 包
affordance_runtime/legacy/        transactional Coordinator runtime
affordance_runtime/benchmarks/    manifests/adapters/measurement only
```

不要求为改目录而一次性重写；先通过 import rules 形成逻辑边界，再在消费者归零时移动或删除。

## 6. 测试现状与迁移原则

本次工作树全套离线验证：

```text
2381 passed, 27 skipped in 91.60s
```

另外通过：

- `git diff --check`；
- 30 个 architecture tests；
- 82 个 reducer/AgentLoop/protocol focused tests；
- 70 个本次 objective/protocol 变更相关 tests。

粗粒度文件扫描显示：326 个 Python test files 中，约 60 个文件提到 `StateKernel/RuntimeCommitter/RunCoordinator/TaskSpec/TaskPlan/ActionContract` 等 legacy marker，约 101 个文件提到 `AgentLoop/TaskGoal/WorldObservation/ActionSpace/BoundActionRequest/ControlTransition` 等 target marker。两组有重叠，marker 统计不等于精确归属，但足以证明旧测试不是可忽略的小尾巴。

### 6.1 不按“旧测试数量”决定保留旧链

测试是 claim 的证据，不是实现的永久所有权。删除旧链前，应逐项判断测试在证明什么：

| 测试类别 | 例子 | 处理 |
|---|---|---|
| shared invariant | schema strictness、effect safety、source lineage、secret stripping、single-send、typed failures | 将性质移植到 target owner 后保留；不因旧 fixture/API 永久保留旧实现 |
| target contract | AgentLoop、ActionSpace、fresh observation、binding currentness、evaluation、ControlTransition | 保留并增强为主线 gate |
| legacy implementation behavior | RuntimeDelta commit 顺序、StateKernel projection、Coordinator stage choreography、TaskPlan-specific progress | legacy 存续期继续通过；物理删除 legacy 时一起删除，不逐字移植 |
| reusable scenario/fixture | pricing/settings/export、BrowserGym fixtures、surface adapters | 保留场景意图，改接 target composition；先迁 scenario，再删旧 gold path |
| benchmark/evidence | target-loop harness、external breadth、immutable reports | benchmark 必须调用产品 composition；历史 evidence 保留但不执行旧 runtime |
| duplicate/example test | 同一不变量的大量固定 case | 用 property/state-machine/generative test 证明共享性质后缩减 witness 列表 |

### 6.2 建立可机械检查的测试清单

建议先增加 pytest marker 或目录级 manifest：

```text
target            目标主链 release gate
shared_invariant  与具体 runtime 无关，双方迁移期都可复用
legacy           只保护 transactional baseline
historical       不进入日常执行，只保留证据/fixture
```

每个 legacy 测试文件至少登记：

```text
protected_claim
current_owner
target_owner_or_delete_reason
migration_status
legacy_deletion_blocking: true/false
```

不要先批量移动目录再理解测试。优先从 claim/owner 映射开始，避免把 `TaskPlan` 或 `StateKernel` 的实现形状原封不动搬进 target。

### 6.3 CI/本地 gate 的迁移顺序

迁移期间：

```text
target + shared_invariant = 主线必须通过
legacy = 在其仍被声明支持时也必须通过
historical evidence = 不作为代码执行 gate
```

默认切换后：

```text
target + shared_invariant = 默认 release/benchmark gate
legacy = 明确隔离的 deprecation lane；只接受 containment/deletion 修改
```

物理删除 commit 中：

1. 先确认 shared claims 已由 target tests 覆盖；
2. 删除 legacy production owners；
3. 同一 coherent slice 删除只证明被删行为的 tests；
4. 保留/迁移有价值的 fixtures 和 scenario acceptance；
5. 删除 legacy marker/lane；
6. 重新运行 full suite、held-out benchmark 和 import/topology gates。

## 7. 收敛实施顺序

### Phase 0 — 固定事实与边界（现在）

状态：本审查完成记录，但不恢复任何 closure 声明。

动作：

- 冻结旧 Coordinator 的新产品能力；只允许 containment、兼容和删除准备；
- 固定 `TaskGoal` 为 whole-task authority、`LocalObjective` 为 rolling execution constraint；
- 为 tests 建立 target/shared/legacy/historical inventory；
- 新增入口和拓扑 gate，防止 benchmark 再造第二个 composition root。

退出条件：所有相关测试和入口都有 owner 分类；没有未解释的第三条自然语言链。

### Phase 1 — 建立唯一 target 产品入口

动作：

1. 实现 `ThinTaskIntake` 和闭合 `TaskIntakeOutcome`；
2. 实现 `TargetRuntime` composition root；
3. 实现 `TargetRuntime.submit_user_input`、`AgentRunSession.resume_user_input`、task/context revision 和一次性 typed continuation（已实现；cancellation 继续沿用 session terminal latch）；
4. 让 target benchmark 从同一个 production composition 构造 loop，只注入 manifest、adapter、seed 和 instrumentation；
5. 为 root API 增加显式 target entry，但暂不删除旧 entry。

退出条件：任意已支持 `UserRequest` 可以不经过 benchmark-specific code 进入 target loop；clarification/confirmation/cancellation 都有完整合法 transition 和性质测试。

### Phase 2 — 收敛模型协议

动作：

1. 将 `grounded_tools.v2` 定为当前视觉 benchmark 主协议；
2. 所有 adapter 声明 `supported_decisions`；
3. manifest/composition 声明并启动检查 `required_decisions`；
4. 拆分 action/objective adapter 静态类型；
5. objective outcome 增加 `NotRequired/NeedsUserInput/Unsupported`；
6. 只有任务能力或 manifest 明确需要时才组装 proposer；
7. structured/dynamic 协议标为 compatibility/ablation，结果不与不同能力 profile 合并。

退出条件：协议切换只改变已声明 transport/presentation，不会暗中改变 benchmark 所需的 control algebra；简单任务不被强制双模型调用。

### Phase 3 — 默认切换，而不是立即物理删除

动作：

- 根 CLI 的普通自然语言 `run` 进入 `TargetRuntime`；
- 根公共 API 导出 target contracts/service；
- 旧 scenario/Coordinator 入口改为显式 `legacy` namespace、command 或 profile；
- pricing/settings/export 的有价值 acceptance scenario 改接 target composition；
- 所有当前主线 BrowserGym benchmark 使用 production composition；
- 文档状态更新为 `DEFAULT_CUTOVER`，而不是继续写 non-default。

退出条件：

- root CLI/API、内部 harness 和外部 benchmark 对同一输入使用同一 target composition identity；
- supported scope 的 target unit/property/integration/full suite 全绿；
- clean SHA 上完成预声明 threshold 的 held-out、多 seed benchmark；
- 旧链没有默认入口，且没有新功能继续进入旧链；
- fresh-context architecture review 能仅从入口和代码得到同一主链答案。

### Phase 4 — 物理删除旧链

Phase 3 通过后立即做依赖归零审计；不设置长期“双默认”观察期，也不按日历等待。满足下列全部条件即可进入物理删除：

1. production root、public API 和非 legacy benchmark 对 `Coordinator/RuntimeCommitter/StateKernel` 的消费者为零；
2. 所有仍有价值的 reference scenario 已经在 target composition 上运行；
3. 每个 legacy test 已分类为 `migrated shared claim`、`retargeted scenario` 或 `delete with legacy behavior`；
4. target 的 intake、user continuation、confirmation、failure、currentness、single-send、evaluation 和 projection properties 已覆盖相应共享不变量；
5. held-out benchmark 没有为了单个 case 新增 production routing branch；
6. implementation status、tests、docs、CLI help 和 package exports 同意 target 已是默认；
7. 独立 fresh-context review 未发现新的 authority owner 或隐藏入口。

物理删除顺序：

```text
legacy CLI/API adapters
→ legacy benchmark runners
→ Coordinator stages and composition
→ RuntimeDelta/RuntimeCommitter/StateKernel projections
→ TaskPlan-only runtime machinery
→ legacy-only contracts/utilities
→ legacy-only tests
→ empty compatibility projections and imports
```

若某个 utility 同时被 target 使用，应先移动到明确的 shared/core owner，而不是随 legacy 删除，也不能因此保留整条 legacy runtime。

## 8. 旧链什么时候删：明确回答

不是现在，也不是等“所有旧测试自然消失”。

- **现在到 Phase 2：** 旧链仍是当前默认，因此代码和 legacy tests 必须继续通过，但禁止新增产品能力。
- **Phase 3：** 先做逻辑删除——target 成为根 CLI/API/benchmark 默认，旧链只能显式调用。
- **Phase 4：** 在一个 clean-SHA target-default held-out benchmark gate 和 fresh-context review 通过、消费者及测试 claim 映射归零后，立即物理删除旧链。

这个门既避免现在过早删除导致失去可运行 baseline，也避免以“还有很多旧测试”为理由无限保留两套架构。

## 9. 必须新增的收敛门禁

### 9.1 入口拓扑

- 根 CLI 普通 run 进入 `ThinTaskIntake -> TargetRuntime -> AgentLoop`；
- public API 不默认构造 `RunCoordinator`；
- benchmark composition 必须复用 production factory；
- target core 不导入 legacy namespace；
- legacy code 不得成为 target intake 的隐藏 preparer。

### 9.2 状态机性质

- `WAITING_USER` 只能由匹配 pending identity 的用户输入继续一次；
- task revision 更新后旧 context/action/binding 必定 stale；
- confirmation 和 user-input continuation 不得重复消费；
- terminal states absorbing；
- `SENT/SENT_UNKNOWN` 不自动重复 dispatch；
- unsupported acquisition/protocol/task semantics typed fail-closed。

### 9.3 协议一致性

- adapter 宣告能力与实际 catalog/schema 相等；
- composition required capabilities 必须是 adapter capability 子集；
- action phase 不得产生 objective；objective phase 不得产生 effectful action；
- 相同 declared capability profile 才能比较/合并 benchmark；
- `NotRequired` 不造成同一 task revision 的重复 objective proposal。

### 9.4 benchmark

- manifest 决定 supported task/effect/protocol/objective scope；
- adapter 只提供环境事实和执行，不拥有任务语义分支；
- benchmark instrumentation 只观察，不改变 Runtime 行为；
- clean SHA、固定 profile、原始 per-case evidence 和 failure attribution 分开保存；
- unit/property gates 保护合同，真实 benchmark 作为泛化和鲁棒性的最终实证。

## 10. 非目标

本计划不要求：

- 引入 event sourcing、durable ledger、通用 workflow platform 或生产级 checkpoint；
- 把旧 `TaskPlan/StateKernel` 逐类重写到 target；
- 将每个旧测试一比一翻译成新测试；
- 在删除旧链前支持所有未来 GUI 任务；
- 以代码行数或测试数量衡量架构完成；
- 为 benchmark 个例增加 Runtime task-name/case-name 分支。

只需要闭合声明支持范围：唯一入口、明确 owner、完整状态代数、typed unsupported handling、真实 benchmark 证据。

## 11. 可证伪的最终退出标准

只有以下条件同时成立，才可以把本次争议子系统重新声明为 verified closed：

- 一条 causal explanation 能解释已知 authority reopenings，或证据证明它们互相独立；
- 自然语言只有一个默认 target ingress；
- `TaskGoal` 是 whole-task 唯一 authority，projection 和 LocalObjective 不成为第二 truth；
- session 的 run/pause/resume/confirm/cancel/terminal transition 代数闭合；
- 每个模型协议的 supported/required decision capabilities 显式且启动时验证；
- objective proposal 对普通任务有 typed `NotRequired`，不强制额外 production branch/model call；
- target、shared、legacy tests 均有明确 claim owner，legacy 删除不丢共享性质；
- product composition 和 benchmark composition 是同一个 owner；
- held-out/generated cases 不需要逐 case 修改 production code；
- clean-SHA implementation、tests、docs、CLI/API、benchmark evidence 与 fresh-context review 一致。

在这些门通过前，最诚实状态是：

```text
TARGET INTERNAL LOOP INTEGRATED NON-DEFAULT
PRODUCT INGRESS / SESSION CONTINUATION / PROTOCOL CAPABILITY OPEN
LEGACY DEFAULT RETAINED, FEATURE-FROZEN
CONVERGENCE IMPLEMENTATION NOT YET VERIFIED
```

## 12. 实施记录：模型 action 协议能力切片

2026-08-13 本切片实现了 Phase 2 的前三个边界，但不代表整个迁移关闭：

- 当前 GUI visual benchmark 主协议由
  `PRIMARY_BENCHMARK_ACTION_PROTOCOL = grounded_tools.v2` 唯一声明；Step-13 gate
  不再复制字符串。历史冻结的 structured breadth profile 保持 compatibility 证据，未改写历史口径。
- `structured_package.v2` 显式支持完整的七种 `DecisionCapability`；
  `dynamic_tools.v1` 和 action phase 的 `grounded_tools.v2` 只支持
  `select_action / request_observation / request_action_page`。objective phase 不冒充 action
  capability。
- `BenchmarkComposition.required_decisions` 将 benchmark 所需控制能力传给
  `TargetRuntime`。构造时若不是 declared capability 的子集，Runtime 在 session、环境 reset
  和模型调用前抛出带 required/supported/missing 事实的 typed
  `UnsupportedCompositionError`。
- provider orchestrator、model policy、pacing 和 instrumentation 包装链保持能力声明透明；
  fallback ports 若声明不同能力会在 orchestrator 构造时失败。
- 当前 primary benchmark composition 要求 tool action 三种控制能力；adapter 不能根据 task
  名称或 case 名称推断、扩大该集合。

仍未完成、不能混入本切片 closure claim 的工作：

- action adapter 与 objective adapter 的静态类型拆分，以及删除 `phase + cast`；
- objective proposer 的 `NotRequired / NeedsInput / Unsupported` outcome 代数；
- product 默认入口切换、target-default benchmark 和 legacy 物理删除门禁。

因此此时更准确的状态是：

```text
MODEL ACTION PROTOCOL CAPABILITIES IMPLEMENTED, OFFLINE VERIFIED
OBJECTIVE PROTOCOL / PRODUCT DEFAULT / LEGACY DELETION OPEN
```

## 13. 实施记录：objective outcome 与 adapter 静态拆分切片

2026-08-13 在 action capability 切片之后继续实现 Phase 2 的 objective 边界：

- objective proposer 的闭合结果代数现在是
  `LocalObjectiveProposal / LocalObjectiveNotRequired / LocalObjectiveNeedsInput /
  LocalObjectiveUnsupported / PolicyFailure`。`NotRequired` 由当前 context scope 产生，Runtime
  将其按当前 task revision 记录，避免每个 action turn 重复调用 proposer；task revision 更新会清除该记录。
- `NeedsInput` 不伪装成 effectful action。Runtime 将它归一化为一个无副作用的 typed
  `AskUser` control root，因此继续复用一次性 request identity、consecutive task revision、重复提交拒绝和
  terminal immutability 合同。`Unsupported` 以闭合 reason code 进入 `BLOCKED`，不归因成模型 provider failure。
- benchmark 的启用事实由 `BenchmarkCase.local_objective_requirement` 持有并进入 manifest digest。
  composition 只有在 requirement 为 `REQUIRED` 时才能提供 proposer；反过来 requirement 为
  `REQUIRED` 却未配置 proposer 也会在 `AgentDecisionPorts` 构造时失败。Step-13 targeted manifest
  显式声明该 requirement；普通 benchmark/task composition 默认 `NOT_REQUIRED`，不会产生额外模型调用。
- `GroundedActionAdapter.generate` 只返回 `ResolvedModelDecision | ModelFailure`；
  `GroundedObjectiveAdapter.generate` 只返回 `ResolvedLocalObjectiveOutcome | ModelFailure`。
  factory 已删除 `phase + cast`。两者只共享 private transport/repair machinery，使用不同 catalog builder、
  resolver、schema version、compatibility key 和公开 return type。
- objective transport schema 升级为 `local-objective-proposal.v2`，grounded objective catalog
  显式提供 proposal/not-required/needs-input/unsupported 四个 outcome tools。旧
  `GroundedToolDecisionAdapter` 名称暂时只是 `GroundedActionAdapter` 的 action-only alias，不再接受
  phase，也不能被组合为 objective port；它将在 consumer 归零后删除。

仍未完成：product 默认入口切换、target-default held-out benchmark、旧链逻辑/物理删除及最终
fresh-context review。因此当前状态是：

```text
MODEL ACTION + OBJECTIVE PROTOCOL BOUNDARIES IMPLEMENTED
OFFLINE FULL-SUITE VERIFIED
PRODUCT DEFAULT / LEGACY DELETION OPEN
```

The live consumer-by-consumer cutover inventory is maintained in
[`2026-08-13-target-cutover-consumer-map.md`](./2026-08-13-target-cutover-consumer-map.md).

## 14. 实施记录：target composition root

2026-08-13 新增 product-owned `compose_target_runtime`，它统一组装
`AgentDecisionPorts -> TargetRuntime`，并集中执行 objective requirement、decision capability、
intake、risk、action-space、binding、context 和 wait-controller 的 composition validation。
`benchmarks/target_loop` 现在只在端口边界添加 instrumentation，再调用同一个 product factory；
架构门禁禁止 target composition owner 导入 benchmark namespace，也禁止 benchmark 直接构造
`AgentLoop/AgentEpisodeRunner/TargetRuntime`。

根 package 已显式导出 `compose_target_runtime`、`TargetRuntime`、自然语言 request/start outcome
和 user-input continuation contracts。CLI `run` 与旧 `RuntimeClient` 仍属于 legacy 默认，消费者映射中
已明确标注；因此这一步是“单一 target 构造 owner + 显式 target API”，不是默认切换。

离线验证：`2422 passed, 27 skipped`，Ruff 和 diff check 通过。live benchmark 未在本切片运行，
product default 与 legacy 删除继续保持 open。

## 15. 实施记录：target consumer composition 收敛

2026-08-13 对整个 `src/affordance_runtime` 再次扫描后，发现
`benchmarks/model_conformance/runtime_decision_matrix.py` 和 `loop_attempt.py` 仍直接构造
`TargetRuntime`。两处现已改为调用 product-owned `compose_target_runtime`；模型策略、evaluator、
context builder 和 wait controller 仍按原值注入，因此此改动只收敛装配 authority，不改变决策语义。

架构门禁现在覆盖完整 source tree：除 `agent/composition.py` 这个 owner 外，任何 shipped module
直接调用 `TargetRuntime(...)` 都会失败；benchmark namespace 同时禁止直接构造
`AgentLoop / AgentEpisodeRunner / TargetRuntime`。focused verification 为 `15 passed`，全量离线验证为
`2423 passed, 27 skipped`。CLI/default、live benchmark 和 legacy 删除仍然 open。

## 16. 实施记录：target public client

2026-08-13 新增 `TargetRuntimeClient` 作为显式产品入口。它接收
`WorldEnvironment + NaturalLanguageTaskRequest`，通过已组合的 `TargetRuntime` 完成 intake、session
创建并运行到第一次 pause/terminal；`TargetRuntimeRunOutcome` 同时持有 typed intake、session 和 result，
非 ready intake 不能伪造 session/result。用户补充输入和 confirmation continuation 继续委托同一 session，
client 不重建 loop，也不持有第二套状态 authority。

原 `RuntimeClient` 的 import 和 Coordinator 行为保持兼容，同时新增明确的
`LegacyRuntimeClient` 名称。target client 的架构门禁禁止它依赖 legacy coordinator/composition；这一步选定了
public client 语义，但没有改变根 CLI 默认。focused verification 为 `24 passed`，全量离线验证为
`2427 passed, 27 skipped`。

## 17. 实施记录：product action evaluator ownership

2026-08-13 进一步检查 CLI 切换所需的环境边界后确认，产品侧已经存在
`BrowserSession -> DomSurfaceAdapter -> UnifiedWorldEnvironment`，它实现 target 所需的 reset、capture、
currentness、execute 和 task revision；不需要复制 BrowserGym 环境。实际的反向依赖是机械 action evaluator
实现位于 `benchmarks/external_smoke`，使产品 composition 若复用它就必须依赖 benchmark namespace。

该实现现已原样提升为 product-owned `ProductionActionEvaluator`，只读取公开 before/after world evidence；
所有 shipped consumers 直接使用产品名称。`BrowserGymMechanicalActionEvaluator` 暂时保留为等价 compatibility
alias，以承接历史测试和外部 import，不再拥有算法。架构门禁保证产品 evaluator 不导入 benchmark。
focused verification 为 `31 passed, 8 skipped`，全量离线验证为 `2428 passed, 27 skipped`。
CLI/default 和 live benchmark 仍然 open。

## 18. 实施记录：product DOM structural effect evidence

2026-08-13 在准备 target CLI 时发现，原机械 evaluator 的 activate 分支要求 screenshot artifact；
普通 `DomSurfaceAdapter` 即使产生可靠结构化状态变化也只能得到 `UNKNOWN`。若直接接 CLI，链路可以启动，
但 DOM 点击后无法形成已验证 progress。

`ProductionActionEvaluator` 现在先检查目标的公开 before/after semantics，并且只在存在 changed fact、
current typed source lineage、structural assurance、source coverage 与 world coverage 均完整时确认
`structural_target_diff_v1` effect。没有结构化变化时不会凭 dispatch receipt 确认 no-effect；已有
`visual_diff_v1` 路径保持不变。

新增真实 Playwright E2E 通过
`compose_target_runtime -> UnifiedWorldEnvironment -> DomSurfaceAdapter -> ProductionActionEvaluator ->
ProductionTaskEvaluator` 完成一次 button activation。策略只看到并选择公开 action ID，selector/binding
仍由 Runtime 内部持有。focused verification 为 `15 passed`，全量离线验证为
`2429 passed, 27 skipped`。显式 target CLI、default cutover 和 live benchmark 仍然 open。

## 19. 实施记录：explicit target product CLI

2026-08-13 新增显式 `affordance-runtime target-run`，但未替换 legacy `run`。它从严格 JSON
stable boundary 构造 `NaturalLanguageTaskRequest`，先经同一个 `ThinTaskIntake` owner；只有
`ReadyTask` 才分配浏览器。空 completion authority、未知 boundary 字段和 private GUI inputs 均 fail closed。

产品 model composition 固定主协议为 `grounded_tools.v2`，并在浏览器分配前要求
`select_action / request_observation / request_action_page` 三种控制能力。模型选择公开 tool/action ID；
Runtime 仍独占 binding 和 executor route。

真实 CLI E2E 暴露 Sync Playwright 与 async model loop 不能直接同线程运行。原 benchmark-only
thread-bound proxy 已提升为 product-owned `ThreadBoundBrowserSession`：浏览器始终留在 owner thread，
async AgentLoop 通过有界同步代理调用。benchmark real-adapter support 改为复用该产品 owner，不再复制实现。

当前显式链路为：

```text
boundary JSON → ThinTaskIntake → ReadyTask → ThreadBoundBrowserSession
→ DomSurfaceAdapter → UnifiedWorldEnvironment → TargetRuntimeClient
→ grounded action selection → internal bind/execute → product evaluators → typed result
```

focused verification 为 `25 passed`；真实 Playwright `target-run` 完成一次 DOM activation；全量离线验证为
`2438 passed, 27 skipped`。旧 `run`、`RuntimeClient` compatibility、target-default live held-out gate 和
legacy 删除仍然 open。

## 20. 实施记录：reference target readiness gate

2026-08-13 对 pricing/settings/export 做真实世界证据核对后，三者均尚不能诚实切换：pricing 缺
interaction-only authority 以及静态文档/结构化输出投影；settings 的 DOM surface 只暴露 action button，
不拥有 `/api/state` authoritative persisted fact；export 缺 download materialization 和 hash/integrity
evidence。已有 confirmation lifecycle 只能授权动作，不能制造 completion evidence。

新增闭合 `ReferenceTargetBlocker` algebra、每场景 `ReferenceTargetReadiness` 和聚合
`require_reference_target_cutover_ready()`。ready 状态必须 blockers 为空且绑定一个 executable target
acceptance test；缺场景、重复/不完整 profile 或任何 blocker 都确定性 fail closed。该 readiness 只属于
entrypoint migration gate，架构门禁禁止它进入 agent/model-policy/world 控制面。

未来 settings HTTP fact source 必须与 DOM/Visual/WoT 一样作为 `SurfaceAdapter` 加入现有
`UnifiedWorldEnvironment -> WorldFusion`，仍然只产生一个 `WorldObservation`；禁止 evaluator 或 case
旁路查询 fixture oracle。focused verification 为 `14 passed`；全量离线验证为
`2443 passed, 27 skipped`。default cutover 和三项 capability remediation 仍然 open。

## 21. 实施记录：统一世界中的 authoritative HTTP state

2026-08-13 settings remediation 没有引入第二个 world 或 evaluator oracle。新增的
`HttpJsonSurfaceAdapter` 只接受产品侧显式注册的 endpoint authority 和 public fact projection
allowlist；endpoint 是 private configuration，raw response、未声明字段和 URL 均不进入
`SurfaceObservation`。adapter 没有 action binding，`execute` 永远返回 typed unsupported。

`ObservationOrchestrator` 对 `environment_state + authoritative` 请求现在选择 state source 为
required，同时把 structural DOM 作为 optional augmentation；两者在同一次 capture 中由
`WorldFusion` 形成唯一 `WorldObservation`。因此 settings 链路是：

```text
NaturalLanguageTaskRequest -> ThinTaskIntake -> initial DOM world
-> model SelectAction(public action_id) -> semantic confirmation
-> fresh private DOM bind -> execute once -> DOM post observation
-> model RequestObservation(environment_state, authoritative)
-> HTTP facts(required) + DOM(optional) -> one fused WorldObservation
-> ProductionTaskEvaluator -> authoritative completion evidence
```

真实 fixture/Playwright acceptance 暴露并修复了两个共享控制缺口：初始缺少所需高 assurance
事实时，`UNKNOWN` 原先在 policy turn 前一律暂停；现在只有当 environment 明确提供尚未采集、可满足
criterion 的 typed source 时才继续控制。其次，已发送的 medium-risk action 若 DOM 无法确认业务 effect，
但同一缺失 source 可澄清，则 Runtime 进入 observation-only uncertainty：允许 observation control，禁止
再次 `SelectAction`；选择正确来源后清除该状态，选择另一 effectful action 则确定性 blocked。整个过程
执行计数保持 1，不重放发送。

settings 的 readiness 现绑定可执行 acceptance
`tests/test_reference_target_settings.py::test_target_settings_confirms_action_then_completes_from_unified_authoritative_world`；
pricing 与 export blockers 仍使聚合 default cutover fail closed。该实现先通过 broad focused gate
`117 passed`，最终变更集再次通过直接相关 gate `59 passed`、`mypy src`（495 个源码文件）、Ruff、
`git diff --check` 与全量 `2452 passed, 27 skipped in 95.97s`。原 feature SHA 的远端 run
`31742943533` 因 CI 安装缺少 NumPy 而 collection 失败；`64d15ae` 同时补齐依赖并让 tee 管道保留
pytest exit code，replacement target attestation `31743521672` 与 BrowserGym conformance
`31743521683` 均通过。

## 22. 实施记录：pricing interaction 与结构化 DOM 输出

2026-08-13 pricing remediation 继续使用同一个 DOM `SurfaceObservation` 和
`UnifiedWorldEnvironment`，没有查询 `/api/pricing`，也没有让 evaluator 读取 fixture oracle。
`DomSurfaceAdapter` 新增显式 trusted interaction operation registration；只有产品 operation
registry 已声明为 local、reversible、interaction-only 的操作才能以 `interaction` 类别进入只读
ActionSpace。页面自己声称的 effect class 不能单独取得这项权限。

同一次 DOM capture 会在有结构化记录或任务明确请求 `structured_document` 时，投影有界的可见
document records。目前声明的最小语法是 article 中的 definition list；hidden 内容不发布，selector、
DOM ID、raw HTML 与执行路由不进入 public target/output。投影形成 `dom_document` 与 record targets、
current structural facts，以及带当前 DOM evidence ref 的 `structured_document` artifact。

action verification 同时收敛了一个原有假阳性：`focused=true` 不再证明 activation effect。
普通控件仍以 target structural diff 验证；注册的 interaction-only activation 必须产生当前、完整、
structural world fact change，pricing 中具体由可见 record inventory 的变化证明。

真实 Playwright acceptance
`tests/test_reference_target_pricing.py::test_target_pricing_reveals_records_and_returns_current_structured_dom_output`
走通：

```text
NaturalLanguageTaskRequest -> ThinTaskIntake -> DOM WorldObservation
-> model SelectAction(Pro reveal) -> private bind/execute -> 1 visible record
-> model SelectAction(Enterprise reveal) -> private bind/execute -> 2 visible records
-> ProductionTaskEvaluator -> structured_document output -> DONE
```

该路径执行恰好两次，模型只提交公开 action ID；训练 fixture 与 held-out DOM 顺序的结构投影均有测试，
pricing readiness 已绑定上述 executable acceptance。export 仍使总 default cutover fail closed。最终本地
验证为 123 个 focused tests、Ruff、`mypy src`（496 个源码文件）、`git diff --check` 与全量
`2461 passed, 27 skipped in 96.50s`。

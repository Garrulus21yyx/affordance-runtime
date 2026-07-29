# Affordance Runtime 唯一权威优化目标架构

> **文档类型：** Authoritative Target Architecture / Architecture Sustainability Decision  
> **状态：** APPROVED_WITH_GUARDRAILS  
> **适用仓库：** `Garrulus21yyx/affordance-runtime`  
> **适用基线：** `648c2da4f6b51c87c5488b6073f0c4b83bf80677`  
> **日期：** 2026-07-29  
> **实施状态：** NOT IMPLEMENTED AS A WHOLE  
> **默认生产进度权威：** 迁移完成前仍为 legacy `TaskPlan + PlanProgress`；目标为本文件定义的 `TaskPlan + TaskProgress`  
> **冲突优先级：** 本文件是 Affordance Runtime 长期目标架构的唯一权威。与以下历史设计冲突时，以本文件为准：
>
> - `docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-simplified-target-architecture.md`
> - `docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-taskplan-authority-architecture.md`
> - ODG-0 至 ODG-9 默认路径提案
> - TPA foundation 文档中仍要求长期并存的 compatibility / projection 设计
>
> 历史文档保留为决策和实验记录，不再定义默认生产架构。

---

## 0. 决议

Affordance Runtime 的长期默认生产主线固定为：

```text
UserRequest
    ↓
TaskSpec
    ↓
PlanCandidate
    ↓ Runtime validation / admission
TaskPlan + TaskProgress
    ↓
UnifiedObservation
    ↓
PlanningRequest
    ↓
PlannerResponse.ActionProposal
    ↓ Runtime validation
ActionContract
    ↓ preflight
ExecutionAttempt
    ↓
ActionReceipt
    ↓ post-action observation
VerificationResult
    ↓
ActionOutcome
    ↓
TaskProgress transition
    ↓
next step / recovery / task completion verification
```

核心原则：

```text
一个概念只有一个 canonical representation；
一个 production decision 只有一个 authority；
每个内部转换必须单向；
每增加一个 canonical owner，必须在同一迁移阶段删除或退役一个旧 owner。
```

停止继续扩展以下默认链路：

```text
obligation candidate set
→ generic evidence normalization
→ generic evidence-to-obligation attribution
→ obligation progress ledger
→ shadow comparison
→ completion-authority migration
```

高级 attribution、概率融合、并行多目标合并等能力只能存在于显式实验 profile，不得进入默认 `RunCoordinator`、`StateKernel`、Planner API 或 task-completion authority。

---

## 1. 项目定位

Affordance Runtime 是：

> **一个从自然语言任务开始，面向长程 GUI、浏览器和设备操作，统一 DOM、Vision、Accessibility、API 与 WoT 感知，支持 Planner-neutral 语义动作、版本化执行合同、独立效果验证和有界恢复的 Agent Runtime。**

项目的技术辨识度集中在：

```text
多来源 UnifiedObservation
稳定 target identity
多 backend 语义动作
版本化 ActionContract
stale-state rejection
receipt / verification 分离
active-step 长程状态
bounded recovery
Planner / Parent Agent 稳定端口
canonical trace 与可复现评估
```

项目当前不以以下能力作为默认生产主线：

- 通用工作流语义引擎；
- 通用 evidence-to-obligation 因果归因系统；
- 分布式 Agent OS；
- 内部 LangGraph 微节点重写；
- 概率世界模型或 Bayesian fusion；
- 通用知识图谱与自动 skill mining；
- 多租户 durable worker 平台；
- 为 benchmark task name、URL、selector 或 seed 建立语义特例。

---

## 2. 当前问题：一致性税

当前代码的主要结构性成本不是单个模块过大，而是同一语义存在多个平行表示：

```text
TaskObligationRelation
SubgoalOutcomeRelation
StateCriterionRelation

SubgoalSpec
StepSpec
TaskPlan
TaskPlanView
TaskPlanDraft

PlanningRequest
PlannerContext
provider payload

TaskPlan progress
TaskSkill progress
ODG progress
ActionProgressRecord
pending_obligations

RecoveryIncident
FailureEnvelope
RecoveryPlan
RecoveryReceipt
RecoveryDelta
RecoveryHistory
```

由此形成：

```text
模型 A 与模型 B 必须一致
    ↓
增加 projector
    ↓
projector 需要 status / identity / digest
    ↓
增加 checker
    ↓
checker 需要 architecture gate
    ↓
旧模型仍在，所有映射继续维护
```

本架构将迁移策略从 additive migration 改为 substitutive migration：

```text
允许：
foundation → production cutover → legacy deletion

禁止：
foundation A → foundation B → projector → checker → shadow → future cutover
```

---

## 3. 架构原则

### P-01：单一语义词汇

相同领域概念只定义一次。任务目标、步骤完成条件、动作预期效果和验证结果共享同一 `CriterionRelation` 与 `Criterion` 词汇。

### P-02：单一业务权威

```text
untrusted draft / proposal
    ↓ validation + admission
Runtime-owned domain object
```

允许：

- `IntentDraft → TaskSpec`
- `PlanCandidate → TaskPlan`
- `PlannerResponse.ActionProposal → ActionContract`

禁止两个 accepted domain object 同时描述同一事实。

### P-03：深层不可变先于 digest

只有深层不可变或在构造时完成规范化拷贝的对象，才能计算并长期保存 digest。

```text
normalize recursively
→ freeze recursively
→ validate
→ compute digest
```

### P-04：一个 consumer 最多一个内部 projection

默认 core 允许：

- `StateKernel → PlanningRequest`
- `DomainEvent → trace JSON`
- `RunResult → API response`

禁止连续内部投影：

```text
State → Request → Context → thawed dict → provider payload
```

### P-05：唯一 progress 与 completion authority

默认生产路径只有：

```text
TaskPlan
TaskProgress
TaskCompletionVerifier
```

TaskSkill、ODG、ActionProgress 和 benchmark reward 都不得拥有独立完成权。

### P-06：Runtime 控制边界与 Planner 算法解耦

Planner 只看到 immutable `PlanningRequest`，只返回封闭的 `PlannerResponse`。Planner 不读取或修改 `StateKernel`、`TaskPlan`、Executor、TraceDag 或 backend handle。

### P-07：Receipt、Effect、Step、Task 四层分离

```text
ActionReceipt.accepted
≠
action effect observed
≠
active step complete
≠
task completion criterion verified
```

### P-08：兼容必须是显式 adapter

禁止通过反射、参数数量、`hasattr()` 或异常探测选择 API。

```text
LegacyXAdapter implements NewPort
```

兼容 adapter 必须有 owner、allowlist 和 deletion gate。

### P-09：核心同步路径不等待 analytics

Route calibration、skill mining、benchmark collection、Langfuse/OTel export 和 evolution 通过 `ActionOutcomeRecorded` 等事件异步或 best-effort 订阅，不决定本次任务结果。

### P-10：治理 gate 检查代码不变量，不检查历史文案

阻塞 gate 聚焦 import、mutation、authority、public signature 和 task-specific branch。文档精确句子、历史 slice 名和行数进入 report，不作为 correctness 证明。

---

## 4. 统一引用与不可变 JSON 值

### 4.1 Canonical refs

```python
@dataclass(frozen=True)
class TaskRef:
    task_id: str
    revision: int


@dataclass(frozen=True)
class ObservationRef:
    snapshot_id: str
    page_revision: str
    environment_revision: str


@dataclass(frozen=True)
class PlanRef:
    plan_id: str
    revision: int


@dataclass(frozen=True)
class ContractRef:
    contract_id: str
    digest: str


@dataclass(frozen=True)
class ExecutionRef:
    execution_id: str


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    source_unit_id: str
    claim_id: str = ""
    field_path: tuple[str, ...] = ()
```

对象树中不重复存储同一 identity 的拆散字段。需要 identity 的地方持有 ref。

### 4.2 Immutable JSON

Core 不使用 `dict[str, Any]` 作为长期 typed contract 字段。允许：

```python
JsonScalar = str | bool | int | float | None
JsonValue = JsonScalar | tuple["JsonValue", ...] | FrozenObject
FrozenObject = tuple[tuple[str, JsonValue], ...]
```

边界 adapter 负责：

```text
external dict/list
→ canonical immutable JSON
```

禁止在 core 中出现通用 `object` + 自定义 freeze/thaw tagged tuple 协议。

---

## 5. 唯一语义词汇

### 5.1 CriterionRelation

只保留一套 relation：

```python
class CriterionRelation(StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"
    MATCHES = "matches"
    IS_VISIBLE = "is_visible"
    IS_ABSENT = "is_absent"
    IS_AVAILABLE = "is_available"
    IS_SELECTED = "is_selected"
    IS_CHECKED = "is_checked"
    IS_EXPANDED = "is_expanded"
    IS_COMPLETED = "is_completed"
    IS_ORDERED_AS = "is_ordered_as"
    HAS_CHANGED = "has_changed"
```

它同时用于：

- TaskSpec completion criterion；
- StepSpec completion criterion；
- ActionContract expected effect；
- VerificationResult；
- task-level completion verification。

不再长期保留：

```text
TaskObligationRelation
SubgoalOutcomeRelation
StateCriterionRelation
```

### 5.2 Criterion

删除没有新增字段或不变量的名义子类：

```text
ValueCriterion
PresenceCriterion
AbsenceCriterion
NavigationCriterion
```

保留一个原子 criterion：

```python
@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    role: Literal["completion", "precondition"]
    subject: str
    relation: CriterionRelation
    expected_value: JsonScalar
    evidence_policy: EvidencePolicy
    source_refs: tuple[SourceReference, ...]
```

只有结构真正不同的 composite 使用独立类型：

```python
@dataclass(frozen=True)
class CompositeCriterion:
    criterion_id: str
    operator: Literal["all_of", "any_of"]
    children: tuple[CriterionRef, ...]
    source_refs: tuple[SourceReference, ...]
```

### 5.3 EvidencePolicy

```python
@dataclass(frozen=True)
class EvidencePolicy:
    minimum_strength: EvidenceStrength
    allowed_source_kinds: tuple[EvidenceSourceKind, ...]
```

证据来源是 `dom_state`、`accessibility_state`、`visual_state`、`api_state`、`device_state`、`artifact_integrity` 等，不使用 `task_obligation` 之类的语义来源冒充 evidence source。

---

## 6. Canonical 顶层对象

默认生产路径只允许以下顶层对象：

1. `UserRequest`
2. `TaskSpec`
3. `PlanRequest`
4. `PlanCandidate`
5. `TaskPlan`
6. `TaskProgress`
7. `UnifiedObservation`
8. `PlanningRequest`
9. `PlannerResponse`
10. `ActionContract`
11. `ExecutionAttempt`
12. `ActionReceipt`
13. `VerificationResult`
14. `ActionOutcome`
15. `Failure`
16. `RecoveryDecision`
17. `RunResult`

### 6.1 TaskSpec

```python
@dataclass(frozen=True)
class TaskSpec:
    ref: TaskRef
    source_text: str
    source_refs: tuple[SourceReference, ...]
    goal: str
    constraints: tuple[TaskConstraint, ...]
    completion_criterion: Criterion | CompositeCriterion
    risk_policy: TaskRiskPolicy
```

TaskSpec 是用户目标语义权威，不包含执行步骤、backend 或历史 evidence。

### 6.2 PlanRequest

```python
@dataclass(frozen=True)
class PlanRequest:
    task: TaskSpec
    observation: PlanningObservationView
    previous_plan: TaskPlan | None
    progress: TaskProgress | None
    trigger: PlanRevisionTrigger | None
    remaining_budget: PlanningBudget
```

它是 Task Planner 的唯一输入。Initial/revision 通过 `previous_plan` 与 `trigger` 的不变量区分，不再维护两套内容高度重复的 request 类型。

### 6.3 PlanCandidate

```python
@dataclass(frozen=True)
class PlanCandidate:
    task_ref: TaskRef
    steps: tuple[StepSpec, ...]
    assumptions: tuple[str, ...]
    provenance: PlanProvenance
```

PlanCandidate 是未接受输入，不能携带：

- plan ID/revision；
- supersedes identity；
- admitted state version；
- capability grant；
- approval token；
- selector、coordinate、backend handle。

### 6.4 StepSpec

```python
@dataclass(frozen=True)
class StepSpec:
    step_id: str
    objective: str
    completion_criterion: Criterion | CompositeCriterion
    preconditions: tuple[Criterion, ...]
    depends_on: tuple[str, ...]
    source_refs: tuple[SourceReference, ...]
    action_budget: int
    recovery_budget: int
```

`SubgoalSpec` 不再是第二套计划步骤。

### 6.5 TaskPlan

```python
@dataclass(frozen=True)
class TaskPlan:
    ref: PlanRef
    task_ref: TaskRef
    supersedes: PlanRef | None
    based_on_state_version: int
    steps: tuple[StepSpec, ...]
    assumptions: tuple[str, ...]
```

TaskPlan 是深层不可变的 Runtime Domain Object。Planner 和 generator 永远不能修改它。

### 6.6 TaskProgress

```python
@dataclass
class TaskProgress:
    plan_ref: PlanRef
    active_step_id: str | None
    completed_step_ids: set[str]
    failed_step_ids: set[str]
    evidence_by_step_id: dict[str, tuple[str, ...]]
    action_count_by_step_id: dict[str, int]
    recovery_count_by_step_id: dict[str, int]
```

TaskProgress 是唯一执行进度权威。持久化或 planner-facing projection 必须复制为 immutable view。

### 6.7 UnifiedAffordance

```python
@dataclass(frozen=True)
class UnifiedAffordance:
    target_id: str
    role: str
    label: str
    surfaces: tuple[Surface, ...]
    supported_actions: tuple[ActionKind, ...]
    state_facts: tuple[StateFact, ...]
    bindings: tuple[BackendBinding, ...]
    source_refs: tuple[PerceptionSourceRef, ...]
    conflict_status: ConflictStatus
    conflicts: tuple[SourceConflict, ...]
    freshness: Freshness
    confidence: float | None
```

不得选择一个 representative source 后丢掉其他 surface。多 action target 不得因为 action 数量不等于 1 而从 Planner read model 消失。

### 6.8 UnifiedObservation

```python
@dataclass(frozen=True)
class UnifiedObservation:
    ref: ObservationRef
    affordances: tuple[UnifiedAffordance, ...]
    observed_text: str
    artifact_refs: tuple[str, ...]
    captured_at_s: float
```

完整 DOM、截图、accessibility tree 和 TD 存 ArtifactStore；Planner 读取 bounded typed view。

### 6.9 PlanningRequest

```python
@dataclass(frozen=True)
class PlanningRequest:
    task: TaskSpec
    plan: TaskPlan | None
    progress: TaskProgressView | None
    active_step: StepSpec
    active_step_scope: ActiveStepScope
    observation: UnifiedObservation
    last_outcome: ActionOutcomeSummary | None
    recovery: RecoverySummary | None
    remaining_budget: RuntimeBudgetView
```

不包含 generic `task_summary`、`latest_outcome`、`recent_proposals`、`verified_effects` 等重复 blob。

### 6.10 PlannerResponse

使用封闭 union，不使用混合 `PlannerDecision`：

```python
PlannerResponse = (
    ActionProposal
    | ClarificationRequest
    | FinishProposal
    | DeferredProposal
    | PlanIssueReport
)
```

```python
@dataclass(frozen=True)
class ActionProposal:
    proposal: PlannerProposal
    model_call: ModelCallRecord | None = None


@dataclass(frozen=True)
class ClarificationRequest:
    question: str
    reason_code: str


@dataclass(frozen=True)
class FinishProposal:
    result: FrozenObject
    reason: str


@dataclass(frozen=True)
class DeferredProposal:
    reason_code: str
    retry_after_s: float | None


@dataclass(frozen=True)
class PlanIssueReport:
    plan_ref: PlanRef
    step_id: str
    kind: PlanIssueKind
    reason_code: str
    evidence_refs: tuple[str, ...]
```

Planner 不返回 ActionContract，不提交 step completion，不修改 TaskPlan。

### 6.11 ActiveStepScope

```python
@dataclass(frozen=True)
class ActiveStepScope:
    step_id: str
    allowed_action_families: tuple[ActionKind, ...]
    allowed_target_ids: tuple[str, ...]
    finish_allowed: bool
```

它取代 terminal admission mini-framework 在 Planner read model 中的职责。Scope 是 bounded hint；ProposalValidator 仍进行最终 fail-closed 校验。

### 6.12 ActionContract

顶层合同保留，但按职责分组：

```python
@dataclass(frozen=True)
class ActionContract:
    ref: ContractRef
    task_ref: TaskRef
    observation_ref: ObservationRef
    action: SemanticAction
    target: TargetBinding
    expected_effects: tuple[Criterion, ...]
    execution: ExecutionPolicy
    verification: VerificationPolicy
    safety: SafetyPolicy | None
```

完整 route candidate scores、debug reason、analytics 和 fallback lineage进入 trace，不进入 hash-critical contract。

### 6.13 ExecutionAttempt / Receipt / Verification / Outcome

```python
@dataclass(frozen=True)
class ExecutionAttempt:
    ref: ExecutionRef
    active_step_id: str
    contract: ActionContract
    before_observation: ObservationRef


@dataclass(frozen=True)
class ActionReceipt:
    execution_ref: ExecutionRef
    backend: str
    accepted: bool
    error_code: str
    latency_ms: float
    artifact_refs: tuple[str, ...]


@dataclass(frozen=True)
class VerificationResult:
    execution_ref: ExecutionRef
    step_id: str
    criterion_id: str
    action_effect_status: Literal["observed", "not_observed", "inconclusive"]
    step_status: Literal["complete", "incomplete", "blocked"]
    observed_deltas: tuple[StateDelta, ...]
    evidence_refs: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True)
class ActionOutcome:
    execution_ref: ExecutionRef
    active_step_id: str
    contract_ref: ContractRef
    before_observation: ObservationRef
    after_observation: ObservationRef
    receipt: ActionReceipt
    verification: VerificationResult
```

每个 effectful execution 最多产生一个最终 ActionOutcome。

### 6.14 Failure / Recovery

```python
@dataclass(frozen=True)
class Failure:
    phase: FailurePhase
    code: str
    reason: str
    recoverable: bool
    context: FailureContext


@dataclass(frozen=True)
class RecoveryDecision:
    kind: RecoveryKind
    reason: str
    reentry_phase: RuntimePhase
    target_backend: str | None = None


@dataclass(frozen=True)
class RecoveryOutcome:
    decision: RecoveryDecision
    success: bool
    changed_state: bool
    observation_ref: ObservationRef | None = None
    error: str = ""
```

纯 reobserve、replan、reground 不创建多层 receipt/delta/history 对象；trace 记录历史，StateKernel 保留当前 recovery 和 typed attempted keys。

---

## 7. Authority Matrix

| 责任 | 唯一 Owner | 禁止承担的责任 |
|---|---|---|
| Natural language → TaskSpec | `TaskInterpreter` + `TaskSpecAuthority` | 不生成动作或 accepted plan |
| Plan candidate 生成 | `TaskPlanGeneratorPort` | 不生成 PlanRef、不写 StateKernel |
| Plan 准入 | `TaskPlanAuthority` | 不执行动作、不提交状态 |
| Plan install/replace | `RunCoordinator` / `TaskTransitionService` | 不发明 step |
| Plan 与 progress 存储 | `StateKernel` | 不解释语义 |
| active step 选择 | `TaskProgressService` | 不调用 Planner |
| 下一动作 | `PlannerPort` | 不修改 plan/progress |
| Proposal 准入 | `ProposalValidator` | 不重新规划 |
| Contract 构建 | `ActionContractBuilder` | 不执行、不完成 step |
| Preflight | `PreflightService` | 不放宽 policy |
| Backend routing | `BackendRouter` | 不判断 task completion |
| 实际执行 | `Executor` | 只返回 receipt |
| 效果与 step 验证 | `EffectVerifier` | 不写 StateKernel |
| task completion 验证 | `TaskCompletionVerifier` | 不提交状态 |
| Recovery 选择 | `RecoveryPolicy` | 不直接执行 backend |
| 状态与 canonical trace 顺序 | `RunCoordinator` | 不实现领域算法 |
| Analytics/evolution | Event subscriber | 不影响本次 RunResult |
| Benchmark scoring | Benchmark adapter | 不影响 Runtime completion |

---

## 8. 唯一生产主循环

```python
while not state.terminal:
    observation_result = perception_phase.run(state.view())
    state.apply(observation_result.transition)
    trace.append_all(observation_result.events)

    step_precheck = progress_phase.check_current_step(
        task=state.task_spec,
        plan=state.task_plan,
        progress=state.task_progress,
        observation=observation_result.observation,
    )
    state.apply(step_precheck.transition)
    trace.append_all(step_precheck.events)
    if step_precheck.advanced:
        continue

    request = planning_request_builder.build(state.view())
    planner_response = planner.propose(request)

    planning_result = planning_phase.admit(planner_response, request)
    state.apply(planning_result.transition)
    trace.append_all(planning_result.events)
    if planning_result.no_execution:
        continue

    execution_result = execution_phase.run(planning_result.contract)
    state.apply(execution_result.transition)
    trace.append_all(execution_result.events)

    progress_result = progress_phase.apply(execution_result.outcome)
    state.apply(progress_result.transition)
    trace.append_all(progress_result.events)

    if progress_result.requires_recovery:
        recovery_result = recovery_phase.run(state.view(), progress_result.failure)
        state.apply(recovery_result.transition)
        trace.append_all(recovery_result.events)
        continue

    if progress_result.all_required_steps_complete:
        task_result = task_completion_verifier.verify(
            state.task_spec,
            state.latest_observation,
            state.last_outcome,
        )
        state.apply(task_result.transition)
        trace.append_all(task_result.events)
```

Coordinator 的职责只有：

- 调用 phase owner；
- 串行提交 state transition；
- 保证 canonical event 顺序；
- 选择 continue / return。

---

## 9. TaskPlan 生命周期

### 9.1 Initial planning

```text
TaskSpec + current observation
    ↓
TaskPlanGeneratorPort
    ↓ PlanCandidate
TaskPlanAuthority
    ↓ accepted TaskPlan / repair / clarification / no-plan
Coordinator
    ↓ install
StateKernel
```

### 9.2 Replan

```text
Failure / PlanIssueReport
    ↓
RecoveryPolicy decides REPLAN_STEP or REPLAN_TASK
    ↓
TaskPlanGeneratorPort
    ↓ PlanCandidate
TaskPlanAuthority
    ↓ TaskPlan revision N+1
Coordinator
    ↓ replace
```

### 9.3 Plan invariants

- TaskPlan 深层不可变；
- 结构变化创建新 PlanRef；
- completed step 必须保留且不可重定义；
- replan 不改变 TaskSpec goal/constraints；
- generator 不能提供 authority fields；
- TaskSkill 只能是 PlanCandidate 或 ActionProposal source；
- planner 只能报告 PlanIssue，不能提交 patch。

---

## 10. PlanningRequest 与 Provider Serialization

标准路径：

```text
StateKernel
    ↓ one bounded typed projection
PlanningRequest
    ↓ pure serializer
provider JSON/messages
```

不再存在第二个领域对象 `PlannerContext`。保留：

```python
def serialize_planning_request(
    request: PlanningRequest,
    policy: PlannerContextPolicy,
) -> ProviderRequest:
    ...
```

Serializer 可以：

- 限长；
- 排序；
- 选择最近 outcome；
- 隐去内部 IDs；
- 产生 provider-specific messages。

Serializer 不可以：

- 解释 StateKernel；
- 重新计算 active step；
- 生成 admission；
- 修改 action scope；
- thaw 一个 generic object blob。

---

## 11. 多来源感知

### 11.1 Lazy fusion

```text
DOM + Accessibility first
    ↓ sufficient?
Vision on demand
    ↓ device/API task?
WoT/API on demand
    ↓ conflict?
active perception / reobserve
```

### 11.2 Target identity

`TargetIdentityResolver` 只返回：

```text
matched
ambiguous
unmatched
conflicted
```

它不规划、不路由、不完成 step。

### 11.3 Conflict

来源冲突保持显式：

```python
SourceConflict(
    target_id=...,
    property_name=...,
    source_values=...,
    severity=...,
)
```

高风险且 material conflict 未解决时，Preflight 阻止执行。

---

## 12. ActionContract 不可变与 digest 威胁模型

### 12.1 必须修复的风险

外层 `frozen=True` 不能保护内部 `dict/list`。任何 hash-critical 对象必须在 `__post_init__` 前完成深层规范化，随后禁止可变引用逃逸。

### 12.2 Digest 保留条件

新增或保留 digest 时必须回答：

1. 防止谁篡改？
2. 跨哪个持久化、进程或审批边界？
3. 为什么 `ID + revision` 不足？
4. 对象是否已经深层不可变？

允许保留：

- approval token 精确绑定 ActionContract；
- artifact 文件完整性；
- 发布的 evidence/profile bundle；
- 外部协议的 canonical payload。

不需要：

- 内存 TaskSpec 版本判断；
- 内存 TaskPlan equality；
- PlanningRequest 内部重复 identity；
- progress repeat 的 JSON string fingerprint。

### 12.3 Contract hash 范围

只覆盖：

```text
task ref
contract ID
semantic action
selected target binding
pre-action observation ref
parameters
preconditions
expected effects
execution policy
verification policy
safety policy
```

不覆盖：

```text
route candidate scores
fallback analytics
debug reason
trace metadata
model call data
```

---

## 13. 单一 Progress 与 Completion

默认 StateKernel 不再保存：

- `ObligationProgressLedger`；
- `pending_obligations` 字符串列表；
- 独立 `TaskSkillRunState` progress；
- 完整 `ActionProgressRecord` 历史。

目标完成链：

```text
ActionOutcome verified
    ↓
active step criterion passed
    ↓
TaskProgress.complete(active_step)
    ↓
activate next ready step
    ↓
all required steps complete
    ↓
TaskCompletionVerifier(TaskSpec.completion_criterion)
    ↓
TaskCompleted
```

规则：

- 一个 ActionOutcome 最多完成一个 active step；
- 后续 step 若已被环境变化满足，在下一轮 planning 前 precheck；
- Planner `FinishProposal` 只触发 task completion verification；
- receipt/external reward 不能形成 StepCompleted 或 TaskCompleted；
- TaskSkill 不得独立触发 TaskCompleted。

Action repeat guard 使用 typed `ActionKey` 和 last outcomes 的 bounded index，不使用 JSON string signature 历史。

---

## 14. 单一 Recovery 协议

当前两套 Recovery 机制收敛为：

```text
Failure
→ RecoveryPolicy
→ RecoveryDecision
→ RecoveryPhase execution if required
→ RecoveryOutcome
```

StateKernel 只保存：

- current failure；
- current recovery decision；
- recovery count；
- attempted strategy keys；
- latest recovery outcome。

完整 incident、attempt、delta、receipt 和 history 进入 trace。只有真实外部副作用 recovery 需要 execution receipt。

---

## 15. StateKernel 目标职责

StateKernel 只保存当前决策需要的状态：

```text
TaskSpec
TaskPlan
TaskProgress
latest UnifiedObservation ref
current ActionContract
last ActionOutcome
current Failure / Recovery
budgets
final status/result
state version
```

不保存完整历史副本：

```text
all observations
all receipts
planner payload history
recovery history
probe receipts
route analytics
full grounding fallback lineage
```

完整历史由 Trace 和 ArtifactStore 拥有。

---

## 16. Trace 与事件

### 16.1 Canonical events

```text
TaskAccepted
TaskPlanAdmitted
TaskPlanRevised
ObservationCaptured
PlannerResponseReceived
PlannerProposalRejected
ActionContractBound
ExecutionAttemptStarted
ActionOutcomeRecorded
RecoverySelected
RecoveryApplied
StepCompleted
TaskCompletionVerified
TaskCompleted
TaskFailed
```

### 16.2 Diagnostic events

```text
grounding candidates
source arbitration
route scoring
verifier detail
model calls
experimental attribution
shadow comparison
```

Diagnostic event：

- 不参与 completion；
- 不参与 retry source of truth；
- 可按 profile 关闭；
- exporter 失败不改变 RunResult。

### 16.3 Subscribers

```text
ActionOutcomeRecorded
    ├── RouteCalibrator
    ├── SkillMiner
    ├── BenchmarkCollector
    ├── EvolutionEvaluator
    └── OTel/LangfuseExporter
```

Core 不等待这些 subscriber。

---

## 17. Compatibility 与 Experiments

### 17.1 Compatibility

每个 compatibility adapter 必须声明：

```yaml
owner:
allowed_importers:
remove_when:
new_production_imports: prohibited
```

默认 `RunCoordinator` 只认识新 Port。Legacy composition root 显式包 adapter。

禁止：

```text
inspect.signature
参数数量探测
union protocol 进入 core coordinator
```

### 17.2 Experiments

以下移动到 `experiments/` 或 optional profile：

- advanced progress attribution；
- obligation progress ledger；
- probabilistic fusion；
- learned routing；
- asynchronous evidence attribution；
- parallel multi-goal planning。

默认 core 不 import experiments。

---

## 18. 公共 API

稳定公共 API：

```text
Runtime / RuntimeClient
RunRequest
RunResult
PlannerPort
PlanningRequest
PlannerResponse
UnifiedObservation
UnifiedAffordance
ActionContract
ActionOutcome
```

Internal：

```text
StateKernel
projection helpers
compatibility adapters
migration contracts
TaskPlanAuthority binder internals
admission diagnostics
```

`__init__.py` 不再直接公开 mutable `StateKernel`、`TaskEnvelope`、route calibration internals 和 migration-only `PlannerDecision`。

---

## 19. 目标模块布局

```text
src/affordance_runtime/
├── api/
│   ├── contracts.py
│   └── runtime.py
├── task/
│   ├── contracts.py
│   ├── interpreter.py
│   ├── planning.py
│   ├── authority.py
│   └── progress.py
├── perception/
│   ├── contracts.py
│   ├── observation_service.py
│   ├── target_identity.py
│   ├── fusion.py
│   └── adapters/
├── planner/
│   ├── contracts.py
│   ├── request_builder.py
│   ├── serializer.py
│   ├── validator.py
│   └── adapters/
├── execution/
│   ├── contracts.py
│   ├── contract_builder.py
│   ├── preflight.py
│   ├── router.py
│   └── executors/
├── verification/
│   ├── contracts.py
│   ├── effect_verifier.py
│   └── task_completion_verifier.py
├── recovery/
│   ├── contracts.py
│   ├── policy.py
│   └── phase.py
├── runtime/
│   ├── coordinator.py
│   ├── state.py
│   ├── transitions.py
│   └── phases/
├── trace/
│   ├── events.py
│   ├── sink.py
│   └── exporters/
├── integrations/
├── analytics/
├── benchmarks/
└── experiments/
```

目录移动在 owner 和 authority 稳定后执行，不作为前期 correctness blocker。

---

## 20. Architecture Gates

### 20.1 阻塞 gate

1. Planner 不 import StateKernel、Coordinator、Executor、Playwright。
2. PlannerPort 只有 `propose(PlanningRequest)`。
3. PlannerResponse 不含 ActionContract 或 state mutation。
4. TaskPlanGeneratorPort 只返回 PlanCandidate。
5. 只有 TaskPlanAuthority 可构造 accepted TaskPlan identity。
6. 只有 application transition owner 可修改 StateKernel。
7. Executor 不 import TaskPlan、RecoveryPolicy 或 benchmark。
8. Verifier 不修改 StateKernel。
9. RecoveryPolicy 不直接调用 Executor。
10. Benchmark/external reward 不修改 completion。
11. Core 不 import `experiments/advanced_progress_attribution`。
12. Core 不包含 task name、URL、selector、seed 分支。
13. hash-critical contracts 必须通过 deep immutability tests。
14. 每个 effectful execution 最多一个 ActionOutcomeRecorded。
15. TaskCompleted 必须来自 TaskCompletionVerifier。

### 20.2 非阻塞 architecture report

- 文件/方法行数；
- import fan-in/fan-out；
- cyclomatic complexity；
- compatibility adapter 数；
- migration-only type 数；
- duplicate enum/field 数；
- StateKernel 历史字段数量；
- Coordinator phase ownership比例。

### 20.3 不再作为 blocking gate

- Markdown 精确短语；
- 当前 slice 名必须出现在多个文档；
- 每个小 foundation 必须有单独 YAML；
- 历史行数 ceiling 被当作架构健康证明。

---

## 21. 重新引入高级 attribution 的条件

仅当出现稳定、可测需求时重新评估：

```text
A. 一个 ActionOutcome 必须同时完成多个无序 step
B. evidence 在 active step 生命周期结束后异步到达
C. 多个 Agent 并行推进同一 TaskPlan
D. 目标允许任意顺序和并行完成
E. 法规要求严格 evidence-to-obligation 审计
F. active-step pre-binding 产生可测 false reject
```

晋升要求：

```text
简化路径无法表达真实需求
+
实验方案提升可测指标
+
不会增加 false completion
+
不引入第二套 production progress authority
```

---

## 22. 最终删除目标

迁移完成后，默认 core 不再拥有：

```text
TaskObligationRelation / SubgoalOutcomeRelation / StateCriterionRelation 三套枚举
SubgoalSpec
TaskPlanView（production）
TaskPlanDraft / TaskPlanDraftProjector
第二个 generator protocol
legacy TaskPlan → Draft → legacy TaskPlan round trip
PlannerContext domain object
freeze_request_value / thaw_request_value generic protocol
reflective planner compatibility
mixed PlannerDecision
PlannerAdmissionView / terminal readiness mini-framework
TaskSkillRunState progress authority
ObligationProgressLedger in default StateKernel
双 recovery protocol
完整 observations/receipts/recovery histories in StateKernel
synchronous RouteCalibrator / evolution inside Coordinator
文档精确文案 blocking gates
```

---

## 23. 最终验收标准

```yaml
semantic_vocabulary:
  criterion_relation_enums: 1
  canonical_criterion_model: 1

planning:
  candidate_model: PlanCandidate
  accepted_model: TaskPlan
  progress_model: TaskProgress
  legacy_round_trip: absent

planner_boundary:
  request_projection_count: 1
  planner_context_domain_object: absent
  reflective_compatibility: absent
  response: closed_union

execution:
  action_contract_deeply_immutable: true
  contract_hash_stable_after_construction: true
  action_outcome_per_execution: exactly_one

progress:
  production_progress_authorities: 1
  taskskill_completion_authority: false
  obligation_ledger_default_state: absent
  task_completion_verified_independently: true

recovery:
  production_protocols: 1

runtime:
  coordinator_domain_algorithms: absent
  statekernel_full_history: absent
  analytics_synchronous_dependency: absent

perception:
  multi_surface_preserved_in_planner_view: true
  multi_action_target_preserved: true
  conflict_status_preserved: true

public_api:
  statekernel_exported: false
  migration_types_exported: false

promotion:
  pr_breadth: required_after_behavior_cutovers
  fresh_diagnostic: required
  official_score_claimed: false_until_separate_promotion
```

---

## 24. 最终架构收口

```text
TaskSpec
    ↓
PlanCandidate
    ↓ TaskPlanAuthority
TaskPlan + TaskProgress
    ↓
UnifiedObservation
    ↓
PlanningRequest
    ↓
PlannerResponse
    ↓
ActionContract
    ↓
ExecutionAttempt
    ↓
ActionReceipt
    ↓
VerificationResult
    ↓
ActionOutcome
    ↓
Advance / Recover / Replan / Verify Task Completion
```

核心复杂度只集中在：

```text
多来源目标统一
多 backend 语义执行
版本化和 stale-safe contract
独立效果验证
active-step 长程状态
bounded recovery
```

任何新增内部表示、digest、checker、projection 或 compatibility seam，都必须证明自己跨越了真实信任、authority、进程、持久化或有损压缩边界；否则不进入默认架构。

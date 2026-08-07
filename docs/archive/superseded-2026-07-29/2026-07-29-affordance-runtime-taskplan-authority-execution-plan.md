# Affordance Runtime TaskPlan 权威与 Planner 边界实施计划

> [!IMPORTANT]
> Superseded by SAR-0. Current authority is
> `docs/superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md`
> and
> `docs/superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md`.
> This archived file is historical context only.

> **文档类型：** Granular Implementation Plan / Change-Admission Program
> **状态：** `PROPOSED_FOR_EXECUTION`
> **架构决议：** `2026-07-29-affordance-runtime-taskplan-authority-architecture.md`
> **父级计划：** `docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-simplification-execution-plan.md`
> **适用分支：** `agent/migrate-runtime-components`
> **原始审查基线：** `7fe493e8429541b4d42801f4519626891ff794d5`
> **执行基线：** `8445747f0d734b3998b88edb204e099edf58d259`
> **当前 production progress authority：** legacy `TaskPlan / Subgoal / PlanProgress`
> **目标 plan authority：** `TaskPlanAuthority`
> **目标 step planner：** immutable `PlanningRequest → StepPlannerPort`
> **日期：** 2026-07-29

---

## 0. 执行摘要

本计划把当前耦合结构：

```text
TaskPlannerPort.plan() 直接返回 TaskPlan
TaskPlanLifecycle 同时调用 planner、构建 context、判断 replacement、验证
TaskPlanFlow 准备 initial/replacement
RunCoordinator 安装/替换
Step Planner 同时读取 TaskEnvelope + mutable StateKernel + BrowserSnapshot
TaskSkill 保留独立 step cursor
```

渐进迁移为：

```text
TaskPlanGeneratorPort
    ↓ TaskPlanDraft
TaskPlanAuthority
    ↓ TaskPlanDecision
RunCoordinator
    ↓ install/replace
StateKernel
    ↓ immutable TaskPlan + mutable StepProgress
StepLifecycle
    ↓ Runtime-selected active step
PlanningRequestBuilder
    ↓ immutable PlanningRequest
StepPlannerPort
    ↓ PlannerProposal / PlanIssueReport
```

执行顺序固定为：

```text
TPA-0  冻结决议、同步文档、S2.1 hardening
TPA-1  完整调用点与 Planner/TaskPlan read-set audit
TPA-2  S3 immutable PlanningRequest contracts + builder
TPA-3  StepPlannerPort 全调用点迁移并删除三参数标准路径
TPA-4  TaskPlanDraft / TaskPlanDecision / TaskPlanAuthority contracts
TPA-5  Rule/LLM/Parent/custom TaskPlan generators 迁移
TPA-6  Validator 按责任拆分，Authority 接管 initial admission
TPA-7  Replan trigger、revision admission、Coordinator replace 收口
TPA-8  TaskSkill 与 reference/benchmark/CLI wiring 对齐
TPA-9  ActiveStepScope + PlanIssueReport 门禁
TPA-10 ActionOutcome/ActiveStepVerifier shadow 与 authority cutover
TPA-11 Legacy/ODG/parallel authority 隔离和清理
TPA-12 PR breadth、fresh diagnostic、文档收尾
```

不允许把这些工作批量成一个重构提交。

---

## 1. 当前基线与权威状态

```yaml
branch: agent/migrate-runtime-components
execution_base_revision: 8445747f0d734b3998b88edb204e099edf58d259
remote_match: true
remote_ci: disabled
promotion: held

current_plan_generation:
  port: TaskPlannerPort
  output: TaskPlan
  implementations:
    - PlanningRouter
    - RuleTaskPlanner
    - TaskObligationOutcomeCompiler
    - LLMTaskPlanner
    - PricingTaskPlanner

current_plan_admission:
  lifecycle: TaskPlanLifecycle
  validator: TaskPlanValidator
  application_flow: TaskPlanFlow
  committer: RunCoordinator
  storage: StateKernel

current_step_planner:
  port: PlannerPort
  signature: propose(TaskEnvelope, StateKernel, BrowserSnapshot)

current_progress_authority:
  plan: TaskPlan
  progress: PlanProgress
  completion: StateKernel.complete_subgoal
  finish_guard: TaskPlanLifecycle.completed

simplified_foundation:
  S0: done
  S1: foundation_only
  S2: foundation_only
  S2_1: completed
  S3: not_started

advanced_attribution:
  status: experimental_only
  ODG_10: stopped
  ODG_11: stopped
```

### 1.1 当前增长棘轮

```text
coordinator.py <= 当前治理 ceiling
RunCoordinator methods <= 26
RunCoordinator.run_sync <= 当前治理 ceiling
task_planning.py <= 当前治理 ceiling
GeneralistLMPlanner.propose <= 222
LLMIntentCompiler.compile <= 253
TaskPlanValidator.validate <= 239
```

每个抽取 slice 完成后应将 ceiling 下调到新的实际值。

---

## 2. 全局执行规则

### 2.1 单一 writer

```yaml
production_writers: 1
interface_decision_owner: main_integrator
parallel_core_writers: prohibited
read_only_subagents: optional
final_diff_reviewer: optional
```

以下模块/接口不允许并行 production 修改：

- `coordinator.py`；
- `state_kernel.py`；
- `planning_contracts.py`；
- TaskPlan schema；
- TaskPlanAuthority；
- StepPlannerPort；
- progress/trace authority。

### 2.2 每个 revision 必须声明

```yaml
plan_candidate_owner:
plan_decision_owner:
plan_commit_owner:
step_planner_owner:
progress_authority:
task_completion_authority:
state_writer:
trace_writer:
legacy_path_status:
```

### 2.3 默认禁止

- task name / URL / selector / seed / benchmark family 语义分支；
- Prompt-only plan repair；
- model/retry/budget 扩张；
- Step Planner 生成 `TaskPlan` / `TaskPlanDraft` / patch；
- Planner-authored completed step / active step；
- RecoveryPolicy 直接安装 plan；
- receipt/external reward completion；
- current ODG ledger取得 authority；
- Coordinator 中新增 plan/criterion matcher；
- 降低 ActionContract/preflight/approval/verifier 边界；
- 大规模目录移动先于 owner 收口。

### 2.4 统一验证层级

Contract-only slice：

```text
focused tests
architecture tests
full pytest
Ruff
mypy
uv build
git diff --check
```

Standard interface cutover：

```text
以上全部
+
provider-facing context equivalence
+
sync/async/reference/parent/BrowserGym planner regression
```

Plan admission/replan behavior change：

```text
以上全部
+
non-BrowserGym initial/replan end-to-end
+
targeted reference scenarios
+
必要时 clean 6×2 PR breadth
```

Authority cutover：

```text
以上全部
+
clean committed PR breadth
+
current revision evidence archive
+
rollback path test
```

---

## 3. 依赖图

```text
TPA-0 S2.1 hardening/docs sync
    ↓
TPA-1 read-set + call-site audit
    ↓
TPA-2 PlanningRequest contracts/builder
    ↓
TPA-3 StepPlannerPort cutover
    ↓
TPA-4 TaskPlan authority contracts
    ↓
TPA-5 Generator migration
    ↓
TPA-6 Initial plan admission cutover
    ↓
TPA-7 Replan admission cutover
    ↓
TPA-8 TaskSkill/reference/benchmark wiring alignment
    ↓
TPA-9 ActiveStepScope + PlanIssueReport
    ↓
TPA-10 ActionOutcome / active-step authority cutover
    ↓
TPA-11 Legacy/ODG isolation
    ↓
TPA-12 Evaluation and closure
```

S3 immutable PlanningRequest 必须先于 TaskPlanAuthority production cutover，避免新 authority 仍然把完整 mutable `StateKernel` 暴露给 Step Planner。

---

# 4. TPA-0 — 冻结决议、S2.1 hardening 与文档同步（已完成）

```yaml
TPA-0: completed
implementation_revision: 8445747f0d734b3998b88edb204e099edf58d259
production_behavior_change: false
projection_authority: none
next_slice: TPA-1
```

本节保留原始准入要求作为历史执行说明。实际 S2.1 已由
`docs/change-admission/s2-1-step-projection-hardening.yaml` 关闭；以下条目不得被解释为
重新打开 S2.1 或扩大其状态模型。

## 4.1 目标

1. 将 TaskPlan ownership 决议写入规范；
2. 修正 S2 projection，不让错误的 active/evidence/provenance 进入 S3；
3. 将 current docs 从 ODG-deferred 语义同步到 simplified active-step / TaskPlanAuthority 路线；
4. 不改变 production behavior。

## 4.2 新文档

建议仓库路径：

```text
docs/superpowers/specs/
  2026-07-29-affordance-runtime-taskplan-authority-architecture.md

docs/superpowers/plans/
  2026-07-29-affordance-runtime-taskplan-authority-execution-plan.md

docs/change-admission/
  tpa-0-taskplan-authority-freeze.yaml
```

## 4.3 S2.1 代码修改

### A. completed/no-active plan 语义

当前 projection 在无 active、无 ready 时回退到最后一步。改为：

```python
class StepActivityStatus(StrEnum):
    ACTIVE = "active"
    READY_NOT_ACTIVATED = "ready_not_activated"
    COMPLETED = "completed"
    NO_PLAN = "no_plan"
```

```python
TaskPlanView.active_step_id: str | None
StepProgressView.active_step_id: str | None
StepProgressView.activity_status: StepActivityStatus
```

规则：

- existing active ID → `ACTIVE`；
- no active + ready → `READY_NOT_ACTIVATED`；
- all required steps completed → `COMPLETED`；
- no ready but incomplete/failed → `PROJECTION_INVALID`（fail-closed）；
- 不伪造最后一步 active。

### B. progress identity validation

增加：

```text
completed IDs ⊆ step IDs
failed IDs ⊆ step IDs
active ID ∈ step IDs
active ∉ completed/failed
evidence map keys ⊆ completed IDs
completed step requires non-empty verifier evidence
```

### C. source provenance

当前 `claim_id` 不能伪装成 source-unit ID。

目标：

```python
@dataclass(frozen=True)
class SourceReference:
    source_id: str
    source_unit_id: str
    claim_id: str = ""
    field_path: tuple[str, ...] = ()
```

规则：

- `claim.source_unit_ids` 非空：逐个投影；
- legacy 无 source unit：显式 compatibility marker；
- 不能无证据生成 exact lineage。

### D. evidence policy

从 `TaskObligationSpec.typed_evidence_requirements` 投影：

- evidence kind/source；
- minimum strength；
- relation；
- subject/value ref。

没有 typed requirement 时：

```text
projection status = unsupported_evidence_policy
```

不得使用 `allowed_source_kinds=("task_obligation",)` 作为生产 verifier policy。

### E. terminal completion projection

保留：

```text
0 terminal → pending
1 terminal → projected
>1 terminal → unsupported
```

S3 request 必须携带 projection status。`unsupported` 时不允许 finish。

## 4.4 RED tests

```text
fully completed plan has no active step
ready-but-not-activated is not ACTIVE
blocked plan has no fake active step
unknown completed/failed ID rejected
evidence key for incomplete step rejected
completed step without evidence rejected
source_unit_ids preserved
claim_id remains separate
missing typed evidence policy rejected/pending
multiple terminal criteria remain unsupported
state.version unchanged
```

## 4.5 文档同步

修改：

```text
docs/current-implementation-plan.md
docs/implementation-status.md
docs/architecture-governance-track.md
.codex/goal-plan.md
```

要求：

- exact current HEAD；
- horizontal lane 不再写“等待 ODG ready obligation”；
- S3 明确基于 `TaskPlanView/StepProgressView`；
- TaskPlanAuthority 决议登记；
- status alignment 恢复 passing 前先消除 drift。

## 4.6 Exit

```yaml
behavior_change: false
projection_authority: none
fake_active_step: closed
provenance_semantics: accurate
evidence_policy: typed_or_fail_closed
current_docs: synchronized
```

## 4.7 建议 commits

```text
docs: freeze TaskPlan authority and StepPlanner boundary
fix: harden legacy step compatibility projection
```

---

# 5. TPA-1 — 完整调用点、Owner 与 Read-set 审计

## 5.1 目标

在改公共接口前生成机器可核对的调用点清单。

## 5.2 输出文档

```text
docs/audits/taskplan-authority-call-sites.md
docs/audits/step-planner-standard-input-read-set.md
docs/audits/taskskill-progress-authority.md
```

## 5.3 审计范围

### TaskPlan generation

```text
TaskPlannerPort
PlanningRouter
RuleTaskPlanner
TaskObligationOutcomeCompiler
LLMTaskPlanner
PricingTaskPlanner
所有测试/fixture/custom planner
```

### Plan admission/commit

```text
TaskPlanValidator
TaskPlanLifecycle
TaskPlanFlow
TaskPlanCommitPreparation
RunCoordinator
StateKernel.install_task_plan
StateKernel.replace_task_plan
```

### Replan triggers

```text
TaskPlanLifecycle.evaluate_replacement
TaskPlanFlow current-state discard
RecoveryCommandKind.REPLAN_TASK / REPLAN_STEP
Coordinator recovery branches
```

### Step Planner input

```text
PlannerPort
GeneralistLMPlanner
ParentAgentPlannerAdapter
PricingPlanner
SettingsPlanner
ExportPlanner
BrowserGymPlanner
BrowserGymGeneralistPlanner
scripted/test planners
DecisionConstraintBuilder
PlannerContextBuilder
terminal readiness helpers
```

### Parallel progress

```text
PlanProgress
TaskSkillRunState
ODG obligation_progress
pending_obligations legacy string list
ActionProgressRecord
```

## 5.4 每项记录格式

```yaml
symbol:
module:
current_role:
reads:
writes:
creates_plan: false
validates_plan: false
commits_plan: false
updates_progress: false
trace_writer: false
target_owner:
migration_slice:
compatibility_window:
deletion_gate:
```

## 5.5 可执行 gate

新增 AST/grep tests：

- `install_task_plan` / `replace_task_plan` production callers allowlist；
- `TaskPlan(` constructor production locations allowlist；
- Planner triple-signature implementation list；
- `StateKernel` import in Step Planner list；
- TaskSkill progress mutation caller list；
- ODG imports in default path list。

## 5.6 Exit

调用点清单覆盖所有 production、integration、benchmark、CLI 和 test helper。

---

# 6. TPA-2 — S3 Immutable PlanningRequest Contracts 与 Builder

## 6.1 目标

标准 Step Planner 不再读取 mutable `StateKernel`，但暂不改变 plan generation/admission authority。

## 6.2 新增模块

```text
src/affordance_runtime/planning_request.py
src/affordance_runtime/planning_request_builder.py
tests/test_planning_request.py
tests/test_planning_request_builder.py
docs/change-admission/s3-immutable-planning-request.yaml
```

## 6.3 Contracts

```text
PlanningRequestIdentity
PlannerTaskView
PlannerStepView
PlannerAffordanceView
PlannerObservationView
PlannerOutcomeSummary
PlannerRecoverySummary
RuntimeBudgetView
PlanningRequest
```

### Request identity

```python
@dataclass(frozen=True)
class PlanningRequestIdentity:
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    snapshot_id: str
    page_revision: str
    environment_revision: str
```

### Step view

```python
@dataclass(frozen=True)
class PlannerStepView:
    plan: TaskPlanView | None
    progress: StepProgressView | None
    active_step: StepSpec | None
    activity_status: StepActivityStatus
```

### Observation view

所有 affordance/backend/source state 必须复制并冻结。禁止将 `BrowserSnapshot` 对象原样放入 request。

## 6.4 PlanningRequestBuilder

唯一允许同时读取：

```text
TaskEnvelope
StateKernel
BrowserSnapshot
legacy step projection
```

的 owner。

禁止：

- StateKernel mutation；
- step activation；
- trace write；
- planner invocation；
- finish/recovery decision；
- plan generation/admission。

## 6.5 State interpretation 迁移

从 `PlannerContextBuilder` 移入 builder：

```text
latest receipt/verification summary
remaining budget
recovery summary
satisfied action targets
active step/action-family view
recent proposal/outcome summary
```

`PlannerContextBuilder` 以后只负责 provider-facing bounded serialization。

## 6.6 RED tests

```text
request contains no StateKernel/TaskEnvelope/BrowserSnapshot
nested collections are deeply immutable
mutating source dict/list after build does not change request
build leaves state.version unchanged
stale TaskSpec/plan/snapshot identity rejected
completed plan produces no active step
ready-not-activated cannot produce effectful planner request
no-plan flat compatibility represented explicitly
recovery/budget summaries bounded
```

## 6.7 Exit

Contracts 和 builder 存在，但 PlannerPort 尚未切换；production behavior 无变化。

---

# 7. TPA-3 — StepPlannerPort 全调用点迁移

## 7.1 目标

将：

```python
propose(envelope, state, snapshot)
```

替换为：

```python
propose(request)
```

并将接口明确命名为 `StepPlannerPort`。

## 7.2 迁移顺序

```text
1. PlannerContextBuilder
2. StrictDecisionConstraintBuilder
3. terminal readiness view adapter
4. GeneralistLMPlanner
5. ParentAgentPlannerAdapter
6. reference planners
7. BrowserGymPlanner / BrowserGymGeneralistPlanner
8. scripted/conformance/test planners
9. Planning contracts
10. Coordinator call site
```

## 7.3 PlannerContextBuilder

目标：

```python
def build(self, request: PlanningRequest) -> PlannerContext:
    ...
```

必须保持 provider payload 等价。增加 golden tests：

```text
old state/snapshot → old PlannerContext JSON
same input → PlanningRequest → new PlannerContext JSON
必须相等（除明确 versioned field change）
```

不得无意 bump prompt/context policy；如 payload 变化，必须记录 policy version并运行 breadth。

## 7.4 Decision constraints

`narrow_terminal_candidates()` 不再接 `StateKernel`/`BrowserSnapshot`。

短期使用 immutable `TaskPlanView/StepProgressView/PlannerObservationView` adapter；长期在 S4/S5 改为 active-step scope/task completion criterion。

## 7.5 Reference planners

`PricingPlanner`、`SettingsPlanner`、`ExportPlanner`：

- 从 request 读 immutable observation/outcome；
- 不再读 StateKernel；
- compatibility direct `ActionContract` 输出可暂留，但不得获得 plan authority；
- active criterion IDs 从 request step identity构造，不读 plan_progress。

## 7.6 BrowserGym

- benchmark terminal状态可以形成 `PlannerDecision` compatibility stop；
- external reward仍不能完成 Runtime step/task；
- BrowserGym planner只读 request projection；
- no benchmark task name进入 Runtime semantic owner。

## 7.7 Compatibility adapter

如历史 replay必须保留旧实现：

```python
class LegacyStepPlannerAdapter(StepPlannerPort):
    ...
```

只允许 compatibility profile 使用；default Runtime禁止调用旧三参数接口。

## 7.8 Architecture exit gates

```text
planning_contracts.py no StateKernel/TaskEnvelope/BrowserSnapshot
planner_context.py no StateKernel/TaskEnvelope
generalist_planner.py no StateKernel/TaskEnvelope/BrowserSnapshot
decision_constraints.py no StateKernel
planner_adapters.py no StateKernel
reference Step Planners no StateKernel
BrowserGym Step Planner adapters no StateKernel
Coordinator is sole PlanningRequestBuilder caller in standard path
```

## 7.9 Benchmark decision

如果 provider-facing JSON、terminal candidate narrowing或 proposal结果发生变化：运行 clean 6×2 PR breadth；否则 full local suite足够，promotion仍 held。

---

# 8. TPA-4 — TaskPlan Authority Neutral Contracts

## 8.1 目标

建立 `Draft → Decision → Commit` 边界，不改 standard plan behavior。

## 8.2 新增模块

```text
src/affordance_runtime/task_plan_contracts.py
src/affordance_runtime/task_plan_authority.py
tests/test_task_plan_authority_contracts.py
docs/change-admission/tpa-4-taskplan-authority-contracts.yaml
```

## 8.3 Contracts

```text
TaskPlanDraft
TaskPlanRequest
TaskPlanRevisionRequest
TaskPlanIssue
TaskPlanDecision
PlanIssueReport
TaskPlanGeneratorPort
```

## 8.4 Authority field ownership

只有 `TaskPlanAuthority` 可生成：

```text
plan_id
plan_revision
supersedes_plan_id
admitted_at_state_version
plan_digest
```

Generator输出这些字段应 schema reject。

## 8.5 RED tests

```text
generator draft cannot include plan_id/version/supersedes
decision accepted requires plan
rejected/clarification cannot carry plan
plan digest deterministic
same draft + same request → stable semantic digest, new runtime ID policy explicit
replacement revision/supersedes enforced
TaskPlan immutable
StepPlanner cannot import authority contracts requiring generation
```

## 8.6 Exit

Authority contracts存在，当前 TaskPlanLifecycle仍是 production admission path。

---

# 9. TPA-5 — TaskPlan Generator 迁移

## 9.1 目标

所有 plan producers只产生 `TaskPlanDraft`。

## 9.2 迁移对象

### Rule generator

```text
TaskObligationOutcomeCompiler
RuleTaskPlanner
```

目标：

```text
RuleTaskPlanGenerator.generate(request) -> TaskPlanDraft
```

### LLM generator

当前 `LLMTaskPlanner`：

- provider schema；
- candidate bind；
- repair loop；
- authority plan construction；
- internal validation。

目标：

```text
LLMTaskPlanGenerator
  provider generation
  bounded candidate repair
  TaskPlanDraft output
```

移除：

- plan ID/version/state binding；
- final acceptance；
- duplicate full validator authority。

### PlanningRouter

目标：

```text
TaskPlanGeneratorRouter
```

返回：

```text
TaskPlanDraft
或 no_plan_candidate
```

### Pricing/custom generators

直接构造 `TaskPlanDraft`，不构造 accepted plan。

## 9.3 Provider schema identity

TaskPlan provider schema/version发生变化时：

- bump `TASK_PLANNER_PROMPT_VERSION` / schema identity；
- update BrowserGym frozen run identity；
- old replay使用 compatibility generator；
- 不把旧结果当新 schema evidence。

## 9.4 Tests

```text
rule draft exact semantic equivalence
LLM draft bounded repair equivalence
provider cannot author authority fields
no StateKernel/Coordinator/Trace imports
generator cannot install/replace plan
router chooses same generator policy
custom generator migration
```

## 9.5 Exit

所有 production plan generation调用已可通过 draft接口；旧 `TaskPlannerPort` 只在 compatibility adapter中存在。

---

# 10. TPA-6 — Validator 拆分与 Initial Plan Authority Cutover

## 10.1 目标

`TaskPlanAuthority` 成为 initial plan 最终决策 Owner。

## 10.2 Validator 拆分顺序

从当前 `TaskPlanValidator` 逐项抽取：

1. `TaskPlanStructuralValidator`；
2. `TaskPlanLineageValidator`；
3. `TaskPlanTaskSpecValidator`；
4. `TaskPlanSafetyPolicy`；
5. `TaskPlanFeasibilityEvaluator`；
6. compatibility repair issue projector。

每次只移出一种变化原因，保留 golden issue equivalence。

## 10.3 TaskPlanAuthority.admit

```python
def admit(
    self,
    request: TaskPlanRequest,
    draft: TaskPlanDraft,
) -> TaskPlanDecision:
    ...
```

顺序：

```text
validate request freshness
→ bind authority fields
→ structural
→ lineage
→ TaskSpec/source coverage
→ safety
→ evidence/criterion
→ feasibility advisory
→ accepted/rejected/repair/clarification
```

Generator repair只响应 typed issues；修复后必须重新走完整 authority。

## 10.4 Application flow

目标：

```text
TaskPlanApplicationFlow.prepare_initial
    ↓
TaskPlanAuthority.create
    ↓
TaskPlanDecision
```

Coordinator仍然：

```text
accepted → state.install_task_plan
non-accepted → trace/recovery/clarification
```

## 10.5 行为等价测试

```text
initial rule plan same steps/criteria/dependencies
LLM plan accepted/repaired/rejected equivalence
invalid task/state identity fail closed
operation escalation rejected
executable selector/coordinate content rejected
missing source coverage rejected
no-plan flat policy explicit
Coordinator install exactly once
state version increments exactly once
```

## 10.6 Cutover authority

```yaml
before:
  plan_decision_owner: TaskPlanLifecycle + Validator composition

after:
  plan_decision_owner: TaskPlanAuthority
  plan_commit_owner: RunCoordinator
```

Replan仍暂时 legacy，直到 TPA-7。

---

# 11. TPA-7 — Replan Authority 收口

## 11.1 目标

Recovery决定“是否 replan”；TaskPlanAuthority决定 replacement；Coordinator提交。

## 11.2 Recovery input/output

`RecoveryPolicy` 输出保持：

```text
REPLAN_STEP
REPLAN_TASK
```

禁止在 `RecoveryCommand` 中携带：

- TaskPlanDraft；
- TaskPlan；
- patch；
- new step IDs；
- completed step claims。

## 11.3 Revision request

```python
@dataclass(frozen=True)
class TaskPlanRevisionRequest:
    task: PlannerTaskView
    previous_plan: TaskPlanView
    progress: StepProgressView
    observation: PlannerObservationView
    failure: TypedFailureSummary
    recovery_reason: str
    remaining_budget: RuntimeBudgetView
    evaluated_at_state_version: int
```

## 11.4 TaskPlanAuthority.revise

必须：

- carry forward completed step definitions exactly；
- preserve evidence lineage；
- maintain TaskSpec/source/risk authority；
- validate N+1 lineage；
- reject no-op replacement；
- reject removal/redefinition of verified steps；
- require new plan ID/digest；
- distinguish `repair_required` from final reject。

## 11.5 Current-state satisfied step

不再通过 ad-hoc plan discard解决。

目标路径：

```text
CurrentStepVerifier proves active step already complete
→ Coordinator completes progress
→ next step
```

只有真正的 plan structure defect才触发 replacement。

因此 current `_prepare_current_state_discard()` 最终应退休。

## 11.6 Tests

```text
budget exhausted triggers replan request
unavailable action family triggers replan or reground per policy
already-satisfied step completes, does not delete plan unit
unsupported criterion triggers plan issue/replan
completed step preserved exact
replacement no-op rejected
replacement new unrequested side effect rejected
replacement risk downgrade/escalation rejected
stale revision request rejected
Coordinator replace exactly once
```

## 11.7 Cutover

Initial 和 replacement plan均由 `TaskPlanAuthority` 决定。

---

# 12. TPA-8 — TaskSkill、Reference、CLI、Benchmark Wiring 对齐

## 12.1 TaskSkill

增加 `StepExecutionStrategyPort` 或明确 adapter：

```text
accepted skill step
→ proposal for current Runtime active step
```

要求：

- Runtime step ID/criterion identity匹配；
- skill不能激活其它 Runtime step；
- skill checkpoint不直接完成 Runtime task；
- normal verifier结果仍由 Coordinator提交 Runtime progress；
- skill fallthrough只切换 strategy，不改 TaskPlan。

## 12.2 Reference planners

分离：

```text
PricingPlanner / SettingsPlanner / ExportPlanner
  → StepPlannerPort implementations

PricingTaskPlanner
  → TaskPlanGeneratorPort implementation
```

禁止同一个类同时实现两种 port。

## 12.3 CLI

显式 wiring：

```python
RunCoordinator(
    step_planner=...,
    task_plan_authority=...,
    task_plan_generator=...,
)
```

flat/no-plan场景显式使用 authority policy，不以 `task_planner=None` 模糊表示。

## 12.4 BrowserGym

- BrowserGymGeneralistPlanner 实现 StepPlannerPort；
- LLMTaskPlanGenerator/authority通过 Runtime normal path注入；
- benchmark终止/reward只影响 evaluation artifact；
- checkpoint identity记录 TaskPlan schema/authority policy/PlanningRequest policy versions；
- external policy compatibility profile不能获得 plan authority。

## 12.5 Tests

```text
CLI pricing with/without task planning
settings/export reference paths
accepted skill action stays in active step
skill cannot complete task independently
BrowserGym wrapper uses PlanningRequest
benchmark adapter cannot call install/replace/complete
run identity version changes correctly
```

---

# 13. TPA-9 — ActiveStepScope 与 PlanIssueReport

## 13.1 目标

让简化架构可以通过执行前 pre-binding成立，避免重新进入 generic post-action attribution。

## 13.2 Contracts

```text
ActiveStepScope
StepScopeResolution
StepActionAuthorization
PlanIssueReport
```

Scope至少包含：

- step ID；
- criterion IDs；
- canonical progress target IDs；
- allowed effectful actions；
- support target/action IDs；
- observation identity。

## 13.3 ProposalValidator

增加 active-step scope gate：

```text
proposal target/action can advance active step
or is explicitly allowed support action
```

Step Planner跨 step proposal：

```text
reject before ActionContract
→ typed reason
→ replan/reobserve/reground/clarify
```

## 13.4 PlanIssueReport

Step Planner可以报告：

```text
step_unexecutable
target_unavailable
criterion_unverifiable
plan_assumption_invalid
scope_ambiguous
```

不能报告新 plan/patch。

## 13.5 RED

```text
slider step → checkbox action rejected
checkbox step → submit rejected
same-step repeated press_key allowed within budget
support disclosure action allowed only by explicit support scope
ambiguous target returns issue/recovery
PlanIssue cannot carry plan patch
```

---

# 14. TPA-10 — ActiveStepVerifier / ActionOutcome 与 Progress Authority Cutover

## 14.1 Shadow 阶段

新增：

```text
CurrentStepVerifier
ActiveStepVerifier
ActionOutcomeBuilder
TaskCompletionVerifier
```

同时计算：

```text
legacy subgoal result
new active-step result
```

只 trace divergence。

## 14.2 Flat task cutover

先对 implicit single-step task切换 authority。

要求：

- no TaskPlan required；
- receipt-only不完成；
- external reward不完成；
- final task criterion独立验证；
- rollback可切回 legacy。

## 14.3 Serial task cutover

```text
one active step
→ one effectful attempt
→ one final ActionOutcome
→ at most one step commit
→ next Planner turn
```

目标场景：

```text
text → select → slider → checkbox → submit
button A → button B
WoT write → DOM confirmation
approval → export → artifact hash
```

## 14.4 Authority switch

```yaml
before:
  progress_authority: legacy PlanProgress

after:
  progress_authority: Runtime StepProgress
  task_completion_authority: TaskSpec completion criterion verifier
  legacy_progress: diagnostic_projection_only
```

## 14.5 Clean evidence

首次 authority cutover必须跑 clean committed PR breadth。

---

# 15. TPA-11 — Legacy、ODG 与平行 Authority 隔离

## 15.1 默认路径删除/隔离

停止默认：

```text
ODG shadow trace
ticket carry
obligation ledger initialization
TaskPlanProgressTarget standard use
active-subgoal-only evidence binding
current-state discard replacement workaround
TaskPlanLifecycle.completed as task final authority
TaskSkill independent task completion
```

## 15.2 兼容 facade

保留历史 replay需要的 facade，但 default profile不得 import。

## 15.3 Physical module split

调用点归零后再拆：

```text
task_plan_contracts.py
task_plan_generation.py
task_plan_authority.py
task_plan_validation.py
step_lifecycle.py
step_planning.py
```

`task_planning.py` 最终成为 compatibility re-export 或删除。

## 15.4 Import gates

```text
default coordinator/state/planning request
不 import experiments/advanced_progress_attribution
```

---

# 16. TPA-12 — 评估、证据与收尾

## 16.1 Validation sequence

```text
1. focused unit/contract
2. architecture gates
3. full pytest
4. Ruff
5. mypy
6. uv build
7. diff check
8. non-BrowserGym serial E2E
9. targeted BrowserGym
10. clean 6×2 PR breadth
11. same revision fresh diagnostic
```

## 16.2 Acceptance

```yaml
planner:
  mutable_state_input: false
  can_modify_plan: false

plan:
  candidate_owner: TaskPlanGeneratorPort
  decision_owner: TaskPlanAuthority
  commit_owner: RunCoordinator
  immutable: true
  revisioned: true

replan:
  trigger_owner: RecoveryPolicy
  decision_owner: TaskPlanAuthority

progress:
  authority: Runtime active_step/StepProgress
  receipt_completion: false
  external_reward_completion: false

state:
  parallel_completion_authorities: 0

behavior:
  pr_breadth_external_reward_no_regression: true
  runtime_failures_not_increased: true
  safety_regressions: 0
```

## 16.3 Documentation closure

同步：

```text
target architecture
this execution plan
current implementation plan
implementation status
architecture governance
responsibility containment
README public claims
benchmark governance
.codex/goal-plan.md
```

旧 ODG/legacy记录保留为历史证据，不改写历史。

---

## 17. 测试矩阵

### 17.1 Plan generation

| Case | Expected |
|---|---|
| Flat single criterion | no_plan_required / implicit step |
| Rule multi-step | deterministic draft |
| LLM valid draft | authority accepts |
| LLM repairable draft | one bounded repair then full revalidation |
| LLM fatal draft | rejected |
| Parent draft | same authority path |
| Generator includes plan ID | schema reject |
| Generator includes selector/coordinate | reject |

### 17.2 Plan authority

| Case | Expected |
|---|---|
| Initial revision != 1 | reject |
| Initial has supersedes | reject |
| Replacement version not N+1 | reject |
| Replacement reuses plan ID | reject |
| Completed step missing | reject |
| Completed step redefined | reject |
| New side effect without source | reject |
| Risk escalation | reject |
| Dependency cycle | reject |
| Missing terminal path | reject/clarify |

### 17.3 Step Planner

| Case | Expected |
|---|---|
| Reads request only | pass |
| Attempts StateKernel import | architecture fail |
| Proposal targets active scope | accept |
| Cross-step effectful target | reject |
| Plan issue report | typed recovery input |
| Plan patch field | schema reject |
| Planner claims completion | ignored/rejected |

### 17.4 Replan

| Case | Expected |
|---|---|
| Action budget exhausted | RecoveryPolicy may choose replan |
| Target stale | reobserve/reground before replan |
| Criterion unverifiable | plan issue → replan/clarify |
| Current state already satisfies step | complete progress, no plan deletion |
| Replacement no-op | reject |
| Replan preserves evidence | pass |

### 17.5 TaskSkill

| Case | Expected |
|---|---|
| Skill matches current step | proposal allowed |
| Skill targets later step | reject/fallthrough |
| Skill checkpoint without Runtime verification | no Runtime completion |
| Skill completes internal cursor | task still requires Runtime step/task verification |

### 17.6 Authority

```text
only Coordinator calls install/replace/complete
TaskPlanAuthority does not mutate state
Generator does not write trace
StepPlanner does not call TaskPlanAuthority
RecoveryPolicy does not return plan
benchmark does not complete Runtime
```

---

## 18. 建议提交序列

```text
Commit 1  docs: freeze TaskPlan authority and planner naming
Commit 2  fix: harden simplified step projection identity
Commit 3  docs: record TaskPlan and StepPlanner call-site audit
Commit 4  feat: add immutable PlanningRequest contracts
Commit 5  feat: add PlanningRequestBuilder
Commit 6  refactor: build planner context from PlanningRequest
Commit 7  refactor: migrate decision constraints to immutable views
Commit 8  refactor: migrate StepPlanner implementations
Commit 9  refactor: switch StepPlannerPort to request-only input
Commit 10 feat: add TaskPlanDraft and TaskPlanAuthority contracts
Commit 11 refactor: migrate rule task plan generator
Commit 12 refactor: migrate model task plan generator
Commit 13 feat: admit initial plans through TaskPlanAuthority
Commit 14 feat: admit replacement plans through TaskPlanAuthority
Commit 15 refactor: align TaskSkill with active Runtime step
Commit 16 feat: enforce ActiveStepScope on proposals
Commit 17 feat: project ActionOutcome and active-step verification
Commit 18 feat: cut over flat task progress authority
Commit 19 feat: cut over serial task progress authority
Commit 20 refactor: isolate advanced attribution and retire legacy authority
Commit 21 docs: archive clean TaskPlan authority migration evidence
```

不要为了减少 commit 数将 9–19 合并。

---

## 19. Rollback 策略

### Interface migration rollback

- compatibility adapter恢复旧 call；
- request contracts保留；
- 不回滚 StateKernel state schema。

### Initial authority rollback

- TaskPlanLifecycle legacy path通过 feature profile恢复；
- 同一 run不能混用两种 admission；
- accepted plan identity/trace保留。

### Replan rollback

- replan authority feature flag在 run开始时冻结；
- 不允许一次 run initial 走新 authority、replacement 走未声明的混合 policy。

### Progress cutover rollback

- 整个 run选择 legacy 或 active-step authority；
- 不允许双 commit；
- shadow trace保留用于诊断。

### Benchmark regression

- 记录负向 evidence；
- reject/revert具体 slice；
- 不弱化 verifier/finish/approval；
- 不扩大 task-specific fallback。

---

## 20. Change-admission 模板

每个 production slice使用：

```yaml
slice_id:
base_revision:
change_type:
production_writers: 1

single_responsibility:
owner_before:
owner_after:

typed_input:
typed_output:

plan_candidate_owner:
plan_decision_owner:
plan_commit_owner:
progress_authority:
state_writer:
trace_writer:

allowed_files:
forbidden_files:

removed_old_path:
compatibility_path:
deletion_gate:

required_tests:
benchmark_requirement:
rollback_trigger:

architecture_admission: not_evaluated
promotion_status: held
```

---

## 21. Definition of Done

整个计划完成需要：

```yaml
task_plan_domain:
  immutable: true
  revisioned: true
  generator_returns_draft: true
  authority_is_unique: true
  coordinator_is_only_committer: true

step_planner:
  name: StepPlannerPort
  input: immutable PlanningRequest
  state_kernel_input: false
  taskplan_mutation: false
  active_step_selection: false
  completion_authority: false

replan:
  trigger: RecoveryPolicy
  plan_decision: TaskPlanAuthority
  commit: RunCoordinator
  completed_progress_preserved: true

state:
  taskplan_storage: accepted_only
  progress_separate: true
  parallel_progress_authorities: false

skill:
  role: step_execution_strategy
  independent_task_completion: false

runtime:
  action_contract_safety_preserved: true
  receipt_effect_completion_separated: true
  task_completion_independently_verified: true

validation:
  full_local_gate: pass
  clean_pr_breadth: pass_or_explicitly_held_with_no_regression
  fresh_diagnostic: recorded
  remote_ci: disabled_or_exact_revision_status_recorded

promotion:
  status: separately_decided
```

---

## 22. 当前立即执行项

从执行基线 `8445747` 开始，下一轮不要直接创建 `TaskPlanAuthority` production path。

严格顺序：

```text
1. TPA-0：已完成；保留冻结决议和 S2.1 证据
2. TPA-1：完整 TaskPlan/Planner/Recovery/TaskSkill call-site audit
3. TPA-2：PlanningRequest contracts + builder
4. TPA-3：StepPlannerPort request-only cutover
5. TPA-4：TaskPlanDraft / TaskPlanDecision / Authority contracts
```

原因：

```text
先切断 Step Planner 对 mutable StateKernel 和 legacy plan internals 的直接读取，
再迁移 TaskPlan decision authority，
可以避免新 TaskPlanAuthority 被旧 Planner 输入边界重新耦合。
```

当前不授权：

```text
TaskPlanAuthority production commit
replan authority cutover
active-step progress cutover
ODG-10/11
PR breadth claim
promotion
```

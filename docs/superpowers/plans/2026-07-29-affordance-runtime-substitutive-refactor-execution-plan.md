# Affordance Runtime 删改式架构优化实施计划

> **文档类型：** Substitutive Refactor Execution Plan  
> **状态：** PROPOSED_FOR_EXECUTION  
> **唯一目标架构：** `2026-07-29-affordance-runtime-authoritative-optimized-architecture.md`  
> **代码基线：** `648c2da4f6b51c87c5488b6073f0c4b83bf80677`  
> **日期：** 2026-07-29  
> **核心策略：** 从 additive migration 切换到 substitutive migration  
> **生产权威约束：** 任一 revision 只能有一个 progress authority、一个 plan admission authority、一个 completion authority  
> **推广状态：** held；本计划不自动授权 PR breadth、fresh diagnostic 或 promotion

---

## 0. 计划目标

本计划不继续增加 TPA-5B 式“新 generator foundation + 旧 production path 保留”的平行结构。目标是按垂直能力切片完成：

```text
建立 canonical replacement
    ↓
切换一个真实 production path
    ↓
删除旧 owner、projector、checker、compatibility seam
```

最终将当前代码库从：

```text
多套 relation
多套 plan/step 表示
PlanningRequest → PlannerContext 双重投影
mixed PlannerDecision
多套 progress / finish / recovery
浅层 frozen + digest checker
Coordinator / StateKernel 历史仓库
```

收敛为：

```text
一个语义词汇
PlanCandidate → TaskPlan → TaskProgress
StateKernel → PlanningRequest → provider serializer
封闭 PlannerResponse
单一 step/task completion path
单一 Recovery protocol
深层 immutable contract
薄 Coordinator + 当前状态 StateKernel
```

---

# 1. 执行规则

## 1.1 One-in, one-out

新增一个 canonical 表示时，同一阶段必须删除或明确退役一个旧表示。

示例：

```text
新增 PlanCandidate
    +
LLM generator 改为直接返回 PlanCandidate
    +
删除 LLMTaskPlanner._bind_candidate() 产生 accepted TaskPlan 的路径
```

不允许：

```text
新增 PlanCandidate
但 legacy TaskPlan、TaskPlanDraft、TaskPlanDraftProjector、两套 generator port 全部长期保留
```

## 1.2 三提交上限

一个迁移单元最多使用以下三类连续提交：

```text
Commit A: RED + canonical contract
Commit B: production cutover
Commit C: legacy deletion + architecture gate
```

超过三提交仍未 cutover 时，必须重新评估范围；不得继续添加 projector/checker。

## 1.3 Compatibility 必须具备删除门

每个 compatibility 文件必须包含机器可读或测试可见的：

```yaml
owner:
allowed_importers:
new_production_imports: prohibited
remove_when:
```

Compatibility 不得通过反射或参数数量探测接口。

## 1.4 Digest threat model

新增或保留 digest 必须记录：

```text
攻击/错误模型
跨越边界
被保护字段
为什么 ID + revision 不足
深层 immutable 证明
```

不能回答则删除 digest。

## 1.5 Receipt 限定

只有真实执行外部动作或真实 recovery side effect 才产生 receipt。Projection、validation、classification、scope resolution 不产生 receipt。

## 1.6 Projection 限定

默认 core 只允许：

```text
State → PlanningRequest
DomainEvent → trace JSON
RunResult → API response
```

新增其它 projection 必须同时删除旧 consumer model。

## 1.7 行为变更触发评估

以下变化之一出现时，必须在 clean committed revision 运行至少 targeted behavioral matrix；涉及默认 planner、progress、finish 或 verifier authority时运行完整 PR breadth：

- provider messages/schema/prompt 变化；
- Planner 可见 target/actions 变化；
- TaskPlan steps/dependency/criterion 变化；
- ActionContract hash/payload变化；
- verification pass/fail变化；
- step/task completion变化；
- recovery选择变化；
- default profile import graph变化。

始终：

```text
official_score_claimed=false
promotion=held
```

---

# 2. 基线模块与目标动作

| 当前模块/对象 | 当前作用 | 目标动作 |
|---|---|---|
| `contracts.py::Observation` | frozen 外壳 + mutable dict/list | 深层 immutable，历史大对象转 artifact ref |
| `contracts.py::Affordance` | 单 surface、单 action、mutable locator/state | 被 `UnifiedAffordance` 取代；backend binding内聚 |
| `contracts.py::ActionContract` | hash-critical mega-object，内部 mutable | 先修复 immutable/hash，再分组为子合同 |
| `planning_contracts.py::PlannerDecision` | contract/proposal/done/diagnostic 混合 | 封闭 `PlannerResponse` union；Planner不返回 contract |
| `planning_request.py` | typed fields + generic frozen blobs | 删除 blob/freeze/thaw，只保留 typed request |
| `planner_context.py` | 第二个 planner domain object | 改为纯 provider serializer 后删除 class |
| `planner_compatibility.py` | 反射检测 1/3 参数 | 显式 adapter；legacy=0 后删除 |
| `TaskObligationRelation` | task relation vocabulary | 合并到 `CriterionRelation` |
| `SubgoalOutcomeRelation` | plan relation vocabulary | 删除，provider candidate 使用 canonical relation |
| `StateCriterionRelation` | simplified relation vocabulary | 重命名为唯一 `CriterionRelation` |
| 名义 Criterion subclasses | 无新增结构 | 合并为 `Criterion` |
| `SubgoalSpec` | legacy step | 删除，`StepSpec` 唯一 |
| `TaskPlanDraft` | 新 candidate | 重命名/收敛为 `PlanCandidate` |
| `TaskPlanView` | migration projection | cutover 后删除 |
| `TaskPlanDraftProjector` | legacy plan → draft | 删除双向 round trip |
| 两套 generator protocol | 输入不同 | 只保留 `TaskPlanGeneratorPort(PlanRequest)` |
| `TaskPlanAuthorityBinder` | 新 step → legacy subgoal，语义损失 | 替换为直接构造 canonical TaskPlan |
| `terminal_readiness.py` | terminal mini-framework | `ActiveStepScope` + ProposalValidator取代 |
| `planner_admission_projection.py` | legacy terminal投影 | scope cutover 后删除 |
| `PlanProgress` | legacy progress | 迁移/重命名为唯一 `TaskProgress` |
| `TaskSkillRunState` | 平行 progress/finish | 变为 candidate/proposal source后删除 |
| `ObligationProgressLedger` | experimental progress in StateKernel | 移出 default StateKernel |
| `pending_obligations` | legacy string progress | 删除 |
| `ActionProgressRecord` | JSON signature历史 | 改为 bounded typed `ActionKey` index |
| Recovery 两套协议 | action recovery + phase command recovery | 合并为 Failure/Decision/Outcome |
| `StateKernel` histories | state + history + diagnostics | 仅当前决策状态；历史归 trace/artifacts |
| `RunCoordinator.run_sync` | 大量领域算法 | phase services；Coordinator只串行提交 |
| Route/evolution同步逻辑 | 同步 core analytics | Event subscriber |
| `__init__.py` | 暴露 internal state/compatibility | 收缩稳定公共 API |
| architecture governance test | 代码 gate + 文案/历史 gate | 保留代码不变量，文案降为 report |

---

# 3. 总体阶段顺序

```text
SAR-0  冻结唯一架构与停止 additive foundation
SAR-1  深层不可变与 stale-hash correctness
SAR-2  统一 Criterion / relation / evidence vocabulary
SAR-3  Plan 垂直替换：PlanCandidate → TaskPlan → TaskProgress
SAR-4  Planner 直接序列化与封闭 PlannerResponse
SAR-5  UnifiedObservation 与 ActiveStepScope，删除 terminal mini-framework
SAR-6  ActionContract 分组、ExecutionAttempt 与 ActionOutcome canonicalization
SAR-7  单一 progress / finish，移除 TaskSkill/ODG parallel authority
SAR-8  单一 Recovery 协议
SAR-9  StateKernel 与 Coordinator 缩减
SAR-10 Analytics / evolution / benchmark 移出同步 core
SAR-11 公共 API 与 governance gate 收缩
SAR-12 全量删除审计、PR breadth、fresh diagnostic、推广评审
```

强依赖：

```text
SAR-1 → SAR-2 → SAR-3
SAR-3 → SAR-4 → SAR-5 → SAR-7
SAR-1 → SAR-6
SAR-7 → SAR-8 → SAR-9
SAR-6/SAR-9 → SAR-10/SAR-11
```

---

# 4. SAR-0 — 唯一架构冻结与治理切换

## 4.1 目标

停止继续按旧 TPA-5B 计划添加平行 foundation。将本架构和本实施计划设为唯一 current source。

## 4.2 文档修改

新增入库：

```text
docs/superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md
docs/superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md
```

历史文档顶部增加：

```text
Status: HISTORICAL / SUPERSEDED_ON_CONFLICT
Superseded by: authoritative optimized architecture
```

修改：

```text
docs/current-implementation-plan.md
docs/implementation-status.md
docs/architecture-governance-track.md
.codex/goal-plan.md
```

## 4.3 决议

```yaml
current_head: 648c2da4f6b51c87c5488b6073f0c4b83bf80677
migration_strategy: substitutive
next_slice: SAR-1-deep-immutability-and-contract-hash
stopped:
  - TPA-5B foundation-only implementation
  - new internal projections without deletion gate
  - new generic digests without threat model
production_authority:
  plan: legacy until SAR-3 cutover
  progress: legacy until SAR-7 cutover
  completion: legacy until SAR-7 cutover
```

## 4.4 Architecture gate 调整

新增阻塞 gate：

```text
新 compatibility 模块必须有 deletion gate
新 production module 不得 import historical ODG default path
新 relation enum 禁止出现
新 TaskPlan generator port 禁止出现
```

文档精确文案 gate暂时标为 deprecated，但在 SAR-11 删除。

## 4.5 Exit

- 没有代码行为变化；
- TPA-5B 不再作为下一项；
- 下一项唯一为 SAR-1；
- old docs保留历史，不再定义 current next slice。

---

# 5. SAR-1 — 深层不可变与 stale hash 修复

> **优先级：P0 correctness**

## 5.1 目标

修复 `frozen=True` 对象内部仍可修改，导致保存的 digest 与当前内容不一致的问题。

## 5.2 新增基础模块

```text
src/affordance_runtime/immutable.py
src/affordance_runtime/refs.py
```

### `immutable.py`

```python
JsonScalar
JsonValue
FrozenObject
freeze_json(value)
thaw_json_at_external_boundary(value)
```

只允许在 API/provider/adapter 边界 thaw；core 不 thaw。

### `refs.py`

```text
TaskRef
ObservationRef
PlanRef
ContractRef
ExecutionRef
```

## 5.3 修改对象

### 5.3.1 Observation

当前：

```text
metadata: dict
fingerprints: dict
artifact_refs: list
```

目标：

```python
@dataclass(frozen=True)
class Observation:
    ref: ObservationRef
    url: str
    dom_hash: str
    screenshot_ref: str
    accessibility_hash: str
    metadata: FrozenObject
    target_fingerprints: tuple[tuple[str, str], ...]
    artifact_refs: tuple[str, ...]
    observed_at_s: float
```

### 5.3.2 Affordance / Lease / Gesture binding

- `provenance`, `backend_candidates`, `evidence` → tuple；
- `locator`, `state`, `payload` → FrozenObject 或 typed binding/state；
- constructors 深拷贝；
- 删除任何返回可变内部引用的 property。

### 5.3.3 ActionContract

第一阶段不改变顶层业务字段，只深层规范化：

```text
locator / parameters → FrozenObject
preconditions / effects / verifiers / capabilities / fallbacks → tuple
route/grounding/gesture内部也必须不可变
```

`contract_hash` 在全部 freeze 和 validation 后计算。

新增：

```python
assert contract.compute_hash() == contract.ref.digest
```

但禁止 caller 修改内部内容，因此该 assertion只用于测试/deserialize boundary。

### 5.3.4 ExecutionReceipt / VerificationEvidence / PlannerDecision

- receipt evidence → FrozenObject；
- verifier observed/expected → JsonValue；
- PlannerDecision 在 SAR-4 删除，SAR-1 先将其 dict字段 freeze，阻止进一步 correctness 风险。

## 5.4 Hash threat model 文档

新增：

```text
docs/security/action-contract-digest-threat-model.md
```

记录：

- approval token依赖 contract digest；
- hash-critical字段；
- excluded analytics字段；
- canonical JSON algorithm；
- schema version策略。

## 5.5 Tests

### RED

```python
old = contract.contract_hash
attempt_mutation(contract.parameters)
# mutation must be impossible
assert contract.contract_hash == old
assert contract.compute_hash() == old
```

覆盖：

- nested dict/list mutation；
- source object mutation after constructor；
- `dataclasses.replace` 正确重新计算 digest；
- serialize/deserialize digest稳定；
- ApprovalToken 对 immutable contract匹配；
- gesture locator和route plan不可变；
- receipt/verifier evidence不可变。

## 5.6 One-out 删除

- 删除散落的 local freeze helper；
- 删除允许可变 list/dict进入 contract 的 constructors；
- 删除依赖“构造后重新置 `contract_hash=""`”的 replace 习惯，改为 contract builder方法。

## 5.7 行为验证

ActionContract payload/hash变化属于安全行为变化：

- full tests；
- approval/capability/preflight focused matrix；
- BrowserGym contract serialization tests；
- targeted export/settings side-effect scenarios；
- 如 hash出现在 benchmark run identity，更新 schema version并运行相关 clean diagnostic。

## 5.8 Exit gate

```yaml
hash_critical_mutable_fields: 0
observation_nested_mutability: 0
affordance_nested_mutability: 0
action_contract_hash_stale_reproduction: impossible
```

---

# 6. SAR-2 — 统一语义词汇

## 6.1 目标

消除三套 relation、无行为 criterion subclass 和重复 evidence policy。

## 6.2 新 canonical 模块

```text
src/affordance_runtime/semantics.py
```

定义：

```text
CriterionRelation
Criterion
CompositeCriterion
EvidenceStrength
EvidenceSourceKind
EvidencePolicy
CriterionRole
```

## 6.3 迁移顺序

### SAR-2A：新 canonical vocabulary + boundary aliases

- 将现有 `StateCriterionRelation` 内容迁移为 `CriterionRelation`；
- `TaskObligationRelation` 与 `SubgoalOutcomeRelation` 暂时只在 external schema adapter中映射；
- 禁止新增关系到旧 enum。

### SAR-2B：Task intake 使用 canonical criterion

修改：

```text
task_intake.py
intent compiler output binder
canonical obligation compiler
```

目标：TaskSpec 直接持有 task completion criterion / source-bound criteria，不再以另一 relation enum表达同一状态。

### SAR-2C：Task planning provider schema 使用 canonical relation

Provider Pydantic candidate可以保留 discriminator，但值类型来自 `CriterionRelation`。

删除：

```text
SubgoalOutcomeRelation
_action_outcome_relations 的重复 relation set转换
```

Action-family兼容矩阵改为：

```python
Mapping[ActionKind, frozenset[CriterionRelation]]
```

### SAR-2D：简化 criterion hierarchy

删除：

```text
ValueCriterion
PresenceCriterion
AbsenceCriterion
NavigationCriterion
```

迁移 constructors/tests/schema。

## 6.4 One-out 删除

每迁移一个 enum的所有 production使用后，同提交删除该 enum和 `_map_relation()`。

最终：

```text
relation enum count == 1
```

## 6.5 Tests

- schema snapshot；
- provider structured output compatibility；
- all relations round-trip；
- action-family compatibility；
- TaskSpec → StepSpec 无 relation mapping；
- no duplicate relation enum AST gate；
- source provenance保留；
- unary/value relation不变量。

## 6.6 PR breadth

如果 provider schema/ref或 prompt JSON变化：

- targeted LLM task planning replay；
- clean 6×2 PR breadth。

## 6.7 Exit

```yaml
criterion_relation_enums: 1
criterion_atomic_classes: 1
relation_projectors: 0
```

---

# 7. SAR-3 — Plan 垂直替换

> **目标：在这一阶段结束时，默认生产 path 不再使用 `SubgoalSpec`、`TaskPlanDraftProjector`、双 generator port 或 legacy TaskPlan round trip。**

## 7.1 Canonical models

在 `task/contracts.py` 或现有模块中收敛：

```text
PlanRequest
PlanCandidate
TaskPlan
TaskProgress
StepSpec
PlanDecision
TaskPlanGeneratorPort
TaskPlanAuthority
```

### 删除/改名

```text
TaskPlanDraft → PlanCandidate
InitialTaskPlanRequest + TaskPlanRevisionRequest → PlanRequest
TaskPlanDraftGeneratorPort → 删除
TaskPlanGeneratorPort → 唯一 port
TaskPlanView → 仅外部/trace snapshot，production cutover后删除
```

## 7.2 SAR-3A — Rule generator 直接返回 PlanCandidate

当前 `RuleTaskPlanDraftGenerator` 先调用 legacy `RuleTaskPlanner.plan()` 生成 TaskPlan再投影。

改为：

```python
RuleTaskPlanGenerator.generate(PlanRequest) -> PlanCandidate
```

直接从 canonical task criteria/constraints生成 StepSpec。

同一切片删除：

```text
RuleTaskPlanDraftGenerator
TaskPlanDraftProjector 在 rule path 的使用
RuleTaskPlanner production constructor
```

不得在 outcome缺失时发明 `IS_VISIBLE`；无法形成 typed criterion时返回 `PlanDecision.CLARIFICATION_REQUIRED` 或 `REJECTED`。

## 7.3 SAR-3B — LLM generator 直接返回 PlanCandidate

修改当前 `LLMTaskPlanner`：

- provider schema仍只允许 candidate fields；
- provider candidate → canonical StepSpec/PlanCandidate；
- 不生成 UUID plan ID；
- 不设置 plan revision/supersedes/state binding；
- bounded repair仍存在，但验证 candidate，不验证 accepted plan lineage。

同一切片删除：

```text
LLMTaskPlanner._bind_candidate() -> legacy TaskPlan
LLMTaskPlanner._bind_subgoal_candidate() -> SubgoalSpec
legacy LLM TaskPlannerPort output
```

如果需要 compatibility，提供显式 `LegacyTaskPlannerAdapter`，仅 tests/benchmarks，禁止 default Runtime import。

## 7.4 SAR-3C — TaskPlanAuthority initial cutover

实现：

```python
PlanCandidate
→ semantic validator
→ TaskPlanAuthority.admit_initial()
→ accepted TaskPlan
```

TaskPlanAuthority 独占：

```text
PlanRef
based_on_state_version
supersedes
admission decision
```

Coordinator 仍是唯一 install committer。

切换一个真实普通 multi-step internal scenario 和 reference pricing path。

同一切片删除：

```text
TaskPlanLifecycle initial legacy validation path
TaskPlanAuthorityBinder legacy SubgoalSpec binder
legacy initial TaskPlan validator identity部分
```

## 7.5 SAR-3D — Replan cutover

RecoveryPolicy只产生 `REPLAN_STEP/TASK` trigger。

```text
PlanRequest(previous plan/progress/trigger)
→ PlanCandidate
→ TaskPlanAuthority.admit_revision
→ TaskPlan N+1
→ Coordinator replace
```

完成 step不可丢失/重定义。

同一切片删除：

```text
legacy replacement TaskPlanFlow
legacy TaskPlanLifecycle replacement path
TaskPlanView round-trip
```

## 7.6 SAR-3E — Legacy plan model deletion

删除：

```text
SubgoalSpec
legacy TaskPlan model
PlanProgress（若未直接重命名）
TaskPlanDraft
TaskPlanDraftProjector
TaskPlanDraftGeneratorRouter
TaskPlanDraftGeneratorPort
TaskPlanAuthorityBinder legacy conversion
TaskObligationOutcomeCompiler producing legacy plan
PricingTaskPlanner legacy output
```

将 remaining call sites迁移到 canonical `StepSpec/TaskPlan/TaskProgress`。

## 7.7 StateKernel cutover

字段：

```python
task_plan: TaskPlan | None
task_progress: TaskProgress | None
```

方法：

```text
install_task_plan
replace_task_plan
activate_next_step
complete_step
record_step_action
```

删除 subgoal命名方法和 aliases。

## 7.8 Tests

### Contract

- candidate无 authority fields；
- PlanRef deterministic admission/retry policy；
- source refs、criteria、dependencies完整；
- no selector/backend/approval；
- deep immutable；
- revision preserves completed steps。

### Equivalence

- rule obligation-backed plans；
- flat implicit step；
- LLM provider initial/repair/replan；
- reference pricing；
- form sequence；
- action budgets；
- entry feasibility。

### Architecture

```text
SubgoalSpec production imports == 0
TaskPlanDraftProjector imports == 0
generator protocols == 1
legacy TaskPlannerPort imports == 0
```

## 7.9 Behavior gate

这是 production plan authority切换：必须运行完整 local gate和 6×2 PR breadth；失败则回滚 cutover而非添加第三套 projection。

---

# 8. SAR-4 — Planner 直接序列化与封闭响应

## 8.1 目标

删除：

```text
PlanningRequest → PlannerContext → provider payload
custom freeze/thaw blob
mixed PlannerDecision
reflective planner compatibility
```

## 8.2 SAR-4A — 收紧 PlanningRequest

删除重复字段：

```text
task_summary
latest_outcome generic blob
recent_proposals generic blob
verified_effects strings
pending_evidence_obligations
satisfied_action_targets generic map
compatibility active step fields
```

保留：

```text
task
plan/progress summary
active step/scope
observation
last outcome summary
recovery summary
budget
```

删除：

```text
freeze_request_value
thaw_request_value
freeze_request_mapping
thaw_request_mapping
```

## 8.3 SAR-4B — ProviderRequestSerializer

新增：

```text
planner/serializer.py
```

```python
serialize(request, policy, provider_profile) -> tuple[ModelMessage, ...]
```

将现有 context policy version迁移到 serializer policy。

同一切片删除 `PlannerContextBuilder` request path，并将 Generalist/Parent Agent直接使用 serializer输出。

## 8.4 SAR-4C — PlannerResponse union

新增封闭 union并切换 Coordinator：

```text
ActionProposal
ClarificationRequest
FinishProposal
DeferredProposal
PlanIssueReport
```

标准 Planner不得返回 `ActionContract`。

Legacy direct-contract planners必须被：

- 改造成 semantic proposal；或
- 放入显式 adapter，仅 compatibility tests/benchmarks。

同一切片删除 `PlannerDecision.contract/result/planner_context` 混合形态。

## 8.5 SAR-4D — 删除反射兼容

将每个 legacy planner在 composition root显式包：

```python
LegacyPlannerAdapter(legacy)
```

Coordinator字段恢复为纯 `PlannerPort`。

删除：

```text
inspect.signature
PlannerCompatibilityPort union
propose_with_runtime_projection
planner_compatibility.py（legacy count=0时）
```

## 8.6 Tests

- provider payload golden；
- no generic blob；
- closed response invalid combinations impossible；
- Planner不能返回 contract；
- explicit adapter behavior；
- default Coordinator imports no compatibility；
- public signature only request；
- context token/latency metrics等价。

## 8.7 Behavior gate

Provider payload或 Planner output schema变化：完整 targeted model replay + PR breadth。

---

# 9. SAR-5 — UnifiedObservation 与 ActiveStepScope

## 9.1 目标

把复杂度投入项目核心多来源能力，并删除 terminal admission mini-framework。

## 9.2 SAR-5A — PlannerAffordanceView 修复

当前 representative source、单 action和空 conflict投影改为直接从 `UnifiedAffordance` 构建：

```text
surfaces: tuple
supported_actions: tuple
state_facts: tuple
source refs: tuple
conflicts: tuple
conflict status
confidence optional
```

多 action target保留；不因为 `len(actions) != 1` 丢弃。

## 9.3 SAR-5B — ActiveStepScope

新增 scope resolver：

```python
resolve(task_plan, task_progress, active_step, observation) -> ActiveStepScope
```

职责：

- 当前 step依赖已由 Runtime满足；
- 将 step criterion/semantic subject绑定到当前 unified target；
- 返回 allowed actions/targets；
- ambiguity/conflict时空 scope + typed failure。

禁止使用 task name/URL/benchmark。

## 9.4 SAR-5C — ProposalValidator cutover

ProposalValidator检查：

```text
proposal target in scope
proposal action family in scope
proposal identity current
proposal可能推进 active criterion
```

Planner看到 scope作为 bounded hint；Validator是 authority。

## 9.5 SAR-5D — 删除 terminal mini-framework

删除默认路径：

```text
TerminalEffectBindingResolver
TaskObligationViewCompiler
TerminalReadinessEvaluator
LegacyPlannerAdmissionProjector
PlannerAdmissionView
TargetAdmissionDecision
PlannerAdmissionSummary
```

如果高级实验需要，移动到 experiments，不 import core。

## 9.6 Tests

- DOM+A11y+Vision同 target；
- multi-action slider；
- conflicts material；
- current step scope；
- cross-step action rejected；
- terminal target only when active step is terminal；
- stale grounding；
- ambiguity fail-closed；
- no lexical label-only terminal matching。

## 9.7 Behavior gate

Planner可见 target集合会变化，必须运行 PR breadth及多 surface scenarios。

---

# 10. SAR-6 — ActionContract 分组与 ActionOutcome canonicalization

## 10.1 前置

SAR-1 已保证深层 immutable和hash正确。本阶段只重组 owner和字段范围，不再次引入平行合同。

## 10.2 子合同

```text
SemanticAction
TargetBinding
ExecutionPolicy
VerificationPolicy
SafetyPolicy
```

ActionContract 顶层持有这些 typed对象。

## 10.3 TargetBinding

只保留最终选定：

```text
semantic target ID
candidate/backend binding
observation ref
fingerprint
lease
```

完整 route plan、score、alternative candidates和 fallback reason写 trace。

## 10.4 ExecutionAttempt

用 final preflight/rebound/approval observation建立：

```text
execution ref
active step ID
contract ref/body
before observation ref
```

Executor只收 ActionContract。

## 10.5 ActionOutcome

将当前 receipt、post observation、verification、step identity收敛为唯一 ActionOutcome。

Canonical trace每个 execution写一次 `ActionOutcomeRecorded`；旧细粒度事件可继续作为 diagnostics但不作为 production state输入。

## 10.6 删除

- `BoundActionExecution` advanced attribution sidecar从 default core移除；
- contract中 analytics route fields；
- duplicate execution identity字段；
- action后多个相互竞争的 final event。

## 10.7 Tests

- preflight rebound identity；
- approval revalidation；
- contract hash范围；
- executor ticket invisibility；
- exactly one outcome；
- receipt-only不完成；
- trace correlation。

---

# 11. SAR-7 — 单一 Progress 与 Finish Authority

## 11.1 目标

所有任务只通过一个路径完成：

```text
ActionOutcome
→ active step verification
→ TaskProgress
→ task completion verification
```

## 11.2 SAR-7A — Current-step precheck

每轮 planning前验证 active step criterion：

- 已满足 → complete active step，下一轮；
- incomplete → Planner；
- inconclusive/conflict → recovery；
- 每次最多推进一个 step。

## 11.3 SAR-7B — ActionOutcome step commit

使用 `VerificationResult.step_status`：

```text
complete → TaskProgress.complete
incomplete + effect observed → same step next turn
blocked/not observed/inconclusive → recovery
```

删除 legacy `bind_active_subgoal_verifiers` 和 subgoal criteria描述匹配路径，改为 canonical criterion IDs。

## 11.4 SAR-7C — Task completion verifier

当 required steps全部完成：

```text
TaskCompletionVerifier(TaskSpec.completion_criterion)
```

只有 passed才能 TaskCompleted。

Planner FinishProposal只请求该 verifier，不直接完成。

## 11.5 SAR-7D — TaskSkill 降级

TaskSkill只能提供：

```text
PlanCandidate
或 ActionProposal
```

删除：

```text
TaskSkillRunState
activate/expose/checkpoint/fallthrough progress mutation
TaskSkill独立 TaskCompleted分支
```

## 11.6 SAR-7E — ODG 与旧 progress移出 default StateKernel

删除 default字段：

```text
obligation_progress
pending_obligations
```

ODG代码移动到 experimental state extension。

## 11.7 SAR-7F — Action dedupe

`ActionProgressRecord` 改为 bounded：

```python
ActionKey(action_kind, target_id, parameter_digest)
RecentActionOutcomeIndex
```

不保存全部 history，不用 JSON string signature。

## 11.8 Tests

- flat task；
- serial text→select→slider→checkbox→submit；
- cross-step action拒绝；
- one action最多一 step；
- current-state next step precheck；
- last step后 task criterion仍未满足；
- TaskSkill不能完成 task；
- receipt/reward不能完成；
- ODG default import absent。

## 11.9 Behavior gate

这是 progress/finish authority切换，必须完整 PR breadth和 fresh diagnostic。

---

# 12. SAR-8 — Recovery 协议统一

## 12.1 目标

合并：

```text
RecoveryAction/Incident/Attempt/Cascade
FailureEnvelope/RecoveryPlan/Command/Receipt/Delta/History
```

## 12.2 Canonical contracts

```text
Failure
RecoveryDecision
RecoveryOutcome
RecoverySummary
```

## 12.3 Policy

RecoveryPolicy输入：

```text
Failure
last ActionOutcome
active step
latest observation
budgets
attempted strategy keys
```

输出 bounded decision：

```text
reobserve
reground
switch_backend
retry
replan_step
replan_task
restore_checkpoint
ask_user
terminate
```

## 12.4 Execution

纯 runtime transition：

```text
reobserve / replan / ask user
```

不产生独立 receipt/delta链。

真实 side effect：

```text
restore checkpoint / provider switch with external operation
```

产生 RecoveryOutcome。

## 12.5 删除

```text
RecoveryIncident history in StateKernel
RecoveryReceipt list
RecoveryDelta list
RecoveryHistory list
parallel RecoveryHandler/Coordinator/Dispatcher职责
```

保留一个 RecoveryPhase service。

## 12.6 Tests

- stale → reobserve/reground；
- backend unavailable → switch；
- uncertain side effect → verify before retry；
- no-op recovery拒绝；
- repeat/cascade bounded；
- replan trigger进入 TaskPlanAuthority；
- budget exhaustion；
- recovery state minimal。

---

# 13. SAR-9 — StateKernel 与 Coordinator 缩减

## 13.1 StateKernel 最终字段

```text
task_spec
task_plan
task_progress
latest_observation_ref
current_contract
last_action_outcome
current_failure
current_recovery
budgets
phase
final_result
state_version
```

可保留极少 bounded summaries，但不得保存完整历史列表。

## 13.2 历史迁移

```text
observations → Trace + ArtifactStore
receipts → ActionOutcome trace
planner_history → model/diagnostic trace
probe_receipts → diagnostic trace
recovery_history → recovery events
route analytics → subscriber store
grounding fallback lineage → diagnostics/artifacts
```

## 13.3 Coordinator phase services

```text
PerceptionPhase
PlanningPhase
ExecutionPhase
ProgressPhase
RecoveryPhase
```

每个返回：

```python
@dataclass(frozen=True)
class PhaseResult:
    transition: StateTransition
    events: tuple[RuntimeEvent, ...]
    next_phase: RuntimePhase
```

Phase不能直接写 StateKernel/Trace；Coordinator串行提交。

## 13.4 提取顺序

1. ProgressPhase（authority已统一）；
2. PlanningPhase；
3. ExecutionPhase；
4. RecoveryPhase；
5. PerceptionPhase。

每提取一个 phase：

- 删除 run_sync 中对应 inline算法；
- 不增加 parallel owner；
- 更新 import gate；
- 下调 architecture report基线。

## 13.5 Coordinator 目标

不是按固定行数验收，而是按职责：

```text
无 task-specific regex
无 criterion matching
无 route scoring
无 verifier repair算法
无 recovery policy算法
无 trace payload构造
```

## 13.6 Tests

- phase output pure；
- transition唯一 writer；
- trace event顺序；
- state version增长；
- failure interruption；
- async wrapper；
- full existing integration。

---

# 14. SAR-10 — Analytics / Evolution / Benchmark 移出同步 Core

## 14.1 Event bus

最小 in-process best-effort subscriber接口：

```python
class RuntimeEventSubscriber(Protocol):
    def handle(self, event: RuntimeEvent) -> None: ...
```

subscriber失败：

- 记录 diagnostic；
- 不改变 RunResult；
- 不触发 recovery。

## 14.2 移动对象

```text
RouteCalibrator
SkillMiner/evolution
Benchmark collector
Langfuse/OTel exporter
policy analytics
```

## 14.3 包边界

```text
analytics/
evolution/
benchmarks/
integrations/
experiments/
```

Core imports这些包的 gate应为禁止；composition root反向注册 subscriber。

## 14.4 Tests

- subscriber故障不影响 task；
- outcome event内容完整；
- no reverse imports；
- benchmark adapter不影响 completion。

---

# 15. SAR-11 — 公共 API 与 Governance Gate 收缩

## 15.1 Public API

更新 `__init__.py`：

### 导出

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

### 不导出

```text
StateKernel
TaskEnvelope
PlannerDecision
RouteCalibrator internals
projection/migration types
compatibility ports
```

提供 migration deprecation cycle，不允许新调用。

## 15.2 Blocking gates 保留

```text
authority import/mutation
public signatures
core→benchmark/experiment reverse dependency
deep immutability
single completion authority
task-specific branch
```

## 15.3 降级为 report

```text
line counts
method counts
complexity
文档精确短语
历史 slice名称
多个 Markdown current revision同步
```

## 15.4 删除 YAML 膨胀规则

只对以下变更要求 ADR/change record：

- authority迁移；
- public API；
- persistent schema；
- security boundary；
- benchmark/promotion claim。

小型纯 refactor不要求独立 change-admission YAML。

## 15.5 Tests

- public import snapshot；
- internal module inaccessible by documented API；
- architecture report生成；
- blocking gate不依赖文案。

---

# 16. SAR-12 — 全量删除审计与评估

## 16.1 Delete inventory gate

最终 grep/AST 应为：

```yaml
TaskObligationRelation: 0 production definitions
SubgoalOutcomeRelation: 0
StateCriterionRelation: 0
SubgoalSpec: 0 production imports
TaskPlanDraftProjector: 0
TaskPlanDraftGeneratorPort: 0
PlannerContext: 0 production imports
freeze_request_value: 0
thaw_request_value: 0
PlannerDecision: 0 public/default imports
inspect.signature planner dispatch: 0
PlannerAdmissionView: 0 default imports
TaskSkillRunState: 0
ObligationProgressLedger in StateKernel: false
pending_obligations in StateKernel: false
parallel recovery protocols: 0
core import benchmarks/experiments: 0
```

## 16.2 Evaluation order

1. unit/full pytest；
2. Ruff/mypy/build/diff；
3. Chromium/DOM/A11y/Vision/WoT focused scenarios；
4. serial non-BrowserGym suite；
5. PR breadth 6×2；
6. fresh diagnostic；
7. safety/approval/export；
8. ablation：DOM-only / Vision-only / WoT-only / Unified；
9. recovery on/off；
10. architecture report comparison。

## 16.3 Required metrics

- task success；
- Runtime success；
- false completion；
- stale action rejection；
- unsafe side effect；
- model calls；
- action count；
- latency；
- recovery success；
- Planner-visible target/action coverage；
- StateKernel field count；
- Coordinator owned algorithms；
- compatibility adapter count；
- production model count；
- relation enum count。

## 16.4 Promotion

PR breadth/fresh diagnostic通过只产生 eligibility；promotion必须独立记录：

```text
same revision
clean tree
full evidence bundle
no blocked architecture gate
no compatibility deletion debt marked critical
```

---

# 17. 具体提交序列建议

```text
01 docs: freeze authoritative optimized architecture

02 test: reproduce nested contract mutation and stale digest
03 refactor: deeply freeze runtime contracts
04 refactor: remove mutable contract constructors and duplicate freeze helpers

05 test: add canonical criterion vocabulary equivalence
06 refactor: migrate task and step semantics to CriterionRelation
07 refactor: delete duplicate relation enums and nominal criterion classes

08 test: add direct rule PlanCandidate generation
09 feat: cut rule planning to PlanCandidate and TaskPlanAuthority
10 refactor: delete rule legacy TaskPlan projection path

11 test: add LLM PlanCandidate provider equivalence
12 feat: cut LLM task planning to PlanCandidate
13 refactor: delete legacy LLM TaskPlan binding and duplicate generator port

14 feat: cut initial TaskPlan admission to canonical TaskPlanAuthority
15 feat: cut replan admission to canonical TaskPlanAuthority
16 refactor: delete SubgoalSpec, legacy TaskPlan, TaskPlanView and lifecycle projectors

17 test: add direct PlanningRequest provider serialization
18 refactor: replace PlannerContext with serializer
19 refactor: replace PlannerDecision with PlannerResponse union
20 refactor: delete reflective planner compatibility

21 feat: preserve multi-surface/multi-action UnifiedObservation in planner view
22 feat: add ActiveStepScope and proposal scope gate
23 refactor: delete terminal admission mini-framework

24 refactor: group immutable ActionContract and narrow hash payload
25 feat: canonicalize ExecutionAttempt and ActionOutcome
26 refactor: delete default advanced attribution sidecar

27 feat: cut active-step progress authority
28 feat: add independent task completion verifier
29 refactor: remove TaskSkill/ODG/pending-obligation completion paths

30 refactor: unify recovery protocol
31 refactor: delete legacy recovery commands/incidents/history duplication

32 refactor: extract progress/planning/execution/recovery/perception phases
33 refactor: trim StateKernel histories to refs/current state

34 feat: publish runtime events to best-effort subscribers
35 refactor: move route/evolution/benchmark analytics out of core

36 refactor: narrow public API
37 refactor: replace prose/line blocking gates with code-invariant gates

38 docs: record final deletion inventory and evidence identity
39 test: archive clean PR breadth and fresh diagnostic
```

每组提交必须保持可回滚；不得把 10 个 authority变化合并为一个大提交。

---

# 18. 子 Agent 分工与 Token 约束

每个生产 slice只有一个 integrator/production writer。

适合子 Agent：

- read-only call-site inventory；
- duplicate enum/import search；
- test matrix审查；
- final diff review；
- benchmark evidence归档检查。

不适合并行委派：

- canonical type/interface决策；
- StateKernel mutation；
- Coordinator cutover；
- TaskPlanAuthority和progress authority；
- public API删除。

子 Agent 输出必须是 bounded packet：

```yaml
scope:
findings:
files:
risks:
recommended_delete:
no_code_changes: true
```

---

# 19. 每阶段统一 Definition of Done

```yaml
canonical_owner:
  exactly_one: true

legacy_owner:
  deleted_or_explicitly_deprecated: true
  deletion_gate_recorded: true
  new_production_imports: false

projections:
  added: at_most_one
  deleted: at_least_one_when_replacing_existing_model

immutability:
  public_typed_results_deeply_immutable: true

state:
  production_authorities: one

validation:
  red: demonstrated
  focused: pass
  full_pytest: pass
  ruff: pass
  mypy: pass
  uv_build: pass
  diff_check: pass

behavior_evidence:
  required_when_changed: complete

claims:
  official_score_claimed: false
  promotion: held_until_separate_decision
```

---

# 20. 立即下一步

基线 `648c2da...` 的下一项不再是旧定义的 `TPA-5B LLM TaskPlan generator draft migration`。

立即执行：

```text
SAR-0：将本架构设为唯一权威，停止 additive foundation
    ↓
SAR-1：深层不可变与 ActionContract stale hash correctness
```

原因：

- `ActionContract` digest用于 approval token绑定；
- 当前内部 dict/list 可在构造后被修改；
- 这是 correctness/security 风险；
- 在这一风险关闭前继续增加 PlanCandidate/Authority foundation会扩大依赖错误对象的代码面。

SAR-1 完成后，按顺序进入：

```text
SAR-2 单一语义词汇
→ SAR-3 Plan 垂直替换
```

不得跳过 SAR-1，亦不得继续通过 projector 把新 StepSpec 转回固定 `READ_ONLY` 的 legacy SubgoalSpec。

# Affordance Runtime 简化架构实施计划（颗粒度版）

> **建议仓库路径：** `docs/superpowers/plans/2026-07-29-affordance-runtime-simplification-execution-plan.md`  
> **文档类型：** Incremental Implementation Plan / Change-Admission Program  
> **状态：** `PROPOSED_FOR_EXECUTION`  
> **目标架构：** `2026-07-29-affordance-runtime-simplified-target-architecture.md`  
> **基线分支：** `agent/migrate-runtime-components`  
> **基线 revision：** `21f49e730a24640b00ef42fd3a3e98e1813f6656`  
> **当前生产进度权威：** legacy `TaskPlan / Subgoal / PlanProgress`  
> **当前 ODG 状态：** foundation/diagnostic only；ODG-10/11 未授权  
> **日期：** 2026-07-29

---

## 0. 执行摘要

本计划把当前默认架构从：

```text
TaskPlan/Subgoal authority
+
不断扩张的 ODG generic attribution foundation
```

迁移为：

```text
TaskSpec
→ TaskPlan / implicit active step
→ immutable PlanningRequest
→ step-scoped PlannerProposal
→ ActionContract
→ ExecutionAttempt
→ independent verification
→ ActionOutcome
→ active-step transition
→ task-level final verification
```

迁移遵循：

```text
freeze
→ contracts
→ compatibility projection
→ immutable planner input
→ active-step scope
→ ActionOutcome shadow
→ flat cutover
→ serial cutover
→ isolate ODG
→ recovery/trace convergence
→ evaluation
```

不允许大爆炸重写，不允许三套 progress authority 并存，不允许通过降低 verifier、finish guard、stale-state 或 approval 边界取得通过。

---

## 1. 当前基线

### 1.1 Repository identity

```yaml
current_head: 21f49e730a24640b00ef42fd3a3e98e1813f6656
branch: agent/migrate-runtime-components
remote_match: true
remote_ci: disabled
promotion: held
```

### 1.2 当前架构状态

- `BoundActionExecution` 与 ODG-9 shadow projection 已存在，但未接入 Coordinator；
- ODG-10 obligation ledger commit 未授权；
- ODG-11 finish authority switch 未授权；
- 标准 PlannerPort 仍接收 mutable StateKernel；
- legacy TaskPlan/Subgoal 仍是生产 progress authority；
- latest PR breadth evidence 仍非 acceptance/promotion 证据；
- Coordinator 与 `run_sync()` 已接近/达到增长冻结线。

### 1.3 当前 active ratchets

```text
coordinator.py <= 3461 lines
RunCoordinator methods <= 26
RunCoordinator.run_sync <= 2034 lines
task_planning.py <= 1642 lines
GeneralistLMPlanner.propose <= 222 lines
LLMIntentCompiler.compile <= 253 lines
TaskPlanValidator.validate <= 239 lines
```

迁移 change 不得提高 ceiling。每次抽取完成后，应将 ceiling 降至新实际值。

---

## 2. 全局执行规则

### 2.1 单一 writer

每个 slice：

```yaml
production_writers: 1
interface_owner: main_integrator
reviewer: optional_diff_only
parallel_core_writers: prohibited
```

### 2.2 双轨一门

最多同时：

- 一个 vertical simplification slice；
- 一个 unrelated horizontal debt slice。

如果 horizontal work触及同一 Planner/State/Coordinator contract，则串行执行。

### 2.3 Authority declaration

每个 revision 必须记录：

```yaml
production_progress_authority:
shadow_progress_model:
task_completion_authority:
state_writer:
trace_writer:
```

### 2.4 禁止项

所有 slice 默认禁止：

- task-name / URL / selector / seed 分支；
- Prompt-only repair；
- model/retry/budget 扩张；
- receipt/external reward completion；
- Coordinator 中新增 criterion matcher；
- Planner-authored step completion；
- Executor/Verifier 接收 mutable StateKernel；
- advanced attribution 进入默认 completion；
- 为通过测试弱化 ActionContract safety。

### 2.5 统一验证

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

Authority cutover slice额外：

```text
non-BrowserGym end-to-end
targeted BrowserGym
clean PR breadth
current revision evidence archive
```

---

## 3. Authority 迁移表

| 阶段 | Flat task progress authority | Multi-step progress authority | New path | ODG |
|---|---|---|---|---|
| S0–S4 | legacy | legacy | contracts / validation shadow | experimental frozen |
| S5 | legacy | legacy | ActionOutcome shadow | diagnostic only |
| S6 | active-step | legacy | flat authority | experimental |
| S7 | active-step | active-step | serial authority | experimental |
| S8+ | active-step | active-step | default | isolated experiment |

任何阶段不得让 legacy、active-step 与 obligation ledger同时具有 completion authority。

---

## 4. 执行依赖图

```text
S0 Architecture Freeze
    ↓
S1 Simplified Core Contracts
    ↓
S2 Legacy → Step Compatibility Projection
    ↓
S3 Immutable PlanningRequest
    ↓
S4 ActiveStepScope + Proposal Gate
    ↓
S5 ActiveStepVerifier + ActionOutcome Shadow
    ↓
S6 Flat-task Authority Cutover
    ↓
S7 Serial Multi-step Authority Cutover
    ↓
S8 Default ODG Isolation + Legacy Authority Retirement
    ↓
S9 Recovery + Canonical Trace Convergence
    ↓
S10 PR Breadth + Fresh Diagnostic
    ↓
S11 Optional Physical Module Reorganization
```

---

# 5. S0 — 架构冻结

## S0.1 目标架构入库

### 目标

- 将目标架构和本实施计划写入仓库；
- 停止 ODG-9 diagnostic hookup；
- 停止 ODG-10/11；
- 不修改 Runtime 行为。

### 修改

```text
docs/superpowers/specs/...
docs/superpowers/plans/...
docs/current-implementation-plan.md
docs/implementation-status.md
docs/architecture-governance-track.md
.codex/goal-plan.md
```

### 文档状态

```yaml
odg_2_to_9:
  status: experimental_foundation
odg_10:
  status: stopped
odg_11:
  status: stopped
default_target:
  progress_authority: active_step
```

### Exit

- 所有 current docs 指向 exact HEAD；
- active vertical lane 改为 S1；
- promotion held；
- 无生产 diff。

## S0.2 默认路径实验隔离门禁

新增 architecture tests：

1. `coordinator.py` 不新增 ODG import；
2. `state_kernel.py` 不新增 obligation ledger authority；
3. `contract_execution_loop.py` 不新增 ticket use beyond existing foundation；
4. default Runtime profile 不 import experiment package；
5. ODG types不能产生 StepCompleted/TaskCompleted。

### Rollback

纯文档/门禁 slice，无行为回滚。

### 建议 commit

```text
docs: freeze simplified runtime target architecture
test: freeze advanced attribution outside default completion path
```

---

# 6. S1 — 简化核心合同

S1 只建立 neutral contracts，不改变生产行为。

## S1.1 SourceReference 与 criterion contracts

### 新增

```text
SourceReference
CriterionEvidencePolicy
ValueCriterion
StateCriterion
PresenceCriterion
AbsenceCriterion
NavigationCriterion
ArtifactCriterion
ApiCriterion
CompositeCriterion
```

### Owner

```text
new owner: step/criterion contracts module
old owner: scattered TaskObligation/VerifierSpec semantics
```

### 要求

- frozen；
- no mutable dict/list；
- exact source refs；
- no arbitrary expression execution；
- minimum evidence strength；
- explicit all_of/any_of。

### RED

- blank criterion ID；
- mutable nested value；
- unsupported relation；
- composite cycle；
- missing source ref for effectful criterion；
- precondition mistaken for completion criterion。

## S1.2 StepSpec / TaskPlan view

新增目标 view，而非第二套 production plan：

```text
StepSpec
TaskPlanView
StepProgressView
```

`TaskPlanView` 从当前 TaskPlan projection，暂不独立修改。

### Tests

- stable exact-ID projection；
- dependency preservation；
- completed evidence preservation；
- no lexical mapping；
- stale plan revision。

## S1.3 ExecutionAttempt / VerificationResult / ActionOutcome

新增：

```text
ObservationIdentity
ExecutionAttempt
StateDelta
VerificationResult
ActionOutcome
ActionOutcomeSummary
```

### 不改

- Executor；
- Verifier pass/fail；
- StateKernel；
- trace；
- Coordinator。

### Exit

- types deep immutable；
- no StateKernel/Coordinator dependency；
- full local gate。

### 建议 commits

```text
feat: add simplified step criterion contracts
feat: add execution attempt and action outcome contracts
```

---

# 7. S2 — Legacy compatibility projection

## S2.1 TaskPlan → Step projection

### 输入

```text
current TaskPlan
current PlanProgress
current TaskSpec
```

### 输出

```text
TaskPlanView
active StepSpec
completed step IDs
step evidence
```

### 映射规则

- exact subgoal/criterion identity only；
- source refs从 TaskSpec/TaskPlan authority投影，`source_unit_id` 与 `claim_id`
  必须分开保存；
- 不使用 label/regex/task name；
- unsupported shape返回 typed `projection_invalid`；
- missing or unsupported typed evidence policy 返回
  `unsupported_evidence_policy`，不得进入未来 active-step completion
  authority；
- completed plan 使用 `activity_status=completed` 且 `active_step_id=null`；
- ready-but-not-activated step 使用 `activity_status=ready_not_activated`
  且 `active_step_id=null`，由 Coordinator 后续显式 activation；
- completed / failed / active / evidence step IDs 必须全部属于 projected
  plan step IDs；
- completed step 必须有 verifier evidence；
- 不修改 state。

## S2.2 Task-level completion criterion projection

为当前 TaskSpec建立 task-level criterion view。若当前 schema不能无歧义投影：

```text
status = pending / unsupported
```

不得从 external reward推断。

## S2.3 Shadow trace

可选记录：

```text
SimplifiedStepProjectionCompared
```

只诊断：

- active identity；
- completed identity；
- criterion coverage；
- projection failure。

不得改变 progress。

### Exit

- form-sequence、button-sequence、flat text等 current cases有 projection；
- 调用前后 StateKernel.version不变；
- no Coordinator algorithm；
- no behavior change。

### Rollback

删除 projector / diagnostic event，不影响现有 Runtime。

---

# 8. S3 — Immutable PlanningRequest

这是不可继续延期的 horizontal boundary。

## S3.1 Planner read-set inventory

逐个记录：

```text
GeneralistLMPlanner
ParentAgentPlannerAdapter
reference planners
DecisionConstraintBuilder
PlannerContextBuilder
```

实际读取字段。

禁止按 StateKernel 全字段生成 view。

输出：

```text
docs/audits/planner-state-read-set.md
```

## S3.2 Immutable views

新增：

```text
PlannerTaskView
PlannerStepView
PlannerObservationView
PlannerOutcomeSummary
PlannerRecoverySummary
RuntimeBudgetView
PlanningRequest
```

所有集合：

```text
list → tuple
dict → discriminated type / immutable entries
set → tuple
```

## S3.3 PlanningRequestBuilder

唯一 StateKernel projection owner：

```python
build(
    task,
    step_projection,
    unified_observation,
    state,
) -> PlanningRequest
```

禁止：

- mutation；
- trace；
- Planner invocation；
- terminal decision；
- active-step activation。

## S3.4 调用点迁移

顺序：

```text
PlannerContextBuilder
DecisionConstraintBuilder
GeneralistLMPlanner
Parent adapter
reference planners
PlannerPort
Coordinator call site
```

旧三参数标准路径删除；必要 compatibility adapter只转发，不保留第二实现。

### RED

- Planner module import StateKernel；
- request共享 state 内部 mutable collection；
- request build改变 state version；
- stale observation；
- Planner尝试 mutation；
- async Planner兼容。

### Exit

```text
planning_contracts.py no StateKernel import
generalist_planner.py no StateKernel import
planner_context.py no StateKernel import
adapters no StateKernel input
```

### 评估

不跑 PR breadth；运行 full behavior suite和 targeted planner tests。

---

# 9. S4 — ActiveStepScope 与 proposal gate

## S4.1 Scope contract

新增：

```text
ActiveStepScope
StepScopeResolution
StepActionAuthorization
```

字段：

```text
step_id
criterion_id
progress target IDs
allowed effectful actions
support target IDs
allowed support actions
observation identity
```

## S4.2 Scope resolver

输入：

```text
StepSpec
UnifiedObservation
grounding / target identity
```

输出：

```text
resolved
ambiguous
unavailable
stale
invalid
```

禁止 lexical benchmark matching。

## S4.3 ProposalValidator shadow

先计算：

```text
legacy validator result
new step-scope authorization
```

只 trace divergence。

## S4.4 Scope enforcement

RED：

```text
slider step → checkbox effectful action rejected
checkbox step → submit rejected
same step repeated press_key allowed
read-only reobserve/support action allowed only by policy
ambiguous target → reground/clarify
unsupported support action → reject
```

### 注意

Active-step scope不能过度限制同一步所需的辅助动作。辅助 effectful action必须：

- 明确属于 step support scope；
- 不完成其它 step；
- 仍经过 ActionContract与Verifier。

### Exit

- cross-step effectful proposals在执行前被拒绝；
- current valid behavior不回归；
- no Coordinator special case。

### Rollback

scope enforcement由临时 migration profile控制；发生 false reject时回到 shadow，保留证据。

---

# 10. S5 — ActiveStepVerifier 与 ActionOutcome shadow

## S5.1 Current-step precheck

新增 authority-free：

```python
CurrentStepVerifier.verify(step, observation) -> StepPrecheckResult
```

只使用独立 observation evidence。

状态：

```text
complete
incomplete
inconclusive
blocked
```

Shadow 阶段不提交 step。

## S5.2 ActiveStepVerifier

输入：

```text
ExecutionAttempt
StepSpec
before observation
after observation
ActionReceipt
existing VerificationReport/evidence
```

输出 `VerificationResult`。

必须区分：

```text
action effect observed but step incomplete
step complete
effect absent
inconclusive
blocked
```

## S5.3 ActionOutcome builder

每个 effectful attempt创建一个 canonical `ActionOutcome` shadow。

### Trace

记录 diagnostic：

```text
ActionOutcomeProjected
```

与 legacy SubgoalProgress 比较：

```text
aligned
legacy_complete_new_incomplete
legacy_incomplete_new_complete
criterion_unprojectable
identity_mismatch
```

## S5.4 TaskCompletionVerifier shadow

所有 projected required steps complete后，验证 TaskSpec completion criterion，但不改变任务完成。

### Exit

- non-BrowserGym serial scenario shadow结果合理；
- no state mutation；
- no extra Planner/Executor calls；
- one outcome per execution；
- full suite pass。

---

# 11. S6 — Flat task authority cutover

## S6.1 Implicit step

对于单 criterion、无 dependency、无特殊阶段预算任务：

```text
TaskPlan = None
active_step = Runtime-generated implicit StepSpec
```

不调用模型 TaskPlanner。

## S6.2 State transition

Coordinator 接收 `VerificationResult`：

```text
complete    → complete implicit step
incomplete  → continue
blocked     → recovery
effect absent/inconclusive → recovery policy
```

## S6.3 Task final verification

Implicit step完成后验证 TaskSpec completion criterion，再提交 TaskCompleted。

## S6.4 范围

首批：

```text
read one value
activate one target
type one value
select one option
```

## S6.5 接受条件

- receipt-only不能完成；
- external reward不能完成；
- TaskPlan不存在也可完成；
- ActionContract safety不变；
- stale/rebound/approval正常；
- legacy flat path与新 path结果等价。

## S6.6 Evidence

运行：

```text
focused non-BrowserGym
targeted BrowserGym flat family
clean committed evidence
```

### Rollback

temporary migration profile切回 legacy flat path；不得保留半提交 state。

---

# 12. S7 — 串行多步骤 authority cutover

## S7.1 Step scheduler

规则：

```text
ready steps = dependencies completed
default active = deterministic first ready step
one active step
```

## S7.2 Commit barrier

每个 effectful action：

```text
ExecutionAttempt
→ execute
→ post-observe
→ verify
→ ActionOutcome
→ commit at most one active step
→ next planning turn
```

## S7.3 Current-state precheck

下一 step激活后，下一轮 observation可直接证明 step完成，但一次 turn最多推进一个 step。

## S7.4 Target scenarios

```text
text → select → slider → checkbox → submit
button A → button B
WoT write → DOM confirmation
export → approval → artifact verification
```

## S7.5 Task final criterion

所有 required steps完成后仍需 task-level verification。

## S7.6 Legacy comparison

切换前：

```text
new active-step path shadow
legacy subgoal path authority
```

切换 revision：

```text
active-step path authority
legacy projection diagnostic only
```

## S7.7 接受条件

- Planner不能跨 step；
-一个 action最多完成一个 step；
- no receipt/reward completion；
- form-sequence Runtime guard residual关闭或有新明确 root cause；
- recovery在同一路径；
- state version、trace lineage确定；
- PR breadth无安全回归。

### Rollback

回到 legacy multi-step authority，保留 new ActionOutcome trace作为诊断；不得双提交。

---

# 13. S8 — 隔离高级 Attribution 与退休旧 authority

## S8.1 Default import gate

默认：

```text
coordinator.py
state_kernel.py
planning request
contract execution
step verifier
```

不得 import：

```text
obligation_attribution
obligation_progress
obligation_current_state
obligation_progress_shadow
obligation_attribution_flow
```

## S8.2 移除默认 ODG hooks

- 停止 ODG shadow events；
- 停止 ticket carry；
- 不初始化 obligation ledger；
- 保留 experiments runner。

## S8.3 Legacy subgoal authority retirement

移除默认调用：

```text
TaskPlanLifecycle.completed as task final authority
state.complete_subgoal in new standard path
active-subgoal-only evidence binding
required-obligation discard/replacement workaround
```

Compatibility profile可暂留，但不得作为 default。

## S8.4 物理迁移

只有调用点清单为零后，移动到：

```text
experiments/advanced_progress_attribution/
```

提供短期 re-export facade，必须标 expiry。

### Exit

- default profile no ODG imports；
- one progress authority；
- architecture tests enforce；
- full suite；
- no benchmark regression。

---

# 14. S9 — Recovery 与 Trace 收口

## S9.1 Recovery input

统一为：

```text
TypedFailure
ActionOutcome | None
active StepSpec
latest UnifiedObservation
remaining budget
recovery history
```

## S9.2 Recovery decision

所有 decision仍走正常 owners：

- reobserve → observation service；
- reground → target resolver；
- switch backend → router；
- retry → execution loop；
- replan → task planner；
- ask user / terminate → Coordinator transition。

## S9.3 Canonical trace

新增并稳定：

```text
ExecutionAttemptStarted
ActionOutcomeRecorded
StepCompleted
TaskCompletionVerified
```

旧 verifier、grounding、route events标 diagnostic。

## S9.4 Coordinator reduction

提取一个 named responsibility，例如：

```text
PostActionOutcomeFlow
```

输入 immutable context，输出 typed preparation；Coordinator只提交。

要求：

```text
coordinator.py < current ceiling
run_sync < current ceiling
new RunCoordinator methods <= 250 lines
```

---

# 15. S10 — 评估与推广判断

## S10.1 非 BrowserGym

必须通过：

- flat tasks；
- serial form；
- button sequence；
- DOM+Vision；
- DOM+WoT；
- stale target；
- backend switch；
- approval；
- verifier inconclusive；
- recovery no-op rejection。

## S10.2 PR breadth

同一 clean committed revision：

```text
6 tasks × 2 seeds
12 observed
0 missing/unrun/invalidated/provider failure
external reward不低于稳定基线
Runtime failures不增加
```

仍：

```text
official_score_claimed=false
promotion=held
```

直到完整 acceptance满足。

## S10.3 Fresh diagnostic

只有：

- flat + multi-step authority稳定；
- PR breadth accepted；
- full local-equivalent gate；
- exact revision identity；

才运行 fresh diagnostic。

## S10.4 Promotion

remote CI disabled时不能声明 remote-green。Promotion另行批准。

---

# 16. S11 — 可选物理模块重组

只在 ownership稳定、default ODG隔离、Coordinator已缩减后进行。

原则：

- 按变化原因移动；
- 每次一个 package boundary；
- compatibility re-export保持 object identity；
- 不同时改变行为；
- 不以 LOC 为唯一目标。

建议顺序：

```text
planning contracts
verification contracts
runtime outcome
perception target identity
recovery contracts
trace exporters
```

---

## 17. 测试矩阵

| 层 | 必测内容 |
|---|---|
| Contract | immutable, identity, invalid/stale/ambiguity |
| Projection | exact mapping, no lexical guess, no mutation |
| Planner | immutable input, step scope, async compatibility |
| Proposal | target/action compatibility, cross-step rejection |
| Contract | stale, lease, fingerprint, capability, approval |
| Execution | receipt semantics, backend errors |
| Verification | effect vs step, receipt-only inconclusive |
| State | one outcome, one step, task final criterion |
| Recovery | real state change, bounded attempts |
| Trace | canonical event cardinality and lineage |
| Architecture | imports, authority, ratchets, default experiment isolation |
| Evaluation | flat, serial, multisurface, PR breadth |

---

## 18. Slice Change-Admission 模板

每个 production/public-contract slice创建：

```yaml
slice_id:
base_revision:
change_type:
single_responsibility:

owner_before:
owner_after:

typed_input:
typed_output:

production_progress_authority:
shadow_model:

state_writer:
trace_writer:

dependencies_added:
dependencies_removed:

included:
excluded:
forbidden:

old_path_removed:
tests:
rollback_trigger:
evidence_identity:

architecture_admission: not_evaluated
promotion_status: held
```

---

## 19. 建议提交序列

```text
1. docs: freeze simplified runtime target architecture
2. test: isolate advanced attribution from default completion
3. feat: add simplified step criterion contracts
4. feat: add execution attempt and action outcome contracts
5. feat: project legacy task plans into immutable step views
6. feat: migrate planners to immutable PlanningRequest
7. test: add active-step proposal scope REDs
8. feat: enforce active-step proposal scope
9. feat: project active-step verification and ActionOutcome
10. feat: enable implicit-step flat task path
11. feat: switch serial task progress to active-step authority
12. refactor: isolate advanced attribution experiments
13. refactor: converge recovery on ActionOutcome
14. feat: emit canonical ActionOutcome trace
15. docs: archive clean simplified-runtime evaluation
```

不要把这些提交压缩成一个 PR 内的无边界混合 diff；可以在同一长期分支上串行提交，但每个 authority切换点必须独立可回滚。

---

## 20. Benchmark 运行节点

| 节点 | PR breadth |
|---|---|
| S0–S4 contract/shadow | 不需要 |
| S5 ActionOutcome shadow | targeted diagnostic only |
| S6 flat cutover | flat targeted |
| S7 serial cutover | full clean 6×2 |
| S8 ODG isolation | full clean 6×2 if behavior surface touched |
| S9 recovery change | targeted recovery + full suite |
| S10 | PR breadth + fresh diagnostic |

---

## 21. 风险与控制

| 风险 | 控制 |
|---|---|
| Active-step scope过窄 | shadow-first，记录 false reject；支持显式 support actions |
| Planner跨step行为被隐藏 | proposal gate在执行前拒绝 |
| Step全部完成但任务没完成 | TaskCompletionVerifier |
| 新旧进度双提交 | authority table + architecture test |
| Flat path绕过 safety | 仍使用 ActionContract/preflight/Verifier |
| 新类型形成平行 TaskSpec | projection-only，旧 authority未切换前不可独立修改 |
| Coordinator继续增长 | seam extraction + ratchet下调 |
| ODG代码继续渗透 | default import gate |
| Trace删得过早 | canonical/diagnostic分层，渐进退役 |
| Benchmark驱动特例 | no task-name/URL/selector rules |
| Recovery成为第二执行路径 | command owner回主 loop |
| external reward影响完成 | hard architecture test |

---

## 22. 子 Agent 与 Token 策略

默认单 integrator。

允许子 Agent：

- read-only read-set inventory；
- isolated log classification；
- final diff-only architecture review。

禁止并行 production writers触及：

```text
coordinator.py
state_kernel.py
PlannerPort
PlanningRequest
TaskSpec/TaskPlan schema
VerificationResult
ActionOutcome
completion authority
```

子 Agent任务包最多包含：

- exact base revision；
- one responsibility；
- 5–8 relevant files；
- normative invariants；
- fixed output schema。

---

## 23. Definition of Done

### 单 slice

- one responsibility；
- owner before/after明确；
- typed I/O；
- state/trace authority不扩散；
- old path删除或明确 shadow；
- positive/negative/stale/ambiguity tests；
- full local gates；
- exact revision evidence；
- docs同步。

### Active-step default path

```text
Planner input immutable
proposal step-scoped
one action → one ActionOutcome
one ActionOutcome → at most one step
receipt/reward不能完成
task criterion独立验证
recovery同路径
ODG不在default imports
```

### 项目评估

- PR breadth acceptance；
- fresh diagnostic；
- safety/regression无退化；
- promotion另行授权。

---

## 24. Immediate Next Actions

从当前 `21f49e...` 开始：

```text
1. 提交 S0 两份架构文档与治理同步
2. 新增“默认 completion 不再扩张 ODG”的架构门禁
3. 创建 S1 change-admission record
4. 写 SuccessCriterion / ExecutionAttempt / VerificationResult / ActionOutcome RED
5. 保持当前 TaskPlan/Subgoal 为唯一生产 authority
6. 不继续 ODG-9 diagnostic trace hookup
7. 不启动 ODG-10/11
8. 不运行 PR breadth，直到 S6/S7 指定节点
```

```yaml
next_slice: S0 simplified architecture freeze
production_behavior_change: false
odg_9_hookup: stopped
odg_10: stopped
odg_11: stopped
promotion: held
```

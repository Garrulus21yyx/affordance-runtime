# 优化后 Agent Loop 目标形态审查归档

日期：2026-07-31  
性质：目标架构、语义模型、实施顺序与 Definition of Done 的规范性审查归档。  
原始输入：`f1aff710-69d0-4ab3-bb4a-cc13b8ec0ade/pasted-text.txt`（1491 行）。

## 失败分布与断点

fresh 30x2 的 48 个失败中，45 个发生在动作派发前，3 个发生在已验证 effect 之后的 step credit/liveness 边界，已证明 Executor 根因数为 0。核心缺口是 `StepSpec.completion_criteria -> StateCriterion.subject: str -> compatibility target resolver -> ActionChoiceBuilder`：完成条件同时承担了“什么状态算完成”和“操作哪个目标”，导致语义不足与字符串解析扩张。

## 规范性主循环

```text
loop invariant / budget / terminal
→ PerceptionStage: UnifiedObservation
→ current-state progress reconciliation
→ PlanningStage: ground InteractionIntent, build ActionChoiceSet, select choice
→ ExecutionStage: bind contract, preflight, execute, post-observe
→ ProgressStage: independently evaluate effect, active step, task completion
→ liveness / owner handoff
→ RecoveryStage only for runtime-mechanical recovery
→ RuntimeCommitter commits transition/events
```

Coordinator 只负责编排 `PerceptionStage`、`PlanningStage`、`ExecutionStage`、`ProgressStage`、`RecoveryStage`，提交结果并根据统一 directive 路由。它不得理解 phase-specific flags。所有 stage 接收一个不可变 input，返回现有统一 `StageResult`；只有 `RuntimeCommitter` 可以修改 StateKernel、推进 version 和提交 trace event。

命名裁决：本段保留审查原称 `ExecutionStage`；在当前代码与控制计划中，它唯一对应现有 `ActionStage`。不得同时存在两个名字的类、alias、wrapper 或第六个 stage。责任裁决：RecoveryStage 仅处理 runtime-mechanical recovery，非 Runtime owner 由 AgentLoop 的唯一 owner router 分派。

## 权限边界

- Runtime admission 负责 canonical TaskSpec/TaskPlan、合法 ActionChoiceSet、安全、capability、approval 和 verification policy。
- 0 choices 返回 typed failure；1 choice 由 Runtime 自动选择；N choices 时模型只返回 `choice_id`。
- LLM 不自由生成默认路径动作，不提交 step/task completion，不豁免 verification。
- RecoveryStage 只处理 runtime-mechanical recovery；Progress、Step Planner、Task Planner、User、Terminal 使用各自 typed handoff。

## Canonical 语义

`CompletionCriterion` 与 `InteractionIntent` 必须分离。`StepSpec.interaction` 使用深度不可变的 typed union：`ElementIntent`、`CollectionIntent`、`RelationIntent`、`RegionIntent` 和 `ValueExpr`。新 PlanCandidate 必须直接产生 typed intent；旧 subject 字符串只能存在于隔离的反序列化/重放兼容边界，且默认 ActionChoice 路径不得 import 它。

Grounding 输出 typed `GroundingResult`，明确 resolved、ambiguous、absent、capability missing 等状态；ActionChoice 只能引用 GroundingResult 中的 targets、target 支持的 action 和已绑定的 required parameters。choice role 至少覆盖 direct、enabling、information。

## Verification、Progress 与 liveness

Action effect、active-step progress、task completion 是三个独立评估。task terminal false 不得清除 active-step credit。active-step criterion IDs 在执行前绑定到 attempt/contract，post-action facts 可由 ProgressStage 按已知 active step 重新匹配。

以下 liveness invariant 是 blocking：

```text
effect passed + step complete
→ commit step

effect passed + step incomplete + relevant facts changed
→ allow continued progress

effect passed + step cannot credit + relevant facts unchanged
→ PROGRESS_CREDIT_INVARIANT

same step + same relevant state + same semantic choice + same effect result
→ at most one ordinary attempt
```

Budget 只能是最后安全上限，不能作为第一个空转检测器。

## Canonical 诊断

默认 trace 只新增/保留两个规范事件：

- `PlanningTurnEvaluated`：active step、interaction intent kind、grounding 状态/candidates、choice count/roles/actions、parameter binding、selection source、failure reason、实际 model stage。
- `PostActionEvaluated`：effect/step/task 三个状态、evidence、before/after relevant facts、progress commit、liveness decision。

报告从这些事件推导 grounded target count、action choice count、selection source、root failure phase 和 terminal status，并删除失真的 PlannerContext 占位指标。60/60 episode 必须有 first owner，unclustered failure 为 0。

## 实施顺序

1. 诊断契约。
2. progress credit 与 liveness。
3. canonical InteractionIntent，一进一出替换默认 subject parser。
4. Element → Collection/Dynamic → Data/Read → Relation → Spatial typed coverage。
5. TaskPlan 与 Intent repair。
6. 五 stage 剩余纯化和默认兼容路径物理删除。

每个单元固定执行 RED unit、focused subsystem、非 BrowserGym generic integration、targeted two-seed replay、clean 6x2、pytest、Ruff、mypy、build、diff check。fresh 30x2 只在规定里程碑运行。

## 反特化与反取巧约束

- production/core 中 BrowserGym/MiniWoB task id、seed、任务标题和 benchmark import 数量必须为 0。
- 不允许按已知失败任务分支；任务名只能出现在测试矩阵和证据文档。
- 行为必须由 typed intent、observation、capability、grounding、choice 和 criterion 驱动。
- 每个修复必须有非 BrowserGym generic fixture、同构改名/重排变体或 property/invariant test；只通过列出的 seed 不构成验收。
- 新 canonical owner 必须在同一单元替换默认旧 owner；不能保留双写、fail-open fallback 或默认 compatibility conversion。
- 不允许以事件存在、token 不存在或局部 LOC 下降代替 runtime behavior、import graph、writer count 和物理删除证据。

## Definition of Done

```yaml
fresh_30x2:
  observed: 60
  provider_failures: 0
  unclustered_failures: 0
  systemic_target_unresolved_cluster: 0
  progress_credit_liveness_cycles: 0
planning:
  interaction_intent_canonical: true
  legacy_subject_parser_default_path: false
  strict_action_choice_owner: runtime
verification:
  action_effect_independent: true
  active_step_independent: true
  task_completion_independent: true
progress:
  budget_as_first_liveness_detector: false
runtime:
  top_level_stages: 5
  state_trace_committer_count: 1
  stage_to_stage_import_edges: 0
  compatibility_default_paths: 0
promotion:
  same_revision_full_tests: pass
  clean_6x2: 12/12
  fresh_30x2: pass_under_declared_policy
  official_score_claimed: false_until_authorized
```

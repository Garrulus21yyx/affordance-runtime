# World-Interaction 能力迁移最新复核

> **Lifecycle:** REVIEW SNAPSHOT
> **Semantic authority:** false
> **Reviewed branch:** `codex/migrate-world-interaction-capabilities`
> **Reviewed HEAD:** `1336d6c5ac3c2c585ad9b885d0a0e0a2d4d8ea90`
> **Review date:** 2026-08-08
>
> 本文记录对迁移分支的事实复核、差距判断与建议实施顺序。若本文与
> `docs/implementation-status.md`、当前实施计划或权威架构冲突，应以各自
> 命名责任范围内的当前权威文档为准。

## 最新复核结论

本次按最新分支重新审核：

```text
branch: codex/migrate-world-interaction-capabilities
HEAD:   1336d6c5ac3c2c585ad9b885d0a0e0a2d4d8ea90
commit: refresh architecture documentation
base:   agent/migrate-runtime-components@8d7cfd6...
```



上一次“目标架构文档没有更新”的结论已经失效。现在根 README、权威架构、演进计划、文档索引、模块责任、benchmark 边界都已经转向：

```text
Thin Semantic Intake
→ Unified World Interface
→ Runtime-owned ActionSpace
→ Semantic ActionIntent
→ current BoundActionRequest
→ execute
→ fresh observation
→ independent evaluation
→ fact-driven replanning
```

并明确停止继续扩张 RuntimeDelta、RuntimeCommitter、durable ledger、checkpoint/resume 和通用 recovery transaction。这个目标方向现在是一致的。

但是，**当前还存在一类新的文档问题：目标文档已经更新，实施状态文档却没有准确反映同一分支上已经存在的迁移代码。**

---

## 一、当前真实状态

### 1. 已经正确完成的迁移基础

这些实现可以保留：

- WoT security、rate limit、schema、state source、event description 解析；
- credential 在 transport 边界 late-bind，并从 receipt/error 中脱敏；
- observation-bound SoM marks、overlay、stale mark 拒绝；
- RoutePolicy 只排序通过 hard gates 的 candidates；
- BindingCache 只复用重新 grounding、fingerprint 一致且 current 的 verified hint；
- `StaticEnvironment`；
- smart-room、mock-web、failure fixtures；
- 一个轻量 `AgentLoop` 原型；
- 一个独立的低风险 `ActionBatch` helper。

这些迁移没有重新引入 CognitiveMap、ContinuousInteractionManager、RecoveryCascade、StateKernel 或 RuntimeCommitter 到新模块中，architecture boundary test 也在保护这一点。

### 2. 新 AgentLoop 仍然只是 scaffold

当前 `AgentLoop` 已经实现：

```text
observe
→ policy decision
→ stale check
→ execute
→ fresh observe
→ evaluate
```

并覆盖了 `SENT_UNKNOWN` 不盲重试、stale zero-call 和 fresh post-observation。

但它还没有实现目标架构的几个核心边界：

| 目标边界 | 当前实现 |
|---|---|
| Runtime-owned ActionSpace | 不存在 |
| Policy 只选 action ID | Policy 直接返回完整 `ActionContract` |
| Runtime 绑定 selector/coordinate/backend | Policy 可以直接构造这些内容 |
| Evaluator 独占 DONE | Policy 可直接返回 `DONE` |
| 语义强 TaskGoal | 当前只有 `goal_id/objective/max_steps` |
| Human confirmation | 只有状态枚举，没有执行路径 |
| WorldObservation / AgentWorldView | 仍使用旧 `Observation` |
| ActionIntent / BoundActionRequest | 仍使用旧 `ActionContract` |
| ActionResult | 仍使用旧 `ExecutionReceipt` |
| ActionBatch 集成 | 只有独立 helper，没有进入 AgentLoop |
| live DOM/Visual/WoT EnvironmentPort | 只有 StaticEnvironment |

当前 `LoopDecision` 在 `EXECUTE` 时直接携带 `ActionContract`，并允许 policy 返回 `DONE`；这与已经写入权威架构的 ActionSpace 和 evaluator-owned completion 规则不一致。

---

## 二、目前仍遗漏或矛盾的文档

### 1. Implementation Status 严重低估了当前分支代码

`docs/implementation-status.md` 仍把 reviewed baseline 写成 `8d7cfd6`，并声明：

```text
P5-A0 documentation complete
P5-A1–A4 code not started
AgentLoop default path not started
ActionBatch / BindingCache not started
```

但本分支已经实际加入 AgentLoop、EnvironmentPort、ActionBatch、RoutePolicy、BindingCache、WoT/SoM 迁移和环境资产。

正确表述应该是：

```text
P5-A0 docs: complete
P5-A1: prototype only; exit gate not met
P5-A2: not started
P5-A3: not started
P5-A4: prototype only; still legacy-type-coupled
P5-B1: EnvironmentPort scaffold only
P5-B2/B3/B4: source capability migration done; target SurfaceAdapter cutover not done
P5-C: StaticEnvironment AgentLoop scaffold only
P5-F: isolated ActionBatch prototype exists ahead of schedule
P5-G1: isolated BindingCache prototype exists ahead of schedule
```

### 2. Current Implementation Plan 同样滞后

当前计划仍写：

```text
No Runtime code slice is active
A1–A4 code not started
ActionBatch not started
BindingCache not started
```



它应该区分三种状态：

```text
NOT STARTED
PROTOTYPE EXISTS / NOT ADMITTED
CUT OVER / DEFAULT
```

否则未来 Codex 很容易重复实现第二套 AgentLoop、第二套 EnvironmentPort 或第二套 BindingCache。

### 3. Migration Plan 又走向了另一个极端：完成度高估

`.codex-migration-plan.md` 将下列项目全部标为 done：

```text
cross-surface positive E2E matrix
lightweight AgentLoop
ActionBatch and AgentEpisodeRunner
```



其中：

- AgentLoop scaffold 可以称为 done；
- ActionBatch contract/helper 可以称为 done；
- **AgentLoop ActionBatch integration 未完成**；
- **新 AgentLoop 的跨 surface 正向 E2E 未完成**。

当前 cross-surface conformance 仍然使用旧的 `StateKernel`、legacy planner、ActionContract materializer、Coordinator、Trace 和 RuntimeCommitter。它证明的是旧路径继续运行，不是新 AgentLoop 完成了 DOM/Visual/WoT 统一闭环。

### 4. Project Plan 也应更新为 prototype 状态

Project Plan 仍然把所有 P5 code phases 标为 not started。

建议改为：

```text
P5-A: docs complete; contracts prototyped incompletely
P5-B: environment and migrated surface capability foundations exist
P5-C: static short-loop prototype exists; live verticals pending
P5-F: batch helper prototype exists; target integration frozen
P5-G: binding-cache prototype exists; target integration frozen
```

### 5. Benchmark 文档缺少“何时进入外部 benchmark”的阶段门

当前 Benchmark Plan 已经正确规定了同 TaskGoal、同 policy、同 evaluator、adapter-only variation，也列出了主要指标。

但没有明确：

- 哪个内部 gate 通过后才能开始外部 benchmark；
- component benchmark 与 full-agent benchmark 的区别；
- 什么时候跑 MiniWoB/BrowserGym；
- 什么时候跑 WebArena/WorkArena；
- 什么时候跑 OSWorld；
- 哪一轮结果可以作为 default-path promotion gate。

这部分需要补充。

---

## 三、目标架构还需要一个小修订

整体权威架构现在是正确的，但 Risk/Binding 的执行顺序还需要收紧。

权威伪代码当前是：

```text
ActionIntent
→ RiskPolicy
→ confirmation
→ bind
→ execute
```



问题是，部分风险取决于 binding：

```text
本地 DOM 编辑
WoT 物理设备动作
外部 API 写入
不同账号/session
```

不能让 binding 自己授权，但必须允许 binding 提高风险。

建议采用轻量两段检查：

```text
ActionIntent
→ semantic risk floor
→ choose candidate binding
→ bound-risk consistency check
→ confirmation subject
→ user confirms semantics/risk/consequences
→ fresh observe + rebind
→ confirm risk class did not increase
→ execute
```

这仍然只是动作附近的局部检查，不是授权平台，也不需要 token registry。

---

## 四、建议重写后的实施状态

当前 branch 的准确状态建议写成：

```text
Architecture documentation reset: COMPLETE

Migrated world-interaction capabilities:
- WoT parsing/security/rate-limit: IMPLEMENTED
- SoM utilities: IMPLEMENTED
- smart-room/mock-web assets: IMPLEMENTED
- RoutePolicy: IMPLEMENTED, not default policy owner
- BindingCache: IMPLEMENTED prototype, not integrated
- StaticEnvironment: IMPLEMENTED
- AgentLoop: IMPLEMENTED scaffold, not target-complete
- ActionBatch: IMPLEMENTED helper, not AgentLoop-integrated

Target contracts:
- TaskGoal: partial prototype
- TaskPlan<Milestone>/LocalObjective: not started
- WorldObservation/AgentWorldView/ActionSpace: not started
- ActionIntent/BoundActionRequest/ActionResult: not started
- semantic human confirmation: not started

New-loop vertical proof:
- static deterministic tests: present
- live DOM: pending
- live Visual: pending
- live WoT: pending
- multi-binding route: pending
- long-horizon: pending

Default path:
- old transactional Coordinator: still default
- new AgentLoop: experimental side path
```

---

## 五、颗粒度实施计划

### Phase 0 — 事实、证据和环境修正

#### `R0.1` 同步当前事实文档

修改：

```text
docs/implementation-status.md
docs/current-implementation-plan.md
docs/project-plan.md
README.md
docs/README.md
.codex-migration-plan.md
docs/migrations/world-interaction-capabilities.md
docs/documentation-manifest.yaml
```

要求：

- baseline 改为最新分支 HEAD；
- 记录 prototype/cutover/default 三种状态；
- 不再写“所有 code 未开始”；
- 不再写“new-loop cross-surface E2E 已完成”；
- 标明 ActionBatch 和 BindingCache 是 ahead-of-sequence isolated prototypes；
- 新增架构重置 change-admission record。

**门禁：**

```text
文档中不存在相互矛盾的 phase 状态
manifest/current plan/status 三者完全一致
所有链接通过
git diff --check
```

#### `R0.2` exact-head 验证

必须在精确 HEAD 上运行：

```bash
pytest -q
ruff check src tests
mypy src
git diff --check
docker compose -f environments/smart_room/docker-compose.yml config
```

迁移记录目前是 `1066 passed`，但有一个 settings benchmark 被 deselect；不能将其描述为完整 full-suite green。

**验收：**

- 不允许 deselect；
- 若确为 baseline failure，应修复或建立明确 issue/xfail，而不是在 release gate 中隐藏；
- 写入 exact-SHA evidence；
- GitHub CI 对 exact HEAD 可见。

#### `R0.3` 迁移环境修复

修复 smart-room thermostat：

当前 `postcondition_mismatch` 阻止 `targetTemperature` 更新，但仍无条件把 `currentTemperature` 设置成请求值，造成部分状态变化。

同时处理：

- node-wot/dashboard 提交 lockfile；
- Docker 使用 `npm ci`；
- event parsing 与 subscription execution 状态分开记录；
- 没有 executor 支持时，不生成可执行 `subscribe` action；
- WoT read state source 增加 security/rate/schema metadata；
- TD 未明确选择 security scheme 时不要按字典第一项猜测。

**验收：**

```text
postcondition_mismatch 下所有相关状态保持不变
live reset/fault/state smoke 通过
WoT event parsing ≠ event execution claim
Docker build reproducible
```

---

## 六、Phase A — 目标合同落地

不要另建 `agent_v2`、`world_v2` 或第二套 EnvironmentPort。直接替换当前 scaffold。

### `A1` TaskGoal / EvaluationSpec

目标模块：

```text
task/contracts.py
task/legacy_adapter.py
```

`TaskGoal` 至少包含：

```text
instruction
constraints
allowed_effects
forbidden_effects
inputs
success_criteria
requested_outputs
risk_profile
optional material bindings
```

当前 `agent.types.TaskGoal` 只有 goal/objective/max_steps，不能继续作为正式合同。

**门禁：**

- 无 page、selector、coordinate、surface、route、Plan 字段；
- effectful task 的空 `allowed_effects` fail closed；
- 普通只读任务不要求来源图；
- strict EvaluationSpec 是可选；
- 旧 TaskSpec 只能单向投影到 TaskGoal，target code 不反向依赖 TaskSpec。

### `A2` TaskPlan / Milestone / LocalObjective

目标模块：

```text
task/planning_contracts.py
```

**验收：**

- 简单任务可以完全绕过 TaskPlanner；
- Milestone 只描述 world state；
- 不含 ActionOption、selector、surface 或 backend；
- milestone completion 只能由 evaluator 产生；
- plan 可以整体替换，不增加 mutation history。

### `A3` Unified World contracts

目标模块：

```text
world/contracts.py
world/view.py
```

实现：

```text
SurfaceObservation
SemanticTarget
ActionBinding
WorldObservation
AgentWorldView
ActionOption
ActionSpace
```

先用当前 `UnifiedObservation` 做单向 projector，不重新实现 fusion。

**门禁：**

- AgentWorldView 不暴露 selector、坐标、WoT href、API handle、credential；
- ActionSpace 绑定非空 observation ID；
- nested collections immutable；
- core contracts 不 import StateKernel、RuntimeDelta、RuntimeCommitter、benchmark 或 adapter；
- current `UnifiedObservation` 仍是唯一当前 world source，直到 projector 被删除。

### `A4` Action 与 evaluation contracts

目标模块：

```text
execution/contracts.py
evaluation/contracts.py
agent/state.py
agent/decisions.py
```

实现：

```text
ActionIntent
BoundActionRequest
ActionResult
ActionEvaluation
TaskEvaluation
Turn
AgentLoopState
AgentDecision
```

**验收：**

- `ActionIntent` 不含 binding payload；
- `BoundActionRequest` 绑定 observation ID 与 binding ID；
- `ActionResult` 不含 task completion；
- `Finish` 只是 proposal；
- Turn 保存 observation IDs，不保存两份完整 Observation；
- 新 core 不再 import `ActionContract`、`ExecutionReceipt` 或 legacy `Observation`。

---

## 七、Phase B — Unified World Interface

### `B1` SurfaceAdapter 和 WorldEnvironment

目标模块：

```text
surfaces/base.py
world/orchestrator.py
world/fusion.py
world/action_space.py
```

接口：

```text
observe
available_actions / bindings
is_current
execute
```

**门禁：**

- core 中没有 `isinstance(BrowserSession)`；
- Environment/World 层不暴露 executor registry 给 AgentLoop；
- coverage 区分 not-acquired、failed、truncated、stale、absent；
- SurfaceAdapter 不 import AgentLoop；
- WorldFusion 不执行动作；
- ActionSpaceBuilder 不调用模型。

### `B2` DOM vertical adapter

包装现有 BrowserSession/DOM adapter，不重写 DOM parser。

**正向用例：**

```text
相同 TaskGoal
→ observe DOM
→ ActionSpace
→ select semantic option
→ bind selector internally
→ execute
→ fresh observe
→ TaskEvaluator COMPLETE
```

**负向用例：**

```text
selector/fingerprint stale
→ zero executor calls
```

### `B3` Visual/SoM adapter

复用当前 SoM migration。

**验收：**

- policy 只看到 mark/semantic target；
- policy 不返回 raw coordinate；
- coordinate 只在 binding payload；
- fresh screenshot identity；
- visual action 后 independent evidence；
- stale mark zero-call。

### `B4` WoT adapter/session

复用 WotAdapter、WotExecutor 和 security/rate-limit。

**验收：**

- Thing discovery/TD parse；
- read property；
- write/invoke；
- fresh state re-read；
- credential 不进入 world view/turn/telemetry；
- effect 用环境状态确认；
- 不使用 test-only observer glue。

---

## 八、Phase C — 正式 Short AgentLoop

### `C1` Runtime-owned ActionSpace

重写当前 `AgentPolicy`：

```python
decide(
    TaskGoal,
    AgentWorldView,
    ActionSpace,
    recent_turns,
    optional_plan,
) -> AgentDecision
```

Policy 不再返回 `ActionContract`。

**验收：**

- 非 ActionSpace ID 拒绝；
- model-injected selector、coordinate、backend、endpoint 拒绝；
- 参数必须符合 option schema。

### `C2` ActionBinder / RouteSelector

```text
ActionIntent
+ current WorldObservation
+ ActionSpace
→ BoundActionRequest
```

**验收：**

- stale binding 零调用；
- 一个 effectful request 只选择一个 route；
- route 执行失败后不能在同一 turn 自动换 backend 再执行；
- 新 route 必须来自 fresh observation 的下一 turn。

### `C3` Evaluator-owned DONE

每一轮开头先运行 TaskEvaluator。

Policy `Finish` 时也重新运行 TaskEvaluator。

**验收：**

- policy 不能直接 DONE；
- initial state 已满足时零执行完成；
- receipt success 不能完成；
- plan exhaustion 不能完成；
- required artifact 缺失不能完成。

### `C4` 小型 AgentLoopState

只保留：

```text
current observation ref
bounded recent turns
optional plan
pending question/confirmation/unknown request
budget
final result
```

**验收：**

- 不含 StateKernel；
- 不含 RuntimeDelta；
- 不含完整 observation history；
- recent turns 上限 8–12；
- action 后的 fresh `after` 直接成为下一轮 observation，不再无条件重复 observe。

### `C5` TurnRecorder

**验收：**

- recorder 抛异常时 AgentLoop 行为不变；
- telemetry 不决定 admission、evaluation 或 completion；
- credential/binding payload 脱敏。

---

## 九、Phase D — 高风险确认和 UNKNOWN effect

### `D1` ExecutorSupport 与 RiskPolicy 分离

```text
ExecutorSupport：backend 能不能做
RiskPolicy：这次语义动作能不能自动做
```

RiskPolicy 只返回：

```text
ALLOW
NEEDS_CONFIRMATION
BLOCK
```

### `D2` 语义确认

确认对象包含：

```text
ActionIntent
effect
risk class
human-readable consequences
confirmation_subject_id
```

不包含：

```text
selector
coordinate
WoT href
backend handle
```

### `D3` fresh rebind

确认后：

```text
fresh observe
→ fresh bind
→ bound-risk consistency check
→ execute
```

**验收：**

- selector/coordinate 变化、语义不变：不重新确认；
- target/destination/parameter/effect/risk 变化：必须重新确认；
- stale rebind：零执行；
- 不建立 approval registry。

### `D4` SENT_UNKNOWN

**验收矩阵：**

| fresh evaluation | 行为 |
|---|---|
| EFFECT_CONFIRMED | 继续 |
| NO_EFFECT | 新 turn 决策 |
| CONFLICT | targeted reobserve |
| UNKNOWN | ask user 或 stop |
| 任意情况 | 不 replay 原 request |

---

## 十、Phase E — 长程任务

### `E1` TaskPlanner

只在：

```text
明显多阶段
连续无进展
环境重大变化
新用户信息
计划无效
```

时调用。

### `E2` MilestoneEvaluator / LocalObjective

Milestone 由事实完成，LocalObjective 无动作序列。

### `E3` bounded context

```text
最近 8–12 Turns
milestone summary
verified evidence refs
```

禁止完整 observation/event history进入模型上下文。

### `E4` ask_user

信息不足时必须询问，不猜测 material parameters。

### `E5` 内部长程验收

使用 migrated mock-web 组合一个 20–50 turn 任务：

```text
跨页面或跨 surface
中途出现新信息
至少一次 ask_user
至少一次 milestone verification
至少一次 plan replacement
一个高风险确认点
```

**验收：**

```text
约束保持率 100%
禁止副作用 0
已验证 milestone 不回退
必要询问不被猜测替代
TaskEvaluator 最终 COMPLETE
```

---

## 十一、Phase F — ActionBatch

当前 helper 保留，但不进入默认 loop，直到 C、D 完成。

重构为：

```text
ActionBatch<ActionIntent>
→ validator
→ BoundActionBatch<BoundActionRequest>
→ execute
→ one fresh observation
→ evaluate
```

**门禁：**

- 最多三个动作；
- 同 observation；
- 同 surface/session；
- low risk；
- 无外部 effect；
- 无 navigation/app/page change；
- 无跨 surface；
- 每个 option 显式 `batchable=true`；
- 前置动作 `observation_barrier=false`；
- 任一失败或 `SENT_UNKNOWN` 立即停止；
- batch 后 fresh observation。

当前 helper 只执行 contracts 并返回 receipts，还没有进入 AgentLoop 或 evaluator，因此不能直接 promotion。

---

## 十二、Phase G — BindingCache / Skill

当前 BindingCache 可保留，但最终应从旧 `RouteOutcome` 迁到新 `ActionEvaluation`。

**门禁：**

- 只记忆 independently verified success；
- recall 必须在当前 observation 重新 grounding；
- fingerprint/currentness 不一致则 miss；
- cache 不保存 executable request；
- Skill 不绕过 ActionSpace、RiskPolicy、fresh observation 或 evaluator；
- 只允许 offline replay 后发布。

---

## 十三、Phase H — breadth、default cutover、旧 core 删除

顺序：

```text
H1 AX/SVG
H2 API/Device/CLI
H3 internal full matrix
H4 new path shadow/default candidate
H5 external benchmark candidate campaign
H6 default composition cutover
H7 old Coordinator edge-isolation
H8 delete StateKernel/RuntimeDelta/RuntimeCommitter/recovery transaction
H9 delete legacy projectors/tests/docs
```

默认切换前必须证明：

```text
同一 TaskGoal
同一 AgentPolicy
同一 semantic vocabulary
同一 ActionEvaluator/TaskEvaluator
只改变 SurfaceAdapter
DOM/AX/Visual/SVG/WoT 全部 COMPLETE
```

---

## 十四、防止 God file 的强制门禁

当前新文件本身都不大，尚未出现新的 god file。风险主要在未来把所有逻辑继续塞入：

```text
agent/types.py
agent/loop.py
environment_port.py
conformance.py
browser_session.py
executors.py
```

### 1. 新 core 文件尺寸门

这些是 review/merge 门，不是产品语义：

```text
新 core module：
    350 行触发强制拆分审查
    500 行禁止合并，除非有书面责任证明

单个函数：
    80 行触发拆分
    120 行禁止合并

一个 class：
    超过 10 个 public methods
    或超过 8 个注入 collaborator
    必须做 owner review
```

### 2. 按责任拆包，不是一类一文件

推荐：

```text
task/contracts.py
task/planning.py

world/contracts.py
world/fusion.py
world/action_space.py
world/orchestrator.py

execution/contracts.py
execution/binder.py
execution/batch.py

evaluation/contracts.py
evaluation/action.py
evaluation/task.py

agent/decisions.py
agent/state.py
agent/loop.py
agent/policy.py

risk/policy.py
risk/confirmation.py
```

不要把所有 dataclass 放回 `agent/types.py`。

### 3. 永久 import redlines

添加 AST/import tests：

```text
agent/ 不得 import adapters、BrowserSession、StateKernel、RuntimeCommitter
AgentPolicy 不得 import GroundingPayload 或 executor
SurfaceAdapter 不得 import AgentLoop
ActionEvaluator 不得 import executor implementation
TaskEvaluator 不得 import dispatch/binder
TurnRecorder 不得被 AgentLoop 用于行为判断
new target core 不得 import ActionContract/ExecutionReceipt after A4
```

### 4. 冻结旧热点

迁移期间禁止向下列文件增加新产品能力：

```text
runtime_committer.py
state_kernel.py
execution_phase.py
progress_phase.py
recovery_phase.py
stage_protocol.py
conformance.py
browser_session.py
executors.py
```

只允许：

- baseline bug fix；
- 一次性 adapter extraction；
- 删除。

新 AgentLoop benchmark 不得继续加进旧 `conformance.py`。

### 5. 每个 PR 必须回答

```text
这个模块唯一的变化原因是什么？
它拥有哪一行 responsibility map？
它禁止拥有什么？
它替代谁？
旧 owner 何时删除？
```

回答不清楚则不准合并。

---

## 十五、外部 benchmark 应该什么时候开始

不是等所有代码完成后才第一次跑，也不是现在立即让外部 benchmark 驱动架构。

### 阶段 1：组件级外部 benchmark

**时间：B3 Visual adapter 完成后。**

可以跑视觉 grounding/component benchmark，验证：

```text
截图 → semantic target/mark
无 raw coordinate policy output
current screenshot binding
```

这只是 adapter evidence，不是 E2E generalization claim。

### 阶段 2：第一次完整外部 Agent benchmark

**时间：C1–C5 和 D1–D4 完成，并通过内部 DOM/Visual/WoT 正向矩阵之后。**

优先复用仓库已有的 BrowserGym/MiniWoB harness，选择固定的小型任务集：

```text
click
type/fill
select
dialog
form
short sequence
```

这一阶段目标不是追求很高分，而是证明：

```text
新 AgentLoop 能正常收集结果
无 benchmark-specific production branch
fresh observation / evaluator / no-retry 都工作
```

**进入条件：**

```text
内部 deterministic matrix 100% 通过
stale zero-call 100%
forbidden side effect 0
unknown duplicate 0
所有 report denominator 完整
```

### 阶段 3：长程外部 benchmark

**时间：E5 内部 20–50 turn 长程任务通过后。**

再进入 WebArena/WorkArena 类长程网页任务。

重点测：

```text
约束保持
新信息记忆
ask_user
milestone verification
fact-driven replan
跨页面稳定性
```

不要在 LocalObjective、bounded turns 和 evaluator 尚未完成时提前跑这类 benchmark，否则失败无法定位。

### 阶段 4：桌面/跨应用 benchmark

**时间：AX、Visual、CLI 和应用切换接口完成后。**

此时才适合运行 OSWorld 类 desktop benchmark。

否则结果只会测出“adapter 尚未实现”，不能评价 AgentLoop 架构。

### 阶段 5：default cutover 前的完整外部 campaign

**时间：H3 内部完整矩阵通过、新 path 已成为 default candidate，但尚未删除旧 core 时。**

运行：

```text
旧 path frozen baseline
新 path candidate
相同模型、task manifest、seed、budget
```

Promotion gate：

- 新 path 成功率不得显著低于 baseline；
- 如果成功率接近，应在观察数、模型调用或延迟上有明确收益；
- 所有本地 correctness invariants 仍为零违规；
- 无 benchmark metadata 泄漏到产品决策；
- exact SHA、clean tree、完整 denominator。

### 阶段 6：default cutover 后 release benchmark

默认切换完成后，在最终 exact SHA 上重新运行完整固定套件。

只有这一轮可以支持：

```text
default-path cross-surface/generalization claim
```

Prompt-injection 或专门安全 benchmark 可以作为后续独立 release evidence，但不应重新成为 GUI core 架构门禁。

---

## 十六、建议接下来实际执行的三个 PR

### PR 1 — Truth reconciliation and migration cleanup

只做：

- 状态文档同步；
- exact-head evidence；
- smart-room mismatch 修复；
- WoT event/security metadata 修正；
- lockfiles；
- migration record 降级为准确状态。

不改 AgentLoop 语义。

### PR 2 — Target contracts

只做 A1–A4：

- TaskGoal；
- World contracts；
- ActionSpace；
- ActionIntent/BoundActionRequest/ActionResult；
- Evaluations/Turn/State；
- legacy one-way projectors；
- import redlines。

不接 live browser。

### PR 3 — One DOM vertical slice

只做：

```text
DOM observe
→ WorldObservation
→ ActionSpace
→ policy selects option
→ bind
→ execute
→ fresh observe
→ evaluator COMPLETE
```

这个 PR 通过后，再复制相同架构到 Visual 和 WoT。

---

## 最终裁定

```text
目标架构文档：现在基本正确
权威链：已经完成切换
当前代码事实文档：仍未同步
迁移能力基础：可保留
新 AgentLoop：scaffold，不是正式 core
ActionBatch：helper prototype，不是集成能力
新-loop cross-surface E2E：尚未完成
default cutover：尚未开始
外部 benchmark：应在内部 DOM/Visual/WoT 矩阵后分阶段启动
```

目前最优先的不是继续写更多 AgentLoop 功能，而是先关闭：

```text
文档事实不一致
+
prototype 与正式 slice 状态混淆
+
exact-head evidence 缺失
```

随后严格按：

```text
contracts
→ one DOM vertical loop
→ Visual
→ WoT
→ confirmation/evaluation
→ internal matrix
→ first external benchmark
```

推进。

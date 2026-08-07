# Affordance Runtime 架构修改意见逐条审计与页面对照

> 事实基线：`agent/migrate-runtime-components @ 786857f8fb61aa99f2c7e6a23eb8225957e1438b`
>
> 本文区分当前事实与目标建议。**建议目标不是当前实现**；意见要求保留的安全边界也不是“需要扁平化的冗余”。

## 1. 文档目的与阅读规则

这份文档把所收到的修改意见逐点落到三个可核验位置：固定提交中的代码事实、现有 GitHub Pages 的具体章节、意见建议的目标架构。它不是 Runtime 已完成改造的声明，也不以新的总结替代原意见。

状态词只使用以下含义：

- `CURRENT`：固定基线中可由代码证明的当前事实。
- `KEEP`：意见明确要求保留的当前权威或安全边界。
- `GAP`：意见指出的当前缺口、有损往返或职责混杂。
- `PROPOSED`：意见建议的目标结构，当前尚未实现。
- `DEFERRED`：意见明确列入 P3、应晚于语义与完成权威收口的能力。

核验口径：代码链接全部固定到上述 SHA；“风险”表示可能发生，不等于仓库已有失败案例；“建议”不等于代码已经存在；拒绝、澄清、UNKNOWN、权限缩减属于防止静默误解的显式结果，不自动算作缺陷。

## 2. 总体结论：该扁平化什么，必须保留什么

修改意见的中心不是“删除阶段”，而是减少同一语义在多套对象之间的重复表达和有损往返。它要求收缩的是数据表示和重叠所有者，同时保留模型提案、Runtime 准入、执行合同、独立验证和权威状态提交之间的边界。

### 2.1 五条不得删除的权威边界

| ID | 必须保留的边界 | 防止的越权或错误 | 当前/目标关系 |
|---|---|---|---|
| `KEEP-01` | 不可信 `IntentProposal` → Runtime 接受的 `TaskSpec` | 模型拥有任务语义权威 | 当前已有 draft/validator/compiler 分离；意见建议收口为 `TaskSpecAuthority`，边界本身保留 |
| `KEEP-02` | 不可信 `PlanCandidate` → Runtime 接受的 `TaskPlan` | 模型拥有计划 ID、版本和安装权 | 当前 `TaskPlanAuthorityBinder` 保留；目标删除的是 legacy 往返，不是 admission |
| `KEEP-03` | Planner `ActionProposal` → Runtime `ActionContract` | 模型直接执行、绕过能力/审批/快照绑定 | 当前边界正确，意见明确不删除 |
| `KEEP-04` | `ExecutionReceipt` → 独立 `VerificationResult` | 执行器用 success 自证任务成功 | 当前 fresh post-action observation + verifier ladder 应保留 |
| `KEEP-05` | `VerificationResult` → Runtime `TaskProgress` | 模型或 verifier 自行写进度、宣布完成 | 当前单写者与证据绑定应保留；完整 task closure 仍需增强 |

### 2.2 五组应收缩的重复表示

| ID | 当前重复链 | 意见判断 | 目标方向 |
|---|---|---|---|
| `FLAT-01` | LLM graph + Runtime graph + raw-text regex parser | 同一自然语言被多次理解，结果可能互相覆盖 | 一次 `IntentProposal`，Runtime 只做准入和 ID/策略权威化 |
| `FLAT-02` | obligation → `StepSpec` → legacy `SubgoalSpec` → `StepSpec` | 明确的有损 round-trip | `TaskPlan<StepSpec> + TaskProgress` 直接成为生产权威 |
| `FLAT-03` | `BrowserSnapshot` → bounded planner observation → `UnifiedObservation` → `ActionChoice` | 模型 token 裁剪同时缩小 Runtime 候选空间 | canonical full observation 供 Runtime；bounded view 只供模型 |
| `FLAT-04` | `PlanningRequest` → `PlannerContext` → provider JSON + 重复 blobs | 再建一套 task/step/progress 领域视图 | 一个 immutable typed request + pure provider serializer |
| `FLAT-05` | terminal-readiness compatibility + progress completion + latest-report completion | 两套窄机制都不是完整 TaskSpec closure | 一个以 TaskSpec completion expression 为准的完成权威 |

> 总原则：扁平化数据表示和权威所有者，不把验证、安全、执行阶段合并成一个大类。

## 3. 逐条链路审计

### `OP-00` 外部请求进入 Runtime

- **意见原意：**入口链 `TaskRequest / UserRequest → optional TaskSpec → RunRequest → TaskRuntimeService / TaskRunner → RunCoordinator` 整体正确，不需要扁平化；自然语言入口和预编译语义入口都应经过统一权威校验。
- **条目性质：**`KEEP`，附带 `PROPOSED` 的 `TaskSpecAuthority` 收口建议。
- **当前实现：**`RunRequest` 绑定任务 ID、goal、target、constraints、capabilities 和可选 `TaskSpec`；外层 goal/identity 不能悄悄覆盖已编译任务。任务级工具面不向父 Agent 暴露 click/type/coordinate 原语。
- **源码证据：**[`runtime.py`][runtime] 的 `RunRequest`/Coordinator；[`integrations/task_api.py`][task-api] 的任务生命周期服务；[`integrations/external_protocol.py`][external-protocol] 的任务级协议。
- **当前线上位置：**[01-B：TaskSpec / 外层参数 → RunRequest](https://garrulus21yyx.github.io/affordance-runtime/entrypoints.html#01-b-run-request)；[01-C：任务级工具调用](https://garrulus21yyx.github.io/affordance-runtime/entrypoints.html#01-c-task-tools)。
- **当前页面表述：**页面已说明参数冲突拒绝、能力只缩小、父 Agent 不获得 primitive GUI 权力。
- **对比：**意见没有要求删除入口适配层；它补充的是即使 caller 提供 TaskSpec，也应将其视为 untrusted proposal，统一经过 schema/source/capability/revision/deep-freeze admission。
- **建议架构：**自然语言走 `UserRequest → IntentInterpreter`；预编译语义走 `Untrusted TaskSpecProposal → TaskSpecAuthority`，二者最终进入同一 TaskSpec authority。
- **状态：**入口隔离为 `CURRENT` + `KEEP`；统一命名的 `TaskSpecAuthority` 为 `PROPOSED`。
- **防误读：**外层冲突语义被拒绝是故意的权限收缩，不应为了“无损”而恢复。

### `OP-01` SourceLedger 与 clause split 的边界

- **意见原意：**保留 `SourceLedgerBuilder`，但只把它当 citation/provenance/coverage audit input；标点、换行、`then` 等句法切分不是语义原子划分，不能自动等价为 obligation、Step 或 completion criterion。
- **条目性质：**`KEEP` + `GAP`。
- **当前实现：**Ledger 保存 whole-request unit、clause units 和 conversation/attachment/target/profile refs；whole request 的存在能保留原文追溯，但 deterministic coverage 只能证明 source ref 覆盖，不能证明模型正确理解了每个条件。
- **源码证据：**[`source_ledger.py`][source-ledger] 的 `SourceLedgerBuilder`、unit/span/hash 构造；[`task_intake.py`][task-intake] 的 source provenance 与 compilation。
- **当前线上位置：**[02-A：UserRequest → SourceLedger](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-a-source-ledger)。
- **当前页面表述：**已写明 clause 切分可能弱化跨句语用关系，并保留 whole-request 与 span。
- **对比：**页面目前主要描述“切分与保留”；意见进一步指出 whole-request claim 覆盖全部 clauses 不是“每个条件均被理解”的证明。
- **建议架构：**增加不可信 `SourceUnitDisposition(role, mapped_requirement_keys, reason)`；Runtime 只验证 required units 均有 disposition、source/span 真存在，复杂或高风险任务再做独立 semantic audit。
- **状态：**Ledger 边界为 `CURRENT` + `KEEP`；disposition 与风险触发 semantic audit 为 `PROPOSED`。
- **防误读：**Clause unit 不是错误数据；错误是把句法 unit 升格为语义权威。

### `OP-02` 自然语言只解释一次的 IntentProposal

- **意见原意：**当前模型同时输出 objective、effects、criteria、evidence、claims、obligations、dependencies、terminal 等多张图；随后 Runtime 又用 raw-text regex normalizers 解释 click/focus/drag/select/type/submit，最后 coverage LLM 再判断完整性。这是最应扁平化的位置。
- **条目性质：**`GAP` + `PROPOSED`。
- **当前实现：**`IntentDraft` 同时包含 requested effects、success criteria、semantic constraints、source claims、obligations 等；intake 流程存在 `_normalize_explicit_action_draft()`、`_normalize_explicit_focus_draft()`、`_normalize_explicit_relation_draft()`、`_normalize_explicit_spatial_point_draft()`、`_normalize_value_entry_draft()` 与 `_restore_explicit_submit_effect()`。
- **源码证据：**[`task_intake.py`][task-intake] 的 `IntentDraft`/`TaskSpec`；[`intent_compiler.py`][llm-intent] 的结构输出和 raw-text normalizers；[`task_obligation_coverage.py`][intent-coverage] 的 coverage review。
- **当前线上位置：**[02-B：SourceLedger → LLMIntentDraft / IntentDraft](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-b-intent-draft)；[02-C：canonical obligations](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-c-canonical-obligations)。
- **当前页面表述：**现页说明 draft 不可执行、canonical compiler 重建权威 ID，但此前没有把 raw-text 二次解释完整画出。
- **对比：**当前是“模型解释 + regex 再解释 + coverage reviewer”；建议是模型只给最小 semantic proposal，Runtime 不再从 raw text 发明或补回效果。
- **建议架构：**`UserRequest + SourceLedger → IntentInterpreter LLM → IntentProposal(requirements, constraints, preferences, outputs, dependencies, ambiguities, source dispositions) → TaskSpecAuthority.admit()`。
- **状态：**多层解释为 `CURRENT` + `GAP`；最小 `IntentProposal` 为 `PROPOSED`。
- **防误读：**意见不反对 Runtime 重新分配 ID、验证来源或拒绝非法 proposal；它反对 Runtime 用 regex 再理解用户语义。

### `OP-03` 可组合 SemanticExpr，而不是封闭 scalar

- **意见原意：**`StateCriterion.expected_value: FrozenScalar` 与只含 `LITERAL/SOURCE_VALUE` 的 `ValueExpr` 无法无损表达 prefix、suffix、range、comparison、all_of、any_of、not 和开放语义；专用枚举或错误压成 equals 都损害 zero-shot。
- **条目性质：**`GAP` + `PROPOSED`。
- **当前实现：**`SemanticValueRelation` 已定义 `EXACT/PREFIX/SUFFIX`，但 `CanonicalObligationCompiler.compile_requested_effects()` 仅把 `EXACT` 收入 `exact_values_by_target`；simplified criteria 的值表达仍是有限闭集。
- **源码证据：**[`task_intake.py`][task-intake] 的 `SemanticValueRelation`；[`canonical_obligation_compiler.py`][canonical-compiler] 的 `compile_requested_effects()`；[`simplified_runtime_contracts.py`][simplified-contracts] 的 `ValueExpr`、`StateCriterion` 和 composite types。
- **当前线上位置：**[02-C：Requested effects → canonical obligations](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-c-canonical-obligations)；[03-A：obligations → StepSpec](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-a-plan-candidate)。
- **当前页面表述：**页面已提示自由关系收敛到 typed relation 会降维，但未具体指出 PREFIX/SUFFIX 在 canonical effect path 被跳过。
- **对比：**当前 schema 能保存部分关系名，却不能保证它们进入 canonical obligation、grounding 和 verification 全链；建议通过组合 AST 让相同语义对象贯穿各层。
- **建议架构：**`LiteralExpr | ReferenceExpr | PredicateExpr | AllOfExpr | AnyOfExpr | NotExpr | OpenSemanticExpr`；registered operator 走 deterministic resolver/verifier，未注册但明确的语义保留为 open，真实歧义才澄清。
- **状态：**有限 schema 与 EXACT-only canonical collection 为 `CURRENT` + `GAP`；组合 AST 为 `PROPOSED`。
- **防误读：**`OpenSemanticExpr` 不是让模型任意执行，而是防止为了迎合封闭 schema 而静默改写用户原意。

### `OP-04` IntentProposal → TaskSpec 的统一准入权威

- **意见原意：**Intent 到 TaskSpec 的权威边界必须保留，但分散在 `LLMIntentDraft`、`IntentDraftValidator`、`CanonicalObligationCompiler`、deterministic coverage 和 model coverage 的职责应收口到 `TaskSpecAuthority.admit()`。
- **条目性质：**`KEEP` + `PROPOSED`。
- **当前实现：**draft、validator、canonical compiler 和 coverage 是分离协作者；Runtime 会重建 canonical IDs、检查 source refs、依赖、policy/capability，并深冻结 TaskSpec。
- **源码证据：**[`task_intake.py`][task-intake] 的 `IntentDraftValidator.compile()`/`TaskSpec`；[`canonical_obligation_compiler.py`][canonical-compiler]；[`task_obligation_coverage.py`][intent-coverage]。
- **当前线上位置：**[02-D：IntentDraft + coverage → TaskSpec admission](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-d-task-spec-admission)。
- **当前页面表述：**现页将 validator 与 canonical compiler 分别描述，模型 reviewer 只有 veto 权。
- **对比：**意见保留所有 validation 内容，但要求一个清晰的 admission owner；repairable 错误最多一次 bounded repair，ambiguous 询问用户，unsupported 返回 typed failure。
- **建议架构：**`TaskSpecAuthority.admit(source_ledger, proposal)` 负责 schema、lineage、disposition coverage、ID、dependencies、risk/capability、evidence policy、open semantic preservation 与 identity/deep freeze。
- **状态：**准入边界为 `CURRENT` + `KEEP`；统一 authority façade 为 `PROPOSED`。
- **防误读：**Authority 不能通过 raw-text regex 补 submit、重解 prefix/suffix 或发明新的用户效果。

### `OP-05` TaskSpec 压缩为 Requirement Authority

- **意见原意：**当前 `requested_effects`、`success_criteria`、`source_claims`、`obligations`、`semantic_value_constraints`、`evidence_requirements` 高度重叠；应由一份 requirement 同时表达用户要求、目标状态、来源、依赖和验证策略。
- **条目性质：**`GAP` + `PROPOSED`。
- **当前实现：**`TaskSpec` 同时保存 objective、targets、effects、entities、preferences、outputs、criteria、constraints、semantic constraints、claims、obligations、forbidden effects、evidence requirements 和 capabilities。
- **源码证据：**[`task_intake.py`][task-intake] 的 `TaskSpec`、`SourcedTaskClaim`、`TaskObligationSpec` 和 `EvidenceRequirement`。
- **当前线上位置：**[02-D：TaskSpec admission](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-d-task-spec-admission)；[02 损失账本](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-loss-ledger)。
- **当前页面表述：**现页强调 TaskSpec 不可变和有来源，但未完整展示同一事实跨六类字段重复表达的内部一致性负担。
- **对比：**当前并行图能提供兼容性和显式证据字段，却可能不一致；建议用 `TaskRequirement` + composite completion 作为唯一语义 authority，SourceLedger 继续承担来源账本。
- **建议架构：**`TaskSpec(ref, source_ledger_ref, objective, requirements, constraints, preferences, desired_outputs, completion, risk_policy)`；requirement 含 interaction hint、desired criterion、dependencies、source refs、runtime evidence policy 和 interpretation status。
- **状态：**多字段并存为 `CURRENT`；单一 requirement authority 为 `PROPOSED`。
- **防误读：**意见不是要求丢弃 provenance/evidence，而是把它们并入同一 requirement，而非维护平行事实图。

### `OP-06` Task Planner 不应机械执行一 obligation 一 Step

- **意见原意：**当前 rule generator 的主要分解是每个 obligation 创建一个 `StepSpec`，不等于真正按里程碑分解；Task Planner 应按独立可验证里程碑、依赖、环境、审批、风险、artifact handoff 和必须重观察的阶段拆分。
- **条目性质：**`GAP` + `PROPOSED`。
- **当前实现：**`RulePlanCandidateGenerator` 遍历 `task_spec.obligations` 生成 steps；因此“填三个字段并提交”可能形成四个步骤，虽然它们可能属于一个表单工作单元。
- **源码证据：**[`task_plan_generators.py`][plan-generators] 的 `RulePlanCandidateGenerator.generate()`；[`simplified_runtime_contracts.py`][simplified-contracts] 的 `StepSpec`。
- **当前线上位置：**[03-A：TaskSpec obligations → PlanCandidate / StepSpec](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-a-plan-candidate)。
- **当前页面表述：**现页已经写出 obligation-to-step 转换和自由叙述降维，但没有把它定性为“机械映射而非宏观任务分解”。
- **对比：**当前 obligation 粒度直接决定 plan 粒度；建议低频 Task Planner 负责宏观里程碑，高频 Step Planner 只依据 active Step + current observation 选下一动作。
- **建议架构：**简单任务走 deterministic single-step plan；复杂任务走 Task Planner LLM；两者都输出 `PlanCandidate<StepSpec>` 并由 authority 接受，Step Planner 不重读 raw text。
- **状态：**one-obligation-one-step 为 `CURRENT` + `GAP`；两层 Planner 边界为 `PROPOSED`。
- **防误读：**两层 Planner 不是把每个动作写进 TaskPlan；动作仍由每轮 Step Planner 产生。

### `OP-07` StepSpec → SubgoalSpec → StepSpec 的有损往返

- **意见原意：**这是当前最严重的计划语义往返之一：typed `StepSpec` 被 authority binder 降级为 legacy `SubgoalSpec`，随后 PlanningRequest 又投影回 `TaskPlanView<StepSpec>`。
- **条目性质：**`CURRENT` + `GAP`，列为 P0。
- **当前实现：**`_subgoal_from_step()` 固定读取 `step.completion_criteria[0]`；若为 `StateCriterion`，expected value 转为字符串。`project_state_legacy_task_plan_to_step_view()` 再根据 legacy plan/progress 构建 simplified view。
- **源码证据：**[`task_plan_contracts.py`][plan-contracts] 的 `TaskPlanAuthorityBinder`/`_subgoal_from_step()`；[`simplified_step_projection.py`][step-projection] 的 legacy-to-simplified projection。
- **当前线上位置：**[03-B：PlanCandidate → 权威 TaskPlan](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-b-plan-authority)；[03-C：StateKernel + Snapshot → PlanningRequest](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-c-planning-request)。
- **当前页面表述：**此前把 PlanCandidate 绑定到 TaskPlan 写得过于平滑，没有显式展示 legacy round-trip。
- **对比：**可能丢失第二个及以后 criteria、Composite/Artifact/API criterion、非字符串值、复杂 expression 和完整 evidence policy；目标路径直接保存 typed steps。
- **建议架构：**`PlanCandidate<StepSpec> → TaskPlanAuthority → TaskPlan<StepSpec> + TaskProgress`，默认生产链删除 `SubgoalSpec` authority、legacy projection、compatibility objective/action-family reconstruction。
- **状态：**round-trip 为 `CURRENT` + `GAP`；直接 typed plan 为 `PROPOSED`。
- **防误读：**意见要求删除的是默认生产权威中的兼容往返，不是否定 TaskPlan admission/version authority。

### `OP-08` Task completion 必须支持复合终态

- **意见原意：**`project_task_completion_criterion()` 对 0 个 terminal obligation 返回 pending、1 个 projected、多个 unsupported；真实任务可能需要多个终态同时成立，不能要求唯一 terminal obligation。
- **条目性质：**`CURRENT` + `GAP` + `PROPOSED`。
- **当前实现：**projection 明确拒绝多个 terminal obligations；当前 TaskSpec 没有一个能直接表示完整任务 closure 的顶层 composite completion authority。
- **源码证据：**[`simplified_step_projection.py`][step-projection] 的 `project_task_completion_criterion()`；[`simplified_runtime_contracts.py`][simplified-contracts] 的 criterion types。
- **当前线上位置：**[06-D：task completion](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion)；[06 损失账本](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-loss-ledger)。
- **当前页面表述：**页面此前用“全部先决义务”描述 terminal readiness，强于通用 projection 的实际表达能力。
- **对比：**当前把 terminal target 与 plan prerequisites 作为窄兼容框架；建议 TaskSpec 直接拥有 `AllOfCriterion` 等 completion expression，最后一步不承担整个任务唯一终态。
- **建议架构：**文件保存、邮件发送、日历创建等 criteria 作为 `AllOfCriterion(children=...)`，最终由唯一 TaskCompletionVerifier 逐项求值。
- **状态：**单 terminal projection 限制为 `CURRENT` + `GAP`；复合 task completion 为 `PROPOSED`。
- **防误读：**多个 terminal unsupported 是显式失败而非静默成功；缺陷在表达能力，不在它拒绝猜测。

### `OP-09` Perception 的当前顺序与建议顺序

- **意见原意：**网站原概念链 `BrowserSnapshot → UnifiedObservation → bounded PlanningRequest` 是正确目标，但当前源码实际先构造 bounded `PlannerObservationView`，再由它产生 `UnifiedObservation`，Runtime 的 `ActionChoiceBuilder` 因而也受模型裁剪影响。
- **条目性质：**`CURRENT` + `GAP` + `PROPOSED`。
- **当前实现：**`UnifiedObservation.from_planner_observation()` 明确接收 `PlannerObservationView`；后者已经限制 visible text、affordances、state fields 和 artifact refs。
- **源码证据：**[`planning_request.py`][planning-request] 的 `PlannerObservationView`；[`planning_request_builder.py`][planning-request-builder] 的 bounded projection；[`unified_observation.py`][unified-observation] 的 `from_planner_observation()`。
- **当前线上位置：**[05-A：多源信号 → BrowserSnapshot](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-a-browser-snapshot)；[05-B：BrowserSnapshot → UnifiedObservation](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-b-unified-observation)；[08-A：权威状态与观测 → PlanningRequest](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-a-planning-request)。
- **当前页面表述：**此前 05-B 画成 snapshot 直接生成 unified observation，属于目标式简化，不足以反映生产路径的先裁剪后统一。
- **对比：**当前模型 prompt space 和 Runtime candidate space 共享同一个已裁剪输入；建议先形成 full canonical observation，再分叉为 Runtime full view 与 model bounded view。
- **建议架构：**`DOM/Accessibility/Visual → perception fusion → canonical UnifiedObservation`；Runtime grounder/choice builder 读取完整当前视图，模型只读取 `PlanningObservationView`。
- **状态：**bounded-first 为 `CURRENT` + `GAP`；canonical-first 分叉为 `PROPOSED`。
- **防误读：**“完整”指 Runtime 当前可用的 canonical target view，不等于无界保留整个 DOM 或把全部页面文本塞进模型。

### `OP-10` 多来源冲突在 Planner 投影中的丢失

- **意见原意：**BrowserSnapshot/unified affordance 可保留多个 grounding candidates，但 Planner inventory 选 representative source，`_affordance_view()` 还把 `conflict_codes=()`；因此“保留来源与冲突”没有完整延续到 Step Planner 输入。
- **条目性质：**`CURRENT` + `GAP`。
- **当前实现：**`_planner_affordance_inventory()` 从 unified target 的 candidates 选首个存在的 representative，并合并 source count/actions/confidence；`_affordance_view()` 把 conflict codes 设为空 tuple。
- **源码证据：**[`planning_request_builder.py`][planning-request-builder] 的 `_planner_affordance_inventory()`、`_affordance_view()`；[`perception.py`][observation] 的 BrowserSnapshot/unified target types。
- **当前线上位置：**[05-A：BrowserSnapshot](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-a-browser-snapshot)；[05-B：UnifiedObservation](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-b-unified-observation)；[05 损失账本](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-loss-ledger)。
- **当前页面表述：**页面强调 snapshot 层保留冲突，但没有区分这些冲突在 planner projection 中是否仍可见。
- **对比：**当前 canonical capture 层的多源信息在 bounded planner view 被代表源/空 conflict list 降维；建议 canonical target 保留 all surfaces/bindings/conflicts/freshness/confidence/actions，model view 只摘要但不静默抹掉 material conflict。
- **建议架构：**模型可以看 `source_count`、`conflict_status`、strongest evidence、available actions；Runtime 保留可追溯的完整 bindings。
- **状态：**代表源与空冲突为 `CURRENT` + `GAP`；冲突摘要协议为 `PROPOSED`。
- **防误读：**选择 representative 不一定产生错误；风险是 material conflict 被表示成“无冲突”。

### `OP-11` PlanningRequest → PlannerContext 的重复投影

- **意见原意：**`PlanningRequest` 已含 task、step、observation、outcomes、recovery、budget、actions、admission，却又携带 summary/compatibility blobs，再被 `PlannerContextBuilder` 转成第二套 dict 领域模型。
- **条目性质：**`CURRENT` + `GAP` + `PROPOSED`。
- **当前实现：**PlanningRequest 含 typed views 和兼容字段；serializer/context builder 再生成 task spec dict、active subgoal、affordance summaries、recent proposals/effects/recovery summary。
- **源码证据：**[`planning_request.py`][planning-request]；[`planning_request_builder.py`][planning-request-builder]；[`planner_context.py`][planner-context]；[`planning_request_serializer.py`][planning-serializer]。
- **当前线上位置：**[08-A：权威状态与观测 → PlanningRequest](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-a-planning-request)；[08-B：PlanningRequest → PlannerContext/messages](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-b-planner-context)。
- **当前页面表述：**现页已承认第二次序列化/裁剪，但没有明确把 `PlannerContext` 定性为可收缩的重复领域对象。
- **对比：**当前 serializer 之前还有一个领域转换；建议 `StateKernel → immutable PlanningRequest → pure provider serializer → messages`，serializer 只排序、截断和适配 provider，不重建任务/步骤/进度权威。
- **建议架构：**删除默认生产链的第二领域对象 `PlannerContext`，把 provider-specific presentation 限定在纯序列化层。
- **状态：**双领域投影为 `CURRENT` + `GAP`；typed request + pure serializer 为 `PROPOSED`。
- **防误读：**建议删除的是领域重复，不是禁止任何 JSON serialization 或 presentation truncation。

### `OP-12` Strict Planner 与历史兼容代码物理分离

- **意见原意：**`GeneralistLMPlanner` 同时承担 strict choice selector、historical free proposal、compatibility semantic compilers、schema repair、compaction、semantic rewrites 和 legacy path，默认 strict planner 不应继续扩大。
- **条目性质：**`GAP` + `PROPOSED`。
- **当前实现：**同一类暴露 strict selection 与 legacy proposal/repair/compaction 等方法，测试和 profile 决定不同路径。
- **源码证据：**[`generalist_planner.py`][generalist-planner] 的 `GeneralistLMPlanner.select()`、legacy propose 和 `compact_planner_context()`；[`planner_context_recovery.py`][context-recovery] 的 compaction owner port。
- **当前线上位置：**[03-D：PlanningRequest → ActionChoice → PlannerProposal](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-d-action-choice)；[08-C：PlannerContext compaction](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-c-context-compaction)。
- **当前页面表述：**页面分别描述 choice selection 与 context compaction，尚未把它们同属一个大类的职责聚合问题并列展示。
- **对比：**意见不要求删除历史能力，而是物理拆成 `StrictStepChoicePlanner` 与 `HistoricalCompatibilityPlanner`，用独立 profile/tests 隔离。
- **建议架构：**默认 strict planner 只保留 `select(ChoicePlanningRequest) -> ActionSelection`；legacy 自由 proposal、semantic rewrite 和 compatibility repair 不进入主类扩展面。
- **状态：**职责聚合为 `CURRENT` + `GAP`；物理拆分为 `PROPOSED`。
- **防误读：**拆分类不等于让 strict planner 拥有更多自由生成权，目标恰恰是缩小其接口。

### `OP-13` N-choice 选择需要足够语义上下文

- **意见原意：**当前 choice 主要提供 ID、action kind、target ID、destination、parameters、criterion IDs；缺 active-step 目标状态、target label/current state、choice reason 和最近失败时，模型难以在多个合法 choice 中做语义选择。
- **条目性质：**`GAP` + `PROPOSED`。
- **当前实现：**`ChoicePlanningRequest`/choice serialization 主要强调 membership 和 identity，严格限制模型只能返回已有 choice ID。
- **源码证据：**[`action_choice.py`][action-choice] 的 `ChoicePlanningRequest`/`ActionChoice`；[`generalist_planner.py`][generalist-planner] 的 `select()`。
- **当前线上位置：**[03-D：ActionChoice → PlannerProposal](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-d-action-choice)。
- **当前页面表述：**页面强调 0/1/N 安全模型和候选遗漏风险，但没有列出多选排序所缺的语义字段。
- **对比：**建议仍不把完整 TaskSpec/历史交给模型，只增加 active-step criteria、target label/role/state、expected effect/reason、last outcome 和 recovery summary。
- **建议架构：**`ChoicePlanningRequest(identity, ActiveStepDecisionView, ActionChoiceView[], last_outcome, recovery_summary)`，响应继续只接受 membership 中的 choice ID。
- **状态：**当前最小 choice payload 为 `CURRENT`；增强 decision view 为 `PROPOSED`。
- **防误读：**增加解释字段不等于放开自由 action/coordinate 生成。

### `OP-14` 保留 ActionChoice 0/1/N，并细化失败 owner 与开放语义逃生通道

- **意见原意：**`0 choices → failure`、`1 choice → Runtime 自动选择`、`N choices → LLM 选 ID` 的设计正确，应保留；要修的是 grounding failure owner 过粗，以及 open semantic expression 的受限解决路径。
- **条目性质：**`KEEP` + `PROPOSED`。
- **当前实现：**`ActionChoiceBuilder` 构造 Runtime-owned candidates；模型不能修改集合。部分 grounding failure 会直接路由 STEP_PLANNER，未完全区分 observation absent、semantic ambiguity、step infeasible 与 user ambiguity。
- **源码证据：**[`action_choice.py`][action-choice]；[`interaction_grounding.py`][grounding]；[`failure_envelope.py`][failure] 与 [`recovery_coordinator.py`][recovery] 的 typed owner/routing。
- **当前线上位置：**[05-C：grounding/choice](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-c-grounding-choice)；[07-B：FailureOwner](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-b-recovery-owner)。
- **当前页面表述：**页面已保留 0/1/N，并把 absent/ambiguous/capability missing 作为 typed failure，但 owner 分工没有细到意见提出的四类。
- **对比：**目标路由为不可见/证据不足→active perception/runtime recovery，多候选语义选择→Step Planner，Step 不可执行→Task Planner，真实用户歧义→User。
- **建议架构：**对 `OpenSemanticExpr` 可发 `OpenChoiceResolutionRequest`；模型只能从当前 target IDs、allowed action kinds 和 TaskSpec 已授权值中选择，并返回 evidence refs。
- **状态：**0/1/N 为 `CURRENT` + `KEEP`；精细 owner 与 bounded semantic fallback 为 `PROPOSED`。
- **防误读：**逃生通道不能读取 raw text 重写 TaskSpec，也不能发明用户要求。

### `OP-15` 保留 Grounding，扩展 Predicate Resolver 而非 regex

- **意见原意：**`InteractionGrounder` 不读取任务原文、只消费 typed intent 与当前 targets 的边界正确；对 prefix/suffix 等开放值，应加 `ValuePredicateResolver`，不要再增加 autocomplete 专用 raw-text regex。
- **条目性质：**`KEEP` + `GAP` + `PROPOSED`。
- **当前实现：**grounder 基于 typed `InteractionIntent` 与 observation targets；collection values 主要映射成 exact `{"option": value}`，适合 exact selection，不足以对候选做组合 predicate filtering。
- **源码证据：**[`interaction_grounding.py`][grounding] 的 `InteractionGrounder`；[`simplified_runtime_contracts.py`][simplified-contracts] 的 interaction/value contracts。
- **当前线上位置：**[05-C：InteractionIntent + Observation → GroundingCandidate / ActionChoice](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-c-grounding-choice)。
- **当前页面表述：**页面肯定 grounding 不重读原文，但尚未展开 exact-only collection resolution 对开放值表达的限制。
- **对比：**建议 resolver 用当前 options 对 `starts_with("An") AND ends_with("ica")` 做 deterministic filtering；0 match 触发 active perception/input prefix，1 match 自动选，N match 交 Step Choice Planner。
- **建议架构：**注册式 `ValuePredicateResolver` 与同一 `SemanticExpr` operator 协议对齐，未注册语义走受限 open resolution 或澄清。
- **状态：**typed grounding 边界为 `CURRENT` + `KEEP`；predicate resolver 为 `PROPOSED`。
- **防误读：**目标不是把自然语言正则从 intake 移到 grounding，而是让 grounding 只处理已准入的 typed predicate。

### `OP-16` ActionContract 与执行边界整体正确

- **意见原意：**`ActionChoice/Proposal → ProposalValidator → ActionContractBuilder → capability gate → preflight → approval → execute → receipt` 必须保留；可拆 `ActionStage` 内部职责，但不能压成 Planner output 直接进 executor。
- **条目性质：**`KEEP` + 局部 `PROPOSED`。
- **当前实现：**ActionStage 处理 bind、preflight、approval、active perception 与 execution，合同绑定当前 snapshot/target/capability/policy；executor 只消费已授权 contract。
- **源码证据：**[`execution_phase.py`][action-stage]；[`contracts.py`][action-contract]；[`safety.py`][capabilities]；[`executors.py`][executor]。
- **当前线上位置：**[05-D：PlannerProposal → ActionContract/preflight](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-d-action-contract)；[05-E：ActionContract → ExecutionReceipt](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-e-execution-receipt)。
- **当前页面表述：**现页已经明确 proposal 非权威、capability/approval/snapshot/preflight 四类检查及 receipt 非完成证明。
- **对比：**意见只建议在 Coordinator 面前保留 `ActionPhase` façade，内部拆 ProposalValidator、ContractBuilder、PreflightService、ApprovalService、BackendRouter、Executor。
- **建议架构：**职责拆分但调用边界不减少；所有执行仍由 Runtime contract 驱动。
- **状态：**合同/执行隔离为 `CURRENT` + `KEEP`；内部 service 拆分为 `PROPOSED`。
- **防误读：**“扁平化”绝不允许 `Planner output → executor` 直连。

### `OP-17` 动作后新观测与独立 Verifier 是成熟边界

- **意见原意：**动作后 `ProgressStage._capture() → fresh post-action BrowserSnapshot → VerifierLadder → VerificationReport` 的方向成熟；没有 verifier 时返回 `INCONCLUSIVE`，不把 receipt success 当成功，应保留。
- **条目性质：**`CURRENT` + `KEEP`。
- **当前实现：**Progress stage 捕获独立 post state；DOM、control state、metadata、HTTP JSON、spatial delta、state delta、receipt evidence 等 verifier 产生 typed evidence/report。
- **源码证据：**[`progress_phase.py`][progress-stage]；[`verification.py`][verification]；[`verification.py`][verifiers]。
- **当前线上位置：**[06-A：Receipt + 新观测 → VerificationReport](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-a-verification-report)；[06-B：VerificationReport → effect decision](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-b-action-effect)。
- **当前页面表述：**现页正确区分 passed/failed/inconclusive，并说明不可观察后端效果可能产生假阴性。
- **对比：**意见没有要求合并 observer、verifier 和 progress；它把这段列为应保留的权威链。
- **建议架构：**继续扩充 verifier ladder 的证据类型，但完成提交仍由 Runtime 独立判断。
- **状态：**`CURRENT` + `KEEP`。
- **防误读：**receipt evidence 可以是 ladder 的一种输入，但不能单独升级成独立完成证明。

### `OP-18` 复用 post-action observation，避免下一轮立即重复 capture

- **意见原意：**当前 ProgressStage 已 capture post snapshot 做 verification，随后 directive 可能让 Coordinator 下一轮再次进入 PerceptionStage 并再 capture；稳定页面会出现连续重复采集。
- **条目性质：**`CURRENT` 风险 + `PROPOSED`。
- **当前实现：**post-action observation 在 ProgressStage 生命周期内参与 verification/progress；下一 loop 的阶段选择没有一个明确 `CONTINUE_WITH_OBSERVATION`/`REUSE_LATEST_OBSERVATION` 契约保证把同一 canonical observation 作为下轮 planner input。
- **源码证据：**[`progress_phase.py`][progress-stage]；[`coordinator.py`][coordinator] 的 directive loop；[`stage_protocol.py`][stage-protocol] 的 `LoopDirective`。
- **当前线上位置：**[04-D：directive → 下一阶段](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-d-loop-directive)；[06-A：post-action capture](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-a-verification-report)。
- **当前页面表述：**此前只说“再次感知”，未揭示 post-action capture 与下一轮 perception 的潜在重复。
- **对比：**建议同一 post-action observation 同时供 effect verification、step completion、task completion 和 next Step Planner；只在 loading、inconclusive、conflict、targeted perception、timeout 等情况下重新捕获。
- **建议架构：**增加 `LoopDirective.CONTINUE_WITH_OBSERVATION` 或 `REUSE_LATEST_OBSERVATION`，显式携带 observation identity/freshness。
- **状态：**重复 capture 路径为 `CURRENT` 风险；复用 directive 为 `PROPOSED`。
- **防误读：**意见不是禁止重新感知；它要求重新感知必须有 freshness/uncertainty 原因，而不是无条件重复。

### `OP-19` Step Completion 要区分状态真值与因果归因

- **意见原意：**`CriteriaEvidenceMatcher` 的 strong、independent、current revision/snapshot、criterion/evidence-requirement link 是正确边界；但“目标状态现在成立”和“目标状态由当前动作造成”是不同问题。
- **条目性质：**`KEEP` + `PROPOSED`。
- **当前实现：**criteria credit 要求 passed strong evidence、独立于 receipt，并绑定当前环境/快照和明确 criterion lineage；动作前 reconciliation 也可发现已满足状态。
- **源码证据：**[`criteria.py`][criteria] 的 `CriteriaEvidenceMatcher`；[`progress_phase.py`][progress-stage] 的 reconciliation/progress credit。
- **当前线上位置：**[06-C：Effect evidence → Step completion](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-c-step-completion)。
- **当前页面表述：**页面已区分 effect passed 与 criterion 可归因，并承认已满足但不能归因时不记 credit。
- **对比：**建议 criterion 增加 satisfaction mode：只关心最终状态时可 precheck 完成；发送/购买/删除等必须证明本次新效果或外部交易。
- **建议架构：**`satisfaction_mode = current_state | new_effect | durable_artifact | external_transaction`，由 evidence policy 选择可接受的证明类型。
- **状态：**强证据绑定为 `CURRENT` + `KEEP`；显式 satisfaction mode 为 `PROPOSED`。
- **防误读：**允许 current-state precheck 不等于对所有副作用免除因果证据。

### `OP-20` TaskCompletionVerifier 的完整 closure 缺口

- **意见原意：**当前 `TaskCompletionVerifier` 主要检查 TaskSpec-backed task 是否有独立 passed VerificationReport，没有逐项求值全部 completion criteria、required requirements、dependencies、仍需成立状态和持久证据；网站 06-D 的描述强于实际最终 gate。
- **条目性质：**`CURRENT` + `GAP`，列为 P0。
- **当前实现：**`runtime_terminal.py` 的 compatibility verifier 对有 TaskSpec 的一般路径只要求传入 verification 且 passed；无 verification、无 receipt、无 effectful action 的特殊情形也可通过。`terminal_readiness.py` 则围绕 legacy plan/progress、active subgoal 与窄 terminal action readiness。
- **源码证据：**[`runtime_terminal.py`][runtime-terminal] 的 `TaskCompletionVerifier.verify()`；[`terminal_readiness.py`][terminal-readiness]；[`terminal_readiness.py`][obligation-view]。
- **当前线上位置：**[06-D：Plan progress → TaskCompleted](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion)。
- **当前页面表述：**此前写成 `TaskObligationViewCompiler → TerminalReadinessEvaluator → READY → TaskCompleted` 并称“全部先决义务”，容易被误读为通用 TaskSpec closure 已实现。
- **对比：**当前实际有“窄 terminal readiness”和“latest independent report based completion”两套不完整机制；目标是一个 evaluator 对 TaskSpec completion expression 全量求值。
- **建议架构：**`TaskCompletionVerifier.verify(task_spec, task_progress, current_observation, evidence_index, latest_outcome)`；全部 required criteria 按 policy 满足后才由 RuntimeCommitter 提交 `TaskCompleted`。
- **状态：**两套窄机制为 `CURRENT` + `GAP`；完整 closure 为 `PROPOSED`。
- **防误读：**Planner `FinishProposal` 只能请求检查完成，不能拥有完成权；Runtime 也可在 closure 成立时自动结束。

### `OP-21` 最终验证需要 Evidence Validity Policy

- **意见原意：**长任务不能要求所有旧证据都来自最终 snapshot；文件 hash、artifact ref、后端状态等持久证据可能继续有效，但当前 UI 状态或外部事务可能需要重查。
- **条目性质：**`PROPOSED`。
- **当前实现：**已有 evidence kind/strength/source constraints、snapshot/revision 绑定和 artifact refs，但没有意见所列的统一 criterion-level validity taxonomy 供最终 closure 组合。
- **源码证据：**[`task_intake.py`][task-intake] 的 `EvidenceRequirement`；[`simplified_runtime_contracts.py`][simplified-contracts] 的 `CriterionEvidencePolicy`；[`criteria.py`][criteria]。
- **当前线上位置：**[06-C：step evidence](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-c-step-completion)；[06-D：task completion](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion)。
- **当前页面表述：**页面强调 current snapshot/revision 与历史外置，但没有完整说明哪些历史证据可跨步骤继续有效。
- **对比：**建议按 criterion 指定 `CURRENT_STATE`、`DURABLE_UNTIL_INVALIDATED`、`ARTIFACT_IMMUTABLE`、`EXTERNAL_RECHECK`、`MODEL_SEMANTIC`、`HUMAN_CONFIRMATION`。
- **建议架构：**TaskCompletionVerifier 组合当前状态、未失效历史强证据、artifact hash、外部 recheck 与 policy 允许的 model/human evidence。
- **状态：**统一 validity policy 为 `PROPOSED`。
- **防误读：**持久证据可复用不等于永不失效；后续可能破坏它的动作必须触发 invalidation。

### `OP-22` ModelVerifier 只能作为 Evidence Provider

- **意见原意：**当前 verifier ladder 主要是机械 verifier，可增加通用 ModelVerifier，但模型只能产生 evidence，是否接受由 EvidencePolicy/TaskCompletionVerifier 决定，进度与完成仍由 Runtime 提交。
- **条目性质：**`PROPOSED`，并重申 `KEEP` 权威边界。
- **当前实现：**机械 verifier 产生 `VerificationReport`；没有一个通用 `ModelVerificationEvidence` 路径覆盖开放语义。
- **源码证据：**[`verification.py`][verification]；[`verification.py`][verifiers]；[`runtime_terminal.py`][runtime-terminal]。
- **当前线上位置：**[06-A：Verifier ladder](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-a-verification-report)；[06-D：TaskCompletion](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion)。
- **当前页面表述：**页面只列当前机械/结构证据和 active perception，没有声称通用 ModelVerifier 已存在。
- **对比：**建议 evidence 包含 criterion ID、verdict、observation ref、evidence refs、confidence 和 reasoning summary；Runtime policy 决定它能否满足特定 criterion。
- **建议架构：**`ModelVerifier → ModelVerificationEvidence → TaskCompletionVerifier(policy) → RuntimeCommitter`。
- **状态：**Model evidence provider 为 `PROPOSED`；Runtime completion authority 为 `KEEP`。
- **防误读：**ModelVerifier 不得直接改 TaskProgress、提交 TaskCompleted、授予 capability 或跳过强机械证据。

### `OP-23` Recovery 架构保留，owner 分类更细

- **意见原意：**`FailureEnvelope → FailureOwner → RecoveryDecision → changed command → RecoveryOutcome` 值得保留；需要细分的是 grounding absent/ambiguous、context truncated、plan invalid、semantic unsupported 等真实 owner。
- **条目性质：**`KEEP` + `PROPOSED`。
- **当前实现：**failure envelope 保存 class/phase/effect status/lineage/attempts/budget；owner/decision 产生 changed dimensions，no-op 检测要求 before/after 证据。部分复合原因仍会收敛为单一 owner。
- **源码证据：**[`failure_envelope.py`][failure]；[`recovery_coordinator.py`][recovery]；[`recovery_phase.py`][recovery-stage]；[`recovery_owner_dispatcher.py`][recovery-owners]。
- **当前线上位置：**[07-A：错误 → FailureEnvelope](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-a-failure-envelope)；[07-B：FailureOwner](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-b-recovery-owner)；[07-C：RecoveryOutcome](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-c-recovery-outcome)；[07-D：不确定效果](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-d-uncertain-effect)。
- **当前页面表述：**现页完整描述 typed owner、changed-dimension/no-op 和 uncertain effect 的保守恢复。
- **对比：**建议 observation 缺失→runtime recovery，多个当前候选→Step Planner，Step infeasible→Task Planner，open semantic→model resolver/user，不可验证外部副作用→terminal/user。
- **建议架构：**Coordinator 只提交 owner 返回的 transition，不自行从错误字符串推导 command。
- **状态：**恢复骨架为 `CURRENT` + `KEEP`；更细 owner taxonomy 为 `PROPOSED`。
- **防误读：**“一个 owner”是控制收敛，不表示 envelope 中次要根因应被删除。

### `OP-24` Trace、Artifact、Benchmark、Skill Evolution 不属于同步完成权威

- **意见原意：**运行事件可以异步进入 trace/artifact，再做 benchmark、failure clustering、skill candidate、replay/promotion；这些离线链不能反向影响当前任务 completion authority。
- **条目性质：**`KEEP`。
- **当前实现：**RuntimeCommitter 写 StateKernel/Trace/Artifact；benchmark 和 evolution 从 run evidence 派生报告或候选，并受 replay/promotion gate 约束。
- **源码证据：**[`trace.py`][trace]；[`artifacts.py`][artifacts]；[`benchmarks/runner.py`][benchmarking]；[`evolution.py`][skill-evolution]。
- **当前线上位置：**[09-A：TraceDag](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-a-trace-dag)；[09-B：Artifacts](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-b-artifacts)；[09-C：Benchmark](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-c-benchmark)；[09-D：Skill evolution](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-d-skill-evolution)。
- **当前页面表述：**现页已明确 runtime evidence、evaluation evidence 与 promotion evidence 是不同层，并强调 benchmark 防泄漏。
- **对比：**意见没有要求删除演化链，只要求保持异步/离线，禁止它成为当次任务的同步成功 gate 或捷径。
- **建议架构：**维持 `Runtime events → Trace/Artifact → benchmark/failure clustering → candidate skill → replay → promotion` 的离线方向。
- **状态：**`CURRENT` + `KEEP`。
- **防误读：**离线证据可以改进未来版本，但不能回写当前 TaskSpec 或替当前 verifier 宣布成功。

## 4. 修改优先级完整落表

### 4.1 P0：当前存在真实语义损失或完成权威缺口

| ID | 原建议 | 依赖与理由 | 主要页面 |
|---|---|---|---|
| `P0-1` | 将 `LLMIntentDraft + IntentDraft + model graph` 收缩为 `IntentProposal` | 减少同一语义的多图重复和不一致；仍保留 Runtime admission | [02-B](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-b-intent-draft) |
| `P0-2` | 建立可组合 `SemanticExpr / ExpectedValue` | 必须先覆盖 prefix、suffix、range、reference、all_of、any_of、open semantic，才能安全删除补偿性 parser | [02-C](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-c-canonical-obligations) |
| `P0-3` | 删除默认路径 raw-text click/focus/drag/select/submit normalizers | 必须晚于 `P0-2`，否则会扩大表达缺口 | [02-B](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-b-intent-draft) |
| `P0-4` | 删除 `StepSpec → legacy SubgoalSpec → StepSpec` | 当前已确认只取首 criterion 并字符串化值，是明确有损 round-trip | [03-B](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-b-plan-authority) |
| `P0-5` | Runtime ActionChoiceBuilder 使用完整 canonical UnifiedObservation | 模型展示预算不得决定 Runtime 目标是否存在 | [05-B](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-b-unified-observation) |
| `P0-6` | TaskCompletionVerifier 求完整 TaskSpec criteria closure | 最新一份 passed report 不能替代全部 requirement、依赖、当前性和证据有效性 | [06-D](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion) |

### 4.2 P1：减少重复投影和职责混杂

| ID | 原建议 | 保留的边界 | 主要页面 |
|---|---|---|---|
| `P1-1` | `PlanningRequest → PlannerContext` 收缩为 typed request + serializer | 保留 provider-specific JSON、排序和展示裁剪 | [08-B](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-b-planner-context) |
| `P1-2` | `GeneralistLMPlanner` 拆成 strict selector 与 historical compatibility planner | strict path 仍只选 Runtime-owned choice ID | [03-D](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-d-action-choice) |
| `P1-3` | `PlanningStage` 内部分成 TaskPlanFlow 与 StepChoiceFlow | TaskPlan authority 与 action choice authority 不合并 | [04-B](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-b-stage-result) |
| `P1-4` | `ProgressStage` 内部分成 PostActionObserver、EffectVerifier、ProgressTransitionService、TaskCompletionVerifier | fresh observation、独立 verifier 和单写者提交继续保留 | [06-A](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-a-verification-report) |
| `P1-5` | 增加 `REUSE_LATEST_OBSERVATION` | loading/conflict/inconclusive/targeted perception/timeout 仍重新捕获 | [04-D](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-d-loop-directive) |

### 4.3 P2：增强开放世界能力

| ID | 能力 | 权限限制 | 主要页面 |
|---|---|---|---|
| `P2-1` | `OpenSemanticExpr` | 保留原语义和 source refs，不直接产生执行权 | [02-C](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-c-canonical-obligations) |
| `P2-2` | `ModelEvidenceProvider` | 只产 evidence，由 policy/Runtime 判断是否接受 | [06-A](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-a-verification-report) |
| `P2-3` | `PredicateResolver` | 只消费已准入的 typed expression 与当前 options，不读 raw text | [05-C](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-c-grounding-choice) |
| `P2-4` | `EvidenceValidityPolicy` | 指定 current/durable/artifact/external/model/human 的有效期和重查规则 | [06-D](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion) |
| `P2-5` | bounded semantic action fallback | 只能从当前 targets、allowed actions、authorized values 中选择并引用证据 | [03-D](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-d-action-choice) |

### 4.4 P3：后置事项

| ID | 后置能力 | 为什么后置 |
|---|---|---|
| `P3-1` | Action Segment / Action Batch | 批量执行会放大错误语义与副作用，必须晚于 TaskSpec/verification closure 收口 |
| `P3-2` | CLI/API surfaces 扩展 | 外壳增多不解决内部语义 round-trip |
| `P3-3` | 跨设备 Workflow Harness | 跨环境会放大 identity、evidence validity 和 recovery 问题，应在核心权威稳定后建设 |

## 5. 建议的唯一完整生产链

下面严格保留意见给出的 11 段顺序。每段都说明转换输入、输出和不能越过的权威边界。

### `CHAIN-01` 外部输入

`TaskRequest / UserRequest → Ingress validation → UserRequest`。入口验证身份、引用、能力上限与基本 schema，不解释 UI primitive，也不允许外层 envelope 覆盖已准入任务语义。

### `CHAIN-02` 来源与一次语义理解

`UserRequest → SourceLedgerBuilder → IntentInterpreter LLM → IntentProposal`。Ledger 保存 whole request 和可引用 spans；IntentProposal 只包含 requirements、typed interaction hints、semantic expressions、constraints、preferences、outputs、dependencies、ambiguities 和 source dispositions。

### `CHAIN-03` TaskSpec 权威化

`IntentProposal → TaskSpecAuthority → TaskSpec`。Authority 执行 schema、lineage、disposition coverage、canonical IDs、dependency consistency、risk/capability bounds、Runtime evidence policy 和 open semantic preservation。repairable 最多一次 bounded repair，ambiguous 询问用户，unsupported 返回 typed failure。

### `CHAIN-04` Task 级规划

`TaskSpec → TaskComplexityRouter → deterministic one-step PlanCandidate | TaskPlanGenerator LLM → TaskPlanAuthority → TaskPlan<StepSpec> + TaskProgress`。Task Planner 不读取 raw text，也不生成具体坐标或审批 token。

### `CHAIN-05` 感知

`Environment → PerceptionSession → canonical UnifiedObservation → StateKernel`。它保留 full current targets、all source bindings、conflicts、freshness 和 evidence refs；这是 Runtime candidate space 的来源。

### `CHAIN-06` Current Step precheck

`Active StepSpec + UnifiedObservation → StepCompletionPrecheck`。若 criterion 已按 satisfaction mode 满足，则直接提交 step progress；否则进入 ActionChoiceBuilder。

### `CHAIN-07` Step 级决策

`ActionChoiceBuilder → 0/1/N`：0 交 typed FailureOwner；1 由 Runtime deterministic selection；N 构造 bounded `ChoicePlanningRequest` 让 StepChoicePlanner 只返回 choice ID；最终由 `ActionSelectionValidator` 校验 membership/identity。

### `CHAIN-08` 合同与执行

`ActionChoice → ActionContractBuilder → ActionContract → task policy/capability/preflight/approval/backend routing → Executor → ExecutionReceipt`。该段保留模型与执行器之间的硬边界。

### `CHAIN-09` 动作后证明

`ExecutionReceipt → PostActionObserver → post-action UnifiedObservation → EffectVerifier Ladder → VerificationResult → ActionOutcome`。ladder 可含 structural/state/artifact/API/visual/model-assisted/human，但每种证据是否可接受由 criterion policy 决定。

### `CHAIN-10` Step 与 Task 进度

`ActionOutcome → StepCompletionVerifier → TaskProgress transition`。Step 未完成或完成后还有 Step 时复用 post-action observation；plan 无效时交 Task Planner replan；所有 Step 完成后进入 TaskCompletionVerifier。

### `CHAIN-11` 唯一任务完成权威

`TaskCompletionVerifier(full TaskSpec completion expression + current observation + retained durable evidence + artifacts + external rechecks + allowed model/human evidence) → RuntimeCommitter → TaskCompleted → RunResult + Evidence + Trace`。Planner finish 只是检查请求，不能提交终态。

## 6. 六个页面修改意见的落实位置

| ID | 页面 | 当前事实必须怎样显示 | 建议目标必须怎样显示 |
|---|---|---|---|
| `PAGE-INTAKE` | [intake 02-B](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-b-intent-draft) / [02-C](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-c-canonical-obligations) / [02-D](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-d-task-spec-admission) | 明示 `LLMIntentDraft → IntentDraft → raw-text normalizers → CanonicalObligationCompiler → coverage → TaskSpec` | `IntentProposal → TaskSpecAuthority → TaskSpec`，并标注尚未实现 |
| `PAGE-PLANNING` | [planning 03-B](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-b-plan-authority) | 明示 `StepSpec → legacy SubgoalSpec → StepSpec` round-trip | `TaskPlan<StepSpec> + TaskProgress` 直接权威 |
| `PAGE-PERCEPTION` | [perception 05-B](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-b-unified-observation) | 明示 bounded `PlannerObservationView` 先于当前 UnifiedObservation | canonical full UnifiedObservation 分叉到 Runtime full view 与 model bounded view |
| `PAGE-VERIFICATION` | [verification 06-D](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion) | 明示 narrow terminal readiness + latest-report completion 两套不完整机制 | full TaskSpec completion expression closure |
| `PAGE-CONTEXT` | [context 08-B](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-b-planner-context) | `PlanningRequest → PlannerContext → model messages` 是当前路径 | `PlanningRequest → pure provider serializer → model messages` 是目标 |
| `PAGE-AGENT-LOOP` | [loop 04-D](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-d-loop-directive) | post-action capture 后下一轮可能再次 perception | `REUSE_LATEST_OBSERVATION` 为建议 directive，不是当前能力 |

## 7. 最终四个语义往返与目标原则

- `FINAL-ROUNDTRIP-01`：自然语言先由模型理解，随后又由 raw-text regex normalizers 理解；目标是自然语言只理解一次，Runtime 只做准入。
- `FINAL-ROUNDTRIP-02`：同一任务要求在 effects、criteria、claims、obligations 等字段重复表达；目标是一套 lossless requirement/criterion authority。
- `FINAL-ROUNDTRIP-03`：typed StepSpec 降级为 legacy SubgoalSpec 后再恢复；目标是 TaskPlan 直接保存 StepSpec。
- `FINAL-ROUNDTRIP-04`：完整观测先按模型预算裁剪，Runtime 再从裁剪结果构造选择；目标是 Runtime 使用 full canonical UnifiedObservation，模型只看 bounded projection。
- `FINAL-PRINCIPLE`：自然语言只理解一次；TaskSpec 只保留一套无损 requirement/criterion 语义；TaskPlan 直接保存 StepSpec；Runtime 使用完整 UnifiedObservation 构造动作；Verifier 根据同一份 post-action observation 逐层证明 effect、step 和 task。

## 8. 全部线上详情锚点索引

这张索引保证 Markdown 能直接跳到每个已有转换块，而不是只跳到页面顶部。

| 页面 | 线上转换块 |
|---|---|
| 入口 | [01-A](https://garrulus21yyx.github.io/affordance-runtime/entrypoints.html#01-a-external-request) · [01-B](https://garrulus21yyx.github.io/affordance-runtime/entrypoints.html#01-b-run-request) · [01-C](https://garrulus21yyx.github.io/affordance-runtime/entrypoints.html#01-c-task-tools) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/entrypoints.html#01-loss-ledger) |
| Intake | [02-A](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-a-source-ledger) · [02-B](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-b-intent-draft) · [02-C](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-c-canonical-obligations) · [02-D](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-d-task-spec-admission) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/intake.html#02-loss-ledger) |
| Planning | [03-A](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-a-plan-candidate) · [03-B](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-b-plan-authority) · [03-C](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-c-planning-request) · [03-D](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-d-action-choice) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/planning.html#03-loss-ledger) |
| Agent Loop | [04-A](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-a-stage-input) · [04-B](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-b-stage-result) · [04-C](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-c-runtime-commit) · [04-D](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-d-loop-directive) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/agent-loop.html#04-loss-ledger) |
| Perception/Action | [05-A](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-a-browser-snapshot) · [05-B](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-b-unified-observation) · [05-C](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-c-grounding-choice) · [05-D](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-d-action-contract) · [05-E](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-e-execution-receipt) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/perception-action.html#05-loss-ledger) |
| Verification | [06-A](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-a-verification-report) · [06-B](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-b-action-effect) · [06-C](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-c-step-completion) · [06-D](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-d-task-completion) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/verification.html#06-loss-ledger) |
| Recovery | [07-A](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-a-failure-envelope) · [07-B](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-b-recovery-owner) · [07-C](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-c-recovery-outcome) · [07-D](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-d-uncertain-effect) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/recovery.html#07-loss-ledger) |
| Context | [08-A](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-a-planning-request) · [08-B](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-b-planner-context) · [08-C](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-c-context-compaction) · [08-D](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-d-history-externalization) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/context.html#08-loss-ledger) |
| Evidence | [09-A](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-a-trace-dag) · [09-B](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-b-artifacts) · [09-C](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-c-benchmark) · [09-D](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-d-skill-evolution) · [损失账本](https://garrulus21yyx.github.io/affordance-runtime/evidence.html#09-loss-ledger) |

## 9. 覆盖台账

“目标建议”表示该条没有当前实现证据可声称；“基线证据”表示固定提交可核验，不表示意见的目标改造已完成。

| Source ID | Markdown section | Public page anchor | Baseline evidence or target proposal | Disposition |
|---|---|---|---|---|
| `OP-00` | §3 OP-00 | entrypoints 01-B/01-C | runtime.py, task_api.py | KEEP + PROPOSED |
| `OP-01` | §3 OP-01 | intake 02-A | source_ledger.py | KEEP + GAP |
| `OP-02` | §3 OP-02 | intake 02-B/02-C | task_intake.py, intent_compiler.py | GAP + PROPOSED |
| `OP-03` | §3 OP-03 | intake 02-C; planning 03-A | canonical_obligation_compiler.py | GAP + PROPOSED |
| `OP-04` | §3 OP-04 | intake 02-D | task_intake.py, task_obligation_coverage.py | KEEP + PROPOSED |
| `OP-05` | §3 OP-05 | intake 02-D | task_intake.py | GAP + PROPOSED |
| `OP-06` | §3 OP-06 | planning 03-A | task_plan_generators.py | GAP + PROPOSED |
| `OP-07` | §3 OP-07 | planning 03-B/03-C | task_plan_contracts.py, simplified_step_projection.py | GAP, P0 |
| `OP-08` | §3 OP-08 | verification 06-D | simplified_step_projection.py | GAP + PROPOSED |
| `OP-09` | §3 OP-09 | perception 05-A/05-B; context 08-A | unified_observation.py | GAP + PROPOSED |
| `OP-10` | §3 OP-10 | perception 05-A/05-B | planning_request_builder.py | GAP |
| `OP-11` | §3 OP-11 | context 08-A/08-B | planner_context.py | GAP + PROPOSED |
| `OP-12` | §3 OP-12 | planning 03-D; context 08-C | generalist_planner.py | GAP + PROPOSED |
| `OP-13` | §3 OP-13 | planning 03-D | action_choice.py | GAP + PROPOSED |
| `OP-14` | §3 OP-14 | perception 05-C; recovery 07-B | action_choice.py, recovery_coordinator.py | KEEP + PROPOSED |
| `OP-15` | §3 OP-15 | perception 05-C | interaction_grounding.py | KEEP + PROPOSED |
| `OP-16` | §3 OP-16 | perception 05-D/05-E | contracts.py, execution_phase.py | KEEP + PROPOSED |
| `OP-17` | §3 OP-17 | verification 06-A/06-B | progress_phase.py, verification.py | KEEP |
| `OP-18` | §3 OP-18 | loop 04-D; verification 06-A | stage_protocol.py | PROPOSED |
| `OP-19` | §3 OP-19 | verification 06-C | criteria.py | KEEP + PROPOSED |
| `OP-20` | §3 OP-20 | verification 06-D | runtime_terminal.py, terminal_readiness.py | GAP, P0 |
| `OP-21` | §3 OP-21 | verification 06-C/06-D | target proposal | PROPOSED |
| `OP-22` | §3 OP-22 | verification 06-A/06-D | target proposal | PROPOSED + KEEP |
| `OP-23` | §3 OP-23 | recovery 07-A–07-D | failure_envelope.py, recovery_coordinator.py | KEEP + PROPOSED |
| `OP-24` | §3 OP-24 | evidence 09-A–09-D | trace.py, artifacts.py | KEEP |
| `KEEP-01`–`KEEP-05` | §2.1 | overview authority plane | baseline boundaries + target naming | KEEP |
| `FLAT-01`–`FLAT-05` | §2.2 | overview architecture diff | baseline round-trips | GAP |
| `P0-1`–`P0-6` | §4.1 | linked per row | baseline gaps + target proposal | P0 |
| `P1-1`–`P1-5` | §4.2 | linked per row | target proposal | P1 |
| `P2-1`–`P2-5` | §4.3 | linked per row | target proposal | P2 |
| `P3-1`–`P3-3` | §4.4 | overview architecture diff | target proposal | DEFERRED |
| `CHAIN-01`–`CHAIN-11` | §5 | overview proposed architecture | target proposal | PROPOSED |
| `PAGE-INTAKE` | §6 | intake 02-B/02-C/02-D | page correction | CURRENT vs PROPOSED |
| `PAGE-PLANNING` | §6 | planning 03-B | page correction | CURRENT vs PROPOSED |
| `PAGE-PERCEPTION` | §6 | perception 05-B | page correction | CURRENT vs PROPOSED |
| `PAGE-VERIFICATION` | §6 | verification 06-D | page correction | CURRENT vs PROPOSED |
| `PAGE-CONTEXT` | §6 | context 08-B | page correction | CURRENT vs PROPOSED |
| `PAGE-AGENT-LOOP` | §6 | loop 04-D | page correction | CURRENT vs PROPOSED |
| `FINAL-ROUNDTRIP-01`–`FINAL-ROUNDTRIP-04` | §7 | overview current architecture | baseline gaps | GAP |
| `FINAL-PRINCIPLE` | §7 | overview proposed architecture | target proposal | PROPOSED |

## 10. 固定基线源码索引

[runtime]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/runtime.py
[task-api]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/integrations/task_api.py
[external-protocol]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/integrations/external_protocol.py
[source-ledger]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/source_ledger.py
[task-intake]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/task_intake.py
[llm-intent]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/intent_compiler.py
[intent-coverage]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/task_obligation_coverage.py
[canonical-compiler]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/canonical_obligation_compiler.py
[simplified-contracts]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/simplified_runtime_contracts.py
[plan-generators]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/task_plan_generators.py
[plan-contracts]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/task_plan_contracts.py
[step-projection]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/simplified_step_projection.py
[planning-request]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/planning_request.py
[planning-request-builder]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/planning_request_builder.py
[unified-observation]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/unified_observation.py
[observation]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/perception.py
[planner-context]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/planner_context.py
[planning-serializer]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/planning_request_serializer.py
[generalist-planner]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/generalist_planner.py
[context-recovery]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/planner_context_recovery.py
[action-choice]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/action_choice.py
[grounding]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/interaction_grounding.py
[failure]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/failure_envelope.py
[recovery]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/recovery_coordinator.py
[action-stage]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/execution_phase.py
[action-contract]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/contracts.py
[capabilities]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/safety.py
[executor]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/executors.py
[progress-stage]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/progress_phase.py
[verification]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/verification.py
[verifiers]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/verification.py
[coordinator]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/coordinator.py
[stage-protocol]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/stage_protocol.py
[criteria]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/criteria.py
[runtime-terminal]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/runtime_terminal.py
[terminal-readiness]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/terminal_readiness.py
[obligation-view]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/terminal_readiness.py
[recovery-stage]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/recovery_phase.py
[recovery-owners]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/recovery_owner_dispatcher.py
[trace]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/trace.py
[artifacts]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/artifacts.py
[benchmarking]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/benchmarks/runner.py
[skill-evolution]: https://github.com/Garrulus21yyx/affordance-runtime/blob/786857f8fb61aa99f2c7e6a23eb8225957e1438b/src/affordance_runtime/evolution.py

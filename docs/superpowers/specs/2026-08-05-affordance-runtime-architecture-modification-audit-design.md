# Affordance Runtime 架构修改意见审计报告设计

## 目标

将用户提供的架构修改意见整理为一份可独立阅读、可逐条反查的详细 Markdown 报告，并把“当前实现架构”与“建议目标架构”同时加入 GitHub Pages 总览。所有结论绑定事实基线 `agent/migrate-runtime-components @ 786857f8fb61aa99f2c7e6a23eb8225957e1438b`，不得把建议写成已实现事实，也不得遗漏或改写意见中的因果关系、优先级和保留边界。

## 交付物

### 1. 详细 Markdown 审计报告

在 `docs/affordance-runtime-deep-dive/` 下新增一份架构修改意见审计 Markdown。它不是意见原文的简略摘要，而是以下内容的可追溯展开：

- 24 个编号链路分析项以及第 0 项入口分析，即 `OP-00` 至 `OP-24`。
- 五条不得删除的权威边界。
- 五组应当扁平化的重复表示。
- P0 的六个修改项。
- P1 的五个职责或投影收缩项。
- P2 的五个开放世界能力项。
- P3 的三个后置事项。
- 建议完整生产链的 11 个阶段。
- 意见明确指定的六个页面同步修改点。
- 最终结论中四个核心语义往返及一条目标收缩原则。

每个 `OP-*` 条目固定包含：

1. 意见原意：忠实保留术语、方向和因果关系。
2. 条目性质：当前事实、风险判断、保留意见或目标建议。
3. 当前实现：基于固定提交核验的实现行为。
4. 源码证据：固定提交上的文件、类、函数和必要测试。
5. 当前线上位置：公开 URL、页面名和稳定章节锚点。
6. 当前页面表述：说明页面现在如何描述该链路。
7. 对比：明确当前实现与意见建议之间的差异。
8. 建议架构：保持意见中的目标边界，不自行扩写成另一套方案。
9. 状态标签：已实现、明确保留、当前缺口、目标建议或后置事项。
10. 防误读：指出哪些内容绝不能被理解成现状或删除建议。

对于无法由代码直接证明的影响，报告使用“可能”“风险”或“意见认为”，不把风险写成已发生事件。对意见中的事实描述若需要补充限定，保留原判断并在“核验说明”中解释，不静默改写。

### 2. 总览双架构图谱

修改 `docs/affordance-runtime-deep-dive/index.html` 的 `SECTION 02`，保留现有整体报告结构，但把原先单一、概念化图谱扩展为两个明确隔离的视图：

- **当前实现架构**：显示固定事实基线中的真实对象往返和兼容路径，包括 raw-text normalizers、`StepSpec → SubgoalSpec → StepSpec`、裁剪后 observation 被 Runtime 候选构造使用、`PlanningRequest → PlannerContext` 二次投影，以及 terminal readiness 与 `TaskCompletionVerifier` 两套不完整机制。
- **建议目标架构**：显示意见提出的 11 段生产链，包括 `IntentProposal`、`TaskSpecAuthority`、`TaskPlan<StepSpec>`、canonical `UnifiedObservation`、post-action observation 复用和完整 TaskSpec closure 的 `TaskCompletionVerifier`。

两个视图必须使用明显的“CURRENT / PROPOSED”标签。建议视图使用“目标”“建议”“尚未实现”等措辞；当前视图不得沿用理想目标替代源码事实。

总览增加逐层对比表，每一层标明：

- 当前对象链。
- 建议对象链。
- 变化类型：保留、收缩、替换、新增或后置。
- 语义损失或权威风险。
- 对应详细审计条目。

保留原有三平面说明，并明确“扁平化数据表示和权威所有者”不等于合并安全、执行、验证边界。

### 3. 稳定线上章节锚点

为九个详情页的转换块和损失账本增加稳定 HTML `id`。锚点使用已有步骤编号的语义化形式，例如：

- `intake.html#02-a-source-ledger`
- `planning.html#03-b-plan-authority`
- `verification.html#06-d-task-completion`

Markdown 中所有线上映射必须链接到公开 GitHub Pages URL 的具体锚点，不能只写文件名或只跳到页面顶部。总览中的对比条目也应链接到相关详细页面位置。

### 4. 六个指定详情页的事实校正

只在意见明确涉及的位置加入当前/目标对照或修正文案，不重构九个单页：

- `intake.html`：标出当前 `LLMIntentDraft / IntentDraft / regex normalizers / CanonicalObligationCompiler` 链和建议 `IntentProposal → TaskSpecAuthority` 链；不得把 normalizers 标记为已经移除。
- `planning.html`：补出生产路径中的 `StepSpec → legacy SubgoalSpec → StepSpec`，并把 `TaskPlan<StepSpec>` 标为目标。
- `perception-action.html`：区分当前“bounded PlannerObservationView 先于 UnifiedObservation”与建议“canonical UnifiedObservation 先于模型裁剪”。
- `verification.html`：修正 06-D 过强表述，说明当前 terminal readiness compatibility path 与 latest-report-based `TaskCompletionVerifier` 均不等同于完整 TaskSpec closure；完整 closure 是目标建议。
- `context.html`：把 `PlanningRequest → PlannerContext` 标成当前二次领域投影，把直接 serializer 标成目标建议。
- `agent-loop.html`：说明当前 post-action capture 后通常还会进入下一轮 perception，复用 post-action observation 是建议能力。

`entrypoints.html`、`recovery.html` 和 `evidence.html` 不因“扁平化”删除已有边界，只增加稳定锚点；必要时通过 Markdown 明确它们属于保留项。

## 信息完整性与防曲解机制

### 原文覆盖台账

报告末尾提供机器可检索的覆盖台账。每个来源条目拥有唯一 ID，并至少映射到：

- Markdown 标题或表格行。
- 一个线上页面锚点；若属于总览原则，则映射到总览双架构图或差异表。
- 一个源码证据位置，或明确标记为“目标建议，无当前实现证据”。
- 一个处置结果。

验收脚本或检查命令应确认所有预定义 ID 均出现，避免依赖人工印象判断“似乎写全了”。

### 状态与证据口径

使用以下互斥主标签：

- `CURRENT`：固定提交中可证明的当前事实。
- `KEEP`：意见明确要求保留的当前边界。
- `GAP`：意见指出的当前缺口或有损往返。
- `PROPOSED`：意见建议的目标结构，尚不代表已实现。
- `DEFERRED`：意见明确放到 P3 的后置能力。

目标建议可以引用现有实现作为迁移起点，但不能因此标成 `CURRENT`。页面中的安全性拒绝、澄清、UNKNOWN 或权限收缩不得误记为应该恢复的语义损失。

## 源码核验范围

当前 HEAD 与事实基线之间没有 `src/` 或 `tests/` 变化，因此代码核验可直接在当前工作树进行，但所有网页源码链接仍绑定完整提交 SHA。重点核验：

- intake、source ledger、canonical obligation compiler 和 semantic value schema。
- task plan generator、authority binder、legacy projection 和 terminal projection。
- observation、planning request、planner context、action choice 和 grounding。
- action contract、execution、post-action observation、criteria evidence 和 task completion。
- recovery owner、Trace、Artifact、benchmark 与 evolution 边界。

## 视觉与交互约束

- 沿用现有静态 HTML、CSS 和零第三方运行时结构。
- 当前与建议架构不得仅靠颜色区分，必须有文字标签和解释。
- 新增锚点后，固定导航不得遮挡目标标题。
- 320px 移动端不得出现页面级横向溢出；宽表格保留局部滚动。
- JavaScript 关闭时，两个架构、对比表和详情内容仍可阅读。

## 验收标准

- Markdown 覆盖全部来源条目，覆盖台账无缺号、重复号或无落点条目。
- `OP-00` 至 `OP-24` 均有当前事实、线上位置、对比、建议和防误读说明。
- 五条保留边界、五组扁平化对象、P0/P1/P2/P3、11 段目标链、六个页面修改点均可机器检索。
- 总览同时显示当前实现与建议目标，标签明确且无事实混淆。
- 六个详情页完成指定事实校正；其余三页不被错误重构。
- 所有公开页面锚点、本地链接、源码固定提交链接和资源链接有效。
- HTML 解析、移动端与桌面端浏览器检查、控制台检查、仓库测试、Ruff 和 `git diff --check` 通过。
- 更新 `gh-pages` 后，公开 URL 和新增锚点可访问。

## 非目标

- 不修改 Runtime 生产代码或测试来实现意见中的目标架构。
- 不把整套报告改造成问答题库。
- 不删除 ActionContract、独立验证、单写者、Recovery owner、Trace 或 Artifact 等意见明确要求保留的边界。
- 不把 `OpenSemanticExpr`、`TaskSpecAuthority`、完整 completion closure、post-action observation 复用等建议描述为已实现。
- 不更新事实基线到当前文档提交；所有实现判断仍绑定 `786857f8fb61aa99f2c7e6a23eb8225957e1438b`。

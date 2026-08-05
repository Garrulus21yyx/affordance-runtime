# Affordance Runtime 中文全链路解读站设计

## 目标

基于分支 `agent/migrate-runtime-components` 的当前远端同步提交 `786857f8fb61aa99f2c7e6a23eb8225957e1438b`，生成一套可直接由 GitHub Pages 托管的中文架构解读站。读者应能从用户自然语言输入开始，沿真实代码路径理解任务接入、意图编译、规划、结构化协议、感知、动作选择、执行、验证、进度归因、恢复、终止、结果与证据输出，同时理解上下文构建和压缩等跨切面问题。

## 受众与预期效果

主要受众是希望完整理解 Agent Runtime、准备以该项目进行技术面试或架构评审的工程师。读完后，读者不仅能复述“模块有哪些”，还应能回答：

- 每个阶段的输入、输出、状态所有者和失败模式是什么；
- 哪些决定由模型提出，哪些决定必须由 Runtime 代码校验或提交；
- Planner 如何从自然语言转成 typed proposal、TaskPlan、StepSpec、InteractionIntent、ActionChoice 与 ActionContract；
- 主循环如何避免过期观察、重复动作、错误进度归因和预算式空转；
- 上下文如何组装、裁剪、恢复，仓库当前实现与通用 Context Manager/会话压缩之间有何区别；
- 目标架构、现有默认路径、兼容边界和未闭合治理项分别是什么。

## 事实规则

1. 当前代码、当前测试和当前脚本优先于历史文档。
2. SAR-0 权威架构文档用于解释目标与约束，但不得冒充已落地实现。
3. 历史/归档文档只用于说明演进背景，必须显式标为历史。
4. 每个关键结论附源码文件、符号或测试锚点。
5. 不从类名推断行为；关键链路必须追到调用者、返回类型和状态提交点。
6. Agent Atlas 仅用于校准分析深度与潜在追问，不作为 Affordance Runtime 事实来源。

## 信息架构：混合式架构图谱

页面采用“总览地图 + 连续 E2E 主叙事 + 纵向深挖专题”的混合结构：

1. **首页心智模型**：一句话定位、系统边界、五阶段主循环、三类权威、关键状态对象。
2. **自然语言到结构化任务**：TaskIntake、IntentCompiler、SourceLedger、Canonical Obligation Compiler、TaskPlan admission、planner proposal 与 schema recovery。
3. **Planner 到 Task/Step**：规划请求组装、上下文序列化、模型输出、结构化校验、StepSpec 与 InteractionIntent、TaskSkill 与 obligation coverage。
4. **Agent Loop 全链路**：Perception → Planning → Execution/Action → Progress → Recovery，说明循环不变量、预算、路由和 RuntimeCommitter。
5. **动作落地 E2E**：UnifiedObservation、grounding、ActionChoiceSet、contract binding、preflight、executor、post-observation、verification、step/task completion。
6. **失败与恢复**：typed failure envelope、owner handoff、provider/context/schema recovery、机械恢复、replan、用户/终端交接。
7. **上下文与压缩**：区分 planner context、runtime state、trace/evidence、模型消息窗口和会话历史；如实说明仓库中的压缩/恢复机制及其边界。
8. **安全、权限与副作用**：scope authorization、capability、approval token、risk、idempotency、compensation 与 uncertain effect。
9. **状态、证据、Trace 与评估**：single writer、obligation attribution、progress credit、liveness、artifact、benchmark 与 evolution。
10. **完整 E2E 案例**：以仓库通用场景为例，逐步展示对象形态和状态变化，不嵌入 benchmark 特化逻辑。
11. **代码地图与阅读路线**：按入口、协议、阶段、恢复、适配器、集成、测试列出源码导航。
12. **术语表与深挖索引**：正文首次出现即解释；末尾提供可检索术语表和架构追问索引，但不写成问答主文。

## 页面交互与视觉表达

- 顶部提供可点击的 E2E 架构图谱，节点跳转到对应章节。
- 桌面端使用固定目录，窄屏折叠为章节导航。
- Mermaid 风格图形以原生 SVG/HTML 实现，避免 GitHub Pages 运行时依赖。
- 每个阶段统一展示：职责、输入、输出、关键类型、状态写入者、失败出口、源码锚点。
- “现状 / 目标 / 兼容 / 风险”使用稳定标签，防止读者混淆架构时态。
- 结构化对象使用可复制的 YAML/JSON/Python 伪实例，但必须与真实 dataclass/enum 字段一致。
- 深挖内容用 `<details>` 渐进展开，保证主链路连续且不牺牲分析深度。
- 页面支持打印和窄屏，所有图表有文字替代说明。

## 文件设计

- `docs/affordance-runtime-deep-dive/index.html`：GitHub Pages 主页面与完整中文报告。
- `docs/affordance-runtime-deep-dive/styles.css`：响应式布局、架构图谱、术语和打印样式。
- `docs/affordance-runtime-deep-dive/site.js`：目录高亮、窄屏导航和轻量交互；核心内容在无 JavaScript 时仍可阅读。
- `docs/affordance-runtime-deep-dive/README.md`：本地预览、GitHub Pages 发布方式、事实基线和维护说明。
- `docs/README.md`：加入报告入口。
- `docs/superpowers/plans/2026-08-01-affordance-runtime-github-pages-report-plan.md`：执行状态与验证记录。

## 内容质量门槛

- 报告覆盖从自然语言输入到结果返回的完整主路径，并单独覆盖 replan/recovery 路径。
- Planner、TaskPlan、Step、Intent、Criterion、Obligation、Choice、Contract、Receipt、Verification、Progress、Trace 等术语均有定义。
- 至少包含：一张系统边界图、一张自然语言到 typed contract 转换图、一张 agent loop 时序图、一张状态所有权图、一张失败/恢复路由图和一个完整 E2E 对象演化示例。
- 每个核心阶段至少给出一个真实源码锚点和一个验证该行为的测试或脚本锚点。
- 明确指出仓库是否存在通用会话级 LLM 历史压缩；不得把 planner context projection/recovery 错称为完整会话压缩。
- 页面内部链接、HTML 结构、源码链接和响应式布局通过自动检查与浏览器检查。

## 非目标

- 不部署或修改远程 GitHub Pages 设置。
- 不改 Runtime 生产代码或测试行为。
- 不声称当前代码已完成 SAR-0 的全部目标架构。
- 不把报告写成面试题集、营销文案或 benchmark 成绩展示页。


# Project Agent Policy

## Mainline and proportional rigor

本项目不追求生产级别保障，也不追求与项目主线无关的非必要严谨性。始终坚持主线：围绕本项目主旨构建结构清晰的 GUI agent，并最终通过 benchmark 结果体现其泛化能力与鲁棒性。

- 以可运行的 GUI 能力、清晰的职责边界和 benchmark 可验证的改进为优先目标。
- 正确性与验证强度应与当前声明范围和实际风险相称；不得因假设性完备、生产级运维要求或未被证据触发的边缘情况阻塞主线。
- 避免为局部问题引入通用平台、过重抽象或大量案例枚举；优先修复有运行数据或性质不变量支持的共享根因。
- benchmark 是泛化与鲁棒性的最终实证标准。单元测试、性质测试和架构审查用于保护主线，而不是取代真实 benchmark，或成为无限延迟 benchmark 的理由。
- 当“进一步严谨”与“推进主线”冲突时，在不破坏已声明核心合同、事实 authority 和基本安全边界的前提下，选择最小、清晰、可测并能尽快回到 benchmark 的方案。

## Owner-first change discipline

任何修复、功能或可观测性改动都必须先确定事实 authority、合同 owner、转换 owner、执行 owner、观测 owner，以及它们的生产者和消费者，再修改对应 owner。不得以“最小改动”“边界补丁”或“先让测试通过”为理由，把职责塞进调用链中方便插入的位置。

- Core Loop 只负责编排既有 typed ports、状态推进和终止；不得承接 provider 协议解析、Tool Schema、参数 normalize、binding、SurfaceAdapter、World projection、视觉语义、评估语义或 Trace 重建逻辑。
- Registry/ToolCatalog 拥有模型可见工具合同；provider transport 只拥有 wire envelope 和 provider exchange；catalog-aware normalizer 只做有合同依据的表示规范化；binding owner 只在合法语义调用之后解析私有执行参数；executor 只执行已绑定请求。
- SurfaceAdapter 拥有外部环境到 Unified World 的采集与来源语义；World projection 拥有统一公开事实；视觉 provider 拥有开放世界视觉推断并返回 typed outcome；任何下游模块不得重新猜测或重复投影这些事实。
- Trace/Langfuse 只能观察各 owner 已产生的输入、输出、typed failure 和 lineage；不得成为第二状态、第二控制流，或在事后重建本应由 owner 直接记录的事实。每次 provider call 及 repair call 的输入和输出必须在 provider 边界直接进入 transcript。
- “选择最小修复”只适用于已经确认正确 owner 之后，在该 owner 内选择最小完整改动；它不能用来绕过根因分析、authority 一致性或职责边界。
- 验收必须覆盖 owner 之间的不变量和真实 benchmark；不得以单个字符串、case 或局部分支测试代替数据流、authority 和异常路径验证。

## Generalization-first implementation constraint

所有产品实现都必须服务于跨任务、跨站点和跨 benchmark case 的泛化能力；测试与 benchmark 只能验证产品合同，不能反向塑造产品分支。

- 禁止针对单个测试、benchmark case、fixture、页面文案、已知 selector、固定 action ID、固定输出名或任务名增加生产特化，也禁止以关键词、单例数量、已知顺序或相似启发式形成软特化。
- 禁止把案例枚举或不断增长的 `if/elif` 机械判断当作能力实现。新增分支必须对应稳定、显式、可复用的领域合同或闭合类型代数，并由清晰的 owner 负责。
- 观察、语义动作、执行路由、外部效果、产物物化和完成判定必须保持职责分离；不得由底层 adapter 猜测任务语义，也不得为了通过验收而重复投影同一事实或建立旁路 oracle。
- DOM、视觉、WoT、HTTP 等输入必须通过 SurfaceAdapter 进入同一个 Unified World；模型只消费统一的公开世界与动作协议，私有路由和执行细节留在 Runtime 内部。
- 浏览器自动化、可访问性树、视觉感知、文件下载、网络传输等成熟底层能力优先委托给 Playwright、BrowserGym 或已选定的可靠库；除非有明确缺口证据，不自造替代实现。
- 不把所有问题都机械化。类型检查、权限、时序、currentness、闭合状态转移、dispatch receipt 和可由明确 postcondition 证明的事实由 Runtime 确定性处理；页面语义理解、开放世界感知、任务分解、语义 grounding，以及不能由明确 postcondition 闭合的判断必须交给 agent/model 或可替换的现成模型 provider。
- 本项目不单独训练、微调或 RL 后训练模型，也不建设训练数据飞轮。agent/specialist 指通过 typed port 使用现成通用多模态、computer-use 或 grounding 模型；不同认知职责可以复用同一模型/provider。能力不足时返回 typed `unsupported/unknown/needs_input`，不得退回手写 benchmark 规则。
- 架构选择应与当前通用 GUI agent 的主流思路一致：agent 负责基于统一公开世界进行感知、推理、规划和语义动作选择，必要时路由到独立的模型-backed grounding/verifier 角色；Runtime 拥有能力路由、合法性、私有绑定、执行、观测、证据 lineage 和最终控制状态。benchmark 提升是结果证据，不是生产代码的条件输入。

## Goal-plan convergence constraints

任务语义能力必须留在现有单一 `CoreAgentLoop` 中，并保持“认知增强不接管控制”的边界：

- 用户目标 authority 只有可修订 `TaskGoal`；当前环境 authority 只有 fresh `WorldObservation`。
- task start/revision 各调用一次 model-backed GoalCompiler。模型只输出有界、静态、非权威的 `GoalPlan`；每项只有
  `id | objective | done_when | depends_on | final`。Runtime 只校验 1..8 items、ID 唯一、依赖存在且无环、文本长度和
  最多一个 final，不解释 GUI 语义，不生成 relation/predicate/entity query AST，也不计算 plan progress。
- `GoalPlan` 直接投影进 `AgentContext`。唯一 ActionPolicy 每 step 根据 `TaskGoal + GoalPlan + fresh World + bounded
  recent steps + tools` 重新判断当前应推进的 item，并只选择一个动作。它必须保留已满足状态、不得重复点击已 active
  toggle（除非目标要求撤销），优先推进依赖已满足的未完成 item，且只有所有依赖从 fresh World 明显满足后才执行 final item。
- `GoalPlan` 不是 mutable milestone/todo、状态机、权限、确认、完成证明或第二真相；Runtime 不存 item status、frontier、
  per-subject progress、GoalBinding、GoalSnapshot 或 achievement record。
- compiler 结果仅为 `Ready|NotRequired|NeedsInput|Unsupported|Failed`。`Unsupported|Failed` 记录 unavailable 后继续普通
  GUI loop；只有确实缺少用户拥有事实的 `NeedsInput` 才复用 `AskUser/waiting_user`。provider/schema failure 不得映射为
  run `failed|blocked`。
- 不自动 recompile。用户修订 `TaskGoal` 时旧 plan 失效并重新编译；URL/layout 变化、重复动作、unchanged/regressed 和
  “撞墙”只进入 ActionPolicy 可见的 World/recent-step feedback。
- provider envelope 对未知的有界描述字段宽容忽略；必填字段缺失、类型错误、重复/悬空/循环依赖、超界内容和多个 final
  typed fail，并最多允许一次 schema repair 和一次 Boundary contract repair。每次 initial/repair transcript 必须立即保存。
- `SelectAction -> Binder -> BoundActionRequest -> Executor` 不变。动作合法性、currentness、binding、风险与确认保持严格；
  GoalPlan 不能隐藏、拒绝或授权动作。
- `ActionEffect` 只证明局部 UI 效果；只有 `TaskEvaluator`/native verifier 可以终止任务。
- VLM 只能经 SurfaceAdapter/Fusion 为同一 World 补充当前证据，不是 repetition/long-task fallback。
- 不引入 Manager/Worker、每步 planner/compiler、单独 LLM goal evaluator、mutable TaskPlan、memory、RAG、ArgMin、
  achievement record、第二 Binder 或第二 Runtime loop。只能由已命名 benchmark 缺口另行触发。

设计解释、SOTA 对齐和实施/验收状态只维护在 `docs/architecture.md` 与 `docs/benchmark.md`。当前状态以这两个文件为准：
Planner/Auditor convergence 的 provider-free G0–G6 已通过；live benchmark 仍需用户单独授权，不得继续案例特化。

## MiniWoB / BrowserGym runtime facts

这些是项目中已经确认的本地运行事实。执行 MiniWoB benchmark 时必须先复用，禁止仅因当前 shell 没有 export 环境变量就宣称 runtime、URL、source 或 provider 配置缺失。

- 项目配置文件：`/home/yang/projects/affordance-runtime/.env`。先加载它，再设置本次运行的显式 profile；不得打印 API key。
- BrowserGym 固定解释器：`/home/yang/.venvs/affordance-browsergym-py312/bin/python`。
- 已安装版本：`browsergym-miniwob==0.14.3`、`playwright==1.44.0`。
- MiniWoB source：`/home/yang/projects/affordance-runtime/evidence/browsergym-bridge/source/MiniWoB-plusplus/miniwob/html`。
- HTML 实际位于 source 下的 `miniwob/*.html`，所以 base URL 必须以 `/miniwob/` 结束。
- 项目专用本地服务默认使用 `127.0.0.1:18888`；不要误用机器上其他项目的 `http.server`。

启动持久后台静态服务：

```bash
setsid /home/yang/.venvs/affordance-browsergym-py312/bin/python -m http.server 18888 \
  --bind 127.0.0.1 \
  --directory /home/yang/projects/affordance-runtime/evidence/browsergym-bridge/source/MiniWoB-plusplus/miniwob/html \
  </dev/null >/tmp/affordance-miniwob-http.log 2>&1 &
```

启动前先用 `curl http://127.0.0.1:18888/miniwob/click-button.html` 检查；返回 200 就复用，不重复启动。运行 benchmark 时设置：

```bash
set -a
source /home/yang/projects/affordance-runtime/.env
set +a
export MINIWOB_URL=http://127.0.0.1:18888/miniwob/
export PYTHONPATH=src:tests
```

Zhipu 视觉运行使用 `glm-4.6v-flash`。需要复现当前视觉 gate 时显式设置：

```bash
export LLM_ACTIVE_PROFILE=zhipu
export LLM_ZHIPU_MODEL=glm-4.6
export LLM_ZHIPU_VISION_MODEL=glm-4.6v-flash
export LLM_PROFILE_FALLBACK_TO_LOCAL=false
```

`.env` 中也可能有不同的默认 `LLM_ZHIPU_MODEL` 或 `LLM_ZHIPU_VISION_MODEL`；明确指定的 benchmark profile 优先，不能据默认值否定当前配置的多模态能力。

## Long benchmark background execution

- 用户要求后台运行时，用持久 PTY/session 启动一次，保存返回的 session ID，立即告诉用户“已启动 + session ID”，不要持续轮询。
- 用户说“查看”时只通过保存的 session ID 读取新输出；不要重复启动同一 run。
- benchmark 主体结束前不要在仅内存对象上做可能失败的临时汇总。优先让正式 runner 写 evidence；若必须打印汇总，先使用兼容字符串/enum 的序列化，并确保原始 per-case 结果已持久化。
- 后台 run 失败时区分：environment/provider/case failure 与 run 完成后的 reporting/serialization failure。后者不得误报为 GUI case 失败。
- 运行配置发现顺序固定为：项目 `AGENTS.md` → 项目 `.env` → 固定 BrowserGym interpreter → 本地 URL 健康检查 → 必要时启动项目专用静态服务。不得每轮从零搜索整个 home 目录。

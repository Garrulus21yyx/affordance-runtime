# Project Agent Policy

## Mainline and proportional rigor

本项目不追求生产级别保障，也不追求与项目主线无关的非必要严谨性。始终坚持主线：围绕本项目主旨构建结构清晰的 GUI agent，并最终通过 benchmark 结果体现其泛化能力与鲁棒性。

- 以可运行的 GUI 能力、清晰的职责边界和 benchmark 可验证的改进为优先目标。
- 正确性与验证强度应与当前声明范围和实际风险相称；不得因假设性完备、生产级运维要求或未被证据触发的边缘情况阻塞主线。
- 避免为局部问题引入通用平台、过重抽象或大量案例枚举；优先修复有运行数据或性质不变量支持的共享根因。
- benchmark 是泛化与鲁棒性的最终实证标准。单元测试、性质测试和架构审查用于保护主线，而不是取代真实 benchmark，或成为无限延迟 benchmark 的理由。
- 当“进一步严谨”与“推进主线”冲突时，在不破坏已声明核心合同、事实 authority 和基本安全边界的前提下，选择最小、清晰、可测并能尽快回到 benchmark 的方案。

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

Zhipu 视觉运行已经确认可使用 `glm-4.1v-thinking-flashx`。需要复现当前视觉 gate 时显式设置：

```bash
export LLM_ACTIVE_PROFILE=zhipu
export LLM_ZHIPU_MODEL=glm-4.1v-thinking-flashx
export LLM_ZHIPU_VISION_MODEL=glm-4.1v-thinking-flashx
export LLM_PROFILE_FALLBACK_TO_LOCAL=false
```

`.env` 中也可能有不同的默认 `LLM_ZHIPU_MODEL` 或 `LLM_ZHIPU_VISION_MODEL`；明确指定的 benchmark profile 优先，不能据默认值否定 4.1V 的多模态能力。

## Long benchmark background execution

- 用户要求后台运行时，用持久 PTY/session 启动一次，保存返回的 session ID，立即告诉用户“已启动 + session ID”，不要持续轮询。
- 用户说“查看”时只通过保存的 session ID 读取新输出；不要重复启动同一 run。
- benchmark 主体结束前不要在仅内存对象上做可能失败的临时汇总。优先让正式 runner 写 evidence；若必须打印汇总，先使用兼容字符串/enum 的序列化，并确保原始 per-case 结果已持久化。
- 后台 run 失败时区分：environment/provider/case failure 与 run 完成后的 reporting/serialization failure。后者不得误报为 GUI case 失败。
- 运行配置发现顺序固定为：项目 `AGENTS.md` → 项目 `.env` → 固定 BrowserGym interpreter → 本地 URL 健康检查 → 必要时启动项目专用静态服务。不得每轮从零搜索整个 home 目录。

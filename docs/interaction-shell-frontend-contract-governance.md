# Interaction Shell 前端合同治理与详细设计

> 状态：Phase 0–3 已作为一个不可拆分的 `interaction-shell.v3` 单元实施并达到 verified closure。Provider-free Runtime/backend/frontend/Playwright 证据已通过，独立fresh-context架构复核结论为APPROVE，coherent implementation commit为 `a6aa19be`，提交后 OpenAPI/Hey API regenerate-and-diff 无差异。Phase 4 仍 dependency-blocked且不属于本次批准范围。
> 日期：2026-08-27。
> 适用工作树：`/home/yang/projects/affordance-runtime-interaction-shell`，审查基线 `codex/external-interaction-shell@7af330c7`，并包含该工作树当前未提交改动。
> 范围：`external/interaction-shell/backend`、`external/interaction-shell/frontend` 与 Runtime `public_session` 边界。
> 排除：主工作树中的遗留 `affordance_runtime.benchmarks.console`。
> 状态 authority：本文件描述目标设计、迁移与治理门；当前 Interaction Shell 实施状态仍以 `docs/interaction-shell.md` 为准，Core/benchmark 状态仍以 `docs/architecture.md`、`docs/benchmark.md` 为准。
> 主线集成：本合同已在独立 integration worktree 中以本地 `codex/simplify-core-runtime@baebf2e2` 为底适配；集成保留 simplify 的 delivery/context/provider/history 热路径，只在原 owner 中加入 Shell control/checkpoint 语义。该 provider-free 集成证据不改变 Phase 4 blocked 状态，也不构成 live benchmark 表现证据。

## 1. 决策

Interaction Shell 采用单向、协议生成优先的前后端协议链：

```text
Runtime public_session
→ RuntimeSessionPort projection
→ backend Pydantic shell contracts                 唯一公共合同 authority
→ deterministic OpenAPI / JSON Schema              生成
→ TypeScript DTO + runtime validators + named SDK   生成
→ authored typed command builder + session controller + pure view model
→ authored React presentation
```

前端可以手写交互与展示实现，但不得手写或镜像任何跨边界协议。具体含义是：

- 允许手写：React 组件、样式、可访问性、布局、视觉文案、通用连接控制、纯 view-model、用户输入状态，以及第 4.2 节限定的穷尽 typed command builder。
- 禁止手写：DTO、endpoint 路径、HTTP method、headers/body envelope、transport command kind 字符串、SSE/AG-UI envelope、事件 payload cast、Runtime 状态/命令 admissibility 代数、与 OpenAPI 同构的测试 fixture。受限 builder 对 generated discriminant 的穷尽匹配是唯一例外。

目标不是把所有前端源代码都生成，而是让**协议事实只定义一次**。任何后端合同变化必须通过生成物和 CI diff 显式传播；前端业务代码只能消费已验证的 typed values。

## 2. 问题与共享根因

本节记录Phase 0冻结时的v2迁移基线，而不是当前实现状态。该基线的Shell大方向正确：前端不 import Core、World、Binder、Surface 或 provider；后端普通路径只通过 `affordance_runtime.app.public_session` 连接 Runtime，并已有外部隔离测试；但当时协议链仍有以下手写接缝。Phase 2–3已按第23节证据删除这些接缝。

### 2.1 手写 transport 绕过了已生成 OpenAPI

`external/interaction-shell/frontend/src/generated/api.ts` 已从 OpenAPI 生成类型；然而 `external/interaction-shell/frontend/src/lib/api.ts` 仍以：

```ts
postCommand(path: string, body: Record<string, unknown>)
```

发送命令，`use-shell-session.ts` 再手写 `commands/answer`、`commands/revise`、`commands/takeover`、`commands/return-control` 等路径、kind 和 body。这使 OpenAPI 只成为静态类型索引，而没有成为 transport authority。

### 2.2 事件合同是弱类型旁路

后端 `ShellEvent` 使用 `type: str` 与 `data: dict[str, object]`，`CoreRuntimeSessionPort` 约定将 snapshot 放进 `data["snapshot"]`；前端通过：

```ts
event.data?.snapshot as Snapshot
```

取值。`data.snapshot` 是真实运行合同，却没有进入 schema 代数，也没有运行时验证。

### 2.3 前端重复推导 Runtime command legality

Hook 与组件分别组合：

```text
run_status
capabilities
checkpoint_id
resume_eligible
control_owner
control_lease_id
viewer.status
```

判断 Start/Answer/Revise/Pause/Resume/TakeOver/ReturnControl 是否可用。Runtime admission 仍会最终拒绝非法命令，但 UI 已经形成第二份不完整状态代数，新增状态或命令需要多点同步。

### 2.4 浏览器展示概念进入公共 Shell 合同

`ViewerState` 暴露 `steel|browserbase` provider，并要求 `/viewer/...`；React 组件直接显示 `Browser session`、`Browser Live View`。这在 Web-only 声明范围内可运行，却无法作为 Android/desktop 的稳定展示合同。

### 2.5 产品控制 Snapshot 混入 benchmark 分析

`RuntimeSessionSnapshot` 包含 `completed_analysis`、`benchmark_result`、token/recovery/Langfuse locator，产品完成卡也显示 benchmark result。同时 `/diagnostics` 已有独立工程分析面。两个投影重叠，使 product session contract 对 benchmark artifact 变化敏感。

### 2.6 transport failure 与 Runtime recovery 在浏览器端合并

任意 SSE failure 在 paused/resumable 状态下都可能触发 `/recover`。当前 manager 对仍存在的 live session会安全返回原 snapshot，但“网络重连”与“进程重启后的 Runtime recovery”仍由前端根据状态猜测，而不是由 Shell owner 返回 typed outcome。

这些问题的共同根因是：**后端虽拥有数据模型，但未拥有完整的客户端 transport、事件 payload 和可执行 command offer；前端被迫补齐这些合同。**

## 3. 目标 owner 模型

| 事实或转换 | 唯一 owner | 生产者 | 消费者 | 不得承担 |
| --- | --- | --- | --- | --- |
| Runtime task/status/interrupt/completion | Runtime `public_session` | `TargetRuntimeSession` | `RuntimeSessionPort` | Web 文案、HTTP、React 状态 |
| Shell public projection | `RuntimeSessionPort` | `CoreRuntimeSessionPort` | Shell manager/API | Core state重建、binding、evaluation |
| Shell schema | backend Pydantic contracts | `contracts.py` | OpenAPI/schema generator | 手写 TS mirror |
| HTTP operations | FastAPI route contract | `api.py` | generated SDK | 前端路径常量 |
| event domain payload | typed `ShellEvent` union | RuntimeSessionPort | AG-UI encoder、generated validator | `dict[str, object]` convention |
| event transport | Shell API transport adapter | AG-UI/SSE encoder | generic frontend stream client | Runtime recovery 决策 |
| semantic command legality/refs | Runtime public session | `TargetRuntimeSession._project` | RuntimeSessionPort | Viewer/deployment、React 状态代数 |
| client-visible command offers | RuntimeSessionPort 的纯交集与投影 | Runtime state-correct capabilities/refs + deployment availability | generated `CommandOffer` | 补算 Runtime legality、授权 |
| Shell session access与串行化 | Shell manager | live credential/session lookup + per-session command lock | RuntimeSessionPort | semantic legality、command identity/currentness、业务结果 |
| deployment-gated command admission | RuntimeSessionPort | fresh `SurfaceAvailability`/deployment capability | Runtime semantic admission | status/ref/business outcome重算；Runtime调用后的事后拒绝 |
| command semantic admission/currentness/idempotency | Runtime public session | `TargetRuntimeSession` | RuntimeSessionPort | HTTP/auth、deployment availability、wire code猜测 |
| command admission wire projection | RuntimeSessionPort 的穷尽纯转换 | typed Runtime admission outcome | Pydantic contract/frontend renderer | 改写业务结果、创建新状态、`runtime_conflict`兜底 |
| product view model | frontend pure presenter | validated snapshot/offers | React components | transport、schema、Runtime legality |
| provider-neutral surface availability | deployment viewer projector | Steel/local deployment profile | RuntimeSessionPort | control owner/lease、interactive legality |
| public `SurfaceView` composition | RuntimeSessionPort 的唯一纯转换 | surface availability + Runtime control owner/lease | Shell snapshot/UI renderer | provider credential、private locator、lease创建 |
| checkpoint record/consumption truth | `RuntimeCheckpointStore` | checkpoint owner | TargetRuntimeSessionFactory inspector/recover | Shell auth/conversation、deployment availability |
| live checkpoint ref/currentness | `TargetRuntimeSession` | current live Runtime state | RuntimeSessionPort | registry/store重建、environment reconnect |
| recovery transition/currentness | `TargetRuntimeSessionFactory` | checkpoint facts + injected environment reconnector | Shell manager | credential auth、conversation projection、HTTP |
| environment reconnectability | deployment composition | `BrowserGymDeploymentSessionFactory`/configured reconnector | TargetRuntimeSessionFactory | checkpoint读取、resume/revise consumption判断 |
| recovered Shell handle installation | Shell manager | authenticated recovery result + bounded conversation projection | Shell API/controller | checkpoint解释、environment恢复、Runtime replay |
| engineering analysis | benchmark export owner + diagnostics adapter | benchmark artifacts | diagnostics UI | product session status |

核心不变量：

1. Runtime authoritative fact 只公开投影一次。
2. Pydantic contract 只生成一次 schema；TS 不维护平行定义。
3. HTTP/SSE 收到的任何数据必须先通过生成 validator，之后才能进入 React state。
4. 前端不得从字段组合推导新的 command legality；它只展示 owner 发布的 command offers。
5. HTTP command accepted 只表示命令已受理；task success 只来自 Runtime completion。

命令运行时顺序固定为单向链：`manager credential/session lock → Port deployment gate → Runtime semantic admission/transition → Port wire projection`。Runtime不得回调manager/Port，Port不得在Runtime返回后再以deployment状态否定已发生的transition；这既固定lock顺序，也防止协调层形成第二控制流。

## 4. 生成代码与手写代码边界

### 4.1 必须生成

建议生成目录：

```text
external/interaction-shell/frontend/src/generated/
├── schema.ts          # DTO、closed unions、operation types
├── validators.ts      # HTTP/SSE runtime decoders
├── client.ts          # named HTTP operations；无裸 path/method/body
├── event-client.ts    # typed AG-UI/SSE envelope decoder
└── examples.ts        # 可选生成；不是协议闭合前置条件
```

必须生成的内容：

- `RuntimeSessionSnapshot`、`ShellEvent`、`ShellCommand`、`CommandAdmission`、`CommandOffer`、`SurfaceView`、diagnostics DTO；
- endpoint path、HTTP method、path/query/header/body/response 类型；
- named methods，例如 `createSession`、`getSnapshot`、`submitCommand`、`recoverSession`、`listCompletedRuns`；
- schema-version 检查和 discriminated-union decoder；
- AG-UI CustomEvent 外层 envelope 的 decoder；
- 若所选生成器支持，则生成 schema-valid examples；测试 fixture 也可由 authored typed builders 提供，但必须只 import generated types 并经 generated validator 校验。

### 4.2 可以手写

```text
frontend/src/session/session-controller.ts
frontend/src/session/command-builder.ts
frontend/src/session/view-model.ts
frontend/src/components/**
frontend/src/app/**
frontend/src/styles/**
```

手写代码只能处理已经 validate 的 domain values。允许职责：

- AbortController、连接/重连退避、React lifecycle；
- 用户正在输入但尚未提交的本地状态；
- 将 command offer 与用户输入交给受限 typed command builder，再交给 generated SDK；
- 纯函数式文案、颜色、图标、布局与可访问性投影；
- UI component composition。

手写 controller 不允许自行构造 JSON envelope，不允许持有 endpoint 字符串，也不允许使用 assertion 把 unknown 变成 domain type。

`command-builder.ts` 是唯一允许的协议邻接手写层，用于表达 OpenAPI 无法自然推导的 UI 意图转换，例如：

```text
ConfirmActionOffer + approve/reject choice → ApproveAction | RejectAction
TextCommandOffer + typed user input       → corresponding ShellCommand
one user intent + CommandIdFactory        → stable command_id
```

它必须是对 generated discriminated unions 的穷尽纯函数，不得读取 raw JSON、path、method、header，不得根据 status/capability 推导 legality，也不得生成 checkpoint/lease/interrupt refs。`command_id` 在一次用户意图建立时只生成一次并由 controller 保留；同一 transport retry 必须复用，不能每次调用 builder 重建。若新 command 无法由这条规则表达，应先扩 canonical backend schema，而不是扩大 builder authority。

### 4.3 生成器本身

优先使用一个锁版本的成熟 OpenAPI/JSON-Schema generator 同时生成 TS client 和 runtime validator。若单一工具无法覆盖 SSE/AG-UI，应保留一个很小的 repository-owned generator adapter，但它只能读取 canonical schema 并生成代码，不得在模板里重写 command/status/event 代数。

每个 FastAPI public route 必须显式固定唯一 `operation_id`；named SDK method 的稳定性由该 ID 与 schema 共同保证，不能依赖 FastAPI 自动命名或路径排序。OpenAPI 不负责推导 offer 到 command 的 UX 语义，该转换由上述受限 builder 表达，本计划不引入 custom `x-*` command metadata 或自制高级 generator。

生成器配置、版本与输入 digest 必须进入生成文件头；生成输出应 deterministic。

## 5. Canonical schema 生成流水线

目标流水线：

```text
backend Pydantic models + FastAPI operations
    │
    ├─ generate-openapi → backend/openapi.json
    ├─ generate-json-schema → backend/schemas/*.json（如 validator generator 需要）
    ▼
generate-frontend
    ├─ schema.ts
    ├─ validators.ts
    ├─ client.ts
    ├─ event-client.ts
    └─ examples.ts（可选）
```

仓库应提供单一命令，例如：

```text
npm run generate:contracts
```

该命令内部必须先从当前 Python app 重新生成 `openapi.json`，而不是信任已提交的旧文件，再生成全部 frontend artifacts。`generate:api` 只读取现存 JSON 不足以证明 backend 与 frontend 一致。

CI 使用临时目录或原地可重复生成，然后执行：

```text
git diff --exit-code -- \
  external/interaction-shell/backend/openapi.json \
  external/interaction-shell/frontend/src/generated
```

任何 schema 或 route 改动若没有提交新生成物，CI 必须失败。

## 6. 目标命令合同

### 6.1 单一 command endpoint

将多个命令 endpoint 收敛为：

```http
POST /sessions/{session_id}/commands
X-Session-Key: ...
Content-Type: application/json

ShellCommand
```

`ShellCommand`继续是闭合discriminated union。统一endpoint保留Shell manager的access gate、RuntimeSessionPort的有界deployment gate和Runtime的semantic admission，不把它们合并成一个弱类型handler或共享owner。

目标 response 保持：

```text
Accepted | Conflict | Unsupported | Rejected
```

旧 endpoint 在一个有界兼容窗口内可以调用同一个 handler，但 generated client 只暴露新 endpoint。兼容窗口结束后物理删除旧 routes，禁止长期维护两套路径。

### 6.2 `CommandOffer`：前端不再推导 command legality

`RuntimeSessionSnapshot` 新增：

```python
command_offers: tuple[CommandOffer, ...]
```

闭合代数建议：

```python
CommandOffer = Annotated[
    StartTaskOffer
    | AnswerQuestionOffer
    | ConfirmActionOffer
    | CancelTaskOffer
    | PauseTaskOffer
    | ResumeTaskOffer
    | ReviseTaskOffer
    | TakeOverOffer
    | ReturnControlOffer
    | CloseSessionOffer,
    Field(discriminator="kind"),
]
```

interaction-scoped ref只存在于对应 offer，例如：

```python
class AnswerQuestionOffer:
    kind: Literal["answer_question"]
    request_id: str
    prompt: str

class ConfirmActionOffer:
    kind: Literal["confirm_action"]
    request_id: str
    summary: str
    risk: str
```

`pending_question` 与 `pending_confirmation` 从 product snapshot删除；其 request id、prompt/summary/risk只由 `AnswerQuestionOffer`/`ConfirmActionOffer` 承载。session-scoped currentness facts仍只存在于 snapshot：`task_revision`、`run_status`、`checkpoint_id`、`control_lease_id`。`ResumeTaskOffer`、`TakeOverOffer`、`ReturnControlOffer` 只表明命令当前可用，不复制 checkpoint/lease。受限 typed command builder同时接收同一个 validated snapshot与所选offer，从 snapshot复制exact checkpoint/lease/currentness token，从interaction offer复制exact request ref，再加入用户输入。React不读取或手写这些refs。

当前设计删除没有独立 owner 和 admission 语义的 `offer_revision`。每个 snapshot中每个offer `kind` 最多出现一次；`ConfirmActionOffer` 是一个交互入口，可根据用户选择穷尽映射为 `ApproveAction` 或 `RejectAction`，但同一snapshot不得出现第二个confirmation offer。

双向完备合同以“snapshot、authenticated actor、deployment availability均未变化，且用户输入满足generated schema”为边界：

- **Legality soundness**：每个published offer经typed builder构造出的对应命令，不得因该offer发布时已经满足的legality/currentness前置条件返回`Conflict`或`Unsupported`。owner处理和durable result建立成功时返回`Accepted`；只有第6.5节闭合枚举的基础设施失败可以返回`Rejected`。因此offer保证“当前可以提交”，不承诺依赖永不失败，也不表示task success。
- **Completeness**：每个当前合法且部署支持的public command intent都有且仅有一个对应offer；Port不得遗漏合法命令，也不得为不合法命令创造offer。对confirmation，approve/reject两个互斥用户选择共享唯一`ConfirmActionOffer`。
- **Currentness**：snapshot、actor或deployment发生变化后，上述保证失效。提交顺序固定为：manager只重新鉴权并取得session lock；RuntimeSessionPort在调用Runtime前fresh-check deployment-gated capability；Runtime重新校验semantic currentness、command identity/idempotency、refs与session/control state。因此offer不是授权票据，也不取代任何owner的admission。

### 6.3 两级 owner 与纯投影边界

当前 `TargetRuntimeSession._project()` 在不同状态间合并 `BASE_PUBLIC_SESSION_CAPABILITIES`，`CoreRuntimeSessionPort._snapshot()` 又根据 Viewer 删除 `take_over/return_control`。v3 先在 Runtime owner 修正这条链：

1. `TargetRuntimeSession._project()` 只发布当前状态结构上合法的 semantic capability，并同时产生该命令所需的 exact public refs。若 capability 已发布，则除用户尚未输入的值和 deployment availability 外，所有结构性前置条件均已满足。
2. `CoreRuntimeSessionPort` 只能把 Runtime capability 与 deployment/viewer availability 做集合交集，再纯投影为 `CommandOffer`。例如 Viewer unavailable 可以抑制 `TakeOverOffer`，但 Port 不得通过重新解释 `run_status`、checkpoint 或 control owner 修复 Runtime legality。
3. 提交时manager只做credential/session access。当前v3的deployment-gated command集合闭合为`Literal["take_over"]`；`ReturnControl`永不被viewer availability阻断。对`TakeOver`，`CoreRuntimeSessionPort`必须在任何Runtime调用前读取fresh `SurfaceAvailability`，native input不可用时直接返回`Unsupported(code="deployment_capability_unavailable")`且Runtime零调用；其余semantic currentness、identity、refs与state只由Runtime重新校验。未来增加gated kind必须扩公共合同和property test，Port不得自行增加条件。offer是客户端可执行提示，不是权限、锁或admission缓存。
4. 原始 `capabilities` 不再作为 v3 product frontend 控制输入；若后端内部保留，只能用于 owner-to-port conversion 和诊断。

Runtime owner 与 Port必须共同满足上述soundness/completeness；“发布项可构造”只是结构性质，不再作为充分验收。Phase 1 必须直接修正并验证 `src/affordance_runtime/app/public_session.py` 的owner前置条件，只修改Shell Port不算闭合；端到端offer soundness/completeness随v3 schema在Phase 2验收。

当前 `start_new_task` 只存在于 Shell `Capability`/`OptionalCommand` schema，Runtime Port未发布也没有 command implementation，是幽灵命令。v3 将其从公共代数和生成物中删除；“同一 session 开新任务”仍是非目标。未来只有在 Runtime owner定义状态转换、refs、admission 与测试后才能重新加入。

### 6.4 文本输入不再按 status 猜意图

当前单一输入框根据 idle/waiting_user/revise capability 猜 Start/Answer/Revise。目标UI不再把所有文本命令竞争到同一个入口：

```text
idle + StartTaskOffer                → primary chat composer绑定Start
waiting_user + AnswerQuestionOffer   → primary chat composer只绑定Answer
ReviseTaskOffer                      → 独立“Revise task”入口/表单
ConfirmActionOffer                   → 独立confirmation dialog
无Start/Answer offer                 → primary chat composer disabled/read-only
```

因此`AnswerQuestionOffer`与`ReviseTaskOffer`可以同时存在，但不会竞争同一输入控件；React不得以条件顺序在二者之间猜意图。每个入口只由对应offer启用，offer消失时未提交的该入口必须失效并要求用户重新确认。

### 6.5 Admission 与 command business outcome 分离

v3固定以下语义：

```text
Accepted
= command在当前snapshot/identity/state下合法，并已被owner处理
= snapshot携带处理后的typed business outcome（若该command有业务结果）

Conflict
= stale/currentness mismatch
 | command identity被不同payload复用
 | checkpoint/ref mismatch或已被竞争命令消费
 | session/control state与该命令冲突
```

对`ReviseTask`，`revised | needs_input | no_change | new_task_suggested | unsupported | failed | effect_reconciliation_required`都是已处理的闭合业务结果，继续由snapshot现有`last_control_outcome`承载。因此合法revision返回：

```text
Accepted(snapshot.last_control_outcome = no_change)
```

而不是`Conflict(code = revision_no_change)`。使用相同`command_id`和相同payload重放一个已持久化的revision business outcome也返回相同的`Accepted` snapshot；只有同一identity对应不同payload才是`command_identity_reused` conflict。

`Conflict`不得再承载`revision_needs_input/revision_no_change/revision_new_task_suggested/revision_unsupported/revision_failed/effect_reconciliation_required`等业务结果。当前session/control state不允许该命令时，direct caller得到`Conflict(code="session_state_conflict" | "control_owner_conflict")`；Runtime根本不支持该命令时由Runtime outcome纯投影`Unsupported(code="command_not_supported")`；fresh deployment capability不可用时由Port在Runtime零调用前返回`Unsupported(code="deployment_capability_unavailable")`。legality soundness要求同一snapshot不得发布对应offer。无法建立持久处理结果的基础设施错误（例如revision outcome persistence失败）转换为稳定typed `Rejected`，不能伪装为业务`failed`或`Conflict`；它不写一个声称已完成处理的`last_control_outcome`。

`Accepted`仍只表示command admission/handling完成。task success唯一来自Runtime completion；controller不得因revision被Accepted或`last_control_outcome=revised`而显示任务成功。

v3同时关闭public admission code集合，不保留`code: str`或`runtime_conflict`兜底：

```python
ConflictCode = Literal[
    "stale_command",
    "command_identity_reused",
    "interaction_ref_mismatch",
    "checkpoint_mismatch",
    "checkpoint_already_consumed",
    "session_closed",
    "session_state_conflict",
    "control_owner_conflict",
    "control_lease_mismatch",
]

UnsupportedCode = Literal[
    "command_not_supported",
    "deployment_capability_unavailable",
]

RejectedCode = Literal[
    "command_processing_failed",
    "command_persistence_failed",
    "command_projection_failed",
    "internal_contract_failure",
]
```

这些是稳定public categories，不要求把每个内部异常名公开。Runtime public-session owner先把当前`run_not_active`、`run_not_revisable`、`user_control_active`等状态细节归一为`session_state_conflict`或`control_owner_conflict`；checkpoint已由resume/revise/takeover消费归一为`checkpoint_already_consumed`；request/checkpoint/lease不匹配进入对应ref/currentness code。持久化、pause boundary、restore前的处理或Shell snapshot投影失败分别进入闭合`RejectedCode`，不得进入`Conflict`。未知内部code在owner conversion边界fail closed为`internal_contract_failure`并记录diagnostic span，不得由Port降级成`runtime_conflict`或向客户端泄漏异常文本。

目标映射只有以下四类：

| owner结果 | public admission | 约束 |
| --- | --- | --- |
| currentness、identity、interaction/checkpoint ref、session/control state冲突 | `Conflict(code: ConflictCode)` | 不执行新业务处理 |
| Runtime不支持该命令 | `Unsupported(code="command_not_supported")` | Runtime outcome由Port纯投影；同一snapshot不得发布对应offer |
| fresh deployment capability不支持该命令 | `Unsupported(code="deployment_capability_unavailable")` | Port在Runtime零调用前产生；不解释Runtime status/ref/business |
| owner已处理并建立durable result，包括非正向业务结果 | `Accepted(snapshot)` | 业务结果只在owner-owned snapshot outcome中 |
| 无法安全建立durable处理结果的基础设施/owner conversion失败 | `Rejected(code: RejectedCode)` | 不伪造业务结果；不泄漏exception text |

同一command identity与相同payload已经存在durable result时重放原public admission和snapshot；不同payload复用identity固定为`command_identity_reused`。Phase 0先建立现有内部code到上述四类的穷尽清单；Phase 1在Runtime public boundary实现闭合conversion，Phase 2删除Shell Port现有`runtime_conflict`fallback并原子公开generated v3 code unions。

## 7. 目标事件合同

### 7.1 删除 untyped `data`

第一版只需要 owner snapshot 更新时，采用最小闭合事件：

```python
class SnapshotUpdated(StrictModel):
    schema_version: Literal["interaction-shell.v3"]
    type: Literal["snapshot.updated"]
    session_id: str
    event_epoch: str
    cursor: int
    emitted_at: datetime
    snapshot: RuntimeSessionSnapshot
```

若有明确第二类 public event，再扩为 union：

```python
ShellEvent = Annotated[
    SnapshotUpdated | SessionClosed | TransportNotice,
    Field(discriminator="type"),
]
```

不要为可能的未来事件预留 `dict[str, object]`。unsupported schema version、unknown event type、AG-UI/event strict schema violation统一转换为terminal `protocol_mismatch`；不得用snapshot resync掩盖部署或协议不兼容。

### 7.2 AG-UI 只是 transport

后端负责：

```text
typed ShellEvent
→ AG-UI CustomEvent encoder
→ SSE bytes
```

generated event client 负责：

```text
SSE bytes
→ AG-UI envelope validator
→ ShellEvent validator
→ typed ShellEvent
```

authored controller 只接收 `ShellEvent`，不得 `JSON.parse`、读取 `value` 或 cast `snapshot`。

### 7.3 cursor 与 epoch

- cursor 在一个 epoch 内严格递增；重复 cursor 幂等忽略；跳号先 resync snapshot，再重连。
- epoch 改变不是普通下一事件；必须停止旧 stream 并执行 typed resync。
- snapshot 的 `event_cursor` 必须不小于承载它的事件 cursor。
- transport disconnect、cursor gap、epoch mismatch每个incident最多执行一次bounded snapshot resync；resync成功后才能按新cursor/epoch重连，失败进入typed connection unavailable，不循环调用recover。
- unsupported schema version、unknown event type或strict schema violation必须停止stream，进入terminal `protocol_mismatch`；不resync、不recover、不自动重连。
- 任何失败都不得部分更新React state。snapshot resync response本身若schema/version不兼容，同样进入terminal `protocol_mismatch`。

## 8. 通用 Surface 展示合同

将浏览器专属 `ViewerState` 替换为闭合 union：

```python
SurfaceView = Annotated[
    UnavailableSurface | ReadOnlySurface | InteractiveSurface,
    Field(discriminator="status"),
]

class UnavailableSurface(StrictModel):
    status: Literal["unavailable"]
    reason_code: str

class ReadOnlySurface(StrictModel):
    status: Literal["read_only"]
    surface_kind: Literal["web", "mobile", "desktop", "generic"]
    presentation: Literal["live_media", "snapshot"]
    protected_path: str

class InteractiveSurface(StrictModel):
    status: Literal["interactive"]
    surface_kind: Literal["web", "mobile", "desktop", "generic"]
    presentation: Literal["live_media"]
    protected_path: str
    input_mode: Literal["native"]
```

`control_owner` 与 `control_lease_id` 只保留在 product session snapshot，`SurfaceView` 不复制这两个 authoritative facts。这里固定唯一转换边界，避免Steel projector与Core Port各做一次read-only/interactive判断：

```python
SurfaceAvailability = Annotated[
    SurfaceChannelUnavailable | SurfaceChannelAvailable,
    Field(discriminator="kind"),
]

class SurfaceChannelUnavailable(StrictModel):
    kind: Literal["unavailable"]
    reason_code: str

class SurfaceChannelAvailable(StrictModel):
    kind: Literal["available"]
    surface_kind: Literal["web", "mobile", "desktop", "generic"]
    presentation: Literal["live_media", "snapshot"]
    protected_path: str
    input_mode: Literal["native"] | None
```

这个内部代数不含provider、control owner或lease。`input_mode=None`只表示deployment没有native input channel，不表示当前agent/user控制状态；`input_mode="native"`也不授权输入。

```text
deployment viewer projector
→ provider-neutral SurfaceAvailability
   （unavailable，或available + surface_kind/presentation/protected_path/input_mode）

CoreRuntimeSessionPort
→ exact SurfaceAvailability × Runtime control_owner/control_lease_id
→ 唯一一次 SurfaceView composition

Pydantic cross-model validator
→ 只验证组合结果，不修复、不重新投影
```

deployment projector不能直接产生`ReadOnlySurface`/`InteractiveSurface`，也不能读取、产生或持有control lease。`CoreRuntimeSessionPort`不能解释provider状态，只能执行上述闭合纯转换：unavailable映射`UnavailableSurface`；available+agent owner映射`ReadOnlySurface`；只有available+input-capable+user owner+非空exact lease才映射`InteractiveSurface`，其余组合fail closed为typed unavailable/contract failure。snapshot validator再保证：`InteractiveSurface`只可与`control_owner=user`且非空exact`control_lease_id`同时出现。

不进入公共合同的字段：

- Steel、Browserbase、Appium、Android streaming 等 provider 名称；
- provider session ID、WHEP/ICE/WebSocket locator；
- credential、CDP URL、device serial；
- selector、coordinate、private action binding。

展示 invariant：

- Agent control 时只能是 read-only/unavailable；
- user/native control 时 exact opaque lease只从 session snapshot读取，且必须与 `InteractiveSurface` 的 cross-model invariant一致；
- unavailable variant在类型上没有 protected path/input；
- protected path 必须 same-origin、secret-free；
- iframe/video/image 等具体 renderer 由 `presentation` 选择，不由 provider 选择。

`SurfaceAvailability`只是一次调用内的provider-neutral conversion input，不进入snapshot、不持久化、不发布给前端，也不是第二状态。Steel/local adapter只能生产它；公开`SurfaceView`只由`CoreRuntimeSessionPort`产生一次。

UI 文案从 `surface_kind` 投影为 Web/Mobile/Desktop/Live Surface，不再硬编码 Browser。Surface Module 不发布 React component；Shell 只维护少量闭合 presentation renderer。

## 9. Product Snapshot 与 Diagnostics 分离

### 9.1 Product snapshot

只保留操作任务所需的公开事实：

```text
session/task identity
task revision/text
run status
completion
command offers（包含pending question/confirmation presentation）
public progress
surface view
control ownership
event epoch/cursor
expiry
```

移除：

```text
completed_analysis
benchmark_result/status
provider tokens/cost/latency analysis
Langfuse URL
local benchmark evidence URL
detour/stall/oscillation analysis
```

### 9.2 Diagnostics

Diagnostics 使用独立 schema version 与 client namespace：

```text
GET /diagnostics/runs
GET /diagnostics/runs/{locator}
```

Shell 不直接理解 `run.json`、`cases/*.json`、`analysis/*.json` 或 benchmark metric keys。目标 producer 是 benchmark owner 生成的 versioned summary export；Shell diagnostics adapter 只校验并提供 allowlisted locator/deep link。

迁移期间现有 `CompletedRunSummaryResolver` 明确标记 transitional；不得继续增加新的 artifact/metric 特例。Diagnostics failure 不影响 product session、command acknowledgement 或 task completion。

## 10. Session controller 与 ViewModel

### 10.1 `session-controller.ts`

唯一职责：

- 通过 generated SDK 创建/读取 session；
- 持有 session credential 的当前浏览器内存引用；
- 启停 generated event stream；
- 处理 AbortController、退避和 connection presentation state；
- 将 validated snapshot 原子提交给 UI store；
- 将 command offer + 用户输入交给 generated SDK；
- 渲染 typed admission notice。

不允许：

- 根据 Runtime status 推导 command legality；
- 构造 command JSON；
- 解析 AG-UI/SSE JSON；
- 把 HTTP 2xx 当作 task success；
- 在 event failure 后自行决定 Runtime recovery。

### 10.2 `view-model.ts`

一个纯函数：

```ts
deriveShellViewModel(snapshot: Snapshot): ShellViewModel
```

它只做 presentation：

- command offer → button/input/dialog model；
- run status → badge tone/text；
- surface kind/presentation → renderer model；
- completion/effect reconciliation → display card；
- public progress → ordered presentation rows。

所有组件消费 `ShellViewModel` 和 typed controller callbacks，不直接读取 raw snapshot 的 status/capability/checkpoint 组合。相同控件可见性判断只能存在一次。

## 11. Recovery 与 transport 重连

目标顺序：

```text
SSE transport disconnect/cursor gap/epoch mismatch
→ generated GET snapshot/resync operation
→ LiveSession(snapshot): update cursor and reconnect
→ RecoveryRequired(checkpoint ref): invoke generated recover operation once
→ typed terminal lookup outcome: stop and present exact cause

unsupported schema version/unknown event type/strict schema violation
→ terminal protocol_mismatch
→ no resync / no recover / no reconnect
```

Recovery在auth/session access、checkpoint inspection、Runtime recover transition和Shell handle installation四个已命名边界分别使用闭合结果；不把它们压成一个union，也不让任何协调层接管其他边界的事实。

鉴权顺序必须以live handle是否存在分流，不能要求正常live deployment配置recovery registry：

```text
live handle存在
→ 使用ManagedSession持有的live session credential鉴权
→ LiveSession

live handle不存在
→ recovery registry存在时使用其鉴权/TTL检查；不存在则RecoveryUnsupported
→ Runtime recovery inspector
→ RecoveryRequired | RecoveryUnavailable | RecoveryUnsupported | RecoveryInspectionFailed
```

live credential mismatch是`Unauthorized`；live session过期是`SessionExpired`。只有live handle不存在且registry存在时才使用registry的闭合鉴权代数：

```python
RecoveryAuthentication = Authenticated | Unauthorized | SessionExpired
```

`Unauthorized`与`SessionExpired`分别稳定映射HTTP 401与410；只有`Authenticated`才进入Runtime inspection。handle缺失且registry未配置时直接返回`RecoveryUnsupported(reason_code="recovery_registry_unavailable")`，不伪装成鉴权失败。Shell registry仍只拥有credential verifier、TTL与bounded conversation projection，不得新增checkpoint id、payload、resume eligibility或environment reconnectability列。

Recovery不设一个包揽全部事实的“总owner”。底层事实与唯一转换边界固定为：live handle存在时`TargetRuntimeSession`独占当前checkpoint ref/currentness；live handle缺失时`RuntimeCheckpointStore`独占durable checkpoint record/consumption truth，deployment composition独占是否提供exact environment reconnector，`TargetRuntimeSessionFactory`独占把store事实与注入的reconnector availability组合成inspection结果以及执行recover transition/currentness；Shell manager只拥有credential、bounded conversation projection和恢复后live handle installation。Phase 1在`affordance_runtime.app.public_session`边界增加read-only typed port，例如：

```python
class PublicRuntimeRecoveryInspector(Protocol):
    async def inspect(self, session_id: str) -> RuntimeRecoveryInspection: ...

RuntimeRecoveryInspection = Annotated[
    RecoverableCheckpoint
    | RecoveryInspectionUnavailable
    | RecoveryInspectionUnsupported
    | RecoveryInspectionFailed,
    Field(discriminator="kind"),
]
```

- `RecoverableCheckpoint` 只公开 exact `checkpoint_id`；它只能由`TargetRuntimeSessionFactory.inspect()`对store事实与已注入reconnector availability做一次组合后产生，表示checkpoint存在、未被resume/revise消费、`resume_eligible`、environment reference和reconnector均可用。
- `RecoveryInspectionUnavailable` 表示没有可恢复checkpoint或checkpoint已消费/失效；manager纯映射为public `RecoveryUnavailable`。
- `RecoveryInspectionUnsupported` 表示该deployment没有checkpoint store/reconnector能力；manager纯映射为public `RecoveryUnsupported`。
- `RecoveryInspectionFailed` 表示checkpoint store读取或authoritative record校验失败；它只携带稳定的public `reason_code="checkpoint_inspection_failed"` 与可选retryability，不暴露异常文本、store路径或payload。

inspector的唯一conversion owner是`TargetRuntimeSessionFactory`：store只返回authoritative records，deployment只注入reconnector或明确不支持，二者都不单独发布`RecoveryRequired`。Inspector只读检查，不恢复环境、不创建session。checkpoint store异常在factory边界转换成`RecoveryInspectionFailed`，不得由deployment或manager解析exception字符串。Shell manager按上述live-first顺序分流；只有live handle缺失且recovery registry鉴权通过时调用inspector并把其typed结果纯映射为公共闭合结果：

```python
AuthenticatedSessionLookup = Annotated[
    LiveSession
    | RecoveryRequired
    | RecoveryUnavailable
    | RecoveryUnsupported
    | RecoveryInspectionFailed,
    Field(discriminator="kind"),
]
```

`RecoveryRequired`只能由manager对factory产出的`RecoverableCheckpoint`做一对一纯映射产生；factory不产生Shell public lookup variant，manager也不得从snapshot/registry重建recoverability。`RecoveryInspectionFailed`是typed lookup结果，不自动调用recover；retryable与否只控制显式用户重试提示，不能开启循环重连。普通网络断开、页面隐藏或代理重置在live handle存在且credential有效时只返回`LiveSession`。恢复调用仍由`TargetRuntimeSessionFactory.recover()`做最终durable currentness检查；inspection不是reservation。

删除未定义的 `recovery_epoch`。每个 controller生命周期内，对 exact `(session_id, checkpoint_id)` 最多尝试一次自动 recovery；transport retry复用同一次 recovery intent，不循环创建。恢复成功后由新 snapshot 的既有 `event_epoch` 隔离旧 stream；失败后显示 typed outcome并等待显式用户动作。checkpoint consumption/idempotency truth仍由`RuntimeCheckpointStore`负责。

### 11.1 实际 recovery attempt 结果

Inspection只是一致性检查，不是reservation；从`RecoveryRequired`到真正调用recover之间允许checkpoint被消费/修订，store、factory、reconnector或restore也可能失败。通过live/recovery credential鉴权后，v3 `/recover` 必须返回闭合、generated-validator可验证的结果：

```python
RecoveryAttempt = Annotated[
    Recovered
    | RecoveryConflict
    | RecoveryUnavailable
    | RecoveryFailed,
    Field(discriminator="kind"),
]

class Recovered(StrictModel):
    kind: Literal["recovered"]
    snapshot: RuntimeSessionSnapshot

class RecoveryConflict(StrictModel):
    kind: Literal["recovery_conflict"]
    reason_code: Literal[
        "checkpoint_already_resumed",
        "checkpoint_already_revised",
        "checkpoint_mismatch",
    ]
    retryable: Literal[False]

class RecoveryUnavailable(StrictModel):
    kind: Literal["recovery_unavailable"]
    reason_code: Literal[
        "checkpoint_not_found",
        "checkpoint_unavailable",
        "recovery_unsupported",
        "environment_not_reconnectable",
    ]
    retryable: Literal[False]

class RecoveryFailed(StrictModel):
    kind: Literal["recovery_failed"]
    reason_code: Literal[
        "checkpoint_store_failed",
        "runtime_factory_failed",
        "environment_reconnect_failed",
        "session_restore_failed",
        "shell_projection_restore_failed",
    ]
    retryable: bool
```

实际attempt同样按边界组合而不共享authority。live handle存在时，manager只鉴权并把exact checkpoint ref交给RuntimeSessionPort；Port调用`TargetRuntimeSession`的typed live-checkpoint admission，由live Runtime独占比较当前paused/resume eligibility/exact ref并返回snapshot或`checkpoint_mismatch`，manager不得读取snapshot字段自行比较。live handle缺失时，`RuntimeCheckpointStore`给出record/consumption事实，deployment-injected reconnector只负责恢复exact environment或返回typed reconnect failure，`TargetRuntimeSessionFactory.recover()`独占durable recovery transition/currentness并把store、reconnector、Runtime factory与session restore阶段穷尽转换为typed internal attempt。Shell manager只负责鉴权、bounded conversation projection、并发单handle安装和`shell_projection_restore_failed`，不产生checkpoint消费/currentness事实或解释environment失败；API只把结果编码成`RecoveryAttempt`。API不得再将这些supported outcomes转换为带exception字符串的409/503 detail。鉴权失败继续使用第11节既有401/410 typed auth边界，request schema错误仍为422；通过鉴权后的所有受支持recover结果均返回`RecoveryAttempt`。

通过鉴权的domain attempt统一以HTTP 200承载union；客户端不得根据409/503猜variant。`RecoveryUnavailable.retryable`固定为false。`RecoveryFailed.retryable=true`只有在owner确认没有安装新live handle、checkpoint未被消费、partial environment已清理且同一checkpoint显式重放安全时才允许；任何未知或无法证明的partial state都必须是false。

`Recovered`是唯一允许controller安装新snapshot并重连stream的variant。其余三个variant都立即停止本次自动恢复：`retryable`只控制是否展示显式用户重试入口，不允许controller自动再次调用recover。attempt结果比先前inspection更权威；二者不一致时不得回退使用旧`RecoveryRequired`。

## 12. 版本与兼容策略

该治理涉及 breaking public contract，目标 schema version 应从 `interaction-shell.v2` 提升到 `interaction-shell.v3`，而不是在 v2 中静默改变 event/snapshot 形状。

兼容原则：

1. Phase 2的原子变更可以在feature branch中暂时让v2 routes与v3 `/commands` 共用一个handler，以便迁移测试；这不是一个可长期部署或独立验收的阶段。
2. 新 frontend 只生成/消费 v3，不在运行时同时支持两个 schema。
3. v2 event 不转换成 v3 event；部署与回滚都以旧或新 frontend/backend镜像成对进行。
4. unknown schema version 明确拒绝并提示部署不匹配，不做字段猜测。
5. v3 E2E通过后进入紧邻的Phase 3并物理删除旧routes/models/tests；不设按日历延长的compatibility window。

不建立长期双栈 adapter、任意版本 registry 或 generic migration framework。

## 13. 安全与数据边界

生成合同不能削弱现有安全不变量：

- session key 保持 header/cookie 私有，不进入 snapshot、event、日志或 generated fixture；
- protected surface path same-origin 且 secret-free；
- private provider locator、credential、World、selector、coordinate、binding、hidden reasoning 均不得进入 schema；
- generated validator 必须 `additionalProperties: false`/等价 strict behavior，未知字段 fail；
- command offer不是权限token；manager只重验credential/session access，Port在Runtime调用前重验deployment-gated capability，Runtime独占exact revision/status/ref/identity语义校验；
- user control input继续逐帧验证 exact current Runtime lease；
- diagnostics engineering evidence 与 product session credential 分离；
- generation logs不得打印 secret-bearing environment 或 example payload。

为防止嵌套泄漏，不只维护字段名 denylist；应对每个 public model采用 allowlisted typed fields，并对序列化结果保留现有 private-field property test。

## 14. 目录目标

```text
external/interaction-shell/
├── backend/
│   ├── interaction_shell/
│   │   ├── contracts/
│   │   │   ├── session.py
│   │   │   ├── commands.py
│   │   │   ├── events.py
│   │   │   ├── surface_view.py
│   │   │   └── diagnostics.py
│   │   ├── api.py
│   │   ├── core_runtime_port.py
│   │   ├── manager.py
│   │   └── ...
│   ├── openapi.json                 # generated
│   └── schemas/                     # generated when needed
└── frontend/
    └── src/
        ├── generated/               # generated only
        ├── session/
        │   ├── session-controller.ts
        │   └── view-model.ts
        ├── components/
        └── app/
```

`contracts.py` 是否立即拆目录不是前置条件。先闭合合同和生成流水线，再按 owner 移动；不能把“拆文件”当成完成治理。

## 15. CI 与静态治理门

### 15.1 必跑门

```text
backend contract tests
backend external-isolation tests
OpenAPI/schema deterministic regeneration
frontend generated SDK/validator regeneration
generated diff clean
frontend lint
frontend typecheck
frontend unit tests
frontend production build
provider-free API + SSE integration test
Playwright E2E synthetic profile
```

### 15.2 禁止模式

在 authored frontend source 中禁止：

```text
fetch( / axios / raw XMLHttpRequest
硬编码 /sessions、/commands、/diagnostics endpoint
Record<string, unknown> 作为 API body
as Snapshot / as ShellEvent / as CommandAdmission
业务代码 JSON.parse HTTP/SSE payload
手写 interface/type 镜像 backend schema
手写 AG-UI CustomEvent shape
组件直接组合 run_status + capabilities + checkpoint/lease
product snapshot 使用 benchmark_result/provider token analysis
```

允许 raw transport 的目录只能是 generated client 或一个经过审查的 generic transport runtime；generic runtime 不含 endpoint/domain field 名称。

建议用 ESLint restricted syntax/import、architecture test 与负向 `rg` gate 组合，而不是依赖 code review 记忆。每个禁止门应有一个故意违规的 gate test，证明规则确实能失败。

### 15.3 后端边界门

- 外部 Shell 普通模块仍只能 import `affordance_runtime.app.public_session`；deployment composition是唯一例外。
- Shell API/manager不得 import BrowserGym/Android/desktop；本计划不改造当前单平台 deployment composition。
- Surface Module 不提供前端 DTO、event 或 React renderer。
- Diagnostics adapter 不 import Core/World/ActionPolicy，也不重建 task outcome。

## 16. 测试设计

### 16.1 Schema/codegen

- 相同 backend revision 两次生成 byte-for-byte 相同。
- 所有 command/event/offer union variant进入 OpenAPI discriminator。
- generated client 能为每个 operation编译一个调用 witness。
- 每个 public route 的显式 `operation_id` 唯一、稳定，并生成预期 named method。
- backend schema变化而 generated output未更新时 CI 失败。
- unknown version、event type、extra private field被 runtime validator 拒绝。

### 16.2 Command offer

- Runtime capability在每个public session状态下都是precondition-complete；Port只做deployment availability交集，不重新解释状态。
- state-machine/property test覆盖双向合同：在snapshot/actor/deployment不变且输入schema合法时，每个offer构造的命令不得因已发布前置条件返回Conflict/Unsupported；owner处理与durable result成功时为Accepted，注入闭合基础设施故障时只为Rejected。每个合法且支持的command intent恰有一个offer。
- 每个offer kind最多一个；confirmation的approve/reject共享一个`ConfirmActionOffer`。
- question/confirmation refs只存在于interaction offer；checkpoint/lease只存在于snapshot；builder只能从同一validated snapshot+offer复制。
- 没有 offer时组件不能发送该 command。
- stale offer若因Runtime state/ref变化，由Runtime返回typed Conflict；若因deployment capability变化，由Port在Runtime零调用前返回typed Unsupported。manager不解释二者。
- waiting_user时primary composer只绑定Answer；Revise始终使用独立入口，即使两个offer同时存在也不靠优先级猜意图。
- accepted admission不会直接产生 completion UI，除非 returned snapshot含 Runtime completion。
- revision的`needs_input/no_change/new_task_suggested/unsupported/failed/effect_reconciliation_required`均返回Accepted并保留exact `last_control_outcome`；这些code不得出现在Conflict。
- 相同revision command identity+payload重放返回相同Accepted outcome；identity+不同payload返回Conflict。
- revision persistence无法建立durable outcome时返回typed Rejected，不返回Conflict或伪造business failed。
- 生成式全命令outcome test证明每个Runtime/Shell owner result恰好映射到一个closed `Accepted | Conflict | Unsupported | Rejected` variant；`ConflictCode | UnsupportedCode | RejectedCode`无开放字符串，未知内部code只成为`Rejected(internal_contract_failure)`并产生diagnostic evidence。
- owner-boundary test证明manager只做auth/session lock，Runtime独占semantic admission/currentness/idempotency，Port除对typed Runtime outcome做穷尽纯转换外，只能在Runtime零调用前检查deployment-gated capability；manager/Port中不存在Runtime status/ref legality或business-outcome重算。
- deployment race test在offer发布后撤销native input capability，证明Port fresh-check返回`Unsupported(deployment_capability_unavailable)`、Runtime调用次数为零；capability可用时Port不得替代Runtime semantic admission。
- 当前deployment-gated kind集合exact为`take_over`；`return_control`在viewer unavailable时仍可到达Runtime。lock/call-order witness证明manager→Port→Runtime单向调用且无Runtime反向回调或Port事后否定transition。
- v3 command/capability union不含未实现的 `start_new_task`。

### 16.3 Event/currentness

- duplicate cursor幂等；gap/epoch mismatch触发 resync，不部分更新。
- unsupported version、unknown type、strict schema violation进入terminal `protocol_mismatch`，不resync/recover/reconnect，也不进入React domain state。
- SSE transient failure先 snapshot resync，不调用 Runtime recover。
- 只有 typed `RecoveryRequired` 能触发一次 exact checkpoint recovery。
- live handle存在时无需recovery registry即可凭live credential resync；只有handle缺失才访问registry和inspector。
- checkpoint store读取/校验异常产生typed `RecoveryInspectionFailed`，不泄漏exception text且不调用recover。
- recovery owner test证明store只产出record/consumption facts、deployment只注入reconnector、Target factory独占absent-handle inspection/recover transition、TargetRuntimeSession独占live-handle checkpoint admission；registry/manager/deployment均不能产生或缓存checkpoint currentness。
- inspection后checkpoint被resume/revise消费分别产生typed `RecoveryConflict`；not found/unsupported/not reconnectable产生`RecoveryUnavailable`。
- actual recover的store/runtime factory/reconnector/session restore/shell projection错误分别进入稳定`RecoveryFailed.reason_code`，API response不含exception detail。
- 只有`Recovered`安装snapshot；所有非Recovered attempt停止自动恢复，retryable只允许显式用户动作。
- old epoch/old control lease不能恢复 viewer input。

### 16.4 Surface view

- web/mobile/desktop/generic 使用同一 renderer contract测试。
- Agent ownership始终无 native input。
- unavailable view在类型上无 path/input；所有 SurfaceView variant都不含owner/lease。
- InteractiveSurface与session snapshot的user owner/exact lease满足cross-model invariant。
- Steel/local projector只产出非持久化`SurfaceAvailability`；只有CoreRuntimeSessionPort可组合公开`SurfaceView`，且validator不修复无效组合。
- public values不含 provider session/credential/selector/coordinate。

### 16.5 Diagnostics isolation

- product snapshot schema不含 benchmark analysis字段。
- diagnostics unavailable不改变 product connection/run status。
- malformed/unknown benchmark export只让对应 summary unavailable，不猜测指标。
- evidence locator保持 allowlisted path和独立 engineering authorization。

## 17. 迁移计划

### Phase 0：冻结基线并选择生成器

范围：只增加或整理测试，不改协议行为。

- 保留当前 13 个 frontend unit tests与16个 external isolation/contract tests基线。
- 选择并锁定能够生成 named client、DTO、runtime validator的工具链；用当前app验证一条HTTP operation与一个typed event witness。
- 为所有public routes固定显式唯一 `operation_id`，增加当前 OpenAPI generation reproducibility witness。
- 增加负向搜索清单，记录现有 raw fetch/cast/path/status inference作为待消除债务；同时建立所有现有Runtime/Shell command outcome code到第6.5节四类v3 admission结果的穷尽迁移清单。

退出条件：所有当前协议 producer/consumer被测试或静态清单覆盖；生成器选择已用可运行witness证明，而不是设计假设。当前typecheck/13 frontend tests/16 backend tests只记为v2 baseline。

### Phase 1：修正 Runtime capability 与 recovery owner

- 在 `src/affordance_runtime/app/public_session.py` 建立未公开的v3 semantic capability/ref projection，使每个状态下的capability precondition-complete并产生exact public refs；现有v2 adapter继续发布v2 schema，不提前发布`CommandOffer`。
- 在Runtime public boundary实现第6.5节的闭合owner result conversion；Phase 1测试直接验证该内部v3 port。v2 adapter继续保持既有response shape和兼容行为，不在本阶段切换revision/recover公共语义。
- 增加由`TargetRuntimeSessionFactory`唯一实现的read-only`PublicRuntimeRecoveryInspector`；它只消费`RuntimeCheckpointStore`事实与deployment注入的reconnector availability。Store不实现inspector，Shell registry schema保持不含checkpoint truth。
- 让现有具体composition `BrowserGymDeploymentSessionFactory` 构造并委托同一个`TargetRuntimeSessionFactory`：只注入checkpoint store与exact environment reconnector（或明确不提供），所有inspect/recover判断仍由Target factory完成。BrowserGym composition不得自行读取checkpoint或映射consumption/currentness；`runtime_app.py`只注入组合后的public factory/inspector。
- 闭合Runtime-owned recovery inspection outcome；它仍是未公开的typed owner port，不在Phase 1增加Shell lookup、`CommandOffer`或v3 HTTP mapping。
- 从v3目标代数删除 `start_new_task`，并删除 `offer_revision` 设想。

退出条件：Runtime state/property tests证明semantic capability前置条件、canonical ref owner、闭合admission conversion和inspection owner；inspection owner覆盖missing/consumed/revised/unreconnectable/unsupported/inspection-failed；Shell DB schema负向证明不含checkpoint truth。v2 compatibility tests证明外部schema、routes和response algebra未切换；若新的v3 capability语义会改变v2 observable projection，则只保留在未公开port中直到Phase 2。Phase 1不单独部署，也不宣称v3 Shell可运行。

### Phase 2：v3 schema、生成物与 frontend 原子切换

- 在一个不可拆分的merge unit中让`CoreRuntimeSessionPort`把Phase 1的Runtime capability与deployment/viewer availability做纯交集并投影`CommandOffer`，同时成为deployment-gated command的唯一提交前fresh gate；同批新增typed event、闭合`SurfaceView`、product/diagnostics分离、typed live-first lookup和统一`/commands`。
- 同一merge unit公开闭合`ConflictCode | UnsupportedCode | RejectedCode`，删除`runtime_conflict`fallback，切换revision admission/business outcome语义，并公开`Recovered | RecoveryConflict | RecoveryUnavailable | RecoveryFailed` attempt；删除revision business result→Conflict及supported recovery failure→HTTP exception detail旁路。
- 同一merge unit组合live credential、recovery registry authentication、Runtime inspection与HTTP mapping；只有handle缺失才进入registry和inspection，Phase 1的owner inspection不直接暴露为第二条public route。
- 从当前 FastAPI app deterministic生成 OpenAPI，再生成 TS DTO、named client、runtime validators与event decoder；examples/fixtures可选。
- 同一merge unit迁移受限 typed command builder、session controller、view model和React components；删除raw path/body/cast/status legality。
- 建立regenerate-and-diff、contract/integration、frontend build与provider-free E2E gates。

退出条件：整组变更作为一个v3 frontend/backend deployment可运行；offer legality soundness/completeness与kind/ref唯一性通过；deployment capability竞态由Port在Runtime零调用前返回typed Unsupported；全命令结果穷尽映射到闭合public admission code unions，基础设施故障不进入Conflict，revision每个business outcome满足Accepted+`last_control_outcome`；actual recovery覆盖live exact-ref mismatch及absent-handle consumed/revised/missing/unreconnectable、store/runtime/reconnector/restore failures，并证明只有Recovered安装snapshot；OpenAPI完整包含全部discriminators；禁止模式扫描清零；旧v2 baseline flows在v3 provider-free integration/E2E通过。允许在feature branch中分subcommit实现，但任何中间状态不得合入、部署或宣称可运行。

### Phase 3：E2E 后立即删除 v2

- 在v3成对部署的provider-free API/SSE与Playwright E2E通过后，立即移除旧command endpoints、v2 models、旧generated file和compatibility tests。
- 更新 `docs/interaction-shell.md` 当前实施状态与证据；部署回滚按旧frontend/backend镜像成对回滚，不保留运行时长期双栈。

退出条件：仓库只有一个当前Shell contract版本，且实现、生成物、测试、文档一致。

### Phase 4：Diagnostics 接 benchmark-owned export

状态：**blocked dependency，不阻塞Phase 0–3**。

当前worktree中既有的 `interaction-shell.completed-run.v1` / `CompletedRunSummaryResolver` 属于Phase 10的
transitional artifact-layout reader：它不是benchmark owner发布的canonical export，也不构成本Phase 4实现或
closure。Phase 0–3只让该既有独立route经过同一OpenAPI生成链，未把其schema、字段或解析规则提升为benchmark
authority；它必须在下述producer合同出现后迁移或删除。

本文件不是benchmark export authority，因此不臆造summary字段、schema ID或artifact路径。Phase 4只有在benchmark owner于`docs/benchmark.md`及其owned schema中发布以下完整producer合同后才能进入implementation：

- versioned completed-run summary的canonical model/schema ID与closed field algebra；
- 唯一稳定的读取边界（API或artifact路径/layout）及currentness/atomic publication语义；
- unavailable、partial、unknown-version与malformed export的typed outcomes；
- producer contract/property tests与至少一个真实benchmark export witness。

解阻后的consumer工作：

- 复用Phase 2已经建立的product/diagnostics隔离，不再修改product snapshot或completion UI合同。
- Diagnostics只消费benchmark-owned versioned summary export。
- `CompletedRunSummaryResolver`停止新增文件布局/metric特例并在export可用后删除旧解析路径。

解阻条件：上述producer合同与witness存在且被benchmark owner声明为当前支持范围。退出条件：product snapshot与diagnostics schema/import测试证明隔离，Shell只消费该versioned export且不重建metric/file-layout语义。

AndroidWorld、OSWorld 与通用 deployment composition 不属于本治理计划。`SurfaceView` 保持平台中性的目的，是不阻塞未来真实第二平台；只有第二平台接入产生证据后，才由独立 Surface Module/composition计划处理 profile注入和平台验收。

## 18. 变更面

| 当前文件 | 目标变更 | Owner |
| --- | --- | --- |
| `src/affordance_runtime/app/public_session.py` | state-correct capabilities/refs；全命令semantic admission与闭合v3 conversion；live exact-checkpoint admission；revision business outcome；`TargetRuntimeSessionFactory` absent-handle inspection/recover transition | Runtime semantic/recovery transition owner |
| `src/affordance_runtime/app/checkpoint.py` | 为recovery inspection提供authoritative只读事实；不向Shell复制payload | Runtime checkpoint owner |
| `src/affordance_runtime/app/__init__.py` | 只导出目标public-session typed ports/models；不暴露checkpoint payload或内部Runtime类型 | Runtime public API boundary |
| `backend/interaction_shell/contracts.py` | v3 snapshot/offer/event/surface/recovery及闭合admission code合同 | Shell contract |
| `backend/interaction_shell/port.py` | 将session/recovery port签名切换到v3 closed lookup/attempt/admission合同 | Shell port boundary |
| `backend/interaction_shell/viewer.py` | 定义不含provider/control facts的内部闭合`SurfaceAvailability`代数 | Surface adapter boundary contract |
| `backend/interaction_shell/core_runtime_port.py` | capability纯交集、offers/events/admission投影；deployment-gated command提交前fresh gate；唯一执行`SurfaceAvailability × Runtime control facts → SurfaceView`；删除`runtime_conflict`fallback | RuntimeSessionPort conversion/deployment-gate owner |
| `backend/interaction_shell/demo_port.py`、`unavailable_port.py` | 穷尽实现同一v3 port代数；不得保留弱类型或exception-detail旁路 | Synthetic/unavailable adapters |
| `backend/interaction_shell/session_registry.py` | 只保留auth/TTL/conversation；明确不存checkpoint truth | Shell auth/projection owner |
| `backend/interaction_shell/manager.py` | session auth/lock、live-first lookup、conversation projection及恢复后单handle安装；不解释Runtime/deployment结果 | Shell resource manager |
| `backend/interaction_shell/api.py` | 单一commands、typed lookup/recovery attempt、AG-UI encoder | HTTP/event transport |
| `backend/interaction_shell/runtime_app.py` | 注入组合后的public session factory/inspector，不解析checkpoint或deployment语义 | ASGI composition boundary |
| `backend/interaction_shell/deployment_app.py` | 让`BrowserGymDeploymentSessionFactory`向同一Target factory注入store/reconnector并委托inspect/recover；保持local non-reconnectable typed outcome | Deployment composition |
| `backend/interaction_shell/steel_viewer.py` | 从Steel私有lease只投影一次调用内的provider-neutral`SurfaceAvailability`；不得产生`SurfaceView`或读取control facts | Deployment-private availability producer |
| `backend/openapi.json` | 当前 app deterministic生成 | generated artifact |
| `frontend/src/generated/**` | DTO/client/validators/events；examples可选 | generated artifacts |
| `frontend/package.json`、`package-lock.json` | 锁定OpenAPI/client/runtime-validator生成器及单一`generate:contracts`/regenerate-and-diff命令 | Frontend build contract |
| `frontend/eslint.config.mjs` | 加入raw fetch/path/body/cast/status推导等禁止模式 | Frontend static gate |
| `external/interaction-shell/frontend/src/lib/api.ts` | 删除或generated re-export | 不再有手写 transport |
| `external/interaction-shell/frontend/src/lib/types.ts` | 删除手写公共DTO；仅保留generated re-export或纯本地UI类型 | Frontend local type boundary |
| `frontend/src/session/command-builder.ts` | offer+typed input到command的唯一穷尽纯转换 | authored typed UX conversion |
| `frontend/src/hooks/use-shell-session.ts` | 迁移为typed controller | frontend session owner |
| `frontend/src/components/shell-app.tsx` | 只消费view model；generic surface labels | presentation |
| `frontend/src/components/diagnostics-workbench.tsx` | 独立diagnostics client/schema | engineering presentation |
| `backend/interaction_shell/completed_runs.py` | 过渡到benchmark-owned summary export | diagnostics adapter |
| `tests/unit/app/test_public_session.py`、`tests/unit/app/test_runtime_checkpoint.py` | Runtime capability/admission/inspection owner性质与故障注入 | Runtime owner verification |
| `external/interaction-shell/tests/backend/test_contracts.py`、`test_core_runtime_port.py`、`test_manager.py`、`test_api.py` | closed schema、纯投影、deployment竞态零Runtime调用、live/absent recovery与HTTP代数 | Shell contract/integration verification |
| `external/interaction-shell/tests/backend/test_deployment_app.py`、`test_steel_viewer.py` | BrowserGym→Target factory delegation、typed reconnectability、Steel只产出SurfaceAvailability且不读取control facts | Deployment/viewer verification |
| `external/interaction-shell/tests/architecture/test_external_isolation.py` | public import、checkpoint truth与生成边界负向门 | Architecture verification |
| `frontend/src/**/*.test.tsx`、`frontend/e2e/**` | generated controller/view-model和原子v3 E2E验收 | Frontend verification |

## 19. 非目标

- 不修改或治理主工作树遗留 benchmark Console。
- 不让 React 直接加载 Surface plugin 或平台 SDK。
- 不建立前端插件市场、动态组件下载或任意 schema renderer。
- 不把 Shell 变成第二 Agent、第二 Runtime state machine或第二 evaluator。
- 不把 command offers当作权限或跳过 Runtime admission。
- 不引入事件溯源；snapshot仍是当前公开状态，event只负责有序更新。
- 不长期支持多个 Shell schema版本。
- 不因治理重写 CopilotKit、AG-UI、FastAPI、Pydantic、React或浏览器 viewer底层。
- 不在本阶段修改 PydanticAI history、GroundedToolCatalog、Binder或Surface action执行。
- 不在本阶段实现AndroidWorld、OSWorld或通用deployment profile registry；真实第二平台出现后单独立项。
- 不实现同一session内的 `start_new_task` 状态转换。

## 20. 工作量与切片

| 工作包 | 相对规模 | 主要风险 |
| --- | --- | --- |
| Runtime capability/recovery owner repair | 中 | 状态代数与checkpoint inspection currentness |
| v3 Pydantic合同 + tests | 中 | command offers与Runtime public capabilities一致性 |
| OpenAPI/client/validator生成 | 中 | SSE/AG-UI runtime validation生成能力 |
| 单一 command endpoint | 小到中 | 有界v2兼容与API tests |
| controller/view-model迁移 | 中 | 保持event cursor/recovery时序 |
| closed SurfaceView union | 中 | session-owned control lease cross-model不变量 |
| diagnostics隔离 | blocked | 等待benchmark owner发布versioned summary schema与读取边界 |

可交付的最小产品合同批次是 Phase 0–3；Phase 2必须原子切换，不能把破坏v2 schema、生成物与frontend迁移拆成可独立落地阶段。Phase 4是后续独立diagnostics治理，并在benchmark producer合同出现前保持blocked。只生成 TS types而保留手写 fetch/cast/status分支不算完成治理。

## 21. 可证伪验收标准

只有同时满足以下条件，才能声明“前端合同治理完成”：

1. Backend Pydantic/FastAPI是唯一schema与operation authority。
2. OpenAPI、TS DTO、runtime validators、named client与event decoder由一个命令 deterministic生成；fixture/examples不作为强制生成项。
3. Regenerate-and-diff CI通过；故意改变backend contract但不更新generated artifacts时gate必失败。
4. Authored frontend没有raw fetch、endpoint字符串、API body字典、domain cast或payload JSON parsing。
5. `ShellEvent` 是闭合typed algebra，无 `data.snapshot` convention。
6. Runtime capability是state-correct且precondition-complete；manager只做session access/serialization，Runtime独占semantic admission，Port只做deployment availability的offer交集、提交前fresh gate与typed result纯转换；deployment gate失败时Runtime零调用，React只消费`CommandOffer`。
7. transport disconnect/cursor gap/epoch mismatch只做bounded resync；protocol mismatch终止且不resync/recover/reconnect；只有typed `RecoveryRequired`触发exact recovery。
8. Product snapshot不含benchmark/provider analysis；Diagnostics failure不影响product truth。
9. `SurfaceView` 是不复制control owner/lease的闭合展示union；deployment只产出瞬时`SurfaceAvailability`，唯一public composition在RuntimeSessionPort，且不泄漏provider identity/private locator。
10. Shell registry不存checkpoint truth；lookup live-first；live TargetRuntimeSession、store、deployment reconnector、Target factory transition与manager installation边界分离。Factory inspector只产生`RecoverableCheckpoint`，manager只能一对一映射为exact`RecoveryRequired`；live exact-ref comparison只由TargetRuntimeSession执行，且auth/unsupported/unavailable/inspection-failed均有typed mapping。
11. Existing web start/answer/confirm/pause/resume/revise/takeover/return/cancel/close flows继续通过provider-free integration与E2E。
12. Unknown version/event/field fail closed，无caller-side猜测或每case生产分支。
13. v3 public schema和generated artifacts中不存在未实现的 `start_new_task` 或无owner的 `offer_revision`。
14. CommandOffer满足legality soundness/completeness、kind唯一性与canonical ref placement；offer命令不会因已发布前置条件返回Conflict/Unsupported，闭合基础设施故障只返回Rejected；Answer/Revise入口不靠UI优先级猜意图。
15. 全命令public admission code集合闭合且无`runtime_conflict`fallback；合法revision的所有closed business outcomes返回Accepted并由`last_control_outcome`表达；Conflict只表示currentness/identity/ref/session-state冲突，基础设施失败只进入Rejected，task success仍只来自Runtime completion。
16. inspection后的实际recover返回closed `RecoveryAttempt`；supported race/failure不进入HTTP exception字符串，只有Recovered安装snapshot且非Recovered不会自动重试。

## 22. 实施后维护规则

- 任何公共合同改动必须先修改 Pydantic owner，再生成；不得先改TS绕过。
- 任何新 command 必须同时提供：closed model、offer projection、admission semantics、generated operation、property/integration test、UI view-model case。
- 任何新 event 必须证明 snapshot-only event不足；没有第二个真实消费者时不扩事件代数。
- 未来任何新 Surface provider只能通过另行批准的deployment/private viewer composition接入，不得增加frontend provider branch。
- 任何新 diagnostics字段必须由benchmark/versioned export owner产生，不得由Shell解析新artifact细节重建。
- generated目录的review重点是输入schema、generator版本和diff摘要，不手工修生成代码。
- 每次发布前执行完整 generation、typecheck、contract、integration和E2E gates。

## 23. 当前证据索引

- `src/affordance_runtime/app/public_session.py`：Runtime-owned v3 capability/ref、closed admission conversion、live exact checkpoint admission以及factory-owned inspection/recovery transition。
- `external/interaction-shell/backend/interaction_shell/contracts.py`：唯一公开 `interaction-shell.v3` Pydantic authority；命名 `CommandOffer`、闭合 `SurfaceView`、event、command、admission与recovery代数。
- `external/interaction-shell/backend/interaction_shell/core_runtime_port.py`：唯一 `SurfaceAvailability × Runtime control facts → SurfaceView` owner、唯一fresh TakeOver deployment gate与Runtime outcome wire projection。
- `external/interaction-shell/backend/interaction_shell/manager.py`：credential/session lock、bounded conversation、typed lookup映射与Recovered-only handle installation；registry schema不含checkpoint truth。
- `external/interaction-shell/backend/interaction_shell/viewer.py`、`steel_viewer.py`：provider-neutral、ephemeral、closed `SurfaceAvailability` producer。
- `external/interaction-shell/backend/interaction_shell/deployment_app.py`：BrowserGym composition委托 `TargetRuntimeSessionFactory`，只注入reconnector且不读取checkpoint。
- `external/interaction-shell/backend/interaction_shell/api.py`、`generate_openapi.py`、`openapi.json`：固定operation IDs、唯一 `/sessions/{session_id}/commands`、typed AG-UI SSE anchor与deterministic OpenAPI。
- `external/interaction-shell/frontend/src/generated/`：`@hey-api/openapi-ts@0.99.0`生成DTO/named SDK/SSE client，`valibot@1.4.2`生成recursive strict runtime validators/event decoder；不存在手改生成物。
- `external/interaction-shell/frontend/src/session/command-builder.ts`：唯一受限、穷尽的 offer+validated snapshot+user intent → generated command builder。
- `external/interaction-shell/frontend/src/hooks/use-shell-session.ts`、`src/session/view-model.ts`、`src/components/shell-app.tsx`：generated SDK/validator controller、纯view-model与offer-driven React；无raw fetch、endpoint/method/body字典、domain cast或status legality分支。
- `external/interaction-shell/tests/backend/`、`tests/architecture/test_external_isolation.py`、frontend unit与`e2e/shell.spec.ts`：owner/race/recovery/outcome/offer/OpenAPI/negative gate和provider-free API/SSE/Playwright证据。

当前验证摘要（2026-08-27）：Runtime owner suite 50 passed；Shell backend/architecture 81 passed、1个可选 `pydantic_ai_harness` import skip；frontend 27 passed，typecheck/lint/build通过；synthetic Playwright 1 passed。focused Ruff、backend Pyright与scoped Mypy通过，deterministic regeneration和`git diff --check`通过。完整root Mypy在跟随整个仓库import时仍报告219个既有、与本迁移无关且位于禁止修改范围的错误；该结果不被改写为本实现通过。未运行live provider或benchmark。

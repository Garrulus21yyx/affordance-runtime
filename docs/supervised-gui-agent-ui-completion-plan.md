# 通用可监督 GUI Agent UI 补齐计划

> 状态：提案与实施计划，尚未声明实施完成或 benchmark closure。
>
> 适用范围：Runtime 视觉观察、单一 ActionPolicy 公共决策、PublicSession、Interaction Shell、生成式前端合同与通用协作 UI。
>
> 状态 authority：当前架构与实施状态仍以 [Architecture](architecture.md) 和 [Benchmark](benchmark.md) 为准。本文件只规定目标合同、迁移顺序、兼容性门禁和退出条件，不得被用作完成证明。
>
> benchmark 约束：本计划不得修改 benchmark task/fixture/selector/站点语义来适配实现。任何 live benchmark 都需要用户单独授权；provider-free 通过不等于 live 能力无回归。

## 1. 目的与产品定位

产品目标是一个通用 GUI Agent 协作台：用户能够看见当前目标、环境、证据、进展、决策点和控制权，并能在任务执行期间回答问题、修订目标、确认高风险动作或接管界面。

购物是旗舰验收任务，不是产品协议。最终实现不得出现 `ShoppingTask`、`ProductCard`、`TaobaoCandidate`、价格/尺码/店铺专属 schema、站点专属视觉 prompt 或“选择第 N 件商品”生产分支。购物任务只证明以下通用能力能够组合成功：

```text
通用目标修订
+ 通用实体候选
+ 通用视觉谓词
+ 通用选项交互
+ 通用结果产物
+ 通用用户接管
```

本计划的目标不是增加第二个 Planner、VLM Planner、聊天 Planner 或 Runtime loop。执行形态保持：

```text
TaskGoal + optional GoalPlan + fresh WorldObservation
→ one ActionPolicy decision
→ Catalog / Binder / Risk / Confirmation / Executor
→ stable capture / fusion
→ StepResult
→ same ActionPolicy on the next step
```

## 2. 当前事实与需要补齐的根因

当前代码已经具备部分正确基础，但合同与接线没有闭合：

1. `RequestObservation` 只接收一个 subject，而 acquisition 层的 `ObservationNeed.subject_ids` 已支持批量 subject。
2. BrowserGym 已可注入 region proposer、point grounder、candidate disambiguator 和 predicate classifier，但 visual offer 未声明 predicate/text/spatial 能力，predicate classifier 没有进入实际 acquisition 分支，point grounder 在 visual projection 调用处仍传入 `None`。
3. region proposal、candidate disambiguation 和 point grounding 仍可接收完整 `TaskGoal`；point prompt 仍要求视觉模型选择“推进整体目标的下一动作”，与唯一 ActionPolicy 冲突。
4. World 已有 alignment proposal/decision、visual-only identity、conflict 和 binding currentness，但 provider 的 unknown/failed/partial batch 结果没有一条完整的 typed ToolReturn 路径。
5. 产品 Shell 只组合 DOM Surface。直接并列加入现有 Visual adapter 会产生同一物理浏览器的重复 reset owner，且两个独立 adapter 无法保证共享 capture identity 和结构/视觉 correspondence。
6. `AskUser` 只有自由文本问题和字段名，缺少通用单选、多选、结构化字段、媒体和证据选项，也缺少与请求对应的闭合 response 代数。
7. `FinalResponse.content` 同时承担 native evaluator submission 和用户可见结果；若直接把 `PublicArtifact` 混入同一路径，会让展示结构影响已有 benchmark final-response codec。
8. PublicSession 只公开当前问题、确认、完成和字符串化 progress；Shell 没有真实展示 transcript，React 仍硬编码 Agent 回复并从字符串猜 UI。
9. Shell 已将 `run_status` 与 `control_owner` 分开。新增 `user_control` run status 会制造第二控制 authority。

共同根因不是“缺少购物功能”，而是三条通用公共链没有闭合：

```text
ActionPolicy observation intent
→ typed acquisition/query
→ provider outcome
→ SurfaceObservation / acquisition outcome
→ World / ToolReturn

ActionPolicy/user interaction intent
→ typed InteractionRequest
→ typed InteractionResponse
→ TaskGoal revision / same ActionPolicy

Runtime and policy owner facts
→ typed public feed blocks
→ generated Shell contract
→ exhaustive React rendering
```

## 3. 非目标

本计划明确不做：

- 第二个 Planner、Manager/Worker、VLM Planner、聊天意图分类 Agent 或独立 goal evaluator；
- mutable milestone/todo、achievement record、第二 World、第二 Binder、第二 evaluator 或第二 provider history；
- 用 Runtime 解释页面语义、价格、商品、文件、航班、酒店或站点文案；
- 让 VLM 直接选择并执行下一动作；
- 让 Option selection 绕过 ActionPolicy/Catalog/Binder 直接 dispatch；
- 让 PublicArtifact、AgentIntent、ActionEffect 或 UI 文案证明任务完成；
- 将 selector、坐标、prompt、provider token、raw trace 或 JSON 暴露到普通用户 feed；
- 为通过单个 benchmark case 增加任务名、固定 ID、固定输出名、页面文字或 selector 分支；
- 在没有用户单独授权时启动 live benchmark；
- 以 provider-free 测试通过替代真实 benchmark 能力验证。

## 4. 权威事实与 owner 模型

| 事实或转换 | 唯一 owner | 生产者 | 消费者 | 明确的非 owner |
| --- | --- | --- | --- | --- |
| 用户目标 | `TaskGoal` | task intake/revision boundary | GoalCompiler、ActionPolicy、evaluator、PublicSession | GoalPlan、Feed、React |
| 静态目标指导 | `GoalPlan` | GoalCompiler boundary | ActionPolicy | Runtime progress、UI todo |
| 当前 GUI 事实 | fresh `WorldObservation` | SurfaceAdapter + WorldFusion | ActionPolicy、evaluator、Binder currentness | transcript、Workspace history、UI |
| Agent 想补的证据 | admitted `RequestObservation` | ActionPolicy ToolCall + Catalog binding | CoreLoop | Visual provider、React |
| acquisition 需要 | `ObservationNeed` | CoreLoop 的机械转换 | ObservationOrchestrator、SurfaceAdapter | provider output、Feed |
| screenshot/frame currentness | Visual capture owner | Browser/BrowserGym SurfaceAdapter | visual provider request、binding currentness | provider output、ActionPolicy |
| provider request | visual SurfaceAdapter | current need + current capture + resolved candidates | Visual provider port | CoreLoop、Shell |
| visual purpose capability offer | grouped visual SurfaceAdapter | actually configured provider ports | GroundedToolCatalog、acquisition selection | provider transport、CoreLoop、prompt |
| provider completed/unknown/failed | visual provider boundary | provider adapter | SurfaceAdapter | WorldFusion、UI |
| source-local视觉事实 | `SurfaceObservation` | visual SurfaceAdapter | WorldFusion | ActionPolicy raw provider result |
| canonical correspondence/conflict | `WorldFusion` | alignment proposals + source facts | WorldObservation、ActionPolicy、Binder | CoreLoop、provider、Shell |
| query-level observed/unknown/failure | `ObservationQueryOutcome` in acquisition boundary | SurfaceAdapter + coordinator | committed `StepResult.observation_outcome` | World fact、TaskEvaluator success |
| observation feedback to policy | committed `StepResult.observation_outcome` | Core transition | ToolReturn、Monitor、Trace | SurfaceAdapter、Shell |
| model-visible tool contract | current `ToolCatalog` | registry/catalog owner | ActionPolicy/provider bridge | CoreLoop、provider transport |
| model-facing observation rollout | Catalog-owned `ObservationToolExposureProfile` contract | product/benchmark composition selects one immutable value per ActionPolicy session | TurnPacker、ToolCatalog、run attestation | Surface offer、provider registry、CoreLoop |
| private action binding | Binder | current World-backed resolver | Executor | model、Option、Feed、Trace |
| GUI side effect | Executor/environment | bound action request | fresh capture、StepResult | VLM、GoalPlan、PublicArtifact |
| task completion | TaskEvaluator/native verifier | fresh World + task contract | RunState/PublicSession | FinalResponse、ActionEffect、Feed |
| final evaluator representation | environment `FinalResponseCodec` | environment boundary | finalization/native evaluator | PublicArtifact、GoalPlan、Shell |
| interaction draft content | ActionPolicy decision or GoalCompiler `NeedsInput` projection | policy/compiler boundary | Core transition admission | PublicSession、React |
| admitted pending interaction | committed RunState/StepResult transition | Core transition | PublicSession command admission | ActionPolicy、Shell、React |
| user interaction response | public command admission | user + Shell command | TaskGoal input/revision boundary | OptionCard、frontend local state |
| public feed source identity/facts | PublicSession typed projection | committed commands/steps/outcomes | Shell adapter | Trace reconstruction、Shell ID allocation、React guessing |
| bounded presentation transcript | Shell projection | accepted public events/commands | React、bounded revision language context as explicitly selected | RunStatus、TaskGoal、completion |
| control status | `RunStatus` + `ControlOwner` | Runtime public session | command offers、Shell view | frontend status table |

核心不变量：

1. 一个事实只有一个 owner；其他层只能保留引用、摘要或不可回写的投影。
2. `RequestObservation`、`ObservationNeed` 和 provider request 是三个连续边界的不同表示，不是三份可独立修改的查询真相。
3. Visual observed evidence 可进入 World；Visual unknown/failed 只能进入 acquisition outcome/ToolReturn，不能伪装为 GUI fact。
4. 任意 executable visual binding 必须绑定同一 capture lineage，并通过既有 Binder/Executor/currentness 路径。
5. Interaction option 是用户选择输入，不是 action authority。
6. PublicArtifact 是展示产物，不是 evaluator outcome，也不能发明实际文件或链接。
7. React 只消费 generated validator 已验证的 closed unions，不根据字符串或字段组合重建 Runtime 状态。

## 5. 目标合同

### 5.1 ActionPolicy 观察请求

模型可见的工具参数使用当前调用的公共 refs，并按 `purpose` 构成 closed discriminated union，而不是一个所有字段都可选的大对象：

```text
RequestObservationInput =
  EntityDiscoveryInput{
    purpose=entity_discovery, atomic_query, max_results=1..32, public_intent?
  }
| VisualPropertyInput{
    purpose=visual_property, subject_refs[1..32], predicate, public_intent?
  }
| CandidateDisambiguationInput{
    purpose=target_disambiguation, candidate_refs[2..32], atomic_query, public_intent?
  }
| PointGroundingInput{
    purpose=point_grounding, atomic_query, candidate_refs[1..32]?, public_intent?
  }
| TextInImageInput{
    purpose=text_in_image, subject_refs[1..32], atomic_query, public_intent?
  }
| SpatialRelationshipInput{
    purpose=spatial_relationship, subject_refs[2..32], predicate, public_intent?
  }
| VisualChangeInput{
    purpose=visual_change, subject_refs[1..32], predicate, public_intent?
  }
```

`atomic_query`/`predicate` 都是 bounded 原子描述：前者描述要发现、消歧、定位或读取的对象，后者描述要分类的属性、关系或变化。各 variant 未列出的字段均 forbidden；`subject_refs` 与 `candidate_refs` 保持输入顺序且不重复。`TEXT_IN_IMAGE` 第一阶段只支持已公开 subject；任意截图 region scope 必须先由 entity discovery 产生公开 ref，避免模型直接提交坐标。

`query_id` 不由模型提供。Catalog binding 使用当前 tool call ID、context generation 和已验证参数创建 Runtime identity，并把 `subject_refs`/`candidate_refs` 一次性解析为 canonical subject IDs。Binding 同时保留 bounded `{input_index, canonical_id}` correlation；旧 public ref 已存在于原 tool call 参数中，但不得被复制成下一轮 executable ref。CoreLoop 收到的是 context-bound internal decision：

```text
RequestObservation
├── context_id
├── query_id
├── purpose: ObservationPurpose
├── subject_ids[]
├── candidate_ids[]
├── atomic_query
├── predicate
├── max_results
├── public_intent?
└── tool_call_id
```

purpose 使用现有语义，不增加同义枚举：

| 用户需要 | `ObservationPurpose` | provider evidence kind |
| --- | --- | --- |
| 发现截图中的相关实体 | `ENTITY_DISCOVERY` | `RegionEvidence` |
| 判断视觉属性/状态 | `VISUAL_PROPERTY` | `PredicateEvidence` |
| 在已知候选中消歧 | `TARGET_DISAMBIGUATION` | `DisambiguationEvidence` |
| 将原子目标落到点 | 新增 `POINT_GROUNDING` | `PointEvidence` |
| 读取图片中的文字 | `TEXT_IN_IMAGE` | `TextEvidence` |
| 判断空间关系 | `SPATIAL_RELATIONSHIP` | `SpatialEvidence` |
| 比较前后视觉变化 | 新增 `VISUAL_CHANGE` | `ChangeEvidence` |

Runtime-owned lifecycle purpose，如 `WORLD_GROUNDING`、`CURRENTNESS_REFRESH`、`CRITERION_VERIFICATION`、`EFFECT_VERIFICATION`，不得进入 model-visible `request_evidence`。`VISUAL_CHANGE` 是 ActionPolicy 发起的开放视觉比较；`EFFECT_VERIFICATION` 是 Runtime 在动作后的生命周期验证，两者不能复用同一个 public purpose。

每个 purpose 必须有闭合字段校验：

- `VISUAL_PROPERTY`：1..32 subjects，非空 predicate，结果逐 subject 完整覆盖；
- `TARGET_DISAMBIGUATION`：2..32 candidates，原子 discriminating predicate/description，最多一个 chosen candidate；
- `POINT_GROUNDING`：一个原子可见目标描述，可选 bounded candidates，不包含整体 TaskGoal；
- `ENTITY_DISCOVERY`：允许无 subjects，必须给 atomic purpose/description 和 max_results；
- `TEXT_IN_IMAGE`：1..32 subjects 和读取目的；当前阶段不接收坐标 region；
- `SPATIAL_RELATIONSHIP`：至少两个 subjects，关系描述非空；
- `VISUAL_CHANGE`：1..32 subjects 和非空 predicate；必须存在同 episode 的 before/after capture lineage，由 Runtime 组装，模型不能提供 digest。

Catalog/CoreLoop 到 `ObservationNeed` 的转换是固定映射，不由 provider 或 CoreLoop 猜测。该 owner 的目标字段为 `need_id=query_id | purpose | subject_ids[] | candidate_ids[] | query_text | evidence_property | max_results | required_modality | required_assurance | freshness`：所有七个 public visual variant 都映射到 `required_modality=VISUAL`、`required_assurance=WEAK`、`freshness=FRESH_ACQUISITION`；purpose 按上表一一映射；canonical subject/candidate refs 分别进入对应 ID tuple；visual property 的 predicate 进入现有 `evidence_property`，其余 `atomic_query`/predicate 进入 bounded `query_text`；不适用的 tuple/string/max_results 必须为空。`before/after` capture lineage 和 currentness 由 Runtime acquisition boundary 后补。必须修改 `ObservationNeed` owner 以无损承载这些字段，不能在 CoreLoop 使用 reason string 旁路。

Agent 请求固定要求 fresh acquisition。模型不能降低 freshness；Runtime 可以在同一 acquisition group 内复用一次已经由该请求触发的 current frame，但不能重用旧 page generation 的坐标或结果。

### 5.2 动态 `request_evidence` ToolCatalog

七种视觉 purpose 不是七个独立 ActionPolicy tools。为保持现有 model protocol 和 benchmark compatibility，DeepSeek 继续最多看到一个 public tool `request_evidence`；它在 Catalog binding 后产生 internal `RequestObservation` decision，不重命名 public tool：

```text
request_evidence
└── oneOf(current applicable purpose variants)
```

Predicate classifier、region proposer、candidate disambiguator、point grounder、OCR、spatial/change provider 都是 visual SurfaceAdapter 后面的 Runtime-private ports，不注册为 DeepSeek tools。`ask_user`、GUI semantic actions 和 `submit_final_response` 仍是各自已有的 public decisions/tools，不与视觉 provider ports 合并。

必须区分三个状态：

```text
provider port registered
≠ purpose advertised in current ToolCatalog
≠ provider called
```

安装或配置 provider 只建立内部能力；编译 Catalog 不调用 provider；只有 ActionPolicy 实际选择 admitted `request_evidence` 后，acquisition 才能调用相应 provider。

`GroundedToolCatalog` 是 model-visible schema 的唯一 owner。它在每个 ActionPolicy turn 根据 exact fresh `AgentContext + ModelTurnDelivery` 重新编译：

```text
visible_purposes
= fresh Context observation capabilities derived from configured ports
∩ agent-visible purpose allowlist
∩ current-World purpose applicability
∩ exact DeliveryManifest ref/cardinality constraints
∩ typed ObservationToolExposureProfile
```

只有 `visible_purposes` 非空时才发布 `request_evidence`。Schema 使用 closed `oneOf`，只包含本轮适用 variants；subject/candidate enum 只来自同轮 `DeliveryManifest` 中 typed readable/current refs。不能注册一个含所有 purpose 和大量 optional 字段的常驻工具，也不能让 provider transport、CoreLoop 或 prompt 自行追加 purpose。

`ObservationToolExposureProfile` 是 Catalog owner 定义的 immutable、typed model-facing rollout contract，例如 `compatibility.v1` 与 `dynamic-visual.v1`；它只规定 schema version 和允许公开的 purpose set，不包含 provider 配置、TaskGoal 或 Runtime 状态。Product/benchmark composition 在创建 ActionPolicy session 时选择一次；`TurnPacker` 将该 exact profile 作为 `compile_grounded_action_catalog(...)` 的显式输入。`GroundedToolCatalog` 保存 profile ID/digest，并将其纳入 `catalog_id`；binding 只接受同一 frozen Catalog snapshot。不得让 Catalog 直接读取全局 provider registry、环境变量或 Surface 实例，也不得让 provider transport 在 schema 编译后修改 profile。

Configured ports 的事实只由 grouped visual Surface owner 投影为 fresh Context 中的 typed `ObservationOffer/observation_capabilities`；Catalog 只消费该公开 capability snapshot。这样 Surface 拥有“实际能做什么”，Catalog 拥有“本轮向模型展示什么”，两者之间没有第二 registry。

Purpose-specific applicability 使用稳定 Runtime facts，不解释 TaskGoal 语义：

| Purpose | 进入当前 ToolCatalog 的必要条件 |
| --- | --- |
| `ENTITY_DISCOVERY` | region proposer 可用，且 current structural/region coverage 明确 incomplete/truncated；不要求输入 ref |
| `VISUAL_PROPERTY` | predicate classifier 可用，且 DeliveryManifest 至少有一个可读 current subject ref |
| `TARGET_DISAMBIGUATION` | disambiguator 可用，且本轮至少有两个可读 current candidate refs |
| `POINT_GROUNDING` | point grounder 可用，current frame 可获取；candidate variant 只枚举本轮 current refs |
| `TEXT_IN_IMAGE` | OCR/text provider 可用，且至少有一个 current subject/image scope |
| `SPATIAL_RELATIONSHIP` | spatial provider 可用，且至少有两个 current subject refs |
| `VISUAL_CHANGE` | change provider 可用，并存在同 episode、可验证 lineage 的 before/after frames |

这些条件只说明“Runtime 当前能够合法完成什么”。TaskGoal 是否真的需要颜色、OCR、空间关系或视觉变化，仍由唯一 ActionPolicy 判断；Runtime 不按任务关键词、站点、页面文案、benchmark ID、重复次数或“模型卡住”猜测视觉语义。

因此“只在需要时出现”的精确定义是：不具备能力、输入、currentness 或本轮 refs 时不出现；具备这些前提但任务语义未必使用时，tool/variant 可以被展示但不被调用。若要求 Runtime 预先判断“这个 TaskGoal 语义上是否需要颜色/OCR”，就必须增加关键词规则、tool-retrieval Planner 或第二次模型分类，这会违反唯一 ActionPolicy。当前方案选择 deterministic applicability filtering + ActionPolicy semantic selection，并用“tool offered 但未选择时 provider 零调用”控制成本。

`ObservationOffer.supported_purposes` 必须由 grouped visual Surface 根据实际配置的 ports 显式生成。Product/benchmark composition 不得依赖 visual modality 的宽泛默认 purpose；未配置 classifier 就不能 advertise `VISUAL_PROPERTY`，未配置 grounder 就不能 advertise `POINT_GROUNDING`。Adaptive escalation 是 Runtime-owned typed need 路径，它可以消费相同 capability offer，但不能把 lifecycle purpose 暴露进 Agent ToolCatalog，也不能因为 provider availability 自行发起无稳定 reason code 的调用。

执行前使用两个 owner 连续 admission，不能让 Catalog binding 直连 Surface/provider registry：

1. Catalog binding 只校验 `context_id/delivery_id/catalog_id`、purpose 属于 exact offered `oneOf`、refs/顺序/唯一性/cardinality 属于 frozen manifest，以及 `ObservationToolExposureProfile` 与 `catalog_id` snapshot 一致。任何新 profile 都必须重新 pack 新 delivery/catalog。
2. Observation acquisition/visual Surface currentness owner 在任何 provider activation 前，使用 live selected `ObservationOffer` 和 capture owner facts 重校验该 purpose capability 仍可用、frame/currentness 有效、before/after lineage 满足且仍属于同 episode。

任一级失败都在 visual provider 调用前 typed reject，provider call count 为零。CoreLoop 只传递 typed decision/need/outcome，不承担第二级语义校验。历史 Catalog、未展示 purpose、模型伪造 ref、消失的 capability、stale frame 和 schema 外字段不得由 repair/fallback 放宽。

动态工具性质门：

- 无 visual provider/无 applicable purpose：整个 `request_evidence` 缺席；
- 只有 classifier：schema 只有 `VISUAL_PROPERTY` variant；
- 无 current refs：所有 ref-required variants 缺席；
- 少于两个 candidates：`TARGET_DISAMBIGUATION` 缺席；
- 无合法 before frame：`VISUAL_CHANGE` 缺席；
- tool 出现但未被选择：所有 visual provider 调用数为零；
- stale Catalog/unoffered purpose/invalid ref：typed reject 且 provider 调用数为零；
- schema 内每个 public ref 都属于同一 DeliveryManifest；
- compatibility profile 的 tool/purpose set、Catalog digest 和 schema token count 满足 9.1–9.3 的预登记门。

现有 `TurnPacker → compile_grounded_tool_catalog()`、`_observation_tool_needed()` 和 `_evidence_request_schema()` 应在 TurnPacker/Catalog owner 边界内演进为上述 typed-profile、purpose-specific compilation；不新建第二 ToolManager、第二 registry 或 provider-side schema authority。

### 5.3 Visual provider 请求

Visual provider 不直接接收 `TaskGoal`、GoalPlan、RunState、ToolCatalog 或完整历史。SurfaceAdapter 按 purpose 编译原子、截图绑定的请求：

```text
VisualProviderRequest
├── query_id
├── purpose
├── atomic_query
├── candidates[]          # provider-call-local ref + role/label/state/bbox
├── max_results
├── image_bytes
├── image_size
└── capture_identity      # Runtime-private，不进入 prompt 文本
```

provider-call-local ref 可以使用 `E1..E32` 以便标注截图，但 canonical subject ID 始终留在 Runtime 私有映射中。Provider 不返回 selector、backend node ID、action ID、TaskGoal 结论或 Runtime identity。

Region proposer 的 prompt 只发现与 atomic query 有关的当前可见实体；point grounder 只定位该原子目标；disambiguator 只在给定候选中判断 referent；predicate classifier 对每个候选判断指定 predicate。任何 provider 都不得选择“推进整体目标的下一动作”。

### 5.4 闭合且支持部分成功的视觉结果

顶层结果使用：

```text
VisualQueryCompleted
├── query_id
├── items[] = VisualEvidence | VisualUnknownItem
└── coverage = complete | partial | unknown

VisualQueryFailed
├── query_id
├── stage
└── reason = transport | timeout | structured_output | provider_error
```

`VisualEvidence` 是以下 closed union：

```text
RegionEvidence{
  evidence_id, region_local_ref, bbox, label, confidence
}
PredicateEvidence{
  evidence_id, subject_id, predicate, truth=true|false, confidence
}
DisambiguationEvidence{
  evidence_id, candidate_ids[], chosen_candidate_id, confidence
}
TextEvidence{
  evidence_id, subject_id, text, confidence
}
SpatialEvidence{
  evidence_id, subject_ids[2..32], predicate, truth=true|false, confidence
}
PointEvidence{
  evidence_id, target_local_ref, point, confidence
}
ChangeEvidence{
  evidence_id, subject_ids[1..32], predicate, truth=true|false, confidence
}
```

这些是 Runtime 内部 variant；`subject_id`、bbox 和 point 不进入公共 ToolReturn。每个 evidence 都继承同一 query/capture provenance。Region/point 的 local ref 只能由 adapter 的 call-local mapping 解析；chosen candidate 必须属于输入 candidate set；空间关系的 subject 顺序必须保持；confidence 必须有限且在 `[0,1]`。Text 可为空只在 provider 明确判定“图像中可观察到空文本”时成立，否则返回 `text_not_legible` unknown。

`VisualUnknownItem` 必须与一个 subject/candidate/scope 关联，原因限定为：

```text
target_not_visible
insufficient_resolution
multiple_plausible_targets
property_not_observable
relation_not_observable
text_not_legible
change_not_determinable
```

对于 batch classification，每个输入 ref 必须恰好对应一个 evidence 或 unknown item；允许同一结果中同时存在 true、false 和 unknown。`VisualQueryFailed` 只表示调用边界没有产生可信 typed result，不能用来表达某个对象看不清。

`coverage` 不是模型自由文本，而是 adapter 根据 items 确定性计算：全部请求 scope 有 evidence 时为 `complete`；evidence 与 unknown 混合时为 `partial`；全部 scope 都是 unknown 时为 `unknown`。对于 discovery，一个或多个 bounded region 为 `complete`，没有可信 region 时返回 scope-level `target_not_visible` unknown；provider 不得用空 items 假装成功。Malformed、重复、越界或不覆盖输入 domain 的 provider payload 在一次允许的 boundary repair 后转成 `VisualQueryFailed(structured_output)`。

### 5.5 provenance 和 currentness

每项可进入 Runtime 的视觉证据附带不可由模型伪造的 provenance：

| 字段 | owner |
| --- | --- |
| provider/model/prompt version | configured provider port + adapter call boundary |
| screenshot digest/image size | capture owner |
| page generation/episode identity | browser SurfaceAdapter |
| viewport/scroll/DPR/zoom | capture owner |
| acquisition latency | adapter 实测 |
| query ID/call ID | Runtime/catalog binding |
| confidence | provider output；Runtime 只做范围校验并保留来源 |
| acquired_at/currentness disposition | Runtime acquisition boundary |

普通用户 UI 只看到 `结构证据`、`视觉证据 · confidence`、`无法确认`、`证据已过期` 等公共摘要。provider/model/prompt/digest/坐标只进入 Labs/Trace 或 Runtime 私有 currentness。

### 5.6 SurfaceObservation 与 WorldFusion 映射

不得在 CoreLoop、ActionPolicy context 或 Shell 新建第二套 correspondence reducer。Visual SurfaceAdapter 将 provider 结果映射到现有 World 合同：

```text
matched
→ visual source-local target/fact + EntityAlignmentProposal
→ WorldFusion 合并到原 canonical target

unmatched
→ visual_only_target_ids
→ 只有满足 executable visual binding 合同才产生 binding

ambiguous
→ 无 alignment proposal、无 binding、typed unresolved outcome

conflict
→ typed alignment/conflict，相关 predicate 不进入可执行/确定状态

unknown
→ 不产生 StateFact 或 binding；进入 acquisition ToolReturn

stale
→ 不属于 provider result；由 binding/currentness owner 拒绝并触发 fresh observation
```

Candidate disambiguation 只证明“哪个候选匹配 query”，不得写成 `visually_selected=true`。只有 `VISUAL_PROPERTY(predicate="selected")` 才能产生选中状态 evidence。

Disambiguation 的正向合同是：若它只在已知 canonical candidates 中选中一个候选，则结果保留在 query outcome，下一轮 ToolReturn 由当前 `ModelTurnDelivery` projection 把 chosen canonical subject 重新映射为 same-World current public ref；它不产生任何 GUI `StateFact`。若 disambiguation 同时证明一个 visual local entity 与 structured candidate 的 correspondence，adapter 只能提交 `EntityAlignmentProposal`，最终是否合并仍由 `WorldFusion` 决定。两条路径都不得产生 `selected` 状态。

Point evidence 不立即执行。它最多形成一个 current visual-only target/binding；下一轮仍由 ActionPolicy 从当前 ToolCatalog 选择 action。

### 5.7 Observation outcome 返回 Agent

CoreLoop 不解释 VisualEvidence 的语义。新增一个由 acquisition owner 定义的 closed carrier：

```text
ObservationQueryOutcome
├── query_id
├── purpose
├── disposition = observed | partial | unknown | failed
├── evidence_refs[]
├── observed_subject_ids[]
├── unknown_items[{locator, reason}]
└── failure_reason?
```

它在 `world/acquisition.py` 与 existing source/need result 同次提交；`StepResult` 新增至多一个 typed `observation_outcome` 字段保存 exact committed outcome；`tool_result_projection.py` 只形成不含 canonical ID 的 bounded semantic result，最终 public ref 必须由同轮 `ModelTurnDelivery` 根据 exact fresh after-World 投影和准入。World 只接收 `VisualEvidence` 已投影出的 source-local facts/alignment proposal，unknown/failed 从不进入 World。这样 query outcome、World fact 和公共 ToolReturn 是三个单向表示，不需要从 feedback string 或 Trace 重建。

CoreLoop 只：

1. 将 admitted RequestObservation 机械编译为 ObservationNeed；
2. 调用 environment capture；
3. 保存 acquisition 的 fulfilled/unknown/failed outcome；
4. 在有 fresh World 时提交 World transition；
5. 将 owner-produced typed outcome 放入 `StepResult`；
6. 由既有 ToolReturn projection 返回下一轮 ActionPolicy。

显式视觉请求得到 unknown 或 provider failure 时，若结构 baseline/current World 仍有效，run 保持 `RUNNING`，下一轮 ActionPolicy 可选择结构路径、换 query、AskUser 或 Abort。只有整个 fresh acquisition/currentness 不可建立，或既有 Runtime 安全合同要求终止时，才进入 blocked/failed。

ToolReturn 至少公开：

```text
kind = observation
query_id
purpose
status = observed | partial | unknown | failed
observed_items[{locator, target_ref?, evidence_refs[], verbs[]}]
unknown_items[{locator, reason}]
evidence_refs[]
reason_code?
executable_grounding? = attached_to_returned_readable_targets
```

`locator` 是 closed union：`InputLocator{input_indices[1..32]}` 指向原 tool call 中 refs 的顺序，适用于 predicate/text/spatial/change/candidate-scoped结果；`QueryScopeLocator{}` 表示无输入 ref 的 discovery 或 no-candidate point 整体 query；`ResultLocator{result_index}` 只用于 discovery 的第 N 个 observed result，禁止用于 unknown。Unknown item 不回显已经过期的 E/N ref。`target_ref` 只有在 canonical subject 仍存在于 exact after-World public projection 时才允许出现。默认 target 是 readable-only；只有同一 `ModelTurnDelivery` 同时满足 `before_world=after_world=current World`、返回显式 `executable_grounding`、并给出 `target_ref + verbs[]` 时，`model_turn_delivery.py` 才能把 claimed route 与 sibling current `ActionSpace` 求交并加入同一 `DeliveryManifest/ToolCatalog`。Point/visual-only target 也必须走这条 exact same-World admission；没有 current route 时只读展示，不能执行。它不得公开 canonical IDs、provider payload、prompt、坐标或 selectors。

Delivery properties：ToolReturn 中每个 E/N/F/R ref 都必须出现在同一 manifest 的 typed readable/fact/region 集；每个 executable E ref 都必须具有 exact admitted route；unknown/failed 零 executable route；stale/absent/current-world-mismatch 零 Catalog attachment；一个成功 disambiguation/predicate/point vertical 必须证明 chosen target 在有合法 same-World route 时可由下一轮唯一 Catalog 选择，在无 route 时确定性保持只读。
另外，entity discovery 零结果与 no-candidate point unknown 必须用 `QueryScopeLocator` 完整 round-trip；batch/spatial unknown 必须用 `InputLocator` 覆盖 exact input indices；任何 purpose/locator 非法组合在 ToolReturn 投影前 typed reject。

### 5.8 InteractionRequest 与 InteractionResponse

用 closed draft/admission 两层合同取代 live `AskUser` contract。模型只产生内容草稿，不拥有公共 identity：

```text
InteractionRequestDraft
├── prompt
├── response_kind
│   ├── free_text
│   ├── single_select
│   ├── multi_select
│   └── structured_fields
├── field_drafts[]
├── option_drafts[]
└── public_intent?
```

draft 中的通用 option 不携带 ID：

```text
InteractionOptionDraft
├── title
├── description
├── media_ref?
├── attributes[{label, value}]
├── evidence_refs[]
└── uncertainties[]
```

`InteractionFieldDraft` 是 closed union：`TextFieldDraft`、`IntegerFieldDraft`、`DecimalFieldDraft`、`BooleanFieldDraft`、`DateFieldDraft`；共同字段只有 bounded label/description/required。当前阶段不允许模型用任意 JSON Schema 定义字段。

Core transition admission 验证 draft 中的 evidence/media refs，按输入顺序分配 request-local `field_id`/`option_id`，并提交 pending request：

```text
InteractionRequest
├── request_id
├── prompt
├── response_kind
├── fields[{field_id, kind, label, description, required}]
├── options[{option_id, title, description, media_ref?, attributes[], evidence_refs[], uncertainties[]}]
└── public_intent?
```

字段约束按 response kind 闭合：`free_text` 无 fields/options；`single_select|multi_select` 有 1..32 options 且无 fields；`structured_fields` 有 1..32 fields 且无 top-level options。需要 enum 字段时先使用 top-level select request，不在首阶段再嵌套一套 option authority。

必须同时定义 response：

```text
FreeTextResponse{text}
SingleSelectionResponse{option_id}
MultiSelectionResponse{option_ids[]}
StructuredFieldsResponse{values[] =
  TextFieldValue{field_id, text}
| IntegerFieldValue{field_id, integer}
| DecimalFieldValue{field_id, decimal_string}
| BooleanFieldValue{field_id, boolean}
| DateFieldValue{field_id, iso_date}
}
```

所有 response 都携带 request ID，并经过现有 expected task revision/run status/command offer admission。未知、重复、不属于该请求、缺少 required field、重复 field，或 value variant 与 field kind 不一致时 typed reject。Decimal 使用 bounded canonical decimal string，date 使用 `YYYY-MM-DD`；解析只发生在 command admission owner，不交给 React 猜测。

GoalCompiler `NeedsInput` 可产生 free-text/structured-fields draft；ActionPolicy 可产生 options draft。两者都不分配公共 ID，也不会新增模型角色。Core committed transition 是 pending interaction 的唯一 authority；PublicSession 只从该 transition 生成 command offer并校验 response。用户回答仍进入 TaskGoal input/revision boundary，下一轮仍由唯一 GoalCompiler（仅 task start/revision）和唯一 ActionPolicy 工作。

### 5.9 public_intent

`public_intent` 是同一个 ActionPolicy ToolCall 上的可选、短、非权威 sidecar，例如：

```text
我先检查当前页面中可见的候选。
我需要用截图确认这些控件的选中状态。
```

它不得声明动作已完成、表单已提交、文件已下载或任务已成功。Runtime 不使用 NLP 规则把它变成事实；UI 明确标记为 Agent intent。已完成什么必须由 `StepResult`、receipt、fresh World 和 evaluator 的 typed projection描述。

### 5.10 PublicArtifact 与 FinalResponse

保留 `FinalResponse.content` 作为 environment codec/native evaluator submission。新增 presentation sidecar，但不改变 evaluator 输入：

```text
PublicArtifactDraft
├── title
├── summary
├── items[]
└── evidence_refs[]
```

PublicSession 只在验证后分配 `artifact_id` 并发布：

```text
PublicArtifact
├── artifact_id
├── title
├── summary
├── items[{item_id, title, summary, attributes[], evidence_refs[]}]
├── links[{title, artifact_ref}]
└── evidence_refs[]
```

规则：

- model draft 可写标题/摘要/展示项，但 evidence refs 必须在当前 finalization admission 中解析；
- 实际下载文件、受保护链接和 materialized artifact ref 只能来自 Executor/environment receipt 或现有 artifact owner；
- model 不能提供任意 URL 作为可下载产物；
- native evaluator 仍只接收原 codec 所需的 final response representation；
- evaluator success 之前不得将 artifact 呈现为完成证明；
- benchmark 要求 JSON final response 时，codec 行为与 payload 必须保持原样。

### 5.11 Public feed 与 Shell transcript

公共 feed 使用 closed union：

```text
UserTurn
GoalAccepted
AgentIntent
RuntimeActivity
EvidenceSummary
InteractionRequest
RevisionOutcome
ConfirmationRequired
ControlChanged
RunFinished
```

`RevisionOutcome` 闭合表示 revised/needs_input/no_change/new_task_suggested/unsupported/effect_reconciliation_required。`RunFinished` 用 outcome 表示 success/failure/blocked/cancelled，避免 Completion 与 Failure 重复终态。

PublicSession 为每个 source record 分配唯一 `source_event_id`（现有 session/event epoch/cursor 或 committed command identity 的 typed 组合）；Shell 不得创建、修改或替换它。Shell presentation 可有独立 `block_id`，但必须由 `(source_event_id, block_kind, ordinal)` 确定性派生，去重 key 也是这三个字段。Shell 可持久化 bounded presentation projection，但只能从 accepted command、Runtime event 和 owner-produced outcome append；不得从当前 snapshot 字符串重新猜测历史。

语言 conversation 与展示 feed 分开：

- revision language context 只包含用户语言轮次以及确实需要被后续指代的 Agent prompt/options/final response；
- RuntimeActivity、EvidenceSummary、control、raw status 不进入 revision compiler；
- Feed 不进入 ActionPolicy provider history；
- checkpoint 不嵌入完整 feed；Shell recovery projection 可按现有 TTL/revoke 规则保存 bounded feed。

持久字段明确分开：feed projection 保存 `block_id/source_event_id/kind/bounded payload`；revision-language projection 只保存被准入的语言 turn identity、role 和 bounded text/option labels。两者都引用 Runtime task revision，但都不能写回、分配或恢复 TaskGoal revision。Snapshot resync 按 source identity 去重，不能按文本相等去重。

### 5.12 状态、command offers 与输入框

`RunStatus` 和 `ControlOwner` 保持正交，不新增 `user_control` RunStatus：

```text
run_status = paused + control_owner = user
→ 用户正在控制界面
```

UnifiedComposer 只由 command offers 决定行为：

| Runtime/public condition | offered/default interaction |
| --- | --- |
| idle | start task |
| running + revise offer | revise task |
| waiting_user + interaction offer | answer interaction；另有“修改整个目标”按钮 |
| waiting_confirmation | approve/reject 按钮；composer 只在 revise offer 存在时修订目标 |
| paused | resume 或 revise |
| user-owned control | 记录 bounded user turn；ReturnControl 后由 Runtime 处理 fresh state |
| terminal | new session/task |

React 不根据 `run_status` 自行创造 command legality。状态文案固定区分：

- `waiting_user`：等待你的回答；
- `waiting_confirmation`：等待操作确认；
- `paused`：任务已暂停；
- `paused + control_owner=user`：你正在控制界面；
- `blocked`：需要处理后才能继续；
- `failed`：任务运行失败。

## 6. 产品 Surface 组合

产品 Shell 不直接把两个都拥有 reset 的 adapter 并列到 `UnifiedWorldEnvironment`。引入一个 browser session 范围的 grouped owner（名称在实现时按现有命名约定确定）：

```text
BrowserSessionSurfaceBundle
├── one physical_environment_id
├── one owns_physical_reset = true
├── one immutable CaptureFrame owner
├── structural offer → existing DomSurfaceAdapter logic
├── visual offer     → existing VisualSurfaceAdapter/provider logic
├── shared capture/acquisition root
├── shared execution surface routing
└── grouped acquire for structural + visual
```

实现可以委托现有 adapter，但从 `ObservationAcquisitionCoordinator` 看必须是同一个 grouped owner。每个 acquisition group 只产生一个 immutable `CaptureFrame{bytes,digest,width,height,viewport,scroll,dpr,zoom,page_generation,episode_id,captured_at}`；structural/visual projection 只能引用该 frame，不能分别重新 screenshot、PNG encode、分配 media identity 或改变 dimensions。这样同次 DOM、bbox、视觉标注、page generation 和 correspondence 才可证明一致。是否把原始 frame 暴露给 model 仍由 projection/profile owner 决定；共享 frame 不等于默认给 ActionPolicy 增加 image payload。

Visual offer 按实际配置发布：

- 无 proposer/grounder/classifier/disambiguator 时，不声明相应 purpose；
- provider availability 本身不触发视觉；
- 显式 RequestObservation 可触发相应 purpose；
- Runtime 仅可基于稳定 owner fact（如 structural coverage truncated、明确 postcondition unresolved）做 adaptive visual escalation；
- 重复动作、相似文案、任务名、页面关键词或“模型撞墙”不得触发 VLM；
- 每次自动 escalation 必须记录 reason code、purpose、provider call count 和 latency，供 A/B 评估。

“新 visual offer 可能新增 VLM 调用”不是指 offer 发布时就调用模型。Offer 只是能力广告；现有 adaptive escalation 可能在 structural coverage 为 `TRUNCATED` 等稳定条件下产生视觉 need。过去对应 purpose 未被 offer 时，该 need 无法路由；接入新 offer 后，它可能变成一次真实 provider call。因此 compatibility profile 必须保留原 offer 集与 escalation 配置，新 purpose 先由显式 capability/profile 启用；不能仅以“Agent 没有显式 RequestObservation”推断调用数不变。

## 7. 分阶段实施计划

### Phase 0 — 冻结基线与防回归门禁

目标：在生产合同变化前建立可比较基线；不改 Runtime 行为。

工作：

1. 记录 exact git SHA、tree digest、Python/BrowserGym/Playwright/provider profile、MiniWoB URL/source 和模型配置，禁止打印 key。Compatibility baseline/candidate 优先使用 clean worktree；若必须使用 dirty tree，单独保存 redacted patch digest/tree digest，不能只记录 `dirty=true`。
2. 保存当前 pytest collection node manifest、focused/full provider-free 结果和 generated SDK diff 状态。
3. 固定原 benchmark manifests、case IDs、seeds、perception profiles、model IDs 和 evaluator codec；保存每个 protected profile 的完整 model-visible ToolCatalog JSON/digest、offer 集与 escalation 配置；实现工作不得修改这些输入来取得通过。
4. 从当前已通过 live evidence 中列出 protected witnesses；从 `docs/benchmark.md` 列出仍 reopened/invalid 的任务，禁止把它们错误当成候选回归。
5. 建立两个 live 比较目的，等待用户授权后执行：
   - compatibility arm：candidate code + 原 benchmark composition/profile；证明旧能力没有被新 UI/visual contract意外改变；
   - capability arm：candidate code + 明确视觉能力；衡量新增视觉收益和成本。
6. 每个 protected runner 必须在 composition boundary 显式注入实际 baseline 使用的 perception profile。该值从既有有效 evidence/run 配置解析并固化，不能把仅存在于测试常量、但 runner 未接线的 `PRIMARY_*` 名称当作事实。
7. 扩展 benchmark run identity/attestation，保存 redacted resolved runtime config：provider/model、vision provider/model、perception profile、`ObservationToolExposureProfile` ID/digest、reasoning settings、turn/token/time budgets、FinalResponse codec、ToolCatalog JSON digest、offer/escalation config digest。Attestation 比较 resolved digest，不根据 profile 名称猜配置相同。
8. 在实现前根据 baseline 重复样本和当前产品预算预登记 paired live 接受阈值：success/safety 是硬门；policy/provider call count 不允许无解释增加；token/latency/visual-call-rate 的绝对或相对容差写入 machine-readable comparison config，不能在看到 candidate 结果后调整。

退出条件：基线 tree/config/tool-schema 身份、测试清单、protected witnesses、预登记容差和已知 reopened 项均可机器读取或在 evidence 目录中定位；无 live run 被擅自启动。

### Phase 1 — Canonical observation query 与迁移面

Owner：`agent/decisions.py`、`world/observation_needs.py`、TurnPacker/Catalog binding、CoreLoop 的机械转换。

工作：

1. 冻结 `ObservationPurpose` 语义映射并增加 `POINT_GROUNDING`、`VISUAL_CHANGE`；`EFFECT_VERIFICATION` 保持 Runtime-only，不增加同义 public purpose。
2. 将模型工具 schema 改为 purpose-specific closed `oneOf`；每轮只发布 capability/profile、current World 和 DeliveryManifest 共同允许的 variants，variant 内使用 `subject_refs[]`/optional candidate refs/predicate/max_results。
3. Catalog 一次性解析 E-ref 到 canonical IDs，并由 Runtime 分配 query ID。
4. `RequestObservation` 改为 batch internal contract；CoreLoop 只构造一个或多个 typed ObservationNeed。
5. 迁移 ToolReturn、history sanitization、step summary、Monitor、checkpoint serialization、CLI 和测试 fixture。
6. internal decision 只保留 batch 新形式；历史 checkpoint 允许版本化只读解码。若 compatibility profile 保留旧 model-facing 单 subject projection，它只能在 Catalog binding owner 转成一元素 `subject_ids[]`，不得形成第二 CoreLoop/provider path；capability profile 只发布新 batch schema。
7. `ObservationOffer.supported_purposes` 由实际 configured provider ports 显式构建；演进现有 Catalog compiler/need predicate/schema builder，不新建第二动态工具 registry。
8. 定义 typed `ObservationToolExposureProfile`；composition 每 session 选择一次，TurnPacker 显式传给 Catalog，profile digest 进入 `catalog_id`、trace 和 benchmark run attestation。

性质测试：

- 1..32 refs round-trip 且保持顺序/唯一性；
- stale/unoffered/mixed-kind ref 在 Catalog binding 前 typed reject，provider call count 为零；
- purpose-specific 字段组合穷尽验证；
- provider-port/purpose、World applicability、manifest ref/cardinality 和 capability profile 的组合生成测试；
- 无 applicable purpose 时 tool 缺席；只有 classifier 时只有 `VISUAL_PROPERTY`；tool 未选择时 provider 零调用；
- query ID 不受模型参数伪造；
- one decision → one bounded WorldObservationRequest；
- default compositions 未配置新 provider 时 observation offers/tool purposes 不扩张。

退出条件：所有 `RequestObservation` 生产者、消费者、checkpoint 和投影只使用新 internal contract；无 CoreLoop provider-specific branch。

### Phase 2 — Predicate batch vertical slice

Owner：visual predicate classifier port、BrowserGym/browser bundle SurfaceAdapter、SurfaceObservation projection、acquisition outcome。

工作：

1. 先只闭合 `VISUAL_PROPERTY`，不同时实现所有 evidence kinds。
2. BrowserGym visual offer 仅在 classifier 存在时声明 `VISUAL_PROPERTY`。
3. 从 request subject IDs 选择当前可见 structured candidates；生成 provider-call-local refs 和 marked screenshot。
4. 调用现有 batch predicate classifier；对每个输入产生 evidence 或 unknown item。
5. provider exception 转为 typed failed outcome；部分 unknown 不抛异常。
6. observed predicate facts 通过 alignment proposal 进入 WorldFusion；unknown/failed 只进入 ToolReturn。
7. provenance 在 adapter call boundary 组装并进入 Trace/Labs 私有记录；公共 World 只保留必要 evidence lineage。

测试：

- 1、2、32 candidates；
- true/false/unknown 混合并逐 ref exactly once；
- omitted/duplicate/unoffered ref structured failure；
- classifier 未配置时 offer 不出现且零调用；
- unknown/failed 不产生 StateFact、ActionBinding 或 completion；
- valid observed fact 与同次 structural target 对齐；
- conflict predicate 不进入 canonical target state；
- same World ToolReturn 给下一轮 ActionPolicy，run 保持可继续；
- observed target refs 经 exact after-World `ModelTurnDelivery` 进入 readable manifest；只有与 sibling ActionSpace 相交的 `target_ref + verbs` 进入 executable Catalog route；unknown/stale 零 route；
- latency/provider failure counters 正确且不泄露 secrets。

退出条件：一个 provider-free fake classifier vertical test 从 ActionPolicy ToolCall 走到下一轮 ToolReturn；默认 benchmark composition 的 provider call 数和 action path 不变。

### Phase 3 — Disambiguation、region、point、text、spatial、change

按 evidence kind 顺序逐个闭合，每个 kind 达到 Phase 2 同等级 vertical gate 后再进入下一个：

1. `TARGET_DISAMBIGUATION`：只在 supplied candidates 中选 referent；删除 `visually_selected` 误投影。
2. `ENTITY_DISCOVERY`：atomic query + max_results；matched/unmatched/ambiguous/conflict 显式。
3. `POINT_GROUNDING`：真实传入 configured point grounder；删除整体目标下一动作 prompt。
4. `TEXT_IN_IMAGE`：bounded subject/region OCR evidence；不把 screenshot text 当指令。
5. `SPATIAL_RELATIONSHIP`：只比较 supplied subjects；关系 unknown 不猜。
6. `VISUAL_CHANGE`：只有同 episode before/after lineage 存在时进入 Agent Catalog；VLM 不声明 page generation。Runtime-owned `EFFECT_VERIFICATION` 继续走内部 typed need，不进入 Agent Catalog。

每个 kind 的共同门禁：

- provider request 不含完整 TaskGoal/GoalPlan/history；
- no immediate dispatch；
- ambiguous/conflict/unknown 零 binding；
- unmatched 只有在 visual-only binding 合同满足时可执行；
- stale observation tool call/catalog/request 必须在 acquisition admission 时拒绝，visual provider 调用数为零；已经由合法旧 acquisition 产生的 point/binding 若随后因 screenshot/page/viewport 变化而 stale，则由既有 Binder/Executor currentness 在 dispatch 前拒绝，不能把“provider 曾经合法调用过”误报为零调用违规；
- no benchmark/task/site string in production prompts or routing；
- provider-free conformance 和 focused benchmark test 通过。

### Phase 4 — 产品 browser Surface bundle

Owner：`external/interaction-shell/backend/.../deployment_app.py` 的部署组合和可复用 browser grouped Surface owner。

工作：

1. 引入同一 BrowserSession 的 grouped structural/visual owner；保持唯一 physical reset owner。
2. 复用现有 DOM capture/dispatch 和 visual provider adapters，不把截图/DOM 协调放入 CoreLoop。
3. 部署配置显式创建 proposer/grounder/disambiguator/classifier；缺失能力 typed unavailable，不 fallback 到本地猜测。
4. structural-only capture 继续是默认低成本路径；visual 只由选中的 typed need 激活。
5. protected Viewer 继续展示同一 browser lease，不创建第二 browser/session/capture authority。

测试：

- exactly one reset for shared browser；
- structural-only request 零 visual provider call；
- grouped request 使用同一 acquisition root/page generation；
- grouped multi-need 只捕获/编码一个 immutable frame，structural/visual media 引用同一 digest/dimensions/viewport/page/episode；
- one adapter close releases exact browser once；
- DOM dispatch 后 fresh grouped capture 与原有 causal `dispatch → stable World → StepResult` 不变量一致；
- Viewer/takeover/return-control currentness 与视觉 binding 相互隔离；
- Shell open without visual configuration retains current DOM behavior。
- protected default W2/profile 的 media count、source offers 和 model image-input count 与 baseline exact parity；共享 capture 本身不得把 screenshot 注入 text-only policy turn。

退出条件：真实产品 session 可在无 VLM 配置下保持现有行为，并在显式视觉配置下完成一条 provider-free fake visual vertical flow。

### Phase 5 — InteractionRequest/Response 和 PublicArtifact

Owner：ActionPolicy ToolCatalog/decision、GoalCompiler NeedsInput projection、PublicSession command admission、finalization boundary。

工作：

1. 定义 closed InteractionRequestDraft/OptionDraft/FieldDraft 与 admitted Request/Response；draft 无 ID，Core transition admission 分配 request/option/field identity。
2. 将 GoalCompiler NeedsInput、ActionPolicy AskUser、public pending question 和 answer command 一次性迁移。
3. response admission 验证 request identity、response kind、option/field domain 和 expected revision/status。
4. Option selection 进入 existing user response/TaskGoal revision input；不生成 action。
5. `public_intent` 作为 decision sidecar 随 StepResult 投影。
6. FinalResponse 保留原 content/codec 路径；新增可选 artifact draft sidecar。
7. finalization admission 验证 evidence refs；PublicSession 分配 public artifact identity；实际 file/link 只来自 receipt/artifact owner。
8. checkpoint/history/public CLI/Shell command 全面迁移；历史 checkpoint 只读兼容。

测试：

- 四种 request/response kind 穷尽 round-trip；
- unknown/duplicate option/field typed reject，零 ActionPolicy/Executor side effect；
- response 只造成 consecutive TaskGoal revision 和既有 GoalCompiler trigger；
- confirmation 仍只走 approve/reject button，不被 InteractionResponse 代替；
- public_intent 不进入 completion/evaluator/current World；
- FinalResponse codec 对现有 plain text 和 WebArena verified schema byte-for-byte保持原行为；
- artifact draft 不调用 evaluator、不创建 link、不证明 success；
- materialized download 只引用 owner receipt；
- task evaluator 仍是唯一 terminal success owner。
- provider-free target-loop 两臂覆盖 artifact absent/present：传给 WebArena/native evaluator 的 bytes、STOP/evaluation ordering 与 terminal outcome exact 相同；artifact 只作为 versioned additive sidecar 在 case evidence SQLite/JSON export round-trip；artifact/report serialization failure 归类为 reporting failure，不得重分类为 GUI case failure。

退出条件：现有 benchmark final response codec、AskUser/answer lifecycle、checkpoint recovery 和 confirmation invariants 均有迁移测试；只有一个 admitted internal interaction/finalization contract。Compatibility Catalog 若省略新增字段，只是同一 binding owner 的受控旧字段投影，不形成第二 Runtime path。

### Phase 6 — PublicSession feed 和 Shell 持久投影

Owner：Runtime public session 提供 typed source facts；Shell manager 只物化 bounded presentation/revision-language projection。

工作：

1. PublicSession 将 accepted command、committed StepResult、interaction、confirmation、revision、control 和 terminal outcome 投影成 closed source records。
2. `RuntimeActivity` 必须根据 receipt/outcome，而不是仅按 decision kind 宣称“完成了交互”。
3. PublicSession 分配 stable source identity；Shell 只确定性派生 presentation block ID，按 `(source_event_id, kind, ordinal)` exact replay 去重，并按现有 TTL/revoke 生命周期持久化 bounded feed。
4. revision conversation 只选择语言相关 blocks；activity/evidence/control 不进入 compiler。
5. snapshot/event schema 版本升级；OpenAPI/Hey API generated contract 重新生成。
6. 普通 feed 排除 provider/token/raw trace/JSON；Labs 保留开发者证据面。

测试：

- command/event replay 幂等且 block order 与 event cursor 因果一致；
- snapshot resync 不重复 append；
- Shell restart/recovery 恢复 bounded feed，但不改变 Runtime status/task/evaluator；
- failed/not-sent/sent-unknown action 不显示为 completed interaction；
- revision diff 只从 committed old/new TaskGoal 结构字段确定性生成；自然语言不可解析时显示“目标说明已更新”，不猜语义；
- public evidence summary 只引用可公开 evidence refs；
- generated schema/validator/client 无手写 mirror。

退出条件：删除 React 硬编码 Agent 回复所需的所有 public blocks 已由 owner 提供；feed recovery 不成为 checkpoint 或 control authority。

### Phase 7 — 通用前端

Owner：generated contract + pure view model + React presentation。

页面结构：

```text
Sessions | Collaboration feed | Live surface
```

组件至少包括：

- `GoalSummary`
- `ConstraintChips`
- `ConversationFeed`
- `ActivityTimeline`
- `EvidenceBadge`
- `OptionSet` / `OptionCard`
- `AttributeList`
- `UncertaintyNotice`
- `RevisionDiff`
- `ConfirmationPanel`
- `ArtifactPanel`
- `SurfaceViewer`
- `ControlBar`
- `UnifiedComposer`

工作：

1. `session/view-model.ts` 对 generated feed union 和 command offers 做穷尽纯投影。
2. `use-shell-session.ts` 继续只使用 generated named SDK/validators；composer 提交 typed interaction response/revision/start command。
3. `shell-app.tsx` 删除硬编码 Agent 回复、字符串状态猜测和 browser-only 标题；右栏统一为 `Live surface`。
4. 普通任务只显示目标、进展、证据、问题、确认、结果和控制；Labs 继续承载 provider/token/raw trace/JSON/benchmark。
5. ProductCard/ShoppingTask 等专属命名不得进入 components/contracts。

测试：

- TypeScript exhaustiveness：新增 feed/request/response/status variant 时编译失败直到处理；
- generated contract check 无 diff；
- waiting_user 与 waiting_confirmation 文案/控件明确区分；
- waiting_user 同时提供回答和修改整个目标；
- paused + user owner 显示用户控制，但不创造新 RunStatus；
- OptionCard 对商品、文件、航班、图表元素使用同一 fixture/schema；
- EvidenceBadge 不显示 selector/coordinate/prompt/provider；
- Labs raw data 不进入 ordinary feed；
- Playwright 覆盖 start、revision、answer、select、confirmation、takeover/return、completion、new session。

退出条件：前端不存在协议 mirror、硬编码 Agent 回复或购物专属组件；所有输入行为由 command offers 驱动。

### Phase 8 — 验证、独立审查和 live benchmark

分三层，不能互相替代：

1. provider-free closure：owner、性质、集成、checkpoint、OpenAPI/generated SDK、前端、文档治理和完整测试通过；
2. independent fresh-context review：不了解实现讨论的审阅者从本文件和代码验证 authority、迁移完整性和 benchmark 门禁；
3. 用户授权的 live benchmark：证明原 benchmark 能力无回归并衡量新增视觉能力。

只有三层均满足对应声明时，才能分别写“implementation complete”“provider-free verified”“live benchmark non-regression verified”。不得合并为一个笼统 closure。

## 8. 完整 causal surface

预计需要检查或修改的 owner，不代表每个文件都必须产生 diff：

### Runtime / Agent

```text
src/affordance_runtime/world/observation_needs.py
src/affordance_runtime/world/acquisition.py
src/affordance_runtime/world/observation_orchestrator.py
src/affordance_runtime/world/contracts.py
src/affordance_runtime/world/fusion.py
src/affordance_runtime/agent/decisions.py
src/affordance_runtime/agent/core_loop.py
src/affordance_runtime/agent/run_state.py
src/affordance_runtime/agent/tool_result_projection.py
src/affordance_runtime/agent/context/step_projection.py
src/affordance_runtime/agent/context/model_turn_delivery.py
src/affordance_runtime/agent/finalization.py
src/affordance_runtime/app/public_session.py
src/affordance_runtime/app/checkpoint.py
src/affordance_runtime/app/runtime.py
src/affordance_runtime/task/revision.py
```

### Model-facing contract

```text
src/affordance_runtime/model/policy/grounded_tool_catalog.py
src/affordance_runtime/model/policy/turn_packer.py
src/affordance_runtime/model/policy/pydantic_ai_bridge.py
src/affordance_runtime/model/policy/perception.py
```

### Visual / BrowserGym / product browser

```text
src/affordance_runtime/surfaces/visual/contracts.py
src/affordance_runtime/surfaces/visual/adapter.py
src/affordance_runtime/surfaces/visual/grounding.py
src/affordance_runtime/surfaces/visual/disambiguation.py
src/affordance_runtime/surfaces/visual/predicate_classification.py
src/affordance_runtime/surfaces/browsergym/environment.py
src/affordance_runtime/surfaces/browsergym/visual_projection.py
src/affordance_runtime/surfaces/browsergym/visual_disambiguation.py
external/interaction-shell/backend/interaction_shell/deployment_app.py
```

### Shell / generated contract / frontend

```text
external/interaction-shell/backend/interaction_shell/contracts.py
external/interaction-shell/backend/interaction_shell/core_runtime_port.py
external/interaction-shell/backend/interaction_shell/conversation.py
external/interaction-shell/backend/interaction_shell/manager.py
external/interaction-shell/backend/interaction_shell/session_registry.py
external/interaction-shell/backend/openapi.json
external/interaction-shell/frontend/src/generated/**
external/interaction-shell/frontend/src/session/command-builder.ts
external/interaction-shell/frontend/src/session/view-model.ts
external/interaction-shell/frontend/src/hooks/use-shell-session.ts
external/interaction-shell/frontend/src/components/**
```

### Tests / benchmark / docs

```text
src/affordance_runtime/benchmarks/target_loop/contracts.py
src/affordance_runtime/benchmarks/target_loop/manifest.py
src/affordance_runtime/benchmarks/target_loop/cases.py
src/affordance_runtime/benchmarks/target_loop/case_evidence_codec.py
src/affordance_runtime/benchmarks/target_loop/runner.py
src/affordance_runtime/benchmarks/target_loop/result_store.py
src/affordance_runtime/benchmarks/target_loop/reporting.py
src/affordance_runtime/benchmarks/target_loop/attestation.py
tests/unit/**
tests/conformance/**
tests/integration/**
tests/benchmarks/runtime/**
tests/benchmarks/surfaces/browsergym/**
tests/architecture/**
external/interaction-shell/tests/backend/**
external/interaction-shell/tests/architecture/**
external/interaction-shell/frontend/tests/**
docs/architecture.md                 # 实施后状态 authority
docs/benchmark.md                    # 验证后证据 authority
```

## 9. Benchmark 不回归合同

### 9.1 必须保持不变的能力与输入

在 compatibility arm 中必须保持：

- 同一个 `CoreAgentLoop`、RunState、ActionPolicy provider history 和 GoalCompiler lifecycle；
- benchmark task manifests、case IDs、seeds、task text、success criteria、evaluator/native verifier；
- action capability registry、Catalog → Binder → Executor path；
- 每个 runner 在 composition boundary 实际解析并显式注入的 perception profile；常量名本身不作为已接线证据；
- provider/model ID、wire capability、reasoning settings、turn/token budgets；
- 除下述显式迁移项外的 model-visible ToolCatalog、offer 集和 escalation 配置；
- final-response codec 和 native STOP/evaluation ordering；
- dispatch → stable capture → fresh World → StepResult causal invariant；
- sent_unknown 零重放、stale 零 provider call、confirmation、forbidden effect 和 cleanup 安全语义；
- evidence/report schema，除非本计划显式添加版本化 additive metrics。

不得通过以下方式取得“无回归”：

- 移除原 case、改变 seed、放宽 evaluator、增大任意预算或超时；
- 为已知任务添加视觉/动作 prompt 特化；
- 用新增 UI 展示或 artifact 代替 native evaluator success；
- 把 provider/environment failure 统计成 task success；
- 只选择新增视觉更擅长的 case；
- 用修改后的同一实现同时充当 baseline 和 candidate。

本计划允许的 model-visible schema delta 必须在 Phase 0 形成 closed allowlist：

1. model-facing `request_evidence.subject → subject_refs[]` 和按 purpose 判别的 query variant；对应 internal `RequestObservation.subject_id → subject_ids[]`；public tool name 保持不变；
2. `AskUser(question, requested_fields)` → `InteractionRequestDraft` 的 request/option/field closed variants；
3. `FinalResponse(content)` 增加 optional `PublicArtifactDraft` sidecar；
4. 各 decision 可选的 bounded `public_intent` sidecar。

这四项不能假称与 baseline 输入完全相同。每项都必须保存前后 Catalog JSON/digest、catalog bytes 和 tool-schema token count，并证明不存在 allowlist 外工具漂移。Binding/round-trip/provider-free properties 证明旧用法可表达且语义保持；若 protected cohort 会看到这些工具，则“策略能力未受影响”只能由 baseline/candidate paired live evidence 支持。为了隔离 rollout，Catalog owner 可以让 compatibility profile 只投影旧字段子集并在 binding boundary 编译成唯一新 internal contract；这不是第二 ActionPolicy 或第二 internal decision algebra。若选择让 compatibility profile 直接看到新 schema，则必须把 schema delta 纳入 paired live 输入，不能再声称 exact model-input parity。新增 visual purpose/offer 只在 capability arm 显式启用。

### 9.2 Provider-free exact gates

每个 phase 至少运行其 focused tests；Phase 0 先从 CI、`docs/benchmark.md` 和现有 evidence 固定当前 canonical green suites，再在 candidate 上运行相同命令。典型根目录命令为：

```bash
.venv/bin/ruff check .
.venv/bin/pytest tests
```

当前文档已经记录的非绿 gate 不能在本计划中伪称为退出前提。`mypy src` 先保存 exact baseline，candidate 要求 changed surface 零错误且全量 error set 不增加；若要把全量 mypy 变绿，必须作为显式 prerequisite phase 实施和验证，不能靠本 UI 计划顺带宣称。

Interaction Shell 运行：

```bash
cd external/interaction-shell
backend/.venv/bin/pytest tests/backend tests/architecture
cd frontend
npm run check:generated
npm test
```

还必须通过：

- documentation governance；
- generated OpenAPI/SDK regenerate-and-diff；
- target boundary/legacy path/generalization redline tests；
- exact pytest collection/result attestation 要求的现有检查；
- 新增 observation/interaction/feed closed-union property tests；
- default no-visual configuration 零新增 provider call 的 vertical test；
- protected profile ToolCatalog/offer/escalation snapshot：除 closed schema-delta allowlist 外无漂移；compatibility profile 不出现新增视觉 purpose。

Provider-free parity 的验收是确定性的：canonical green suites 收集完整且零失败；已知非绿 suite 的 collection/outcome/error baseline 不恶化；原固定 benchmark runner property tests 不删不弱；新增合同 properties 通过。

### 9.3 Live compatibility arm

只有用户授权后执行。Baseline 必须来自候选改动前的 exact clean commit/worktree，candidate 来自改动后的 exact clean commit/worktree；若有不可避免的 dirty state，run identity 必须携带 tree/patch digest。二者加载同一 `.env` 后显式覆盖相同 benchmark profile，不打印 secrets，并在启动前 attestation resolved runtime config digest、ToolCatalog digest、offer/escalation digest 与预登记 comparison config。

运行顺序：

1. 检查固定 BrowserGym interpreter、MiniWoB source 和 `127.0.0.1:18888/miniwob/` 健康；
2. 在 baseline commit 运行受保护的原 benchmark cohort；
3. 在 candidate commit 使用相同 cases/seeds/provider/model/budgets 运行 compatibility arm；
4. 比较 per-case outcome、native evaluator result、policy/provider call counts、tokens、latency、invalid arguments、grounding gaps、安全 metrics 和视觉调用数，并应用 Phase 0 预登记、不可事后修改的容差；
5. 任何差异必须归因到具体 owner transition，不能仅用 aggregate success 掩盖；
6. 再运行一个未用于开发的 held-out case/cross-domain cohort。

最低接受条件：

- 原 protected successful witnesses 在 candidate compatibility arm 仍由 native evaluator success；
- 原安全不变量保持零违规：stale provider call、duplicate unknown replay、forbidden effects、fallback、cleanup failure；
- 未配置新增视觉 provider 的 case 不新增 visual provider call；
- final response codec、tool grounding、dispatch receipt 和 terminal ordering 无回归；
- aggregate 成本变化有逐项解释，不能由重复 VLM 或重复 ActionPolicy 调用造成；
- catalog bytes/tool-schema tokens 只允许 closed schema-delta allowlist 中预登记的变化；compatibility profile 若选择旧字段投影则要求 exact parity；
- token/latency/visual-call-rate 满足 Phase 0 machine-readable comparison config；超过预登记容差即 regression，不能仅写“已有解释”后放行；
- 若模型随机性导致 outcome 不一致，增加同配置重复/paired evidence，不能直接选择最好一次；
- 发现 regression 时停止 capability arm，修复 owner 后从 provider-free gate 重新开始。

由于模型和外部环境可能非确定，计划不得承诺“单次 live run 数值完全相等”。可证明的是：确定性合同 exact parity；受控配置下的 protected witness parity；以及基于 paired evidence 的性能非回归判断。

### 9.4 Live capability arm

compatibility arm 通过后才能执行。新增视觉能力使用相同 ActionPolicy 和任务合同，仅改变显式 perception/provider capability。至少覆盖：

- ScreenSpot point-in-box；
- batch predicate accuracy 与 per-ref coverage；
- unknown/ambiguous calibration；
- screenshot/page generation 改变后的 stale point refusal；
- MiniWoB adaptive visual cohort；
- 跨域通用任务：购物候选、图表、图片文字、SVG、同名控件，以及文件列表/地图/远程桌面中至少一种。

报告分开呈现：success、safety、provider availability、tokens、latency、visual call rate、unknown rate、calibration。视觉 arm 失败不能反向修改 task fixture 或引入生产特化。

## 10. 风险与控制

| 风险 | 触发机制 | 控制/验证 |
| --- | --- | --- |
| 新 visual offer 导致隐式额外 VLM 调用 | truncated structural coverage 自动 escalation | capability-conditional offer；reason-coded call；default no-provider zero-call test；A/B call-rate gate |
| 动态 observation tool 过度暴露 | 用静态 purpose allowlist 或宽泛 visual 默认值生成 schema | Catalog 每轮做 provider×World×Manifest×profile 交集；无 variant 则 tool 缺席；Catalog digest/token gate |
| 动态 tool 变成第二 registry | provider/Surface 各自向模型注册工具 | 只有 `GroundedToolCatalog` 生成 public spec；provider ports 保持 Runtime-private |
| structural/visual 重复截图与 media | 两个 projection 各自 screenshot/encode/发布 | grouped immutable CaptureFrame owner；one-frame/digest property；default model image-input parity |
| CoreLoop 承担视觉语义 | 按 evidence kind 增加分支 | 只接受 typed outcome/World；provider-specific routing留在 SurfaceAdapter |
| query 三份真相 | RequestObservation/ObservationNeed/provider request 都可独立表达语义 | 明确单向 compile；Runtime IDs；purpose mapping property test |
| partial unknown 丢失 | 顶层 Observed/Unknown 三选一 | Completed(items evidence/unknown) + Failed；per-ref exactly-once |
| disambiguation 被误写成 UI selected | provider choice 投影为 state fact | DisambiguationEvidence 与 PredicateEvidence 分离；删除 `visually_selected` 旁路 |
| visual binding 跨截图执行 | point 未绑定 capture/page | provenance + existing currentness；stale zero-dispatch property |
| Option 绕过 ActionPolicy | option_id 直接映射 binding | response 只进入 TaskGoal revision；下一轮重新选 action |
| transcript 成为第二 TaskGoal | Shell feed 被当作 current state | language/feed 分离；Runtime TaskGoal始终注入 compiler；feed不可回写 |
| run status/control owner 合并 | 新增 `user_control` status | 保持正交字段；command offers 驱动 UI |
| artifact 改变 benchmark final response | structured artifact 进入 codec | content/codec路径保持；artifact为sidecar；codec parity tests |
| UI 重建 Runtime 状态 | string label/field组合判断 | closed unions + generated validators + exhaustive view model |
| docs 文件使 full gate 失败 | 新文档未加入治理清单/README | 同步 documentation governance 与 README；focused governance test |
| 为旗舰购物任务特化 | fixture/文案反向进入生产 | architecture redline search + cross-domain same-contract tests |

## 11. 独立读者审核协议

实施计划和每个 phase 完成后，都要求一个没有本轮讨论上下文的独立审阅者只读取：

1. 本文件；
2. `docs/architecture.md` 与 `docs/benchmark.md`；
3. phase diff 和相关测试输出；
4. 不读取作者的口头解释或未持久化结论。

审阅者必须回答：

1. 当前事实、提案、已实施状态和 live benchmark 证据是否被清楚区分？
2. `RequestObservation → ObservationNeed → provider request` 是否只有一条单向 authority 链？
3. Visual observed/unknown/failed/partial batch 是否闭合，unknown 是否可能被写成 GUI fact？
4. correspondence、visual-only identity、conflict 和 stale currentness 是否复用现有 owner，而非新建 reducer？
5. point/disambiguation 是否仍有“替 ActionPolicy 选择下一动作”的路径？
6. Interaction option 是否可能绕过 Catalog/Binder/Executor？
7. PublicArtifact 或 public_intent 是否可能影响 native evaluator 或宣称完成？
8. transcript/feed、TaskGoal、RunStatus/ControlOwner、checkpoint/history 是否保持独立 authority？
9. 原 benchmark manifests、profiles、codec、evaluator、安全不变量和 causal step 是否有明确保护门？
10. provider-free、live compatibility 和 live capability 结论是否被诚实分开？
11. 迁移面是否遗漏 checkpoint、ToolReturn/history sanitization、generated SDK、Shell recovery 或 docs governance？
12. 是否存在购物、站点、task ID、selector、固定顺序或输出名生产特化？
13. 七种视觉 purpose 是否只是同一个动态 `request_evidence` 的 current variants，并绑定为 internal `RequestObservation`；ToolCatalog 是否仅根据 configured ports、fresh World、exact DeliveryManifest 和 capability profile 发布适用 schema，并保证 offer/compile 本身零 provider call？

审阅结论只允许：

- `APPROVE`：未发现阻塞问题，所有已知风险有 owner 与 falsifiable gate；
- `REQUEST_CHANGES`：列出具体 owner、违反的不变量、可复现路径和所需验证；
- `BLOCKED`：缺少必要代码/evidence，不能判断；不得把缺证据写成通过。

作者必须逐项记录审阅意见、修订位置和 disposition。没有 fresh-context `APPROVE` 不能进入 live benchmark non-regression 声明。

## 12. 最终退出条件

只有以下条件同时满足，才可把本计划标记为完成：

1. 三套通用合同（visual query/result、interaction request/response、public feed/artifact）均是 closed typed algebra；
2. 所有 producer/consumer、exceptional path、checkpoint/recovery、history/ToolReturn、generated contract 和 UI 均迁移；
3. CoreLoop 保持单一 orchestration loop，没有 provider/UI/任务语义；
4. current World、TaskGoal、ToolCatalog、Binder、Executor、TaskEvaluator、RunStatus/ControlOwner 各有唯一 owner；
5. matched/unmatched/ambiguous/conflict/unknown/stale 的行为通过 owner-level properties；
6. dynamic `request_evidence` 只有本轮适用 variants，无 purpose 时整个 tool 缺席，offer/catalog compilation 保持零 provider call；no-visual/default benchmark composition 行为与 provider call profile 受保护；
7. full provider-free、Shell、generated SDK、frontend、docs governance gates 通过；
8. 独立 fresh-context review 得到 `APPROVE`；
9. 用户授权后的 live compatibility arm 证明原 protected benchmark 能力无回归；
10. 用户授权后的 capability arm 提供新增视觉/交互能力的跨域 benchmark evidence；
11. 实施状态同步到 `docs/architecture.md`，验证证据同步到 `docs/benchmark.md`；本文件不自行宣称 closure；
12. 没有依赖任务名、站点、固定 selector、页面文案、action ID、输出名或购物字段的生产分支。

如果第 9 项尚未获得授权或尚未执行，可以声明“implementation complete / provider-free verified”，但必须保持“live benchmark non-regression unverified”，不得宣称不影响原 benchmark 能力已经被实证证明。

## 13. 实施记录模板

每个 phase 在实际执行时使用以下记录，不在本计划中预填成功：

```text
Phase:
Implementation commit/worktree:
Owners changed:
Contracts migrated:
Focused tests:
Full provider-free result:
Generated contract diff:
Benchmark inputs changed: yes/no（必须解释）
Live benchmark authorized: yes/no
Live evidence:
Independent reviewer:
Review disposition:
Open risks/blockers:
Architecture status update:
Benchmark status update:
```

## 14. 独立读者审核记录

审核日期：2026-08-28。两位审阅者均以 fresh context 工作，只读取本文件、状态 authority 文档、相关代码和测试/benchmark 合同；都未修改文件，也未运行 live benchmark。

### 合同与 owner 审核

第一轮 disposition：`REQUEST_CHANGES`。发现并要求修订：

- observation input 缺少按 purpose 的判别代数和 atomic query 来源；
- VisualEvidence/unknown/failed 缺少无损 `ObservationQueryOutcome → StepResult → ToolReturn` 载体；
- Interaction draft/admission identity 与 field/value algebra 未分开；
- PublicSession source identity 与 Shell presentation block identity 混淆；
- observation ToolReturn 的 current E-ref 未闭合同轮 `ModelTurnDelivery → DeliveryManifest → ToolCatalog` admission；
- discovery/no-candidate point 的 scope-level unknown 缺少可编码 locator。

修订位置：5.1、5.3、5.5–5.7、5.10、Phase 2、Phase 6 和完整 causal surface。最终复核：12 个审核问题全部 `APPROVE`；未发现仍会导致实现者分叉、重复投影或第二 authority 的缺口。

### Benchmark 非回归审核

第一轮 disposition：`REQUEST_CHANGES`。发现并要求修订：

- runner 未显式证明实际 resolved perception/provider/model 配置相同；
- model-visible schema delta allowlist 只覆盖 observation，遗漏 interaction/final artifact/public_intent；
- structural/visual capture 可能重复 screenshot/encode/media；
- 计划错误地把当前非绿的全量 mypy 当作 green exit gate；
- PublicArtifact 缺少 target-loop codec/persistence/reporting vertical。

修订位置：Phase 0、Phase 4、Phase 5、完整 benchmark causal surface、9.1–9.3 和风险表。最终复核：`APPROVE`；五项均已有唯一 owner、machine-readable identity 或 falsifiable gate。

### 动态 observation tool 增量审核

用户要求七种视觉 purpose 符合“动态 tool、仅在当前可用时出现”后，计划新增 5.2，并由第三位 fresh-context 审阅者对 public/internal tool identity、rollout profile、purpose filtering、两级 admission、stale 语义和 benchmark compatibility 做增量审核。

第一轮 disposition：`REQUEST_CHANGES`。审阅发现并要求修订：

- active capability/profile 没有 typed owner 或 frozen snapshot，Catalog 可能被迫直连 Surface/provider registry；
- Catalog binding 与 acquisition/Surface currentness 的二次校验 owner 混淆；
- stale observation request 的 provider-zero-call 与已经合法产生 point 后的 stale dispatch 拒绝被混写；
- 文档误把现有 public tool `request_evidence` 写成 `request_observation`，会制造未登记 tool rename 和 benchmark schema delta。

修订位置：owner 表、5.2、Phase 0、Phase 1、Phase 3、完整 causal surface、9.1、独立审核问题 13 和最终退出条件。最终复核：`APPROVE`。Public tool 保持 `request_evidence`，Catalog binding 后产生 internal `RequestObservation`；`ObservationToolExposureProfile` 每 ActionPolicy session 冻结并由 TurnPacker 显式传入；Catalog 与 acquisition/Surface 使用两个 owner 连续 admission；offer/catalog compilation 保持零 provider call。

审核结论只批准本计划的清晰性和充分性。它不表示代码已经实施，也不表示 live benchmark non-regression 已验证；后者仍必须取得用户单独授权并通过 9.3 的 paired baseline/candidate evidence。

# Coordinator 局部瘦身与行为修复优先级审查归档

日期：2026-07-31  
性质：外部审查决议归档；与后续实现证据共同构成 SAR-9 closure 输入。  
原始输入：`54f23945-fa2a-43b9-817f-ce2b87cf049c/pasted-text.txt`（491 行）。

## 审查结论

```yaml
coordinator_file_slimming: successful
control_flow_decomposition: successful
runtime_architecture_purification: incomplete
blocks_current_behavior_repairs: false
```

巨型 Coordinator 已被拆开，主循环的 budget、perception、current-state progress、task plan、planning、contract、preflight、execution、verification、progress/failure 顺序已经可读。该成果足以冻结继续拆文件，但不能宣称 Runtime 已完成架构纯化。

未完成项包括：phase 仍可能是可变的小 Coordinator；Coordinator 曾直接理解大量 phase 私有结果；StateKernel 仍混有历史、诊断、缓存和兼容字段；PlannerDecision、旧 PlannerPort、PlannerContext 与 fail-open scope resolver 等兼容路径尚未全部退出默认路径。

## 行为故障优先级

审查将 fresh 30x2 的 48 个失败归为：30 个 target unresolved、9 个 no feasible ActionChoice、2 个 no active-step ActionChoice、3 个 TaskPlan action-instruction、1 个 Intent coverage、3 个 progress evidence credit/liveness。当前没有证据把这些归因于 Executor。

执行顺序冻结为：

1. 修复 3 个 progress credit/liveness 闭环。
2. 建立真实 planning/post-action 诊断，区分 root failure 与 terminal envelope。
3. 用 canonical typed semantics 解决 ActionChoice 边界，而不是恢复自由动作生成。
4. 修复 TaskPlan/Intent admission。
5. 每个行为单元守住 clean 6x2，再在规定节点运行 fresh 30x2。
6. 主要语义簇关闭后再完成兼容删除与剩余纯化。

## 冻结项

- 不再新增顶层 phase 或从 `run_sync()` 搬一段代码到新文件。
- 不以 Coordinator 行数下降替代 orchestration cluster、依赖边、writer 数和兼容路径的实际下降。
- 不在同一切片混合大规模架构搬迁和语义行为修改。
- 不用更多 facade、adapter、微切片 YAML 或 forbidden-token 测试代替旧默认 owner 的物理删除。

## 当前 HEAD 校准

基线 revision：`0d8a4287975b5ac44ac7695c7fa6ece63041fd20`。当前 `coordinator.py` 约 272 行，已低于审查中基于旧 revision 的 647 行；当前已有共享 `stage_protocol.py` 和唯一提交边界 `runtime_committer.py`，旧 phase 模块也已有一批被删除。旧行数和旧模块清单只作为历史证据，不作为要求重新创建或重新迁移这些结构的理由。

仍然有效的规范要求是：五个顶层 stage、一个 State/Trace writer、stage 间零 import、默认路径零兼容 adapter、StateKernel 不保存完整历史、行为门真实通过。

## 决议状态

```yaml
accepted:
  coordinator_decomposition: true
  stop_phase_expansion: true
  behavior_before_remaining_consolidation: true
held:
  sar_9_full_closure: true
  promotion: true
```


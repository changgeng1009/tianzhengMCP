# MCP NextGen 接管摘要

## 最终结论

- 阶段：`MCP-UPGRADE-HANDOFF`
- 最终状态：`MCP_UPGRADE_HANDOFF_PARTIAL`
- 安全裁决：`CONDITIONAL_NEXTGEN_BASELINE_ONLY`，风险等级 `HIGH`
- 协议版本：`1.0.0`
- 当前后端边界：`MOCK-only`
- Legacy adapter：`DISABLED_CONTRACT_ONLY`
- `production_d1_allowed=false`

DeepSeek 实验项目不是 Git 仓库，是纯 Python 五层原型；无 .NET 项目、真实 AutoCAD 进程内插件、COM、天正接口或真实 DWG backend。原始 `pytest -q` 实测为 75 collected、69 passed、6 failed，README 的 76/76 声明未复现。

五层裁决为：Layer A、B、C、E `ACCEPT_WITH_ADAPTATION`；Layer D 实验实现因 resume 重放、批次重复副作用、幂等、journal/checkpoint 和审批缺陷被 `REJECT`。正式项目未整体复制实验代码，而是在 `mcp_nextgen` 建立隔离、版本化、Mock-only 基线。

## 已接入基线

| 区域 | 当前状态 | 关键限制 |
|---|---|---|
| Protocol/Schema | 版本 `1.0.0`，12 个核心结构，9 个 tool Schema | 只允许版本化 canonical JSON |
| Control Server | import-safe FastMCP 对象，9 tools，不自动启动 | 鉴权尚未接入实际服务入口 |
| Transport | loopback policy、token auth、framing、replay guard | 无 listener，不是可运行 transport |
| Job/Journal/Checkpoint | 新隔离实现，append-only hash chain、原子 checkpoint、动态批次和三计数 | 审批消费、跨进程幂等与全字段互校验仍开放 |
| Mock backend/runtime | 确定性内存模型、失败注入、timeout/cancel/manual-save 模拟 | 不能证明真实 CAD 能力 |
| Legacy adapter | 合同骨架 | 永久 disabled，所有执行方法阻断 |

控制面当前只有 `cad.capabilities`、`cad.documents.list`、`cad.document.inspect` 返回安全 Mock 结果；其余 6 个工具返回 `MOCK_BACKEND_NOT_IMPLEMENTED`。Layer D 和 Mock runtime 库尚未由 dispatcher 接线。

## 测试与安全证据

- NextGen 定向复测：`47/47 PASSED`，该次未读取 DWG。
- 全量回归：`1554/1561`，7 failed、1 warning；状态为 `FAILED_WITH_SAFETY_BOUNDARY_VIOLATION`。
- 全量回归通过 imported `_preflight()` 间接以只读 SHA-256 方式读取了 3 个真实 DWG；无 AutoCAD/COM、无 DWG 修改或保存。该结果不能视为合规全量回归通过，且在关闭 `SEC-FINAL-019` 前不得再次直接运行 `pytest -q`。
- 正式 P4.1 未重跑、未写图、冻结代码未修改。NextGen 的动态 batch、三计数、atomic checkpoint、resume no duplicate 和 automatic dependency 测试不能替代正式 P4.1 验收。

## 仍被阻断

- 持久 single-use approval claim/consume。
- FastMCP 服务入口的不可绕过鉴权、loopback、消息限制与 replay 接线。
- 跨进程 idempotency/job_id 唯一 claim 和 crash window 恢复。
- checkpoint/journal 全字段互校验与多进程 writer fencing。
- Real backend、.NET plugin、COM、天正、Legacy enablement、Production D1。

完整结论见 `artifacts/mcp_upgrade_handoff/mcp_upgrade_handoff_final_report.md`。

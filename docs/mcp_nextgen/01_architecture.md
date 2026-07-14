# MCP NextGen 架构

## 目标与现状

目标架构是：

```text
AI / Codex
  -> Python MCP Control Server
  -> Local authenticated JSON-RPC
  -> AutoCAD in-process .NET plugin
  -> ICadBackend / ITianzhengBackend
  -> AutoCAD / Tianzheng
```

本阶段只实现左侧的隔离协议、import-safe 控制面、transport 合同，以及纯内存 Mock/Layer D 基线。实际 local listener、.NET plugin、Real backend 和天正接口均未实现。

## 当前组件

```text
mcp_nextgen/
  control_server/  FastMCP 注册与严格 dispatcher
  protocol/        版本、枚举、12 个 canonical 模型
  schemas/         核心与 9-tool 严格 Schema
  transport/       policy/auth/framing/replay；无 listener
  jobs/            状态、协调、幂等、边界与快照
  journal/         append-only hash-chain journal、原子 checkpoint
  safety/          审批、绑定、canonical hash、路径 containment
  backends/        ICadBackend 与确定性 MockCadBackend
  runtime/         Mock plugin lifecycle、DocumentContext、scheduler
integrations/
  legacy_p4_adapter/  默认禁用的合同骨架
```

## 控制流边界

`mcp_nextgen.control_server.server:mcp` 在 import 时只构造 FastMCP 对象并注册 9 tools：

- 没有 `main()`
- 没有 `.run()`
- 不启动 stdio、HTTP 或 TCP
- 不绑定端口
- 不访问文件或 CAD

所有工具进入 `dispatch_tool()` 后先执行 registry Schema 与审批绑定校验。当前 dispatcher 尚未调用 `LayerDCoordinator`、`MockPluginRuntime` 或 `MockCadBackend`。因此，除三个安全查询外，其余工具明确返回 `NOT_IMPLEMENTED`。

## 五层映射

| 层 | NextGen 对应实现 | 状态 |
|---|---|---|
| A — Control Server | `control_server`、`schemas` | import-safe、Mock-only；未接执行层 |
| B — Local Transport | `transport` | contract-only，无 listener |
| C — Plugin Runtime | `runtime.MockPluginRuntime` | 纯内存模拟，不是 AutoCAD 插件 |
| D — Job/Journal/Safety | `jobs`、`journal`、`safety` | 隔离重写基线，待正式测试固化 |
| E — Backend | `backends.MockCadBackend` | deterministic Mock-only |

## 来源与适配

仅吸收 DeepSeek 的白名单、结构化错误、文档身份、JSON Lines、批次、progress、journal/checkpoint 等概念。实验 `server.py`、`tcp_jsonrpc.py`、默认 token、原 JobExecutor、split executor 和写路径没有整体迁入。

正式项目现有 P2/P3/P4.1、backend、bridge、报告 Schema 和 DWG 路径保持不变。Legacy adapter 通过独立命名空间预留，不改写或包装旧执行器。

## 依赖方向

协议模型是跨层合同。控制面、Schema、transport、Layer D、runtime/backend 应依赖协议，不允许反向依赖旧 P4/COM 模块。Mock 与 Legacy/Real 通过 `BackendKind` 和 capability identity 隔离。

## 当前验证状态

各实现 Agent 已完成编译、import 和隔离内存自检；正式 `tests/nextgen` 与主线全量回归待 test_agent 最终验证。文档不以临时自检替代最终测试结论。



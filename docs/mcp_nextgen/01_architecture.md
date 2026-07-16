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

S4 已实现协议内的 Mock-only 控制面：版本化 tools/resources/prompts、作业状态机、审批绑定、进度事件、append-only journal 与原子 checkpoint，以及确定性 Mock 执行。实际 local listener、.NET plugin、Real backend 和天正接口均未实现。

## 当前组件

```text
mcp_nextgen/
  control_server/  import-safe FastMCP 注册、发现层、严格 dispatcher、ControlPlaneService
  protocol/        版本、枚举、12 个 canonical 模型
  schemas/         核心与 13-tool 严格 Schema
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

`mcp_nextgen.control_server.server:mcp` 在 import 时只构造 FastMCP 对象并注册 13 tools、3 resources 和 2 prompts：

- 没有 `main()`
- 没有 `.run()`
- 不启动 stdio、HTTP 或 TCP
- 不绑定端口
- 不访问文件或 CAD

所有工具进入 `dispatch_tool()` 后先执行 registry Schema 与审批绑定校验。`cad.batch.plan`、`cad.job.status`、`cad.job.approve`、`cad.job.run_mock`、`cad.job.cancel`、`cad.job.events` 接入 `ControlPlaneService`，只持久化 Mock job 的安全证据；不调用 AutoCAD、COM、天正或真实 backend。`cad.entities.query`、`cad.entities.inspect`、`cad.batch.clone`、`cad.batch.transform` 保持 `NOT_IMPLEMENTED` 并安全返回错误。

## 五层映射

| 层 | NextGen 对应实现 | 状态 |
|---|---|---|
| A — Control Server | `control_server`、`schemas` | `IMPLEMENTED_BASELINE`；import-safe、Mock-only 控制面 |
| B — Local Transport | `transport` | contract-only，无 listener |
| C — Plugin Runtime | `runtime.MockPluginRuntime` | 纯内存模拟，不是 AutoCAD 插件 |
| D — Job/Journal/Safety | `jobs`、`journal`、`safety` | `IMPLEMENTED_BASELINE`；状态机、审批、journal/checkpoint 仅服务 Mock job |
| E — Backend | `backends.MockCadBackend` | deterministic Mock-only |

## 来源与适配

仅吸收 DeepSeek 的白名单、结构化错误、文档身份、JSON Lines、批次、progress、journal/checkpoint 等概念。实验 `server.py`、`tcp_jsonrpc.py`、默认 token、原 JobExecutor、split executor 和写路径没有整体迁入。

正式项目现有 P2/P3/P4.1、backend、bridge、报告 Schema 和 DWG 路径保持不变。Legacy adapter 通过独立命名空间预留，不改写或包装旧执行器。

## 依赖方向

协议模型是跨层合同。控制面、Schema、transport、Layer D、runtime/backend 应依赖协议，不允许反向依赖旧 P4/COM 模块。Mock 与 Legacy/Real 通过 `BackendKind` 和 capability identity 隔离。

## 当前验证状态

S4 验收以 `tests/nextgen`、`tests/s4` 与默认安全回归的最终报告为准。文档不以实现存在或临时自检替代最终测试结论。


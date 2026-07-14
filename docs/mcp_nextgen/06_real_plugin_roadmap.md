# 真实 AutoCAD 插件路线图

## 当前事实

真实 in-process AutoCAD .NET plugin 尚未实现。当前没有：

- `IExtensionApplication` 插件
- AutoCAD `DocumentContext` / 主线程队列
- .NET JSON-RPC listener
- `ICadBackend` 的真实插件实现
- `ITianzhengBackend`
- 真实 COM/天正连接
- 真实 DWG 读写
- Production D1

`MockPluginRuntime`、`MockMainThreadScheduler` 和内存 save/reopen 只能验证合同与失败路径，不能作为真实插件证据。

## 分阶段路线

### R0 — 当前 Mock-only 基线

- 协议 `1.0.0`
- 9 tools 严格 Schema
- Layer D 安全重写
- deterministic Mock backend/runtime
- disabled Legacy adapter
- `production_d1_allowed=false`

完成状态以正式测试为准；测试结果待 test_agent 最终验证。

### R1 — 测试与控制面 Mock 接线

- 固化 `tests/nextgen`
- 覆盖 protocol、approval、journal/checkpoint、resume、automatic dependency、manual save、timeout/cancel、Mock failure injection
- dispatcher 只接 Mock runtime
- 保持无 listener 或仅进行受控内存调用
- 主线全量回归

### R2 — 实际本地 transport

- 只允许精确 `127.0.0.1`
- 外部安全注入 token
- 应用版本协商
- frame 累计大小限制
- session/replay/timeout/drain/shutdown
- 负向安全测试
- 不连接 AutoCAD

### R3 — 纯 .NET 接口项目

- 定义消息 DTO、错误模型、lifecycle 和 backend interface
- 不引用 AutoCAD DLL 的 contract 项目可先编译
- 建立 Python/.NET protocol conformance tests
- 仍不加载 AutoCAD

### R4 — In-process plugin sandbox

- 实现 `IExtensionApplication`
- DocumentContext 与主线程调度
- 显式文档身份核验
- 仅测试副本
- save/reopen/failure injection/crash recovery
- 禁止天正命令与 Production D1

### R5 — 天正只读能力

- 单独 capability probe
- Mock/Native/Tianzh正身份分离
- 只读对象与文档证据
- 不开放写入

### R6 — 受控 sandbox 写入

仅在 L3、工作副本、完整审批、回归和人工放行后考虑。L4/Production D1 仍需独立阶段和单次授权，不能由路线图自动升级。

## 阶段门禁

每阶段必须满足：

- 安全审计通过
- test_agent 全量回归通过
- capability 不夸大
- 文档与协议同步
- 原图完整性证明
- Manager 明确推进

本路线图不构成任何 CAD 连接或写入授权。



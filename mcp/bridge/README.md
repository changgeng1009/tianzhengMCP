# MCP Bridge 架构说明
## 概述
MCP Bridge 是 Python MCP wrapper 与 AutoCAD/天正 之间的本地 HTTP Bridge 层。提供三种运行模式的分层架构，确保安全、可控地操作 CAD。
## 分层架构
```
MCP Server (server.py)
       |
  BridgeDispatcher (统一请求分发)
       |
  +----+----+----+
  |    |    |    |
 Mock DryRun Real (默认禁用)
  |    |    |
  +----+----+
       |
  SafetyGate (跨层安全校验)
```
## Layer 1: Mock Bridge
- **文件**: `mock_bridge.py`
- **用途**: 开发调试、单元测试、CI 环境
- **连接 AutoCAD**: 否
- **执行 CAD 操作**: 否
- **返回数据**: 模拟的合理数据
## Layer 2: Dry-Run Bridge
- **文件**: `dry_run_bridge.py`
- **用途**: 命令预览、变更审核、前置验证
- **连接 AutoCAD**: 否
- **执行 CAD 操作**: 否
- **输出**: 每个操作的预期命令字符串、是否会修改 DWG
## Layer 3: Real Bridge
- **文件**: `real_bridge.py`
- **用途**: 真实执行 CAD 操作
- **状态**: 默认禁用 (`RealBridgeStub`)
- **启用**: 调用 `enable_real_execution()` + 通过 SafetyGate
## Safety Gate
- **文件**: `safety_gate.py`
- **校验层级**: 操作级 + 请求级 + 模式级
- **永久禁止**: DELETE 操作在所有模式下均不允许
- **高风险操作**: 需要 `allow_high_risk=True`
- **REAL 模式**: 必须显式调用 `enable_real_execution()`
## HTTP Endpoints
| Endpoint | Method | 描述 |
|----------|--------|------|
| `/bridge/v1/execute` | POST | 执行一批操作 |
| `/bridge/v1/preview` | POST | 预览操作（dry-run） |
| `/bridge/v1/validate` | POST | 校验 schema |
| `/bridge/v1/status` | GET | 获取连接状态 |
## 核心 Schema
| Schema | 描述 |
|--------|------|
| `BridgeRequest` | 请求体 — 包含操作列表、模式、安全选项 |
| `BridgeResponse` | 响应体 — 包含结果、安全校验、统计 |
| `BridgeOperation` | 单个操作 — 类型、几何、属性、风险标记 |
| `OperationResult` | 单个操作结果 — 状态、消息、handle |
## 使用方式
```python
from mcp.bridge import BridgeFactory, BridgeMode
# Mock 模式
bridge = BridgeFactory.create(BridgeMode.MOCK)
response = bridge.execute(request)
# Dry-Run 模式
bridge = BridgeFactory.create(BridgeMode.DRY_RUN)
response = bridge.execute(request)
# Real 模式（需要先启用）
from mcp.bridge import enable_real_execution
enable_real_execution()
bridge = BridgeFactory.create(BridgeMode.REAL)
```
## 安全规则
1. 所有 DELETE 操作被永久禁止
2. REAL 模式默认禁用，需要显式启用
3. 高风险操作需要 `allow_high_risk=True`
4. 每次请求必须通过 SafetyGate 校验
5. 写操作必须经过预览和确认
## 文件结构
```
mcp/bridge/
  __init__.py        — BridgeFactory, BridgeDispatcher, 统一导出
  schemas.py         — 所有数据模型和 schema 定义
  safety_gate.py     — 安全门校验逻辑
  mock_bridge.py     — Mock 模式实现
  dry_run_bridge.py  — Dry-Run 模式实现
  real_bridge.py     — Real 模式接口和桩实现
  README.md          — 本文档
```

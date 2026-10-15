> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

﻿# Agent Report
## Agent Name: safety_audit_agent
## Assigned Task
Phase M0 安全审计：审查"天正 CAD MCP 接口系统"所有真实执行风险，创建安全策略文档和审计报告。

## Files Read
共读取并审计 20 个核心安全相关文件：

| 文件 | 用途 |
|------|------|
| [ROADMAP.md](/D:/ExampleWorkspace/天正/ROADMAP.md) | 项目整体架构理解 |
| [cad/connection.py](/D:/ExampleWorkspace/天正/cad/connection.py) | COM 连接管理，含 default_manager 全局单例 |
| [cad/commands.py](/D:/ExampleWorkspace/天正/cad/commands.py) | SendCommand 透传，无命令过滤 |
| [cad/entities.py](/D:/ExampleWorkspace/天正/cad/entities.py) | 基础 CAD 实体创建 (draw_line, draw_polyline, add_text) |
| [cad/document.py](/D:/ExampleWorkspace/天正/cad/document.py) | Document 列举与读取 |
| [tools/connect.py](/D:/ExampleWorkspace/天正/tools/connect.py) | MCP 工具：连接 AutoCAD |
| [tools/command.py](/D:/ExampleWorkspace/天正/tools/command.py) | MCP 工具：SendCommand |
| [tools/draw.py](/D:/ExampleWorkspace/天正/tools/draw.py) | MCP 工具：draw_line |
| [tools/documents.py](/D:/ExampleWorkspace/天正/tools/documents.py) | MCP 工具：list_documents, get_active_document |
| [tools/execution.py](/D:/ExampleWorkspace/天正/tools/execution.py) | MCP 工具：执行计划管理 |
| [execution/models.py](/D:/ExampleWorkspace/天正/execution/models.py) | 执行模型，含 risk_level 和 executable 标记 |
| [execution/executor.py](/D:/ExampleWorkspace/天正/execution/executor.py) | 基础 CAD 执行器 |
| [execution/validation.py](/D:/ExampleWorkspace/天正/execution/validation.py) | 坐标校验与映射完整性检查 |
| [execution/queue.py](/D:/ExampleWorkspace/天正/execution/queue.py) | 执行队列，preview→confirm→execute 流程 |
| [tianzheng_interface/dry_run_engine.py](/D:/ExampleWorkspace/天正/tianzheng_interface/dry_run_engine.py) | Dry-run 模拟引擎 |
| [tianzheng_interface/proxy_handler.py](/D:/ExampleWorkspace/天正/tianzheng_interface/proxy_handler.py) | Proxy 对象分类处理器 |
| [mcp/t30_writeback/sandbox.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/sandbox.py) | DWG sandbox 创建 |
| [mcp/t30_writeback/real_adapter.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/real_adapter.py) | T30 写回适配器，含 dry_run/fake/real 三态 |
| [mcp/t30_writeback/com_probe.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/com_probe.py) | COM 能力探测（含 DWG 打开能力） |
| [mcp/t30_writeback/object_factory.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/object_factory.py) | T30 对象工厂，fake/real 双模式 |
| [mcp/t30_writeback/transaction.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/transaction.py) | 事务引擎：plan→validate→execute→verify→commit |
| [mcp/t30_writeback/verifier.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/verifier.py) | 实体创建验证 |
| [mcp/t30_writeback/action_translator.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/action_translator.py) | 修复计划 → T30 写回动作翻译 |
| [mcp/adapter_t30.py](/D:/ExampleWorkspace/天正/mcp/adapter_t30.py) | T30 写回适配器旧版 |
| [server.py](/D:/ExampleWorkspace/天正/server.py) | MCP Server 工具注册 |

## Files Modified/Created
- [SAFETY_POLICY.md](/D:/ExampleWorkspace/天正/SAFETY_POLICY.md) — 创建：完整安全策略文档
- [reports/safety_audit_agent_report.md](/D:/ExampleWorkspace/天正/reports/safety_audit_agent_report.md) — 创建：本审计报告
- [agent_outbox/safety_audit_agent_report.md](/D:/ExampleWorkspace/天正/agent_outbox/safety_audit_agent_report.md) — 创建：本报告副本

## Work Completed
完成了对"天正 CAD MCP 接口系统"全部 20 个安全关键文件的完整审计，涵盖：

1. **COM 连接安全边界**: 审计了 connection.py、connect.py 的全局单例暴露风险
2. **SendCommand 调用路径**: 追溯 tools/command.py → cad/commands.py → document.SendCommand() 完整链路
3. **DWG 写入路径**: 审计了 entities.py、draw.py、executor.py 中所有直接修改 DWG 的操作
4. **DWG 保存路径**: 确认无直接保存代码，但 SendCommand 可绕过
5. **sandbox 绕行风险**: 审计了 sandbox.py、real_adapter.py、transaction.py 的安全门控
6. **dry-run 前置校验**: 审计了 dry_run_engine.py 和 proxy_handler.py 的防护有效性
7. **T30 天正对象写入**: 审计了 object_factory.py、com_probe.py、action_translator.py 的 fake/real 双模式

## Tests Run
无测试运行 — 本阶段为纯审计阶段，禁止任何真实执行操作。

## Test Result
N/A — 审计阶段不执行测试。

## Safety Check
* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO

## Risks Found

### 严重 [CRITICAL]

**[SK-001] SendCommand 无命令过滤** — cad/commands.py:26
- CommandService.send_command() 直接将任意字符串透传给 document.SendCommand()
- 可执行 SAVE、WBLOCK、ERASE ALL、UNDO、TPIPE、TDRAIN 等任意命令
- MCP 工具 send_command 直接暴露此能力
- **建议**: 立即添加命令白名单或完全移除 send_command MCP 工具

### 高 [HIGH]

**[SK-002] default_manager 全局单例暴露** — cad/connection.py:156
- default_manager = AutoCADConnectionManager() 作为模块级全局变量
- 任何代码 rom cad.connection import default_manager 即可获取 AutoCAD 控制权
- 无访问控制、无审计日志、无权限检查
- **建议**: 改为依赖注入，或在 connect() 前增加授权检查

**[SK-003] draw_line 直接修改 active DWG** — cad/entities.py, tools/draw.py
- EntityService.draw_line() 直接调用 document.ModelSpace.AddLine()
- 修改的是用户当前激活的 DWG，无沙盒、无备份
- 如果 active document 恰好是 source DWG，则直接修改源文件
- **建议**: 写入前检查 active document 是否为受保护的源 DWG；添加自动备份

**[SK-004] DWG 保存可被绕过** — 无直接保存代码，但 SendCommand 可执行 SAVE
- 项目中没有实现 document.Save() 调用
- 但 SendCommand 无过滤，可透传 SAVE/QSAVE/SAVEAS
- 源 DWG 被保存后不可逆
- **建议**: SendCommand 必须过滤 SAVE 相关命令

### 中 [MEDIUM]

**[SK-005] com_probe 可能自动打开 DWG** — mcp/t30_writeback/com_probe.py:149
- _resolve_document() 在 llow_open_document=True 时调用 Documents.Open()
- 可能意外打开 source DWG 文件
- **建议**: allow_open_document 默认必须为 False，且需要用户确认

**[SK-006] real_com_mode 可被代码级绕过** — mcp/t30_writeback/real_adapter.py:25
- RealT30WritebackAdapter.__init__(real_com_mode=False) 构造函数参数
- 如果调用方传入 True，直接绕过 dry-run 保护
- **建议**: 增加环境变量/配置文件禁令，或移除构造函数参数，改为运行时授权检查

**[SK-007] sandbox_dir 无路径校验** — mcp/t30_writeback/sandbox.py:24
- options.get("sandbox_dir") 无校验，可被设为源 DWG 相同目录
- 可能导致 sandbox 副本覆盖源 DWG
- **建议**: 增加路径冲突检查，禁止 sandbox_dir 等于源 DWG 目录

### 低 [LOW]

**[SK-008] 坐标校验默认边界过宽** — execution/validation.py:16
- DEFAULT_CAD_WORLD_BOUNDS 为 ±100000，对某些大图纸可能不适用
- 超出边界仅标记 HIGH risk，非禁止
- **建议**: 可配置化或基于实际 DWG 范围动态计算

## Remaining Work
本次审计发现的风险需要在后续 Phase 中修复：

1. **Phase M1**: 修复 SK-001 (SendCommand 命令过滤) — 最高优先级
2. **Phase M1**: 修复 SK-002 (全局单例重构)
3. **Phase M2**: 修复 SK-003 (draw_line sandbox 保护)
4. **Phase M2**: 修复 SK-005 (com_probe allow_open_document)
5. **Phase M3**: 修复 SK-006 (real_com_mode 授权检查)
6. **Phase M3**: 修复 SK-007 (sandbox_dir 路径校验)
7. **Phase M4**: 修复 SK-008 (坐标边界可配置化)

## Recommendation
本次审计确认项目安全架构整体良好——写操作路径（T30 writeback）有完整的事务引擎和 sandbox 保护，Phase 1-6 的只读操作也有严格边界。但存在两个关键安全债务需要立即修复：

1. **SendCommand 无过滤**（CRITICAL）是最危险的漏洞，建议在 Phase M1 立即添加命令白名单
2. **全局单例 default_manager**（HIGH）会导致隐式权限提升，建议改为显式依赖注入

SAFETY_POLICY.md 已建立明确的安全状态层级（L0-L4）和审批短语规则，供后续所有 Phase 和 agent 遵守。

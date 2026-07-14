# Task for Phase M1 — 天正给排水接口层实现 agent
## Assigned by: Manager
## Phase: M1
## Task ID: M1-dev-agent-001

## Task Description

实现 Phase M1 全部 5 个任务项：

### M1.1 实现 `tianzheng_interface/scanner.py`
天正 DWG 一键扫描器核心流水线：
1. 接受已分类的实体数据（ProxyObjectHandler 输出）
2. 接受已构建的语义模型（semantic_reader 输出）
3. 接受已构建的管网图（PipeNetworkGraphBuilder 输出）
4. 组装 DWGScanResult，按 system_type 分组
5. 生成统计信息
**约束**：不连接 AutoCAD，纯数据流水线，dry-run only。

### M1.2 实现 `tianzheng_interface/report_builder.py`
Markdown + JSON 双格式报告生成器：
1. `build_markdown_report(scan_result: DWGScanResult) -> str`
2. `build_json_report(scan_result: DWGScanResult) -> str`
3. `save_report(scan_result, output_dir)` -> 保存 md + json
**约束**：纯数据转换，不访问 AutoCAD/DWG。

### M1.3 新增 `config/tianzheng_system_types.json`
给排水系统类型配置，包含：给水、排水、消防、喷淋等系统类型定义、关键词、图层映射。

### M1.4 新增 `config/tianzheng_action_templates.json`
Action 模板配置，定义 add_pipe / add_valve / add_fitting / update_diameter 等操作的参数模板。

### M1.5 新增 `examples/tianzheng_dwg_scan_report.md`
完整的扫描报告样例文件。

## Input Files
- tianzheng_interface/model.py (数据模型)
- tianzheng_interface/proxy_handler.py (实体分类器)
- tianzheng_interface/action_schema.py (Action 定义)
- tianzheng_interface/dry_run_engine.py (干运行引擎)
- pipe_network/graph_builder.py (管网图构建)
- pipe_network/models.py (管网图模型)
- tianzheng/semantic_reader.py (语义读取)
- config/pipe_diameter_patterns.json (管径模式)

## Constraints
- 禁止连接 AutoCAD
- 禁止打开 DWG
- 禁止 SendCommand
- 禁止执行天正命令
- 禁止保存 DWG
- 所有操作纯数据，dry-run only

## Expected Output
- tianzheng_interface/scanner.py (新建)
- tianzheng_interface/report_builder.py (新建)
- config/tianzheng_system_types.json (新建)
- config/tianzheng_action_templates.json (新建)
- examples/tianzheng_dwg_scan_report.md (新建)
- tests/test_tianzheng_interface_scanner.py (新建)
- tests/test_tianzheng_interface_report_builder.py (新建)
- agent_outbox/ 报告

---

# Task for cad_bridge_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-ARCH-CE-001

## Task Description

在安全预审已允许的纯离线范围内，基于真实代码审计 DeepSeek Layer C（Mock Plugin Runtime）与 Layer E（MockCadBackend），并对照正式项目 real/COM/bridge/executor/P4 adapter 边界。检查插件生命周期、DocumentContext、主线程调度、timeout/cancel/progress/partial/save failure/identity conflict；检查 ICadBackend、open/close、create/copy/transform、batch/save/reopen/identity/hash/protected region/failure injection/determinism。明确 Mock 不得替换或伪装 Real，并设计 LegacyCadBackendAdapter 的最小接口边界，但本任务不实现、不连接执行器。

## Constraints

- 本任务只读审计，不修改代码、测试或实验项目。
- 禁止连接 AutoCAD/天正、COM；禁止打开或修改任何 DWG。
- 禁止 CopyObjects、SendCommand、LISP、NETLOAD、P4.1、Production D1。
- 不导入或调用可能初始化 COM/真实执行器的模块。

## Expected Output

- `agent_outbox/cad_bridge_agent_report.md`
- Layer C/E 验收结论、文件/行号证据、正式项目对照、Legacy adapter 合同建议、拒绝/延期项。

---

# Task for cad_bridge_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-MIG-BACKEND-004

## Task Description

依据 Layer C/E 审计，在隔离命名空间实现 nextgen backend/runtime 基线。实现 `ICadBackend`/抽象协议、确定性 MockCadBackend（文档 open/close/identity/hash、entity create/copy/transform、batch、save/reopen 模拟、protected region、failure injection、进度/部分失败/保存失败/身份冲突）、MockPluginRuntime（lifecycle/DocumentContext/主线程调度模拟/timeout/cancel/progress）。实现 `LegacyCadBackendAdapter` 或等价禁用骨架：默认 disabled，不得在 import 时导入 COM/旧执行器，不得调用 P4，必须显式依赖注入且本阶段永远报告 Real unavailable/production false。

## Owned Files

- `mcp_nextgen/backends/**`
- `mcp_nextgen/runtime/**`
- `integrations/legacy_p4_adapter/**`

## Constraints

- 不修改旧 backend、bridge、executor、P2/P3/P4.1、tests。
- 禁止 AutoCAD/天正/COM/DWG/CopyObjects/SendCommand/LISP/NETLOAD/P4.1/Production D1。
- 仅编译/import 自检；不得初始化或调用真实执行模块。
- Mock/Real capability 必须显式区分，Mock 不得伪装 Real。

## Expected Output

- 上述隔离实现与标准 `agent_outbox/cad_bridge_agent_report.md`。
- 报告列出自检、Legacy adapter 状态、Mock/Real 分离声明。

---

# Task for cad_bridge_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-FIX-MOCK-009

## Task Description

修复 `tests/nextgen/test_nextgen_handoff.py::test_mock_backend_is_deterministic`：两个等价新建 Mock backend 的默认 DocumentIdentity 仅因 `created_at` 微秒不同而不相等。采用最小修改使 Mock 时间确定且可显式注入，不改变 Real/Legacy 语义，不修改测试。仅运行内存/compile 自检，不运行 pytest（由 test_agent 验证）。

## Owned Files

- `mcp_nextgen/backends/**`
- `agent_outbox/cad_bridge_agent_report.md`

## Constraints

- 不修改 tests、旧代码、runtime/legacy（除非 import 对齐绝对必要）。
- 禁止 AutoCAD/天正/COM/DWG/P4.1/Production D1。

## Expected Output

- 最小业务修复与标准 outbox，说明确定性时钟策略。

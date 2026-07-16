# Task for test_agent
## Assigned by: Manager
## Phase: CAD-NEXTGEN-MCP-CONTROL-PLANE-S4
## Task ID: CAD-S4-TEST-003

## Task Description
审计并补充 S4 NextGen MCP Control Plane 的离线/Mock 安全测试。覆盖 protocol schema、Tool Registry、Job 状态机、Approval 绑定、checkpoint、append-only journal、Mock 执行流程和错误处理。先审计既有 `mcp_nextgen` 与 `tests/nextgen`，只在并行控制面 API 稳定后新增 `tests/s4/**` 或等价隔离测试；不得修改业务模块，除非 Manager 明确批准最小测试辅助修复。

## Constraints
- 禁止连接 AutoCAD、天正、COM，禁止读取、解析、扫描或哈希真实 DWG/DXF。
- 仅运行受项目级文件访问守卫保护的默认测试；排除 real_dwg、external_integration、autocad_required、tianzheng_required、com_required、production_only。
- 禁止 Real Backend、真实 listener、TCP/socket、exec/shell 或生产写入。
- 使用 `tmp_path`、内存 Mock 与虚构 `mock://` 文档身份；静态 fixture 不得包含 CAD 文件。
- 不削弱既有安全断言或访问守卫。

## Expected Output
- `tests/s4/**`（仅在现有测试未覆盖的 S4 控制面合同存在时新增）。
- `artifacts/s4_nextgen_mcp_control_plane/<run_id>/s4_test_audit.json`。
- 更新 `agent_outbox/test_agent_report.md`，包括测试计划、实际结果、真实 CAD 零访问和未实现边界。
## Assigned by: Manager
## Phase: CAD-BASELINE-REFREEZE
## Task ID: REFREEZE-TEST-PREPARE-20260714T220937+0800
## Task Description
仅准备安全测试执行清单。只读核对现有文件访问守卫、pytest marker、旧安全基线测试命令/结果和测试目录结构，按用户要求生成精确测试命令计划；不得运行 pytest，等待 Safety Agent 明确 `APPROVE_TESTS`。
## Input Files
- `D:\CodexWork\天正\pytest.ini`
- `D:\CodexWork\天正\conftest.py`
- `D:\CodexWork\天正\tests`
- `D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T193554+0800_s2_1\test_command_manifest.json`
- 旧基线中的测试结果与 marker/守卫策略 JSON
## Constraints
- 禁止运行任何 pytest。
- 禁止连接 AutoCAD、天正或 COM。
- 禁止读取、解析、扫描或哈希任何真实 DWG/DXF。
- 所有命令必须加载项目根守卫。
- 所有外部集成/真实 CAD 放行环境变量必须保持关闭。
- 必须排除 `real_dwg`、`external_integration`、`autocad_required`、`tianzheng_required`、`com_required`、`production_only`。
## Expected Output
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/run/refreeze_test_command_plan.json`
- `agent_outbox/test_agent_report.md`
- 状态：`WAITING_FOR_SECURITY_APPROVAL`
# Task for test_agent
## Assigned by: Manager
## Phase: CAD-CONFIG-S2
## Task ID: CAD-CONFIG-S2-TEST-PLAN-001

## Task Description
只读审计现有 pytest 配置、守卫、Skill/NextGen/CLI 测试路径，制定 CAD-CONFIG-S2 的分阶段安全测试计划和新增测试文件边界。识别最小可复用 synthetic fixture 与现有 marker 表达式，不运行测试、不修改测试。

## Constraints
- 不读取、解析、扫描或哈希 DWG/DXF。
- 不连接 AutoCAD、天正或 COM；不运行 external/real/production 测试。
- 不修改守卫以放宽安全规则。

## Expected Output
- `D:\CodexWork\天正\agent_outbox\test_agent_report.md`
- 报告包含现有测试路径、建议新增路径、命令、守卫启用方式、计数采集方式和真实 CAD 零访问验收点。

## WP4 Implementation Authorization

### Task ID: CAD-CONFIG-S2-WP4

WP1 公共配置 API 已稳定，WP2 已完成，WP3 正在实施。现在创建新增测试，但在 WP3 完成前不得运行阶段 A–E 命令。

独占修改：
- `tests/config_driven/**`
- `tests/config_cli/**`
- 必要时仅追加兼容断言到 `skills/autocad-tianzheng-automation/tests/test_skill.py`、`tests/skill/test_skill_cli.py`、`tests/skill/test_skill_package.py`；不得删除或弱化现有断言。

覆盖原需求 100 项测试域，允许按参数化方式合并用例；必须能形成需求编号到 test id 的映射。静态 fixture 不得包含 `.dwg/.dxf`；CAD 路径仅作虚构字符串；不得调用 exists/stat/read/hash/strict resolve；不得覆盖项目级 guard fixture。

先写测试并做语法检查。待 WP3/CLI 完成及 Manager 发出 `RUN_PHASED_TESTS` 后，才按 Phase A–E 顺序运行。更新 outbox，明确已写/未运行状态。

## Test Completion Handoff

### Task ID: CAD-CONFIG-S2-TEST-COMPLETE-006

此前 Phase A/B/C/D 已通过，Phase E 首轮只剩一个旧测试对离线模块名 `generic_autocad` 的误报。该测试已获授权最小修正：禁止真实 AutoCAD/COM 模块、CAD 进程和 guard 连接事件，但允许明确的离线 `adapters.generic_autocad.adapter` 命名空间。现在先只读审计该修正，再运行：

1. 定向旧安全测试；
2. Phase E 全量默认安全回归。

每次运行：清除 `CAD_TEST_ALLOW_EXTERNAL_READONLY`，设置新的 `CAD_SAFE_TEST_RUN_DIR`，从根目录以 `python -m pytest -q -c pytest.ini --strict-markers -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"` 执行。

不得运行任何被排除 marker；不得读取真实 DWG/DXF；不得修改实现或守卫。若失败：仅修复明显错误的测试断言且不得削弱真实 CAD/COM/guard 检测；否则停止并报告。生成 Phase E 结果和访问摘要至 `artifacts/cad_config_driven_s2/20260715T113724+0800_s2`，并更新 outbox。

## Post-S2 Freeze Test Run

### Task ID: CAD-POST-S2-FREEZE-TEST-002

冻结目录：`artifacts/post_s2_baseline_freeze/20260716T170858+0800_post_s2`。在不修改任何代码/守卫/Git的条件下，严格运行：

1. `tests/config_driven`；
2. `skills/autocad-tianzheng-automation/tests`；
3. `tests/nextgen`；
4. `tests/config_cli tests/skill/test_skill_cli.py`；
5. 默认安全回归。

每个 pytest 进程从项目根 `python -m pytest -q -c pytest.ini --strict-markers`，排除六类 marker，清除所有 external readonly 放行，使用独立 `CAD_SAFE_TEST_RUN_DIR`。收集 passed/failed/skipped/warning 和 guard 摘要，写入冻结目录 `test_results.json`；真实DWG读写、CAD/COM/天正/外部进程任一非0即停止。warning 只记录，不改代码。更新 test outbox。

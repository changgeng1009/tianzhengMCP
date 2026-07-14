# Task for safety_audit_agent
## Assigned by: Manager
## Phase: CAD-SAFETY-S2.1
## Task ID: CAD-SAFETY-S2.1-A
## Run ID: 20260714T193554+0800_s2_1

## Task Description
对 `tests`、`mcp_nextgen`、`mcp`、`scripts`、`skills/autocad-tianzheng-automation` 做文本级静态 CAD 文件访问审计，建立 SEC-FINAL-019 的静态证据与 pytest marker 清单。

## Input Files
- 指定范围内的 Python、PowerShell、JSON、Markdown、YAML/TOML/INI/CFG 等文本源码与配置
- `artifacts/mcp_upgrade_handoff` 中现有 JSON/Markdown 接管证据

## Constraints
- 严禁打开、读取、扫描或哈希任何 DWG/DXF。
- 搜索仅限文本扩展名，排除二进制、`output`、`图纸`、`.git`、缓存和临时目录。
- 不跟随 JSON/Markdown 中出现的 CAD 路径。
- 不修改产品代码，不运行 pytest，不连接 AutoCAD、天正或 COM。

## Expected Output
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/real_dwg_static_access_inventory.json`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/real_dwg_static_access_inventory.md`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/pytest_marker_inventory.json`
- `agent_outbox/safety_audit_agent_report.md`

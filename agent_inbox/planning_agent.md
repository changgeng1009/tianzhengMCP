# Task for planning_agent
## Assigned by: Manager
## Phase: CAD-SAFETY-S2.1
## Task ID: CAD-SAFETY-S2.1-DOCS

## Task Description

为 `SEC-FINAL-019` 关闭工作建立报告与冻结基线结构，设计并实现只读静态审计入口和独立基线复核入口，提供 16 项关闭条件的机读 Schema/校验，并准备阶段报告骨架。等待测试 Agent 的真实结果后再定稿，不提前宣告关闭。

## Input Files

- `AGENTS.md`
- `pytest.ini`
- `artifacts/mcp_upgrade_handoff/`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/`
- `tests/`
- `mcp_nextgen/`
- `mcp/`
- `scripts/`
- `skills/autocad-tianzheng-automation/`

## Constraints

- 禁止运行 pytest、外部集成测试、P4.1 或任何 CAD/COM/天正程序。
- 禁止读取、解析、扫描、哈希或跟随访问任何 DWG/DXF。
- 审计工具只读取允许的文本源码，不跟随文本或报告中的 CAD 路径。
- 基线复核工具只读取基线 JSON、源码清单和校验文件；源码哈希必须先做路径/扩展名/排除目录 fail-closed 校验。
- 显式排除 DWG/DXF、图纸、output、artifacts 二进制、cache、`.git` 和临时文件。
- 不修改业务执行逻辑、统一 Skill、原始 GitHub Skill、ROADMAP 或 TASK_BOARD。
- 不提前将 `SEC-FINAL-019` 标记为 CLOSED；测试结果由 Manager/测试 Agent 回填。

## Expected Output

- `scripts/audit_default_test_cad_access.py`
- `scripts/verify_safe_test_baseline.py`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/` 报告骨架和关闭 Schema
- `artifacts/cad_safe_test_baseline/20260714T193554+0800_s2_1/` 冻结基线模板
- `agent_outbox/planning_agent_report.md`

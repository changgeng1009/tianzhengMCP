# Task for command_registry_agent
## Assigned by: Manager
## Phase: CAD-SKILL-S0/S1
## Task ID: CAD-SKILL-S1-CURRENT-PROJECT-AUDIT

## Task Description

对 `D:\CodexWork\天正` 当前正式项目进行真实代码能力审计，形成可供统一 AutoCAD + 天正 Skill 封装使用的当前能力清单与矩阵。代码与测试证据优先，不以 README 声明代替实现证据。

## Input Files

- `D:\CodexWork\天正`（递归审计）
- 重点目录：`cad/`、`cad_compare/`、`command_registry/`、`coordinate/`、`execution/`、`mcp/`、`mcp_nextgen/`、`mcp_service/`、`pipe_network/`、`reference/`、`roi/`、`semantic_diff/`、`tianzheng/`、`tianzheng_interface/`、`vision/`、`tests/`、`docs/`

## Constraints

- 排除 `artifacts/`、`skills/autocad-tianzheng-automation/`、安装目标和大型二进制。
- 禁止读取任何 `.dwg` 内容；禁止运行会触碰 DWG 的脚本或测试。
- 禁止连接或启动 AutoCAD/天正；禁止 COM、SendCommand、CopyObjects、LISP、NETLOAD。
- 禁止修改现有执行器、现有测试、ROADMAP、TASK_BOARD。
- 能力分类限定为：`GENERIC_AUTOCAD`、`TIANZHENG_WATER`、`TIANZHENG_HVAC`、`SHARED_ORCHESTRATION`、`SAFETY`、`PROJECT_SPECIFIC`、`EXPERIMENTAL`、`DEPRECATED`。
- 必须区分实现存在、测试验证、接口占位、项目专用和未验证能力。

## Expected Output

- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/current_project_capability_inventory.json`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/current_project_capability_matrix.md`
- `agent_outbox/command_registry_agent_report.md`

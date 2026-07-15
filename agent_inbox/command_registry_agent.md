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
# Task for command_registry_agent
## Assigned by: Manager
## Phase: CAD-CONFIG-S2
## Task ID: CAD-CONFIG-S2-WP1

## Dependency
仅在 Manager 明确通知 `s2_implementation_gate=PASS` 后开始。

## Task Description
实现 WP1：canonical Manifest 1.1.0、1.0/1.0.0 兼容与迁移、canonical serialization、六层默认值、限制性安全合并、纯词法路径解析、统一错误模型及 execution plan Schema。不得开始 Runtime/Workflow/Template/Simulation 实现，不得修改 adapters 或 tests。

## Owned Files
- `skills/autocad-tianzheng-automation/schemas/project_manifest.schema.json`
- `skills/autocad-tianzheng-automation/schemas/project_manifest_v1_0.schema.json`
- `skills/autocad-tianzheng-automation/schemas/execution_plan.schema.json`
- `skills/autocad-tianzheng-automation/config/**`，但排除 `config/workflows/**`
- `skills/autocad-tianzheng-automation/runtime/errors.py`

CLI 暂不修改，待 WP3 接口冻结后另派任务。

## Required Semantics
- canonical version `1.1.0`；最低兼容 `1.0`/`1.0.0`；未知/过新/过旧明确失败。
- 未知顶层字段不得静默丢弃；仅显式 `extensions` 可承载扩展。
- 6 层优先级：run override > project > workflow > product > skill > system，但安全字段只能收紧。
- production/real access 默认 false；source_write_forbidden/sandbox/fail_closed/visual/engineering review 默认 true；approval 不继承；L3/L4 不可由配置授予。
- Path resolver 仅字符串/结构规范化；不得对 CAD 路径调用 open/read/stat/exists/hash/strict resolve；阻断 traversal、UNC、外部、source-output collision、Skill 安装目录输出。
- 使用 apply_patch 编辑，显式 UTF-8；不得触碰预存删除、mcp_nextgen、P2/P3/P4.1、安全守卫、安装目录或原始 GitHub Skill。

## Validation
只运行你拥有模块的轻量 Python/JSON Schema 单元自检，不运行全量 pytest；不得创建/读取 DWG/DXF。记录命令和结果。

## Expected Output
- 实现上述 Owned Files。
- 更新 `agent_outbox/command_registry_agent_report.md`。
- 报告列出文件、API、兼容性、安全不变量、自检结果和剩余 WP3/CLI 接口依赖。

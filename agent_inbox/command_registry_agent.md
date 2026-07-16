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

## WP1-CLI Integration Task

### Task ID: CAD-CONFIG-S2-CLI-002

WP3 已完成。现在扩展 `skills/autocad-tianzheng-automation/scripts/skill_cli.py`，保留并兼容现有 5 个入口，同时实现：

- `manifest validate|normalize|explain|migrate|diff`
- `config resolve`
- `runtime select`
- `product select`
- `backend select`
- `workflow select`
- `plan build|verify|hash`
- `simulate <manifest> --backend offline|nextgen_mock`
- `templates list|create`

所有命令支持 `--json`；成功/错误使用统一结构与 exit code 0/2/3/4/5/6/7/8/9。Manifest 必须经 `ManifestLoader`/Migrator/DefaultResolver/PathResolver 后进入 WP3 路由，不得直接用 1.1.0 Schema 拒绝旧 1.0 example。默认 offline；不可用/Real backend 明确失败；不得读取 Manifest 中的 CAD 文件路径，不得启动子进程。

Owned Files：
- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- 必要时最小修改同目录 `__init__.py`
- 不修改 tests、runtime、config、adapters、docs。

完成后只运行 CLI 的离线 smoke/`--help`/旧入口兼容自检，不运行 pytest。更新 command_registry outbox 的 CLI 部分并回传命令数量、exit code 自检和未解决项。

## Approval Plan Gap Fix

### Task ID: CAD-CONFIG-S2-APPROVAL-TRACE-007

只读审计指出 Execution Plan 的 approval 输出未显式区分 `approval_declared`、`approval_reference_present`、`approval_verified`、`approval_consumed`、`approval_expired`、`approval_scope_match`。在不更改真实 approval authority、不提升任何 L3/L4 或 backend 的条件下，最小补足此合同：本阶段所有未由独立 authority 验证的状态必须明确 `false` 或 `UNVERIFIED`，并保留 `APPROVAL_REQUIRED` / `REAL_BACKEND_NOT_AVAILABLE` blocked 行为。

允许修改：
- `skills/autocad-tianzheng-automation/runtime/execution_plan.py`
- 如绝对必要，最小修改相关 runtime contract/schema
- 仅追加相关 `tests/config_driven/**` 测试

不得改 CLI、文档、守卫、Git 或任何 CAD/Real backend 路径。运行定向新增/受影响测试并更新 command_registry outbox。

## Final Skill Installation

### Task ID: CAD-CONFIG-S2-INSTALL-009

前置：最终 A–E 回归全部通过。现在执行仅限统一 Skill 的安装收尾：

1. 确认规范源及安装目录 `.dwg/.dxf` 数均为 0；
2. 运行 Skill `quick_validate`；
3. 运行 `sync_skill_installation.ps1` dry-run；
4. 实际同步，禁止删除未知安装文件；
5. 计算规范源/安装目录非排除文件 SHA256 并要求一一匹配；
6. 在安装目录运行 CLI `--help`、`templates list`、一个虚构模板 `manifest validate` 与 `plan build`；
7. 不修改原始 GitHub Skill，不执行任何 Git 操作，不访问任何 CAD。

把结果写入 `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_manifest.json` 和 `installation_hash_verification.json`，并更新 command_registry outbox。

## Template Create Installation Path Fix

### Task ID: CAD-CONFIG-S2-TEMPLATE-OUTPUT-011

安装态发现 `templates create <id> --output <dir>` 对安装目录内输出正确 fail-closed，但当前实现也拒绝显式指定的安装外临时目录，无法完成安装态模板验证。最小修正 CLI 的模板复制输出策略：

- 允许显式指定、安装目录/规范源目录之外的非 CAD 输出目录；
- 继续拒绝输出到规范源、安装目录、CAD 扩展名、UNC、路径遍历或任何真实执行路径；
- 不改变 ManifestPathResolver 对文档路径的 `project_relative` 安全策略；
- 仅调整 `scripts/skill_cli.py` 及必要 CLI 专用测试。

必须新增/更新测试覆盖“显式外部安全临时输出成功”和“源/安装目录输出仍拒绝”。运行定向 CLI 测试；完成后由 Manager 重新执行 D/E 回归、同步和安装态验证。不得改Git/CAD/守卫。

## Postfix Installation Verification

### Task ID: CAD-CONFIG-S2-INSTALL-POSTFIX-012

CLI 输出策略修复且 postfix Phase D/E 已通过。重新执行 quick_validate、sync dry-run、实际同步、源/安装 SHA256 比对；确认两端 CAD 扩展名数为0、无未知安装文件删除。然后从安装目录：

1. `templates list`；
2. 使用一个显式的安装外临时目录执行 `templates create plain_autocad_redraw --output <temp>`；
3. 对所生成的 `project_manifest.json` 执行 `manifest validate` 与 `plan build`；
4. 验证 `templates create` 指向安装目录仍返回 exit 6。

生成或更新 installation artifacts，所有步骤不得Git/CAD/COM/DWG。

## Template Create Reject Exit-Code Fix

### Task ID: CAD-CONFIG-S2-TEMPLATE-REJECT-013

安装态模板外部创建/验证/计划已通过；但把输出指向安装目录时，安全拒绝返回 `CONFIG_CONFLICT`/exit 3，而 Path policy 合同要求 `PATH_*` / exit 6。最小修正 `templates create` 的源目录/安装目录拒绝映射：保留拒绝，不改变路径边界，只将该路径策略违规返回统一 `PATH_EXTERNAL_NOT_ALLOWED`（或等价 PATH code）与 exit 6。

仅改 CLI 及专用测试；运行定向CLI测试。完成后重新执行 postfix Phase D/E 和安装同步/安装态验证。不得改Git/CAD/guard。

## Final Installation Acceptance Retry

### Task ID: CAD-CONFIG-S2-INSTALL-FINAL-014

Template reject error-code fix、postfix2 Phase D/E 已通过。执行最终安装验收：quick_validate；源/安装 CAD 扩展名数=0；sync dry-run→apply且不删除未知文件；131+ 非排除文件SHA256一一匹配；安装态 `--help`/`templates list`；安装外临时目录 `templates create→manifest validate→plan build` 全部exit0；安装目录输出 `templates create` 必须 `PATH_EXTERNAL_NOT_ALLOWED`/exit6。更新安装 artifacts/outbox，不得Git/CAD/COM/DWG。

## Post-S2 Skill and Capability Freeze

### Task ID: CAD-POST-S2-FREEZE-SKILL-003

冻结目录：`artifacts/post_s2_baseline_freeze/20260716T170858+0800_post_s2`。只读生成：

- `skill_installation_freeze.json`：规范源/安装目录文件数、对应非排除文件SHA256、unknown deletion/addition、CAD扩展名数；
- `capability_matrix.json`：Skill包装/配置驱动/Workflow/ExecutionPlan/Mock PASS，Real AutoCAD/Tianzheng/ObjectARX/NextGen Real NOT_IMPLEMENTED，生产 DISABLED；
- `security_state.json`：production_allowed/d1=false、real_cad_access/backend=false、AutoCAD/天正/COM=0。

可运行只读 quick_validate 与 hash 比对，不得同步、修改Skill、改Git、连CAD或读DWG/DXF。更新 command_registry outbox。

## S3 Product Schema and Runtime Decoupling

### Task ID: CAD-S3-PRODUCT-CORE-001

以当前 S2 Tag 为起点，实现纯离线的 ProductProfile 模型与 Product/Runtime 解耦。Product 仅允许 `generic_autocad`、`tianzheng_water`、`tianzheng_hvac`、`offline_analysis`；Runtime 独立于产品，至少支持 `offline`、`mock`、`com`、`objectarx`，其中后两者必须 NOT_AVAILABLE。

实现/更新仅限配置与路由合同（选择现有结构最小扩展）：ProductProfile schema/registry、产品-运行时兼容选择、明确状态/required backend/capabilities。不得将 runtime_mode 继续作为 product；保留 S2 兼容 wrapper。不得接入任何真实 backend、CAD、COM。

新增针对性测试和报告 `artifacts/s3_product_unification/<run_id>/product_schema_audit.json`。完成后更新 command_registry outbox，列明实际改动与状态。

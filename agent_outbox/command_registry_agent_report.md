# Agent Report

## Agent Name

command_registry_agent

## Assigned Task

CAD-CONFIG-S2-CLI-002 — 在 WP1/WP3 已冻结接口上实现分组离线 CLI，保持旧入口兼容，并统一 JSON 错误与退出码。

## Files Read

- `agent_inbox/command_registry_agent.md`
- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `skills/autocad-tianzheng-automation/config/*.py`
- `skills/autocad-tianzheng-automation/runtime/{contracts,routing,backend_registry,workflow_registry,execution_plan,simulation,errors}.py`
- `skills/autocad-tianzheng-automation/adapters/registry.py`
- `skills/autocad-tianzheng-automation/templates/template_catalog.json`
- `agent_outbox/intent_mapper_agent_report.md`
- `skill-creator/SKILL.md`

## Files Modified

1. `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
2. `agent_outbox/command_registry_agent_report.md`

未修改 `scripts/__init__.py`、测试、WP1/WP3 实现、业务执行器、安全守卫、冻结基线、安装目录、原始 GitHub Skill、DWG/DXF 或任何 Real backend。

## Work Completed

### CLI 命令面

共实现 21 个叶子命令，其中 16 个新分组命令、5 个旧兼容入口：

- `manifest validate|normalize|explain|migrate|diff`（5）
- `config resolve`（1）
- `runtime select`（1）
- `product select`（1）
- `backend select`（1）
- `workflow select`（1）
- `plan build|verify|hash`（3）
- `simulate <manifest> --backend offline|nextgen_mock`（1）
- `templates list|create`（2）
- 旧入口 `inspect-manifest`、`validate-manifest`、`select-runtime`、`build-plan --dry-run`、`capabilities --mode`（5）

所有叶子命令均接受 `--json`；新命令统一输出 `{"ok": true, "result": ...}`。旧入口默认保持原直接 JSON 形状，显式 `--json` 时使用统一 envelope，兼顾历史调用与新合同。

### Manifest 与路由流水线

- Manifest 路由命令统一执行：`ManifestLoader.load → validate source → ManifestMigrator.preview → validate canonical 1.1.0 → DefaultResolver.resolve → ManifestPathResolver.resolve_manifest → runtime/product/backend/workflow select`。
- 旧 1.0/1.0.0 示例不再被直接套用 1.1 Schema，验证、迁移和旧入口 smoke 均通过。
- `manifest migrate` 默认生成同目录 `.migrated.json`，支持 `--preview` 和显式 `--output`；禁止原地写回、禁止覆盖已有 JSON、禁止写入不存在的父目录。
- `manifest diff` 在双方迁移到 canonical 后生成稳定路径级差异与 canonical hash。
- `manifest explain` 输出迁移、六层配置来源、安全合并、纯词法路径、runtime/product/backend/workflow 路由轨迹。

### Plan、Simulation 与模板

- `plan build` 委托 `ExecutionPlanBuilder`；`verify` 同时执行 Execution Plan Schema 与 hash/plan_id 校验；`hash` 重算语义 hash。
- `simulate` 只允许 `offline` 与 `nextgen_mock`，后端通过 run override 显式选择后再构建计划；委托 `simulate_plan`，不导入执行器、不启动子进程。
- `templates list` 读取 Skill 内 catalog；`templates create` 只创建 canonical `project_manifest.json`，输出限制为当前项目相对路径，拒绝覆盖以及写入安装目录/原始 GitHub Skill。
- unavailable/Real backend 请求由静态 registry fail-closed；`legacy_com` 定向 smoke 返回 `BACKEND_NOT_AVAILABLE` / exit 4。

### 错误与退出码

- 参数错误也进入结构化 `SkillRuntimeError` JSON，不输出非结构化 argparse 错误。
- 退出码自检覆盖并通过：
  - 2：Manifest/Plan 校验
  - 3：配置、runtime、product、workflow 冲突
  - 4：backend/Real execution 不可用
  - 5：approval/权限提升/不可执行计划
  - 6：路径/真实 CAD 访问阻断
  - 7：Manifest 版本/迁移
  - 8：安全基线
  - 9：内部错误

## Tests Run

未运行 pytest。全部检查设置 `PYTHONDONTWRITEBYTECODE=1`，仅使用 JSON/Schema/合同和临时 synthetic JSON：

1. 顶层、`manifest`、`plan`、`templates` 的 `--help`：PASS。
2. 内存 CLI smoke：20/20 PASS，覆盖 1.0 validate/normalize/migrate preview/diff、1.1 config/runtime/product/backend/workflow、plan build、offline/nextgen_mock simulate、templates list 和 5 个旧入口。
3. 临时目录 synthetic JSON smoke：`plan verify`、`plan hash`、`templates create` 3/3 PASS；临时目录退出后自动清理。
4. 结构化退出码 2–9：8/8 PASS。
5. unavailable Real backend：`legacy_com → BACKEND_NOT_AVAILABLE / exit 4` PASS。
6. Python AST/导入检查：PASS；无 `subprocess`、`win32com`、`pythoncom`、`comtypes` 导入，无 CAD/COM/SendCommand 调用。

## Test Result

PASS（CLI 轻量 smoke 范围）：

- 新命令：16/16 已实现
- 旧入口：5/5 已保留并 smoke 通过
- CLI 叶子命令总数：21
- 实际调用 smoke：23/23 PASS（20 内存命令 + 3 临时 JSON 命令）
- exit code：2–9 全覆盖 PASS
- unavailable/Real backend fail-closed：PASS
- pytest：未运行（按任务要求）

## Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened DWG: NO
* Read/Parsed/Scanned/Hashed DWG or DXF: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Started subprocess from Skill CLI: NO
* Enabled Legacy backend: NO
* Enabled NextGen Real backend: NO
* Saved or modified CAD file: NO
* Ran pytest or external integration: NO
* Executed Git command: NO

## Risks Found

- 当前 CLI 仅完成实现与轻量 smoke；正式 `tests/config_driven`、Skill 定向测试和默认安全回归仍由 test_agent 执行。
- `templates create` 有意只接受当前目录下的相对输出目录；如未来需要外部模板输出，必须新增显式路径政策和安全审计，不能放宽现有限制。
- 词法路径解析不观察磁盘 symlink/junction；真实运行前仍必须由独立 runtime guard 验证。CLI 未把词法解析声明为真实身份验证。
- 旧入口默认直接 JSON 与新命令 envelope 并存是兼容决策；机器调用如需统一结构应显式使用 `--json`。

## Remaining Work

- test_agent 增加并运行 CLI 正式测试、默认安全回归及 marker 隔离测试。
- docs_agent 将 21 个命令、envelope、退出码和模板相对路径限制回填到 CLI 文档。
- Manager 汇总 WP1/WP3/CLI 后再决定是否进入后续工作包；本 Agent 不推进 S2 下一阶段。

## Recommendation

CLI-002 可交付 test_agent。正式验收应继续保持离线守卫，使用 synthetic JSON/临时目录，不读取 Manifest 中声明的 DWG/DXF 路径，也不得启用任何 Real backend。

---

## CAD-CONFIG-S2-INSTALL-009（安装收尾）

### Files Read

- `skills/autocad-tianzheng-automation/SKILL.md`
- `skills/autocad-tianzheng-automation/scripts/validate_skill.ps1`
- `skills/autocad-tianzheng-automation/scripts/sync_skill_installation.ps1`
- 安装目录 `scripts/skill_cli.py`（仅通过 CLI `--help` 与 `templates list` 运行）

### Files Modified

- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_manifest.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_hash_verification.json`

---

## CAD-S3-PRODUCT-CORE-001（ProductProfile 与 Product/Runtime 解耦）

### Files Modified

- `skills/autocad-tianzheng-automation/runtime/product_profile.py`
- `skills/autocad-tianzheng-automation/schemas/product_profile.schema.json`
- `skills/autocad-tianzheng-automation/schemas/project_manifest.schema.json`
- `tests/config_driven/test_s3_product_profile.py`
- `artifacts/s3_product_unification/20260716T173813+0800/product_schema_audit.json`
- 本 outbox（追加本节）

### Work Completed

- 新增不可变 `ProductProfileRegistry`：只包含 `generic_autocad`、`tianzheng_water`、`tianzheng_hvac` 与 `offline_analysis`；暖通状态明确为 `INTERFACE_ONLY`。
- 新增独立 `ExecutionRuntime`：`offline`、`mock`、`com`、`objectarx`；前两者仅是离线/Mock 合同，后两者固定 `NOT_AVAILABLE`，选择时 fail-closed。
- 新增 `ProductRuntimeRouter`，产品与执行运行时独立选择；其结果始终 `execution_allowed=false`，不提供真实 CAD 执行。
- Canonical Manifest Schema 接受 S3 可选字段 `product.profile` 与 `runtime.execution_runtime`，同时保留原 `requested_product`/`runtime_mode` 的 S2 兼容入口。

### Tests Run

```powershell
$env:PYTHONPATH='.'
python -m pytest -q tests/config_driven/test_s3_product_profile.py tests/config_driven/test_manifest_schema.py tests/config_driven/test_runtime_product_routing.py tests/config_driven/test_product_adapters.py
```

结果：`35 passed`。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO

### Remaining Integration

- Workflow/Adapter Agent 可按四个稳定 product_id 完成绑定；CLI 若需要展示新运行时应调用 `ProductRuntimeRouter`，不得把 `mock` 描述为真实执行。

### Post-audit Minimal Fix

- `product.profile` 与 S2 兼容字段 `product.requested_product` 同时存在时，先对 `autocad`、`unknown`、`offline` 等别名归一化；归一化后不同即 `PRODUCT_MODE_CONFLICT` fail-closed。
- S3 profile 与既有 `runtime.runtime_mode` 不一致时，在新 Router 与既有 `RuntimeRouter` 两条路径均 fail-closed，消除静默不一致。
- 所有 `com`/`objectarx` 请求（含 `offline_analysis` 的不兼容分支）统一带有 `runtime_status=NOT_AVAILABLE` 与 `real_backend=NOT_IMPLEMENTED` 结构化证据。
- 回归命令：`PYTHONPATH=. python -m pytest -q tests/config_driven/test_s3_product_profile.py tests/config_driven/test_runtime_product_routing.py tests/config_driven/test_manifest_schema.py`，结果：`35 passed`。

### CLI 最小集成

- `_resolve_pipeline` 已调用 `ProductRuntimeRouter.select_from_manifest`，将独立产品/执行运行时选择保存为 `product_runtime` context；不修改 ExecutionPlan Schema，也不调用 backend。
- `manifest explain` 输出 `product_profile`；`product select` 在原 Adapter 选择字段外追加 `product_profile`，其中明确 `execution_allowed=false`。
- 回归命令：`PYTHONPATH=. python -m pytest -q tests/config_cli/test_manifest_cli.py tests/config_cli/test_routing_cli.py tests/config_driven/test_s3_product_profile.py tests/config_driven/test_runtime_product_routing.py`，结果：`37 passed`。

---

## CAD-CONFIG-S2-TEMPLATE-OUTPUT-011（安装态模板外部临时输出修正）

### Files Read

- `agent_inbox/command_registry_agent.md`
- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `skills/autocad-tianzheng-automation/config/path_resolver.py`（只读确认未改）
- `tests/config_cli/test_plan_template_cli.py`

### Files Modified

- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `tests/config_cli/test_plan_template_cli.py`
- 本 outbox（追加此节）

### Work Completed

- `templates create` 不再把 CLI 模板输出强制套用 Manifest 的 `project_relative` 文档路径策略；新增 CLI 专用、纯词法的输出目录校验。
- 仍允许原有当前目录相对输出；新增允许显式指定的安装目录/规范源目录之外的绝对临时目录。
- 持续拒绝规范源、安装目录、原始 GitHub Skill、UNC、`..` 路径段和 `.dwg`/`.dxf` 输出目录；模板仍只写 UTF-8 JSON，拒绝覆盖既有目标。
- 未修改 `ManifestPathResolver`、Registry、Backend、守卫、安装目录或任何 CAD/Real backend 路径。

### Tests Run

```powershell
python -m pytest -q tests/config_cli/test_plan_template_cli.py
```

结果：`9 passed in 1.67s`。

新增覆盖：显式外部临时输出成功；规范源和安装目录输出拒绝；路径遍历、UNC、`.dwg`、`.dxf` 输出拒绝。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO

### Remaining Work

Manager 需将规范源同步到安装目录后，重新执行安装态 CLI 外部临时输出验证及 D/E 回归；本修正未自行同步或执行 Git 操作。
- 本 outbox（追加此节）

### Work Completed

- 规范源与安装目录的 `.dwg/.dxf` 文件名均为 0；未读取任何 CAD 内容。
- `validate_skill.ps1`：PASS（`Skill is valid!`）。
- 同步 dry-run：131 文件，`ADD=61`、`UPDATE=17`、`UNCHANGED=53`，`DeletesUnknownFiles=false`，未知删除为 0。
- 实际同步并逐文件校验：PASS；仅复制上述新增/更新项，未删除未知安装文件。
- 同步后非排除文件 SHA256：源/安装均为 131 文件，source-only=0、destination-only=0、mismatch=0。
- 安装目录 CLI：`--help` PASS；`templates list --json` PASS（10 个模板）。

### Installed CLI Template Verification

从安装目录以相对输出 `s2_cli_synthetic_probe` 运行：

```powershell
python -m scripts.skill_cli templates create offline_analysis --output s2_cli_synthetic_probe --json
```

按路径安全策略返回 exit 6：`PATH_EXTERNAL_NOT_ALLOWED`（field=`output`）。当前工作目录就是 Skill 安装目录，而模板输出守卫明确禁止向安装目录写入。因此未绕过策略，未继续执行该临时模板的 `manifest validate` / `plan build`；这是安装态 CLI 使用边界，不是 CAD 访问或同步失败。

### Test Result

- 安装同步和哈希验证：PASS。
- 安装目录 CLI 基础可用性：PASS。
- “在安装目录内创建模板”的组合自检：按 fail-closed 路径政策 BLOCKED（exit 6），需 Manager 按 S2 验收口径决定是否视为预期安全拒绝。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO
* Deleted unknown installation files: NO

### Evidence

- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_manifest.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_hash_verification.json`

---

## CAD-POST-S2-FREEZE-SKILL-003（Skill 与能力冻结）

### Files Read

- `skills/autocad-tianzheng-automation/` 与安装目录中的非 CAD Skill 文件，仅用于清单与 SHA256 比对。
- `skills/autocad-tianzheng-automation/scripts/validate_skill.ps1`。

### Files Modified

- `artifacts/post_s2_baseline_freeze/20260716T170858+0800_post_s2/skill_installation_freeze.json`
- `artifacts/post_s2_baseline_freeze/20260716T170858+0800_post_s2/capability_matrix.json`
- `artifacts/post_s2_baseline_freeze/20260716T170858+0800_post_s2/security_state.json`
- 本 outbox（追加本节）

### Work Completed

- `quick_validate` 为 PASS（exit 0）。
- 规范源与安装目录非排除文件均为 131；逐个相对路径及 SHA256 完全一致，未知新增、未知删除和哈希不一致均为 0。
- 规范源总文件数 170、安装目录总文件数 161；差异均为排除的本地 Python 缓存（`__pycache__/*.pyc`），不属于安装缺失或未知 Skill 文件。
- 两端 `.dwg/.dxf` 文件数均为 0；本冻结未读取任何 CAD 内容。
- 能力矩阵明确冻结：Skill 包装、配置驱动、Workflow Registry、Execution Plan 与 Mock Backend 为 PASS；Real AutoCAD、Tianzheng Real、ObjectARX、NextGen Real 均为 `NOT_IMPLEMENTED`；生产绘图为 `DISABLED`。
- 安全状态冻结：`production_allowed=false`、`production_d1_allowed=false`、`real_cad_access=false`、`real_backend=false`；AutoCAD、天正、COM 连接计数均为 0。

### Test Result

```text
validate_skill.ps1: PASS (exit 0)
source/install nonexcluded SHA256 match: PASS
```

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Performed sync: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO

### Recommendation

本子任务的 Skill、能力和安全冻结证据均为 PASS；等待 Manager 汇总 Git、源码清单和测试冻结结果后进行人工审查，不进入 S3。

---

## CAD-CONFIG-S2-INSTALL-POSTFIX-012（安装后置复验）

### Files Read

- `skills/autocad-tianzheng-automation/SKILL.md`
- `skills/autocad-tianzheng-automation/scripts/validate_skill.ps1`
- `skills/autocad-tianzheng-automation/scripts/sync_skill_installation.ps1`
- 安装目录 CLI（仅 `--help`、`templates list`、外部临时模板 JSON 的 validate/plan 命令）

### Files Modified

- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_manifest.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_hash_verification.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_postfix_verification.json`
- 本 outbox（追加本节）

### Work Completed

- 源和安装目录 `.dwg/.dxf` 文件名计数均为 0；未读取任何 CAD 内容。
- `quick_validate` PASS。
- sync dry-run 与 apply 均完成：131 文件，`UPDATE=1`、`ADD=0`、`UNCHANGED=130`，未删除未知安装文件。
- 非排除、非 CAD 文件的 SHA256 逐项比对 PASS：源/安装各 131，缺失 0、未知 0、不一致 0。
- 安装目录 CLI `--help` 和 `templates list --json` 均 PASS；显式安装外临时目录的 `templates create`、`manifest validate`、`plan build` 均为 exit 0。

### Test Result

安装目录输出拒绝行为发生，但退出码合同失败：

```text
expected exit code: 6
actual exit code:   3
error code:         CONFIG_CONFLICT
```

按 `CAD-CONFIG-S2-INSTALL-POSTFIX-012` 的“任何异常停止报告”要求，未自行修改 CLI 或继续后续操作。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO
* Deleted unknown installation files: NO

### Recommendation

Manager 应将安装目录拒绝路径的统一退出码合同最小修复为 exit 6 后，重新执行本后置验证；本 Agent 未提升 Backend、审批或生产权限。

---

## CAD-S4-PROTOCOL-001（NextGen MCP Protocol / Tool Registry）

### Files Read

- `mcp_nextgen/control_server/{server,dispatcher}.py`
- `mcp_nextgen/protocol/{version,enums,models}.py`
- `mcp_nextgen/schemas/{core,tools,validator}.py`
- `tests/nextgen/test_nextgen_handoff.py`

### Files Modified

- `mcp_nextgen/control_server/discovery.py`
- `mcp_nextgen/control_server/server.py`
- `mcp_nextgen/control_server/__init__.py`
- `mcp_nextgen/schemas/tools.py`
- 本 outbox（追加本节）

### Work Completed

- 将既有 9-tool registry 扩展为版本仍为 `1.0.0` 的 13-tool S4 registry，并为每个工具补齐 `errorSchema`、`status`、`available` 与允许的离线/Mock runtime 声明。
- 已注册 3 个静态 MCP resources：能力、工具注册表和固定安全边界；以及 2 个只生成文字的 prompts。资源与提示均为纯数据，不会启动服务或读取文件。
- `cad.capabilities` 现在返回完整、带 `status`/`available`/Schema 的 tool registry，而非仅返回名称列表，便于 Skill 发现真实能力边界。
- `cad.capabilities`、`cad.documents.list`、`cad.document.inspect`、`cad.batch.plan`、`cad.job.status`、`cad.job.approve`、`cad.job.run_mock`、`cad.job.cancel`、`cad.job.events` 为 `IMPLEMENTED_BASELINE`。其中 batch plan 只创建 `PLANNED` Mock 作业；approve 必须绑定 job/plan/operation/product/runtime/expiry；run_mock 仅调用无 CAD 句柄的确定性模拟。
- `cad.entities.query`、`cad.entities.inspect`、`cad.batch.clone`、`cad.batch.transform` 均明确为 `NOT_IMPLEMENTED` 和 `available=false`。
- registry 自检会拒绝将 `NOT_IMPLEMENTED` 工具声明为 `available=true`。

### Tests Run

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CAD_SAFE_TEST_RUN_DIR = Join-Path $env:TEMP 'cad_s4_protocol_registry'
python -m pytest -q tests/nextgen/test_nextgen_handoff.py -k 'server_import_surface or server_factory or tool_schema_registry or control_dispatcher or arbitrary_code_execution_tools'
```

结果：`5 passed, 42 deselected`。

另运行 registry/discovery 纯内存自检：PASS（13 tools、3 resources、2 prompts）；dispatcher synthetic Mock 完整生命周期（plan→approve→run_mock→events/status 及 cancel）smoke：PASS；`.dwg` synthetic 路径返回 `REAL_CAD_PATH_BLOCKED`。

在 S4 service 和测试合同稳定后，补充运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CAD_SAFE_TEST_RUN_DIR = Join-Path $env:TEMP 'cad_s4_nextgen_combined'
python -m pytest -q tests/nextgen/test_nextgen_handoff.py tests/s4
```

结果：`60 passed`。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened/read/parsed/hashed DWG or DXF: NO
* Started listener/TCP/exec/shell: NO
* Enabled Legacy/Real backend: NO
* Production D1 allowed: NO
* Executed Git command: NO

### Remaining Work

- approval/run/cancel/recovery 的状态机合同由 `ControlPlaneService` 提供；当前 MCP 公开工具不新增真实执行入口，`cad.batch.clone` / `cad.batch.transform` 仍不得提升为可用。

### 状态一致性修订

- 发现资源和 `cad.capabilities` 的对外 `control_plane_status` 已统一为 `IMPLEMENTED_BASELINE`，仅表示 S4 Mock-only 控制面合同已实现。
- 同时显式公开 `real_backend_status=NOT_IMPLEMENTED` 与 `real_backend_available=false`；本修订不提升任何 AutoCAD、天正、COM 或生产能力。

---

## CAD-CONFIG-S2-TEMPLATE-REJECT-013（模板输出拒绝码修正）

### Files Modified

- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `tests/config_cli/test_plan_template_cli.py`
- 本 outbox（追加本节）

### Work Completed

- 模板输出位于规范源、安装目录或原始 Skill 时，继续 fail-closed，未改变输出边界或允许范围。
- 此类路径策略违规现在统一抛出 `PATH_EXTERNAL_NOT_ALLOWED`，CLI 映射为 exit code `6`，不再误报为 `CONFIG_CONFLICT`/exit `3`。
- 专用测试同步断言 `PATH_*` 错误码与 exit `6`；安装外临时输出成功与 traversal/UNC/CAD 后缀拒绝覆盖保持不变。

### Tests Run

```powershell
python -m pytest -q tests/config_cli/test_plan_template_cli.py -k 'templates_create'
```

结果：`4 passed, 5 deselected`。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO

### Recommendation

可由 Manager 重新执行 postfix Phase D/E、同步与安装态验证；本修正未触碰 CAD、文件访问守卫、Backend/审批能力或 Git 状态。

---

## CAD-CONFIG-S2-INSTALL-FINAL-014（最终安装验收）

### Files Read

- `skills/autocad-tianzheng-automation/scripts/validate_skill.ps1`
- `skills/autocad-tianzheng-automation/scripts/sync_skill_installation.ps1`
- 规范源与安装目录中的非 CAD Skill 文件（仅用于 SHA256 一一比对）
- 安装目录 CLI，以及安装外临时目录生成的 synthetic JSON Manifest

### Files Modified

- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_manifest.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_hash_verification.json`
- 本 outbox（追加本节）

### Work Completed

- 规范源与安装目录 `.dwg/.dxf` 文件名计数均为 0；未读取任何 CAD 内容。
- `quick_validate`：PASS（exit 0）。
- 安装同步：dry-run 后 apply，131 个非排除文件；`UPDATE=1`、`ADD=0`、`UNCHANGED=130`，未删除未知安装文件。
- 独立 SHA256 一一比对：源/安装各 131，缺失 0、未知 0、不一致 0。
- 安装态 `--help`、`templates list`、安装外临时目录 `templates create -> manifest validate -> plan build` 均 exit 0。
- 安装目录输出仍 fail-closed：`PATH_EXTERNAL_NOT_ALLOWED`，exit 6。

### Test Result

`CAD-CONFIG-S2-INSTALL-FINAL-014`: PASS。

首次链路中将生成 Manifest 误定位为模板名子目录，导致对不存在的路径调用 validate/plan（exit 2）；确认 CLI 正确将文件生成在输出根 `project_manifest.json` 后，以实际生成路径重跑，两个命令均 exit 0。此项仅为验收调用路径修正，未改代码、配置、Git 或 CAD 文件。

### Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened or read DWG/DXF: NO
* Started CAD/Real backend: NO
* Executed Git command: NO
* Modified original GitHub Skill: NO
* Deleted unknown installation files: NO

### Evidence

- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_manifest.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/installation_hash_verification.json`

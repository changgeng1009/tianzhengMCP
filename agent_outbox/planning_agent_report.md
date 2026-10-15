# Agent Report

## Agent Name

planning_agent

## Assigned Task

CAD-CONFIG-S2-PLAN-001 — 只读审计原 CAD-CONFIG-S2 需求与当前统一 Skill，形成文件级实施计划、分工、依赖、验收矩阵、报告映射和 source change 边界。

## Files Read

- `C:/Users/example-user/.codex/attachments/example-attachment/pasted-text.txt`
- `skills/autocad-tianzheng-automation/schemas/project_manifest.schema.json`
- `skills/autocad-tianzheng-automation/runtime/*.py`
- `skills/autocad-tianzheng-automation/safety/*.py`
- `skills/autocad-tianzheng-automation/adapters/**/adapter.py`、`backend.py`
- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `skills/autocad-tianzheng-automation/scripts/sync_skill_installation.ps1`
- `skills/autocad-tianzheng-automation/capabilities/backend_matrix.json`
- `skills/autocad-tianzheng-automation/manifests/template.json`
- `skills/autocad-tianzheng-automation/tests/test_skill.py`
- `skills/autocad-tianzheng-automation/SKILL.md`、`README.md`
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/new_baseline_verifier_result.json`
- 当前 Git 分支、HEAD 和工作区状态（仅元数据）

## Files Modified

- `agent_outbox/planning_agent_report.md`

未修改统一 Skill、项目源码、测试、冻结基线或安装目录。

## Authoritative Baseline Gate

- 权威 baseline ID：`CAD-SAFE-20260714T220937+0800`。
- 权威 final bundle SHA256：`87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`。
- 正式 verifier 证据：exit code 0，source manifest、checksum、closure conditions 全部 `PASS`。
- 禁止使用 Skill 中 freeze 前 provenance SHA `13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9` 作为 S2 入口基线。
- S2 实施前必须现场再次运行 verifier；若失败，立即返回 `CAD_CONFIG_S2_BLOCKED_BY_BASELINE_DRIFT`，不得写入任何 S2 文件。

## Existing Module Audit

| 域 | 当前事实 | S2 结论 |
|---|---|---|
| Manifest | `project_manifest.schema.json` 为扁平结构，`schema_version=1.0`；已有 project/task/runtime/product/backend/workflow 等字段的早期形态 | 需要向后兼容升级到 canonical `1.1.0`；保留 1.0 输入与迁移路径，不直接跳 2.0 |
| Runtime | `runtime/selector.py` 实现 5 个模式的基础 fail-closed 选择 | 保留 `select_runtime` 兼容入口，新建可解释的 runtime/product 路由结果与 conflict trace |
| Plan | `runtime/planner.py` 仅按原 manifest JSON 计算简化 hash | 新建 canonical resolved manifest、确定性 execution plan、plan canonicalizer/validator/hasher；旧 `build_offline_plan` 作为 wrapper |
| Capability | `runtime/capability_registry.py` 只按 3 个产品读取 JSON | 扩展为 Product/Backend/Workflow registry，静态读取能力，不连接 CAD |
| Adapter | Generic/Water/HVAC 与 Original/Legacy/NextGen Mock 合同已存在 | 保留类名和状态；只增加 registry/选择结果，不增加真实执行路径 |
| Backend | offline、original adapter、nextgen-mock 可作离线/Mock；Legacy disabled；Real 全部不可用 | 以 capability matrix 为权威，manifest 不得提升 availability；`require_real_execution=true` 必须阻断 |
| Approval | `safety/approval.py` 已绑定 job/document/plan/single-use/expiry | 配置只能声明审批需求；不能生成或继承有效 approval；L3/L4 只输出 blocked plan |
| Path Guard | `runtime/file_guard.py` 仅按后缀和实验目录阻断读取 | 另建纯字符串/结构路径解析器；不打开、不 stat/hash CAD，阻断 traversal/UNC/source-output collision/安装目录输出 |
| CLI | 4 个旧命令：inspect、validate、select-runtime、build-plan，加 capabilities | 增加分组命令，保留旧命令别名和输出兼容层；默认 offline、结构化 error/exit code |
| Workflow | 11 个 Markdown 过程文档，无机器可读 registry | 新增机器可读 workflow 定义；真实写入合同均为 `NOT_EXECUTABLE_CURRENTLY` |
| Template | 5 个 examples + 1 个扁平 template | 新增 10 个 canonical 模板、catalog、capability matrix；全部虚构和 project-relative |
| Tests | Skill 当前 64 项，项目有 `tests/skill`、`tests/nextgen`，无 `tests/config_driven` | 新增独立配置测试域；现有安全 guard、64 Skill、47 NextGen 全部保留 |

## Recommended Target Architecture

Canonical 数据流固定为：

`ManifestLoader → SchemaValidator → ManifestMigrator → DefaultResolver → SecurityAwareConfigMerger → ManifestPathResolver → RuntimeSelector → ProductAdapterRegistry → BackendSelector → WorkflowRegistry → ExecutionPlanBuilder → Canonicalizer/Hasher → Offline/MockSimulator → EvidenceBundle`

建议 canonical version 为 `1.1.0`，最低兼容版本为现有 `1.0`（同时接受规范化别名 `1.0.0`）。禁止静默丢字段；未知顶层字段报 `MANIFEST_UNKNOWN_FIELD`，厂商/项目扩展只允许进入显式 `extensions`。

## File-Level Ownership and Work Packages

### WP0 — 安全入口与变更快照（safety_audit_agent + planning_agent）

只生成 artifacts，不改实现：

- `artifacts/cad_config_driven_s2/<run_id>/baseline_precheck.json`
- `artifacts/cad_config_driven_s2/<run_id>/source_change_manifest.json` 的 before snapshot/排除清单
- `artifacts/cad_config_driven_s2/<run_id>/configuration_layer_matrix.json`

依赖：无。完成 verifier PASS 和 start snapshot 后才解锁 WP1。

### WP1 — Manifest、版本、默认值、安全合并、路径与 CLI（command_registry_agent）

独占目标文件：

- 修改 `schemas/project_manifest.schema.json`（canonical 1.1.0）
- 新增 `schemas/project_manifest_v1_0.schema.json`
- 新增 `schemas/execution_plan.schema.json`
- 新增 `config/__init__.py`
- 新增 `config/models.py`
- 新增 `config/errors.py`
- 新增 `config/canonical.py`
- 新增 `config/manifest_loader.py`
- 新增 `config/versioning.py`
- 新增 `config/migrator.py`
- 新增 `config/default_registry.py`
- 新增 `config/merge.py`
- 新增 `config/path_resolver.py`
- 新增 `config/defaults/system_defaults.json`
- 新增 `config/defaults/skill_defaults.json`
- 新增 `config/defaults/plain_autocad_defaults.json`
- 新增 `config/defaults/tianzheng_water_defaults.json`
- 新增 `config/defaults/tianzheng_hvac_defaults.json`
- 新增 `config/defaults/offline_analysis_defaults.json`
- 修改 `runtime/errors.py`，集中增加规定 error code，但保留既有异常类
- 修改 `scripts/skill_cli.py`，增加分组命令并保留 4 个旧命令与 `capabilities`

边界：`approval` 不参与默认继承；path resolver 只处理字符串/边界，不执行 `exists/stat/read/hash/resolve(strict=True)` 于 CAD 输入。

### WP2 — Product/Backend 静态能力合同（cad_bridge_agent）

独占目标文件：

- 新增 `adapters/registry.py`
- 按需最小修改 `adapters/generic_autocad/adapter.py`
- 按需最小修改 `adapters/tianzheng_water/adapter.py`
- 按需最小修改 `adapters/tianzheng_hvac/adapter.py`
- 按需最小修改 `adapters/*/__init__.py`
- 修改 `capabilities/backend_matrix.json`
- 新增 `capabilities/product_adapter_matrix.json`

状态不变量：Generic=`OFFLINE_PLANNING_IMPLEMENTED`；Water real=`NOT_IMPLEMENTED` 且 topology/engineering 未验证；HVAC read partial、write interface-only；Legacy=`DISABLED_CONTRACT_ONLY`；所有 Real backend=`NOT_IMPLEMENTED/NOT_AVAILABLE`。不得导入 COM、启动 CAD 或调用旧执行器。

### WP3 — Runtime/Product/Backend/Workflow 路由与确定性 Plan（intent_mapper_agent）

独占目标文件：

- 修改 `runtime/contracts.py`，新增 resolved/routing/plan immutable contracts，保留旧 ABC
- 修改 `runtime/selector.py`，旧 `select_runtime` 委托新 selector
- 修改 `runtime/planner.py`，旧 `build_offline_plan` 委托新 builder
- 新增 `runtime/routing.py`
- 新增 `runtime/backend_registry.py`
- 新增 `runtime/workflow_registry.py`
- 新增 `runtime/execution_plan.py`
- 新增 `runtime/simulation.py`
- 新增 `config/workflows/*.json`（11 个用户指定 workflow）
- 新增 `templates/<template_id>/project_manifest.json`（10 个指定模板）
- 新增 `templates/template_catalog.json`
- 新增 `templates/template_capability_matrix.json`

依赖：WP1 canonical/resolution contracts + WP2 adapter/backend registry。计划 hash 排除时间、随机值、临时目录和 notes；路径/键序/斜杠归一化；`plan_id` 由 hash 派生。任何 L3/L4、Real backend 或真实写入 workflow 都生成 blocked plan。

### WP4 — 测试（test_agent）

独占目标文件：

- 新增 `tests/config_driven/conftest.py`
- 新增 `tests/config_driven/test_manifest_schema.py`
- 新增 `tests/config_driven/test_versioning_migration.py`
- 新增 `tests/config_driven/test_defaults_merge.py`
- 新增 `tests/config_driven/test_path_resolution.py`
- 新增 `tests/config_driven/test_runtime_product_routing.py`
- 新增 `tests/config_driven/test_backend_workflow.py`
- 新增 `tests/config_driven/test_execution_plan.py`
- 新增 `tests/config_driven/test_templates.py`
- 新增 `tests/config_driven/test_cli.py`
- 新增 `tests/config_driven/test_safety_boundaries.py`
- 修改 `skills/autocad-tianzheng-automation/tests/test_skill.py`，仅增加兼容与新功能断言，不删除旧断言
- 按需修改 `tests/test_skill_cli.py`、`tests/skill/test_skill_package.py`，只增加兼容断言

所有 CAD 扩展 fixture 只能在 `tmp_path` 动态生成随机 synthetic 内容并显式登记；不得读取 artifacts/用户目录中的 CAD，也不得借测试跳过掩盖失败。

### WP5 — 文档与 Skill 说明（docs_agent）

独占目标文件：

- 新增 `docs/configuration_driven_architecture.md`
- 新增 `docs/project_manifest_reference.md`
- 新增 `docs/manifest_versioning_and_migration.md`
- 新增 `docs/config_merge_precedence.md`
- 新增 `docs/path_resolution_policy.md`
- 新增 `docs/runtime_and_product_routing.md`
- 新增 `docs/backend_selection_policy.md`
- 新增 `docs/workflow_registry.md`
- 新增 `docs/execution_plan_determinism.md`
- 新增 `docs/config_cli_reference.md`
- 新增 `docs/config_security_boundaries.md`
- 新增 `docs/template_guide.md`
- 新增 `docs/s2_known_limitations.md`
- 修改 `SKILL.md`、`README.md`、`CHANGELOG.md`

依赖：WP1–WP3 接口冻结；可以先建文档骨架，但最终参数、错误码和 CLI 必须从实际实现回填，禁止文档领先虚报。

### WP6 — 审计、安装与终稿（safety_audit_agent + command_registry_agent + planning_agent + docs_agent）

- safety_audit_agent：复核 safety merge、路径边界、零 CAD/COM、backend 状态和最终测试证据。
- command_registry_agent：仅在全部测试 PASS 后执行 `quick_validate`、sync dry-run、apply、70+ 文件逐项 SHA 校验和安装态 CLI/模板验证；未知安装文件不删除。
- planning_agent：关闭 source change manifest，确保 final change set 仅含 start snapshot 后的获批 S2 文件。
- docs_agent：生成 `known_limitations.json`、`s2_final_report.md/json`。

## Dependency Order

1. **G0 Baseline gate**：现场 verifier + start snapshot；失败立即停止。
2. **G1 Contract freeze**：WP1 先完成 version/schema/error/canonical contract；safety_audit_agent 审查后锁定。
3. **G2 Config core**：WP1 完成 loader/migrator/default/merge/path；单元测试先绿。
4. **G3 Capability contracts**：WP2 可与 G2 后半段并行，但必须基于 G1 枚举和错误模型。
5. **G4 Routing/plan**：WP3 等待 G2 + G3；先 routing，再 workflow，再 execution plan/hash/simulation。
6. **G5 CLI/templates**：CLI 等待 G2/G4；模板等待 schema/workflow 稳定。
7. **G6 Focused tests**：WP4 按模块增量运行，接口变更不得靠放宽守卫或删除断言解决。
8. **G7 Documentation**：WP5 回填最终接口与限制。
9. **G8 Full acceptance**：安全回归与零访问摘要全部 PASS。
10. **G9 Installation**：quick_validate → dry-run → apply → SHA → 安装态 CLI/模板。
11. **G10 Evidence close**：source change manifest、独立安全复核、32 项报告、最终状态。

## Test Sequence

所有 pytest 命令均使用 `-c pytest.ini --strict-markers` 和：

`-m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"`

固定顺序：

1. S2 写入前正式 baseline verifier（权威 ID/SHA）。
2. 守卫轻量自检，确认 plugin 启用；专项预期阻断与默认违规分开计数。
3. `pytest -q tests/config_driven ...`。
4. `pytest -q skills/autocad-tianzheng-automation/tests ...`，要求原 64 项不减少。
5. `pytest -q tests/nextgen ...`，要求现有 47 项不减少且只走 Mock/control-plane。
6. `pytest -q tests/test_skill_cli.py tests/skill ...` 或最终确认的 CLI 路径。
7. 默认安全回归：`pytest -q -m <六类排除表达式>`。
8. `quick_validate`、安装 dry-run/apply/hash、安装态 CLI 和 10 个模板验证。

每阶段均要求：真实 DWG read/write=0、CAD process=0、COM=0、天正=0、real backend execution=0；发生意外真实 CAD 尝试时立即停止，不进入下一阶段。

## Acceptance Matrix

| 验收域 | 最低证据 | PASS 条件 |
|---|---|---|
| Baseline | `baseline_precheck.json` | ID=`CAD-SAFE-...`、final SHA=`87b995...`、verifier 三项 PASS |
| Schema/version | schema + version/migration matrix | canonical 1.1.0；1.0 可迁移；too old/new/unknown 明确失败；未知字段不丢失 |
| Defaults/merge | registry/trace + tests | 6 层来源可追踪；安全值只收紧；approval 不继承；allow/deny/protected 合并符合策略 |
| Path | policy + tests | 相对 manifest 目录；cwd 无关；traversal/UNC/外部/碰撞/安装目录阻断；不打开 CAD |
| Routing | runtime/product/backend/workflow matrix | 5 runtime；冲突 fail-closed；不可用 backend 不被 manifest 提升；不 silent fallback |
| Adapters | product/backend matrix | 四类离线 adapter 状态准确；Real/Legacy 边界不变 |
| Workflow | registry + 11 定义 | 11 项齐全；写入合同 `NOT_EXECUTABLE_CURRENTLY` |
| Templates | catalog + validation | 10 项、虚构、相对路径、Schema PASS；写入模板生成 blocked plan |
| Plan | schema/vectors/determinism | 同输入同 hash；键序/时间/斜杠非语义变化不改 hash；语义变化改 hash；verify 可检出 mismatch |
| CLI | command matrix + tests | 新增 16 个分组命令能力；旧 5 个入口保留；JSON/error_code/exit code 符合约定；默认 offline |
| Safety | guard/log/summary | DWG read/write=0；CAD/COM/天正/Real backend=0；Manifest 无法授予 L4 |
| Compatibility | Skill/NextGen/default regression | 原测试不减少、不删除；64 Skill、47 NextGen 基线不回退；默认回归 0 failed |
| Installation | manifest/hash report | unknown 不删除；源/安装逐项 SHA 一致；原始 GitHub Skill unchanged |

## Artifact Report Mapping

| 输出 | 责任 Agent |
|---|---|
| `baseline_precheck.json` | safety_audit_agent |
| `existing_manifest_audit.json`、`manifest_schema_change_report.json`、`manifest_version_matrix.json`、`manifest_migration_matrix.json` | command_registry_agent |
| `configuration_layer_matrix.json` | planning_agent |
| `default_registry.json`、`config_merge_policy.json`、`path_resolution_policy.json` | command_registry_agent，safety_audit_agent 复核 |
| `security_merge_test_results.json` | test_agent |
| `runtime_routing_matrix.json`、`workflow_registry.json`、`template_catalog.json` | intent_mapper_agent |
| `product_adapter_matrix.json`、`backend_selection_matrix.json` | cad_bridge_agent |
| `template_validation_results.json` | test_agent |
| `execution_plan_schema.json` | command_registry_agent |
| `execution_plan_determinism_results.json`、`plan_hash_test_vectors.json` | test_agent |
| `cli_command_matrix.json` | command_registry_agent |
| `cli_test_results.json`、`config_unit_test_results.json`、`skill_test_results.json`、`nextgen_test_results.json`、`safe_default_regression_results.json`、`default_test_file_access_summary.json` | test_agent |
| `source_change_manifest.json` | planning_agent |
| `installation_manifest.json`、`installation_hash_verification.json` | command_registry_agent；test_agent 独立抽查 |
| `known_limitations.json`、`s2_final_report.md/json` | docs_agent；safety_audit_agent 最终签核 |

## Source Change Boundary

1. S2 的 before 状态以 **现场 verifier 通过后的当前文件系统快照** 为准，不以 `git diff HEAD` 为准。
2. start snapshot 必须记录路径、类型、SHA256（仅源码/Schema/JSON/Markdown/配置；排除 DWG/DXF、output、artifacts 二进制、cache、`.git`、临时文件）。
3. 当前全部预存 modified/deleted/untracked 路径进入 `preexisting_workspace_changes`，不归因于 S2；用户已确认的预存删除不构成规划阻断，也不得恢复、删除、stage 或改写。
4. `agent_inbox/`、`agent_outbox/` 和本阶段 `artifacts/cad_config_driven_s2/<run_id>` 属于协作/证据变化，不计入 S2 product source change。
5. S2 product source 只允许本报告 WP1–WP5 列出的 Skill 源、Schema、配置、模板、文档和测试路径；任何额外业务路径均触发 `UNPLANNED_SOURCE_CHANGE`。
6. 每个 source change 记录 `path/before_sha256/after_sha256/change_type/owner/work_package/reason/tests`；新增文件 before 为 null。
7. 不修改 `mcp_nextgen`、`mcp`、P2/P3/P4.1、真实执行器、安全 guard、原始 GitHub Skill或冻结基线。
8. 基线预检证明的是 S2 开始前状态；S2 的预期源码修改会使该 source manifest 不再代表最终源码。最终报告不得把入口基线伪称为 S2 后当前源码基线；完成后应建议另立后续安全重新冻结门，不得覆盖父基线。

## Stop Conditions

任一条件触发即停止后续包并保留证据：

- 入口 verifier 非 PASS、ID/SHA 不匹配：`CAD_CONFIG_S2_BLOCKED_BY_BASELINE_DRIFT`。
- 任何 DWG/DXF 被成功读取、写入、解析、扫描或哈希，或 CAD/天正/COM/Real backend 被触发：`CAD_CONFIG_S2_REAL_CAD_ACCESS_VIOLATION`。
- 发现 WP 清单外源码变化且无法解释：`UNPLANNED_SOURCE_CHANGE`，不得混入 source change manifest。
- Schema 迁移静默丢字段、未知字段被吞、版本无迁移路径。
- 安全字段被放宽、Manifest/override 提升 production/L3/L4/backend availability、approval 被继承或伪造。
- Runtime/Product/Backend/Workflow 冲突发生 silent fallback 或 Mock 冒充 Real。
- execution plan 在相同 canonical 输入下 hash 不稳定，或 hash mismatch 未阻断。
- 原 64 Skill、47 NextGen、旧 CLI/adapter/checkpoint/guard 兼容性被删除或弱化。
- 默认安全回归有失败或 unexpected guard block。
- 同步准备删除未知安装文件、源/安装 SHA 不一致、原始 GitHub Skill发生变化。

## Work Completed

- 已识别当前 Manifest、runtime selector、planner、capability registry、adapter、backend、approval、file guard、CLI、workflow、template 和测试结构。
- 已确定 canonical 1.1.0 的向后兼容实施策略。
- 已建立 6 个工作包、文件级独占所有权、10 个依赖 gate、测试顺序、13 域验收矩阵、32 项报告映射和 fail-closed 停止条件。
- 已明确 source change 与预存工作区变化隔离规则。

## Tests Run

- 未运行 pytest。
- 未运行 CAD-CONFIG-S2 verifier；仅读取已通过的正式 verifier 证据，实际实施仍须在写入前现场复核。
- 只执行文本/JSON/源码只读审计和 Git 元数据查看。

## Test Result

`CAD_CONFIG_S2_PLAN_READY_FOR_MANAGER_ROUTING`

## Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Used COM: NO
* Opened DWG: NO
* Read/Parsed/Scanned/Hashed DWG or DXF: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO
* Modified Skill/source/tests/baseline/installation: NO

## Risks Found

- 当前扁平 `1.0` 与目标 nested canonical 模型差异较大，若直接原地替换会破坏 5 个旧 examples 和旧 CLI；必须由 migrator + compatibility wrapper 过渡。
- Skill 内 baseline SHA 字段仍是 freeze 前 provenance；S2 precheck 只能使用权威外部 baseline reference。
- S2 完成后的源码预期不同于入口冻结源码；若后续阶段要求“当前源码冻结”，必须另建新基线，不能覆盖本次入口基线。
- 路径 canonicalize 在 Windows 上容易误触文件系统；实现必须把 lexical normalization 与 runtime verification 分离，本阶段不跟随链接或打开 CAD。

## Remaining Work

- Manager 按 G0–G10 派发实现、测试、审计、文档和同步任务。
- 实施前现场运行权威 baseline verifier 并冻结 start snapshot。

## Recommendation

在 G0 通过后进入 WP1；优先锁定 Schema/version/error/canonical contract，再并行配置核心与静态 adapter/backend 合同。任何真实 CAD、权限提升或非计划源码变化均 fail-closed。最终 CAD-CONFIG-S2 只能宣称离线配置驱动和 NextGen Mock 可用，不得宣称真实执行。

# Agent Report

## Agent Name

command_registry_agent

## Assigned Task

CAD-CONFIG-S2-WP1 — 实现 canonical Manifest 1.1.0、1.0/1.0.0 兼容迁移、canonical serialization、六层默认值、限制性安全合并、纯词法路径解析、统一错误模型及 Execution Plan Schema。

## Files Read

- `agent_inbox/command_registry_agent.md`
- `skills/autocad-tianzheng-automation/schemas/project_manifest.schema.json`（旧 1.0）
- `skills/autocad-tianzheng-automation/runtime/errors.py`
- `skills/autocad-tianzheng-automation/examples/*.json`
- `skills/autocad-tianzheng-automation/runtime/selector.py`
- `skills/autocad-tianzheng-automation/runtime/planner.py`
- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `skills/autocad-tianzheng-automation/safety/approval.py`
- `skill-creator/SKILL.md`

## Files Modified

共 20 个 Owned Files：

1. `schemas/project_manifest.schema.json`
2. `schemas/project_manifest_v1_0.schema.json`
3. `schemas/execution_plan.schema.json`
4. `runtime/errors.py`
5. `config/__init__.py`
6. `config/models.py`
7. `config/errors.py`
8. `config/canonical.py`
9. `config/versioning.py`
10. `config/migrator.py`
11. `config/manifest_loader.py`
12. `config/merge.py`
13. `config/default_registry.py`
14. `config/path_resolver.py`
15. `config/defaults/system_defaults.json`
16. `config/defaults/skill_defaults.json`
17. `config/defaults/plain_autocad_defaults.json`
18. `config/defaults/tianzheng_water_defaults.json`
19. `config/defaults/tianzheng_hvac_defaults.json`
20. `config/defaults/offline_analysis_defaults.json`

另按任务要求更新本报告：`agent_outbox/command_registry_agent_report.md`。

未修改 CLI、Adapters、tests、`config/workflows/**`、`mcp_nextgen`、P2/P3/P4.1、安全守卫、安装目录、冻结基线或原始 GitHub Skill。

## Work Completed

### Manifest 与版本

- canonical version 固定为 `1.1.0`。
- 保存独立的 1.0/1.0.0 compatibility Schema；原 5 个示例均可验证并迁移。
- `ManifestVersionPolicy` 明确区分 unsupported、too old、too new。
- `ManifestMigrator.preview()` 输出字段变化、deprecated、unmigrated 和 warnings；`migrate()` 返回 canonical Manifest。
- 未知 1.0 顶层字段报 `MANIFEST_UNKNOWN_FIELD`；只有 canonical `extensions` 允许扩展。
- 不继承旧 approval；发现旧审批对象报 `CONFIG_APPROVAL_INHERITANCE_FORBIDDEN`。
- 旧 checkpoint、identity、options 等不静默丢失，进入显式 `extensions.legacy_*`。
- 迁移不生成时间、UUID、approval 或真实身份验证结论。

### Canonical serialization

- `canonicalize()`、`canonical_dumps()`、`canonical_hash()` 提供 UTF-8、稳定键序、紧凑 JSON 和 SHA256。
- 路径字段统一 `/`；支持排除生成时间和临时目录等非语义字段。
- 相同语义 JSON 的 canonical hash 可重复。

### 六层默认值与安全合并

- 顺序固定为：`system_default → skill_default → product_default → workflow_default → project_manifest → run_override`；即高优先级为 run override > project > workflow > product > skill > system。
- `DefaultRegistry.describe()` 输出层级与默认文件来源。
- `DefaultResolver.resolve()` 返回 resolved value、逐叶字段 source trace 和 merge trace。
- `production_allowed`、`production_d1_allowed`、`real_cad_access_allowed`、外部/UNC 权限按 AND 收紧。
- `offline_only`、`dry_run`、`simulate_only`、source write 禁止、sandbox、fail-closed、视觉/工程复核、manual save 按 OR 保持强制。
- L0/L1/L2 可声明离线计划；L3/L4 配置请求直接报 `CONFIG_PRIVILEGE_ESCALATION_BLOCKED`，不形成批准。
- denylist、protected regions、prohibited products、required capabilities 取确定性并集；allowlist 采用 fail-closed 交集。
- 默认/workflow/run override 不得携带 approval；backend availability/support/execution 字段不得由配置覆盖。

### 纯词法路径解析

- `ManifestPathResolver` 只使用 `ntpath` 进行字符串规范化，从不调用 `open/read/stat/exists/hash/resolve`。
- 相对路径锚定 Manifest 目录，不依赖 PowerShell cwd。
- 支持声明 `project_relative`、`workspace_relative`、`absolute_explicit`、`external_readonly`。
- 默认阻断 `..`、UNC、外部绝对路径、项目/workspace 越界、source/output collision、Skill 安装或原始 Skill 输出根。
- 输出 `ResolvedPathRecord.filesystem_accessed=false` 和 `runtime_boundary_verification_required=true`。
- 符号链接/junction 由外部安全层观察后调用 `validate_runtime_boundary_observation()`；本层不探测文件系统。

### Schema 与错误模型

- canonical Schema 含 16 个规定顶层域和显式 extensions。
- Safety const 保持 production/real access=false，source write/sandbox/fail-closed/visual/engineering review=true。
- Execution Plan Schema 覆盖计划身份、路由、审批、文档、保护区、操作、阶段、证据、验证、恢复、阻断、manifest hash 与 plan hash。
- `runtime.errors.SkillRuntimeError` 现提供统一 `to_error_payload()` 和结构化 exit code，同时保留原有异常类兼容性。

## Public APIs for WP3

- `ManifestLoader.load(path)`
- `ManifestLoader.validate(manifest)`
- `ManifestLoader.load_canonical(path)`
- `ManifestMigrator.preview(manifest, to_version="1.1.0")`
- `ManifestMigrator.migrate(manifest, to_version="1.1.0")`
- `ManifestVersionPolicy.normalize(version)`
- `ManifestVersionPolicy.migration_path(version)`
- `ManifestVersionPolicy.compatibility_matrix`
- `DefaultRegistry.system_defaults()` / `skill_defaults()` / `product_defaults()` / `describe()`
- `DefaultResolver.resolve(project_manifest, product_or_mode=..., workflow_defaults=..., run_override=...)`
- `ConfigMerger.merge_layers([(source, mapping), ...])`
- `ManifestPathResolver.resolve_one(...)`
- `ManifestPathResolver.resolve_manifest(manifest, manifest_directory=...)`
- `ManifestPathResolver.validate_runtime_boundary_observation(...)`
- `canonicalize()` / `canonical_dumps()` / `canonical_hash()`
- 所有 `SkillRuntimeError` 子类：`.code`、`.exit_code`、`.to_error_payload()`。

## Compatibility

- 旧 `runtime.errors` 导入类名保持存在。
- 旧扁平 `schema_version=1.0` 与规范化 `1.0.0` 均支持。
- 原 5 个示例不要求立即改写；WP3/CLI 可在入口自动验证、迁移后再路由。
- 当前 `runtime.selector.select_runtime`、`runtime.planner.build_offline_plan` 和旧 CLI 未修改；WP3 应以 wrapper 委托新 API，避免破坏旧调用。
- Canonical backend 使用下划线名称；迁移器已映射旧连字符名称。WP3 BackendRegistry 应消费 canonical 名称并在兼容输出层映射旧名称。

## Safety Invariants

- `production_allowed=false`
- `production_d1_allowed=false`
- `real_cad_access_allowed=false`
- `source_write_forbidden=true`
- `sandbox_required=true`
- `fail_closed=true`
- `dry_run=true`
- `simulate_only=true`
- `manual_save_required=true`
- `visual_review_required=true`
- `engineering_review_required=true`
- approval 不继承、不生成、不验证为有效授权
- L3/L4 不可由配置授予
- backend capability/availability 不可由 Manifest 提升
- 路径解析不访问文件系统，CAD identity 仅保持声明状态

## Tests Run

未运行 pytest 或外部集成。执行两组 PowerShell here-string → Python 内存自检，均设置 `PYTHONDONTWRITEBYTECODE=1`：

1. JSON/AST/API 自检：9 个 Owned JSON 解析、11 个 Owned Python 模块 AST、1.0→1.1.0 迁移及双 Schema 验证、canonical hash 重复性、3 类安全降级阻断、纯词法路径、traversal 与 source/output collision。
2. 边界矩阵自检：3 个 Schema `Draft202012Validator.check_schema`；5 个旧 example 全部验证→迁移→canonical Schema 验证；too old/new、未知字段、approval 继承、backend capability override、限制性数组、UNC/外部路径阻断。

## Test Result

PASS：

- JSON parse：9/9
- Python AST/import：11/11
- Schema metaschema：3/3
- 旧 example migration：5/5
- canonical determinism：PASS
- security downgrade/privilege/backend/approval blocks：PASS
- lexical path/traversal/UNC/external/collision：PASS
- CAD/DWG/DXF 文件创建、打开、读取、解析、扫描或哈希：0
- AutoCAD、天正、COM、Real backend：0

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
* Ran full pytest: NO
* Modified tests or safety guard: NO
* Modified installation or original GitHub Skill: NO

## Risks Found

- WP3 必须在调用 runtime selector/backend/workflow 前先执行 `load → validate old → migrate → validate canonical → resolve defaults → resolve paths`。
- 词法解析不能证明磁盘上的 symlink/junction 身份；真实运行前仍必须由独立安全后端观察并回传边界结果。本阶段不得据此声明 runtime identity verified。
- Allowlist 从系统空 trust root 开始时始终为空，这是 fail-closed 行为；未来 workflow 若需操作，必须由权威 registry 定义基础 allowlist，而不是由 Manifest 自行扩大。
- Canonical Schema 强制视觉/工程复核为 true；若未来确有安全的离线例外，需要单独版本和安全审计，不得由 override 放宽。

## Remaining Work

- WP3 实现 Runtime/Product/Backend/Workflow 路由、ExecutionPlanBuilder、simulation 和 legacy wrappers。
- CLI 在 WP3 接口冻结后另派；当前未修改。
- test_agent 为本 API 增加正式 `tests/config_driven`、Skill/CLI/安全回归测试。
- docs_agent 在实现冻结后回填版本、合并、路径和 CLI 文档。

## Recommendation

WP1 可交付 WP3。WP3 应直接使用上述公共 API，并维持 canonical 1.1.0、结构化错误、零 CAD 文件访问和所有安全不变量；不得复制一套相互冲突的配置加载/合并/路径实现。

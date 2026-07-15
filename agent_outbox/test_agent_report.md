# Agent Report

## Agent Name

test_agent

## Assigned Task

`CAD-CONFIG-S2-TEST-PLAN-001`

## Files Read

- `agent_inbox/test_agent.md`
- `pytest.ini`
- `tests/conftest.py`
- `tests/safety/pytest_plugin.py`
- `tests/safety/real_cad_access_guard.py`
- `tests/safety/test_real_cad_access_guard.py`
- `tests/skill/test_skill_cli.py`
- `tests/skill/test_skill_package.py`
- `tests/nextgen/test_nextgen_handoff.py`
- `skills/autocad-tianzheng-automation/tests/conftest.py`
- `skills/autocad-tianzheng-automation/tests/test_skill.py`
- `skills/autocad-tianzheng-automation/scripts/skill_cli.py`
- `skills/autocad-tianzheng-automation/schemas/project_manifest.schema.json`
- `artifacts/cad_safe_test_baseline/20260714T220937+0800/test_command_manifest.json`
- `artifacts/cad_safe_test_baseline/20260714T220937+0800/pytest_marker_policy.json`
- `artifacts/cad_safe_test_baseline/20260714T220937+0800/file_access_guard_policy.json`
- `artifacts/cad_safe_test_baseline/20260714T220937+0800/synthetic_fixture_manifest.json`
- `artifacts/cad_safe_test_baseline/20260714T220937+0800/test_inventory.json`
- `artifacts/cad_safe_test_baseline/20260714T220937+0800/default_test_file_access_summary.json`
- CAD-CONFIG-S2 用户需求附件 `pasted-text.txt`

仅读取文本源码、JSON、Markdown、Schema 和路径名；未读取、解析、扫描或哈希任何 DWG/DXF。

## Files Modified

- `agent_outbox/test_agent_report.md`

未修改测试、守卫、业务代码、Schema、Skill 或配置。

## Work Completed

### 1. 现有安全测试基线

- 当前冻结基线目录：`artifacts/cad_safe_test_baseline/20260714T220937+0800`。
- 当前基线 SHA256：`87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`。
- 历史默认安全回归：1603 collected / 1602 passed / 0 failed / 1 skipped。
- 历史 Skill 定向测试：64/64 passed。
- 历史 NextGen 定向测试：47/47 passed。
- 历史真实 DWG 成功读取/写入、CAD 进程、COM、天正和 Real backend 执行均为 0。

### 2. 守卫启用方式

- 根 `pytest.ini` 通过 `addopts = -p tests.safety.pytest_plugin` 强制加载项目级守卫。
- 守卫在 `pytest_configure` 阶段安装，覆盖测试收集和 import-time 访问。
- 每条测试命令必须从项目根执行，并显式携带 `-c pytest.ini --strict-markers`。
- 每个 pytest 进程启动前必须设置独立 `CAD_SAFE_TEST_RUN_DIR`；该环境变量必须在 Python 启动前设置。
- 每个 pytest 进程启动前必须清除 `CAD_TEST_ALLOW_EXTERNAL_READONLY`，禁止启用真实外部只读门。
- 不得传入 `-p no:tests.safety.pytest_plugin`，不得另建会遮蔽根 `pytest.ini` 的配置文件。

统一 marker 表达式：

```text
not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only
```

### 3. 现有可复用测试路径

- `skills/autocad-tianzheng-automation/tests`：统一 Skill、Manifest、runtime、adapter、approval、capability 和离线计划兼容性。
- `tests/nextgen`：NextGen Mock、控制面、checkpoint/journal、幂等、保护区域及真实能力隔离。
- `tests/skill/test_skill_cli.py`：现有旧 CLI 兼容性及不连接 AutoCAD 约束。
- `tests/skill/test_skill_package.py`：既有 Skill 包结构和安全默认值。
- `tests/safety/test_real_cad_access_guard.py`：守卫自身有效性；不应混入新增配置单元测试的违规统计。

当前 `tests/config_driven` 不存在，必须作为 S2 新测试域创建；本规划阶段不创建该目录。

### 4. 建议新增测试文件边界

配置核心测试放入 `tests/config_driven/`：

- `conftest.py`：仅定义虚构 Manifest、固定时钟和 deterministic serializer fixture；不得覆盖或放宽项目级守卫。
- `test_manifest_schema.py`：需求 1～10，覆盖最小/完整 Manifest、必填项、未知字段、UTF-8、canonical JSON 和 round-trip。
- `test_manifest_versioning.py`：需求 4～7，覆盖兼容矩阵、旧版本迁移、过新/过旧版本和迁移失败。
- `test_defaults_and_merge.py`：需求 11～24，覆盖六层优先级、来源追踪、限制性安全合并、数组策略、backend 和 approval 不可继承。
- `test_path_resolution.py`：需求 25～34，仅验证字符串、规范化和边界；不得调用真实 CAD 文件的 `exists/stat/open/read/hash`。
- `test_runtime_product_routing.py`：需求 35～42，覆盖五种 runtime、产品冲突、prohibited product 和 fail-closed。
- `test_backend_selection.py`：需求 43～52，覆盖 offline/nextgen_mock 可用、contract/real backend 禁用及 Mock 不冒充 Real。
- `test_workflow_registry.py`：需求 53～61，覆盖 11 类 workflow、能力冲突和写入 placeholder 不可执行。
- `test_execution_plan.py`：需求 62～73，覆盖 deterministic plan、canonical hash、时间/键序/斜杠归一化、blocked reason 和 hash mismatch。
- `test_templates.py`：验证至少 10 个模板全部为虚构相对路径、安全默认值且可生成离线或 blocked plan。
- `test_security_boundaries.py`：需求 91～100，覆盖无 CAD/COM/子进程、无真实 CAD 读取/哈希、Manifest 不授予 L4、生产默认 false、Real backend 不提升。

CLI 测试单独放入 `tests/config_cli/`，避免阶段 A 运行整个 `tests/config_driven` 时与阶段 D 重复：

- `test_manifest_cli.py`：validate、normalize、explain、migrate、diff。
- `test_routing_cli.py`：config/runtime/product/backend/workflow select。
- `test_plan_cli.py`：plan build/verify/hash、offline/nextgen_mock simulate。
- `test_template_cli.py`：templates list/create。
- `test_cli_contract.py`：需求 89～90，覆盖 `--json`、统一 error model 和 exit code 0/2/3/4/5/6/7/8/9。
- `test_legacy_cli_compatibility.py`：只验证现有兼容命令未被删除，不复制旧测试实现。

### 5. Synthetic fixture 策略

优先复用：

- pytest 内置 `tmp_path`、`monkeypatch`；
- 项目插件提供的 `cad_access_guard`；
- 项目插件提供的 `synthetic_cad_factory`，仅在必须验证 `.dwg/.dxf` 扩展名的运行时临时文件行为时使用；
- `tests/fixtures/synthetic_cad_identity/fake_document_identity.json` 和 `fake_checkpoint.json` 中可复用的虚构身份/checkpoint 数据。

新增 fixture 限制：

- 静态 fixture 只允许 `.json`、`.bin`、`.txt`，不得新增静态 `.dwg/.dxf`。
- Manifest 内的 CAD 路径默认只作为虚构字符串，不创建文件、不检查存在性、不跟随打开。
- 若必须创建 CAD 扩展名文件，只能通过 `synthetic_cad_factory` 在当前测试 `tmp_path` 内动态创建，显式登记 `synthetic_test_file=true`，并由 owner-scoped teardown 自动撤销。
- 不得从真实 CAD 文件截取字节，不得把真实文件改扩展名。
- 现有 `fake_manifest.json` 和 Skill `synthetic_manifest.json` 不是 S2 canonical Manifest；只可用于迁移/拒绝测试，不可直接声明为新 Schema 的正例。

### 6. 分阶段安全测试命令计划

以下命令仅为实施完成后的计划，本任务未执行。每阶段先清除外部放行变量，并使用独立访问日志目录。

#### Phase 0 — 冻结基线预检

```powershell
python -m scripts.verify_safe_test_baseline --baseline "artifacts\cad_safe_test_baseline\20260714T220937+0800" --project-root "."
```

必须 exit 0，且 source manifest、checksum、closure conditions 全为 true；否则停止并返回 `CAD_CONFIG_S2_BLOCKED_BY_BASELINE_DRIFT`。

#### Phase A — 新增配置单元测试

```powershell
Remove-Item Env:CAD_TEST_ALLOW_EXTERNAL_READONLY -ErrorAction SilentlyContinue
$env:CAD_SAFE_TEST_RUN_DIR="artifacts\cad_config_driven_s2\<run_id>\test_logs\phase_a_config_unit"
python -m pytest -q -c pytest.ini --strict-markers tests/config_driven -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
```

#### Phase B — 统一 Skill 定向测试

```powershell
Remove-Item Env:CAD_TEST_ALLOW_EXTERNAL_READONLY -ErrorAction SilentlyContinue
$env:CAD_SAFE_TEST_RUN_DIR="artifacts\cad_config_driven_s2\<run_id>\test_logs\phase_b_skill"
python -m pytest -q -c pytest.ini --strict-markers skills/autocad-tianzheng-automation/tests -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
```

#### Phase C — NextGen 定向测试

```powershell
Remove-Item Env:CAD_TEST_ALLOW_EXTERNAL_READONLY -ErrorAction SilentlyContinue
$env:CAD_SAFE_TEST_RUN_DIR="artifacts\cad_config_driven_s2\<run_id>\test_logs\phase_c_nextgen"
python -m pytest -q -c pytest.ini --strict-markers tests/nextgen -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
```

#### Phase D — 新旧 CLI 定向测试

```powershell
Remove-Item Env:CAD_TEST_ALLOW_EXTERNAL_READONLY -ErrorAction SilentlyContinue
$env:CAD_SAFE_TEST_RUN_DIR="artifacts\cad_config_driven_s2\<run_id>\test_logs\phase_d_cli"
python -m pytest -q -c pytest.ini --strict-markers tests/config_cli tests/skill/test_skill_cli.py -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
```

#### Phase E — 默认安全回归

```powershell
Remove-Item Env:CAD_TEST_ALLOW_EXTERNAL_READONLY -ErrorAction SilentlyContinue
$env:CAD_SAFE_TEST_RUN_DIR="artifacts\cad_config_driven_s2\<run_id>\test_logs\phase_e_default_safe_regression"
python -m pytest -q -c pytest.ini --strict-markers -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
```

执行规则：Phase 0/A/B/C/D/E 严格串行；任一阶段失败或出现 unexpected guard block，停止后续阶段，不得用 marker 隐藏普通失败。

### 7. 计数和证据采集方式

每阶段采集：

- pytest exit code；
- collected / passed / failed / skipped / warning / deselected；
- 当前阶段 `CAD_SAFE_TEST_RUN_DIR/default_test_file_access_log.jsonl`；
- 当前阶段 `CAD_SAFE_TEST_RUN_DIR/default_test_file_access_summary.json`；
- error code、失败 test id 和首个安全阻断栈；
- 使用的 marker expression、工作目录、Python/pytest 版本。

阶段结果分别写入：

- `config_unit_test_results.json`
- `skill_test_results.json`
- `nextgen_test_results.json`
- `cli_test_results.json`
- `safe_default_regression_results.json`

默认回归的最终访问摘要复制到阶段根 `default_test_file_access_summary.json`。不得把守卫专项测试的预期阻断混入 S2 违规计数；新增配置、Skill、NextGen 和 CLI 阶段的 unexpected 阻断必须为 0。

### 8. 真实 CAD 零访问验收点

每阶段以及最终汇总必须满足：

- `real_dwg_successful_reads = 0`
- `real_dwg_successful_writes = 0`
- `cad_processes_started = 0`
- `autocad_com_connections = 0`
- `tianzheng_connections = 0`
- `real_backend_executions = 0`
- `external_processes_started = 0`，除非是经 Manager 单独批准且不含 CAD 路径的安装态 CLI 子进程；此类事件必须单独解释，不得计作 CAD 执行。
- `unexpected_default_blocks = 0`
- 新增 S2 测试不得设置 `CAD_TEST_ALLOW_EXTERNAL_READONLY=1`。

任一真实 CAD 成功访问、CAD 进程/COM/天正连接或 Real backend 执行，立即停止并输出 `CAD_CONFIG_S2_REAL_CAD_ACCESS_VIOLATION`。

## Tests Run

未运行任何测试；未运行 pytest、collect-only、CLI、subprocess 或 verifier。本任务仅做只读规划。

## Test Result

`TEST_PLAN_READY_NOT_EXECUTED`

## Safety Check

* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO
* Read, parsed, scanned or hashed DWG/DXF: NO
* Ran pytest or test collection: NO
* Ran external integration tests: NO
* Modified file access guard: NO

## Risks Found

- `tests/config_driven` 和 `tests/config_cli` 当前尚不存在；测试计数只能在实现完成后采集，规划阶段不得预报新增 collected 数。
- 现有 `tests/skill/test_skill_cli.py` 包含 `.dwg` 路径字符串，但只构造参数/Manifest，不打开文件；新实现不得把这些字符串自动解析为文件访问。
- 新 `ManifestPathResolver` 若使用 `exists()`、`stat()`、`resolve(strict=True)`、`read_bytes()` 或文件哈希验证 CAD 身份，将违反本阶段“只做字符串、结构和边界检查”的要求并触发守卫。
- `tests/config_driven/conftest.py` 若定义同名 fixture 覆盖 `cad_access_guard` 或 `synthetic_cad_factory`，可能削弱 owner-scoped 登记；禁止重定义这两个 fixture。
- 当前旧 Manifest Schema 为扁平 `schema_version = 1.0`；S2 canonical 顶层模型更复杂，迁移测试必须同时验证兼容性和不静默丢字段，不能只验证新 Schema 正例。
- CLI 存在统一 Skill 离线 CLI 与项目旧 `mcp.skill_cli` 两套表面，阶段 D 必须同时验证新命令和旧兼容命令，防止误删已发布入口。

## Remaining Work

- 等待配置系统实现后创建上述测试文件。
- 由 Safety Audit 审核新增测试边界、fixture 和命令计划。
- Manager 明确放行后才可按 Phase 0/A/B/C/D/E 串行执行。
- 执行后生成各阶段结果 JSON、访问日志和最终零访问摘要。

## Recommendation

`TEST_PLAN_READY；WAITING_FOR_IMPLEMENTATION_AND_SECURITY_APPROVAL`

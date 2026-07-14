# Agent Report
## Agent Name
safety_audit_agent

## Assigned Task
CAD-SAFETY-S2.1-A（run_id：`20260714T193554+0800_s2_1`）

## Files Read
- 指定范围 `tests`、`mcp_nextgen`、`mcp`、`scripts`、`skills/autocad-tianzheng-automation` 内的 636 个文本源码、测试和配置文件。
- `artifacts/mcp_upgrade_handoff/integration_test_results.json`
- `artifacts/mcp_upgrade_handoff/security_findings.json`
- `artifacts/mcp_upgrade_handoff/security_findings.md`
- `artifacts/mcp_upgrade_handoff/deferred_items.json`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/cad_skill_packaging_final_report.json`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/cad_skill_packaging_final_report.md`
- 未打开、读取、扫描或哈希任何 DWG/DXF；未跟随 JSON/Markdown 中的 CAD 路径。

## Files Modified
- `agent_inbox/safety_audit_agent.md`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/real_dwg_static_access_inventory.json`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/real_dwg_static_access_inventory.md`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/pytest_marker_inventory.json`
- `agent_outbox/safety_audit_agent_report.md`

## Work Completed
- 仅对允许的文本扩展名做静态扫描，并排除 `.git`、缓存、`output`、`图纸` 和 artifacts 二进制内容。
- 扫描 636 个文本文件；326 个文件、3401 行命中用户指定关键词；134 个文件、386 行含 `.dwg/.dxf` 字面量。
- 对有安全意义的命中按八类归档；生产代码与默认测试可达风险分开记录。
- 识别 39 个保留的生产/外部集成 CAD 访问表面，未删除、未修改业务逻辑。
- 确认 1 个未标记且默认测试可达的真实 CAD 间接访问点：
  `tests/acceptance/test_stage6_p1_accelerated_r4_preflight.py::test_preflight_only_never_imports_com`
  → `scripts.run_stage6_p1_accelerated_r4._preflight`
  → 固定真实 DWG 路径 `open(path, "rb")` / SHA-256。
- 确认当前 `pytest.ini` 未注册 `real_dwg`、`external_integration`、`autocad_required`、`tianzheng_required`、`com_required`、`production_only`，六类 marker 的赋值数均为 0。
- 定位五个 Windows GBK 解码 UTF-8 源码失败：均位于 `tests/acceptance/test_stage6_p1_emergency_fast_full_rerun.py` 的五个 `Path.read_text()` 调用，应显式 `encoding="utf-8"`。
- 定位 R4 缺失文件问题：它不是安全 skip；既有证据显示缺失前已成功读取三个真实 DWG。应以 synthetic/monkeypatch 重构或显式外部隔离，禁止补造/读取真实 R4 文件。
- 定位同一 emergency 测试文件中七个固定 artifacts JSON 依赖和 `tests/mcp_service/test_h0_pipeline_status.py` 的固定状态 JSON 依赖；二者当前不跟随 CAD，但应改为 synthetic fixture 以冻结 hermetic 基线。

## Tests Run
- 未运行 pytest（任务明确禁止）。
- 仅使用 PowerShell `ConvertFrom-Json` 验证两个 JSON 输出可解析。

## Test Result
- `real_dwg_static_access_inventory.json`：JSON 解析 PASS。
- `pytest_marker_inventory.json`：JSON 解析 PASS。
- 运行时守卫、marker、子进程防护及默认回归尚待其他 S2.1 子任务实施和验证。

## Safety Check
* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO
* Read or hashed DWG/DXF bytes: NO
* Ran pytest: NO
* Ran P4.1: NO
* Used COM: NO

## Risks Found
1. `CAD-STATIC-001` 是当前 SEC-FINAL-019 的确认调用链，且未标记；在修复和守卫前运行默认全量 pytest 会再次触发真实 CAD 读取风险。
2. 仅 marker 排除不足以关闭问题：必须同时启用 builtins/pathlib/os/shutil/hash/subprocess 守卫并记录访问日志。
3. `tmp_path` CAD 文件目前主要是合成数据，但关闭基线应要求显式 synthetic 注册，不能只凭目录自动放行。
4. 固定 artifacts JSON 测试不直接读取 CAD，但非 hermetic，可能因历史产物漂移导致失败或未来路径跟随风险。
5. 当前静态阶段不能关闭 SEC-FINAL-019。

## Remaining Work
- 注册六类 pytest marker 并实施默认排除表达式。
- 将 R4 preflight 测试重构为 synthetic/monkeypatch，或将真实行为显式隔离。
- 修复五个 UTF-8 读取和七个固定 artifacts JSON fixture。
- 实施并自测文件访问、hash helper 与 subprocess 守卫。
- 运行定向测试和默认安全回归，生成零成功读写日志及独立复核证据。

## Recommendation
- 保留生产 CAD 代码，不修改 P2/P3/P4.1 业务逻辑。
- 默认安全测试用 synthetic fixture；真实环境测试必须显式 marker 且不在本阶段运行。
- 在运行任何默认回归前，先确保 `CAD-STATIC-001` 不再可达真实路径，并让守卫 fail-closed。
- 静态阶段状态保持：`SEC_FINAL_019=OPEN`。

---

# GUARD REVIEW — CAD-SAFETY-S2.1-C

## Review Scope

本复审仅静态读取以下文本文件，未运行 pytest，未打开、读取或哈希任何 DWG/DXF：

- `tests/conftest.py`
- `tests/safety/real_cad_access_guard.py`
- `tests/safety/test_real_cad_access_guard.py`
- `tests/acceptance/test_stage6_p1_accelerated_r4_preflight.py`
- `pytest.ini`
- P4.1 入口及业务文件的文件元数据（仅确认本阶段未改）

## Decision

`BLOCK_C`

守卫已具备良好骨架，但仍存在可绕过路径和证据失真，当前不能作为 SEC-FINAL-019 关闭依据。

## Passed Review Items

1. **项目默认测试启用范围**：根 `pytest.ini` 的 `testpaths=tests`，`tests/conftest.py` 在 `pytest_configure` 安装守卫，覆盖默认 `tests/**` 的收集和运行阶段；`pytest_unconfigure` 恢复 monkeypatch，不向生产运行时注入依赖。
2. **基础文件 API 覆盖**：已拦截 `builtins.open`、`Path.open/read_bytes/read_text`、`os.open`、`shutil.copy/copy2/copyfile` 和 `subprocess.Popen`。
3. **真实 CAD 写阻断基本逻辑**：未登记 CAD 文件写入被阻断；外部只读环境变量存在时，写模式仍进入 `real_cad_boundary`。
4. **Synthetic 显式登记**：要求 `synthetic_test_file=true`、CAD 扩展名、路径位于已登记 pytest `tmp_path`，未登记临时 `.dwg` 被阻断。
5. **Marker 注册**：`pytest.ini` 已注册 `real_dwg`、`external_integration`、`autocad_required`、`tianzheng_required`、`com_required`、`production_only` 和 `guard_self_test`，无 unknown-marker 设计问题。
6. **日志分类骨架**：预期守卫自测阻断与默认测试意外阻断已分开为 `expected_guard_self_test_block` / `unexpected_default_test_block`，堆栈与 marker 会写入事件。
7. **生产定义隔离**：守卫模块只由测试 `conftest` 导入；安装和卸载局限于 pytest 会话，没有修改生产模块定义。
8. **R4 测试最小改造**：原危险用例现使用 `tmp_path` 中四个随机 synthetic DWG，先显式登记，再 monkeypatch R4 的四个 CAD 常量、计划路径和期望哈希；生产 `scripts/run_stage6_p1_accelerated_r4.py` 未改。
9. **P4.1 边界**：`mcp/orchestration/stage6_p4_1_whole_drawing_completion.py` 及 `run/execute/finalize/recover/resume_stage6_p4_1.py` 的最后修改时间均为 2026-07-13，早于本阶段；未发现 CAD-SAFETY-S2.1 修改 P4.1 业务代码的证据。

## Blocking Findings

### C-BLOCK-001 — 路径规范化未解析符号链接或 junction

- 位置：`tests/safety/real_cad_access_guard.py::_norm()`。
- 当前实现：`expandvars/expanduser + normpath + abspath + normcase`，没有 `realpath` 或 `Path.resolve(strict=False)`。
- 风险：`tmp_path` 下的已登记 `synthetic.dwg` 可以是指向外部真实 DWG 的 symlink/junction；字符串路径仍位于 synthetic root 且精确命中 `_synthetic_files`，守卫会放行。
- 测试缺口：现有“相对路径、大小写、斜杠、UNC”测试未覆盖 symlink/junction。
- 必须修复：登记和访问时同时保存/比较 lexical path 与 resolved path；resolved target 必须仍位于同一 synthetic root，拒绝 symlink、junction、reparse point 或任何越界解析。

### C-BLOCK-002 — External 只读门过宽

- 位置：`evaluate_path()` 第 145–151 行附近。
- 当前条件：`_current_markers.intersection(EXTERNAL_MARKERS)` 任一命中，加 `CAD_TEST_ALLOW_EXTERNAL_READONLY=1` 即放行真实 CAD 只读。
- 风险：仅有 `production_only`、`autocad_required`、`com_required` 等任一 marker 就能与环境变量组合放行，未要求真实文件测试明确声明 `real_dwg` / `external_integration`。
- 必须修复：至少要求 `external_integration` 与 `real_dwg` 两个 marker 同时存在，再加只读环境变量；写入始终无条件拒绝。自测应分别覆盖缺少任一 marker、缺少 env、写模式和三门齐备只读。

### C-BLOCK-003 — 子进程可通过已知扫描/包装命令绕过

- 位置：`check_command()`。
- 当前检查只覆盖：首个 executable 恰为 CAD 进程名，或任一参数字符串包含 `.dwg/.dxf`。
- 可绕过示例：
  - `python scripts/run_stage6_p1_accelerated_r4.py --preflight-only`
  - `powershell -File scripts/run_stage6_p1_accelerated_r4.ps1`
  - `cmd /c acad.exe /nologo`
  - `powershell -Command "Start-Process acad.exe"`
- 风险：这些命令未携带 CAD 路径字面量，但脚本内部固定常量可读取真实 DWG，包装 shell 也可启动 CAD。
- 必须修复：维护 fail-closed 的已知 CAD/preflight/scanner 脚本表；递归审计 `python`、PowerShell、`cmd /c` 的脚本与命令字符串；检查任意 token 中的 CAD 进程名及 `Start-Process`/调用运算符目标。新增对应守卫自测。

### C-BLOCK-004 — 访问摘要把关键关闭指标硬编码为 0

- 位置：`build_summary()` 第 342–351 行附近。
- 当前硬编码：`real_dwg_successful_reads=0`、`real_dwg_successful_writes=0`、`cad_processes_started=0`、`autocad_com_connections=0`、`tianzheng_connections=0`。
- 风险：当 external readonly 被允许时，事件记录为 allowed，但摘要仍声称真实 DWG 成功读取为 0；若 C-BLOCK-003 绕过 CAD 进程，`cad_processes_started` 仍为 0。COM/天正连接没有探针却输出确定的 0，属于不可证明的关闭证据。
- 必须修复：从事件真实计算 read/write/process 指标；`explicit_external_readonly` 的 allowed 事件必须计入成功读取。COM/天正需要明确拦截/探针，否则输出 `not_observed`/`not_instrumented`，不得硬编码为 0。默认关闭运行中任何 external allowed read 必须导致关闭条件失败。

### C-BLOCK-005 — 项目外 Skill 测试路径并非自动受根守卫覆盖

- 范围：`tests/conftest.py` 只对其目录树生效。
- 风险：若直接运行 `pytest skills/autocad-tianzheng-automation/tests`，该目录不是 `tests/conftest.py` 的子目录，守卫不会自动加载；默认 `pytest -q` 因 `testpaths=tests` 不受影响，但“Skill 定向测试”若使用 Skill 内测试路径可能失去守卫。
- 必须修复：明确 Skill 定向命令只运行根 `tests/skill`，或把守卫注册为根级 pytest plugin/在 Skill 测试树增加只导入同一守卫的 conftest。基线命令清单必须证明所有纳入关闭结论的测试路径都加载守卫。

## Non-blocking Observations

1. `Path.write_bytes/write_text` 当前依赖其内部调用 `Path.open` 被动态 monkeypatch；建议显式包裹两者以减少 Python 实现变化风险。
2. `_synthetic_roots` 和 `_synthetic_files` 跨测试会话内持续累积；建议 teardown 时按测试清除登记，避免测试间授权残留。
3. `external_processes_started` 当前按 allowed `Popen` 检查事件计数，表示“允许尝试并随后调用原 Popen”，名称基本合理；若 Popen 自身失败，应区分 attempted 与 successfully_started。

## Required Retest Before APPROVE_C

完成上述阻断修复后，应由 test_agent 运行并提供：

1. 新增 symlink/junction 越界测试；
2. external readonly 双 marker + env 三门测试；
3. 已知 R4/preflight 脚本、PowerShell/`cmd /c` 包装 CAD 进程阻断测试；
4. allowed external read 能被摘要准确计数的测试；
5. Skill 定向测试确实加载守卫的证明；
6. 守卫专项测试与默认安全回归均通过，意外 blocked attempt 为 0。

## Final Guard Review Status

`BLOCK_C`

---

# GUARD REVIEW 2 — BLOCK_C 修复复审

## Review Method

仅静态读取守卫、插件、专项测试、R4 测试、UTF-8/non-hermetic 修复和相关业务文件元数据；未运行 pytest，未读取、打开或哈希 DWG/DXF。

## Decision

`BLOCK_C`

原 5 个阻断项中 4 项已实质关闭，`C-BLOCK-002` 的双 marker 语义仍未实现，不能批准。

## Original Blocking Item Closure Matrix

| 原阻断项 | 复审状态 | 证据 |
|---|---|---|
| C-BLOCK-001 symlink/junction 解析 | CLOSED | `_norm()` 已使用 `Path(raw).resolve(strict=False)`；登记时按解析后路径验证仍位于 synthetic root。专项测试创建指向 `tmp_path` 外目标的 symlink，只有 `symlink_to()` 抛出 OS 权限/能力 `OSError` 时才 skip，否则必须因越界抛 `ValueError`。Windows junction/reparse point同样由 resolved-path 边界实施运行时约束。 |
| C-BLOCK-002 external 只读门 | **OPEN** | 见下方唯一阻断项。 |
| C-BLOCK-003 subprocess 绕过 | CLOSED | 已加入 CAD 进程 token、脚本解释器、危险 preflight/scanner/hash 脚本片段及包装 shell 检查；专项覆盖 `cmd /c acad.exe`、PowerShell scanner、R4 preflight 和 file_sha256。 |
| C-BLOCK-004 摘要硬编码 | CLOSED | 文件访问在底层 API 成功返回后追加 `.completed` 事件；真实只读/写入、进程 started、COM/天正事件均从事件计算。另拦截新的 `win32com/pythoncom/comtypes` 导入并报告 newly imported modules。 |
| C-BLOCK-005 Skill 显式测试覆盖 | CLOSED | `pytest.ini` 使用 `addopts = -p tests.safety.pytest_plugin` 注册项目级插件；该插件不依赖 `tests/conftest.py` 的目录继承，可覆盖从项目配置启动的显式 Skill 测试路径。专项静态断言验证插件配置和文件存在。 |

## Remaining Blocking Finding

### C2-BLOCK-001 — `intersection()` 仍只要求任一 marker

位置：`tests/safety/real_cad_access_guard.py::evaluate_path()`。

当前条件为：

```python
self._current_markers.intersection(EXTERNAL_READONLY_MARKERS)
```

其中 `EXTERNAL_READONLY_MARKERS = {"real_dwg", "external_integration"}`。`set.intersection()` 返回非空即为真，因此只标记 `external_integration` 或只标记 `real_dwg` 都可配合环境变量放行真实 CAD 只读，并非要求两个 marker 同时存在。

专项测试 `test_external_marker_readonly_requires_explicit_environment` 也只添加 `external_integration` 就断言放行，固化了错误门控语义；`test_other_external_markers_do_not_release_readonly` 仅证明 `autocad_required` 不放行，不能证明双 marker。

必须最小修复为等价的双 marker 子集判断，例如：

```python
EXTERNAL_READONLY_MARKERS.issubset(self._current_markers)
```

并新增/调整测试覆盖：

1. 只有 `external_integration` + env：拒绝；
2. 只有 `real_dwg` + env：拒绝；
3. 两个 marker、无 env：拒绝；
4. 两个 marker + env + 只读：允许；
5. 两个 marker + env + 写入：始终拒绝。

## Regression Repair Review

### 五个 UTF-8 失败

`tests/acceptance/test_stage6_p1_emergency_fast_full_rerun.py` 的五个源码读取均已显式 `encoding="utf-8"`。原断言仍保留：AST 可解析、Save/Close/copy2、unexpected 交付语义、task-results 字段和六个报告文件名，未删除或放宽核心断言。

### 七个 non-hermetic 冻结计划测试

已改为在 `tmp_path` 写入 synthetic JSON；仍严格断言 4343 task、repair count、source handle 唯一、task id 唯一且非空、至少七个区域对、protected bbox、ordinary+TDb 总数和全部 transform_id。未以 skip/marker 隐藏失败，测试目标未削弱。

### R4 间接访问修复

R4 preflight 测试仍实际调用生产 `_preflight()`，但四个 CAD 路径、计划路径和期望哈希均在调用前 monkeypatch 为显式登记的 `tmp_path` synthetic 文件；继续断言 preflight 通过、stats 存在且 COM 模块状态不变。`scripts/run_stage6_p1_accelerated_r4.py` 最后修改时间仍为 2026-07-12，未修改业务实现。

### P4.1 冻结边界

P4.1 orchestration 及 run/execute/finalize/recover/resume 文件最后修改时间均为 2026-07-13，早于本阶段；没有本阶段修改 P4.1 业务代码的证据。

## Final Review 2 Status

`BLOCK_C`

仅剩 external 双 marker 子集判断及对应测试需要最小修复；其余四项可保持关闭。

---

# GUARD REVIEW 3 — External 门最小复审

## Review Boundary

仅静态核对 `tests/safety/real_cad_access_guard.py` 的 external 只读条件及 `tests/safety/test_real_cad_access_guard.py` 的五类测试源码；未运行测试，未读取、打开或哈希任何 DWG/DXF。

## Findings

1. `EXTERNAL_READONLY_MARKERS = {"real_dwg", "external_integration"}`。
2. 放行条件已改为 `EXTERNAL_READONLY_MARKERS.issubset(self._current_markers)`，不再使用任一命中的 `intersection()`。
3. 同一条件还要求 `CAD_TEST_ALLOW_EXTERNAL_READONLY == "1"`。
4. 条件前置 `not write_requested`；真实 CAD 写入在双 marker 与环境变量齐备时仍返回 `real_cad_boundary`。
5. 五类测试源码均存在并保持明确断言：
   - 仅 `real_dwg` + env：拒绝；
   - 仅 `external_integration` + env：拒绝；
   - 双 marker、无 env：拒绝；
   - 双 marker + env + `rb`：仅只读放行；
   - 双 marker + env + `wb`：始终拒绝。

## Decision

`APPROVE_C`

此前唯一剩余的 external 双 marker 门阻断已按要求关闭。该批准仅表示守卫实现通过静态安全复审；运行时测试结果仍由 test_agent 的受守卫测试证据负责。

---

# STAGE D FAILURE DIAGNOSIS

## Failed Test

`tests/acceptance/test_stage6_p1_emergency_fast_full_rerun.py::test_emergency_delivery_accepts_unexpected`

## Diagnosis

结论：`FIX_TEST_SAFE`

该失败来自测试辅助逻辑的字符串切片误判，不需要修改业务脚本。

当前断言：

```python
assert "unexpected" not in src.split("HARD STOP")[0] if "HARD STOP" in src else True
```

它把脚本从文件开头到第一次 `HARD STOP` 文本之间的所有内容都当作“硬停止条件”。但该区间合法包含：

- 第 7 行模块说明：接受 `33 unexpected_new + 6 existing_modified` 作为已知可修复副作用；
- 第 303–304 行：计算 `unexpected_handles` 和合并 new handles；
- 第 326–327 行：生成 unexpected side-effect evidence；
- 第 334 行：打印 unexpected 数量。

这些位置的语义是记录、分类、输出证据和转人工修复，不是阻断。因此该断言无论业务安全语义是否正确，都因第 7 行文档字符串而失败。

真正的 `HARD STOP` 分支位于业务脚本约第 343–355 行，只针对：

1. `existing_deleted > 0`；
2. `protected_region_modified > 0`；
3. `protected_region_intersection > 0`；
4. `mapped_task_count != 4343`；
5. `wrong_region_writes > 0`。

未发现以 `unexpected_handles` / `unexpected_new` 为条件的 hard-stop 分支。脚本随后将 unexpected evidence 写入 `unexpected_new_objects.json`，最终状态为 `EMERGENCY_FAST_FULL_RERUN_COMPLETE`，并明确 `manual_repair_required=True`；这与测试文档所述“repairable, not blocking”一致。

## Precise Safe Recommendation

仅修复测试辅助判断，保持并可加强现有断言：

1. 使用 `ast.parse(src)`；
2. 遍历 `ast.If`；
3. 找出 body 中包含字符串 `HARD STOP` 的分支；
4. 对每个该分支的 `node.test` 使用 `ast.unparse()` 或 AST dump，断言条件不含 `unexpected`；
5. 断言至少发现一个 hard-stop 分支，避免空集合假通过；
6. 保留 `manual_repair_required` 和 `EMERGENCY_FAST_FULL_RERUN_COMPLETE` 断言；
7. 建议增加 `unexpected_new_objects.json` 以及结果字段 `"unexpected_new": len(unexpected_handles)` 的正向断言。

此修复：

- 不修改 `scripts/run_stage6_p1_emergency_fast_full_rerun.py`；
- 不删除原测试目标；
- 不放宽 deleted/protected/mapped/wrong-region 安全停止条件；
- 比全局字符串前缀检查更精确地验证“unexpected 不作为硬停止条件”。

## Final Recommendation

`FIX_TEST_SAFE`

---

# PRE-E STATIC RESCAN

## Command

`python -m scripts.audit_default_test_cad_access`

该命令只读取 UTF-8 文本白名单，硬排除 DWG/DXF 扩展名、不跟随 symlink、不跟随源码内容中的路径。本轮没有运行 pytest。

## Result

- 审计状态：`PASS`
- 文本文件：645
- 关键词命中：3560
- 未标记默认真实 DWG/DXF 访问链：0
- DWG/DXF 打开、读取或哈希：0
- AutoCAD/天正/COM：未连接

审计器的逐行启发式统计包含 `REAL_DWG_DIRECT_ACCESS=2` 和 `REAL_DWG_INDIRECT_ACCESS=12`，但交叉复核确认它们是守卫自测虚构路径、synthetic fixture、R4 monkeypatch 调用或静态字符串，不是默认测试可达真实 CAD 链。

## Marker Review

`pytest.ini` 已完整注册：

- `real_dwg`
- `external_integration`
- `autocad_required`
- `tianzheng_required`
- `com_required`
- `production_only`
- `guard_self_test`

并通过 `addopts = -p tests.safety.pytest_plugin` 加载项目级守卫插件。默认排除表达式完整。

## Repair Review

1. R4 测试只使用显式登记的 `tmp_path` synthetic CAD，并在调用生产 `_preflight()` 前 monkeypatch 所有 CAD/计划路径和期望哈希；没有真实路径跟随。
2. 五个 UTF-8 测试显式 `encoding="utf-8"`，只读取 Python 源码。
3. 七个 non-hermetic 测试使用 `tmp_path` synthetic JSON，不再依赖固定 artifacts 计划。
4. 阶段 D 的 unexpected 测试辅助断言已按 AST 语义修复，不修改业务脚本、不删除安全断言。

## Decision

`APPROVE_E`

允许进入 E 阶段受守卫默认回归；不得将本静态批准单独视为 SEC-FINAL-019 已关闭。

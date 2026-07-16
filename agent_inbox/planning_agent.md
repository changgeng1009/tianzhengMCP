# Task for planning_agent
## Assigned by: Manager
## Phase: CAD-BASELINE-REFREEZE
## Task ID: CAD-BASELINE-REFREEZE-CANDIDATE-BUILD
## Task Description
基于本阶段安全审计和五阶段测试证据，生成新的候选安全基线并执行正式 verifier 候选预检。
## Input Files
- artifacts/cad_safe_test_baseline/20260714T193554+0800_s2_1
- artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800
- AGENTS.md
- scripts/build_safe_source_manifest.py
- scripts/verify_safe_test_baseline.py
## Constraints
- 旧基线只读，绝不修改。
- 不读取、解析、扫描或哈希任何 DWG/DXF。
- 不更新统一 Skill。
- 新基线先保持 CANDIDATE/PENDING，等待独立复核。
## Expected Output
- artifacts/cad_safe_test_baseline/20260714T220937+0800
- 本阶段输出目录中的 new_baseline_manifest.json
- 本阶段输出目录中的 new_baseline_reference.json
- 候选构建与预检报告
# Task for planning_agent
## Assigned by: Manager
## Phase: CAD-CONFIG-S2
## Task ID: CAD-CONFIG-S2-PLAN-001

## Task Description
在不修改实现的前提下，审计原 CAD-CONFIG-S2 需求与当前统一 Skill 结构，形成可执行的文件级分工、依赖顺序、验收矩阵和 source change 边界。必须使用权威基线 `CAD-SAFE-20260714T220937+0800` / `87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`，不得使用 Skill 中 freeze 前 provenance SHA。

## Constraints
- 当前仅规划和只读审计，不实施 S2，不编辑 Skill/源码/测试。
- 不读取、解析、扫描或哈希 DWG/DXF。
- 不连接 AutoCAD、天正或 COM，不启动外部集成。
- 将预存工作区变更排除在 S2 source change manifest 之外。

## Expected Output
- `D:\CodexWork\天正\agent_outbox\planning_agent_report.md`
- 报告包含模块分工、目标文件、依赖、测试顺序、报告文件映射和停止条件。

## Final Artifact Assembly

### Task ID: CAD-CONFIG-S2-ARTIFACTS-010

根据已完成实现、用户授权 Git state revision、A–E 最终测试证据和现有 inventories，补齐原 CAD-CONFIG-S2 指定的根 artifacts（不覆盖历史事实；旧阻断结论以修订字段/附录保留）。根目录为 `artifacts/cad_config_driven_s2/20260715T113724+0800_s2`。

必须生成或更新：`manifest_schema_change_report.json`、`manifest_version_matrix.json`、`manifest_migration_matrix.json`、`configuration_layer_matrix.json`、`default_registry.json`、`config_merge_policy.json`、`security_merge_test_results.json`、`path_resolution_policy.json`、`runtime_routing_matrix.json`、`product_adapter_matrix.json`、`backend_selection_matrix.json`、`workflow_registry.json`、`template_catalog.json`、`template_validation_results.json`、`execution_plan_schema.json`、`execution_plan_determinism_results.json`、`plan_hash_test_vectors.json`、`cli_command_matrix.json`、`cli_test_results.json`、`config_unit_test_results.json`、`skill_test_results.json`、`nextgen_test_results.json`、`safe_default_regression_results.json`、`default_test_file_access_summary.json`、`source_change_manifest.json`、`known_limitations.json`、`s2_final_report.md`、`s2_final_report.json`。

可读取源码、测试结果、JSON/Markdown、Git元数据；不得读取/哈希任何DWG/DXF或被删除CAD blob，不得执行Git写操作、pytest、安装同步或改Skill代码。source change manifest 须明确排除用户确认的199条删除、两个授权 commit 作为当前基线、以及协作 inbox/outbox/artifacts；记录本次继续执行后新增S2路径。最终报告按原任务34项结构，状态先标记 `PENDING_INSTALLATION_VERIFICATION`，待安装Agent完成再由Manager回填最终状态。

## Final Report Closeout

### Task ID: CAD-CONFIG-S2-FINALIZE-015

安装验收已 PASS。根据最新 postfix2 Phase D/E、最终安装证据和用户授权 Git state 修订，更新 `source_change_manifest.json`、`known_limitations.json`、`s2_final_report.md`、`s2_final_report.json`。34项终稿须标明：

- 分支/HEAD/两个提交/199删除均由用户确认；无后续 Git 操作；
- 199删除排除于本次S2继续变更且未读取其中CAD；
- D=32 passed，E=1731 passed/0 failed/1 skipped/1 warning；A=104、B=64、C=47；
- 当前安装同步131/131一致、create→validate→plan 安装态 PASS、安装目录拒绝 exit6；
- verifier source manifest 当前因获批S2源码漂移而FAIL，但checksum/closure PASS，10/10 drift授权且非本阶段阻断；
- 真实DWG读写、CAD/COM/天正/Real backend=0；
- final status=`CAD_CONFIG_DRIVEN_S2_COMPLETE`。

保持历史阻断/incident记录，不删除。不得Git/CAD/pytest/sync或改实现。

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
- `D:\ExampleWorkspace\天正\agent_outbox\planning_agent_report.md`
- 报告包含模块分工、目标文件、依赖、测试顺序、报告文件映射和停止条件。

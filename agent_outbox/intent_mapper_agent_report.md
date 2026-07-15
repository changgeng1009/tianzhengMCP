# Agent Report

## Agent Name

intent_mapper_agent

## Assigned Task

CAD-CONFIG-S2-WP3-PREP / WP3_IMPLEMENT — 配置驱动 Runtime、Workflow、Execution Plan 与离线模拟。

## Files Read

- `agent_inbox/intent_mapper_agent.md`
- `skills/autocad-tianzheng-automation/schemas/project_manifest.schema.json`
- `skills/autocad-tianzheng-automation/config/**`
- `skills/autocad-tianzheng-automation/adapters/registry.py`
- `skills/autocad-tianzheng-automation/adapters/generic_autocad/**`
- `skills/autocad-tianzheng-automation/adapters/tianzheng_water/**`
- `skills/autocad-tianzheng-automation/adapters/tianzheng_hvac/**`
- `skills/autocad-tianzheng-automation/capabilities/*.json`
- 本报告“Files Modified”所列实现和配置文件

## Files Modified

- `skills/autocad-tianzheng-automation/runtime/contracts.py`
- `skills/autocad-tianzheng-automation/runtime/selector.py`
- `skills/autocad-tianzheng-automation/runtime/planner.py`
- `skills/autocad-tianzheng-automation/runtime/routing.py`
- `skills/autocad-tianzheng-automation/runtime/backend_registry.py`
- `skills/autocad-tianzheng-automation/runtime/workflow_registry.py`
- `skills/autocad-tianzheng-automation/runtime/execution_plan.py`
- `skills/autocad-tianzheng-automation/runtime/simulation.py`
- `skills/autocad-tianzheng-automation/config/workflows/*.json`（11 项）
- `skills/autocad-tianzheng-automation/templates/*/project_manifest.json`（10 项）
- `skills/autocad-tianzheng-automation/templates/template_catalog.json`
- `skills/autocad-tianzheng-automation/templates/template_capability_matrix.json`
- `agent_outbox/intent_mapper_agent_report.md`

## Work Completed

- 实现可解释的 Runtime Router 与冲突检测，按显式 override、Manifest、显式上下文、唯一离线元数据证据的优先级选择；不读取文档内容。
- 保持旧 `select_runtime` 返回合同：`generic_autocad -> autocad`、`unknown -> offline`。
- 保持旧 `build_offline_plan` 对 1.0/1.0.0/无版本 Manifest 的返回结构；仅 1.1.0 Canonical Manifest 进入新 PlanBuilder。
- 复用 WP2 Product/Backend 静态注册表，不复制注册逻辑；不可用 backend 即 fail-closed，不使用 fallback 静默降级。
- 建立 11 项机器可读 Workflow 合同：
  - `generic_autocad_redraw_offline`
  - `generic_autocad_clone_plan`
  - `pdf_intermediate_dwg_plan`
  - `image_dimension_parametric_redraw_plan`
  - `tianzheng_water_scan_plan`
  - `tianzheng_water_completion_plan`
  - `tianzheng_hvac_scan_plan`
  - `tianzheng_hvac_write_placeholder`
  - `offline_document_comparison`
  - `offline_capability_audit`
  - `nextgen_mock_job_simulation`
- 建立 10 项 Canonical 1.1.0 Manifest 模板、模板目录和能力矩阵；均使用虚构相对路径，未包含姓名、学号或项目绝对路径。
- 实现确定性 Execution Plan：包含显式 runtime/product/backend/workflow、审批要求、文档声明、保护区域、阶段、验证/恢复要求、限制和阻断原因。
- Plan/Manifest hash 排除 `created_at`、`generated_at`、`notes`、随机值、run id、临时目录，并复用 canonical 层完成 JSON 键序与路径斜杠归一化。
- 写入、L3/L4 或 Real workflow 只生成 blocked plan；Water completion 与 HVAC write placeholder 均返回不可执行状态。
- NextGen Mock simulation 只返回内存 Mock 证据；显式声明 `real_execution=false`、CAD/COM/天正连接均为 false，且不启动子进程。
- 离线分析允许处理带产品声明的文档元数据，但不会把该声明解释为选择或连接相应 CAD 产品。

## Tests Run

1. JSON Schema + PlanBuilder 离线自检：
   - 11 个 Workflow 全部加载；
   - 10 个模板全部通过 `project_manifest.schema.json`；
   - 每个模板重复构建结果完全一致；
   - 每个计划通过 plan hash / plan id 复核；
   - 8 个离线或 Mock 模板可生成离线可执行计划；
   - 2 个写入模板按预期 blocked；
   - NextGen Mock 模拟通过。
2. 安全路由/哈希自检：
   - Owned Python 模块 AST 解析；
   - runtime/product 冲突；
   - auto_detect 多产品冲突；
   - Legacy backend 不可用且不静默 fallback；
   - 非语义字段和路径斜杠变化不改变 hash；
   - 语义变更改变 hash；
   - 篡改计划被 `PLAN_HASH_MISMATCH` 拦截。
3. 旧兼容入口自检：
   - plain/water/HVAC/offline 4 个旧示例选择结果兼容；
   - 旧 planner 保留 `execution_allowed=false` 与 `PLAN_READY`。
4. 静态约束检查：
   - 模板/Workflow 无项目绝对路径、姓名、学号、Production=true 或 Real backend 请求；
   - `git diff --check` 无空白错误。
5. 未运行全量 pytest；按 WP3 授权留给 test_agent 统一回归。

## Test Result

- Workflow 加载：PASS（11/11）
- Manifest Schema：PASS（10/10）
- 确定性 Plan/Hash：PASS（10/10）
- 写入/Real 阻断：PASS（2/2）
- NextGen Mock simulation：PASS
- 冲突与 backend fail-closed：PASS
- 旧 selector/planner compatibility：PASS
- 静态安全检查：PASS

## Safety Check

* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Read or hashed DWG/DXF content: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Started subprocess from runtime simulation: NO
* Enabled Legacy backend: NO
* Enabled Real backend: NO
* Saved DWG: NO
* Modified source DWG: NO

## Risks Found

- Workflow 与模板是离线配置合同；未证明任何真实 CAD 读取、写入或工程语义能力。
- Water/HVAC 扫描项当前只构建扫描计划，真实产品实例检测和对象读取仍需未来 Real backend。
- `tianzheng_water_completion_plan` 与 `tianzheng_hvac_write_placeholder` 仅为 blocked 合同；不得描述为已实现写入。
- NextGen Mock 只证明 Mock 基线，不代表 NextGen Real、listener、AutoCAD .NET 插件或天正真实后端。
- 全量 pytest、CLI 集成和安装同步不在本 Agent 的 Owned Files 轻量自检范围。

## Remaining Work

- test_agent 固化并运行 WP3 的 Schema、路由冲突、Plan hash、blocked workflow、simulation 与旧兼容回归。
- docs_agent 更新配置驱动文档、模板说明与阶段报告。
- Manager 在 WP1/WP2/WP3 合并后执行统一 CLI/安全回归和 Skill 同步。
- Real/Legacy 后端、CAD/COM、DWG 访问及 Production D1 继续保持不可用。

## Recommendation

WP3 实现可进入 test_agent 统一回归。验收时应重点核对：11/10 数量、旧 1.0 Planner 合同、backend 不静默 fallback、Water/HVAC 写入模板 blocked、NextGen Mock 不冒充 Real，以及同一 Canonical Manifest 的计划哈希稳定性。


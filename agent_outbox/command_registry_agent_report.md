# Agent Report

## Agent Name

command_registry_agent

## Assigned Task

CAD-SKILL-S1-CURRENT-PROJECT-AUDIT — 当前正式项目真实代码能力审计

## Files Read

- `D:\CodexWork\天正\AGENTS.md`
- `D:\CodexWork\天正\cad\**\*.py`
- `D:\CodexWork\天正\cad_compare\**\*.py`
- `D:\CodexWork\天正\command_registry\**\*.py|*.json|*.md`
- `D:\CodexWork\天正\coordinate\**\*.py`
- `D:\CodexWork\天正\execution\**\*.py`
- `D:\CodexWork\天正\mcp\**\*.py`（代码优先定向审计）
- `D:\CodexWork\天正\mcp_nextgen\**\*.py`
- `D:\CodexWork\天正\mcp_service\**\*.py`
- `D:\CodexWork\天正\pipe_network\**\*.py`
- `D:\CodexWork\天正\reference\**\*.py`
- `D:\CodexWork\天正\roi\**\*.py`
- `D:\CodexWork\天正\semantic_diff\**\*.py`
- `D:\CodexWork\天正\tianzheng\**\*.py`
- `D:\CodexWork\天正\tianzheng_interface\**\*.py`
- `D:\CodexWork\天正\vision\**\*.py`
- 与能力相关的 `tests/**/*.py` 和 `docs/**/*.md`
- `D:\CodexWork\天正\artifacts\mcp_upgrade_handoff\mcp_upgrade_handoff_final_report.json`（Manager 指定既有验收结论）
- `D:\CodexWork\天正\artifacts\mcp_upgrade_handoff\security_findings.json`（仅核对 `SEC-FINAL-019`）

未读取任何 `.dwg`、`.dxf`、PDF/PNG/JPG 内容或大型二进制；未重新审计 `D:\CodexWork\天正-mcp-lab`。

## Files Modified

- `D:\CodexWork\天正\agent_inbox\command_registry_agent.md`
- `D:\CodexWork\天正\agent_outbox\command_registry_agent_report.md`
- `D:\CodexWork\天正\artifacts\cad_skill_packaging\20260714T000000Z_s0s1\current_project_capability_inventory.json`
- `D:\CodexWork\天正\artifacts\cad_skill_packaging\20260714T000000Z_s0s1\current_project_capability_matrix.md`

未修改任何现有执行器、测试、MCP/NextGen 源码、ROADMAP、TASK_BOARD 或 DWG。

## Work Completed

1. 完成正式项目代码能力递归盘点，按 `GENERIC_AUTOCAD`、`TIANZHENG_WATER`、`TIANZHENG_HVAC`、`SHARED_ORCHESTRATION`、`SAFETY`、`PROJECT_SPECIFIC`、`EXPERIMENTAL`、`DEPRECATED` 分类。
2. 普通 AutoCAD 已确认：运行实例附着接口、文档解析、常用 AcDb 对象读取、Line/Polyline/Text 创建、图层/块属性读取、CAD 模型比较、坐标标定与空间对齐。
3. 给排水已确认：产品/环境接口、TDb/TCH/Proxy 扫描模型、Pipe/Valve/Fitting/Dimension、给排水/消防/喷淋/消火栓分类、DNDiameter、语义 diff、几何管网图、missing、review-only 与人工视觉验收。
4. 给排水边界：`native_topology_verified=false`，`engineering_semantic_completeness_verified=false`；通用 COM backend 不支持原生创建 TDb pipe/valve/fitting，项目专用写入不可泛化。
5. 暖通已确认仅为 `INTERFACE_ONLY`：31 条未实测命令种子和 disabled domain placeholder。真实产品检测、暖通对象类型、只读 scanner、房间/风管/暖通水管/设备/风口/标注语义及写入均 `NOT_IMPLEMENTED`。
6. Checkpoint/Resume 已确认 NextGen Mock-only 基线支持 append-only hash chain、atomic checkpoint、动态批次、三计数、resume 去重、自动依赖、`MANUAL_SAVE_REQUIRED`；跨进程锁、持久化审批消费及完整互校验仍有限制，旧 P4.1 未被改写。
7. 固化 NextGen 边界：现有 `mcp_nextgen` 是唯一安全基线，protocol `1.0.0`、Mock-only；Control Plane `PARTIALLY_IMPLEMENTED`；Legacy `DISABLED_CONTRACT_ONLY`；Real/COM/.NET/Tianzheng NextGen backend `NOT_IMPLEMENTED`；`production_d1_allowed=false`。
8. `SEC-FINAL-019` 保持 `OPEN`；未运行全量 pytest，未触发间接 DWG hash helper。

## Tests Run

```text
python -m pytest -q \
  tests/skill/test_professional_domain.py \
  tests/backends/test_backend_architecture.py \
  tests/backends/test_backend_router.py \
  tests/backends/test_mock_backend.py \
  tests/nextgen/test_nextgen_handoff.py \
  tests/test_tianzheng_interface_action_schema.py \
  tests/test_tianzheng_interface_dry_run_engine.py \
  tests/test_tianzheng_interface_model.py \
  tests/test_tianzheng_interface_proxy_handler.py \
  tests/test_tianzheng_interface_scanner.py \
  tests/test_semantic_diff_engine.py \
  tests/test_cad_to_cad_diff.py \
  tests/test_cad_to_cad_matcher.py \
  tests/test_phase11_spatial_alignment.py \
  tests/test_phase12_missing_detector.py \
  tests/test_phase13_sandbox.py
```

以上测试在执行前按模块和调用边界筛选，不连接 AutoCAD，不读取 DWG，只使用纯数据、Fake、Mock 或临时目录。

## Test Result

- `197 passed in 4.98s`
- JSON inventory 解析校验：通过；`schema_version=1.0.0`，共 35 项能力，8 类分类齐全。
- 未运行当前项目全量回归，因为 `SEC-FINAL-019` 明确要求隔离会间接读取真实 DWG 的 acceptance 路径。

## Safety Check

* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO

补充：未读取任何 DWG 字节；未使用 COM、CopyObjects、LISP、NETLOAD；未运行 P4.1；未运行 Production D1。

## Risks Found

1. `SEC-FINAL-019` 仍为 `OPEN`：全量测试存在经间接 helper 读取真实 DWG 字节的路径。
2. `mcp/backends/com_backend.py` 在 `attach_only=false` 时可 Dispatch AutoCAD；统一 Skill 必须默认 offline 且显式禁止自动启动。
3. 旧 P4.1 executor 具有真实 COM、CopyObjects、保存和项目路径/plan 耦合，只能列为 `PROJECT_SPECIFIC/UNSAFE`，不能作为默认 Skill backend。
4. 暖通命令种子未经过本机验证，不能被 Capability Registry 提升为 `IMPLEMENTED`。
5. 几何管网图、视觉重合和对象类型识别均不能替代原生拓扑、显示环境和工程语义完整性验证。
6. NextGen approval consumption、跨进程 idempotency/locking、完整 checkpoint/journal 互校验仍有开放项。

## Remaining Work

- 由 Manager/skill 封装 Agent 将本 inventory 映射到统一 Capability Registry、Product Adapter 和 Backend Adapter。
- 暖通仅建立独立接口与明确状态，不启用真实命令或写入。
- SEC-FINAL-019 需在后续独立安全阶段满足完整新证据后才能关闭；本阶段不处理。

## Recommendation

1. `plain_autocad` 复用读取、比较、坐标、计划能力；真实 COM 只能经显式 Legacy adapter 与 L3 Sandbox 审批。
2. `tianzheng_water` 复用 scanner/semantic/diff/graph/review-only；原生写入继续降级并要求人工复核。
3. `tianzheng_hvac` 保持 `INTERFACE_ONLY`，不得复制给排水对象规则。
4. NextGen 仅接入现有 Mock-only protocol `1.0.0` 合同，禁止覆盖 `mcp_nextgen` 或重新引入 rejected Layer D/TCP/exec/shell。
5. Skill 默认 `offline_analysis`、`production_allowed=false`、`production_d1_allowed=false`。

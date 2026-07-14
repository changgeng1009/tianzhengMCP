# Roadmap

> 历史记录脱敏说明（redacted / not_rerun）：本页记录的真实 CAD 测试输出仅作为历史背景；对象句柄、测试线坐标和原生对象属性值已移除。本次隐私清理没有连接 CAD、重新运行测试或重新确认历史验收结果。

## Phase 1：MCP Server

状态：已完成。

当前项目已经完成最小 MCP Server，并注册 `connect_cad`、`disconnect`、`status` 三个 Phase 1 工具。本阶段不连接 AutoCAD，不调用 COM。

## Phase 2：AutoCAD Communication Layer

状态：AutoCAD Communication Layer：真实连接与实时画线已验证。

目标是建立与当前已打开 AutoCAD 2026 的 COM 通信层。当前阶段只验证连接、文档读取、`ActiveDocument.SendCommand` 和 `ModelSpace.AddLine`，不研究天正接口。

Phase 2.1 已将 ProgID 尝试顺序改为 `AutoCAD.Application.25.1`、`AutoCAD.Application.25`、`AutoCAD.Application`。

Phase 2.3 已修复 `ModelSpace.AddLine()` 参数类型，正式路径使用 `VARIANT(VT_ARRAY | VT_R8)` 构造 3D 点。真实测试已通过 `AutoCAD.Application.25.1` 连接 `Drawing1.dwg`，成功创建 `AcDbLine`，对象 handle 为 `2CF`。用户已确认 AutoCAD 屏幕实时出现 `0,0 -> 5000,0` 的线段。

## Phase 3：Vision Compare Engine MVP

状态：已完成。

目标是建立 Reference Model、Current CAD Model、Diff Engine 三层架构。当前阶段允许使用 Mock Current CAD Model，不接 MCP，不控制 CAD。

## Phase 4：Diff + MCP 接入

状态：Execution Queue MVP 已完成，基础 CAD 对象真实执行已验证。

目标是让 MCP 提供 Current CAD Model，并把 Diff Result 转换为可确认的增量操作建议。当前已完成 Diff Result 到 ExecutionPlan / OperationQueue 的安全执行链路，只真实执行基础 CAD 对象 `add_line`、`add_polyline`、`add_text`；`move_entity`、`modify_entity`、`delete_suggestion` 暂不自动执行。

手动集成测试已通过 `AutoCAD.Application.25.1` 连接 `Drawing1.dwg`，执行队列成功创建 `AcDb2dPolyline`、`AcDbLine`、`AcDbText`，并安全跳过 `modify_entity`、`move_entity`、`delete_suggestion`。

## Phase 4.5：Coordinate Mapping Layer

状态：Coordinate Mapping MVP 已完成，不执行 CAD。

目标是把 Reference Model / Diff Result / Execution Plan 中的 `image_pixel` 或 `normalized` 坐标转换为 `cad_world` 坐标。当前已支持 2 点相似变换、3 点仿射变换、ExecutionPlan 批量映射、原始坐标保留、mapping confidence、calibration id、transform type 和超范围 high risk 标记。

执行安全门禁已加入：可执行操作如果仍是 `normalized` 或 `image_pixel`，执行队列会拒绝真实 CAD 执行。

## Phase 4.6：Mapped ExecutionPlan → Safe CAD Execution

状态：Mapped ExecutionPlan → Safe CAD Execution：真实 AutoCAD 执行已验证。

目标是把 Phase 4.5 输出的 mapped `cad_world` ExecutionPlan 接入 Phase 4 安全执行队列。当前只允许在经过 preview 和 confirm 后真实执行 `add_line`、`add_polyline`、`add_text`。`normalized` 和 `image_pixel` 坐标会被拒绝执行，缺失 `mapping_confidence`、`calibration_id`、`transform_type` 也会被拒绝执行。

本阶段新增 CAD 世界坐标范围校验，默认范围为 `x/y = -100000 到 100000`。超出范围的操作会被标记为 high risk，默认不执行，必须显式允许高风险后才可继续。

本阶段不开发天正 Tool Layer，不执行 `delete_suggestion`，不执行 `move_entity` / `modify_entity`，不进入完整自动补图流程。

手动集成测试已通过：用户运行 `python scripts/manual_execute_mapped_plan_test.py`，在 preview 后输入 `YES`；`confirmed=True` 后执行成功，AutoCAD 返回真实 `handle` / `object_name`，执行 `ZOOM EXTENTS` 后 CAD 屏幕中可见新增对象。

## Phase 5：Real Current CAD Reader

状态：Real Current CAD Reader：真实 AutoCAD 当前图纸读取已验证。

目标是只读当前已经打开的 AutoCAD 图纸，读取 `ModelSpace` / `PaperSpace` 中的基础 CAD 对象，并输出可供 Diff Engine 使用的 `CurrentCADModel` JSON。

当前已支持读取 `Line`、`Polyline` / `2DPolyline` / `3DPolyline`、`Circle`、`Arc`、`Text`、`MText`、`BlockReference`、`Dimension`、Layer 信息、Handle、ObjectName、BoundingBox、Geometry、Color、Linetype。无法解析的对象会降级为 `unknown_cad_entity`，并保留 handle、object_name、layer、bounding_box、confidence 和 reason。

本阶段严格只读，不写入 CAD，不修改 CAD，不删除对象，不调用天正命令，不进入自动补图流程。单元测试已通过：`70 passed`。

真实读取测试已通过：`python scripts/manual_read_current_drawing_test.py` 成功连接 `AutoCAD.Application.25.1`，读取 `Drawing1.dwg`，统计结果为 `lines=3`、`polylines=2`、`texts=2`、`blocks=0`、`dimensions=0`、`unknown=0`，并导出 `examples/current_cad_model_from_real_sample.json`。

## Phase 5.5：Reference DWG Reader + Real CAD-to-CAD Diff MVP

状态：MVP 已完成，单元测试通过，手动 Reference DWG Diff 脚本已提供。

目标是读取同时打开的 current 和 reference 两个 AutoCAD Documents，将 reference 解析为 `ReferenceCADModel`，将 current 解析为 `CurrentCADModel`，执行 CAD-to-CAD Diff，并生成 `ExecutionPlan Preview`。

本阶段只读 current/reference，不复制 Reference DWG，不导入 Reference DWG，不绑定 Xref，不写入 CAD，不删除当前图纸内容，不调用天正命令。

当前支持输出 `add`、`modify`、`move`、`delete_suggestion`。禁止 `copy_all`、`paste_all`、`import_reference_dwg`、`rebuild_all`、`delete_all`。`delete_suggestion` 只能预览，不允许自动执行。

管径文字识别已支持 `DN50`、`DN65`、`DN75`、`DN80`、`DN100`、`DN150`、`DN200`、`DN250`、`DN300`、`De110`、`De160`，并将 `DN 200` 标准化为 `DN200`。管径与管线关联不确定时标记 `Need User Confirmation`。

单元测试已通过：`88 passed`。

## Phase 5.5.1：ROI Region Filter for Reference / Current CAD Diff

状态：MVP 已完成，单元测试通过，手动 ROI Diff 脚本已增强。

目标是在真实建筑 DWG 中避免整图 Diff，只对用户指定的水泵房大样图 ROI 区域建模和比较。

当前新增 `ROIRegion`、ROI 实体过滤器、关键词辅助定位函数 `find_text_entities_by_keyword(model, keyword)`，并增强 `scripts/manual_reference_dwg_diff_test.py`：用户选择 current/reference Documents 后，必须分别输入 current ROI 和 reference ROI，脚本只保留 ROI 内对象，再执行 CAD-to-CAD Diff 和 ExecutionPlan Preview。

本阶段只读，不写入 CAD，不复制 Reference DWG，不导入 Reference DWG，不绑定外部参照，不进入天正 Tool Layer，不进入自动补图。

单元测试已通过：`98 passed`。

## Phase 6.0：天正给排水 T30 V1.0 环境接入与对象可见性验证

状态：天正给排水 T30 V1.0 环境真实连接已验证。

目标是验证 MCP / Python COM 是否能够连接并读取由天正给排水 T30 V1.0 启动并加载天正插件的 AutoCAD 2026 实例。

当前新增天正环境检测、对象可见性诊断、用户选择对象诊断和天正命令调用预留字段。脚本只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不进入自动补图。

手动脚本：`python scripts/diagnose_tianzheng_t30_environment.py`。

单元测试已通过：`103 passed`。

真实环境检测已由用户确认通过：AutoCAD COM 连接成功，`successful_progid=AutoCAD.Application.25.1`，活动图纸为 `synthetic_sample_t8.dwg`；Caption 包含 `T30天正给排水软件 V1.0公测版 For Autodesk AutoCAD 2026`，MenuGroups 包含 `TANGENT`，SupportPath 包含 `tangent / twt30v1 / twtt30v1`，`tianzheng detected=true`。

## Phase 6.1：Interactive Tianzheng Object Inspector

状态：MVP 已完成，单元测试通过，手动对象点击检查脚本已提供。

目标是让用户在天正给排水 T30 V1.0 启动的 AutoCAD 中手动点击管线、阀门、水泵、地漏、管径标注、普通文字、普通线段、图块和标注等对象，脚本通过 COM 只读输出对象诊断信息。

当前新增 `tianzheng.object_inspector.inspect_entity(entity)`，会尽量读取 handle、object_name、entity_name、layer、color、linetype、BoundingBox、XData、ExtensionDictionary 和可用属性列表。所有属性读取都使用容错逻辑，Proxy / unknown / custom object 不会导致脚本崩溃。

手动脚本：`python scripts/manual_tianzheng_object_inspect.py`。脚本使用临时 `SelectionSet.SelectOnScreen()` 获取用户选择对象，并保存结果到 `examples/tianzheng_object_inspection_sample.json`。

Phase 6.1.1 已修复 pywin32 下 `Utility.GetEntity("请选择一个对象: ")` 触发 `TypeError: The Python instance can not be converted to a COM object` 的兼容性问题。

本阶段严格只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不开发 `create_pipe` / `create_valve`，不进入天正绘图 Tool Layer，不进入自动补图。

单元测试已通过：`115 passed`。

## Phase 6.1.2：Selected Region / Selected Objects Reader for Tianzheng DWG

状态：MVP 已完成，单元测试通过，手动框选对象读取脚本已提供。

目标是在真实水泵房 DWG 中避免整图读取和整图 Diff。用户通过天正给排水 T30 V1.0 打开 DWG 后，手动框选水泵房目标区域对象，程序只读取框选 SelectionSet 中的对象，并输出 `SelectedCADModel`。

当前新增 `tianzheng.selection_reader.read_selected_entities(document)`，使用临时 `__TianzhengSelectionReaderTemp__` SelectionSet，调用 `SelectOnScreen()`，遍历所有被选对象，并对每个对象调用 `inspect_entity(entity)`。

手动脚本：`python scripts/manual_tianzheng_selection_reader.py`。脚本输出 active document、天正环境摘要、selection_count、object_name top 20、layer top 20、proxy / tianzheng_like / unknown 数量和前 20 个对象摘要，并保存到 `examples/selected_tianzheng_model_sample.json`。

本阶段只读，不读取整图，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不执行 CAD-to-CAD Diff，不进入自动补图。

单元测试已通过：`123 passed`。

## Phase 6.2：Tianzheng Object Semantic Reader MVP

状态：MVP 已完成，单元测试通过，手动语义读取脚本已提供。

目标是在 Phase 6.0 / 6.1 已确认天正环境与对象选择可用的基础上，把已识别的天正对象转换为结构化语义对象。

当前已支持：

- `TDbPipe` -> `pipe`
- `TDbPipeValve` -> `valve`
- `TDbPipeFitting` -> `fitting`
- `TDbDimension2` -> `dimension`

当前新增 `tianzheng.semantic_reader`，提供 `read_tdb_pipe()`、`read_tdb_pipe_valve()`、`read_tdb_pipe_fitting()`、`read_tdb_dimension()`、`probe_entity_properties()` 和 `read_selected_tianzheng_semantic_model()`。

手动脚本：`python scripts/manual_tianzheng_semantic_reader_test.py`。脚本通过天正环境检测后，让用户框选水泵房区域对象，输出语义统计、object_name top 20、semantic_type 统计、system_type 统计，并保存到 `examples/tianzheng_semantic_model_sample.json`。

本阶段只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不开发 `create_pipe` / `create_valve`，不做 Reference / Current Diff，不进入自动补图。

Phase 6.2.1 已根据真实小样本将 `TDbPipeFitting` 从 `unknown_tianzheng` 改为 `fitting`。真实样本中 `TDbPipe: 3`、`TDbPipeValve: 2`、`TDbPipeFitting: 1` 时，summary 应输出 `pipe=3`、`valve=2`、`fitting=1`、`unknown_tianzheng=0`。

重要限制：`TDbPipe` 的起终点、方向、长度来自 bounding_box 推断；`TDbPipeValve` / `TDbPipeFitting` 的中心点和尺寸来自 bounding_box 推断；`diameter_guess = Radius * 2` 只是猜测，不能直接当真实管径。`TDbPipeFitting` 当前不硬判弯头、三通或接头。

单元测试已通过：`145 passed`。

## Phase 6.2.2：DN Pipe Diameter Label Recognition + Pipe Association MVP

状态：MVP 已完成，单元测试通过，手动管径标注关联脚本已提供。

目标是在 `TDbPipe.Radius` 不可直接作为真实 DN 管径的前提下，从用户框选区域识别 DN / De / Φ / D 管径文字，并与附近 `TDbPipe` 建立候选关联。

当前新增：

- `tianzheng.diameter_label_reader`
- `tianzheng.pipe_label_association`
- `config/pipe_diameter_patterns.json`
- `scripts/manual_tianzheng_diameter_association_test.py`
- `examples/tianzheng_diameter_association_sample.json`
- `docs/tianzheng_diameter_association_mvp.md`

当前支持识别并标准化 `DN 200 -> DN200`、`dn200 -> DN200`、`De 110 -> De110`、`Φ 100 -> Φ100`、`D 100 -> D100`。

管径关联仅生成 `diameter_candidates`，所有 `pipe_associations` 默认 `selected_diameter = null` 且 `status = need_user_confirmation`。即使只有一个高置信候选，也不自动确定最终管径。

本阶段只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不进入 Diff 或自动补图。

单元测试已通过：`161 passed`。

### Phase 6.2.2.1：ActiveDocument Resolution + COM Collection Compatibility

状态：已完成，COM Document 解析与集合兼容性已修复。

本阶段修复真实天正运行中出现的两个兼容性问题：

- `MenuGroups` 在 pywin32 下不能直接迭代，已改为优先使用 `Count` / `Item()`，并兼容 0 基 / 1 基 COM Collection。
- 天正环境检测成功但 `active_document = null` 时，脚本不能继续把 Application 或无效对象当作 Document 使用。当前已新增 `cad.document_resolver`，在调用 `SelectionSets` 前统一解析并校验有效 AutoCAD Document。

当前手动脚本已更新为先解析有效 Document，再进入 `SelectionSet.SelectOnScreen()`：

- `scripts/manual_tianzheng_diameter_association_test.py`
- `scripts/manual_tianzheng_semantic_reader_test.py`
- `scripts/manual_tianzheng_selection_reader.py`
- `scripts/manual_tianzheng_object_inspect.py`

本阶段仍然只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不进入天正绘图 Tool Layer，不进入 Diff 或自动补图。

测试结果：`pytest -q` 通过，结果为 `171 passed`；相关脚本和模块已通过 `python -m py_compile`。

### Phase 6.2.2.2：SelectionSet Empty Selection Handling + Cleanup Fix

状态：已完成，空选择处理与临时 SelectionSet 清理已修复。

本阶段修复真实运行中用户未选中对象时的交互问题，以及临时 SelectionSet 删除失败的问题：

- 用户未选择对象时，不再输出大段 traceback。
- 脚本会提示 `No entity selected. Please select objects in AutoCAD and press Enter.`。
- 用户可以按 Enter 重新框选，或输入 `q / quit` 退出。
- 新增 `tianzheng.selection_utils.safe_delete_selection_set()`，按直接对象、`SelectionSets.Item(name)`、遍历 `SelectionSets` 三层兜底删除临时选择集。
- `manual_tianzheng_diameter_association_test.py`、`manual_tianzheng_semantic_reader_test.py`、`manual_tianzheng_selection_reader.py` 已接入重试流程。

本阶段仍然只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不进入天正绘图 Tool Layer，不进入自动补图。

测试结果：`pytest -q` 通过，结果为 `176 passed`；相关脚本和模块已通过 `python -m py_compile`。

### Phase 6.2.3：TDbPipe Diameter / Label Deep Probe

状态：MVP 已完成，TDbPipe 管径 / 标签深度探测脚本已提供。

本阶段基于真实测试结论：疑似 DN 管径文字区域被选中后，实际对象仍然是 `TDbPipe`，因此 DN 文字可能是 `TDbPipe` 内部显示内容或天正动态标签，而不是独立 `AcDbText` / `AcDbMText`。

当前新增：

- `tianzheng/tdbpipe_deep_probe.py`
- `scripts/manual_tdbpipe_deep_probe.py`
- `docs/tdbpipe_deep_probe_mvp.md`
- `examples/tdbpipe_deep_probe_sample.json`
- `tests/test_tdbpipe_deep_probe.py`

探测内容包括 TDbPipe 基础属性、候选管径属性、XData 多 RegAppName 读取、ExtensionDictionary、COM TypeInfo 和 `dir(entity)` 可疑字段名筛选。属性、XData、ExtensionDictionary 中出现 `DN / De / Φ / D` 管径格式时，会写入 `diameter_candidates`。

重要限制：`TDbPipe.Radius` 不能当真实 DN 管径；`diameter_candidates` 只是候选，不自动确认最终管径。

本阶段仍然只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不进入天正绘图 Tool Layer，不进入 Diff 或自动补图。

测试结果：`pytest -q` 通过，结果为 `186 passed`；新增脚本和模块已通过 `python -m py_compile`。

### Phase 6.2.3.1：TDbPipe TypeInfo Property Reader

状态：TDbPipe TypeInfo Property Reader：真实 `TDbPipe.DNDiameter` 读取与 DN 标准化已验证。

本阶段基于真实 `TDbPipe` 深度探测结果，确认天正管线对象可暴露 `DNDiameter`、`SysType`、`SElevation`、`EElevation`、`ModelType`、`Label`、`DrawLabel`、`SysLabel`、`Radius`、`Length` 等属性。当前已将 `DNDiameter` 标准化为 `DNxxx` 并写入 `read_tdb_pipe()` 输出的 `diameter` 字段；`Radius` 只保留为 `display_radius`，不再作为真实管径猜测。

真实图纸复测已通过：

- `PIPE-给水` 的历史 `TDbPipe` 属性值已脱敏；保留 `DNDiameter` 标准化、`SysType`、`SElevation`、`EElevation` 字段说明，不分发真实读回值。
- `PIPE-消防` 的历史 `TDbPipe` 属性值已脱敏；保留 `DNDiameter` 标准化、`SysType`、`SElevation`、`EElevation` 字段说明，不分发真实读回值。

结论：`TDbPipe.DNDiameter` 是当前最可靠的管径来源；`Radius` 仅保留为 `display_radius`。

本阶段仍然只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不进入 Diff 或自动补图。

## Phase 6.3：Semantic Diff Engine（只读）

状态：MVP 已完成，单元测试通过。

目标是比较 `CurrentSemanticModel` 与 `ReferenceSemanticModel`，输出严格结构化的语义差异：

- `add_pipe`
- `remove_pipe`
- `modify_pipe`
- `move_pipe`
- `diameter_mismatch`
- `system_mismatch`

本阶段只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不生成执行队列，不进入自动补图。

当前 MVP 只对 `semantic_type = pipe` 的 `TDbPipe` 输出差异。管径比较只使用已经真实验证过的 `TDbPipe.DNDiameter` 标准化结果，即 `diameter.normalized`；不使用 `Radius`、`display_radius`、`Radius * 2` 或 `diameter_guess`。

## Phase 6.4：Pipe Network Graph Builder

状态：MVP 已完成，单元测试通过。

目标是将已有 `SemanticModel` 升级为只读 `PipeNetworkGraph`：

```json
{
  "nodes": [],
  "edges": [],
  "systems": [],
  "subgraphs": []
}
```

当前实现基于 `TDbPipe` 起终点生成 node 和 edge，按 `node_tolerance` 合并近距离端点；`TDbPipeValve` / `TDbPipeFitting` 通过 center 点贴近并入附近节点；`systems` 按 `system_type` 汇总，`subgraphs` 按系统类型输出连通分量。

管径继续只使用真实验证过的 `TDbPipe.DNDiameter` 标准化结果，即 `diameter.normalized`。

本阶段只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不执行 Diff，不生成执行队列，不进入自动补图。

## Phase 7：Validation / Monitor / Agent

状态：待开发。

目标是加入校验、监控和长期运行 Agent 能力，使系统能持续比较、确认和执行增量修改。

---

# Phase M0-M4：天正给排水接口层重构（Millennium 计划）

> **以下为 2026-07-08 新增的 M0-M4 + D1-E2 阶段规划。**
> M 系列为接口层重构阶段，D 系列为文档化阶段，E 系列为示例与交付阶段。
> 原有 Phase 1-6.4 已完成部分保持不变，Phase 7-17 代码已大量存在于 `mcp/` 中但 ROADMAP 未同步更新。

---

## Phase M0：项目规划与状态审计

状态：✅ 已完成

### 目标
对项目进行全面状态审计，同步 ROADMAP 与代码实际状态，定义后续 M1-M4 + D1-E2 的验收标准与任务拆分。

### 输出物
- `ROADMAP.md`：新增 Phase M0-M4 + D1-E2 阶段规划
- `TASK_BOARD.md`：全新任务看板，按 Phase 组织
- `reports/planning_agent_report.md`：规划阶段工作报告

### 关键发现
- ROADMAP 写到 Phase 6.4 截止，Phase 7 标记为"待开发"
- 实际 `mcp/` 中已有 Phase 7 (pipeline.py)、Phase 8 (pipeline_v2.py)、Phase 9-17 (各子模块) 代码
- `tianzheng_interface/` 模块（7/7 创建）已实现 model.py、action_schema.py、proxy_handler.py、dry_run_engine.py
- 但缺少 scanner.py、report_builder.py
- `tests/` 中已有 Phase 7-17 测试，pytest 186 passed
- `server.py` 已注册 21 个 MCP 工具，但未注册 `tianzheng_interface/` 模块的工具

---

## Phase M1：天正给排水接口层完整化（只读）

状态：待开发

### 目标
基于已有的 `tianzheng_interface/model.py`、`action_schema.py`、`proxy_handler.py`、`dry_run_engine.py`，补齐核心缺失模块。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| M1.1 | 实现 `tianzheng_interface/scanner.py` | 天正 DWG 一键扫描器：环境检测 → 实体分类 → 语义分析 → 管网图 → 报告 | ⏳ |
| M1.2 | 实现 `tianzheng_interface/report_builder.py` | Markdown + JSON 双格式报告生成器 | ⏳ |
| M1.3 | 新增配置 `config/tianzheng_system_types.json` | 给排水系统类型配置 | ⏳ |
| M1.4 | 新增配置 `config/tianzheng_action_templates.json` | Action 模板配置 | ⏳ |
| M1.5 | 新增样例 `examples/tianzheng_dwg_scan_report.md` | 扫描报告样例 | ⏳ |

### 验收标准
- [ ] `pytest -q` 全量通过（含新增测试）
- [ ] scanner.py 可在无 AutoCAD 环境下运行 dry-run
- [ ] report_builder.py 输出符合设计规范
- [ ] 配置与样例文件格式正确

### 安全约束
- 严格只读，不写入 CAD
- 不调用 `TPIPE` / `TDRAIN`
- 不修改 target.dwg

---

## Phase M2：Action Schema 验证与 Dry-run 完善

状态：待开发

### 目标
在 M1 完成基础上，完善 Action Schema 验证和 Dry-run 引擎，确保冲突检测覆盖完整。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| M2.1 | 完善 `tianzheng_interface/action_schema.py` | 增加所有 action type 定义（add_pipe/add_valve/modify_diameter/modify_elevation/modify_system_type/remove_pipe） | ⏳ |
| M2.2 | 完善 `tianzheng_interface/dry_run_engine.py` | 增强冲突检测（空间/图层/管径/连接）+ 变更预估 | ⏳ |
| M2.3 | 完善 `tianzheng_interface/proxy_handler.py` | 增加未知天正类型的自动发现能力 | ⏳ |
| M2.4 | 新增 `tests/test_tianzheng_interface_scanner.py` | scanner 单元测试 | ⏳ |
| M2.5 | 新增 `tests/test_tianzheng_interface_report_builder.py` | report_builder 单元测试 | ⏳ |
| M2.6 | 扩展 `tests/test_tianzheng_interface_dry_run_engine.py` | dry-run 完整测试 | ⏳ |

### 验收标准
- [ ] `pytest -q` 全量通过
- [ ] Action schema 覆盖所有给排水操作类型
- [ ] Dry-run 冲突检测：空间冲突 / 图层冲突 / 管径冲突 / 连接冲突
- [ ] 变更预估准确：新增实体数 / 修改实体数 / 待审核数 / 不可执行操作数

### 安全约束
- 所有 action.ready_to_execute = False（Phase M2 仍为只读）

---

## Phase M3：MCP 集成与手动验证

状态：待开发

### 目标
将 `tianzheng_interface/` 模块接入 `server.py`，注册新的 MCP 工具，并通过手工脚本对真实 target.dwg 执行端到端验证。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| M3.1 | 在 `server.py` 注册 `tianzheng_interface` MCP 工具 | 注册 `scan_tianzheng_dwg`、`generate_dry_run_report`、`classify_tianzheng_objects` | ⏳ |
| M3.2 | 新增 `scripts/manual_tianzheng_scan.py` | 交互式天正 DWG 扫描脚本 | ⏳ |
| M3.3 | 新增 `scripts/manual_dry_run_report.py` | 基于扫描结果生成 dry-run 报告 | ⏳ |
| M3.4 | 真实 target.dwg 全流程验证 | 对 `artifactsreal.test.001/target.dwg` 执行扫描 → 模型 → Action → Dry-run → 报告 | ⏳ |
| M3.5 | 新增 `examples/water_supply_semantic_model_sample.json` | 完整给排水语义模型样例 | ⏳ |

### 验收标准
- [ ] 3 个新 MCP 工具可正常调用
- [ ] 手工脚本对 target.dwg 扫描成功并输出完整报告
- [ ] `pytest -q` 全量通过
- [ ] 端到端流程无异常

### 安全约束
- 所有 M3 MCP 工具为只读
- 手工脚本不可写 DWG
- dry-run 报告不触发真实 CAD 操作

---

## Phase M4：文档化与工程基础设施

状态：待开发

### 目标
完善项目文档、README、API 文档，确保交付物完整且可直接交付。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| M4.1 | 更新 `README.md` | 反映 M0-M4 最新架构 | ⏳ |
| M4.2 | 创建 `docs/tianzheng_interface_api.md` | 接口 API 文档 | ⏳ |
| M4.3 | 创建 `docs/architecture_overview.md` | 完整架构总览 | ⏳ |
| M4.4 | 更新 `requirements.txt` | 确认依赖完整 | ⏳ |
| M4.5 | 代码规范检查 | 确保所有新文件风格一致 | ⏳ |

### 验收标准
- [ ] README.md 准确反映当前项目状态
- [ ] API 文档覆盖所有 `tianzheng_interface` 公开接口
- [ ] 架构总览文档覆盖所有模块
- [ ] `pip install -r requirements.txt` 无错

---

## Phase D1：交付文档

状态：待开发

### 目标
编写面向用户的交付文档。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| D1.1 | 创建 `docs/user_guide.md` | 用户使用指南 | ⏳ |
| D1.2 | 创建 `docs/deployment_guide.md` | 部署指南 | ⏳ |

### 验收标准
- [ ] 文档完整、可执行
- [ ] 新手可按文档自行部署

---

## Phase D2：变更日志与版本管理

状态：待开发

### 目标
整理 CHANGELOG 和版本管理策略。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| D2.1 | 创建 `CHANGELOG.md` | 从 Phase 1 到 M4 的完整变更日志 | ⏳ |
| D2.2 | 版本号确定 | 确定首个交付版本号 | ⏳ |

### 验收标准
- [ ] CHANGELOG 覆盖所有已完成 Phase

---

## Phase E1：示例数据与演示

状态：待开发

### 目标
准备完整示例数据集和演示材料。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| E1.1 | 整理 `examples/` 目录 | 确保 20+ 样例文件组织清晰 | ⏳ |
| E1.2 | 创建演示脚本 `examples/demo_workflow.py` | 一键演示脚本 | ⏳ |
| E1.3 | 创建 `examples/demo_output.md` | 演示预期输出 | ⏳ |

### 验收标准
- [ ] 演示脚本可独立运行
- [ ] 输出符合预期

---

## Phase E2：最终验收

状态：待开发

### 目标
执行最终全量验收，确保所有阶段的产出满足质量标准。

### 任务
| # | 任务 | 描述 | 状态 |
|---|------|------|------|
| E2.1 | 运行全量 `pytest -q` | 确保所有测试通过 | ⏳ |
| E2.2 | 运行全量代码检查 | 确保新代码无语法错误 | ⏳ |
| E2.3 | 安全审计 | 确认无违规写 DWG 代码路径 | ⏳ |
| E2.4 | 创建 `reports/final_acceptance_report.md` | 最终验收报告 | ⏳ |

### 验收标准
- [ ] `pytest -q` 全量通过
- [ ] 安全审计 0 违规
- [ ] 最终验收报告完整

---

## Phase MCP-UPGRADE-HANDOFF：DeepSeek 升级版 MCP 接口接管验收与受控主线吸收

状态：部分接管基线已交付，安全闭环与合规全量回归仍阻塞；最终状态为 `MCP_UPGRADE_HANDOFF_PARTIAL`。本阶段不得标记完全完成，不得推进下一阶段。

### 阶段目标

以 `D:\ExampleWorkspace\天正-mcp-lab` 的真实代码为准，依次完成交付盘点、原样测试复现、五层架构与安全审计、正式项目能力对照、受控代码迁移、兼容适配、全量回归和文档固化。实验项目不得整体覆盖正式项目；正式项目已经验证的执行器、测试、报告 Schema、DWG 路径和安全规则必须保留。

### 固定安全边界

- `production_d1_allowed=false`。
- 禁止连接或启动 AutoCAD/天正，禁止使用 COM、SendCommand、LISP、NETLOAD、CopyObjects。
- 禁止打开、读取、修改或保存任何 DWG；禁止运行 P4.1；禁止操作实验候选图、Reference、Target。
- 本阶段只允许源码/配置/文档审计、Python/.NET 编译、单元/集成/Mock/loopback 测试以及安全的代码级适配。
- Mock 与 Real 能力必须在类型、能力注册、文档和测试中严格区分；Mock 通过不代表真实 AutoCAD 插件能力完成。
- 任意代码执行、任意文件访问、未认证远程监听、默认 `0.0.0.0`、外部 URL 回调、绕过审批或文档身份校验的写入路径均为硬阻断项。

### 工作包与依赖

| 工作包 | 内容 | 主要负责人 | 前置依赖 | 阶段门 |
|---|---|---|---|---|
| MUH-0 | 阶段规划、依赖和安全门固化 | planning_agent | 无 | 仅规划完成，不推进阶段 |
| MUH-1 | DeepSeek 真实交付盘点、目录树、Git/包/.NET/Schema/测试/五层模块清单 | docs_agent | MUH-0 | 盘点必须来自真实代码，不依赖 README 推断 |
| MUH-2 | 原交付原样编译、测试、导入、Schema、示例和 Mock 测试复现 | test_agent | MUH-1 | 修改前先固化原始失败证据 |
| MUH-3 | 五层架构验收和安全硬阻断审计 | safety_audit_agent、command_registry_agent、cad_bridge_agent | MUH-1、MUH-2 原始证据 | Safety Audit 裁决优先 |
| MUH-4 | 与正式项目逐项能力对照，形成接受/适配/延期/拒绝决策 | Manager 汇总，各域 Agent 提供证据 | MUH-3 | 不因“新架构”默认优于现有实现 |
| MUH-5 | 统一版本化协议、审批模型、capability、job/journal/checkpoint 契约 | command_registry_agent、safety_audit_agent | MUH-4 | 无版本自由 JSON、无 plan hash 或无身份绑定不得进入执行层 |
| MUH-6 | 受控迁移、兼容层与 `LegacyCadBackendAdapter`（或等价接口） | cad_bridge_agent、command_registry_agent | MUH-5 且安全放行 | 禁止重写或替换现有真实执行器；禁止触发真实后端 |
| MUH-7 | nextgen、兼容、P4.1 checkpoint 回归及正式项目全量测试 | test_agent | MUH-6 | 不删除或弱化已有测试；失败不得标为接受 |
| MUH-8 | 架构/协议/安全/恢复/集成/插件路线图文档与最终交付报告 | docs_agent、Manager | MUH-3 至 MUH-7 的真实结果 | Manager 仅在所有门满足后裁定最终状态 |

### 关键验收门

1. **原始证据门**：先保存原始测试命令、计数、通过/失败/跳过、警告、耗时、环境和失败详情，之后才允许最小修复。
2. **安全门**：`security_findings` 中的硬阻断项必须隔离、删除或拒绝迁移；未关闭的 Critical/High 阻断项禁止进入 MUH-6。
3. **迁移门**：每个迁移文件必须有来源、决定、适配说明和测试覆盖；不得整库复制覆盖。
4. **恢复门**：journal 必须 append-only 且有序列/哈希链；checkpoint 原子写入；完成批次动态读取；resume 不重复执行；保存失败支持 `MANUAL_SAVE_REQUIRED`。
5. **审批门**：审批绑定 `job_id`、DocumentIdentity、plan hash、允许操作以及 expiry 或 single-use；当前默认最高不超过安全测试范围，不授予 L4 生产权限。
6. **回归门**：新增测试、legacy adapter 兼容测试、正式项目原有测试和全量回归均须记录真实结果。
7. **阶段门**：`safety_audit_agent` 放行、`test_agent` 全量测试通过、`docs_agent` 文档完成且所有 outbox 就绪后，Manager 才能裁定最终状态。

### 必需交付物

- `artifacts/mcp_upgrade_handoff/` 下完整 inventory、原始测试、架构验收矩阵、主线对照、安全发现、迁移/拒绝/延期清单、集成测试和最终报告（JSON/Markdown）。
- `docs/mcp_nextgen/00_handoff_summary.md` 至 `07_known_limitations.md`。
- 受控接入的 nextgen 包、legacy adapter 及 `tests/nextgen/`；具体目录以现有项目结构审计结论为准。

### 2026-07-14 收口证据

- DeepSeek 原始交付：`pytest -q` 共 75 项，69 通过、6 失败；原交付不是可直接接受基线。
- NextGen 定向回归：`pytest -q tests/nextgen` 共 47 项，47 通过、0 失败；该结果仅证明 Mock-only 定向基线。
- 正式项目全量回归：1561 项中 1554 通过、7 失败、1 warning，状态为 `FAILED_WITH_SAFETY_BOUNDARY_VIOLATION`，不能声明合规通过。
- 全量测试间接调用 `_preflight()`，以只读 `rb`/SHA-256 方式实际读取 3 个真实 DWG；未连接 AutoCAD/天正/COM，未修改或保存 DWG，但读取行为仍违反本阶段明确边界，登记为 `SEC-FINAL-019`（HIGH、OPEN）。
- 最终安全裁决：`CONDITIONAL_NEXTGEN_BASELINE_ONLY`，风险等级 `HIGH`。19 项发现中 4 Critical、12 High、3 Medium；8 Fixed、3 Rejected Not Migrated、5 Deferred、3 Open。
- 已建立 53 个受控基线文件；实验源码 `ACCEPT_AS_IS` 为 0。Layer A/B/C/E 为 `ACCEPT_WITH_ADAPTATION`，Layer D 原样迁移为 `REJECT`。
- 协议版本为 `1.0.0`；12 个 canonical 结构；9 个 MCP tools 均为 Mock 能力，只有 3 个提供安全 Mock 结果，其余 6 个未实现。
- `LegacyCadBackendAdapter` 为 `DISABLED_CONTRACT_ONLY`；`execution_enabled=false`、`production_allowed=false`、`production_d1_allowed=false`。
- NextGen 已覆盖 dynamic completed batch、三计数、atomic checkpoint、resume no duplicate、automatic dependency、manual save 等回归；正式 P4.1 冻结代码未修改、未重跑，其 checkpoint 原子写和三计数未宣告修复。
- RealCadBackend、.NET in-process plugin、天正 backend、COM adapter、Legacy enablement、真实 save/reopen/rollback 与 Production D1 均未实现。

### 未关闭阻断与延期

1. 关闭 `SEC-FINAL-019`，以假 DWG/依赖注入隔离旧 acceptance preflight，并在跨模块调用图审计后再运行全量回归。
2. 修复 5 个 Windows GBK/UTF-8 旧测试失败；不得用 47/47 覆盖全量 1554/1561 的失败记录。
3. 强制 FastMCP 服务入口鉴权、精确 loopback 和 replay 防护，禁止绕过 dispatcher。
4. 建立 single-use approval 的持久原子消费与跨进程幂等/锁，关闭 journal crash window。
5. 完成 checkpoint/journal 全字段互校验；正式 P4.1 的适配必须另立阶段并重新 Safety Audit。
6. Real/plugin/Legacy/Production D1 继续延期并保持禁用。

### 最终状态判定

依据最终 artifacts、各 Agent outbox 与 Manager 收口指令，本阶段判定为 `MCP_UPGRADE_HANDOFF_PARTIAL`。该判定只接受 NextGen Mock-only 受控基线，不代表安全门、全量回归、Legacy、Real/plugin、P4.1 或 Production D1 完成；本阶段保持未完全完成状态，不推进下一阶段。

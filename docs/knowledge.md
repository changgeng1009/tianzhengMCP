# Knowledge

> 历史记录脱敏说明（redacted / not_rerun）：本页记录的真实 CAD 测试输出仅作为历史背景；对象句柄、测试线坐标和原生对象属性值已移除。本次隐私清理没有连接 CAD、重新运行测试或重新确认历史验收结果。

## 本阶段设计决策

- Vision Compare Engine 作为独立 `vision/` 模块实现，不接入 MCP Server。
- `server.py` 不修改，Phase 1 MCP Server 保持原状。
- Provider 命名为 `OpenAIVisionProvider`，模型通过 `VisionProviderConfig(model="gpt-5.5")` 指定。
- 图片细节等级通过 `VisionProviderConfig(image_detail=...)` 指定，默认 `original`，成本敏感时可改为 `high`。
- OpenAI Vision 输出必须走结构化 JSON，不允许自然语言作为业务输出。
- Current CAD Model 当前只支持 Mock JSON 输入，为后续 MCP 接入预留边界。
- Diff Engine 只输出增量建议，不输出重绘整图。

## 已知限制

- MVP 不做图像预处理；轻微旋转、边框、噪点、模糊等鲁棒性主要由 GPT-5.5 Vision 识别和置信度表达承担。
- MVP 不执行真实 OpenAI API 单元测试，避免网络依赖和额度消耗。
- MVP 不做图像坐标到 CAD 世界坐标的转换。
- MVP 不处理复杂多页图纸、跨视口比例尺、图纸坐标校准。
- Diff 匹配策略目前优先按实体 ID 匹配，其次按类型和少量稳定属性匹配。
- `delete_suggestion` 只是建议，不允许自动执行。

## 后续 MCP 接入预留点

- MCP 后续应提供 Current CAD Model JSON，而不是让 Vision 模块直接调用 AutoCAD。
- MCP 输出需要包含实体 ID、类型、几何、属性、置信度、证据和不确定性字段。
- 后续应新增 Coordinate Mapping 层，把 `image_pixel` 或 `normalized` 坐标映射到 `cad_world`。
- Diff + MCP 接入阶段应把 `DiffResult` 转换为可人工确认的操作队列。
- Incremental Editing 阶段只允许对确认后的 `add / modify / move / delete_suggestion` 执行增量操作。

## Vision MVP 阶段禁止事项

- 不把 Vision MVP 改成 OCR。
- 不把 Vision MVP 改成 PDF 转 CAD。
- 不把 Vision MVP 改成图片生成 DWG。
- 不在 Vision MVP 阶段控制 CAD、调用 COM、研究天正接口或使用 `SendCommand`。
- 不提前开发天正给排水 Tool Layer。

## Phase 2：AutoCAD Communication Layer

### 本阶段实现

- 新增 `cad/` 模块，封装 AutoCAD COM 连接、文档读取、命令发送和基础实体创建。
- MCP 工具层新增 `list_documents`、`get_active_document`、`send_command`、`draw_line`。
- `connect_cad` 现在连接当前已经打开的 AutoCAD，不自动启动 AutoCAD。
- `status` 返回当前 COM 连接状态、AutoCAD 可见性、版本、活动图纸和打开文档数量。
- 单元测试使用 Fake COM 对象，不要求本机必须打开 AutoCAD。

### COM 连接策略

- 优先尝试 AutoCAD 2026 ProgID：`AutoCAD.Application.25.1`。
- 然后尝试版本化 ProgID：`AutoCAD.Application.25`。
- 最后尝试通用 ProgID：`AutoCAD.Application`。
- 使用 `win32com.client.GetObject(Class=...)` 连接正在运行的实例。
- 不使用 `Dispatch`，避免自动启动 AutoCAD。

### 手动检查清单

1. AutoCAD 2026 必须已经手动打开。
2. 必须已经打开一个 DWG 文件。
3. AutoCAD 当前不能停留在未结束的命令状态。
4. Python 和 AutoCAD 尽量使用相同权限运行：不要一个用管理员权限，一个不用。
5. 使用 64-bit Python。
6. 已安装 pywin32。
7. 不要使用 AutoCAD LT 作为测试目标。
8. 不要只打开天正启动器，必须进入实际 AutoCAD 编辑界面。

### Phase 2.1 当前验证状态

- AutoCAD 2026 真实连接：本次运行 `python scripts/diagnose_autocad_com.py` 时未发现可连接的 AutoCAD COM 运行对象。
- Python：3.13.13，64-bit。
- pywin32：可用。
- 已尝试 ProgID：`AutoCAD.Application.25.1`、`AutoCAD.Application.25`、`AutoCAD.Application`。
- 当前结果：三个 ProgID 均通过 `win32com.client.GetObject(Class=...)` 返回 COM 错误 `操作无法使用`。
- 进程检查：未发现 `acad.exe` 或相关 AutoCAD 编辑进程。
- 成功使用的 ProgID：无，待用户手动打开 AutoCAD 2026 和测试 DWG 后确认。
- `SendCommand`：已实现 `ActiveDocument.SendCommand(command)`，由于当前未连接 AutoCAD，真实发送结果待手动集成测试确认。
- `AddLine`：已实现 `ModelSpace.AddLine(start, end)` 并调用 `ActiveDocument.Regen(1)`，由于当前未连接 AutoCAD，屏幕实时画线结果待手动集成测试确认。

### Phase 2.3 当前验证状态

- Phase 2 标记：AutoCAD Communication Layer：真实连接与实时画线已验证。
- AutoCAD 2026 真实连接：已成功。
- 成功 ProgID：`AutoCAD.Application.25.1`。
- AutoCAD Version：`25.1s (LMS Tech)`。
- ActiveDocument：`Drawing1.dwg`。
- AddLine 参数修复方式：`VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z])`。
- 真实画线测试：`python scripts/manual_draw_line_test.py` 成功执行 `ModelSpace.AddLine()`。
- 创建对象：`object_name=AcDbLine`；真实对象句柄已脱敏。
- 测试线：历史真实绘线输出坐标已脱敏；不作为当前验收证据。
- CAD 屏幕肉眼确认：原记录称用户曾确认测试线可见；本次清理没有重新观察或确认 CAD 输出。

### 已知问题

- 如果 AutoCAD 未打开，`connect_cad` 会返回明确错误，不会自动启动 AutoCAD。
- 如果 AutoCAD 打开但没有活动图纸，文档、命令和绘图操作会返回错误。
- `SendCommand` 依赖 AutoCAD 命令行状态；如果当前命令未结束，后续命令可能受影响。
- 当前只验证基础 AutoCAD 控制，不涉及天正命令、天正对象或业务语义。

### 下一阶段建议

- Phase 2 已完成真实连接与实时画线验证；进入后续阶段前保持当前通信层稳定。
- Phase 4 前先稳定 Current CAD Model 的 MCP 输出格式。
- 暂不进入天正给排水 Tool Layer，避免把通信层和业务层耦合。

## Phase 4：Diff Result 到 MCP Execution Queue

### 本阶段实现

- 新增 `execution/` 模块，定义 `ExecutionPlan`、`Operation`、`OperationType`、`OperationStatus`、`OperationQueue` 和 `ExecutionResult`。
- 新增 `ExecutionPlanner`，把 Diff Result 转换为安全执行计划。
- 新增 MCP 工具：`generate_execution_plan`、`preview_execution_plan`、`confirm_execution_plan`、`execute_execution_plan`。
- 扩展 `cad.entities.EntityService`，支持 `draw_polyline(points)` 和 `add_text(text, x, y, height)`。
- 新增 `examples/execution_plan_sample.json` 和 `docs/execution_queue_mvp.md`。

### 安全决策

- 默认 Safe Mode：所有计划必须先 preview，再 confirm，最后才能 execute。
- `delete_suggestion` 永远不能自动执行。
- 当前只真实执行 `add_line`、`add_polyline`、`add_text`。
- `move_entity` 和 `modify_entity` 当前只生成计划，执行时返回 `not_implemented`。
- 超过 10 个操作的计划自动标记为 `high` risk。
- 本阶段不是自动补图，不重建整张图纸，不接入天正命令。

### 当前限制

- `examples/diff_result_sample.json` 中的新增对象使用 normalized 坐标，真实 CAD 执行时需要后续坐标映射层进一步处理。
- 手动集成脚本会额外加入明确标记的 smoke-test line/text 操作，用于验证基础 CAD 执行能力。
- 天正给排水对象和高级修改逻辑留到后续阶段。

### 手动集成测试结果

- 命令：`python scripts/manual_execute_plan_test.py`，输入 `YES` 确认执行。
- AutoCAD 连接：成功，`successful_progid=AutoCAD.Application.25.1`。
- ActiveDocument：`Drawing1.dwg`。
- 从 `examples/diff_result_sample.json` 生成 Execution Plan：成功。
- Preview：成功。
- Confirm：成功。
- Execute：成功。
- `modify_entity`：未执行，返回 `not_executable`。
- `move_entity`：未执行，返回 `not_executable`。
- `delete_suggestion`：未执行，返回 `not_executable`。
- `add_polyline`：执行成功，`object_name=AcDb2dPolyline`；真实对象句柄已脱敏。
- 手动 smoke-test `add_line`：执行成功，`object_name=AcDbLine`；真实对象句柄已脱敏。
- 手动 smoke-test `add_text`：执行成功，`object_name=AcDbText`；真实对象句柄已脱敏。
- CAD 屏幕肉眼确认：脚本已成功创建对象并提示确认；屏幕可见性以用户当前 AutoCAD 视图观察为准。

## Phase 4.5：Coordinate Mapping Layer

### 本阶段实现

- 新增 `coordinate/` 模块，定义 `CoordinateSystem`、`Point2D`、`Point3D`、`BoundingBox`、`CalibrationPoint`、`CoordinateTransform`、`MappingResult`。
- 新增校准机制，支持 2 点相似变换和 3 点仿射变换。
- 新增坐标变换，支持 `normalized -> cad_world`、`image_pixel -> normalized`、`image_pixel -> cad_world`、`cad_world -> normalized`。
- 新增 ExecutionPlan 批量映射，保留原始坐标并写入映射后的 `cad_world` 坐标。
- 新增执行安全门禁：可执行操作如果仍是 `normalized` 或 `image_pixel`，`execute_execution_plan` 会拒绝执行并返回 `Coordinate mapping is not calibrated.`。

### 示例与验证

- 校准点示例：`examples/calibration_points_sample.json`。
- 映射结果示例：`examples/mapped_execution_plan_sample.json`。
- 手动脚本：`python scripts/manual_coordinate_mapping_test.py`。
- 示例映射：`[0.2, 0.8] normalized -> [2000.0, 4000.0, 0.0] cad_world`。

### 安全决策

- 本阶段不执行 CAD。
- 不把 `normalized` 坐标当成 `cad_world` 坐标。
- 校准点不足时拒绝映射。
- 映射坐标超出合理 CAD 范围时标记 high risk。
- 天正给排水对象和自动补图仍不进入本阶段。
## Phase 4.6：Mapped ExecutionPlan → Safe CAD Execution

### 本阶段实现

- 新增 `execution.validation`，在真实执行前校验 mapped ExecutionPlan。
- `execute_execution_plan(plan_id)` 已接入同一套坐标安全门禁。
- 新增 `execute_mapped_execution_plan(plan_json, confirmed=False, allow_high_risk=False)`，默认只预览，不执行 CAD。
- 新增 `scripts/manual_execute_mapped_plan_test.py`，用于手动验证 mapped `cad_world` 计划能在 AutoCAD 中创建基础对象。
- 新增 `examples/mapped_execution_result_sample.json` 和 `docs/mapped_execution_mvp.md`。

### 安全决策

- 只有 `cad_world` 坐标允许进入真实 CAD 执行。
- `normalized` 和 `image_pixel` 坐标一律拒绝执行，返回 `Coordinate mapping is not calibrated.`。
- 可执行操作必须包含 `mapping_confidence`、`calibration_id`、`transform_type`。
- 默认 CAD 合理范围为 `x/y = -100000 到 100000`。
- 超出范围的可执行对象会被标记为 `high` risk，默认不执行；只有显式 `allow_high_risk=True` 才允许继续。
- `delete_suggestion` 永远不能自动执行。
- 当前只真实执行 `add_line`、`add_polyline`、`add_text`。

### 测试结果

- 单元测试：`pytest -q` 已通过，结果为 `61 passed`。
- 本阶段单元测试使用 Fake CAD Executor，不调用真实 AutoCAD。
- 手动 AutoCAD 集成测试：`python scripts/manual_execute_mapped_plan_test.py` 已由用户运行并验证通过。
- Preview 后输入 `YES`，`confirmed=True` 后真实执行成功。
- Mapped execution plan 已通过坐标与安全校验。
- AutoCAD 已返回真实 `handle` / `object_name`。
- 执行 `ZOOM EXTENTS` 后，用户已确认 CAD 屏幕中可以看到新增对象。
- Phase 4.6 状态：Mapped ExecutionPlan → Safe CAD Execution：真实 AutoCAD 执行已验证。

### 已知限制

- 当前 CAD bounds 是静态配置，不是从 AutoCAD 图纸 extents 自动读取。
- 当前不执行 `move_entity` 和 `modify_entity`。
- 当前不开发天正给排水 Tool Layer。
- 当前不进入完整自动补图、参考 DWG 同步、Agent 或 Monitor。

## Phase 5：Real Current CAD Reader

### 本阶段实现

- 新增 `cad.reader.CADReader`，只读当前 AutoCAD `ModelSpace` / `PaperSpace`。
- 新增 `cad.geometry`，负责点、坐标数组和 BoundingBox 安全解析。
- 新增 `cad.layers`，读取图层名称、颜色和线型。
- 新增 `cad.blocks`，读取 BlockReference 的基础属性。
- 新增 MCP Tools：`read_current_drawing()`、`read_selected_entities()`、`summarize_current_drawing()`。
- 新增手动脚本：`scripts/manual_read_current_drawing_test.py`。
- 新增示例：`examples/current_cad_model_from_real_sample.json`。
- 新增文档：`docs/current_cad_reader_mvp.md`。

### 只读安全边界

- 本阶段所有工具只读取当前 CAD。
- 不调用 `AddLine`、`AddPolyline`、`AddText`。
- 不调用 `Delete`、`Move`、`Copy`。
- 不调用修改类 `SendCommand`。
- 不开发天正命令，不进入自动补图。

### CurrentCADModel 对齐

- 输出 `source.kind = current_autocad`。
- 实体保留 `id`、`handle`、`type`、`object_name`、`layer`、`geometry`、`bounding_box`、`properties`、`confidence`、`source`。
- `geometry.coordinate_system` 明确为 `cad_world`。
- `geometry.points` 使用 Phase 3 可加载的 `{x, y, coordinate_system}` 格式。
- CAD 原始元数据同时保留在实体顶层和 `properties` 中，便于后续 Diff 和执行追踪。

### 支持对象

- `Line`
- `Polyline` / `2DPolyline` / `3DPolyline`
- `Circle`
- `Arc`
- `Text`
- `MText`
- `BlockReference`
- `Dimension`
- 无法解析对象降级为 `unknown_cad_entity`，保留 handle、object_name、layer、bounding_box、confidence 和 reason。

### 测试结果

- 单元测试：`pytest -q` 已通过，结果为 `70 passed`。
- 单元测试使用 Fake COM 对象，不依赖真实 AutoCAD。
- 手动读取脚本已真实运行通过：`python scripts/manual_read_current_drawing_test.py`。
- 真实连接 ProgID：`AutoCAD.Application.25.1`。
- AutoCAD Version：`25.1s (LMS Tech)`。
- ActiveDocument：`Drawing1.dwg`。
- 当前图纸对象统计：`lines=3`、`polylines=2`、`texts=2`、`blocks=0`、`dimensions=0`、`unknown=0`。
- 已导出真实 CurrentCADModel JSON：`examples/current_cad_model_from_real_sample.json`。
- 本阶段真实测试确认：只读当前 CAD，不写入、不修改、不删除任何对象。

### 已知限制

- 天正对象当前暂不做专业语义解析，可能降级为 block 或 `unknown_cad_entity`。
- Polyline 的 bulge、曲线拟合等高级几何暂未展开。
- Dimension 当前只读取基础属性，不拆解复杂标注语义。
- 当前不读取参考 DWG，不进入自动补图、Agent 或 Monitor。

## Phase 5.5：Reference DWG Reader + Real CAD-to-CAD Diff MVP

### 本阶段实现

- 新增 `reference/` 模块，读取 Reference Document 并建立 `ReferenceCADModel`。
- 新增 `reference.filters.ReferenceEntityFilter`，过滤图签、标题栏和非设计内容。
- 新增 `reference.pipe_diameter.PipeDiameterExtractor`，识别并标准化 DN / De 管径文字。
- 新增 `cad_compare/` 模块，完成 ReferenceCADModel 与 CurrentCADModel 的 CAD-to-CAD Diff。
- 新增手动脚本：`scripts/manual_reference_dwg_diff_test.py`。
- 新增配置：`config/reference_filter_rules.json`、`config/pipe_diameter_patterns.json`、`config/standard_mapping.json`。
- 新增示例：`examples/reference_cad_model_sample.json`、`examples/pipe_diameter_extraction_sample.json`、`examples/real_current_vs_reference_diff_sample.json`、`examples/cad_to_cad_execution_plan_sample.json`。

### 安全边界

- Reference DWG 只作为结构化参考来源。
- 不复制 Reference DWG 对象。
- 不导入 Reference DWG。
- 不绑定 Reference DWG 为外部参照。
- 不批量粘贴参考图块。
- 不写入 CAD，不删除当前图纸内容。
- 不调用天正命令，不进入自动补图。

### Diff 决策

- 只输出 `add`、`modify`、`move`、`delete_suggestion`。
- 禁止输出 `copy_all`、`paste_all`、`import_reference_dwg`、`rebuild_all`、`delete_all`。
- `delete_suggestion` 仅作为建议，转换为 ExecutionPlan Preview 后不可执行。
- 当前采用保守几何 tolerance 匹配，轻微坐标误差不重复创建。

### 管径识别

- 支持识别 `DN50`、`DN65`、`DN75`、`DN80`、`DN100`、`DN150`、`DN200`、`DN250`、`DN300`、`De110`、`De160`。
- `DN 200` 标准化为 `DN200`。
- `De 110` 标准化为 `De110`。
- 当前只识别管径文字；如果不能确定它属于哪条管线，必须标记 `Need User Confirmation`。

### 测试结果

- 单元测试：`pytest -q` 已通过，结果为 `88 passed`。
- 单元测试使用 Fake COM / JSON 数据，不依赖真实 AutoCAD。
- 手动脚本已提供；需要用户同时打开 current 和 reference 两个 DWG 后运行。

### 已知限制

- 当前不做天正专业对象语义识别。
- 当前不自动关联管径文字和具体管线。
- 当前不执行 ExecutionPlan，只生成 Preview。
- 当前不进入完整自动补图、Agent 或 Monitor。

## Phase 5.5.1：ROI Region Filter for Reference / Current CAD Diff

### 本阶段实现

- 新增 `roi/` 模块，包含 `ROIRegion`、ROI 实体过滤器和关键词辅助定位。
- 新增 `config/roi_presets.json`，用于保存常用 ROI。
- 增强 `scripts/manual_reference_dwg_diff_test.py`，要求用户分别输入 current ROI 和 reference ROI。
- CAD-to-CAD Diff 现在在手动脚本中只对 ROI 内对象执行。
- 新增文档：`docs/roi_filter_mvp.md`。

### ROI 过滤规则

对象满足任一条件即保留：

- `bounding_box` 与 ROI 相交。
- entity center 在 ROI 内。
- `geometry.points` 中有点在 ROI 内。
- text insertion point / position 在 ROI 内。

过滤输出包含：

- `kept_entities`
- `excluded_entities_count`
- `roi_summary`

### 辅助定位

- 新增 `find_text_entities_by_keyword(model, keyword)`。
- 可用 `水泵房大样图` 等标题文字辅助用户找到区域。
- 当前不自动确定 ROI，只辅助人工输入。

### 安全边界

- 本阶段禁止整图 Diff。
- 不写入 CAD。
- 不复制、不导入、不绑定 Reference DWG。
- 不开发天正 Tool Layer。
- 不进入自动补图、Agent 或 Monitor。

### 测试结果

- 单元测试：`pytest -q` 已通过，结果为 `98 passed`。
- 单元测试使用 JSON / Fake 数据，不依赖真实 AutoCAD。

## Phase 6.0：天正给排水 T30 V1.0 环境接入与对象可见性验证

### 本阶段实现

- 新增 `tianzheng/` 诊断模块。
- 新增 `TianzhengEnvironmentDetector`，检测由天正 T30 启动并加载插件的 AutoCAD 环境。
- 新增 `TianzhengVisibilityDiagnostic`，统计当前图纸中的代理对象、疑似天正对象、未知对象和基础可见对象。
- 新增用户选择对象诊断能力，读取当前选择集中的 handle、object_name、layer、color、linetype。
- 新增手动脚本：`scripts/diagnose_tianzheng_t30_environment.py`。
- 新增示例：`examples/tianzheng_t30_diagnostic_sample.json`。
- 新增文档：`docs/tianzheng_t30_environment_mvp.md`。

### 检测信号

- AutoCAD Caption
- AutoCAD Version
- ActiveDocument
- MenuGroups
- SupportPath
- TrustedPaths
- `MENUNAME`
- `ACADVER`

检测关键词包括：`Tianzheng`、`Tangent`、`T30`、`天正`。

### 未检测到天正环境时的提示

```text
Tianzheng T30 environment is not detected. Please launch AutoCAD through 天正给排水 T30 V1.0.
```

### 安全边界

- 本阶段只读，不写入 CAD。
- 不调用天正绘图命令。
- 不调用 `TPIPE` / `TDRAIN`。
- 不开发天正 Tool Layer。
- 不进入自动补图。
- 天正命令调用仅保留 `command_probe` 诊断字段，不实际发送命令。

### 测试结果

- 单元测试：`pytest -q` 已通过，结果为 `103 passed`。
- 单元测试使用 Fake COM 对象，不依赖真实天正或真实 AutoCAD。
- 手动天正环境检测已由用户真实验证通过。
- AutoCAD COM 连接成功，成功 ProgID：`AutoCAD.Application.25.1`。
- ActiveDocument：`synthetic_sample_t8.dwg`。
- Caption 包含：`T30天正给排水软件 V1.0公测版 For Autodesk AutoCAD 2026`。
- MenuGroups 包含：`TANGENT`。
- SupportPath 包含：`tangent / twt30v1 / twtt30v1`。
- `tianzheng detected=true`。

## Phase 6.1：Interactive Tianzheng Object Inspector

### 本阶段实现

- 新增 `tianzheng.object_inspector.inspect_entity(entity)`。
- 新增 `scripts/manual_tianzheng_object_inspect.py`。
- 新增 `docs/tianzheng_object_inspector_mvp.md`。
- 新增示例：`examples/tianzheng_object_inspection_sample.json`。
- 新增单元测试：`tests/test_tianzheng_object_inspector.py`。

### 对象检查内容

对象检查器会尽量读取：

- `handle`
- `object_name`
- `entity_name`
- `layer`
- `color`
- `linetype`
- `bounding_box`
- `available_properties`
- `xdata`
- `extension_dictionary`
- `diagnostic`

所有属性读取都必须容错。某个属性读取失败不会导致脚本崩溃，而是写入 `diagnostic.errors`。

### 天正对象判断信号

`is_tianzheng_like` 当前综合以下信号：

- `object_name` / `entity_name` 包含 `TCH`、`TWT`、`Tianzheng`、`Tangent`、`TArch`、`天正`。
- 图层包含给水、排水、给排水、管、阀、泵、地漏、pipe、drain、valve、pump 等关键词。
- 对象为 Proxy。
- 对象存在 XData。
- 对象存在 ExtensionDictionary。

该字段只是诊断信号，不代表已经完成天正业务语义分类。

### 手动检查流程

用户通过天正给排水 T30 V1.0 打开真实 DWG 后运行：

```powershell
python scripts/manual_tianzheng_object_inspect.py
```

脚本会提示用户在 CAD 中点击对象，并使用临时 `SelectionSet.SelectOnScreen()` 获取对象。建议依次点击：

- 天正管线
- 阀门
- 水泵
- 地漏
- 管径标注
- 普通文字
- 普通线段
- 图块
- 标注

每次点击结果会保存到 `examples/tianzheng_object_inspection_sample.json`。

### 安全边界

- 本阶段只读，不写入 CAD。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不开发 `create_pipe` / `create_valve`。
- 不开发天正给排水 Tool Layer。
- 不执行 CAD-to-CAD Diff 或 ROI Diff。
- 不进入自动补图。
- 不批量分解对象。

### 测试结果

- 单元测试：`pytest -q` 已通过，结果为 `115 passed`。
- 单元测试使用 Fake COM 对象，不依赖真实 AutoCAD / 天正。

### Phase 6.1.1 对象选择兼容性修复

- 真实运行中 `Utility.GetEntity("请选择一个对象: ")` 在 pywin32 下触发 `TypeError: The Python instance can not be converted to a COM object`。
- 根因是 AutoCAD COM 的 `Utility.GetEntity` 在 pywin32 中不能直接按字符串 prompt 方式调用。
- 当前脚本已改为临时 SelectionSet 方案：删除同名临时选择集，创建 `__TianzhengObjectInspectTemp__`，调用 `SelectOnScreen()`，选择多个对象时只取第一个，未选择对象时返回明确错误，最后删除临时 SelectionSet。
- 该修复仍然只读，不写入 CAD，不调用天正绘图命令。

### 已知限制

- 当前只诊断对象身份和可读取属性，不解析天正专业语义。
- XData / ExtensionDictionary 是否可读取以及具体结构，需要真实点击样本确认。
- Proxy 对象目前只做身份诊断，不做分解或恢复。
- 本阶段不写入、不修改、不删除 CAD 对象。

## Phase 6.1.2：Selected Region / Selected Objects Reader for Tianzheng DWG

### 本阶段实现

- 新增 `tianzheng.selection_reader.read_selected_entities(document)`。
- 新增手动脚本：`scripts/manual_tianzheng_selection_reader.py`。
- 新增文档：`docs/tianzheng_selection_reader_mvp.md`。
- 新增示例：`examples/selected_tianzheng_model_sample.json`。
- 新增单元测试：`tests/test_tianzheng_selection_reader.py`。

### 设计决策

- 真实水泵房 DWG 中包含建筑底图、图框、其他区域和其他专业内容，不能直接整图读取或整图 Diff。
- 当前阶段改为用户手动框选水泵房目标区域对象。
- 程序只读取用户 SelectionSet 中的对象，不遍历整张 `ModelSpace`。
- 每个被选对象继续复用 `inspect_entity(entity)`，确保天正对象、Proxy、unknown 对象都能安全保留诊断信息。

### SelectedCADModel 输出

输出结构包含：

- `source = selected_tianzheng_entities`
- `active_document`
- `selection_count`
- `entities`
- `summary`

实体至少保留：

- `handle`
- `object_name`
- `entity_name`
- `layer`
- `color`
- `linetype`
- `bounding_box`
- `is_proxy`
- `is_tianzheng_like`
- `diagnostic.errors`

完整对象检查结果保留在 `inspection` 字段。

### 安全边界

- 本阶段只读。
- 不读取整图。
- 不写入 CAD。
- 不修改、不删除 CAD 实体。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不做 CAD-to-CAD Diff。
- 不复制、不导入 Reference DWG，不绑定 Xref。
- 不进入自动补图。
- 允许删除的只有临时 SelectionSet，不是 CAD 图元。

### 手动测试

运行：

```powershell
python scripts/manual_tianzheng_selection_reader.py
```

脚本会提示用户在 AutoCAD 中框选需要识别的区域对象，然后导出：

```text
examples/selected_tianzheng_model_sample.json
```

### 测试结果

- 单元测试使用 Fake COM，不依赖真实 AutoCAD / 天正。
- 当前新增测试覆盖：临时 SelectionSet 清理、SelectOnScreen 读取多个对象、空选择明确错误、每个对象调用 inspect、Proxy 不中断、JSON 可序列化、summary 统计。
- 全量单元测试：`pytest -q` 已通过，结果为 `123 passed`。

## Phase 6.2：Tianzheng Object Semantic Reader MVP

### 已确认真实天正对象

用户真实点击结果已确认以下对象可识别：

- `TDbDimension2`：天正标注对象，layer 通常为 `TWT_DIM`，XData 和 ExtensionDictionary 可用。
- `TDbPipe`：天正管线对象，layer 包括 `PIPE-喷淋` / `PIPE-消防`，available_properties 包含 `Radius`，XData 和 ExtensionDictionary 可用。
- `TDbPipeValve`：天正阀门对象，layer 包括 `VALVE_消防` / `EVALVE_喷淋`，XData 和 ExtensionDictionary 可用。
- Phase 6.2.1 真实小样本确认 `TDbPipeFitting` 会出现，当前应归类为 `fitting`，不再归入 `unknown_tianzheng`。

### 本阶段实现

- 新增 `tianzheng.semantic_reader`。
- 新增 `read_tdb_pipe(entity)`，输出 pipe 语义对象。
- 新增 `read_tdb_pipe_valve(entity)`，输出 valve 语义对象。
- 新增 `read_tdb_pipe_fitting(entity)`，输出 fitting 语义对象。
- 新增 `read_tdb_dimension(entity)`，输出 dimension 语义对象。
- 新增 `probe_entity_properties(entity, property_names)`，逐项容错探测属性。
- 新增 `read_selected_tianzheng_semantic_model(document)`，通过 `SelectionSet.SelectOnScreen()` 读取框选对象并生成 `TianzhengSemanticModel`。
- 新增手动脚本：`scripts/manual_tianzheng_semantic_reader_test.py`。
- 新增示例：`examples/tianzheng_semantic_model_sample.json`。
- 新增文档：`docs/tianzheng_semantic_reader_mvp.md`。

### 推断规则

- `TDbPipe` 从 layer 推断系统类型：`PIPE-消防` -> `消防`，`PIPE-喷淋` -> `喷淋`，`PIPE-给水` -> `给水`，`PIPE-排水` -> `排水`。
- `TDbPipeValve` 从 layer 推断系统类型和阀门类型：`VALVE_消防` -> `消防阀门`，`EVALVE_喷淋` -> `喷淋电动阀`。
- `TDbPipeFitting` 从 layer 推断系统类型：`PIPE-消防` -> `消防`，`PIPE-喷淋` -> `喷淋`，`PIPE-给水` -> `给水`，`PIPE-排水` -> `排水`。
- `TDbPipe` 的方向、起点、终点和长度来自 bounding_box 推断，`source = bounding_box_inference`。
- `TDbPipeValve` 的中心点、宽度、高度来自 bounding_box 推断。
- `TDbPipeFitting` 的中心点、宽度、高度来自 bounding_box 推断；`fitting_type_guess` 暂为 `unknown`，不硬判弯头 / 三通 / 接头。

### 重要限制

- bounding_box 推断不等于天正内部真实几何参数。
- `Radius` 可读取时，`diameter_guess = Radius * 2` 只是猜测，不可直接当作真实管径。
- `TDbDimension2` 的文字和测量值只做常见属性探测，读取失败写入 warnings。
- 深度属性探测已扩展 `PipeDN`、`DN`、`NominalDiameter`、`Material`、`Elevation`、`StartPoint`、`EndPoint`、`Center`、`FittingType`、`ValveType` 等字段；每个对象输出 `readable_properties` 和 `failed_properties`。
- 本阶段只读，不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不开发 `create_pipe` / `create_valve`，不进入 Diff 或自动补图。

### 手动测试

运行：

```powershell
python scripts/manual_tianzheng_semantic_reader_test.py
```

脚本会提示用户框选水泵房区域对象，并导出：

```text
examples/tianzheng_semantic_model_sample.json
```

### 测试结果

- 单元测试使用 Fake COM，不依赖真实 AutoCAD / 天正。
- 全量单元测试：`pytest -q` 已通过，结果为 `145 passed`。

## Phase 6.2.2：DN Pipe Diameter Label Recognition + Pipe Association MVP

### 背景结论

- Phase 6.2.1 真实小区域复测中，`TDbPipe.Radius = 1.5`，对应 `diameter_guess = 3.0`。
- 该值明显不能直接当真实 DN 管径。
- 管径应优先来自图纸中的 DN / De / Φ / D 文字或天正管径标注。

### 本阶段实现

- 新增 `tianzheng.diameter_label_reader`。
- 新增 `tianzheng.pipe_label_association`。
- 新增配置：`config/pipe_diameter_patterns.json`。
- 新增手动脚本：`scripts/manual_tianzheng_diameter_association_test.py`。
- 新增示例：`examples/tianzheng_diameter_association_sample.json`。
- 新增文档：`docs/tianzheng_diameter_association_mvp.md`。

### 管径文字识别

当前支持：

- `DN50` / `DN 50` / `dn200`
- `De110` / `De 110`
- `Φ100` / `Φ 100`
- `D100` / `D 100`

标准化示例：

- `DN 200` -> `DN200`
- `dn200` -> `DN200`
- `De 110` -> `De110`
- `Φ 100` -> `Φ100`

### 文字属性探测

疑似文字和标注对象会尝试读取：

- `TextString`
- `Contents`
- `Text`
- `MText`
- `TextOverride`
- `DimensionText`
- `PrimaryText`
- `Measurement`
- `Label`
- `Name`
- `Value`

成功字段写入 `readable_text_properties`，失败字段写入 `failed_text_properties`。COM tuple / array 会转为 JSON list。

### 管径与管线候选关联

当前关联依据：

- label position / bounding_box center。
- pipe inferred line。
- label center 到 pipe inferred line 的距离。
- label 位于一定容差内时进入 `diameter_candidates`。

所有关联默认：

- `selected_diameter = null`
- `status = need_user_confirmation`

即使只有一个高置信候选，也不自动确定最终管径。

### 安全边界

- 本阶段只识别、候选关联、导出预览。
- 不写入 CAD。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不做 Diff、不进入自动补图。

### 测试结果

- 单元测试使用 Fake COM，不依赖真实 AutoCAD / 天正。
- 全量单元测试：`pytest -q` 已通过，结果为 `161 passed`。
## Phase 6.2.2.1：ActiveDocument Resolution + COM Collection Compatibility 修复

### 背景

真实运行 `python scripts/manual_tianzheng_diameter_association_test.py` 时，天正环境已检测成功，但 `active_document` 输出为 `null`，随后脚本把错误 COM 对象传入语义读取流程，导致访问 `document.SelectionSets` 时报错：

```text
AttributeError: <unknown>.SelectionSets
```

同一次日志还确认 `MenuGroups` 不能直接迭代：

```text
TypeError: This object does not support enumeration
```

### 修复内容

- 新增 `cad.document_resolver`，集中处理 AutoCAD Application 到有效 Document 的解析。
- `resolve_active_document(app)` 会优先校验 `app.ActiveDocument`，失败时遍历 `app.Documents` 回退查找可用图纸。
- Document 校验明确要求：`Name`、`ModelSpace` 或 `PaperSpace`、`SelectionSets`、`Utility`。
- 天正手动脚本在调用 `SelectionSet.SelectOnScreen()` 前，统一使用 `resolve_active_document(app)`，不再直接把 Application 当 Document。
- `tianzheng.environment._menu_group_names()` 改为优先使用 `Count` / `Item()` 读取 COM Collection，并兼容 0 基 / 1 基索引。
- `read_selected_tianzheng_semantic_model(document)` 增加 Document 前置校验，遇到无效对象时返回明确错误，而不是继续访问 `<unknown>.SelectionSets`。
- `manual_tianzheng_object_inspect.py` 保存结果时不再二次读取 `require_active_document()`，避免重新触发错误对象解析。

### 当前结论

- 本修复只处理 COM 对象解析和集合兼容。
- 本修复不写入 CAD。
- 本修复不调用 `TPIPE` / `TDRAIN`。
- 本修复不进入天正绘图 Tool Layer。
- 本修复不进入 Diff 或自动补图。

### 测试结果

- 针对性测试：`pytest -q tests/test_document_resolver.py tests/test_tianzheng_environment.py tests/test_tianzheng_semantic_reader.py` 通过，结果为 `34 passed`。
- 全量测试：`pytest -q` 通过，结果为 `171 passed`。
- 语法检查：`python -m py_compile` 覆盖新增解析器、环境检测、语义读取和相关手动脚本，已通过。

## Phase 6.2.2.2：SelectionSet Empty Selection Handling + Cleanup Fix

### 背景

Document Resolver 真实复测已通过后，脚本可以进入 `SelectionSets`。但当用户没有在 AutoCAD 中选中对象时，原流程会把空选择当作程序异常处理，输出 traceback：

```text
RuntimeError: 未选择任何对象。
```

同时临时 SelectionSet 删除在真实 COM 环境中可能失败：

```text
AttributeError: Add.Delete
```

### 修复内容

- 新增 `tianzheng.selection_utils`。
- 新增 `NoSelectionError`，统一表示用户未选择对象，错误码为 `NO_SELECTION`。
- 新增 `safe_delete_selection_set(document, name, selection_set=None)`，删除临时 SelectionSet 时依次尝试：
  - `selection_set.Delete()`
  - `document.SelectionSets.Item(name).Delete()`
  - 遍历 `SelectionSets` 后按 `Name` 匹配删除
- 删除失败只记录 warning，不中断主流程。
- `read_selected_tianzheng_semantic_model(document)` 和 `read_selected_entities(document)` 在 `Count < 1` 时抛出 `NoSelectionError`，不再抛普通 `RuntimeError`。
- `manual_tianzheng_diameter_association_test.py`、`manual_tianzheng_semantic_reader_test.py`、`manual_tianzheng_selection_reader.py` 已接入重试流程。
- 用户未选择对象时，脚本提示：

```text
No entity selected. Please select objects in AutoCAD and press Enter.
```

并允许按 Enter 重试，或输入 `q / quit` 退出。

### 用户操作提示

脚本会明确提示：

- 请切换到 AutoCAD 窗口，用鼠标框选对象。
- 看到命令行显示“找到 x 个”后，请在 AutoCAD 中按 Enter / 空格 / 右键确认。
- 不要在 PowerShell 中确认选择。

### 当前结论

- 本修复只处理空选择和临时 SelectionSet 清理。
- 本修复保持只读。
- 本修复不写入 CAD。
- 本修复不调用 `TPIPE` / `TDRAIN`。
- 本修复不进入天正绘图 Tool Layer。
- 本修复不进入自动补图。

### 测试结果

- 局部测试：`pytest -q tests/test_tianzheng_selection_reader.py tests/test_tianzheng_semantic_reader.py tests/test_tianzheng_object_inspector.py` 通过，结果为 `48 passed`。
- 全量测试：`pytest -q` 通过，结果为 `176 passed`。
- 语法检查：`python -m py_compile` 覆盖选择工具、语义读取、框选读取和相关手动脚本，已通过。
## Phase 6.2.3：TDbPipe Diameter / Label Deep Probe

### 背景

Phase 6.2.2 中普通 DN / De / Φ / D 文字识别在真实图纸小区域里出现 `diameter_label_count = 0`。用户单独点击疑似 DN 管径文字区域后，实际选中的对象仍然是 `TDbPipe`，并且 XData 中出现：

```json
{
  "types": [1001, 1000],
  "values": ["TG_PIPELABEL_THICK_SHOW", "0"]
}
```

这说明管径文字可能不是独立 `AcDbText` / `AcDbMText`，而是 `TDbPipe` 内部显示字段或天正动态标签。

### 本阶段实现

- 新增 `tianzheng.tdbpipe_deep_probe.probe_tdbpipe(entity)`。
- 新增手动脚本 `scripts/manual_tdbpipe_deep_probe.py`。
- 新增文档 `docs/tdbpipe_deep_probe_mvp.md`。
- 新增示例 `examples/tdbpipe_deep_probe_sample.json`。
- 新增测试 `tests/test_tdbpipe_deep_probe.py`。

### 探测范围

`probe_tdbpipe()` 只读探测：

- `Radius`、`Diameter`、`PipeDiameter`、`PipeDN`、`DN`、`NominalDiameter`、`PipeSize`、`Label`、`PipeLabel`、`TextString`、`Material`、`SystemType`、`PipeType`、`StartPoint`、`EndPoint` 等属性。
- `GetXData("")`、`GetXData(None)` 和常见 RegAppName。
- `GetExtensionDictionary()` 的 keys、对象名、handle 和常见字符串属性。
- `entity._oleobj_.GetTypeInfo()`。
- `dir(entity)` 中包含 Pipe / DN / Diameter / Label / Text / Material / Type / Size 的可疑字段名。

### 当前结论

- `TDbPipe.Radius` 仍然不能当真实 DN 管径。
- `diameter_candidates` 只表示候选，不自动确定最终管径。
- 本阶段只读，不写入 CAD。
- 本阶段不调用 `TPIPE` / `TDRAIN`。
- 本阶段不调用天正绘图命令。
- 本阶段不进入 Diff 或自动补图。

### 测试结果

- 新增单元测试：`pytest -q tests/test_tdbpipe_deep_probe.py` 通过，结果为 `10 passed`。
- 全量测试：`pytest -q` 通过，结果为 `186 passed`。
- 语法检查：`python -m py_compile .\tianzheng\tdbpipe_deep_probe.py .\scripts\manual_tdbpipe_deep_probe.py` 已通过。

## Phase 6.2.3.1：TDbPipe TypeInfo Property Reader

状态：TDbPipe TypeInfo Property Reader：真实 `TDbPipe.DNDiameter` 读取与 DN 标准化已验证。

### 背景

真实 `TDbPipe` 深度探测显示，普通 DN 文字识别不一定能找到独立 `AcDbText` / `AcDbMText`。天正管线对象自身可以暴露 `DNDiameter`、`SysType`、`SElevation`、`EElevation`、`ModelType`、`Label`、`DrawLabel`、`SysLabel`、`Radius`、`Length` 等动态属性。

### 当前实现

- `tianzheng.tdbpipe_deep_probe.probe_tdbpipe()` 已优先读取 `DNDiameter`。
- `DNDiameter` 标准化规则为：`100 -> DN100`、`"100" -> DN100`、`"DN100" -> DN100`。
- `probe_tdbpipe()` 输出 `dn_diameter_raw`、`normalized_diameter`、`diameter_source`、`diameter_confidence`。
- `read_tdb_pipe()` 已将管径写入语义模型的 `diameter` 字段。
- `Radius` 只保留为 `display_radius`，不再生成 `diameter_guess`。
- `SysType` 作为 `system_type_raw` 保留；`system_type` 仍以 layer 推断为准。冲突时只记录 warning。
- `SElevation` / `EElevation` 写入 `elevation.start` / `elevation.end`。
- 手动深度探测脚本会突出输出 `DNDiameter`、`normalized_diameter`、`SysType`、`SElevation`、`EElevation`、`ModelType`、`Label`、`DrawLabel`、`SysLabel`、`Radius`、`Length`。

### 边界

本阶段只读，不写 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不进入 Diff、自动补图或 Tool Layer。

### 真实测试结果

用户已在真实天正给排水 T30 V1.0 图纸中完成复测：

1. 点击 `PIPE-给水` 的 `TDbPipe`：
   - `DNDiameter`：历史真实值已脱敏
   - `normalized_diameter`：历史真实值已脱敏
   - `diameter_source = TDbPipe.DNDiameter`
   - `SysType`：历史真实值已脱敏
   - `SElevation`：历史真实值已脱敏
   - `EElevation`：历史真实值已脱敏

2. 点击 `PIPE-消防` 的 `TDbPipe`：
   - `DNDiameter`：历史真实值已脱敏
   - `normalized_diameter`：历史真实值已脱敏
   - `diameter_source = TDbPipe.DNDiameter`
   - `SysType`：历史真实值已脱敏
   - `SElevation`：历史真实值已脱敏
   - `EElevation`：历史真实值已脱敏

结论：`TDbPipe.DNDiameter` 已被真实验证为当前最可靠的管径来源。`Radius` 只保留为 `display_radius`，不再作为真实管径或 `diameter_guess`。

## Phase 6.3：Semantic Diff Engine（只读）

### 当前实现

新增只读语义差异模块：

- `semantic_diff.matcher`
- `semantic_diff.diff_engine`

输入：

- `CurrentSemanticModel`
- `ReferenceSemanticModel`

输出严格 `DiffResult`：

```json
{
  "add_pipe": [],
  "remove_pipe": [],
  "modify_pipe": [],
  "move_pipe": [],
  "diameter_mismatch": [],
  "system_mismatch": []
}
```

### 匹配策略

- 几何相似度优先。
- `system_type` 相同会提高匹配优先级。
- `layer` 相同会提高匹配优先级。
- 多个候选时使用距离最近原则。

为保证能检测 `system_mismatch`，系统类型不同但几何高度相似的管线仍允许形成 match pair，然后输出系统类型冲突。

### 管径规则

管径比较只使用 `diameter.normalized`，该字段来自已经真实验证过的 `TDbPipe.DNDiameter`。

禁止使用：

- `Radius`
- `display_radius`
- `Radius * 2`
- `diameter_guess`

### 边界

本阶段只读，不写 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不生成执行队列，不进入自动补图。

当前 MVP 只输出 pipe 差异。valve / fitting / text label 后续再扩展。

## Phase 6.4：Pipe Network Graph Builder

### 当前实现

新增只读拓扑构建模块：

- `pipe_network.models`
- `pipe_network.graph_builder`

输入为已有 `SemanticModel`，包括：

- `TDbPipe`
- `TDbPipeValve`
- `TDbPipeFitting`

输出为 `PipeNetworkGraph`：

```json
{
  "nodes": [],
  "edges": [],
  "systems": [],
  "subgraphs": []
}
```

### 构建规则

- `TDbPipe` 的 `start_point` / `end_point` 生成节点。
- 距离在 `node_tolerance` 内的端点合并为同一个节点。
- 每个 `TDbPipe` 生成一条 edge。
- `TDbPipeValve` / `TDbPipeFitting` 使用 center 点贴近并入附近节点。
- 系统按 `system_type` 汇总。
- `subgraphs` 按系统类型生成连通分量。

### 管径规则

edge 的 `diameter` 只来自 `diameter.normalized`，也就是已真实验证的 `TDbPipe.DNDiameter` 标准化结果。

不使用 `Radius`、`display_radius`、`Radius * 2` 或 `diameter_guess`。

### 边界

本阶段只读，不写 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令，不执行 Diff，不生成执行队列，不进入自动补图。

### 已知限制

当前拓扑来自 `inferred_geometry` / `bounding_box` 推断，不等于天正内部真实连接拓扑。valve / fitting 当前按中心点贴近节点处理，尚未解析多端口或真实连接方向。

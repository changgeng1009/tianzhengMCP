# Phase 6.2：Tianzheng Object Semantic Reader MVP

## 目标

Phase 6.0 已确认 Python / MCP 连接的是由天正给排水 T30 V1.0 启动的 AutoCAD 2026。Phase 6.1 已确认用户可以通过 `SelectionSet.SelectOnScreen()` 选择天正对象，并读取对象的 `handle`、`object_name`、`layer`、`bounding_box` 等基础诊断信息。

本阶段目标是把已确认可识别的天正对象转换为结构化语义对象：

- `TDbPipe` -> `pipe`
- `TDbPipeValve` -> `valve`
- `TDbPipeFitting` -> `fitting`
- `TDbDimension2` -> `dimension`

本阶段只读，不修改 CAD，不调用天正绘图命令。

## 严格边界

- 不写入 CAD。
- 不修改或删除对象。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不开发 `create_pipe` / `create_valve`。
- 不做 CAD-to-CAD Diff 或 ROI Diff。
- 不做自动补图。
- 不批量分解或 `Explode` 天正对象。
- 不复制、导入或绑定 Reference DWG。

允许删除的只有临时 SelectionSet，不是 CAD 图元。

## 核心模块

### `tianzheng/semantic_reader.py`

主要函数：

```python
read_tdb_pipe(entity)
read_tdb_pipe_valve(entity)
read_tdb_pipe_fitting(entity)
read_tdb_dimension(entity)
read_semantic_entity(entity)
read_selected_tianzheng_semantic_model(document)
probe_entity_properties(entity, property_names)
```

### `scripts/manual_tianzheng_semantic_reader_test.py`

手动脚本流程：

1. 连接当前 AutoCAD。
2. 检测天正 T30 环境。
3. 提示用户框选水泵房区域对象。
4. 读取选中对象。
5. 输出语义统计。
6. 输出 object_name top 20。
7. 输出 semantic_type 统计。
8. 导出 `examples/tianzheng_semantic_model_sample.json`。

## TianzhengSemanticModel

```json
{
  "source": "tianzheng_semantic_reader",
  "active_document": "xxx.dwg",
  "selection_count": 0,
  "entities": [],
  "summary": {
    "total": 0,
    "pipe": 0,
    "valve": 0,
    "fitting": 0,
    "dimension": 0,
    "text": 0,
    "block": 0,
    "unknown_tianzheng": 0
  }
}
```

## Pipe 语义读取

`TDbPipe` 当前读取：

- handle
- object_name
- layer
- system_type
- bounding_box
- Radius
- XData
- ExtensionDictionary keys

`system_type` 从 layer 推断：

- `PIPE-消防` -> `消防`
- `PIPE-喷淋` -> `喷淋`
- `PIPE-给水` -> `给水`
- `PIPE-排水` -> `排水`
- 无法判断 -> `unknown`

`inferred_geometry` 来自 bounding_box：

- `x1 == x2` -> `vertical`
- `y1 == y2` -> `horizontal`
- x/y 都有差值 -> `diagonal`
- x/y 都无差值 -> `point_like`

注意：起点、终点和长度来自 `bounding_box_inference`，不等于天正内部真实管线参数。

## Valve 语义读取

`TDbPipeValve` 当前读取：

- handle
- object_name
- layer
- system_type
- valve_type_guess
- bounding_box
- center / width / height
- XData
- ExtensionDictionary keys

推断规则：

- `VALVE_消防` -> `消防阀门`
- `EVALVE_喷淋` -> `喷淋电动阀`
- 无法判断 -> `unknown`

中心点、宽度、高度来自 bounding_box 推断。

## Fitting 语义读取

真实小样本已确认 `TDbPipeFitting` 会出现在天正给排水 T30 图纸中，当前归类为：

```json
{
  "semantic_type": "fitting",
  "object_name": "TDbPipeFitting"
}
```

`TDbPipeFitting` 当前读取：

- handle
- object_name
- layer
- system_type
- fitting_type_guess
- bounding_box
- center / width / height
- XData
- ExtensionDictionary keys
- readable_properties
- failed_properties

`system_type` 继续从 layer 推断：

- `PIPE-消防` -> `消防`
- `PIPE-喷淋` -> `喷淋`
- `PIPE-给水` -> `给水`
- `PIPE-排水` -> `排水`
- 无法判断 -> `unknown`

`fitting_type_guess` 当前默认为 `unknown`。除非后续发现可靠属性，不硬判弯头、三通或接头。

中心点、宽度、高度来自 bounding_box 推断，只是几何近似。

## Dimension 语义读取

`TDbDimension2` 当前尝试读取：

- `TextOverride`
- `TextString`
- `Measurement`
- `DimensionText`
- `PrimaryText`
- `Rotation`
- `StyleName`

读取失败不会中断，会写入 `diagnostic.warnings`。

## 深度属性探测

`probe_entity_properties(entity, property_names)` 已扩展属性探测范围，包括：

- `Radius`
- `Diameter`
- `PipeDiameter`
- `PipeDN`
- `DN`
- `NominalDiameter`
- `PipeType`
- `SystemType`
- `Material`
- `Elevation`
- `StartPoint`
- `EndPoint`
- `Center`
- `Position`
- `Location`
- `Rotation`
- `Angle`
- `Direction`
- `Width`
- `Height`
- `Length`
- `Name`
- `Type`
- `FittingType`
- `ValveType`
- `TextString`
- `TextOverride`
- `Measurement`
- `StyleName`
- `EffectiveName`
- `InsertionPoint`
- `ScaleFactor`
- `XScaleFactor`
- `YScaleFactor`
- `ZScaleFactor`

每个对象都会输出 `readable_properties` 和 `failed_properties`。COM tuple / array 会转换为 JSON 可序列化 list。

## Radius 与管径限制

当前如果 `TDbPipe.Radius` 可读取，会生成：

```json
{
  "radius": 50.0,
  "diameter_guess": 100.0,
  "diameter_guess_source": "radius_times_2_guess"
}
```

`diameter_guess` 只是由 `Radius * 2` 得到的猜测，不能直接当作真实管径。真实管径还需要后续结合天正属性、标注文字或业务规则验证。

## 测试

单元测试使用 Fake COM，不依赖真实 AutoCAD / 天正：

```powershell
pytest -q
```

当前结果：

```text
145 passed
```

## 后续预留

后续可以基于 `TianzhengSemanticModel` 做：

- 局部 current/reference Diff。
- ExecutionPlan Preview。
- 天正对象更细粒度语义分类。
- 管径文字与管线的关联确认。

## Phase 6.2.3.1 更新：TDbPipe 管径语义读取

`read_tdb_pipe(entity)` 已接入 `TDbPipe.DNDiameter` 读取结果，并将其写入语义模型的 `diameter` 字段：

```json
{
  "diameter": {
    "raw": 100,
    "normalized": "DN100",
    "source": "TDbPipe.DNDiameter",
    "confidence": 0.95,
    "requires_confirmation": false
  }
}
```

标准化规则：

- `100` -> `DN100`
- `"100"` -> `DN100`
- `"DN100"` -> `DN100`

如果 `DNDiameter` 读取失败或无法标准化，则 `normalized = null`、`confidence = 0.0`、`requires_confirmation = true`。读取失败会保留在 `properties.failed_properties` 中。

`Radius` 不再被转换为 `diameter_guess`。当前只作为 `properties.display_radius` 保存，用于诊断显示，不代表真实管径。

语义读取同时保留：

- `system_type`：继续来自 layer 推断。
- `system_type_raw`：来自 `TDbPipe.SysType`，仅作为原始属性记录。
- `elevation.start` / `elevation.end`：来自 `SElevation` / `EElevation`。
- `properties.Length`、`ModelType`、`Label`、`DrawLabel`、`SysLabel` 等可读属性。

如果 `SysType` 与 layer 推断结果不一致，只记录 warning，不覆盖 `system_type`。本阶段仍然只读，不写 CAD，不调用天正绘图命令。

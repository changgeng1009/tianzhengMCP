# Phase 5：Real Current CAD Reader MVP

## 定位

本阶段只读取当前已经打开的 AutoCAD 图纸，建立真实 `CurrentCADModel` JSON，用于后续 Diff Engine。

本阶段严格只读：

- 不写入 CAD
- 不修改 CAD
- 不删除 CAD 对象
- 不调用天正命令
- 不开发自动补图
- 不开发 Agent / Monitor

## 读取链路

```text
AutoCAD 当前图纸
  -> ModelSpace / PaperSpace
  -> 基础 CAD 对象解析
  -> CurrentCADModel JSON
  -> 后续 Diff Engine
```

## 支持对象

当前 MVP 支持读取：

- `AcDbLine` -> `line`
- `AcDbPolyline` / `AcDb2dPolyline` / `AcDb3dPolyline` -> `polyline`
- `AcDbCircle` -> `circle`
- `AcDbArc` -> `arc`
- `AcDbText` -> `text`
- `AcDbMText` -> `mtext`
- `AcDbBlockReference` -> `block_reference`
- ObjectName 中包含 `Dimension` 的对象 -> `dimension`

无法解析的对象会降级为：

```text
unknown_cad_entity
```

并保留：

- `handle`
- `object_name`
- `layer`
- `bounding_box`
- `confidence`
- `reason`

## 输出结构

输出对齐 Phase 3 的 `CurrentCADModel`：

```json
{
  "source": {
    "kind": "current_autocad",
    "active_document": "test.dwg"
  },
  "entities": [
    {
      "id": "2CF",
      "handle": "2CF",
      "type": "line",
      "object_name": "AcDbLine",
      "layer": "0",
      "geometry": {
        "coordinate_system": "cad_world",
        "points": [
          {
            "x": 0.0,
            "y": 0.0,
            "coordinate_system": "cad_world"
          }
        ]
      },
      "confidence": 1.0,
      "status": "Confirmed",
      "source": "current_autocad"
    }
  ]
}
```

CAD 专用字段也保留在实体顶层和 `properties` 中，方便后续 Diff 和执行阶段追踪原始对象。

## MCP Tools

新增只读工具：

```text
read_current_drawing()
read_selected_entities()
summarize_current_drawing()
```

`read_selected_entities()` 在没有选择对象时返回空选择集，不报错。

## 手动测试

运行前：

1. 手动打开 AutoCAD 2026。
2. 打开一个测试 DWG。
3. 确认 AutoCAD 当前不处于未结束命令状态。

运行：

```powershell
python scripts/manual_read_current_drawing_test.py
```

脚本会：

1. 连接当前 AutoCAD。
2. 输出对象统计。
3. 读取当前图纸。
4. 导出 `examples/current_cad_model_from_real_sample.json`。
5. 不修改 CAD。

## 已知限制

- 天正对象当前不会解析为专业给排水语义，可能降级为 block 或 `unknown_cad_entity`。
- 复杂 Dimension 只读取基础属性，未做标注语义拆解。
- Polyline 曲线拟合、bulge 等高级几何暂未展开。
- 当前不做参考 DWG 同步。
- 当前不进入自动补图流程。

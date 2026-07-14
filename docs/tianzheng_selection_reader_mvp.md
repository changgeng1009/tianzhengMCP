# Phase 6.1.2：Selected Region / Selected Objects Reader for Tianzheng DWG

## 目标

真实水泵房 DWG 通常不是单独一张水泵房图，里面还包含建筑底图、图框、其他区域、其他专业对象和大量无关内容。

因此本阶段不读取整张 DWG，不做整图 Diff，而是让用户在天正给排水 T30 V1.0 启动的 AutoCAD 中手动框选目标区域对象。程序只读取框选对象，并输出 `SelectedCADModel`。

## 严格边界

- 只读框选对象。
- 不读取整张 DWG。
- 不写入 CAD。
- 不修改或删除 CAD 实体。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不做 CAD-to-CAD Diff。
- 不复制、导入 Reference DWG，不绑定 Xref。
- 不进入自动补图。

允许删除的只有临时 SelectionSet，不是 CAD 图元。

## 核心模块

### `tianzheng/selection_reader.py`

核心函数：

```python
read_selected_entities(document)
```

流程：

1. 删除同名临时 SelectionSet。
2. 创建 `__TianzhengSelectionReaderTemp__`。
3. 调用 `SelectionSet.SelectOnScreen()`。
4. 遍历用户框选的所有对象。
5. 对每个对象调用 `inspect_entity(entity)`。
6. 输出 `SelectedCADModel`。
7. 删除临时 SelectionSet。

### `scripts/manual_tianzheng_selection_reader.py`

手动脚本流程：

1. 连接当前 AutoCAD。
2. 检测天正 T30 环境。
3. 输出 active document。
4. 提示用户在 CAD 中框选水泵房区域对象。
5. 读取 SelectionSet 中所有对象。
6. 输出对象统计。
7. 导出 `examples/selected_tianzheng_model_sample.json`。

## SelectedCADModel 结构

```json
{
  "source": "selected_tianzheng_entities",
  "active_document": "xxx.dwg",
  "selection_count": 1,
  "entities": [],
  "summary": {
    "total": 1,
    "line": 1,
    "polyline": 0,
    "block_reference": 0,
    "text": 0,
    "mtext": 0,
    "dimension": 0,
    "proxy": 0,
    "tianzheng_like": 0,
    "unknown": 0
  }
}
```

每个实体至少包含：

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

完整 `inspect_entity()` 结果保留在 `inspection` 字段中，便于后续语义分析。

## 输出诊断

手动脚本会输出：

- active document
- 天正环境检测摘要
- selection_count
- object_name top 20
- layer top 20
- proxy 数量
- tianzheng_like 数量
- unknown 数量
- 前 20 个对象摘要

## 测试

单元测试使用 Fake COM，不依赖真实 AutoCAD / 天正：

```powershell
pytest -q
```

当前结果：

```text
123 passed
```

## 已知限制

- 当前不判断框选区域是否完整，只读取用户实际选中的对象。
- 当前不做天正语义分类，只保留对象检查诊断结果。
- 如果天正对象在 COM 中表现为 Proxy，当前只标记并保留原始诊断，不尝试分解。
- 当前不把 SelectedCADModel 接入 Diff 或执行队列。

## 后续预留

后续可以基于 SelectedCADModel 继续做：

- 天正对象语义分析。
- 局部 Reference / Current Diff。
- 补图计划预览。
- Proxy 降级处理。

# Phase 6.2.2：DN Pipe Diameter Label Recognition + Pipe Association MVP

## 目标

真实测试已确认 `TDbPipe.Radius = 1.5` 时，`diameter_guess = 3.0` 明显不能直接当真实 DN 管径。

因此本阶段新增 DN / De / Φ / D 管径文字识别，并把管径文字与附近的 `TDbPipe` 建立候选关联。

本阶段只做识别、候选关联和导出预览，不写入 CAD，不调用天正绘图命令。

## 严格边界

- 不写入 CAD。
- 不修改或删除对象。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不开发 `create_pipe` / `create_valve`。
- 不做 CAD-to-CAD Diff 或 ROI Diff。
- 不批量分解或 `Explode` 天正对象。
- 不导入、复制或绑定 Reference DWG。

## 新增模块

### `tianzheng/diameter_label_reader.py`

负责识别管径文字：

- `DN50`
- `DN 50`
- `dn200`
- `De 110`
- `Φ 100`
- `D 100`

标准化规则：

- `DN 200` -> `DN200`
- `dn200` -> `DN200`
- `De 110` -> `De110`
- `Φ 100` -> `Φ100`

会探测文字属性：

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

读取失败不会中断，会写入 `failed_text_properties`。

### `tianzheng/pipe_label_association.py`

负责把管径标签与附近管线建立候选关联。

关联依据：

- label bounding_box / center。
- pipe inferred line。
- label center 到 pipe inferred line 的距离。
- 默认只生成 candidates，不写入最终管径。

输出中 `selected_diameter` 默认始终为 `null`，`status` 默认 `need_user_confirmation`。

## 配置

新增：

```text
config/pipe_diameter_patterns.json
```

当前配置：

```json
{
  "patterns": [
    "DN\\s*\\d+",
    "De\\s*\\d+",
    "D\\s*\\d+",
    "Φ\\s*\\d+"
  ]
}
```

## 手动脚本

```powershell
python scripts/manual_tianzheng_diameter_association_test.py
```

流程：

1. 连接天正 AutoCAD。
2. 检测天正环境。
3. 框选包含管线和 DN / De / Φ 管径文字的区域。
4. 生成 `TianzhengSemanticModel`。
5. 提取管径文字。
6. 生成 `PipeDiameterAssociationModel`。
7. 导出 `examples/tianzheng_diameter_association_sample.json`。

## 输出结构

```json
{
  "source": "tianzheng_diameter_association",
  "active_document": "xxx.dwg",
  "selection_count": 0,
  "summary": {
    "pipes": 0,
    "diameter_labels": 0,
    "associations": 0,
    "unmatched_pipes": 0,
    "unmatched_labels": 0,
    "need_user_confirmation": 0
  },
  "diameter_labels": [],
  "pipe_associations": []
}
```

## 关键限制

- `TDbPipe.Radius` 不能直接当真实 DN 管径。
- 管径应优先来自图纸文字 / 管径标注。
- 当前只建立候选关联，不自动确定最终管径。
- 即使只有一个高置信候选，也保持 `selected_diameter = null`。
- 用户确认后，后续阶段才允许把 candidate 提升为 selected diameter。

## 测试

```powershell
pytest -q
```

当前结果：

```text
161 passed
```

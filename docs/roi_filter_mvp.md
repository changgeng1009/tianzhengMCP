# Phase 5.5.1：ROI Region Filter MVP

## 为什么不能直接整图 Diff

真实建筑 DWG 往往包含完整建筑平面、图框、标题栏、其他专业对象和多个局部大样图。

如果直接对整张 Reference DWG 和 Current DWG 做 CAD-to-CAD Diff，会产生大量无关差异，甚至把其他区域对象误判为水泵房需要补充的内容。

因此真实图纸必须先选择目标区域，再只对 ROI 内对象建模和 Diff。

## 本阶段目标

```text
Reference DWG
  -> Reference ROI
  -> Reference ROI Model

Current DWG
  -> Current ROI
  -> Current ROI Model

Reference ROI Model + Current ROI Model
  -> CAD-to-CAD Diff
  -> ExecutionPlan Preview
```

本阶段仍然只读，不写 CAD。

## ROI 数据结构

```json
{
  "id": "pump_room_reference_roi",
  "name": "水泵房大样图区域",
  "coordinate_system": "cad_world",
  "min_x": 0,
  "min_y": 0,
  "max_x": 10000,
  "max_y": 8000
}
```

当前只支持 `cad_world` 坐标。

## 保留规则

对象满足任一条件即保留：

1. `bounding_box` 与 ROI 相交。
2. entity center 在 ROI 内。
3. `geometry.points` 中有点在 ROI 内。
4. text insertion point / position 在 ROI 内。

过滤结果包含：

- `kept_entities`
- `excluded_entities_count`
- `roi_summary`

## 手动输入 ROI

`scripts/manual_reference_dwg_diff_test.py` 已增强为 ROI 流程：

1. 列出打开的 Documents。
2. 用户选择 current document。
3. 用户选择 reference document。
4. 用户输入 current ROI。
5. 用户输入 reference ROI。
6. 只保留 ROI 内对象。
7. 对 ROI 内模型做 CAD-to-CAD Diff。
8. 输出 ExecutionPlan Preview。
9. 不执行 CAD 写入。

## 辅助定位

新增：

```python
find_text_entities_by_keyword(model, keyword)
```

例如搜索：

```text
水泵房大样图
```

返回匹配文字的 handle 和位置，帮助用户人工确定 ROI。

当前不自动确定 ROI。

## 后续方向

后续可以通过图名、视口、图框、标题文字和块边界自动识别 ROI，但不属于当前阶段。

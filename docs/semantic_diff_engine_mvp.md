# Phase 6.3：Semantic Diff Engine MVP

## 目标

本阶段实现只读的 CAD-to-CAD Semantic Diff Engine。

输入为：

- `CurrentSemanticModel`
- `ReferenceSemanticModel`

输出为严格结构化的 `DiffResult`：

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

## 严格边界

- 不写入 CAD。
- 不修改 CAD。
- 不删除 CAD 对象。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不生成执行队列。
- 不进入自动补图。

本阶段只比较语义模型并输出差异。

## 匹配规则

当前 MVP 只对 `semantic_type = pipe` 的 `TDbPipe` 做差异输出。

匹配依据：

1. 几何相似度优先。
2. `system_type` 相同时优先级更高。
3. `layer` 相同时优先级更高。
4. 多个候选时使用距离最近原则。

为保证能识别 `system_mismatch`，系统类型不同但几何高度相似的管线仍允许形成 match pair，然后输出系统类型冲突。

## 差异分类

- `add_pipe`：reference 中存在，current 中不存在。
- `remove_pipe`：current 中存在，reference 中不存在。只读建议，不允许自动执行。
- `modify_pipe`：匹配成功，但属性不同。
- `move_pipe`：匹配成功，但几何偏移超过 `move_tolerance`。
- `diameter_mismatch`：管径不一致，严重级别为 `high`。
- `system_mismatch`：系统类型不一致，严重级别为 `high`。

## 管径规则

管径比较只使用 `diameter.normalized`，该字段来自真实验证过的 `TDbPipe.DNDiameter`。

不使用：

- `Radius`
- `display_radius`
- `Radius * 2`
- `diameter_guess`

示例：

```json
{
  "pipe_handle": "CUR-P-001",
  "reference_pipe_handle": "REF-P-001",
  "current": "DN100",
  "reference": "DN200",
  "severity": "high"
}
```

## 模块

- `semantic_diff.matcher`
  - 负责抽取管线实体、几何点、计算距离、选择最近匹配。
- `semantic_diff.diff_engine`
  - 负责生成严格 `DiffResult`。

## 当前限制

- MVP 只输出 pipe 相关差异。
- valve / fitting / text label 暂不进入最终 DiffResult 数组。
- 几何来自 `inferred_geometry` / `bounding_box`，不是天正内部真实拓扑。
- 本阶段不判断管线连接关系。
- 本阶段不生成 CAD 写入计划。

## 测试

单元测试使用纯 JSON / Fake 数据，不依赖真实 AutoCAD 或天正：

```powershell
pytest -q tests/test_semantic_diff_engine.py
```

# Phase 5.5：CAD-to-CAD Diff MVP

## 定位

本阶段比较 `ReferenceCADModel` 和 `CurrentCADModel`，输出增量 Diff，并生成 `ExecutionPlan Preview`。

默认不执行 CAD 写入。

## Diff 输出

只允许输出：

- `add`
- `modify`
- `move`
- `delete_suggestion`

禁止输出：

- `copy_all`
- `paste_all`
- `import_reference_dwg`
- `rebuild_all`
- `delete_all`

## 匹配策略

当前 MVP 使用保守匹配：

- 实体类型必须一致。
- 几何点在 tolerance 内才视为同一对象。
- 文字对象按位置匹配，内容不同输出 `modify`。
- Reference 中存在但 Current 中缺失，输出 `add`。
- Current 中存在但 Reference 中缺失，输出 `delete_suggestion`。

## ExecutionPlan Preview

DiffResult 可转换为 ExecutionPlan Preview：

- `add` -> `add_line` / `add_polyline` / `add_text`
- `modify` -> `modify_entity`
- `move` -> `move_entity`
- `delete_suggestion` -> 只预览，不可执行

本阶段只生成 Preview，不调用执行工具，不写 CAD。

## 限制

- 当前不复制 Reference DWG 对象。
- 当前不导入 Reference DWG。
- 当前不绑定 Xref。
- 当前不处理天正专业对象语义。
- 当前不进入自动补图完整流程。

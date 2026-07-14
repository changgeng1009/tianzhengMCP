# Phase 5.5：Pipe Diameter Extraction MVP

## 定位

本阶段只从 Reference DWG 的 `Text` / `MText` / `Dimension` 中识别管径文字，不推断它属于哪条管线。

如果管径文字与管线关联不明确，必须标记：

```text
Need User Confirmation
```

## 支持格式

当前支持：

- `DN50`
- `DN65`
- `DN75`
- `DN80`
- `DN100`
- `DN150`
- `DN200`
- `DN250`
- `DN300`
- `De110`
- `De160`

标准化示例：

- `DN 200` -> `DN200`
- `DN200` -> `DN200`
- `De 110` -> `De110`

## 输出

```json
{
  "entity_id": "RT1",
  "handle": "RT1",
  "raw_text": "DN 200",
  "diameter": "DN200",
  "confidence": 0.9,
  "status": "Need User Confirmation",
  "reason": "Diameter text recognized, but pipe association is not determined in Phase 5.5."
}
```

## 限制

- 当前不做管径与管线自动绑定。
- 当前不识别天正专业对象语义。
- 当前不根据经验补全缺失管径。

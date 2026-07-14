# Phase 17 视觉模板库说明

Phase 17 增加喷头、阀门、管件、图例模板库结构，以及 DN/De/Φ 管径解析、系统类型分类、文本语义抽取和模板识别评估。

## 重要边界

- 默认模板是 metadata 模板，不代表真实图片模板已存在。
- 没有真实模板图片时，模板必须 `enabled=false`。
- 无模板、无 OCR、无 OpenCV 时必须安全降级。
- 模板匹配结果必须包含 `confidence`、`method`、`template_id`。
- 低置信度结果不得进入自动补图依据。

## Confidence Gate

- `< 0.60`：丢弃，不进入有效 symbol。
- `0.60 - 0.85`：review symbol。
- `>= 0.85`：high confidence symbol。

## 可扩展点

- 将真实喷头、阀门、管件、图例图片加入模板库 JSON。
- 使用 `VisionSampleRegistry` 收集真实样本。
- 使用 `evaluate_template_detection()` 对模板识别效果做 precision / recall 评估。

## CVVisionProvider 接入

`CVVisionProvider` 支持：

```python
CVVisionProvider(
    use_template_library=True,
    template_store=store,
    template_match_threshold=0.85,
)
```

未传 `template_store` 时旧行为保持不变。

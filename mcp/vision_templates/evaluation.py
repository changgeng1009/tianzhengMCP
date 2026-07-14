from __future__ import annotations

from mcp.vision_templates.models import ClassifiedSymbol, TemplateEvaluationResult


def evaluate_template_detection(
    detected: list[ClassifiedSymbol],
    expected: list[dict],
    options: dict | None = None,
) -> TemplateEvaluationResult:
    options = dict(options or {})
    tolerance = float(options.get("bbox_iou_threshold", 0.2))
    warnings: list[str] = []
    if not expected:
        warnings.append("expected sample list is empty")
    matched_expected: set[int] = set()
    true_positive = 0
    for symbol in detected:
        for index, expected_item in enumerate(expected):
            if index in matched_expected:
                continue
            if symbol.symbol_type == expected_item.get("symbol_type") and _bbox_iou(symbol.bbox, expected_item.get("bbox", [])) >= tolerance:
                true_positive += 1
                matched_expected.add(index)
                break
    false_positive = max(0, len(detected) - true_positive)
    false_negative = max(0, len(expected) - true_positive)
    precision = true_positive / len(detected) if detected else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    confidence_average = sum(symbol.confidence for symbol in detected) / len(detected) if detected else 0.0
    return TemplateEvaluationResult(
        sample_id=str(options.get("sample_id", "sample")),
        detected_count=len(detected),
        expected_count=len(expected),
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=round(precision, 4),
        recall=round(recall, 4),
        confidence_average=round(confidence_average, 4),
        warnings=warnings,
    )


def _bbox_iou(a: list[float], b: list[float]) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    denom = area_a + area_b - inter
    return inter / denom if denom else 0.0


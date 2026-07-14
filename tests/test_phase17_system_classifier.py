from __future__ import annotations


def test_classify_system_text_supports_chinese_keywords() -> None:
    from mcp.vision_templates.system_classifier import classify_system_text

    assert classify_system_text("自动喷水灭火系统").system_type == "sprinkler"
    assert classify_system_text("消火栓管").system_type == "fire_hydrant"
    assert classify_system_text("生活给水").system_type == "domestic_water"
    assert classify_system_text("污水排水").system_type == "drainage"
    unknown = classify_system_text("设备间")
    assert unknown.system_type == "unknown"
    assert unknown.confidence < 0.6


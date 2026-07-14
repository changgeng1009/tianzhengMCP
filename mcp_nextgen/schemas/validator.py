"""无外部依赖的严格 Schema 子集校验器。

只实现本包 Schema 实际使用的关键字。未知关键字不会改变安全决定；类型、必填、
const/enum、长度、数量、pattern、additionalProperties 会严格执行。
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any


class SchemaValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _validate(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, item) for item in expected_types):
            errors.append(f"{path}: 类型应为 {expected_types}")
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 必须等于 {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 不在允许枚举中")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: 字符串过短")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: 字符串过长")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            errors.append(f"{path}: 不匹配 pattern")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}: 必须是带时区的 date-time")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: 小于 minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: 大于 maximum")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: 数组元素不足")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: 数组元素过多")
        if schema.get("uniqueItems"):
            normalized = [repr(item) for item in value]
            if len(set(normalized)) != len(normalized):
                errors.append(f"{path}: 数组元素必须唯一")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{index}]", errors)

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}.{required}: 缺少必填字段")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value).difference(properties))
            for extra in extras:
                errors.append(f"{path}.{extra}: 不允许额外字段")
        for name, child_schema in properties.items():
            if name in value:
                _validate(value[name], child_schema, f"{path}.{name}", errors)


def validate_instance(instance: Any, schema: dict[str, Any]) -> None:
    errors: list[str] = []
    _validate(instance, schema, "$", errors)
    if errors:
        raise SchemaValidationError(errors)

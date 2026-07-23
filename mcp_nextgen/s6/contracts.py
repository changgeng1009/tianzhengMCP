"""S6 结构化普通 AutoCAD 操作合同。

合同完全后端中立且只处理内存数据。它不导入 AutoCAD/COM，也不接受文件路径；
真实 COM 适配必须在显式 L3 synthetic sandbox 门之后消费本计划。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping, Sequence


S6_SCHEMA_VERSION = "1.0.0"
S6_SYNTHETIC_LAYER = "CADAGENT_S6_MVP"
S6_ALLOWED_OPERATIONS = frozenset({
    "CREATE_LINE", "CREATE_CIRCLE", "CREATE_POLYLINE", "CREATE_ARC", "CREATE_RECTANGLE", "CREATE_TEXT", "CREATE_MTEXT",
    "CREATE_BLOCK_DEFINITION", "INSERT_BLOCK_REFERENCE", "QUERY_ENTITIES",
    "MOVE_ENTITY", "COPY_ENTITY", "ROTATE_ENTITY", "SCALE_ENTITY", "DELETE_ENTITY",
    "ENSURE_LAYER", "ENSURE_TEXT_STYLE", "ENSURE_DIMENSION_STYLE",
    "SAVE_SYNTHETIC_DOCUMENT", "CLOSE_SYNTHETIC_DOCUMENT", "REOPEN_SYNTHETIC_DOCUMENT",
})
_ENTITY_KINDS = frozenset({"arc", "rectangle", "text", "mtext", "block_definition", "block_reference", "line", "circle", "polyline"})
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$-]{0,63}$")


class CadOperationValidationError(ValueError):
    """DTO/计划输入不满足 S6 synthetic 合同时抛出。"""


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CadOperationValidationError(f"{name} 必须为数值") from exc
    if not math.isfinite(result) or abs(result) > 100_000:
        raise CadOperationValidationError(f"{name} 必须为合成范围内有限数值")
    return result


def _identifier(value: str, name: str) -> str:
    text = str(value).strip()
    if not _OPERATION_RE.fullmatch(text):
        raise CadOperationValidationError(f"{name} 无效")
    return text


def _name(value: str, name: str) -> str:
    text = str(value).strip()
    if not _NAME_RE.fullmatch(text):
        raise CadOperationValidationError(f"{name} 无效")
    return text


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return format(_finite(value, "几何数值"), ".17g")
    raise CadOperationValidationError("计划包含不支持的值类型")


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        object.__setattr__(self, "z", _finite(self.z, "z"))

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_value(cls, value: Any, name: str = "point") -> "Point3":
        if isinstance(value, Point3):
            return value
        if isinstance(value, Mapping):
            return cls(value.get("x"), value.get("y"), value.get("z", 0.0))
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) in {2, 3}:
            return cls(value[0], value[1], value[2] if len(value) == 3 else 0.0)
        raise CadOperationValidationError(f"{name} 无效")


@dataclass(frozen=True)
class Point2:
    """后端中立二维点；所有 S6 平面图元以毫米为默认工程单位。"""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class Vector3:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "vector.x"))
        object.__setattr__(self, "y", _finite(self.y, "vector.y"))
        object.__setattr__(self, "z", _finite(self.z, "vector.z"))

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass(frozen=True)
class GeometryTolerance:
    """统一的绝对/相对浮点容差；不得使用隐式比较。"""

    absolute: float = 1e-9
    relative: float = 1e-9

    def __post_init__(self) -> None:
        for name in ("absolute", "relative"):
            value = _finite(getattr(self, name), name)
            if value <= 0:
                raise CadOperationValidationError(f"{name} 必须大于 0")
            object.__setattr__(self, name, value)

    def close(self, first: float, second: float) -> bool:
        return math.isclose(_finite(first, "first"), _finite(second, "second"), abs_tol=self.absolute, rel_tol=self.relative)


@dataclass(frozen=True)
class BoundingBox:
    minimum: Point3
    maximum: Point3

    def __post_init__(self) -> None:
        minimum = Point3.from_value(self.minimum, "bbox.minimum")
        maximum = Point3.from_value(self.maximum, "bbox.maximum")
        if minimum.x > maximum.x or minimum.y > maximum.y or minimum.z > maximum.z:
            raise CadOperationValidationError("BoundingBox 最小值不得大于最大值")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    def to_dict(self) -> dict[str, Any]:
        return {"minimum": self.minimum.to_dict(), "maximum": self.maximum.to_dict()}


@dataclass(frozen=True)
class Transformation:
    """明确使用弧度的二维旋转与正比例缩放，不暴露 COM Matrix。"""

    translation: Vector3 = field(default_factory=lambda: Vector3(0.0, 0.0, 0.0))
    rotation_radians: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "translation", Vector3(**self.translation.to_dict()) if isinstance(self.translation, Vector3) else Vector3(**dict(self.translation)))
        object.__setattr__(self, "rotation_radians", _finite(self.rotation_radians, "rotation_radians"))
        scale = _finite(self.scale, "scale")
        if scale <= 0:
            raise CadOperationValidationError("scale 必须大于 0")
        object.__setattr__(self, "scale", scale)

    def to_dict(self) -> dict[str, Any]:
        return {"translation": self.translation.to_dict(), "rotation_radians": self.rotation_radians, "scale": self.scale}


@dataclass(frozen=True)
class LayerSpec:
    name: str
    color_index: int = 7
    linetype: str = "Continuous"
    lineweight: int = -1
    visible: bool = True
    locked: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "layer name"))
        if not isinstance(self.color_index, int) or not 1 <= self.color_index <= 255:
            raise CadOperationValidationError("Layer color_index 必须为 1–255")
        object.__setattr__(self, "linetype", _name(self.linetype, "linetype"))
        if not isinstance(self.lineweight, int):
            raise CadOperationValidationError("lineweight 必须为整数")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "color_index": self.color_index, "linetype": self.linetype, "lineweight": self.lineweight, "visible": self.visible, "locked": self.locked}


@dataclass(frozen=True)
class TextStyleSpec:
    name: str
    font: str = "txt.shx"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "text style"))
        if not self.font or len(self.font) > 255 or any(token in self.font for token in ("\\", "/", ":")):
            raise CadOperationValidationError("TextStyle font 必须是非路径字体名")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "font": self.font}


@dataclass(frozen=True)
class DimensionStyleSpec:
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "dimension style"))

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name}


@dataclass(frozen=True)
class LinetypeSpec:
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "linetype"))


@dataclass(frozen=True)
class LineweightSpec:
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int):
            raise CadOperationValidationError("lineweight 必须为整数")


def _point(value: Any, name: str) -> dict[str, float]:
    return Point3.from_value(value, name).to_dict()


def _validate_geometry(kind: str, geometry: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(geometry)
    if kind == "arc":
        result = {"center": _point(value.get("center"), "center"), "radius": _finite(value.get("radius"), "radius"),
                  "start_angle": _finite(value.get("start_angle"), "start_angle"), "end_angle": _finite(value.get("end_angle"), "end_angle")}
        if result["radius"] <= 0 or math.isclose(result["start_angle"], result["end_angle"], abs_tol=1e-12):
            raise CadOperationValidationError("Arc 半径或角度范围无效")
        return result
    if kind == "rectangle":
        first, second = _point(value.get("corner_a"), "corner_a"), _point(value.get("corner_b"), "corner_b")
        if math.isclose(first["x"], second["x"]) or math.isclose(first["y"], second["y"]):
            raise CadOperationValidationError("Rectangle 不得退化")
        return {"corner_a": first, "corner_b": second}
    if kind in {"text", "mtext"}:
        content_key = "content" if kind == "mtext" else "text"
        content = str(value.get(content_key, ""))
        if not content or len(content) > 4096:
            raise CadOperationValidationError(f"{kind} 内容无效")
        result: dict[str, Any] = {content_key: content, "insertion_point": _point(value.get("insertion_point"), "insertion_point"),
                                  "height": _finite(value.get("height", 100.0), "height"), "rotation": _finite(value.get("rotation", 0.0), "rotation")}
        if result["height"] <= 0:
            raise CadOperationValidationError(f"{kind} height 必须大于 0")
        if kind == "mtext":
            result["width"] = _finite(value.get("width", 1000.0), "width")
            if result["width"] <= 0:
                raise CadOperationValidationError("mtext width 必须大于 0")
        return result
    if kind == "block_definition":
        name = _name(value.get("name", ""), "block name")
        entities = value.get("entities", [])
        if not isinstance(entities, Sequence) or isinstance(entities, (str, bytes)) or not entities:
            raise CadOperationValidationError("BlockDefinition 必须包含实体")
        return {"name": name, "entities": [_canonical(item) for item in entities]}
    if kind == "block_reference":
        scale = _finite(value.get("scale", 1.0), "scale")
        if scale <= 0:
            raise CadOperationValidationError("BlockReference scale 必须大于 0")
        return {"block_name": _name(value.get("block_name", ""), "block_name"), "insertion_point": _point(value.get("insertion_point"), "insertion_point"),
                "rotation": _finite(value.get("rotation", 0.0), "rotation"), "scale": scale}
    if kind == "line":
        start, end = _point(value.get("start"), "start"), _point(value.get("end"), "end")
        if start == end:
            raise CadOperationValidationError("Line 起终点不得相同")
        return {"start": start, "end": end}
    if kind == "circle":
        radius = _finite(value.get("radius"), "radius")
        if radius <= 0:
            raise CadOperationValidationError("Circle radius 必须大于 0")
        return {"center": _point(value.get("center"), "center"), "radius": radius}
    if kind == "polyline":
        raw = value.get("vertices", [])
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 2:
            raise CadOperationValidationError("Polyline vertices 无效")
        return {"vertices": [_point(item, "vertex") for item in raw], "closed": bool(value.get("closed", False))}
    raise CadOperationValidationError(f"未支持实体类型: {kind}")


@dataclass(frozen=True)
class EntitySpec:
    entity_type: str
    geometry: Mapping[str, Any]
    layer: str = S6_SYNTHETIC_LAYER
    style: str | None = None

    def __post_init__(self) -> None:
        kind = str(self.entity_type).lower()
        if kind not in _ENTITY_KINDS:
            raise CadOperationValidationError("entity_type 未支持")
        if self.layer != S6_SYNTHETIC_LAYER:
            raise CadOperationValidationError("S6 只允许专用 synthetic 图层")
        object.__setattr__(self, "entity_type", kind)
        object.__setattr__(self, "geometry", _validate_geometry(kind, self.geometry))
        if self.style is not None:
            object.__setattr__(self, "style", _name(self.style, "style"))

    def to_dict(self) -> dict[str, Any]:
        return {"entity_type": self.entity_type, "geometry": _canonical(self.geometry), "layer": self.layer, "style": self.style}


@dataclass(frozen=True)
class EntitySelector:
    handle: str | None = None
    operation_id: str | None = None
    entity_type: str | None = None
    layer: str | None = None

    def __post_init__(self) -> None:
        if not any((self.handle, self.operation_id, self.entity_type, self.layer)):
            raise CadOperationValidationError("selector 至少需要一个条件")
        if self.operation_id is not None:
            object.__setattr__(self, "operation_id", _identifier(self.operation_id, "selector.operation_id"))
        if self.entity_type is not None and self.entity_type.lower() not in _ENTITY_KINDS:
            raise CadOperationValidationError("selector.entity_type 未支持")
        if self.layer is not None and self.layer != S6_SYNTHETIC_LAYER:
            raise CadOperationValidationError("selector 只能定位 S6 synthetic 图层")

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in {"handle": self.handle, "operation_id": self.operation_id, "entity_type": self.entity_type, "layer": self.layer}.items() if value is not None}


@dataclass(frozen=True)
class CadOperation:
    operation_id: str
    operation: str
    entity: EntitySpec | None = None
    selector: EntitySelector | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _identifier(self.operation_id, "operation_id"))
        operation = str(self.operation).upper()
        if operation not in S6_ALLOWED_OPERATIONS:
            raise CadOperationValidationError("operation 未支持")
        object.__setattr__(self, "operation", operation)
        if (operation.startswith("CREATE_") or operation == "INSERT_BLOCK_REFERENCE") and self.entity is None:
            raise CadOperationValidationError("创建操作需要 entity")
        if operation in {"MOVE_ENTITY", "COPY_ENTITY", "ROTATE_ENTITY", "SCALE_ENTITY", "DELETE_ENTITY"} and self.selector is None:
            raise CadOperationValidationError("变换/删除操作需要 selector")
        params = dict(self.parameters)
        if operation in {"MOVE_ENTITY", "COPY_ENTITY"}:
            params["displacement"] = _point(params.get("displacement"), "displacement")
        if operation == "ROTATE_ENTITY":
            params["base_point"] = _point(params.get("base_point"), "base_point"); params["angle"] = _finite(params.get("angle"), "angle")
        if operation == "SCALE_ENTITY":
            params["base_point"] = _point(params.get("base_point"), "base_point"); params["scale"] = _finite(params.get("scale"), "scale")
            if params["scale"] <= 0: raise CadOperationValidationError("scale 必须大于 0")
        if operation == "ENSURE_LAYER":
            params["layer"] = LayerSpec(**dict(params.get("layer", {}))).to_dict()
        if operation == "ENSURE_TEXT_STYLE":
            params["text_style"] = TextStyleSpec(**dict(params.get("text_style", {}))).to_dict()
        if operation == "ENSURE_DIMENSION_STYLE":
            params["dimension_style"] = DimensionStyleSpec(**dict(params.get("dimension_style", {}))).to_dict()
        object.__setattr__(self, "parameters", _canonical(params))
        object.__setattr__(self, "depends_on", tuple(_identifier(item, "depends_on") for item in self.depends_on))

    def to_dict(self) -> dict[str, Any]:
        return {"operation_id": self.operation_id, "operation": self.operation, "entity": self.entity.to_dict() if self.entity else None,
                "selector": self.selector.to_dict() if self.selector else None, "parameters": dict(self.parameters), "depends_on": list(self.depends_on)}


@dataclass(frozen=True)
class CadOperationPlan:
    job_id: str
    document_token: str
    operations: tuple[CadOperation, ...]
    schema_version: str = S6_SCHEMA_VERSION
    batch_policy: str = "best_effort"
    plan_id: str = ""
    dry_run: bool = False
    expected_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _identifier(self.job_id, "job_id"))
        object.__setattr__(self, "document_token", _identifier(self.document_token, "document_token"))
        operations = tuple(self.operations)
        if not operations:
            raise CadOperationValidationError("operation plan 不得为空")
        ids = [item.operation_id for item in operations]
        if len(ids) != len(set(ids)):
            raise CadOperationValidationError("operation_id 不得重复")
        known = set(ids)
        if any(set(item.depends_on) - known for item in operations):
            raise CadOperationValidationError("depends_on 引用了未知 operation")
        if self.batch_policy not in {"best_effort", "all_or_nothing"}:
            raise CadOperationValidationError("batch_policy 无效")
        plan_id = self.plan_id or f"{self.job_id}.plan"
        object.__setattr__(self, "plan_id", _identifier(plan_id, "plan_id"))
        object.__setattr__(self, "dry_run", bool(self.dry_run))
        object.__setattr__(self, "expected_capabilities", tuple(_identifier(item, "expected_capabilities") for item in self.expected_capabilities))
        object.__setattr__(self, "operations", operations)

    @property
    def plan_hash(self) -> str:
        # 文档 token 由独立 L3 approval/document identity 绑定。将随机生成的
        # ownership token 排除在 hash 外，才能先冻结计划哈希、再 reserve synthetic
        # document 并把其 token 写回计划，避免 reserve ↔ plan_hash 的循环依赖。
        payload = self.to_dict(include_hash=False)
        payload.pop("document_token", None)
        return sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value = {"schema_version": self.schema_version, "plan_id": self.plan_id, "job_id": self.job_id, "document_token": self.document_token,
                 "batch_policy": self.batch_policy, "dry_run": self.dry_run, "expected_capabilities": list(self.expected_capabilities),
                 "operations": [item.to_dict() for item in self.operations]}
        if include_hash: value["plan_hash"] = self.plan_hash
        return value

    def to_execution_tasks(self) -> list[dict[str, Any]]:
        return [{"task_id": item.operation_id, "kind": "s6_cad_operation", "payload": item.to_dict(), "depends_on": list(item.depends_on)} for item in self.operations]


@dataclass(frozen=True)
class EntitySnapshot:
    handle: str
    entity_type: str
    layer: str
    geometry: Mapping[str, Any]
    operation_id: str
    deleted: bool = False

    @property
    def fingerprint(self) -> str:
        return sha256(canonical_json({"entity_type": self.entity_type, "geometry": self.geometry, "layer": self.layer}).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {"handle": self.handle, "entity_type": self.entity_type, "layer": self.layer, "geometry": _canonical(self.geometry), "operation_id": self.operation_id, "deleted": self.deleted, "fingerprint": self.fingerprint}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EntitySnapshot":
        return cls(str(value["handle"]), str(value["entity_type"]), str(value["layer"]), dict(value["geometry"]), str(value["operation_id"]), bool(value.get("deleted", False)))


@dataclass(frozen=True)
class CadOperationResult:
    operation_id: str
    status: str
    entities: tuple[EntitySnapshot, ...] = ()
    error_code: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"operation_id": self.operation_id, "status": self.status, "entities": [item.to_dict() for item in self.entities], "error_code": self.error_code, "warning": self.warning}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CadOperationResult":
        return cls(str(value["operation_id"]), str(value["status"]), tuple(EntitySnapshot.from_dict(item) for item in value.get("entities", [])), value.get("error_code"), value.get("warning"))

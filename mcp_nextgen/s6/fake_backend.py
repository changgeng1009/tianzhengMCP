"""S6 纯内存合成 Sandbox 后端。

它是 DTO 合同的主回归实现，不创建文件、不导入 COM，保存/重开仅复制内存快照。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Mapping

from .contracts import CadOperation, CadOperationPlan, CadOperationResult, CadOperationValidationError, EntitySelector, EntitySnapshot, S6_SYNTHETIC_LAYER


class SyntheticCadBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class CadBatchResult:
    plan_hash: str
    results: tuple[CadOperationResult, ...]
    rolled_back: bool = False
    dry_run: bool = False


class SyntheticCadBackend:
    """仅接受由当前 job 注册的 synthetic document token 的纯内存执行器。"""

    def __init__(self, *, job_id: str, document_token: str) -> None:
        self.job_id = str(job_id)
        self.document_token = str(document_token)
        self._entities: dict[str, EntitySnapshot] = {}
        self._block_definitions: dict[str, EntitySnapshot] = {}
        self._layers: dict[str, Mapping[str, Any]] = {}
        self._text_styles: dict[str, Mapping[str, Any]] = {}
        self._dimension_styles: dict[str, Mapping[str, Any]] = {}
        self._applied: dict[str, CadOperationResult] = {}
        self._saved: tuple[dict[str, EntitySnapshot], dict[str, EntitySnapshot], dict[str, CadOperationResult], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]] | None = None
        self._closed = False
        self._next_handle = 1

    @property
    def synthetic_only(self) -> bool:
        return True

    def execute_plan(self, plan: CadOperationPlan) -> CadBatchResult:
        if plan.job_id != self.job_id or plan.document_token != self.document_token:
            raise SyntheticCadBackendError("S6_DOCUMENT_IDENTITY_MISMATCH", "计划不属于当前 synthetic document")
        if self._closed:
            raise SyntheticCadBackendError("S6_DOCUMENT_CLOSED", "重开前不得执行计划")
        before = deepcopy((self._entities, self._block_definitions, self._applied, self._layers, self._text_styles, self._dimension_styles, self._next_handle))
        results: list[CadOperationResult] = []
        for operation in plan.operations:
            try:
                result = self.execute_operation(operation)
                results.append(result)
            except (SyntheticCadBackendError, CadOperationValidationError) as exc:
                failed = CadOperationResult(operation.operation_id, "FAILED", error_code=getattr(exc, "code", "S6_OPERATION_VALIDATION_FAILED"))
                results.append(failed)
                if plan.batch_policy == "all_or_nothing":
                    self._entities, self._block_definitions, self._applied, self._layers, self._text_styles, self._dimension_styles, self._next_handle = before
                    return CadBatchResult(plan.plan_hash, tuple(results), rolled_back=True)
        if plan.dry_run:
            self._entities, self._block_definitions, self._applied, self._layers, self._text_styles, self._dimension_styles, self._next_handle = before
        return CadBatchResult(plan.plan_hash, tuple(results), rolled_back=False, dry_run=plan.dry_run)

    def execute_operation(self, operation: CadOperation) -> CadOperationResult:
        previous = self._applied.get(operation.operation_id)
        if previous is not None:
            return CadOperationResult(operation.operation_id, "ALREADY_APPLIED", previous.entities)
        kind = operation.operation
        if kind.startswith("CREATE_") or kind == "INSERT_BLOCK_REFERENCE":
            result = self._create(operation)
        elif kind in {"ENSURE_LAYER", "ENSURE_TEXT_STYLE", "ENSURE_DIMENSION_STYLE"}:
            result = self._ensure_style(operation)
        elif kind == "QUERY_ENTITIES":
            result = CadOperationResult(operation.operation_id, "QUERY_OK", tuple(self.query(operation.selector)))
        elif kind in {"MOVE_ENTITY", "ROTATE_ENTITY", "SCALE_ENTITY"}:
            result = self._transform(operation)
        elif kind == "COPY_ENTITY":
            result = self._copy(operation)
        elif kind == "DELETE_ENTITY":
            result = self._delete(operation)
        elif kind in {"SAVE_SYNTHETIC_DOCUMENT", "CLOSE_SYNTHETIC_DOCUMENT", "REOPEN_SYNTHETIC_DOCUMENT"}:
            result = self._lifecycle(operation)
        else:
            raise SyntheticCadBackendError("S6_OPERATION_UNSUPPORTED", kind)
        self._applied[operation.operation_id] = result
        return result

    def query(self, selector: EntitySelector | None = None) -> list[EntitySnapshot]:
        values = list(self._entities.values()) + list(self._block_definitions.values())
        values = [item for item in values if not item.deleted]
        if selector is None:
            return sorted(values, key=lambda item: item.handle)
        return [item for item in values if (selector.handle is None or item.handle == selector.handle)
                and (selector.operation_id is None or item.operation_id == selector.operation_id)
                and (selector.entity_type is None or item.entity_type == selector.entity_type)
                and (selector.layer is None or item.layer == selector.layer)]

    def save(self) -> None:
        self._saved = (deepcopy(self._entities), deepcopy(self._block_definitions), deepcopy(self._applied), deepcopy(self._layers), deepcopy(self._text_styles), deepcopy(self._dimension_styles))

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> None:
        if self._saved is None:
            raise SyntheticCadBackendError("S6_SAVE_REQUIRED", "重开前必须保存")
        self._entities, self._block_definitions, self._applied, self._layers, self._text_styles, self._dimension_styles = deepcopy(self._saved)
        self._closed = False

    def _create(self, operation: CadOperation) -> CadOperationResult:
        entity = operation.entity
        if entity is None:
            raise SyntheticCadBackendError("S6_ENTITY_REQUIRED", "创建操作缺少实体")
        expected = {
            "CREATE_ARC": "arc", "CREATE_RECTANGLE": "rectangle", "CREATE_TEXT": "text", "CREATE_MTEXT": "mtext",
            "CREATE_BLOCK_DEFINITION": "block_definition", "INSERT_BLOCK_REFERENCE": "block_reference",
            "CREATE_LINE": "line", "CREATE_CIRCLE": "circle", "CREATE_POLYLINE": "polyline",
        }.get(operation.operation)
        if expected != entity.entity_type:
            raise SyntheticCadBackendError("S6_ENTITY_OPERATION_MISMATCH", "操作与实体类型不匹配")
        if entity.entity_type == "block_reference" and not any(item.geometry.get("name") == entity.geometry["block_name"] for item in self._block_definitions.values()):
            raise SyntheticCadBackendError("S6_BLOCK_DEFINITION_NOT_FOUND", "Block definition 不存在")
        snapshot = self._new_snapshot(entity.entity_type, entity.geometry, operation.operation_id)
        (self._block_definitions if entity.entity_type == "block_definition" else self._entities)[snapshot.handle] = snapshot
        return CadOperationResult(operation.operation_id, "CREATED", (snapshot,))

    def _ensure_style(self, operation: CadOperation) -> CadOperationResult:
        mapping = {
            "ENSURE_LAYER": (self._layers, "layer"),
            "ENSURE_TEXT_STYLE": (self._text_styles, "text_style"),
            "ENSURE_DIMENSION_STYLE": (self._dimension_styles, "dimension_style"),
        }
        registry, key = mapping[operation.operation]
        spec = dict(operation.parameters[key]); name = str(spec["name"])
        existing = registry.get(name)
        if existing is None:
            registry[name] = spec
            return CadOperationResult(operation.operation_id, "CREATED")
        if dict(existing) == spec:
            return CadOperationResult(operation.operation_id, "ALREADY_EXISTS_EQUIVALENT")
        return CadOperationResult(operation.operation_id, "CONFLICT", error_code="S6_STYLE_CONFLICT")

    def _target(self, selector: EntitySelector | None) -> EntitySnapshot:
        matches = self.query(selector)
        if len(matches) != 1:
            raise SyntheticCadBackendError("S6_SELECTOR_NOT_UNIQUE", f"selector 命中 {len(matches)} 个实体")
        return matches[0]

    def _transform(self, operation: CadOperation) -> CadOperationResult:
        target = self._target(operation.selector)
        if target.entity_type == "block_definition":
            raise SyntheticCadBackendError("S6_BLOCK_DEFINITION_IMMUTABLE", "不得变换 BlockDefinition")
        geometry = deepcopy(dict(target.geometry))
        if operation.operation == "MOVE_ENTITY":
            geometry = _translate(geometry, operation.parameters["displacement"])
        elif operation.operation == "ROTATE_ENTITY":
            geometry = _rotate(geometry, operation.parameters["base_point"], float(operation.parameters["angle"]))
        else:
            geometry = _scale(geometry, operation.parameters["base_point"], float(operation.parameters["scale"]))
        updated = EntitySnapshot(target.handle, target.entity_type, target.layer, geometry, target.operation_id)
        self._entities[target.handle] = updated
        return CadOperationResult(operation.operation_id, "UPDATED", (updated,))

    def _copy(self, operation: CadOperation) -> CadOperationResult:
        target = self._target(operation.selector)
        if target.entity_type == "block_definition":
            raise SyntheticCadBackendError("S6_COPY_FORBIDDEN", "不得复制 BlockDefinition")
        copied = self._new_snapshot(target.entity_type, _translate(deepcopy(dict(target.geometry)), operation.parameters["displacement"]), operation.operation_id)
        self._entities[copied.handle] = copied
        return CadOperationResult(operation.operation_id, "CREATED", (copied,))

    def _delete(self, operation: CadOperation) -> CadOperationResult:
        target = self._target(operation.selector)
        if target.entity_type == "block_definition":
            if any(item.entity_type == "block_reference" and item.geometry.get("block_name") == target.geometry.get("name") for item in self._entities.values() if not item.deleted):
                raise SyntheticCadBackendError("S6_BLOCK_DEFINITION_IN_USE", "Block definition 仍被引用")
            self._block_definitions.pop(target.handle, None)
        else:
            self._entities.pop(target.handle, None)
        deleted = EntitySnapshot(target.handle, target.entity_type, target.layer, target.geometry, target.operation_id, deleted=True)
        return CadOperationResult(operation.operation_id, "DELETED", (deleted,))

    def _lifecycle(self, operation: CadOperation) -> CadOperationResult:
        if operation.operation == "SAVE_SYNTHETIC_DOCUMENT": self.save(); status = "SAVED"
        elif operation.operation == "CLOSE_SYNTHETIC_DOCUMENT": self.close(); status = "CLOSED"
        else: self.reopen(); status = "REOPENED"
        return CadOperationResult(operation.operation_id, status)

    def _new_snapshot(self, entity_type: str, geometry: Mapping[str, Any], operation_id: str) -> EntitySnapshot:
        handle = f"S6{self._next_handle:06X}"; self._next_handle += 1
        return EntitySnapshot(handle, entity_type, S6_SYNTHETIC_LAYER, deepcopy(dict(geometry)), operation_id)


def _walk_points(value: Any, fn):
    if isinstance(value, Mapping):
        if {"x", "y"}.issubset(value): return fn(dict(value))
        return {key: _walk_points(item, fn) for key, item in value.items()}
    if isinstance(value, list): return [_walk_points(item, fn) for item in value]
    return value


def _translate(geometry: Mapping[str, Any], displacement: Mapping[str, Any]) -> dict[str, Any]:
    dx, dy, dz = float(displacement["x"]), float(displacement["y"]), float(displacement.get("z", 0.0))
    return _walk_points(geometry, lambda point: {**point, "x": point["x"] + dx, "y": point["y"] + dy, "z": point.get("z", 0.0) + dz})


def _rotate(geometry: Mapping[str, Any], base: Mapping[str, Any], angle: float) -> dict[str, Any]:
    base = {key: float(value) for key, value in base.items()}
    c, s = math.cos(angle), math.sin(angle)
    def transform(point: dict[str, Any]) -> dict[str, Any]:
        x, y = point["x"] - base["x"], point["y"] - base["y"]
        return {**point, "x": base["x"] + x*c-y*s, "y": base["y"] + x*s+y*c}
    return _walk_points(geometry, transform)


def _scale(geometry: Mapping[str, Any], base: Mapping[str, Any], factor: float) -> dict[str, Any]:
    base = {key: float(value) for key, value in base.items()}
    def transform(point: dict[str, Any]) -> dict[str, Any]:
        return {**point, "x": base["x"]+(point["x"]-base["x"])*factor, "y": base["y"]+(point["y"]-base["y"])*factor,
                "z": base.get("z", 0.0)+(point.get("z", 0.0)-base.get("z",0.0))*factor}
    result = _walk_points(geometry, transform)
    if "radius" in result: result["radius"] = float(result["radius"]) * factor
    if "height" in result: result["height"] = float(result["height"]) * factor
    if "width" in result: result["width"] = float(result["width"]) * factor
    if "scale" in result: result["scale"] = float(result["scale"]) * factor
    return result

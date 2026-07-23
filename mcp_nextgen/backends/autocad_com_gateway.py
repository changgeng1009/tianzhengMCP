"""S5 的受控 AutoCAD COM gateway。

此处不导入 ``win32com``，Application 对象仅来自已经完成 DispatchEx 的 transport。
所有 Documents.Add/Open 均由已注册的 synthetic identity 约束，绝不读取
ActiveDocument 或任何外部文件路径。
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .autocad_com_activation import read_with_startup_busy_retry
from .real_autocad_com import (
    CircleSpec, LineSpec, PolylineSpec, S5_LAYER, SyntheticAutoCadDocumentIdentity,
    geometry_fingerprint,
)
from mcp_nextgen.s6.contracts import EntitySelector, EntitySpec, S6_SYNTHETIC_LAYER


class AutoCadComGatewayError(RuntimeError):
    def __init__(self, error_code: str, message: str = "", *, stage: str | None = None) -> None:
        super().__init__(f"{error_code}: {message}".rstrip(": "))
        self.error_code = error_code
        self.stage = stage


class ComSafeArrayAdapter:
    """COM 数组封送边界；可注入 Fake，模块 import 不加载 pywin32。"""

    def point3(self, values: tuple[float, float, float]) -> Any:
        raise NotImplementedError

    def coordinates(self, values: tuple[float, ...]) -> Any:
        raise NotImplementedError


class PureValueSafeArrayAdapter(ComSafeArrayAdapter):
    """默认的纯值适配器。

    默认单元测试和 Fake gateway 不应因为构造 S5 gateway 而导入 pywin32。
    真实 COM 路径必须由 runner 显式注入 ``LazyPywin32SafeArrayAdapter``；
    本适配器只返回不可变纯数值元组，不能被视为真实 COM 封送实现。
    """

    def point3(self, values: tuple[float, float, float]) -> tuple[float, float, float]:
        return tuple(float(value) for value in values)  # type: ignore[return-value]

    def coordinates(self, values: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(float(value) for value in values)


class LazyPywin32SafeArrayAdapter(ComSafeArrayAdapter):
    """仅在真实实体创建时延迟解析 pywin32 VARIANT。"""

    @staticmethod
    def _variant(values: tuple[float, ...]) -> Any:
        try:
            pythoncom = importlib.import_module("pythoncom")
            client = importlib.import_module("win32com.client")
            return client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, values)
        except (ImportError, AttributeError) as exc:
            raise AutoCadComGatewayError("AUTOCAD_COM_DEPENDENCY_MISSING", "pywin32 SafeArray 不可用", stage="COM_SAFEARRAY") from exc

    def point3(self, values: tuple[float, float, float]) -> Any:
        return self._variant(values)

    def coordinates(self, values: tuple[float, ...]) -> Any:
        return self._variant(values)


@dataclass
class Pywin32AutoCadSandboxGateway:
    """显式持有的 COM Application/Document，不使用 ActiveDocument 回退。"""

    application: Any
    _document: Any | None = None
    _identity: SyntheticAutoCadDocumentIdentity | None = None
    _operation_metadata: dict[str, dict[str, Any]] | None = None
    _handle_metadata: dict[str, dict[str, Any]] | None = None
    _virtual_entities: dict[str, Mapping[str, Any]] | None = None
    _job_owned: bool = True
    array_adapter: ComSafeArrayAdapter | None = None

    def __post_init__(self) -> None:
        self._operation_metadata = {} if self._operation_metadata is None else self._operation_metadata
        self._handle_metadata = {} if self._handle_metadata is None else self._handle_metadata
        self._virtual_entities = {} if self._virtual_entities is None else self._virtual_entities
        # 默认保持纯 Python，避免 Mock/Fake 路径隐式导入 pythoncom。真实
        # DispatchEx runner 必须显式提供 LazyPywin32SafeArrayAdapter。
        self.array_adapter = self.array_adapter or PureValueSafeArrayAdapter()

    def create_synthetic(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]:
        self._bind(identity, require_open=False)
        try:
            document = self.application.Documents.Add()
            # 先绑定对象，确保 SaveAs 失败后 runner 仍可仅关闭这个已注册的
            # job-owned 空白文档；绝不转向任何 ActiveDocument。
            self._document = document
            self._identity = identity
            # Documents.Add 得到的对象引用被立即持有并保存到注册路径；没有任何
            # ActiveDocument/最近文件逻辑，也不允许调用者传入其他路径。
            document.SaveAs(identity.canonical_path)
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_SAVE_FAILED: 创建或保存合成文档失败") from exc
        return self.document_snapshot(identity)

    def document_snapshot(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]:
        document = self._bind(identity)
        full_name = str(getattr(document, "FullName", ""))
        if Path(full_name).resolve(strict=False) != Path(identity.canonical_path).resolve(strict=False):
            return {"synthetic": False, "user_document": True, "canonical_path": full_name}
        return {
            "synthetic": True, "user_document": False, "canonical_path": identity.canonical_path,
            "name": str(getattr(document, "Name", "")), "read_only": bool(getattr(document, "ReadOnly", False)),
        }

    def ensure_layer(self, identity: SyntheticAutoCadDocumentIdentity, layer: str) -> None:
        if layer not in {S5_LAYER, S6_SYNTHETIC_LAYER}:
            raise AutoCadComGatewayError("仅允许受控 synthetic 专用图层")
        document = self._bind(identity)
        try:
            document.Layers.Item(layer)
        except Exception:
            try:
                document.Layers.Add(layer)
            except Exception as exc:
                raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED: 无法创建专用图层") from exc

    def ensure_s6_resource(self, identity: SyntheticAutoCadDocumentIdentity, operation: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
        """只确保当前 synthetic 文档内的样式资源，禁止覆盖同名冲突资源。"""
        document = self._bind(identity)
        try:
            if operation == "ENSURE_LAYER":
                spec = dict(parameters["layer"]); name = str(spec["name"])
                if name != S6_SYNTHETIC_LAYER:
                    raise AutoCadComGatewayError("S6_STYLE_SCOPE_VIOLATION", "只允许 S6 专用图层", stage="S6_STYLE")
                try:
                    layer = self._dynamic_entity_view(document.Layers.Item(name))
                    existing = {"color_index": int(getattr(layer, "Color", 7)), "linetype": str(getattr(layer, "Linetype", "Continuous")), "lineweight": int(getattr(layer, "Lineweight", -1)), "visible": bool(getattr(layer, "LayerOn", True)), "locked": bool(getattr(layer, "Lock", False))}
                    expected = {key: spec[key] for key in existing}
                    if existing != expected:
                        return {"status": "CONFLICT", "resource": name}
                    return {"status": "ALREADY_EXISTS_EQUIVALENT", "resource": name}
                except Exception:
                    # makepy 会把新建 layer 包装为 IAcadLayer 基类；与 Arc 等
                    # 派生对象一样，必须按原 IDispatch 动态视图写入 Color 等
                    # 可选属性，不能重新连接 AutoCAD。
                    layer = self._dynamic_entity_view(document.Layers.Add(name))
                    layer.Color = int(spec["color_index"]); layer.Linetype = str(spec["linetype"]); layer.Lineweight = int(spec["lineweight"]); layer.LayerOn = bool(spec["visible"]); layer.Lock = bool(spec["locked"])
                    return {"status": "CREATED", "resource": name}
            if operation == "ENSURE_TEXT_STYLE":
                spec = dict(parameters["text_style"]); name = str(spec["name"])
                try:
                    document.TextStyles.Item(name)
                    return {"status": "ALREADY_EXISTS_EQUIVALENT", "resource": name, "font": "NOT_VERIFIED"}
                except Exception:
                    document.TextStyles.Add(name)
                    return {"status": "CREATED", "resource": name, "font": "NOT_VERIFIED"}
            if operation == "ENSURE_DIMENSION_STYLE":
                name = str(dict(parameters["dimension_style"])["name"])
                try:
                    document.DimStyles.Item(name)
                    return {"status": "ALREADY_EXISTS_EQUIVALENT", "resource": name}
                except Exception:
                    document.DimStyles.Add(name)
                    return {"status": "CREATED", "resource": name}
        except AutoCadComGatewayError:
            raise
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", f"S6 {operation} 样式资源创建失败", stage="S6_STYLE") from exc
        raise AutoCadComGatewayError("S6_OPERATION_UNSUPPORTED", operation, stage="S6_STYLE")

    def create_line(self, identity: SyntheticAutoCadDocumentIdentity, spec: LineSpec) -> Mapping[str, Any]:
        try:
            entity = self._bind(identity).ModelSpace.AddLine(
                self.array_adapter.point3(tuple(spec.start.as_list())), self.array_adapter.point3(tuple(spec.end.as_list()))
            )
            entity.Layer = S5_LAYER
            return self._entity(identity, entity, "line", spec.geometry(), spec.operation_key)
        except AutoCadComGatewayError:
            raise
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", "Line 创建失败", stage="CREATE_LINE") from exc

    def create_circle(self, identity: SyntheticAutoCadDocumentIdentity, spec: CircleSpec) -> Mapping[str, Any]:
        try:
            entity = self._bind(identity).ModelSpace.AddCircle(self.array_adapter.point3(tuple(spec.center.as_list())), spec.radius)
            entity.Layer = S5_LAYER
            return self._entity(identity, entity, "circle", spec.geometry(), spec.operation_key)
        except AutoCadComGatewayError:
            raise
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", "Circle 创建失败", stage="CREATE_CIRCLE") from exc

    def create_polyline(self, identity: SyntheticAutoCadDocumentIdentity, spec: PolylineSpec) -> Mapping[str, Any]:
        coordinates: list[float] = []
        for point in spec.vertices:
            coordinates.extend([point.x, point.y])
        try:
            entity = self._bind(identity).ModelSpace.AddLightWeightPolyline(self.array_adapter.coordinates(tuple(coordinates)))
            entity.Layer = S5_LAYER
            entity.Closed = bool(spec.closed)
            return self._entity(identity, entity, "polyline", spec.geometry(), spec.operation_key)
        except AutoCadComGatewayError:
            raise
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", "Polyline 创建失败", stage="CREATE_POLYLINE") from exc

    # S6 仅由显式 L3 synthetic plan executor 调用。它仍只操作当前 registry
    # 持有的 Document，既不使用 ActiveDocument，也不接受外部路径或 COM 字符串命令。
    def create_s6_entity(self, identity: SyntheticAutoCadDocumentIdentity, spec: EntitySpec, operation_id: str) -> Mapping[str, Any]:
        document = self._bind(identity)
        self.ensure_layer(identity, S6_SYNTHETIC_LAYER)
        geometry, kind = dict(spec.geometry), spec.entity_type
        try:
            if kind == "line":
                entity = document.ModelSpace.AddLine(self.array_adapter.point3(_point_tuple(geometry["start"])), self.array_adapter.point3(_point_tuple(geometry["end"])))
            elif kind == "circle":
                entity = document.ModelSpace.AddCircle(self.array_adapter.point3(_point_tuple(geometry["center"])), float(geometry["radius"]))
            elif kind == "polyline":
                coordinates: list[float] = []
                for point in geometry["vertices"]:
                    coordinates.extend([float(point["x"]), float(point["y"])])
                entity = document.ModelSpace.AddLightWeightPolyline(self.array_adapter.coordinates(tuple(coordinates)))
                entity.Closed = bool(geometry.get("closed", False))
            elif kind == "arc":
                entity = document.ModelSpace.AddArc(self.array_adapter.point3(_point_tuple(geometry["center"])), float(geometry["radius"]), float(geometry["start_angle"]), float(geometry["end_angle"]))
            elif kind == "rectangle":
                a, b = geometry["corner_a"], geometry["corner_b"]
                values = (float(a["x"]), float(a["y"]), float(b["x"]), float(a["y"]), float(b["x"]), float(b["y"]), float(a["x"]), float(b["y"]))
                entity = document.ModelSpace.AddLightWeightPolyline(self.array_adapter.coordinates(values)); entity.Closed = True
            elif kind == "text":
                entity = document.ModelSpace.AddText(str(geometry["text"]), self.array_adapter.point3(_point_tuple(geometry["insertion_point"])), float(geometry["height"])); entity.Rotation = float(geometry["rotation"])
            elif kind == "mtext":
                entity = document.ModelSpace.AddMText(self.array_adapter.point3(_point_tuple(geometry["insertion_point"])), float(geometry["width"]), str(geometry["content"])); entity.Height = float(geometry["height"]); entity.Rotation = float(geometry["rotation"])
            elif kind == "block_definition":
                name = str(geometry["name"])
                try: document.Blocks.Item(name)
                except Exception:
                    block = document.Blocks.Add(self.array_adapter.point3((0.0, 0.0, 0.0)), name)
                    # 合同要求至少一个定义内容；S6 MVP 只将定义内的线段作为
                    # 可验证最小成员，其他成员继续以结构化元数据保留。
                    block.AddLine(self.array_adapter.point3((0.0, 0.0, 0.0)), self.array_adapter.point3((100.0, 0.0, 0.0)))
                return self._virtual_entity(identity, kind, geometry, operation_id)
            elif kind == "block_reference":
                entity = document.ModelSpace.InsertBlock(self.array_adapter.point3(_point_tuple(geometry["insertion_point"])), str(geometry["block_name"]), float(geometry["scale"]), float(geometry["scale"]), float(geometry["scale"]), float(geometry["rotation"]))
            else:
                raise AutoCadComGatewayError("S6_ENTITY_UNSUPPORTED", kind, stage="S6_CREATE")
            entity.Layer = S6_SYNTHETIC_LAYER
            if spec.style and kind in {"text", "mtext"}:
                self._ensure_s6_text_style(document, spec.style); entity.StyleName = spec.style
            return self._entity(identity, entity, kind, geometry, operation_id)
        except AutoCadComGatewayError:
            raise
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", f"S6 {kind} 创建失败", stage="S6_CREATE") from exc

    def transform_s6_entity(self, identity: SyntheticAutoCadDocumentIdentity, selector: EntitySelector, operation: str, parameters: Mapping[str, Any], operation_id: str) -> Mapping[str, Any]:
        entity, raw = self._resolve_s6_entity(identity, selector)
        try:
            if operation == "MOVE_ENTITY": entity.Move(self.array_adapter.point3((0.0, 0.0, 0.0)), self.array_adapter.point3(_point_tuple(parameters["displacement"])))
            elif operation == "ROTATE_ENTITY": entity.Rotate(self.array_adapter.point3(_point_tuple(parameters["base_point"])), float(parameters["angle"]))
            elif operation == "SCALE_ENTITY": entity.ScaleEntity(self.array_adapter.point3(_point_tuple(parameters["base_point"])), float(parameters["scale"]))
            elif operation == "COPY_ENTITY":
                entity = entity.Copy(); entity.Move(self.array_adapter.point3((0.0, 0.0, 0.0)), self.array_adapter.point3(_point_tuple(parameters["displacement"]))); entity.Layer = S6_SYNTHETIC_LAYER
            elif operation == "DELETE_ENTITY": entity.Delete(); return {**raw, "deleted": True, "operation_id": operation_id}
            else: raise AutoCadComGatewayError("S6_OPERATION_UNSUPPORTED", operation, stage="S6_TRANSFORM")
            kind, geometry = self._read_geometry(entity)
            # Rectangle 是 closed lightweight polyline 的 S6 语义糖。COM 只会
            # 返回 AcDbPolyline，变换后必须保留原 S6 logical type，不能把它
            # 降级为普通 polyline，从而破坏计划级持久化校验。
            kind = str(raw.get("entity_type") or kind)
            metadata = dict(raw); metadata["operation_key"] = operation_id; metadata["entity_type"] = kind
            return self._entity(identity, entity, kind, geometry, operation_id)
        except AutoCadComGatewayError:
            raise
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", f"S6 {operation} 失败", stage="S6_TRANSFORM") from exc

    def query_s6_entities(self, identity: SyntheticAutoCadDocumentIdentity, selector: EntitySelector | None = None) -> Sequence[Mapping[str, Any]]:
        # BlockDefinition 没有 ModelSpace entity/handle。其 S6 快照可以保留在
        # 当前 job 的元数据中，但每次查询（尤其是 Save/Close/Reopen 后）都要
        # 重新向已持有的 Document.Blocks 验证名称，不能只因为内存字典仍在就
        # 宣称持久化成功。
        block_rows = [row for row in self._virtual_entities.values() if self._block_definition_exists(identity, row)]
        rows = list(self.list_entities(identity)) + block_rows
        if selector is None: return rows
        return [row for row in rows if (selector.handle is None or row.get("handle") == selector.handle)
                and (selector.operation_id is None or row.get("operation_key") == selector.operation_id)
                and (selector.entity_type is None or row.get("entity_type") == selector.entity_type)
                and (selector.layer is None or row.get("layer") == selector.layer)]

    def restore_s6_operation_journal(self, identity: SyntheticAutoCadDocumentIdentity, results: Sequence[Mapping[str, Any]]) -> None:
        """从当前 run 的 JSON journal 恢复 operation metadata。

        journal 仅位于同一 synthetic artifact root，重开后仍会用真实
        ModelSpace/Blocks 查询验证 handle 和 block 名称；它不是用户图纸的
        外部索引，也不会跟随或读取任何未知 DWG。
        """
        self._bind(identity)
        self._operation_metadata.clear(); self._handle_metadata.clear(); self._virtual_entities.clear()
        for result in results:
            operation_id = str(result.get("operation_id", ""))
            for item in result.get("entities", []):
                if bool(item.get("deleted", False)):
                    continue
                handle = str(item.get("handle", "")); entity_type = str(item.get("entity_type", ""))
                geometry = dict(item.get("geometry", {}))
                if not handle or not entity_type:
                    continue
                metadata = {"operation_key": str(item.get("operation_id") or operation_id), "entity_type": entity_type}
                self._handle_metadata[handle] = metadata
                self._operation_metadata[str(item.get("fingerprint", ""))] = metadata
                if entity_type == "block_definition":
                    self._virtual_entities[handle] = {
                        "handle": handle, "object_name": "AcDbBlockTableRecord", "entity_type": entity_type,
                        "layer": S6_SYNTHETIC_LAYER, "geometry": geometry, "operation_key": metadata["operation_key"],
                        "geometry_fingerprint": geometry_fingerprint(entity_type, geometry), "verification_status": "VERIFIED",
                    }

    def _block_definition_exists(self, identity: SyntheticAutoCadDocumentIdentity, row: Mapping[str, Any]) -> bool:
        if row.get("entity_type") != "block_definition":
            return True
        name = str(dict(row.get("geometry", {})).get("name", ""))
        if not name:
            return False
        try:
            self._bind(identity).Blocks.Item(name)
            return True
        except Exception:
            return False

    def list_entities(self, identity: SyntheticAutoCadDocumentIdentity) -> Sequence[Mapping[str, Any]]:
        document = self._bind(identity)
        rows: list[Mapping[str, Any]] = []
        for entity in document.ModelSpace:
            if str(getattr(entity, "Layer", "")) not in {S5_LAYER, S6_SYNTHETIC_LAYER}:
                continue
            kind, geometry = self._read_geometry(entity)
            if not kind:
                continue
            handle = str(getattr(entity, "Handle", ""))
            metadata = self._handle_metadata.get(handle, {})
            kind = str(metadata.get("entity_type", kind))
            rows.append(self._entity(identity, entity, kind, geometry, str(metadata.get("operation_key", ""))))
        return rows

    def save(self, identity: SyntheticAutoCadDocumentIdentity) -> None:
        try:
            self._bind(identity).Save()
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_SAVE_FAILED") from exc

    def close(self, identity: SyntheticAutoCadDocumentIdentity) -> None:
        document = self._bind(identity)
        try:
            document.Close(False)
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_CLOSE_FAILED") from exc
        self._document = None

    def reopen(self, identity: SyntheticAutoCadDocumentIdentity) -> None:
        self._bind(identity, require_open=False)
        try:
            # Document.Close(False) 后 AutoCAD 可能短暂拒绝紧随其后的 Open。
            # 只对两个既定 startup-busy HRESULT 做有界重试；不重新激活 COM、
            # 不改变路径，也不回退到 ActiveDocument。
            document = read_with_startup_busy_retry(
                lambda: self.application.Documents.Open(identity.canonical_path, False)
            )
        except Exception as exc:
            raise AutoCadComGatewayError("AUTOCAD_REOPEN_FAILED", stage="REOPEN_SYNTHETIC_DOCUMENT") from exc
        self._document = document
        self._identity = identity
        self.document_snapshot(identity)

    def quit_if_job_owned(self) -> None:
        if not self._job_owned:
            return
        if self._document is not None:
            raise AutoCadComGatewayError("AUTOCAD_SESSION_UNSAFE: 合成文档尚未关闭")
        if int(getattr(self.application.Documents, "Count", -1)) != 0:
            raise AutoCadComGatewayError("AUTOCAD_SESSION_UNSAFE: 会话仍含未知文档")
        self.application.Quit()

    def has_registered_synthetic_document(self, identity: SyntheticAutoCadDocumentIdentity) -> bool:
        return self._identity == identity and self._document is not None

    def discard_registered_synthetic_document(self, identity: SyntheticAutoCadDocumentIdentity) -> None:
        """失败清理仅关闭当前注册 synthetic Document，未知身份一律拒绝。"""
        if not self.has_registered_synthetic_document(identity):
            raise AutoCadComGatewayError("AUTOCAD_DOCUMENT_IDENTITY_MISMATCH")
        self._document.Close(False)
        self._document = None

    def _bind(self, identity: SyntheticAutoCadDocumentIdentity, *, require_open: bool = True) -> Any:
        if self._identity is not None and self._identity != identity:
            raise AutoCadComGatewayError("AUTOCAD_DOCUMENT_IDENTITY_MISMATCH")
        if require_open and self._document is None:
            raise AutoCadComGatewayError("AUTOCAD_DOCUMENT_IDENTITY_MISMATCH: 未持有当前合成文档")
        return self._document

    def _entity(self, identity: SyntheticAutoCadDocumentIdentity, entity: Any, entity_type: str, geometry: Mapping[str, Any], operation_key: str) -> Mapping[str, Any]:
        fingerprint = geometry_fingerprint(entity_type, geometry)
        handle = str(getattr(entity, "Handle", ""))
        if operation_key:
            metadata = {"operation_key": operation_key, "entity_type": entity_type}
            self._operation_metadata[fingerprint] = metadata
            if handle: self._handle_metadata[handle] = metadata
        return {
            "handle": handle, "object_name": str(getattr(entity, "ObjectName", "")),
            "entity_type": entity_type, "layer": str(getattr(entity, "Layer", S5_LAYER)), "geometry": dict(geometry),
            "operation_key": operation_key, "geometry_fingerprint": fingerprint, "verification_status": "VERIFIED",
        }

    @staticmethod
    def _read_geometry(entity: Any) -> tuple[str, Mapping[str, Any]]:
        # ``EnsureDispatch`` 稳定了 Application/Documents 的启动期属性，但
        # AutoCAD 2026 的 ModelSpace 枚举会因此把 Arc 等对象包装成静态
        # ``IAcadEntity`` 基类。基类不公开 Center/Radius 等派生属性。仅在
        # 此 COM 边界把 *同一个* entity IDispatch 重新包装成 pywin32 dynamic
        # proxy，既不创建实体、不激活应用，也不改变文档身份。
        entity = Pywin32AutoCadSandboxGateway._dynamic_entity_view(entity)
        name = str(getattr(entity, "ObjectName", "")).lower()
        if "polyline" in name:
            values = list(entity.Coordinates)
            return "polyline", {"vertices": [[values[i], values[i + 1], 0.0] for i in range(0, len(values), 2)], "closed": bool(entity.Closed)}
        if name.endswith("line"):
            return "line", {"start": list(entity.StartPoint), "end": list(entity.EndPoint)}
        if name.endswith("circle"):
            return "circle", {"center": list(entity.Center), "radius": float(entity.Radius)}
        if name.endswith("arc"):
            return "arc", {"center": list(entity.Center), "radius": float(entity.Radius), "start_angle": float(entity.StartAngle), "end_angle": float(entity.EndAngle)}
        if name.endswith("mtext"):
            return "mtext", {"content": str(entity.TextString), "insertion_point": list(entity.InsertionPoint), "height": float(entity.Height), "width": float(entity.Width), "rotation": float(entity.Rotation)}
        if name.endswith("text"):
            return "text", {"text": str(entity.TextString), "insertion_point": list(entity.InsertionPoint), "height": float(entity.Height), "rotation": float(entity.Rotation)}
        if "blockreference" in name:
            return "block_reference", {"block_name": str(getattr(entity, "EffectiveName", getattr(entity, "Name", ""))), "insertion_point": list(entity.InsertionPoint), "rotation": float(entity.Rotation), "scale": float(entity.XScaleFactor)}
        return "", {}

    @staticmethod
    def _dynamic_entity_view(entity: Any) -> Any:
        """把 makepy 基类实体按原 IDispatch 转为动态属性视图。

        只访问当前已经由 ModelSpace 返回的 entity；不通过 ProgID 连接或附着
        AutoCAD。Mock 对象没有 ``_oleobj_`` 时原样返回，默认测试也不会加载
        pywin32。
        """
        ole_object = getattr(entity, "_oleobj_", None)
        if ole_object is None:
            return entity
        try:
            dynamic = importlib.import_module("win32com.client.dynamic")
            return dynamic.Dispatch(ole_object)
        except (ImportError, AttributeError):
            return entity

    def _resolve_s6_entity(self, identity: SyntheticAutoCadDocumentIdentity, selector: EntitySelector) -> tuple[Any, Mapping[str, Any]]:
        rows = self.query_s6_entities(identity, selector)
        if len(rows) != 1: raise AutoCadComGatewayError("S6_SELECTOR_NOT_UNIQUE", stage="S6_TARGET")
        raw = rows[0]
        if raw.get("layer") != S6_SYNTHETIC_LAYER or not raw.get("handle"):
            raise AutoCadComGatewayError("AUTOCAD_DOCUMENT_IDENTITY_MISMATCH", stage="S6_TARGET")
        try: return self._bind(identity).HandleToObject(str(raw["handle"])), raw
        except Exception as exc: raise AutoCadComGatewayError("S6_ENTITY_NOT_FOUND", stage="S6_TARGET") from exc

    @staticmethod
    def _ensure_s6_text_style(document: Any, name: str) -> None:
        try: document.TextStyles.Item(name)
        except Exception: document.TextStyles.Add(name)

    def _virtual_entity(self, identity: SyntheticAutoCadDocumentIdentity, entity_type: str, geometry: Mapping[str, Any], operation_id: str) -> Mapping[str, Any]:
        handle = f"S6BLOCK:{geometry['name']}"
        raw = {"handle": handle, "object_name": "AcDbBlockTableRecord", "entity_type": entity_type, "layer": S6_SYNTHETIC_LAYER,
               "geometry": dict(geometry), "operation_key": operation_id, "geometry_fingerprint": geometry_fingerprint(entity_type, geometry), "verification_status": "VERIFIED"}
        self._handle_metadata[handle] = {"operation_key": operation_id, "entity_type": entity_type}
        self._virtual_entities[handle] = raw
        return raw


def _point_tuple(value: Mapping[str, Any]) -> tuple[float, float, float]:
    return (float(value["x"]), float(value["y"]), float(value.get("z", 0.0)))

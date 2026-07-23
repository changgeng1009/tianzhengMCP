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
    _job_owned: bool = True
    array_adapter: ComSafeArrayAdapter | None = None

    def __post_init__(self) -> None:
        self._operation_metadata = {} if self._operation_metadata is None else self._operation_metadata
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
        if layer != S5_LAYER:
            raise AutoCadComGatewayError("仅允许 S5 专用图层")
        document = self._bind(identity)
        try:
            document.Layers.Item(layer)
        except Exception:
            try:
                document.Layers.Add(layer)
            except Exception as exc:
                raise AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED: 无法创建专用图层") from exc

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

    def list_entities(self, identity: SyntheticAutoCadDocumentIdentity) -> Sequence[Mapping[str, Any]]:
        document = self._bind(identity)
        rows: list[Mapping[str, Any]] = []
        for entity in document.ModelSpace:
            if str(getattr(entity, "Layer", "")) != S5_LAYER:
                continue
            kind, geometry = self._read_geometry(entity)
            if not kind:
                continue
            fingerprint = geometry_fingerprint(kind, geometry)
            metadata = self._operation_metadata.get(fingerprint, {})
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
        if operation_key:
            self._operation_metadata[fingerprint] = {"operation_key": operation_key}
        return {
            "handle": str(getattr(entity, "Handle", "")), "object_name": str(getattr(entity, "ObjectName", "")),
            "entity_type": entity_type, "layer": str(getattr(entity, "Layer", S5_LAYER)), "geometry": dict(geometry),
            "operation_key": operation_key, "geometry_fingerprint": fingerprint, "verification_status": "VERIFIED",
        }

    @staticmethod
    def _read_geometry(entity: Any) -> tuple[str, Mapping[str, Any]]:
        name = str(getattr(entity, "ObjectName", "")).lower()
        if "polyline" in name:
            values = list(entity.Coordinates)
            return "polyline", {"vertices": [[values[i], values[i + 1], 0.0] for i in range(0, len(values), 2)], "closed": bool(entity.Closed)}
        if name.endswith("line"):
            return "line", {"start": list(entity.StartPoint), "end": list(entity.EndPoint)}
        if name.endswith("circle"):
            return "circle", {"center": list(entity.Center), "radius": float(entity.Radius)}
        return "", {}

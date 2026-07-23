"""S5 Real AutoCAD COM Sandbox 的业务层合同。

本模块刻意不导入 ``win32com``、不启动进程、也不打开任意 DWG。实际 COM
调用必须由注入的 gateway 实现；因此默认单元测试可完全使用 Fake gateway。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4


S5_LAYER = "CADAGENT_S5_MVP"
S5_BACKEND = "real_autocad_com"
S5_PRODUCT = "generic_autocad"
S5_RUNTIME = "com"
S5_SAFETY_LEVEL = "L3_SANDBOX_WRITE"
S5_ALLOWED_OPERATIONS = frozenset(
    {
        "CREATE_SYNTHETIC_DOCUMENT",
        "CREATE_LINE",
        "CREATE_CIRCLE",
        "CREATE_POLYLINE",
        "QUERY_ENTITY",
        "SAVE_SYNTHETIC_DOCUMENT",
        "REOPEN_SYNTHETIC_DOCUMENT",
        "VERIFY_SYNTHETIC_DOCUMENT",
        "CLOSE_SYNTHETIC_DOCUMENT",
        # S6 仍只允许当前 job 新建的 L3 synthetic sandbox；这些名称不是
        # production 权限，也不会被默认测试或普通 Manifest 自动授予。
        "CREATE_ARC", "CREATE_RECTANGLE", "CREATE_TEXT", "CREATE_MTEXT",
        "CREATE_BLOCK_DEFINITION", "INSERT_BLOCK_REFERENCE", "QUERY_ENTITIES",
        "MOVE_ENTITY", "COPY_ENTITY", "ROTATE_ENTITY", "SCALE_ENTITY", "DELETE_ENTITY",
        "ENSURE_LAYER", "ENSURE_TEXT_STYLE", "ENSURE_DIMENSION_STYLE",
        "S6_EXECUTE_SYNTHETIC_PLAN",
    }
)


class RealAutoCadComBackendError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None,
                 stage: str | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.details = dict(details or {})
        self.stage = stage


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", f"{name} 必须为有限数值")
    if abs(number) > 100_000:
        raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", f"{name} 超出 S5 合成坐标范围")
    return number


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        object.__setattr__(self, "z", _finite(self.z, "z"))

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.z]


def _operation_key(value: str) -> str:
    key = str(value).strip()
    if not key or len(key) > 160:
        raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "operation_key 无效")
    return key


@dataclass(frozen=True)
class LineSpec:
    start: Point3
    end: Point3
    layer: str = S5_LAYER
    operation_key: str = ""

    def __post_init__(self) -> None:
        if self.start == self.end:
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "Line 起终点不得相同")
        object.__setattr__(self, "operation_key", _operation_key(self.operation_key))
        if self.layer != S5_LAYER:
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "S5 仅允许专用图层")

    def geometry(self) -> dict[str, Any]:
        return {"start": self.start.as_list(), "end": self.end.as_list()}


@dataclass(frozen=True)
class CircleSpec:
    center: Point3
    radius: float
    layer: str = S5_LAYER
    operation_key: str = ""

    def __post_init__(self) -> None:
        radius = _finite(self.radius, "radius")
        if radius <= 0:
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "Circle 半径必须大于 0")
        object.__setattr__(self, "radius", radius)
        object.__setattr__(self, "operation_key", _operation_key(self.operation_key))
        if self.layer != S5_LAYER:
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "S5 仅允许专用图层")

    def geometry(self) -> dict[str, Any]:
        return {"center": self.center.as_list(), "radius": self.radius}


@dataclass(frozen=True)
class PolylineSpec:
    vertices: tuple[Point3, ...]
    closed: bool = False
    layer: str = S5_LAYER
    operation_key: str = ""

    def __post_init__(self) -> None:
        vertices = tuple(self.vertices)
        if len(vertices) < 2 or (self.closed and len(vertices) < 3):
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "Polyline 顶点数量无效")
        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "operation_key", _operation_key(self.operation_key))
        if self.layer != S5_LAYER:
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "S5 仅允许专用图层")

    def geometry(self) -> dict[str, Any]:
        return {"vertices": [point.as_list() for point in self.vertices], "closed": self.closed}


def _canonical_geometry_value(value: Any) -> Any:
    """将 COM 重开后的 list/tuple/int/float 差异归一为稳定 JSON 值。

    AutoCAD COM 经保存重开后可能把 tuple 变为 list，并把 ``0`` 表示为
    ``0.0``。指纹只用于 S5 固定合成几何的同一性判定，因此使用有限浮点的
    17 位通用表示以保持二进制 double 的可重复性；原始 geometry 仍原样保留
    在 EntityRecord/Evidence 中。
    """
    if isinstance(value, Mapping):
        return {str(key): _canonical_geometry_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_geometry_value(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "几何指纹包含非有限数值")
        return format(number, ".17g")
    raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "几何指纹包含不支持的数据类型")


def geometry_fingerprint(entity_type: str, geometry: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"entity_type": str(entity_type).lower(), "geometry": _canonical_geometry_value(geometry)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SyntheticAutoCadDocumentIdentity:
    run_id: str
    job_id: str
    plan_hash: str
    canonical_path: str
    ownership_token: str
    created_at: str
    synthetic: bool = True
    user_document: bool = False
    source_document: None = None


class DocumentOwnershipRegistry:
    """内存中的 S5 所有权账本；不从磁盘反查或猜测用户文档。"""

    def __init__(self, artifact_root: str | Path) -> None:
        self._root = Path(artifact_root).resolve(strict=False)
        self._items: dict[str, SyntheticAutoCadDocumentIdentity] = {}

    def reserve(self, *, run_id: str, job_id: str, plan_hash: str, output_path: str | Path) -> SyntheticAutoCadDocumentIdentity:
        path = Path(output_path).resolve(strict=False)
        sandbox = (self._root / "sandbox").resolve(strict=False)
        if path.suffix.lower() != ".dwg" or path.parent != sandbox:
            raise RealAutoCadComBackendError("REAL_CAD_ACCESS_SCOPE_VIOLATION", "合成文档必须位于当前 artifacts/sandbox 根目录")
        identity = SyntheticAutoCadDocumentIdentity(
            run_id=str(run_id), job_id=str(job_id), plan_hash=str(plan_hash), canonical_path=str(path),
            ownership_token=uuid4().hex, created_at=_utc_now(),
        )
        self._items[identity.ownership_token] = identity
        return identity

    def verify(self, identity: SyntheticAutoCadDocumentIdentity, *, job_id: str, plan_hash: str) -> None:
        actual = self._items.get(identity.ownership_token)
        if actual != identity or identity.job_id != job_id or identity.plan_hash != plan_hash or not identity.synthetic or identity.user_document:
            raise RealAutoCadComBackendError("AUTOCAD_DOCUMENT_IDENTITY_MISMATCH", "合成文档身份或所有权不匹配")


@dataclass
class L3SyntheticSandboxApproval:
    job_id: str
    plan_hash: str
    document_token: str
    allowed_operations: frozenset[str]
    expires_at: datetime
    backend: str = S5_BACKEND
    product: str = S5_PRODUCT
    runtime: str = S5_RUNTIME
    safety_level: str = S5_SAFETY_LEVEL
    single_use: bool = True
    consumed: set[str] = field(default_factory=set)

    def authorize(self, *, identity: SyntheticAutoCadDocumentIdentity, operation: str) -> None:
        if (self.backend, self.product, self.runtime, self.safety_level) != (S5_BACKEND, S5_PRODUCT, S5_RUNTIME, S5_SAFETY_LEVEL):
            raise RealAutoCadComBackendError("APPROVAL_SCOPE_MISMATCH", "S5 审批范围不匹配")
        if self.job_id != identity.job_id or self.plan_hash != identity.plan_hash or self.document_token != identity.ownership_token:
            raise RealAutoCadComBackendError("APPROVAL_SCOPE_MISMATCH", "审批未绑定当前合成文档")
        if datetime.now(timezone.utc) >= self.expires_at.astimezone(timezone.utc):
            raise RealAutoCadComBackendError("APPROVAL_EXPIRED", "S5 审批已过期")
        if operation not in self.allowed_operations or operation not in S5_ALLOWED_OPERATIONS:
            raise RealAutoCadComBackendError("APPROVAL_OPERATION_FORBIDDEN", f"审批不允许操作: {operation}")
        if self.single_use and operation in self.consumed:
            raise RealAutoCadComBackendError("APPROVAL_SINGLE_USE_CONSUMED", f"操作已消耗: {operation}")
        if self.single_use:
            self.consumed.add(operation)


class AutoCadComSandboxGateway(Protocol):
    """唯一可触达 COM 的边界；其真实实现留给受控 transport。"""

    def create_synthetic(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]: ...
    def document_snapshot(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]: ...
    def ensure_layer(self, identity: SyntheticAutoCadDocumentIdentity, layer: str) -> None: ...
    def create_line(self, identity: SyntheticAutoCadDocumentIdentity, spec: LineSpec) -> Mapping[str, Any]: ...
    def create_circle(self, identity: SyntheticAutoCadDocumentIdentity, spec: CircleSpec) -> Mapping[str, Any]: ...
    def create_polyline(self, identity: SyntheticAutoCadDocumentIdentity, spec: PolylineSpec) -> Mapping[str, Any]: ...
    def list_entities(self, identity: SyntheticAutoCadDocumentIdentity) -> Sequence[Mapping[str, Any]]: ...
    def save(self, identity: SyntheticAutoCadDocumentIdentity) -> None: ...
    def close(self, identity: SyntheticAutoCadDocumentIdentity) -> None: ...
    def reopen(self, identity: SyntheticAutoCadDocumentIdentity) -> None: ...
    def quit_if_job_owned(self) -> None: ...


@dataclass(frozen=True)
class EntityRecord:
    handle: str
    object_name: str
    entity_type: str
    layer: str
    geometry: Mapping[str, Any]
    operation_key: str
    geometry_fingerprint: str
    document_identity: str
    created_by_job: str
    verification_status: str


class RealAutoCadComBackend:
    """只支持 S5 合成 Sandbox 的可注入后端，不含真实 COM 导入。"""

    def __init__(self, *, gateway: AutoCadComSandboxGateway, artifact_root: str | Path, registry: DocumentOwnershipRegistry | None = None) -> None:
        self._gateway = gateway
        self._registry = registry or DocumentOwnershipRegistry(artifact_root)

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "backend": S5_BACKEND, "support_level": "AVAILABLE_SANDBOX_MVP",
            "synthetic_only": True, "user_dwg_access": "FORBIDDEN", "production_write": "FORBIDDEN",
            "supported_entities": ["line", "circle", "polyline", "arc", "rectangle", "text", "mtext", "block_definition", "block_reference"],
            "supported_operations": ["query", "move", "copy", "rotate", "scale", "delete", "ensure_layer", "ensure_text_style", "ensure_dimension_style"],
            "tianzheng_support": "NOT_IMPLEMENTED", "transactional_rollback": "NOT_AVAILABLE",
            "batch_semantics": "BEST_EFFORT_REAL__ALL_OR_NOTHING_MOCK_ONLY", "real_cad_access": "EXPLICIT_INTEGRATION_ONLY",
        }

    def reserve_synthetic_document(self, *, run_id: str, job_id: str, plan_hash: str, output_path: str | Path) -> SyntheticAutoCadDocumentIdentity:
        return self._registry.reserve(run_id=run_id, job_id=job_id, plan_hash=plan_hash, output_path=output_path)

    def create_synthetic_document(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval) -> Mapping[str, Any]:
        self._authorize(identity, approval, "CREATE_SYNTHETIC_DOCUMENT")
        # 首次 Documents.Add 前 gateway 尚不可能持有 document；此处只验证
        # registry/L3 绑定，创建完成后立即再执行完整 snapshot 身份校验。
        self._registry.verify(identity, job_id=identity.job_id, plan_hash=identity.plan_hash)
        created = dict(self._gateway.create_synthetic(identity))
        self._verify(identity)
        return created

    def query_entities(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval) -> list[EntityRecord]:
        self._authorize(identity, approval, "QUERY_ENTITY")
        self._verify(identity)
        return [self._record(identity, raw) for raw in self._gateway.list_entities(identity)]

    def create_line(self, identity: SyntheticAutoCadDocumentIdentity, spec: LineSpec, approval: L3SyntheticSandboxApproval) -> tuple[str, EntityRecord]:
        return self._create(identity, spec, approval, "CREATE_LINE", "line")

    def create_circle(self, identity: SyntheticAutoCadDocumentIdentity, spec: CircleSpec, approval: L3SyntheticSandboxApproval) -> tuple[str, EntityRecord]:
        return self._create(identity, spec, approval, "CREATE_CIRCLE", "circle")

    def create_polyline(self, identity: SyntheticAutoCadDocumentIdentity, spec: PolylineSpec, approval: L3SyntheticSandboxApproval) -> tuple[str, EntityRecord]:
        return self._create(identity, spec, approval, "CREATE_POLYLINE", "polyline")

    def save_document(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval) -> None:
        self._authorize(identity, approval, "SAVE_SYNTHETIC_DOCUMENT"); self._verify(identity); self._gateway.save(identity)

    def close_document(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval) -> None:
        self._authorize(identity, approval, "CLOSE_SYNTHETIC_DOCUMENT"); self._verify(identity); self._gateway.close(identity)

    def reopen_document(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval) -> None:
        self._authorize(identity, approval, "REOPEN_SYNTHETIC_DOCUMENT")
        # Close 后 gateway 按约定不再持有 Document 引用；若在 Open 前调用
        # _verify() 会把合法的关闭状态误判为身份缺失。重开前仅校验内存
        # ownership/L3 绑定，Open 成功后立即执行完整文档身份校验。
        self._registry.verify(identity, job_id=identity.job_id, plan_hash=identity.plan_hash)
        self._gateway.reopen(identity)
        self._verify(identity)

    def verify_persistence(self, identity: SyntheticAutoCadDocumentIdentity, expected: Sequence[EntityRecord], approval: L3SyntheticSandboxApproval) -> bool:
        self._authorize(identity, approval, "VERIFY_SYNTHETIC_DOCUMENT")
        self._verify(identity)
        found = {(item.operation_key, item.geometry_fingerprint) for item in (self._record(identity, raw) for raw in self._gateway.list_entities(identity))}
        expected_keys = {(item.operation_key, item.geometry_fingerprint) for item in expected}
        if not expected_keys.issubset(found):
            raise RealAutoCadComBackendError("AUTOCAD_PERSISTENCE_VERIFICATION_FAILED", "重开后实体几何或 operation_key 不一致")
        return True

    def normal_shutdown(self) -> None:
        """仅委托 gateway 对已确认的 job-owned 会话执行正常 Quit。"""
        self._gateway.quit_if_job_owned()

    def s4_execution_descriptor(self, identity: SyntheticAutoCadDocumentIdentity) -> dict[str, Any]:
        self._verify(identity)
        return {
            "backend": S5_BACKEND, "execution_mode": "com_activation", "synthetic": True,
            "document_identity": {"canonical_path": identity.canonical_path, "ownership_token": identity.ownership_token},
            "job_id": identity.job_id, "plan_hash": identity.plan_hash, "approval_required": True,
            "tool_status": "INTERFACE_ONLY_UNVALIDATED", "limitations": self.capabilities(),
        }

    @staticmethod
    def s4_capability_gate(*, external_integration_verified: bool) -> dict[str, Any]:
        """S4 不可仅因代码存在而暴露真实 COM Tool。"""
        return {
            "backend": S5_BACKEND,
            "available": bool(external_integration_verified),
            "support_level": "AVAILABLE_SANDBOX_MVP" if external_integration_verified else "NOT_IMPLEMENTED_UNVALIDATED",
            "production_allowed": False,
            "user_dwg_access": "FORBIDDEN",
            "reason": "必须由显式 S5 synthetic 外部集成证据开启",
        }

    def _create(self, identity: SyntheticAutoCadDocumentIdentity, spec: Any, approval: L3SyntheticSandboxApproval, operation: str, entity_type: str) -> tuple[str, EntityRecord]:
        self._authorize(identity, approval, operation); self._verify(identity)
        fingerprint = geometry_fingerprint(entity_type, spec.geometry())
        for raw in self._gateway.list_entities(identity):
            record = self._record(identity, raw)
            if record.operation_key == spec.operation_key:
                if record.geometry_fingerprint == fingerprint and record.entity_type == entity_type:
                    return "ALREADY_APPLIED", record
                raise RealAutoCadComBackendError("AUTOCAD_IDEMPOTENCY_FAILED", "operation_key 已被不同几何占用")
        self._gateway.ensure_layer(identity, S5_LAYER)
        creator = getattr(self._gateway, f"create_{entity_type}")
        return "CREATED", self._record(identity, creator(identity, spec), fallback_type=entity_type, fallback_geometry=spec.geometry(), operation_key=spec.operation_key)

    def _verify(self, identity: SyntheticAutoCadDocumentIdentity) -> None:
        self._registry.verify(identity, job_id=identity.job_id, plan_hash=identity.plan_hash)
        snapshot = dict(self._gateway.document_snapshot(identity))
        if snapshot.get("synthetic") is not True or snapshot.get("user_document") is True or snapshot.get("canonical_path") != identity.canonical_path:
            raise RealAutoCadComBackendError("AUTOCAD_DOCUMENT_IDENTITY_MISMATCH", "gateway 文档快照不属于当前合成文档")

    @staticmethod
    def _authorize(identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval, operation: str) -> None:
        approval.authorize(identity=identity, operation=operation)

    @staticmethod
    def _record(identity: SyntheticAutoCadDocumentIdentity, raw: Mapping[str, Any], *, fallback_type: str = "", fallback_geometry: Mapping[str, Any] | None = None, operation_key: str = "") -> EntityRecord:
        entity_type = str(raw.get("entity_type", fallback_type)).lower()
        geometry = dict(raw.get("geometry", fallback_geometry or {}))
        key = str(raw.get("operation_key", operation_key))
        if not entity_type or not key:
            raise RealAutoCadComBackendError("AUTOCAD_ENTITY_VALIDATION_FAILED", "COM gateway 未返回必要实体身份")
        return EntityRecord(handle=str(raw.get("handle", "")), object_name=str(raw.get("object_name", "")), entity_type=entity_type,
            layer=str(raw.get("layer", S5_LAYER)), geometry=geometry, operation_key=key,
            geometry_fingerprint=str(raw.get("geometry_fingerprint", geometry_fingerprint(entity_type, geometry))),
            document_identity=identity.ownership_token, created_by_job=identity.job_id,
            verification_status=str(raw.get("verification_status", "VERIFIED")))

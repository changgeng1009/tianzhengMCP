"""NextGen backend 隔离模型。

本模块只包含可序列化纯数据，不持有 COM、AutoCAD document 或其他 native handle。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from mcp_nextgen.protocol.enums import BackendKind, DocumentRole
from mcp_nextgen.protocol.models import DocumentIdentity
from mcp_nextgen.protocol.version import PROTOCOL_VERSION


@dataclass(frozen=True)
class BackendCapability:
    """backend 能力声明；Mock/Legacy/Real 的身份不可互换。"""

    capability_id: str
    operation: str
    backend_kind: BackendKind
    available: bool
    production_allowed: bool = False
    dry_run: bool = True
    real_cad_execution: bool = False
    real_dwg_modified: bool = False
    schema_version: str = PROTOCOL_VERSION
    evidence_paths: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_VERSION:
            raise ValueError("backend capability 协议版本不匹配")
        if self.backend_kind is BackendKind.MOCK:
            if self.production_allowed or self.real_cad_execution or self.real_dwg_modified:
                raise ValueError("Mock capability 不得宣称生产或真实 CAD/DWG 能力")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["backend_kind"] = self.backend_kind.value
        value["evidence_paths"] = list(self.evidence_paths)
        return value


@dataclass
class BackendSession:
    session_id: str
    backend_kind: BackendKind
    document_id: str
    opened_identity: DocumentIdentity
    connected: bool = True
    document_open: bool = True
    manual_save_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "backend_kind": self.backend_kind.value,
            "document_id": self.document_id,
            "opened_identity": self.opened_identity.to_dict(),
            "connected": self.connected,
            "document_open": self.document_open,
            "manual_save_required": self.manual_save_required,
        }


@dataclass
class MockEntity:
    entity_id: str
    entity_type: str
    geometry: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    protected_region_ids: list[str] = field(default_factory=list)
    automatic_dependency: bool = False
    revision: int = 0

    def clone(self, new_entity_id: str) -> "MockEntity":
        from copy import deepcopy

        value = deepcopy(self)
        value.entity_id = new_entity_id
        value.revision = 0
        value.properties["source_entity_id"] = self.entity_id
        return value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProtectedRegion:
    region_id: str
    bbox: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not self.region_id:
            raise ValueError("region_id 不能为空")
        x1, y1, x2, y2 = self.bbox
        if x1 > x2 or y1 > y2:
            raise ValueError("protected region bbox 必须按 min/max 排列")


@dataclass(frozen=True)
class FailureInjection:
    """按调用序号触发的确定性故障。"""

    operation: str
    occurrence: int = 1
    error_code: str = "MOCK_FAILURE_INJECTED"
    message: str = "Mock 故障注入"
    document_id: str | None = None
    batch_id: str | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        if not self.operation:
            raise ValueError("failure operation 不能为空")
        if self.occurrence < 1:
            raise ValueError("failure occurrence 必须大于等于 1")


@dataclass(frozen=True)
class BackendExecutionContext:
    request_id: str
    job_id: str
    idempotency_key: str
    dry_run: bool = False
    production_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.request_id or not self.job_id or not self.idempotency_key:
            raise ValueError("backend execution context 缺少 request/job/idempotency")
        if self.production_allowed:
            raise ValueError("当前 backend 基线禁止 production_allowed=true")


def mock_document_identity(
    *,
    document_id: str,
    document_full_path: str,
    document_sha256: str,
    read_only: bool,
    created_at: str,
) -> DocumentIdentity:
    return DocumentIdentity(
        document_full_path=document_full_path,
        document_sha256=document_sha256,
        document_role=DocumentRole.MOCK_DOCUMENT,
        document_id=document_id,
        backend_kind=BackendKind.MOCK,
        read_only=read_only,
        created_at=created_at,
    )

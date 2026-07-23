"""S5 RealAutoCadComBackend 的纯 Fake Gateway 单元测试。

不导入 win32com，不启动 AutoCAD，也不创建、打开或读取 DWG 文件；`tmp_path`
中的 .dwg 仅作为尚未落盘的 synthetic identity 字符串。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any, Mapping

import pytest

from mcp_nextgen.backends.real_autocad_com import (
    S5_ALLOWED_OPERATIONS,
    CircleSpec,
    DocumentOwnershipRegistry,
    L3SyntheticSandboxApproval,
    LineSpec,
    Point3,
    PolylineSpec,
    RealAutoCadComBackend,
    RealAutoCadComBackendError,
    SyntheticAutoCadDocumentIdentity,
    geometry_fingerprint,
)


class FakeSandboxGateway:
    """内存 gateway；所有“持久化”只发生在 Python list 深拷贝中。"""

    def __init__(self) -> None:
        self.identity: SyntheticAutoCadDocumentIdentity | None = None
        self.entities: list[dict[str, Any]] = []
        self.saved_entities: list[dict[str, Any]] = []
        self.created = False
        self.closed = False
        self.layer_calls: list[str] = []
        self.quit_calls = 0

    def _snapshot(self, identity: SyntheticAutoCadDocumentIdentity) -> dict[str, Any]:
        return {
            "synthetic": True,
            "user_document": False,
            "canonical_path": identity.canonical_path,
        }

    def create_synthetic(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]:
        self.identity = identity
        self.created = True
        return self._snapshot(identity)

    def document_snapshot(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]:
        if self.closed:
            raise AssertionError("关闭后、重开前不得读取 Document snapshot")
        return self._snapshot(identity)

    def ensure_layer(self, _identity: SyntheticAutoCadDocumentIdentity, layer: str) -> None:
        self.layer_calls.append(layer)

    def _create(self, entity_type: str, identity: SyntheticAutoCadDocumentIdentity, spec: Any) -> Mapping[str, Any]:
        raw = {
            "handle": f"H{len(self.entities) + 1}",
            "object_name": {"line": "AcDbLine", "circle": "AcDbCircle", "polyline": "AcDbPolyline"}[entity_type],
            "entity_type": entity_type,
            "layer": spec.layer,
            "geometry": spec.geometry(),
            "operation_key": spec.operation_key,
            "verification_status": "VERIFIED",
        }
        self.entities.append(raw)
        return raw

    def create_line(self, identity: SyntheticAutoCadDocumentIdentity, spec: LineSpec) -> Mapping[str, Any]:
        return self._create("line", identity, spec)

    def create_circle(self, identity: SyntheticAutoCadDocumentIdentity, spec: CircleSpec) -> Mapping[str, Any]:
        return self._create("circle", identity, spec)

    def create_polyline(self, identity: SyntheticAutoCadDocumentIdentity, spec: PolylineSpec) -> Mapping[str, Any]:
        return self._create("polyline", identity, spec)

    def list_entities(self, _identity: SyntheticAutoCadDocumentIdentity):
        return deepcopy(self.entities)

    def save(self, _identity: SyntheticAutoCadDocumentIdentity) -> None:
        self.saved_entities = deepcopy(self.entities)

    def close(self, _identity: SyntheticAutoCadDocumentIdentity) -> None:
        self.closed = True

    def reopen(self, _identity: SyntheticAutoCadDocumentIdentity) -> None:
        self.closed = False
        self.entities = deepcopy(self.saved_entities)

    def quit_if_job_owned(self) -> None:
        self.quit_calls += 1


class FirstCreateStrictGateway(FakeSandboxGateway):
    """首次创建前不允许 backend 读取尚不存在的 Document snapshot。"""

    def __init__(self, *, mismatch_after_create: bool = False) -> None:
        super().__init__()
        self.create_calls = 0
        self.snapshot_calls = 0
        self.mismatch_after_create = mismatch_after_create

    def create_synthetic(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]:
        self.create_calls += 1
        return super().create_synthetic(identity)

    def document_snapshot(self, identity: SyntheticAutoCadDocumentIdentity) -> Mapping[str, Any]:
        self.snapshot_calls += 1
        if not self.created:
            raise AssertionError("首次 Documents.Add 前不得读取 Document snapshot")
        if self.mismatch_after_create:
            return {"synthetic": False, "user_document": True, "canonical_path": r"C:\\foreign\\drawing.dwg"}
        return super().document_snapshot(identity)


def _identity(tmp_path: Path) -> tuple[RealAutoCadComBackend, FakeSandboxGateway, SyntheticAutoCadDocumentIdentity]:
    gateway = FakeSandboxGateway()
    registry = DocumentOwnershipRegistry(tmp_path)
    backend = RealAutoCadComBackend(gateway=gateway, artifact_root=tmp_path, registry=registry)
    identity = backend.reserve_synthetic_document(
        run_id="s5-unit-run",
        job_id="s5-unit-job",
        plan_hash="a" * 64,
        output_path=tmp_path / "sandbox" / "s5_synthetic_autocad_mvp.dwg",
    )
    return backend, gateway, identity


def _approval(identity: SyntheticAutoCadDocumentIdentity, *operations: str) -> L3SyntheticSandboxApproval:
    return L3SyntheticSandboxApproval(
        job_id=identity.job_id,
        plan_hash=identity.plan_hash,
        document_token=identity.ownership_token,
        allowed_operations=frozenset(operations),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )


def test_dtos_reject_nonfinite_invalid_geometry_and_non_s5_layer() -> None:
    with pytest.raises(RealAutoCadComBackendError, match="有限"):
        Point3(math.nan, 0, 0)
    with pytest.raises(RealAutoCadComBackendError, match="不得相同"):
        LineSpec(Point3(0, 0), Point3(0, 0), operation_key="line")
    with pytest.raises(RealAutoCadComBackendError, match="半径"):
        CircleSpec(Point3(0, 0), 0, operation_key="circle")
    with pytest.raises(RealAutoCadComBackendError, match="顶点"):
        PolylineSpec((Point3(0, 0), Point3(1, 0)), closed=True, operation_key="poly")
    with pytest.raises(RealAutoCadComBackendError, match="专用图层"):
        LineSpec(Point3(0, 0), Point3(1, 0), layer="0", operation_key="line")


def test_geometry_fingerprint_normalizes_com_reopen_list_tuple_and_numeric_shapes() -> None:
    created = {
        "start": (0, 0, 0),
        "end": (1000, 0, 0),
        "nested": {"radius": 500},
    }
    reopened = {
        "start": [0.0, 0.0, 0.0],
        "end": [1000.0, 0.0, 0.0],
        "nested": {"radius": 500.0},
    }
    assert geometry_fingerprint("LINE", created) == geometry_fingerprint("line", reopened)


def test_registry_rejects_non_sandbox_or_tampered_document_identity(tmp_path: Path) -> None:
    backend, _gateway, identity = _identity(tmp_path)
    with pytest.raises(RealAutoCadComBackendError) as error:
        backend.reserve_synthetic_document(
            run_id="run", job_id="job", plan_hash="b" * 64,
            output_path=tmp_path / "not-sandbox.dwg",
        )
    assert error.value.code == "REAL_CAD_ACCESS_SCOPE_VIOLATION"
    tampered = replace(identity, plan_hash="c" * 64)
    approval = _approval(tampered, "CREATE_SYNTHETIC_DOCUMENT")
    with pytest.raises(RealAutoCadComBackendError) as mismatch:
        backend.create_synthetic_document(tampered, approval)
    assert mismatch.value.code == "AUTOCAD_DOCUMENT_IDENTITY_MISMATCH"


def test_l3_approval_is_exact_document_bound_and_single_use(tmp_path: Path) -> None:
    backend, _gateway, identity = _identity(tmp_path)
    wrong = _approval(replace(identity, job_id="other"), "CREATE_SYNTHETIC_DOCUMENT")
    with pytest.raises(RealAutoCadComBackendError) as mismatch:
        backend.create_synthetic_document(identity, wrong)
    assert mismatch.value.code == "APPROVAL_SCOPE_MISMATCH"
    approval = _approval(identity, "CREATE_SYNTHETIC_DOCUMENT")
    backend.create_synthetic_document(identity, approval)
    with pytest.raises(RealAutoCadComBackendError) as consumed:
        backend.create_synthetic_document(identity, approval)
    assert consumed.value.code == "APPROVAL_SINGLE_USE_CONSUMED"
    expired = L3SyntheticSandboxApproval(
        job_id=identity.job_id, plan_hash=identity.plan_hash, document_token=identity.ownership_token,
        allowed_operations=frozenset({"QUERY_ENTITY"}), expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(RealAutoCadComBackendError) as expired_error:
        backend.query_entities(identity, expired)
    assert expired_error.value.code == "APPROVAL_EXPIRED"


def test_first_synthetic_create_skips_preopen_snapshot_and_verifies_identity_after_add(tmp_path: Path) -> None:
    gateway = FirstCreateStrictGateway()
    registry = DocumentOwnershipRegistry(tmp_path)
    backend = RealAutoCadComBackend(gateway=gateway, artifact_root=tmp_path, registry=registry)
    identity = backend.reserve_synthetic_document(
        run_id="first-create", job_id="first-job", plan_hash="a" * 64,
        output_path=tmp_path / "sandbox" / "s5_synthetic_autocad_mvp.dwg",
    )
    backend.create_synthetic_document(identity, _approval(identity, "CREATE_SYNTHETIC_DOCUMENT"))
    assert gateway.create_calls == 1
    assert gateway.snapshot_calls == 1


def test_first_synthetic_create_fails_closed_when_postadd_identity_snapshot_mismatches(tmp_path: Path) -> None:
    gateway = FirstCreateStrictGateway(mismatch_after_create=True)
    registry = DocumentOwnershipRegistry(tmp_path)
    backend = RealAutoCadComBackend(gateway=gateway, artifact_root=tmp_path, registry=registry)
    identity = backend.reserve_synthetic_document(
        run_id="first-create-mismatch", job_id="first-job", plan_hash="a" * 64,
        output_path=tmp_path / "sandbox" / "s5_synthetic_autocad_mvp.dwg",
    )
    with pytest.raises(RealAutoCadComBackendError) as error:
        backend.create_synthetic_document(identity, _approval(identity, "CREATE_SYNTHETIC_DOCUMENT"))
    assert error.value.code == "AUTOCAD_DOCUMENT_IDENTITY_MISMATCH"
    assert gateway.create_calls == 1
    assert gateway.snapshot_calls == 1


def test_create_query_save_close_reopen_persistence_and_idempotency(tmp_path: Path) -> None:
    backend, gateway, identity = _identity(tmp_path)
    backend.create_synthetic_document(identity, _approval(identity, "CREATE_SYNTHETIC_DOCUMENT"))
    line = LineSpec(Point3(0, 0), Point3(1000, 0), operation_key="line-1")
    circle = CircleSpec(Point3(2000, 0), 500, operation_key="circle-1")
    polyline = PolylineSpec(
        (Point3(0, 1500), Point3(1000, 1500), Point3(1000, 2500), Point3(0, 2500)),
        closed=True,
        operation_key="poly-1",
    )
    status_line, record_line = backend.create_line(identity, line, _approval(identity, "CREATE_LINE"))
    status_circle, record_circle = backend.create_circle(identity, circle, _approval(identity, "CREATE_CIRCLE"))
    status_poly, record_poly = backend.create_polyline(identity, polyline, _approval(identity, "CREATE_POLYLINE"))
    assert (status_line, status_circle, status_poly) == ("CREATED", "CREATED", "CREATED")
    assert {item.entity_type for item in backend.query_entities(identity, _approval(identity, "QUERY_ENTITY"))} == {
        "line", "circle", "polyline"
    }
    backend.save_document(identity, _approval(identity, "SAVE_SYNTHETIC_DOCUMENT"))
    backend.close_document(identity, _approval(identity, "CLOSE_SYNTHETIC_DOCUMENT"))
    backend.reopen_document(identity, _approval(identity, "REOPEN_SYNTHETIC_DOCUMENT"))
    assert backend.verify_persistence(
        identity, [record_line, record_circle, record_poly], _approval(identity, "VERIFY_SYNTHETIC_DOCUMENT")
    ) is True
    status_retry, retry = backend.create_line(identity, line, _approval(identity, "CREATE_LINE"))
    assert status_retry == "ALREADY_APPLIED"
    assert retry.handle == record_line.handle
    assert len(gateway.entities) == 3
    changed = LineSpec(Point3(0, 0), Point3(999, 0), operation_key="line-1")
    with pytest.raises(RealAutoCadComBackendError) as collision:
        backend.create_line(identity, changed, _approval(identity, "CREATE_LINE"))
    assert collision.value.code == "AUTOCAD_IDEMPOTENCY_FAILED"
    assert gateway.layer_calls == ["CADAGENT_S5_MVP", "CADAGENT_S5_MVP", "CADAGENT_S5_MVP"]


def test_descriptor_mcp_gate_and_capability_do_not_claim_production(tmp_path: Path) -> None:
    backend, gateway, identity = _identity(tmp_path)
    descriptor = backend.s4_execution_descriptor(identity)
    assert descriptor["backend"] == "real_autocad_com"
    assert descriptor["execution_mode"] == "com_activation"
    assert descriptor["synthetic"] is True
    assert descriptor["approval_required"] is True
    assert descriptor["tool_status"] == "INTERFACE_ONLY_UNVALIDATED"
    capabilities = backend.capabilities()
    assert capabilities["synthetic_only"] is True
    assert capabilities["user_dwg_access"] == "FORBIDDEN"
    assert capabilities["production_write"] == "FORBIDDEN"
    assert set(S5_ALLOWED_OPERATIONS) >= {"CREATE_LINE", "CREATE_CIRCLE", "CREATE_POLYLINE"}
    backend.normal_shutdown()
    assert gateway.quit_calls == 1

"""显式 S5 外部集成编排器；默认调用即拒绝，避免测试意外启动 AutoCAD。"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

from .autocad_com_activation import (
    ComActivationSessionHost, IsolatedComActivator, RealComLaunchPolicy,
    read_with_startup_busy_retry,
)
from .autocad_com_gateway import LazyPywin32SafeArrayAdapter, Pywin32AutoCadSandboxGateway
from .autocad_launcher import (
    AutoCadJobOwnedSessionGuard, AutoCadProcessIdentity, AutoCadProcessOwnershipRegistry,
    AutoCadSessionIdentity, WindowsAcadProcessInspector, WindowsHwndPidResolver,
    WindowsProcessIdentityInspector,
)
from .real_autocad_com import (
    CircleSpec, L3SyntheticSandboxApproval, LineSpec, Point3, PolylineSpec,
    RealAutoCadComBackend, RealAutoCadComBackendError, S5_ALLOWED_OPERATIONS,
)


def run_s5_synthetic_mvp(*, artifact_root: str | Path, run_id: str, job_id: str, plan_hash: str,
                         integration_enabled: bool, client_importer: Any, progid: str = "AutoCAD.Application.25.1",
                         expected_executable: str = r"E:\AutoCAD 2026\acad.exe",
                         process_inspector: Any | None = None, hwnd_pid_resolver: Any | None = None,
                         process_identity_inspector: Any | None = None) -> dict[str, Any]:
    """完成唯一允许的三实体 synthetic 闭环；调用方必须显式开启外部集成门。"""
    if not integration_enabled:
        raise RealAutoCadComBackendError("S5_EXTERNAL_INTEGRATION_DISABLED", "必须显式启用 S5 外部集成")
    root = Path(artifact_root).resolve(strict=False)
    inspect_processes = process_inspector or WindowsAcadProcessInspector()
    before = tuple(inspect_processes())
    if before:
        raise RealAutoCadComBackendError("CAD_S5_BLOCKED_BY_ACTIVE_USER_DOCUMENT", "启动前已存在 acad.exe，拒绝附着")
    ownership = AutoCadProcessOwnershipRegistry()
    hwnd_to_pid = hwnd_pid_resolver or WindowsHwndPidResolver()
    inspect_identity = process_identity_inspector or WindowsProcessIdentityInspector()
    backend: RealAutoCadComBackend | None = None
    gateway: Pywin32AutoCadSandboxGateway | None = None
    identity = None
    session_verified = False
    shutdown_complete = False
    process_identity_verification = "OS_VERIFIED"
    stage = "COM_ACTIVATION"
    with ComActivationSessionHost(policy=RealComLaunchPolicy()).activation_context():
        try:
            application = IsolatedComActivator(client_importer=client_importer).activate(progid)
            stage = "COM_VERSION"
            version = read_with_startup_busy_retry(lambda: str(application.Version))
            if not version.startswith("25"):
                raise RealAutoCadComBackendError("AUTOCAD_VERSION_MISMATCH", f"仅允许 AutoCAD 2026，实际版本: {version}")
            stage = "COM_PROCESS_IDENTITY"
            after_activation = tuple(inspect_processes())
            hwnd = read_with_startup_busy_retry(lambda: int(application.HWND))
            hwnd_pid = int(hwnd_to_pid(hwnd))
            new_pids = {item.pid for item in after_activation} - {item.pid for item in before}
            if hwnd_pid not in new_pids:
                raise RealAutoCadComBackendError("AUTOCAD_SESSION_UNSAFE", "COM HWND 未映射到本次新建 acad.exe")
            process_candidate = AutoCadProcessIdentity(
                job_id=job_id, process_id=hwnd_pid, executable_path=str(Path(expected_executable).resolve(strict=False)),
                process_start_time=time(), launched_by_job=True, ownership_token=uuid4().hex,
            )
            try:
                process = inspect_identity(process_candidate)
            except OSError as exc:
                # 仅允许新 DispatchEx 会话的 COM identity fallback。pre-snapshot
                # 必须为空且 HWND PID 已在本次新增集合；旧/未知会话与 force
                # 路径不得使用这条非生产级替代证据。
                if getattr(exc, "winerror", None) != 5:
                    raise
                application_path = read_with_startup_busy_retry(lambda: str(application.Path))
                actual_executable = (Path(application_path) / "acad.exe").resolve(strict=False)
                expected = Path(expected_executable).resolve(strict=False)
                if before or hwnd_pid not in new_pids or actual_executable != expected or not version.startswith("25"):
                    raise RealAutoCadComBackendError("AUTOCAD_SESSION_UNSAFE", "COM fallback 无法确认新建会话身份") from exc
                process = replace(process_candidate, os_verified_executable_path=str(actual_executable))
                process_identity_verification = "COM_VERIFIED_OS_INSPECTION_UNAVAILABLE"
            ownership.register(process)
            stage = "DEFAULT_DOCUMENT_INSPECTION"
            document_count = read_with_startup_busy_retry(lambda: int(application.Documents.Count))
            session = AutoCadSessionIdentity(job_id=job_id, process=process, com_progid=progid,
                autocad_version=version, document_count=document_count, connected_at=time())
            verification = read_with_startup_busy_retry(
                lambda: AutoCadJobOwnedSessionGuard(ownership=ownership, hwnd_pid_resolver=hwnd_to_pid).verify(session, application)
            )
            if not verification.has_only_new_default_blank_documents:
                raise RealAutoCadComBackendError("AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED", "新会话默认文档状态不安全")
            session_verified = True
        # 已验证为 job-owned 的默认空白文档可以不保存关闭；此后唯一打开的
        # 文档将是 registry 注册的 synthetic 文档。
            stage = "DEFAULT_DOCUMENT_CLOSE"
            for document in application.Documents:
                document.Close(False)
            if read_with_startup_busy_retry(lambda: int(application.Documents.Count)) != 0:
                raise RealAutoCadComBackendError("AUTOCAD_SESSION_UNSAFE", "无法清理已验证的默认空白文档")
            # Real COM 闭环显式选择 VARIANT/SafeArray 封送；默认 gateway
            # 仅服务于 Mock/Fake，绝不在测试时隐式导入 pywin32。
            stage = "SYNTHETIC_DOCUMENT_CREATE"
            gateway = Pywin32AutoCadSandboxGateway(
                application=application,
                array_adapter=LazyPywin32SafeArrayAdapter(),
            )
            backend = RealAutoCadComBackend(gateway=gateway, artifact_root=root)
            identity = backend.reserve_synthetic_document(
            run_id=run_id, job_id=job_id, plan_hash=plan_hash,
            output_path=root / "sandbox" / "s5_synthetic_autocad_mvp.dwg",
        )
            approval = L3SyntheticSandboxApproval(
            job_id=job_id, plan_hash=plan_hash, document_token=identity.ownership_token,
            allowed_operations=S5_ALLOWED_OPERATIONS,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10), single_use=False,
        )
            backend.create_synthetic_document(identity, approval)
            stage = "ENTITY_CREATE"
            created = [
            backend.create_line(identity, LineSpec(Point3(0, 0), Point3(1000, 0), operation_key="s5.line.1"), approval),
            backend.create_circle(identity, CircleSpec(Point3(2000, 0), 500, operation_key="s5.circle.1"), approval),
            backend.create_polyline(identity, PolylineSpec((Point3(0, 1500), Point3(1000, 1500), Point3(1000, 2500), Point3(0, 2500)), True, operation_key="s5.polyline.1"), approval),
        ]
            records = [record for _, record in created]
            stage = "SYNTHETIC_DOCUMENT_SAVE"
            backend.save_document(identity, approval)
            stage = "SYNTHETIC_DOCUMENT_CLOSE"
            backend.close_document(identity, approval)
            stage = "SYNTHETIC_DOCUMENT_REOPEN"
            backend.reopen_document(identity, approval)
            stage = "PERSISTENCE_VERIFICATION"
            backend.verify_persistence(identity, records, approval)
            stage = "IDEMPOTENCY_VERIFICATION"
            idempotent = [
            backend.create_line(identity, LineSpec(Point3(0, 0), Point3(1000, 0), operation_key="s5.line.1"), approval)[0],
            backend.create_circle(identity, CircleSpec(Point3(2000, 0), 500, operation_key="s5.circle.1"), approval)[0],
            backend.create_polyline(identity, PolylineSpec((Point3(0, 1500), Point3(1000, 1500), Point3(1000, 2500), Point3(0, 2500)), True, operation_key="s5.polyline.1"), approval)[0],
        ]
            stage = "FINAL_SYNTHETIC_SAVE"
            backend.save_document(identity, approval)
            stage = "FINAL_SYNTHETIC_CLOSE"
            backend.close_document(identity, approval)
            # AutoCAD 在关闭最后一个 synthetic Document 后可能自动生成一个
            # Drawing*.dwg 空白文档。仍使用同一 Job-owned HWND/PID guard 重新
            # 检查；只有它满足默认空白合同时才 Close(False)，绝不猜测或关闭
            # 任何外部/已命名 Document。
            stage = "POST_CLOSE_DEFAULT_DOCUMENT_INSPECTION"
            post_close_verification = AutoCadJobOwnedSessionGuard(
                ownership=ownership, hwnd_pid_resolver=hwnd_to_pid
            ).verify(session, application)
            if not post_close_verification.has_only_new_default_blank_documents:
                raise RealAutoCadComBackendError(
                    "AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED",
                    "关闭合成文档后出现非默认空白文档",
                    stage=stage,
                )
            for document in application.Documents:
                document.Close(False)
            if read_with_startup_busy_retry(lambda: int(application.Documents.Count)) != 0:
                raise RealAutoCadComBackendError(
                    "AUTOCAD_CLOSE_FAILED",
                    "无法关闭经验证的默认空白文档",
                    stage="POST_CLOSE_DEFAULT_DOCUMENT_CLOSE",
                )
            stage = "NORMAL_SHUTDOWN"
            backend.normal_shutdown()
            shutdown_complete = True
        except Exception as exc:
            # 只有 Phase B 已验证的会话、且 gateway 仍持有注册 synthetic
            # Document 时，才允许 Close(False)；未知身份不得 Close/Quit。
            if session_verified and gateway is not None and identity is not None:
                try:
                    if gateway.has_registered_synthetic_document(identity):
                        gateway.discard_registered_synthetic_document(identity)
                    if read_with_startup_busy_retry(lambda: int(application.Documents.Count)) == 0:
                        gateway.quit_if_job_owned()
                except Exception:
                    pass
            if isinstance(exc, RealAutoCadComBackendError):
                raise
            error_code = str(getattr(exc, "error_code", "") or "S5_INTEGRATION_UNCLASSIFIED_EXCEPTION")
            raise RealAutoCadComBackendError(
                error_code,
                f"S5 synthetic integration failed at {stage}: {exc}",
                details={"exception_type": type(exc).__name__},
                stage=str(getattr(exc, "stage", "") or stage),
            ) from exc
    after_shutdown = tuple(inspect_processes())
    if after_shutdown:
        raise RealAutoCadComBackendError("AUTOCAD_CLOSE_FAILED", "Job-owned AutoCAD 未在正常退出后消失")
    return {
        "synthetic": True, "document": identity.canonical_path, "entities_created": len(records),
        "persistence_verified": True, "idempotency_results": idempotent,
        "backend_capability": "AVAILABLE_SANDBOX_MVP_ONLY_AFTER_EXTERNAL_VERIFICATION",
        "process_identity_verified": True, "post_shutdown_acad_process_count": 0,
        "com_identity": {"progid": progid, "version": version, "process_id": process.process_id,
            "executable_path": process.os_verified_executable_path, "creation_filetime": process.os_process_creation_filetime,
            "verification_level": process_identity_verification},
        "document_identity": {"canonical_path": identity.canonical_path, "run_id": identity.run_id,
            "job_id": identity.job_id, "plan_hash": identity.plan_hash, "synthetic": True, "user_document": False},
    }

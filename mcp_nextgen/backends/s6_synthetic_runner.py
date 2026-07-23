"""显式 S6 Real COM synthetic sandbox 集成编排器。

默认测试绝不调用该入口。调用者必须显式传入 ``integration_enabled=True``，且
启动前不存在任何 acad.exe；该函数只会新建当前 run 的 sandbox DWG。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from time import sleep, time
from typing import Any
from uuid import uuid4

from mcp_nextgen.s6.contracts import CadOperation, CadOperationPlan, CadOperationResult, EntitySelector, EntitySpec
from mcp_nextgen.s6.real_com_executor import S6RealComPlanExecutor

from .autocad_com_activation import ComActivationSessionHost, IsolatedComActivator, RealComLaunchPolicy, read_with_startup_busy_retry
from .autocad_com_gateway import LazyPywin32SafeArrayAdapter, Pywin32AutoCadSandboxGateway
from .autocad_launcher import AutoCadJobOwnedSessionGuard, AutoCadProcessIdentity, AutoCadProcessOwnershipRegistry, AutoCadSessionIdentity, WindowsAcadProcessInspector, WindowsHwndPidResolver, WindowsProcessIdentityInspector
from .real_autocad_com import L3SyntheticSandboxApproval, RealAutoCadComBackend, RealAutoCadComBackendError, S5_ALLOWED_OPERATIONS


def _read_com_startup(operation: Any) -> Any:
    """补齐 DispatchEx 后 dynamic dispatch 尚未填充属性表的短暂窗口。"""
    deadline = time() + 60.0
    last: Exception | None = None
    while time() < deadline:
        try:
            return read_with_startup_busy_retry(operation)
        except AttributeError as exc:
            last = exc
            sleep(1.0)
    raise RealAutoCadComBackendError("AUTOCAD_COM_STARTUP_BUSY_TIMEOUT", "AutoCAD COM 启动期属性未就绪") from last


def _s6_operations() -> tuple[CadOperation, ...]:
    return (
        CadOperation("s6.layer.1", "ENSURE_LAYER", parameters={"layer": {"name": "CADAGENT_S6_MVP", "color_index": 3, "linetype": "Continuous", "lineweight": -1, "visible": True, "locked": False}}),
        CadOperation("s6.textstyle.1", "ENSURE_TEXT_STYLE", parameters={"text_style": {"name": "CADAGENT_S6_TEXT", "font": "txt.shx"}}),
        CadOperation("s6.dimstyle.1", "ENSURE_DIMENSION_STYLE", parameters={"dimension_style": {"name": "CADAGENT_S6_DIM"}}),
        CadOperation("s6.line.1", "CREATE_LINE", EntitySpec("line", {"start": [0, -300], "end": [500, -300]})),
        CadOperation("s6.circle.1", "CREATE_CIRCLE", EntitySpec("circle", {"center": [800, -300], "radius": 120})),
        CadOperation("s6.polyline.1", "CREATE_POLYLINE", EntitySpec("polyline", {"vertices": [[1100, -400], [1300, -200], [1500, -400]], "closed": False})),
        CadOperation("s6.arc.1", "CREATE_ARC", EntitySpec("arc", {"center": [0, 0], "radius": 200, "start_angle": 0.0, "end_angle": 1.57})),
        CadOperation("s6.rectangle.1", "CREATE_RECTANGLE", EntitySpec("rectangle", {"corner_a": [600, 0], "corner_b": [1100, 300]})),
        CadOperation("s6.text.1", "CREATE_TEXT", EntitySpec("text", {"text": "S6 Synthetic", "insertion_point": [0, 600], "height": 80}, style="CADAGENT_S6_TEXT")),
        CadOperation("s6.mtext.1", "CREATE_MTEXT", EntitySpec("mtext", {"content": "S6 synthetic sandbox", "insertion_point": [0, 800], "height": 70, "width": 800}, style="CADAGENT_S6_TEXT")),
        CadOperation("s6.block.def.1", "CREATE_BLOCK_DEFINITION", EntitySpec("block_definition", {"name": "CADAGENT_S6_BLOCK", "entities": [{"kind": "line"}]})),
        CadOperation("s6.block.ref.1", "INSERT_BLOCK_REFERENCE", EntitySpec("block_reference", {"block_name": "CADAGENT_S6_BLOCK", "insertion_point": [1400, 0], "scale": 1.0})),
        CadOperation("s6.move.arc.1", "MOVE_ENTITY", selector=EntitySelector(operation_id="s6.arc.1"), parameters={"displacement": [50, 0, 0]}),
        CadOperation("s6.copy.text.1", "COPY_ENTITY", selector=EntitySelector(operation_id="s6.text.1"), parameters={"displacement": [300, 0, 0]}),
        CadOperation("s6.rotate.rectangle.1", "ROTATE_ENTITY", selector=EntitySelector(operation_id="s6.rectangle.1"), parameters={"base_point": [600, 0, 0], "angle": 0.2}),
        CadOperation("s6.scale.mtext.1", "SCALE_ENTITY", selector=EntitySelector(operation_id="s6.mtext.1"), parameters={"base_point": [0, 800, 0], "scale": 1.1}),
        CadOperation("s6.delete.copy.text.1", "DELETE_ENTITY", selector=EntitySelector(operation_id="s6.copy.text.1")),
        CadOperation("s6.query.final", "QUERY_ENTITIES"),
    )


def run_s6_synthetic_mvp(*, artifact_root: str | Path, run_id: str, job_id: str, integration_enabled: bool,
                          client_importer: Any, progid: str = "AutoCAD.Application.25.1",
                          expected_executable: str = r"E:\AutoCAD 2026\acad.exe",
                          process_inspector: Any | None = None, hwnd_pid_resolver: Any | None = None,
                          process_identity_inspector: Any | None = None) -> dict[str, Any]:
    """在 S5 受控 COM_ACTIVATION 上执行一次完整 S6 real synthetic 闭环。"""
    if not integration_enabled:
        raise RealAutoCadComBackendError("S6_EXTERNAL_INTEGRATION_DISABLED", "必须显式启用 S6 external integration")
    root = Path(artifact_root).resolve(strict=False); sandbox = (root / "sandbox").resolve(strict=False)
    if sandbox.parent != root or not str(root): raise RealAutoCadComBackendError("REAL_CAD_ACCESS_SCOPE_VIOLATION", "S6 artifact root 无效")
    inspect_processes = process_inspector or WindowsAcadProcessInspector(); before = tuple(inspect_processes())
    if before: raise RealAutoCadComBackendError("CAD_S6_BLOCKED_BY_ACTIVE_USER_DOCUMENT", "启动前已存在 acad.exe，拒绝附着")
    preliminary = CadOperationPlan(job_id, "pending", _s6_operations())
    ownership = AutoCadProcessOwnershipRegistry(); hwnd_to_pid = hwnd_pid_resolver or WindowsHwndPidResolver(); inspect_identity = process_identity_inspector or WindowsProcessIdentityInspector()
    gateway: Pywin32AutoCadSandboxGateway | None = None; identity = None; backend = None; session_verified = False; stage = "COM_ACTIVATION"
    with ComActivationSessionHost(policy=RealComLaunchPolicy()).activation_context():
        try:
            application = IsolatedComActivator(client_importer=client_importer).activate(progid)
            version = _read_com_startup(lambda: str(application.Version))
            if not version.startswith("25"): raise RealAutoCadComBackendError("AUTOCAD_VERSION_MISMATCH", f"仅允许 AutoCAD 2026，实际: {version}")
            after = tuple(inspect_processes()); hwnd = read_with_startup_busy_retry(lambda: int(application.HWND)); hwnd_pid = int(hwnd_to_pid(hwnd)); new_pids = {item.pid for item in after} - {item.pid for item in before}
            if hwnd_pid not in new_pids: raise RealAutoCadComBackendError("AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH", "COM HWND 未映射到本次新增实例")
            candidate = AutoCadProcessIdentity(job_id=job_id, process_id=hwnd_pid, executable_path=str(Path(expected_executable).resolve(strict=False)), process_start_time=time(), launched_by_job=True, ownership_token=uuid4().hex)
            try: process = inspect_identity(candidate)
            except OSError as exc:
                if getattr(exc, "winerror", None) != 5: raise
                actual = (Path(read_with_startup_busy_retry(lambda: str(application.Path))) / "acad.exe").resolve(strict=False)
                if actual != Path(expected_executable).resolve(strict=False): raise RealAutoCadComBackendError("AUTOCAD_SESSION_UNSAFE", "COM fallback executable 不匹配") from exc
                process = replace(candidate, os_verified_executable_path=str(actual))
            ownership.register(process); session = AutoCadSessionIdentity(job_id=job_id, process=process, com_progid=progid, autocad_version=version, document_count=read_with_startup_busy_retry(lambda: int(application.Documents.Count)), connected_at=time())
            verification = read_with_startup_busy_retry(lambda: AutoCadJobOwnedSessionGuard(ownership=ownership, hwnd_pid_resolver=hwnd_to_pid).verify(session, application))
            if not verification.has_only_new_default_blank_documents: raise RealAutoCadComBackendError("AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED", "新会话默认文档不安全")
            session_verified = True
            for document in application.Documents: document.Close(False)
            if read_with_startup_busy_retry(lambda: int(application.Documents.Count)) != 0: raise RealAutoCadComBackendError("AUTOCAD_SESSION_UNSAFE", "无法关闭默认空白文档")
            stage = "SYNTHETIC_DOCUMENT_CREATE"; gateway = Pywin32AutoCadSandboxGateway(application=application, array_adapter=LazyPywin32SafeArrayAdapter()); backend = RealAutoCadComBackend(gateway=gateway, artifact_root=root)
            identity = backend.reserve_synthetic_document(run_id=run_id, job_id=job_id, plan_hash=preliminary.plan_hash, output_path=sandbox / "s6_real_autocad_capabilities_mvp.dwg")
            plan = CadOperationPlan(job_id, identity.ownership_token, _s6_operations())
            if plan.plan_hash != identity.plan_hash: raise RealAutoCadComBackendError("S6_PLAN_HASH_UNSTABLE", "reserve 前后计划 hash 不一致")
            approval = L3SyntheticSandboxApproval(job_id=job_id, plan_hash=plan.plan_hash, document_token=identity.ownership_token, allowed_operations=S5_ALLOWED_OPERATIONS, expires_at=datetime.now(timezone.utc)+timedelta(minutes=10), single_use=False)
            backend.create_synthetic_document(identity, approval)
            stage = "S6_OPERATION_EXECUTION"; executor = S6RealComPlanExecutor(backend, gateway); first = executor.execute(identity, approval, plan)
            # 进程内 executor metadata 不能作为重开后的唯一幂等证据。把已完成
            # 的纯 DTO result 以 append-only journal 写入同一 run artifact；重开
            # 后重新读取并恢复 handle/operation metadata，再验证真实 ModelSpace。
            journal_path = root / "s6_operation_journal.json"
            journal = {"schema_version": "1.0.0", "job_id": job_id, "plan_hash": plan.plan_hash,
                       "document": identity.canonical_path, "results": [item.to_dict() for item in first.results]}
            journal_path.write_text(json.dumps(journal, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            stage = "S6_SAVE_CLOSE_REOPEN"; backend.save_document(identity, approval); backend.close_document(identity, approval); backend.reopen_document(identity, approval)
            restored_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if restored_journal.get("job_id") != job_id or restored_journal.get("plan_hash") != plan.plan_hash or restored_journal.get("document") != identity.canonical_path:
                raise RealAutoCadComBackendError("S6_IDEMPOTENCY_JOURNAL_MISMATCH", "S6 synthetic journal 与当前 job/document/plan 不匹配")
            gateway.restore_s6_operation_journal(identity, restored_journal["results"])
            stage = "S6_PERSISTENCE"; persisted = gateway.query_s6_entities(identity, None)
            found = {str(item.get("entity_type")) for item in persisted if not item.get("deleted")}
            required = {"line", "circle", "polyline", "arc", "rectangle", "text", "mtext", "block_definition", "block_reference"}
            if not required.issubset(found): raise RealAutoCadComBackendError("AUTOCAD_PERSISTENCE_VERIFICATION_FAILED", f"S6 重开后实体缺失: {sorted(required-found)}")
            restored_results = {item.operation_id: item for item in (CadOperationResult.from_dict(value) for value in restored_journal["results"])}
            stage = "S6_IDEMPOTENCY"; replay = S6RealComPlanExecutor(backend, gateway, persisted_results=restored_results).execute(identity, approval, plan)
            if any(item.status != "ALREADY_APPLIED" for item in replay.results): raise RealAutoCadComBackendError("AUTOCAD_IDEMPOTENCY_FAILED", "S6 相同计划重放创建了新操作")
            backend.save_document(identity, approval); backend.close_document(identity, approval)
            # S5 已验收：关闭最后一个 synthetic document 后默认空白文档可自动
            # 出现。只要同一 job-owned session guard 确认安全，允许 Close(False)。
            # 关闭最后一个 Document 后 AutoCAD 可能短暂拒绝 HWND/Documents
            # 的只读查询；复用 S5 已验证的有界 startup-busy 重试，不重新
            # DispatchEx、不创建第二实例，也不操作未知文档。
            verification = read_with_startup_busy_retry(
                lambda: AutoCadJobOwnedSessionGuard(ownership=ownership, hwnd_pid_resolver=hwnd_to_pid).verify(session, application)
            )
            if not verification.has_only_new_default_blank_documents: raise RealAutoCadComBackendError("AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED", "关闭 S6 synthetic 后出现非默认文档")
            for document in application.Documents: document.Close(False)
            if read_with_startup_busy_retry(lambda: int(application.Documents.Count)) != 0: raise RealAutoCadComBackendError("AUTOCAD_CLOSE_FAILED", "默认文档未关闭")
            backend.normal_shutdown()
        except Exception as exc:
            if session_verified and gateway is not None and identity is not None:
                try:
                    if gateway.has_registered_synthetic_document(identity): gateway.discard_registered_synthetic_document(identity)
                    if read_with_startup_busy_retry(lambda: int(application.Documents.Count)) == 0: gateway.quit_if_job_owned()
                except Exception: pass
            if isinstance(exc, RealAutoCadComBackendError): raise
            raise RealAutoCadComBackendError("S6_INTEGRATION_FAILED", f"S6 real synthetic 失败于 {stage}: {type(exc).__name__}", stage=stage) from exc
    # Application.Quit 为正常异步退出；给 job-owned 进程一个有界窗口自行
    # 收尾，绝不使用 taskkill/TerminateProcess 或按名称批量终止。
    after_shutdown = tuple(inspect_processes())
    for _ in range(40):
        if not after_shutdown: break
        sleep(0.5)
        after_shutdown = tuple(inspect_processes())
    if after_shutdown: raise RealAutoCadComBackendError("AUTOCAD_CLOSE_FAILED", "Job-owned AutoCAD 未正常退出")
    return {"run_id": run_id, "job_id": job_id, "backend": "real_autocad_com", "execution_mode": "com_activation", "synthetic": True, "document": identity.canonical_path,
            "entities_created": len(first.results), "entities_persisted": len(persisted), "idempotency_results": [item.status for item in replay.results], "post_shutdown_acad_process_count": 0,
            "user_dwg_reads": 0, "user_dwg_writes": 0, "tianzheng_connections": 0, "force_termination": False, "autocad_version": version,
            "idempotency_journal": str(journal_path)}

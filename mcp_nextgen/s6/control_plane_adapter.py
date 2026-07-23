"""S6 结构化计划到既有 S4 Mock Control Plane 的窄适配。

这不是 Real COM 通道：它只创建 ``mock://`` 身份的 S4 作业，并把纯内存
``SyntheticCadBackend`` 作为 executor。真实 COM 必须继续走显式 L3 synthetic
runner，不能借由 S4 dispatcher 偷渡。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from mcp_nextgen.control_server.service import ControlPlaneService

from .contracts import CadOperationPlan
from .fake_backend import CadBatchResult, SyntheticCadBackend


S6_CONTROL_OPERATION = "s6_synthetic_operation_plan"


class S6ControlPlaneAdapterError(RuntimeError):
    pass


class S6MockControlPlaneAdapter:
    """只接入 S4 的 Mock 生命周期，保留其 offline/mock 安全边界。"""

    def __init__(self, service: ControlPlaneService, backend: SyntheticCadBackend) -> None:
        self._service = service
        self._backend = backend
        self._plans: dict[str, CadOperationPlan] = {}
        self._results: dict[str, CadBatchResult] = {}

    def submit(self, plan: CadOperationPlan, *, request_id: str, idempotency_key: str,
               product: str = "generic_autocad", execution_runtime: str = "mock", backend: str = "nextgen_mock") -> dict[str, Any]:
        if product != "generic_autocad" or execution_runtime != "mock" or backend != "nextgen_mock":
            raise S6ControlPlaneAdapterError("S6 Mock adapter 只接受 generic_autocad + mock + nextgen_mock")
        self._plans[plan.job_id] = plan
        document_identity = {
            "document_full_path": f"mock://s6/{plan.document_token}",
            "document_sha256": sha256(plan.document_token.encode("utf-8")).hexdigest(),
            "document_role": "MOCK_DOCUMENT",
        }
        job = self._service.create_job(
            job_id=plan.job_id, request_id=request_id, idempotency_key=idempotency_key,
            plan_hash=plan.plan_hash, operation=S6_CONTROL_OPERATION, product=product,
            execution_runtime=execution_runtime, backend=backend, document_identity=document_identity,
            tasks=({"task_id": f"{plan.job_id}.batch", "batch_id": f"{plan.job_id}.batch", "operation": S6_CONTROL_OPERATION},),
        )
        return job.to_dict()

    def approve_and_run(self, job_id: str) -> dict[str, Any]:
        plan = self._plans.get(job_id)
        if plan is None:
            raise S6ControlPlaneAdapterError("未知 S6 计划")
        expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        self._service.approve(job_id, {
            "job_id": job_id, "plan_hash": plan.plan_hash, "operation": S6_CONTROL_OPERATION,
            "product": "generic_autocad", "runtime": "mock", "allowed_operations": [S6_CONTROL_OPERATION],
            "expires_at": expires, "single_use": True, "production_allowed": False, "production_d1_allowed": False,
        })
        def execute(_job: Any, _task: Any) -> dict[str, Any]:
            result = self._backend.execute_plan(plan)
            self._results[job_id] = result
            failed = next((item for item in result.results if item.status == "FAILED"), None)
            return {"status": "FAILED" if failed else "COMPLETED", "error_code": failed.error_code if failed else None,
                    "real_backend": False, "real_cad_access": False}
        job = self._service.run(job_id, executor=execute)
        return {"job": job.to_dict(), "operation_result": self._results[job_id], "backend": "nextgen_mock", "synthetic": True,
                "real_backend": False, "limitations": ["仅 S6 pure-memory Mock，不连接 AutoCAD/COM"]}

    def result_for(self, job_id: str) -> CadBatchResult | None:
        return self._results.get(job_id)

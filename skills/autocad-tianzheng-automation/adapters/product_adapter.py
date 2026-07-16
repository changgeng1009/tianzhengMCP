"""S3 统一 ProductAdapter 离线合同。

该模块只产生声明性 inspect/plan/validate/execute 结果。它不导入 CAD、COM、
真实后端或原始 Skill 脚本；``execute`` 也绝不执行绘图操作。
"""

from __future__ import annotations

from abc import ABC
from typing import Any, Mapping

from runtime.contracts import ICadProductAdapter


class ProductAdapter(ICadProductAdapter, ABC):
    """所有产品适配器共用的安全、纯数据合同。"""

    EXECUTE_AVAILABILITY = "BLOCKED_OFFLINE_OR_MOCK_CONTRACT_ONLY"

    def contract(self) -> dict[str, Any]:
        """返回可由 registry 审计的静态产品合同。"""
        capability = dict(self.capabilities())
        capability.setdefault("product_status", capability.get("status", "NOT_IMPLEMENTED"))
        capability.setdefault("required_backends", ["offline"])
        capability.setdefault("limitations", [])
        capability.update(
            {
                "adapter_id": type(self).__name__,
                "inspect_available": True,
                "plan_available": True,
                "validate_available": True,
                "execute_available": False,
                "execute_availability": self.EXECUTE_AVAILABILITY,
                "real_cad_access": False,
                "real_execution": False,
            }
        )
        return capability

    def inspect(self, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """生成离线检查请求，不访问输入 CAD 文件。"""
        return self._operation_result("inspect", request)

    def plan(self, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """生成离线计划合同，不执行后端。"""
        return self._operation_result("plan", request)

    def validate(self, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """验证产品合同边界，而非验证或读取 CAD 文档。"""
        supplied = dict(request or {})
        require_real = bool(supplied.get("require_real_execution", False))
        requested_backend = str(supplied.get("backend", "offline"))
        valid = not require_real and requested_backend not in self._real_backend_ids()
        result = self._operation_result("validate", supplied)
        result.update(
            {
                "valid": valid,
                "code": "OK" if valid else "BACKEND_NOT_AVAILABLE",
                "reason": (
                    None
                    if valid
                    else "ProductAdapter 不提供 Real CAD execution；请求只能离线或 Mock"
                ),
            }
        )
        return result

    def execute(self, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """只返回阻断/Mock 合同，永远不调用任何 CAD 或 COM 代码。"""
        supplied = dict(request or {})
        backend = str(supplied.get("backend", "offline"))
        validation = self.validate(supplied)
        mock_requested = backend == "nextgen_mock"
        result = self._operation_result("execute", supplied)
        result.update(
            {
                "executed": False,
                "backend": backend,
                "code": (
                    "MOCK_EXECUTION_CONTRACT_ONLY"
                    if validation["valid"] and mock_requested
                    else "REAL_CAD_EXECUTION_BLOCKED"
                ),
                "status": "MOCK_CONTRACT" if validation["valid"] and mock_requested else "BLOCKED",
                "reason": (
                    "仅返回 NextGen Mock 合同；未启动或连接 CAD"
                    if validation["valid"] and mock_requested
                    else "当前 ProductAdapter 仅支持离线规划；真实执行被安全阻断"
                ),
                "real_cad_access": False,
                "com_connection": False,
            }
        )
        return result

    def _operation_result(
        self, operation: str, request: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        contract = self.contract()
        return {
            "operation": operation,
            "adapter": contract["adapter_id"],
            "product": contract.get("product"),
            "product_status": contract["product_status"],
            "required_backends": list(contract["required_backends"]),
            "limitations": list(contract["limitations"]),
            "request": dict(request or {}),
            "real_cad_access": False,
            "real_execution": False,
        }

    @staticmethod
    def _real_backend_ids() -> frozenset[str]:
        return frozenset(
            {
                "legacy_com",
                "nextgen_real",
                "autocad_dotnet_plugin",
                "tianzheng_water_real",
                "tianzheng_hvac_real",
                "objectarx",
                "com",
            }
        )


__all__ = ["ProductAdapter"]

"""S6 普通 AutoCAD 合成 Sandbox 的后端中立合同与执行适配。

本包默认只提供纯 Python DTO 与 Fake 执行器；导入它不会加载 pywin32、
连接 COM 或访问 CAD 文件。
"""

from .contracts import (
    CadOperation,
    CadOperationPlan,
    CadOperationResult,
    CadOperationValidationError,
    EntitySelector,
    EntitySpec,
    EntitySnapshot,
    Point3,
    S6_ALLOWED_OPERATIONS,
)
from .fake_backend import CadBatchResult, SyntheticCadBackend, SyntheticCadBackendError
from .real_com_executor import S6RealComPlanExecutor, S6RealExecutionResult

__all__ = [
    "CadOperation", "CadOperationPlan", "CadOperationResult", "CadOperationValidationError",
    "EntitySelector", "EntitySpec", "EntitySnapshot", "Point3", "S6_ALLOWED_OPERATIONS",
    "CadBatchResult", "SyntheticCadBackend", "SyntheticCadBackendError", "S6RealComPlanExecutor", "S6RealExecutionResult",
]

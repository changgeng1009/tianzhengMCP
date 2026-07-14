from typing import Any, Mapping

from runtime.contracts import ICadBackend, SupportLevel
from runtime.errors import UnsafeOperation
from runtime.planner import build_offline_plan


class NextGenMcpMockBackend(ICadBackend):
    name = "nextgen-mock"
    support_level = "IMPLEMENTED_BASELINE"
    control_plane_status = "PARTIALLY_IMPLEMENTED"
    real_cad_capability = False

    def build_plan(self, manifest: Mapping[str, Any]):
        return build_offline_plan({**manifest, "preferred_backend": self.name})


class NextGenMcpBackendPlaceholder(ICadBackend):
    name = "nextgen-real"
    support_level = SupportLevel.INTERFACE_ONLY
    real_cad_capability = False

    def build_plan(self, manifest: Mapping[str, Any]):
        return {
            "status": self.support_level.value,
            "backend": self.name,
            "execution_allowed": False,
            "real_cad_capability": False,
            "reason": "下一代 MCP 尚未接入并验收",
        }

    def execute(self, *_):
        raise UnsafeOperation("NextGen MCP 仅为占位接口")

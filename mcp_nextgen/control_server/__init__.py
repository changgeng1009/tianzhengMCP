"""import-safe、Mock-only NextGen MCP 控制面；本包不会自动运行服务。"""

from .dispatcher import ControlPlaneError, configure_control_plane_service, dispatch_tool
from .discovery import NEXTGEN_PROMPTS, NEXTGEN_RESOURCES, list_prompts, list_resources, self_check_discovery
from .server import create_mcp, mcp
from .service import ControlJob, ControlJobStatus, ControlPlaneJobError, ControlPlaneService, ControlProgressEvent

__all__ = [
    "ControlJob",
    "ControlJobStatus",
    "ControlPlaneError",
    "ControlPlaneJobError",
    "ControlPlaneService",
    "ControlProgressEvent",
    "NEXTGEN_PROMPTS",
    "NEXTGEN_RESOURCES",
    "configure_control_plane_service",
    "create_mcp",
    "dispatch_tool",
    "list_prompts",
    "list_resources",
    "mcp",
    "self_check_discovery",
]

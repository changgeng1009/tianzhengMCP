"""import-safe FastMCP 控制面；本包不会自动运行服务。"""

from .dispatcher import ControlPlaneError, dispatch_tool
from .server import create_mcp, mcp

__all__ = ["ControlPlaneError", "create_mcp", "dispatch_tool", "mcp"]

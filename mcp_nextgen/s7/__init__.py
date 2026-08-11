"""S7 AutoCAD plugin backend integration.

Importing this package opens no socket, starts no AutoCAD and loads no pywin32.
"""

from .plugin_route import (
    PluginRouteError,
    S7PluginRouteService,
    build_plugin_route_service,
)

__all__ = ["PluginRouteError", "S7PluginRouteService", "build_plugin_route_service"]

"""天正 MCP NextGen 隔离基线。

本包吸收实验项目中可验证的协议、白名单和本地传输概念，但所有实现均为
正式项目内的重新设计。当前能力严格限定为 Mock-only，且不会在 import 时
启动服务、绑定端口或连接 AutoCAD/天正。
"""

from .protocol.version import PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS

__version__ = "0.1.0"

__all__ = ["PROTOCOL_VERSION", "SUPPORTED_PROTOCOL_VERSIONS", "__version__"]

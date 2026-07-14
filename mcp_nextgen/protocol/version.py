"""应用层协议版本与协商。"""

from __future__ import annotations

PROTOCOL_VERSION = "1.0.0"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION,)


class ProtocolVersionError(ValueError):
    """客户端与服务端没有共同协议版本。"""


def _semver_key(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ProtocolVersionError(f"非法协议版本: {version!r}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def negotiate_version(
    client_versions: list[str] | tuple[str, ...],
    server_versions: list[str] | tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS,
) -> str:
    """选择双方共同支持的最高语义化版本。"""

    common = set(client_versions).intersection(server_versions)
    if not common:
        raise ProtocolVersionError("没有共同支持的应用协议版本")
    return max(common, key=_semver_key)

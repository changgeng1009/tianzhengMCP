"""纯本地 transport policy；不包含 socket/listen 实现。"""

from __future__ import annotations

from dataclasses import dataclass

from ..protocol.version import SUPPORTED_PROTOCOL_VERSIONS


class TransportPolicyError(ValueError):
    """transport policy 不满足本地安全约束。"""


@dataclass(frozen=True)
class LocalTransportPolicy:
    bind_host: str = "127.0.0.1"
    max_message_bytes: int = 1 * 1024 * 1024
    max_request_id_length: int = 128
    max_idempotency_key_length: int = 128
    max_pending_requests: int = 256
    replay_ttl_seconds: float = 300.0
    supported_versions: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS
    authentication_required: bool = True
    production_d1_allowed: bool = False

    def __post_init__(self) -> None:
        if self.bind_host != "127.0.0.1":
            raise TransportPolicyError("本地 transport 只能使用 127.0.0.1")
        if not 1024 <= self.max_message_bytes <= 16 * 1024 * 1024:
            raise TransportPolicyError("max_message_bytes 必须在 1 KiB 到 16 MiB 之间")
        if not 1 <= self.max_pending_requests <= 4096:
            raise TransportPolicyError("max_pending_requests 超出安全范围")
        if self.replay_ttl_seconds <= 0:
            raise TransportPolicyError("replay_ttl_seconds 必须为正数")
        if not self.authentication_required:
            raise TransportPolicyError("本地 transport 不允许关闭鉴权")
        if self.production_d1_allowed:
            raise TransportPolicyError("当前基线禁止 Production D1")
        if not self.supported_versions:
            raise TransportPolicyError("supported_versions 不能为空")

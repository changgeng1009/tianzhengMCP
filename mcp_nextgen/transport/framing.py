"""有界 JSON-RPC 2.0 + JSON Lines framing。

本模块只编解码内存中的完整 frame，不读取 socket、不监听端口。调用方必须在
累计读取阶段同样执行 `max_message_bytes`，不得先无限缓存再调用本 codec。
"""

from __future__ import annotations

import json
from typing import Any, Collection

from ..protocol.version import negotiate_version
from ..schemas.tools import NEXTGEN_TOOLS
from ..schemas.validator import SchemaValidationError, validate_instance
from .policy import LocalTransportPolicy


class TransportMessageError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_REQUIRED_ENVELOPE = {
    "jsonrpc", "protocol_version", "id", "idempotency_key", "method", "params"
}


class JsonLineCodec:
    def __init__(
        self,
        policy: LocalTransportPolicy | None = None,
        allowed_operations: Collection[str] | None = None,
    ):
        self.policy = policy or LocalTransportPolicy()
        self.allowed_operations = frozenset(allowed_operations or NEXTGEN_TOOLS)

    def _validate_envelope(self, message: dict[str, Any]) -> None:
        extras = set(message).difference(_REQUIRED_ENVELOPE)
        missing = _REQUIRED_ENVELOPE.difference(message)
        if missing:
            raise TransportMessageError("INVALID_REQUEST", f"缺少 envelope 字段: {sorted(missing)}")
        if extras:
            raise TransportMessageError("INVALID_REQUEST", f"不允许 envelope 额外字段: {sorted(extras)}")
        if message["jsonrpc"] != "2.0":
            raise TransportMessageError("INVALID_JSONRPC_VERSION", "jsonrpc 必须为 2.0")
        try:
            negotiate_version([message["protocol_version"]], self.policy.supported_versions)
        except (TypeError, ValueError) as exc:
            raise TransportMessageError("PROTOCOL_VERSION_UNSUPPORTED", str(exc)) from exc
        request_id = message["id"]
        if not isinstance(request_id, str) or not request_id:
            raise TransportMessageError("REQUEST_ID_REQUIRED", "request_id 不能为空")
        if len(request_id) > self.policy.max_request_id_length:
            raise TransportMessageError("REQUEST_ID_TOO_LONG", "request_id 超出长度限制")
        idempotency_key = message["idempotency_key"]
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise TransportMessageError("IDEMPOTENCY_KEY_REQUIRED", "idempotency_key 不能为空")
        if len(idempotency_key) > self.policy.max_idempotency_key_length:
            raise TransportMessageError("IDEMPOTENCY_KEY_TOO_LONG", "idempotency_key 超出长度限制")
        method = message["method"]
        if not isinstance(method, str) or method not in self.allowed_operations:
            raise TransportMessageError("UNKNOWN_METHOD", f"未知操作: {method!r}")
        if not isinstance(message["params"], dict):
            raise TransportMessageError("INVALID_PARAMS", "params 必须是对象")
        try:
            validate_instance(message["params"], NEXTGEN_TOOLS[method]["inputSchema"])
        except SchemaValidationError as exc:
            raise TransportMessageError("INVALID_PARAMS", str(exc)) from exc
        if message["params"]["request_id"] != request_id:
            raise TransportMessageError("REQUEST_ID_MISMATCH", "envelope id 与 params.request_id 不一致")
        if message["params"]["idempotency_key"] != idempotency_key:
            raise TransportMessageError(
                "IDEMPOTENCY_KEY_MISMATCH",
                "envelope idempotency_key 与 params.idempotency_key 不一致",
            )

    def encode_request(self, message: dict[str, Any]) -> bytes:
        self._validate_envelope(message)
        encoded = json.dumps(
            message,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self.policy.max_message_bytes:
            raise TransportMessageError("MESSAGE_TOO_LARGE", "消息超过大小限制")
        return encoded + b"\n"

    def decode_request(self, frame: bytes) -> dict[str, Any]:
        if not isinstance(frame, bytes):
            raise TransportMessageError("INVALID_FRAME", "frame 必须是 bytes")
        if len(frame) > self.policy.max_message_bytes + 1:
            raise TransportMessageError("MESSAGE_TOO_LARGE", "消息超过大小限制")
        if not frame.endswith(b"\n") or frame.count(b"\n") != 1:
            raise TransportMessageError("INVALID_FRAME", "每个 frame 必须且只能以一个换行结束")
        try:
            text = frame[:-1].decode("utf-8", errors="strict")
            message = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportMessageError("MALFORMED_JSON", str(exc)) from exc
        if not isinstance(message, dict):
            raise TransportMessageError("INVALID_REQUEST", "JSON-RPC 消息必须是对象")
        self._validate_envelope(message)
        return message

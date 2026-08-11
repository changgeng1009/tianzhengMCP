"""AutoCAD Managed Plugin transport client (Protocol 2.0, loopback only).

This is the ONLY module that speaks the plugin wire protocol. Everything above it —
``AutoCadPluginBackend``, the capability router, MCP tools — sees S6 contracts and
structured errors, never frames, sockets or JSON envelopes.

Security posture
----------------
* binds/connects to loopback ONLY; a non-loopback host fails closed before any socket;
* the auth token is injected, never defaulted, never logged, never placed in an S6 DTO;
* only protocol MAJOR 2 is accepted — 1.x/3.x fail closed rather than "best effort";
* a write whose response is lost is reported as UNKNOWN, never silently retried.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import socket
import struct
import time
import uuid
from typing import Any, Mapping

PLUGIN_PROTOCOL_VERSION = "2.0.0"
PLUGIN_PROTOCOL_MAJOR = 2
FRAME_HEADER_BYTES = 4
MAX_PAYLOAD_BYTES = 1 * 1024 * 1024
MIN_TOKEN_LENGTH = 32
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TRANSPORT_ATTEMPTS = 2  # one retry, per the two-round repair rule

#: Loopback literals. Note ``localhost`` is deliberately NOT accepted: it is DNS-resolved
#: and could be repointed. Only explicit loopback IP literals are allowed.
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1"})


class PluginTransportError(RuntimeError):
    """Structured transport/protocol failure.

    ``retryable`` refers ONLY to whether the request may be re-sent safely; it is never
    set for a write whose outcome is unknown.
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        retryable: bool = False,
        stage: str = "transport",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.stage = stage
        self.details = dict(details or {})


class PluginExecutionOutcomeUnknown(PluginTransportError):
    """A write was sent but no response arrived: the effect may or may not exist.

    Never auto-retried. Re-sending could duplicate entities, so the caller must decide
    (and, once persistent idempotency is in play, replay with the same key).
    """

    def __init__(self, message: str) -> None:
        super().__init__("PLUGIN_EXECUTION_OUTCOME_UNKNOWN", message, retryable=False, stage="execution")


def redact_token(token: str | None) -> str:
    """Short digest for logs/reprs. Never returns any part of the token itself."""
    if not token:
        return "<empty>"
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:8] + "..."


def validate_loopback_host(host: str) -> str:
    """Fail closed unless *host* is an explicit loopback IP literal."""
    candidate = (host or "").strip()
    if candidate in _ALLOWED_HOSTS:
        return candidate
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise PluginTransportError(
            "PLUGIN_HOST_NOT_LOOPBACK",
            "plugin host must be an explicit loopback IP literal (127.0.0.1 or ::1)",
        ) from exc
    if not parsed.is_loopback:
        raise PluginTransportError(
            "PLUGIN_HOST_NOT_LOOPBACK", "plugin host must be a loopback address"
        )
    return str(parsed)


def protocol_major(version: str) -> int:
    try:
        return int(str(version).split(".", 1)[0])
    except (TypeError, ValueError) as exc:
        raise PluginTransportError(
            "PLUGIN_PROTOCOL_VERSION_MISMATCH", f"unparsable protocol version {version!r}"
        ) from exc


@dataclass(frozen=True)
class PluginCapabilities:
    """Cached runtime handshake. Capability comes from the plugin, never from constants."""

    protocol_version: str
    capability_version: str
    plugin_version: str
    process_id: int
    session_id: str
    session_nonce: str
    readiness: bool
    readiness_state: str
    supported_operations: tuple[str, ...]
    supported_entity_types: tuple[str, ...]
    transaction_support: bool
    batch_support: bool
    batch_transaction_mode: str
    dry_run_support: bool
    document_ownership_support: bool
    idempotency_support: str
    persistence_support: bool
    tianzheng_support: str
    autocad_version: str = ""

    @classmethod
    def from_result(cls, result: Mapping[str, Any]) -> "PluginCapabilities":
        return cls(
            protocol_version=str(result.get("protocol_version", "")),
            capability_version=str(result.get("capability_version", "")),
            plugin_version=str(result.get("plugin_version", "")),
            process_id=int(result.get("process_id", 0) or 0),
            session_id=str(result.get("session_id", "")),
            session_nonce=str(result.get("session_nonce", "")),
            readiness=bool(result.get("readiness", False)),
            readiness_state=str(result.get("readiness_state", "")),
            supported_operations=tuple(result.get("supported_operations") or ()),
            supported_entity_types=tuple(result.get("supported_entity_types") or ()),
            transaction_support=bool(result.get("transaction_support", False)),
            batch_support=bool(result.get("batch_support", False)),
            batch_transaction_mode=str(result.get("batch_transaction_mode", "")),
            dry_run_support=bool(result.get("dry_run_support", False)),
            document_ownership_support=bool(result.get("document_ownership_support", False)),
            idempotency_support=str(result.get("idempotency_support", "NOT_IMPLEMENTED")),
            persistence_support=bool(result.get("persistence_support", False)),
            tianzheng_support=str(result.get("tianzheng_support", "NOT_AVAILABLE")),
            autocad_version=str(result.get("autocad_version", "")),
        )

    def supports(self, operation: str) -> bool:
        return operation in self.supported_operations

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "capability_version": self.capability_version,
            "plugin_version": self.plugin_version,
            "process_id": self.process_id,
            "session_id": self.session_id,
            "readiness": self.readiness,
            "readiness_state": self.readiness_state,
            "supported_operations": list(self.supported_operations),
            "supported_entity_types": list(self.supported_entity_types),
            "transaction_support": self.transaction_support,
            "batch_support": self.batch_support,
            "batch_transaction_mode": self.batch_transaction_mode,
            "dry_run_support": self.dry_run_support,
            "document_ownership_support": self.document_ownership_support,
            "idempotency_support": self.idempotency_support,
            "persistence_support": self.persistence_support,
            "tianzheng_support": self.tianzheng_support,
            "autocad_version": self.autocad_version,
            # session_nonce is intentionally omitted: it is session state, not a report field.
        }


class _Connection:
    """One framed socket. Framing: [4-byte unsigned big-endian length][UTF-8 JSON]."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def send(self, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        if len(body) > MAX_PAYLOAD_BYTES:
            raise PluginTransportError("FRAME_TOO_LARGE", "request exceeds the protocol payload cap")
        self._sock.sendall(struct.pack(">I", len(body)) + body)

    def _read_exactly(self, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            chunk = self._sock.recv(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def receive(self) -> dict[str, Any]:
        header = self._read_exactly(FRAME_HEADER_BYTES)
        if len(header) == 0:
            raise PluginTransportError(
                "CONNECTION_RESET", "plugin closed the connection", retryable=True)
        if len(header) < FRAME_HEADER_BYTES:
            raise PluginTransportError("MALFORMED_FRAME", "truncated frame header")

        (declared,) = struct.unpack(">I", header)
        if declared == 0 or declared > MAX_PAYLOAD_BYTES:
            raise PluginTransportError("FRAME_TOO_LARGE", f"illegal declared length {declared}")

        body = self._read_exactly(declared)
        if len(body) < declared:
            raise PluginTransportError("MALFORMED_FRAME", "truncated frame body")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginTransportError("MALFORMED_FRAME", "response was not valid UTF-8 JSON") from exc


@dataclass
class PluginTransportConfig:
    host: str = "127.0.0.1"
    port: int = 5987
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    connect_timeout_seconds: float = 10.0


class PluginTransportClient:
    """Authenticated, versioned client for the in-process AutoCAD plugin.

    The token is supplied by the caller (constructor injection). There is deliberately no
    default and no environment fallback inside this class, so a misconfigured deployment
    cannot silently authenticate.
    """

    def __init__(
        self,
        config: PluginTransportConfig,
        *,
        auth_token: str,
        connection_factory: Any = None,
    ) -> None:
        self._host = validate_loopback_host(config.host)
        if not isinstance(config.port, int) or not (1 <= config.port <= 65535):
            raise PluginTransportError("PLUGIN_CONFIG_INVALID", "plugin port is out of range")
        if not auth_token or len(auth_token) < MIN_TOKEN_LENGTH:
            raise PluginTransportError(
                "PLUGIN_TOKEN_INVALID",
                f"an injected auth token of at least {MIN_TOKEN_LENGTH} characters is required",
            )

        self._config = config
        self._token = auth_token
        self._connection_factory = connection_factory or _Connection
        self._connection: Any = None
        self._capabilities: PluginCapabilities | None = None
        self._session_nonce: str = ""

    # ------------------------------------------------------------------ repr

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"PluginTransportClient(host={self._host!r}, port={self._config.port}, "
            f"token={redact_token(self._token)}, connected={self.connected})"
        )

    __str__ = __repr__

    # ------------------------------------------------------------ properties

    @property
    def connected(self) -> bool:
        return self._connection is not None

    @property
    def capabilities(self) -> PluginCapabilities | None:
        return self._capabilities

    @property
    def session_id(self) -> str:
        return self._capabilities.session_id if self._capabilities else ""

    # ------------------------------------------------------------ lifecycle

    def connect(self) -> PluginCapabilities:
        """Connect, authenticate and handshake. Idempotent while already connected."""
        if self._connection is not None and self._capabilities is not None:
            return self._capabilities

        try:
            self._connection = self._connection_factory(
                self._host, self._config.port, self._config.connect_timeout_seconds
            )
        except (ConnectionRefusedError, OSError) as exc:
            self._connection = None
            raise PluginTransportError(
                "CONNECTION_REFUSED",
                "the AutoCAD plugin is not listening on the configured loopback port",
                retryable=True,
            ) from exc

        try:
            self._authenticate()
            self._capabilities = self._handshake()
        except Exception:
            self.disconnect()
            raise
        return self._capabilities

    def disconnect(self) -> None:
        """Drop the connection and all session state. A new nonce is required afterwards."""
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._capabilities = None
        self._session_nonce = ""

    def _authenticate(self) -> None:
        response = self._exchange({
            "type": "auth",
            "auth_token": self._token,
            "protocol_version": PLUGIN_PROTOCOL_VERSION,
        })
        if not response.get("success"):
            # An auth failure is a configuration error: never auto-retried.
            raise PluginTransportError(
                response.get("error_code") or "AUTH_FAILED",
                "plugin rejected the authentication handshake",
                retryable=False,
                stage="authentication",
            )

    def _handshake(self) -> PluginCapabilities:
        response = self._exchange(self._build_request("capabilities", require_nonce=False))
        if not response.get("success"):
            raise PluginTransportError(
                response.get("error_code") or "PLUGIN_HANDSHAKE_FAILED",
                "plugin did not return capabilities",
                stage="handshake",
            )

        capabilities = PluginCapabilities.from_result(response.get("result") or {})

        major = protocol_major(capabilities.protocol_version)
        if major != PLUGIN_PROTOCOL_MAJOR:
            raise PluginTransportError(
                "PLUGIN_PROTOCOL_VERSION_MISMATCH",
                f"plugin speaks protocol {capabilities.protocol_version}; "
                f"this client requires major {PLUGIN_PROTOCOL_MAJOR}",
                retryable=False,
                stage="protocol",
                details={"plugin_protocol_version": capabilities.protocol_version},
            )

        if not capabilities.readiness:
            raise PluginTransportError(
                "PLUGIN_NOT_READY", "plugin reports readiness=false", retryable=True, stage="handshake"
            )

        self._session_nonce = capabilities.session_nonce
        return capabilities

    def _reconnect(self) -> None:
        """Full re-establish: new socket, new auth, new capabilities, new nonce."""
        self.disconnect()
        self.connect()

    # --------------------------------------------------------------- requests

    def _build_request(
        self,
        operation_type: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        document_context: Mapping[str, Any] | None = None,
        job_id: str = "s7-plugin-backend",
        operation_id: str | None = None,
        idempotency_key: str = "",
        dry_run: bool = False,
        timeout_ms: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        require_nonce: bool = True,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "protocol_version": PLUGIN_PROTOCOL_VERSION,
            "request_id": f"backend-{uuid.uuid4().hex[:12]}",
            "job_id": job_id,
            "operation_id": operation_id or f"op-{uuid.uuid4().hex[:8]}",
            "operation_type": operation_type,
            "document_context": dict(document_context or {}),
            "parameters": dict(parameters or {}),
            "idempotency_key": idempotency_key,
            "expected_capability": "autocad_plugin_backend",
            "dry_run": bool(dry_run),
            "timeout_ms": int(timeout_ms or self._config.timeout_seconds * 1000),
            "metadata": dict(metadata or {}),
        }
        if require_nonce:
            request["session_nonce"] = self._session_nonce
        return request

    def _exchange(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._connection is None:
            raise PluginTransportError("CONNECTION_REFUSED", "not connected", retryable=True)
        self._connection.send(payload)
        return self._connection.receive()

    def call(
        self,
        operation_type: str,
        *,
        mutating: bool,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send one request, handling reconnect/nonce refresh under strict safety rules.

        ``mutating`` is the critical flag. For a mutating call, a failure AFTER the request
        left the process means the effect is UNKNOWN — the plugin may have committed it —
        so the request is never re-sent automatically.
        """
        last_error: PluginTransportError | None = None

        for attempt in range(1, MAX_TRANSPORT_ATTEMPTS + 1):
            if self._connection is None or self._capabilities is None:
                self.connect()

            request = self._build_request(operation_type, **kwargs)
            sent = False
            try:
                if self._connection is None:  # pragma: no cover - defensive
                    raise PluginTransportError("CONNECTION_REFUSED", "not connected", retryable=True)
                self._connection.send(request)
                sent = True
                response = self._connection.receive()
            except PluginTransportError as exc:
                if mutating and sent:
                    # The request was on the wire; we cannot know whether it committed.
                    raise PluginExecutionOutcomeUnknown(
                        "the write request was sent but no response was received; "
                        "the plugin may or may not have committed it"
                    ) from exc
                last_error = exc
                self.disconnect()
                if not exc.retryable or attempt == MAX_TRANSPORT_ATTEMPTS:
                    raise
                continue
            except (socket.timeout, TimeoutError) as exc:
                if mutating and sent:
                    raise PluginExecutionOutcomeUnknown(
                        "the write request timed out awaiting a response; outcome is unknown"
                    ) from exc
                last_error = PluginTransportError("TIMEOUT", "plugin did not respond in time", retryable=True)
                self.disconnect()
                if attempt == MAX_TRANSPORT_ATTEMPTS:
                    raise last_error from exc
                continue
            except OSError as exc:
                if mutating and sent:
                    raise PluginExecutionOutcomeUnknown(
                        "the connection dropped after the write was sent; outcome is unknown"
                    ) from exc
                last_error = PluginTransportError("CONNECTION_RESET", "connection dropped", retryable=True)
                self.disconnect()
                if attempt == MAX_TRANSPORT_ATTEMPTS:
                    raise last_error from exc
                continue

            error_code = response.get("error_code") or ""

            # A stale nonce is safe to recover from for READ-ONLY calls only: the plugin
            # rejects before scheduling, so no side effect can have occurred.
            if error_code in {"SESSION_NONCE_INVALID", "SESSION_NONCE_REQUIRED"} and attempt < MAX_TRANSPORT_ATTEMPTS:
                self._reconnect()
                continue

            return response

        raise last_error or PluginTransportError("PLUGIN_UNAVAILABLE", "plugin request failed")

    # --------------------------------------------------------- convenience

    def health(self) -> dict[str, Any]:
        return self.call("health", mutating=False)

    def refresh_capabilities(self) -> PluginCapabilities:
        response = self.call("capabilities", mutating=False)
        if not response.get("success"):
            raise PluginTransportError(
                response.get("error_code") or "PLUGIN_HANDSHAKE_FAILED", "capabilities refresh failed")
        capabilities = PluginCapabilities.from_result(response.get("result") or {})
        self._capabilities = capabilities
        self._session_nonce = capabilities.session_nonce
        return capabilities

    def __enter__(self) -> "PluginTransportClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disconnect()

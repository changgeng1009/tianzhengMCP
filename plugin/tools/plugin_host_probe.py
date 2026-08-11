"""S7.1-B diagnostic probe for the AutoCAD Managed Plugin host.

Scope (deliberately minimal):
  * connect to 127.0.0.1 only;
  * perform the connection-level auth handshake;
  * request health / capabilities;
  * send an unknown operation;
  * send a whitelisted-but-not-yet-implemented operation;
  * check connection closure and structured responses.

This is NOT AutoCadPluginBackend. It implements no ICadBackend, no MCP route, and no
S6 DTO mapping. It never creates CAD entities, documents, or files other than the
sanitized evidence JSON it is asked to write.

The token is read from the environment (TIANZHENG_PLUGIN_TOKEN) and is NEVER printed
or written to the evidence file -- only a short SHA-256 prefix is recorded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import struct
import sys
import uuid
from typing import Any

# Must match the plugin's MAJOR. 1.x is rejected by plugin protocol >= 2.0.0
# (readiness changed from string to boolean).
PROTOCOL_VERSION = "2.0.0"
LEGACY_PROTOCOL_VERSION = "1.0.0"
HEADER_BYTES = 4
MAX_PAYLOAD_BYTES = 1 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def redact(secret: str | None) -> str:
    if not secret:
        return "<empty>"
    return "sha256:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8] + "..."


class PluginConnection:
    """One framed, authenticated loopback connection."""

    def __init__(self, port: int, timeout: float = 15.0) -> None:
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self._sock.settimeout(timeout)

    def __enter__(self) -> "PluginConnection":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    # -- framing: [4-byte unsigned big-endian byte length][UTF-8 JSON] --

    def send(self, payload: dict[str, Any] | str) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        body = text.encode("utf-8")
        if len(body) > MAX_PAYLOAD_BYTES:
            raise ProbeError("payload exceeds protocol cap")
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

    def receive(self) -> dict[str, Any] | None:
        """Read exactly one frame. None means the peer closed on a boundary."""
        header = self._read_exactly(HEADER_BYTES)
        if len(header) == 0:
            return None
        if len(header) < HEADER_BYTES:
            raise ProbeError("truncated frame header")
        (declared,) = struct.unpack(">I", header)
        if declared == 0 or declared > MAX_PAYLOAD_BYTES:
            raise ProbeError(f"illegal declared length {declared}")
        body = self._read_exactly(declared)
        if len(body) < declared:
            raise ProbeError("truncated frame body")
        return json.loads(body.decode("utf-8"))

    def roundtrip(self, payload: dict[str, Any] | str) -> dict[str, Any] | None:
        self.send(payload)
        return self.receive()

    def authenticate(self, token: str) -> dict[str, Any] | None:
        return self.roundtrip(
            {"type": "auth", "auth_token": token, "protocol_version": PROTOCOL_VERSION}
        )


def build_request(
    operation_type: str,
    *,
    session_nonce: str | None = None,
    timeout_ms: int = 10_000,
) -> dict[str, Any]:
    """Business request envelope. Deliberately carries NO auth_token."""
    request: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": f"probe-{uuid.uuid4().hex[:12]}",
        "job_id": "s7-1-b-probe",
        "operation_id": f"op-{uuid.uuid4().hex[:8]}",
        "operation_type": operation_type,
        "document_context": {},
        "parameters": {},
        "idempotency_key": f"idem-{uuid.uuid4().hex[:8]}",
        "expected_capability": "autocad_plugin_backend",
        "dry_run": False,
        "timeout_ms": timeout_ms,
        "metadata": {},
    }
    if session_nonce is not None:
        request["session_nonce"] = session_nonce
    return request


def sanitize(response: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop nothing sensitive is present, but never echo a token even if one appeared."""
    if response is None:
        return None
    cleaned = json.loads(json.dumps(response))
    for key in ("auth_token", "token", "secret"):
        cleaned.pop(key, None)
    return cleaned


# ----------------------------- checks -----------------------------


def check_wrong_token(port: int) -> dict[str, Any]:
    with PluginConnection(port) as conn:
        response = conn.authenticate("wrong-token-" + uuid.uuid4().hex * 2)
        closed = conn.receive() is None if response is not None else True

    result = sanitize(response) or {}
    return {
        "name": "wrong_token_rejected",
        "response": result,
        "assertions": {
            "success_is_false": result.get("success") is False,
            "retryable_is_false": result.get("retryable") is False,
            "no_result_payload": result.get("result") in (None, {}),
            "no_session_id": "session_id" not in json.dumps(result),
            "no_session_nonce": "session_nonce" not in json.dumps(result),
            "no_capability_disclosure": "supported_operations" not in json.dumps(result),
            "no_plugin_state": result.get("plugin_state") in ("", None),
            "connection_closed": closed,
        },
    }


def check_valid_token_and_handshake(port: int, token: str) -> dict[str, Any]:
    with PluginConnection(port) as conn:
        auth = sanitize(conn.authenticate(token)) or {}
        health = sanitize(conn.roundtrip(build_request("health"))) or {}
        caps = sanitize(conn.roundtrip(build_request("capabilities"))) or {}

    health_result = health.get("result") or {}
    caps_result = caps.get("result") or {}

    return {
        "name": "valid_token_health_capabilities",
        "auth": auth,
        "health": health,
        "capabilities": caps,
        "assertions": {
            "auth_success": auth.get("success") is True,
            "multiple_requests_one_connection": bool(health) and bool(caps),
            "health_success": health.get("success") is True,
            "health_has_no_session_nonce": "session_nonce" not in health_result,
            "capabilities_success": caps.get("success") is True,
            "capabilities_has_session_nonce": bool(caps_result.get("session_nonce")),
            "session_id_consistent": (
                bool(health_result.get("session_id"))
                and health_result.get("session_id") == caps_result.get("session_id")
            ),
            "supported_operations_empty": caps_result.get("supported_operations") == [],
            "supported_entity_types_empty": caps_result.get("supported_entity_types") == [],
            "transaction_not_implemented": caps_result.get("transaction_support") == "NOT_IMPLEMENTED",
            "batch_not_implemented": caps_result.get("batch_support") == "NOT_IMPLEMENTED",
            "idempotency_not_implemented": caps_result.get("idempotency_support") == "NOT_IMPLEMENTED",
            "tianzheng_not_available": caps_result.get("tianzheng_support") == "NOT_AVAILABLE",
        },
    }


def check_unknown_operation(port: int, token: str) -> dict[str, Any]:
    with PluginConnection(port) as conn:
        conn.authenticate(token)
        response = sanitize(conn.roundtrip(build_request("send_command"))) or {}

    return {
        "name": "unknown_operation_rejected",
        "response": response,
        "assertions": {
            "success_is_false": response.get("success") is False,
            "error_is_unknown_operation": response.get("error_code") == "UNKNOWN_OPERATION",
            "stage_is_validation": response.get("stage") == "validation",
            "no_entities": response.get("entity_ids") == [] and response.get("handles") == [],
            "transaction_none": response.get("transaction_status") == "none",
            "document_none": response.get("document_status") == "none",
        },
    }


def check_stage_operation(port: int, token: str, operation: str) -> dict[str, Any]:
    """Core Application.Idle proof: a queued op must be executed by the main thread."""
    with PluginConnection(port) as conn:
        conn.authenticate(token)
        caps = sanitize(conn.roundtrip(build_request("capabilities"))) or {}
        nonce = (caps.get("result") or {}).get("session_nonce")

        missing = sanitize(conn.roundtrip(build_request(operation))) or {}
        wrong = sanitize(conn.roundtrip(build_request(operation, session_nonce="stale-nonce"))) or {}
        accepted = sanitize(conn.roundtrip(build_request(operation, session_nonce=nonce))) or {}

    markers = {}
    for warning in accepted.get("warnings") or []:
        if warning.startswith("dispatch="):
            markers = dict(
                part.split("=", 1) for part in warning.split(";") if "=" in part
            )

    return {
        "name": "stage_whitelisted_operation",
        "operation": operation,
        "nonce_missing_response": missing,
        "nonce_wrong_response": wrong,
        "accepted_response": accepted,
        "dispatch_markers": markers,
        "assertions": {
            "nonce_missing_rejected": missing.get("error_code") == "SESSION_NONCE_REQUIRED",
            "nonce_wrong_rejected": wrong.get("error_code") == "SESSION_NONCE_INVALID",
            "success_is_false": accepted.get("success") is False,
            "error_is_not_implemented_in_stage": accepted.get("error_code") == "NOT_IMPLEMENTED_IN_STAGE",
            "created_count_zero": accepted.get("created_count") == 0,
            "modified_count_zero": accepted.get("modified_count") == 0,
            "transaction_none": accepted.get("transaction_status") == "none",
            "document_none": accepted.get("document_status") == "none",
            "dispatched_via_application_idle": markers.get("dispatch") == "application_idle",
            "executed_on_main_thread": markers.get("on_main_thread") == "true",
            "thread_matches_initialize": (
                markers.get("executing_thread") == markers.get("initialize_main_thread")
            ),
            "idle_ticks_observed": int(markers.get("idle_ticks", "0")) > 0,
        },
    }


def check_port_closed(port: int) -> dict[str, Any]:
    try:
        with PluginConnection(port, timeout=3.0):
            refused = False
    except OSError:
        refused = True
    return {
        "name": "listener_stopped",
        "assertions": {"connection_refused": refused},
    }


# ----------------------------- driver -----------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="S7.1-B plugin host probe (loopback only)")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=str, default=None, help="sanitized evidence JSON path")
    parser.add_argument(
        "--check",
        choices=["all", "port-closed"],
        default="all",
    )
    parser.add_argument("--stage-operation", default="create_line")
    args = parser.parse_args()

    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")

    if args.check == "port-closed":
        report: dict[str, Any] = {
            "probe": "s7_1_b_plugin_host_probe",
            "endpoint": f"127.0.0.1:{args.port}",
            "checks": [check_port_closed(args.port)],
        }
    else:
        if not token:
            print("TIANZHENG_PLUGIN_TOKEN is not set in this process environment", file=sys.stderr)
            return 2
        report = {
            "probe": "s7_1_b_plugin_host_probe",
            "endpoint": f"127.0.0.1:{args.port}",
            "bind_address_used": "127.0.0.1",
            "token_source": "process environment (TIANZHENG_PLUGIN_TOKEN)",
            "token_digest": redact(token),
            "checks": [
                check_wrong_token(args.port),
                check_valid_token_and_handshake(args.port, token),
                check_unknown_operation(args.port, token),
                check_stage_operation(args.port, token, args.stage_operation),
            ],
        }

    failures = [
        f"{check['name']}.{name}"
        for check in report["checks"]
        for name, ok in check.get("assertions", {}).items()
        if not ok
    ]
    report["failed_assertions"] = failures
    report["all_assertions_passed"] = not failures

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

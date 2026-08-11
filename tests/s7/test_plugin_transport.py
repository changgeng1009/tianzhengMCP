"""S7.3 transport tests. No AutoCAD, no real socket: a fake connection drives the client."""
from __future__ import annotations

import json
import socket
import struct

import pytest

from mcp_nextgen.backends.plugin_transport import (
    MAX_PAYLOAD_BYTES,
    PLUGIN_PROTOCOL_VERSION,
    PluginExecutionOutcomeUnknown,
    PluginTransportClient,
    PluginTransportConfig,
    PluginTransportError,
    protocol_major,
    redact_token,
    validate_loopback_host,
)

TOKEN = "s7-test-token-0123456789abcdef0123456789"


def capabilities_result(**overrides):
    payload = {
        "protocol_version": "2.0.0", "capability_version": "s7.2-entity-mvp",
        "plugin_version": "0.2.0-s7.2", "process_id": 4242,
        "session_id": "sess-1", "session_nonce": "nonce-1",
        "readiness": True, "readiness_state": "AVAILABLE_SANDBOX_ENTITY_MVP",
        "supported_operations": ["health", "capabilities", "create_synthetic_document",
                                 "create_layer", "create_line", "create_circle",
                                 "create_polyline", "query_entities", "batch_execute",
                                 "save", "close", "reopen"],
        "supported_entity_types": ["circle", "line", "polyline"],
        "transaction_support": True, "batch_support": True,
        "batch_transaction_mode": "all_or_nothing", "dry_run_support": True,
        "document_ownership_support": True,
        "idempotency_support": "AVAILABLE_SANDBOX_MVP", "persistence_support": True,
        "tianzheng_support": "NOT_AVAILABLE", "autocad_version": "25.1.0.0",
    }
    payload.update(overrides)
    return payload


class FakeConnection:
    """Scripted responses; records every frame the client sent."""

    def __init__(self, host, port, timeout, *, responses=None, raise_on_receive=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.sent: list[dict] = []
        self.closed = False
        self._responses = list(responses or [])
        self._raise_on_receive = raise_on_receive

    def close(self):
        self.closed = True

    def send(self, payload):
        self.sent.append(dict(payload))

    def receive(self):
        if self._raise_on_receive is not None:
            raise self._raise_on_receive
        if not self._responses:
            raise PluginTransportError("CONNECTION_RESET", "no more scripted responses", retryable=True)
        return self._responses.pop(0)


def make_client(responses, **config_kwargs):
    holder = {}

    def factory(host, port, timeout):
        conn = FakeConnection(host, port, timeout, responses=list(responses))
        holder["conn"] = conn
        return conn

    client = PluginTransportClient(
        PluginTransportConfig(**config_kwargs), auth_token=TOKEN, connection_factory=factory)
    return client, holder


AUTH_OK = {"success": True, "stage": "authentication"}
CAPS_OK = {"success": True, "stage": "handshake", "result": capabilities_result()}


# ------------------------------------------------------------------ loopback


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_loopback_hosts_are_accepted(host):
    assert validate_loopback_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "10.0.0.1", "example.com", "", "localhost"])
def test_non_loopback_hosts_fail_closed(host):
    # 'localhost' is refused deliberately: it is DNS-resolved and could be repointed.
    with pytest.raises(PluginTransportError) as exc:
        validate_loopback_host(host)
    assert exc.value.error_code == "PLUGIN_HOST_NOT_LOOPBACK"


def test_client_refuses_a_non_loopback_configuration():
    with pytest.raises(PluginTransportError):
        PluginTransportClient(PluginTransportConfig(host="0.0.0.0"), auth_token=TOKEN)


# ------------------------------------------------------------------ token


def test_token_is_required_and_must_be_long_enough():
    for bad in ("", "short", "still-too-short-for-a-token"):
        with pytest.raises(PluginTransportError) as exc:
            PluginTransportClient(PluginTransportConfig(), auth_token=bad)
        assert exc.value.error_code == "PLUGIN_TOKEN_INVALID"


def test_repr_never_leaks_the_token():
    client, _ = make_client([])
    text = repr(client)
    assert TOKEN not in text
    assert "sha256:" in text


def test_redact_token_never_returns_the_secret():
    assert TOKEN not in redact_token(TOKEN)
    assert redact_token("") == "<empty>"


def test_exception_text_never_contains_the_token():
    client, _ = make_client([{"success": False, "error_code": "AUTH_FAILED"}])
    with pytest.raises(PluginTransportError) as exc:
        client.connect()
    assert TOKEN not in str(exc.value)


# ------------------------------------------------------------------ protocol


def test_handshake_caches_capabilities():
    client, _ = make_client([AUTH_OK, CAPS_OK])
    caps = client.connect()

    assert caps.protocol_version == "2.0.0"
    assert caps.session_id == "sess-1"
    assert caps.readiness is True
    assert caps.batch_transaction_mode == "all_or_nothing"
    assert caps.persistence_support is True
    assert caps.supports("create_line")
    assert not caps.supports("create_text")


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "3.0.0", "0.9.0"])
def test_incompatible_protocol_major_fails_closed(version):
    client, _ = make_client([
        AUTH_OK, {"success": True, "result": capabilities_result(protocol_version=version)}])
    with pytest.raises(PluginTransportError) as exc:
        client.connect()
    assert exc.value.error_code == "PLUGIN_PROTOCOL_VERSION_MISMATCH"
    assert exc.value.retryable is False


def test_protocol_major_parsing():
    assert protocol_major("2.0.0") == 2
    with pytest.raises(PluginTransportError):
        protocol_major("not-a-version")


def test_auth_failure_is_not_retryable():
    client, _ = make_client([{"success": False, "error_code": "AUTH_FAILED"}])
    with pytest.raises(PluginTransportError) as exc:
        client.connect()
    assert exc.value.error_code == "AUTH_FAILED"
    assert exc.value.retryable is False


def test_not_ready_plugin_is_rejected():
    client, _ = make_client([AUTH_OK, {"success": True, "result": capabilities_result(readiness=False)}])
    with pytest.raises(PluginTransportError) as exc:
        client.connect()
    assert exc.value.error_code == "PLUGIN_NOT_READY"


def test_requests_carry_no_auth_token_field():
    client, holder = make_client([AUTH_OK, CAPS_OK, {"success": True, "result": {}}])
    client.connect()
    client.call("health", mutating=False)

    business = [frame for frame in holder["conn"].sent if frame.get("type") != "auth"]
    assert business, "expected business frames"
    for frame in business:
        assert "auth_token" not in frame
        assert frame["protocol_version"] == PLUGIN_PROTOCOL_VERSION


def test_session_nonce_is_attached_to_business_requests():
    client, holder = make_client([AUTH_OK, CAPS_OK, {"success": True, "result": {}}])
    client.connect()
    client.call("health", mutating=False)

    health = [f for f in holder["conn"].sent if f.get("operation_type") == "health"][0]
    assert health["session_nonce"] == "nonce-1"


# ------------------------------------------------------------------ recovery


def test_connection_refused_is_reported_as_retryable():
    def factory(host, port, timeout):
        raise ConnectionRefusedError("nothing listening")

    client = PluginTransportClient(
        PluginTransportConfig(), auth_token=TOKEN, connection_factory=factory)
    with pytest.raises(PluginTransportError) as exc:
        client.connect()
    assert exc.value.error_code == "CONNECTION_REFUSED"
    assert exc.value.retryable is True


def test_stale_nonce_triggers_reconnect_for_a_read():
    # First call gets a stale-nonce rejection; the client reconnects and succeeds.
    sequences = [
        [AUTH_OK, CAPS_OK, {"success": False, "error_code": "SESSION_NONCE_INVALID"}],
        [AUTH_OK, CAPS_OK, {"success": True, "result": {"ok": True}}],
    ]
    calls = {"n": 0}

    def factory(host, port, timeout):
        conn = FakeConnection(host, port, timeout, responses=sequences[min(calls["n"], 1)])
        calls["n"] += 1
        return conn

    client = PluginTransportClient(
        PluginTransportConfig(), auth_token=TOKEN, connection_factory=factory)
    response = client.call("health", mutating=False)

    assert response["success"] is True
    assert calls["n"] == 2, "expected a reconnect"


def test_lost_response_on_a_write_is_unknown_outcome_not_a_retry():
    """The decisive safety rule: a sent write with no response is never re-sent."""
    def factory(host, port, timeout):
        return FakeConnection(
            host, port, timeout,
            responses=[AUTH_OK, CAPS_OK],
            raise_on_receive=None)

    client, holder = make_client([AUTH_OK, CAPS_OK])
    client.connect()
    holder["conn"]._raise_on_receive = OSError("connection dropped")

    with pytest.raises(PluginExecutionOutcomeUnknown) as exc:
        client.call("batch_execute", mutating=True)

    assert exc.value.error_code == "PLUGIN_EXECUTION_OUTCOME_UNKNOWN"
    assert exc.value.retryable is False
    batches = [f for f in holder["conn"].sent if f.get("operation_type") == "batch_execute"]
    assert len(batches) == 1, "a write must never be automatically re-sent"


def test_read_timeout_is_retryable_but_bounded():
    client, holder = make_client([AUTH_OK, CAPS_OK])
    client.connect()
    holder["conn"]._raise_on_receive = socket.timeout("timed out")

    with pytest.raises(PluginTransportError) as exc:
        client.call("health", mutating=False)
    assert exc.value.error_code in {"TIMEOUT", "CONNECTION_RESET"}


def test_disconnect_clears_session_state():
    client, _ = make_client([AUTH_OK, CAPS_OK])
    client.connect()
    assert client.connected and client.capabilities is not None

    client.disconnect()
    assert not client.connected
    assert client.capabilities is None
    assert client.session_id == ""


def test_oversized_payload_is_refused_before_send():
    from mcp_nextgen.backends.plugin_transport import _Connection

    class Sock:
        def sendall(self, data):
            raise AssertionError("must not send an oversized payload")

        def close(self):
            pass

    conn = _Connection.__new__(_Connection)
    conn._sock = Sock()
    with pytest.raises(PluginTransportError) as exc:
        conn.send({"blob": "x" * (MAX_PAYLOAD_BYTES + 10)})
    assert exc.value.error_code == "FRAME_TOO_LARGE"

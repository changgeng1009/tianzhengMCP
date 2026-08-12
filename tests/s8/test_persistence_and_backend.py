"""Persistence, idempotency and backend-routing rules.

AutoCAD and Tianzheng launch count for this file is 0. The real save/close/reopen round trip
is proven only by the opt-in integration run; nothing here simulates the Tianzheng API.
"""
from __future__ import annotations

import json

import pytest

from mcp_nextgen.s8.persistence import (
    IDEMPOTENCY_CONFLICT,
    NATIVE_IDENTITY_MISMATCH,
    NOT_READABLE,
    PIPE_NOT_FOUND,
    build_signature,
    compare_roundtrip,
    evaluate_replay,
)
from mcp_nextgen.s8.tianzheng_backend import (
    TIANZHENG_CAPABILITIES,
    TianzhengBackend,
    TianzhengBackendError,
    TianzhengPipeSpec,
)


def snapshot(runtime_class="TDbPipe", handle="211", start=(0.0, 0.0, 0.0),
             end=(3000.0, 0.0, 0.0), length=3000.0, properties=None):
    return {
        "runtime_class": runtime_class,
        "primary_handle": handle,
        "start": list(start),
        "end": list(end),
        "length": length,
        "properties": properties if properties is not None else {
            "diameter": {"value": None, "source": NOT_READABLE},
            "system": {"value": None, "source": NOT_READABLE},
            "elevation": {"value": 0.0, "source": "native_object"},
        },
    }


# ------------------------------------------------------------------ signature

def test_signature_keeps_only_properties_that_were_readable():
    sig = build_signature(snapshot())

    assert sig["native_runtime_class"] == "TDbPipe"
    assert sig["readable_properties"] == {"elevation": 0.0}
    assert sorted(sig["unavailable_properties"]) == ["diameter", "system"]


def test_unreadable_property_is_not_folded_in_as_null():
    # Two pipes with unreadable diameters must not be treated as "same diameter".
    sig = build_signature(snapshot())
    assert "diameter" not in sig["readable_properties"]


# ------------------------------------------------------------ persistence gate

def test_roundtrip_passes_when_class_and_geometry_survive():
    verdict = compare_roundtrip(snapshot(), snapshot())

    assert verdict["native_identity_preserved"] is True
    assert verdict["error_code"] is None
    assert verdict["handle_stable"] is True
    assert verdict["geometry_preserved"] is True


def test_roundtrip_fails_when_object_becomes_a_proxy():
    after = snapshot(runtime_class="AcDbProxyEntity")

    verdict = compare_roundtrip(snapshot(), after)

    assert verdict["native_identity_preserved"] is False
    assert verdict["error_code"] == NATIVE_IDENTITY_MISMATCH
    assert "not loaded in the reading session" in verdict["reasons"][0]


def test_roundtrip_fails_when_object_is_missing_after_reopen():
    verdict = compare_roundtrip(snapshot(), {"runtime_class": ""})

    assert verdict["native_identity_preserved"] is False
    assert verdict["error_code"] == PIPE_NOT_FOUND


def test_roundtrip_fails_when_class_degrades_to_an_ordinary_entity():
    verdict = compare_roundtrip(snapshot(), snapshot(runtime_class="AcDbLine"))

    assert verdict["native_identity_preserved"] is False
    assert verdict["error_code"] == NATIVE_IDENTITY_MISMATCH


def test_roundtrip_fails_when_geometry_moves():
    verdict = compare_roundtrip(snapshot(), snapshot(end=(2999.0, 0.0, 0.0)))

    assert verdict["geometry_preserved"] is False
    assert verdict["native_identity_preserved"] is False


def test_geometry_comparison_tolerates_float_noise():
    verdict = compare_roundtrip(snapshot(), snapshot(end=(3000.0 + 1e-9, 0.0, 0.0)))

    assert verdict["geometry_preserved"] is True


def test_handle_change_alone_does_not_fail_the_gate():
    # Semantic equivalence must not rest on the handle alone.
    verdict = compare_roundtrip(snapshot(handle="211"), snapshot(handle="9AB"))

    assert verdict["handle_stable"] is False
    assert verdict["native_identity_preserved"] is True


def test_readable_property_change_fails_the_gate():
    before = snapshot(properties={"elevation": {"value": 0.0, "source": "native_object"}})
    after = snapshot(properties={"elevation": {"value": 500.0, "source": "native_object"}})

    verdict = compare_roundtrip(before, after)

    assert verdict["property_mismatches"] == ["elevation"]
    assert verdict["native_identity_preserved"] is False


def test_properties_unreadable_on_either_side_are_not_compared():
    verdict = compare_roundtrip(snapshot(), snapshot())

    assert verdict["properties_compared"] == ["elevation"]
    assert set(verdict["properties_not_comparable"]) == {"diameter", "system"}


# --------------------------------------------------------------- idempotency

def inventory(pipes, fittings):
    return {"pipe_count": pipes, "fitting_count": fittings}


def test_replay_is_idempotent_when_nothing_new_appears():
    verdict = evaluate_replay(inventory(1, 2), inventory(1, 2), {"status": "already_applied"})

    assert verdict["idempotent"] is True
    assert verdict["duplicate_created"] is False
    assert verdict["error_code"] is None


def test_replay_that_creates_a_second_pipe_is_a_conflict():
    verdict = evaluate_replay(inventory(1, 2), inventory(2, 4), {"status": "created"})

    assert verdict["duplicate_created"] is True
    assert verdict["idempotent"] is False
    assert verdict["error_code"] == IDEMPOTENCY_CONFLICT


def test_duplicate_fittings_alone_still_fail_idempotency():
    # The pipe count held steady but the nodes doubled: still a broken guarantee.
    verdict = evaluate_replay(inventory(1, 2), inventory(1, 4), {"status": "already_applied"})

    assert verdict["duplicate_created"] is True
    assert verdict["idempotent"] is False


def test_equivalent_status_is_accepted():
    verdict = evaluate_replay(inventory(1, 2), inventory(1, 2), {"status": "equivalent"})
    assert verdict["idempotent"] is True


def test_replay_reporting_created_is_rejected_even_without_duplicates():
    verdict = evaluate_replay(inventory(1, 2), inventory(1, 2), {"status": "created"})

    assert verdict["idempotent"] is False
    assert "expected already_applied" in verdict["reasons"][0]


def test_replay_verdict_is_json_serializable():
    verdict = evaluate_replay(inventory(1, 2), inventory(1, 2), {"status": "already_applied"})
    assert json.loads(json.dumps(verdict))["idempotent"] is True


# ------------------------------------------------------------ backend routing

class FakeClient:
    """Records calls and replays queued responses. No sockets, no AutoCAD."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def call(self, operation_type, *, mutating, **kwargs):
        self.calls.append({"operation_type": operation_type, "mutating": mutating, **kwargs})
        for index, (op, response) in enumerate(self._responses):
            if op == operation_type:
                self._responses.pop(index)
                return response
        return {"success": True, "result": {}}


def ok(result):
    return {"success": True, "result": result}


CREATED = {
    "status": "created",
    "primary_handle": "211",
    "primary_runtime_class": "TDbPipe",
    "related_handles": ["212", "213"],
    "related_runtime_classes": ["TDbPipeFitting", "TDbPipeFitting"],
    "native_object_count": 3,
    "creation_method": "tianzheng_fixed_command",
    "pipe_count_before": 0, "pipe_count_after": 1,
    "fitting_count_before": 0, "fitting_count_after": 2,
    "native_identity_confirmed": True,
    "record_persisted": True,
}


def make_backend(responses):
    client = FakeClient(responses)
    return TianzhengBackend(client, poll_interval=0.0, poll_timeout=5.0), client


def test_backend_declares_only_the_minimal_capabilities():
    assert TIANZHENG_CAPABILITIES == (
        "create_native_pipe", "query_native_pipe", "validate_native_pipe_identity")
    for absent in ("create_valve", "create_fitting", "create_equipment", "annotation"):
        assert absent not in TIANZHENG_CAPABILITIES


def test_create_reports_primary_and_related_objects_separately():
    backend, _client = make_backend([
        ("tianzheng_create_pipe", ok({"started": True})),
        ("diagnostic_native_pipe_result", ok({"available": True, "running": False, "result": CREATED})),
    ])

    creation = backend.create_pipe(
        "tok", TianzhengPipeSpec((0, 0, 0), (3000, 0, 0)), idempotency_key="k1")

    assert creation.primary_handle == "211"
    assert creation.primary_runtime_class == "TDbPipe"
    assert creation.related_handles == ["212", "213"]
    assert creation.native_object_count == 3
    assert creation.native_identity_confirmed is True


def test_create_sends_structured_parameters_and_no_command_text():
    backend, client = make_backend([
        ("tianzheng_create_pipe", ok({"started": True})),
        ("diagnostic_native_pipe_result", ok({"available": True, "running": False, "result": CREATED})),
    ])

    backend.create_pipe("tok", TianzhengPipeSpec((0, 0, 0), (3000, 0, 0)), idempotency_key="k1")

    request = next(c for c in client.calls if c["operation_type"] == "tianzheng_create_pipe")
    assert request["parameters"] == {
        "start": [0, 0, 0], "end": [3000, 0, 0], "idempotency_key": "k1"}
    assert request["idempotency_key"] == "k1"
    assert request["mutating"] is True
    # Nothing resembling a command surface may cross the boundary.
    serialized = json.dumps(request)
    for forbidden in ("HZGX", "command", "lisp", "SendCommand", "keystroke"):
        assert forbidden.lower() not in serialized.lower()


def test_replayed_creation_is_surfaced_as_already_applied():
    replayed = dict(CREATED, status="already_applied", replayed_from_record=True,
                    pipe_count_after=1, fitting_count_after=2)
    backend, _client = make_backend([
        ("tianzheng_create_pipe", ok({"started": True})),
        ("diagnostic_native_pipe_result", ok({"available": True, "running": False, "result": replayed})),
    ])

    creation = backend.create_pipe(
        "tok", TianzhengPipeSpec((0, 0, 0), (3000, 0, 0)), idempotency_key="k1")

    assert creation.status == "already_applied"
    assert creation.replayed_from_record is True
    assert creation.duplicate_created is False


def test_creation_without_a_native_pipe_raises_structured_error():
    backend, _client = make_backend([
        ("tianzheng_create_pipe", ok({"started": True})),
        ("diagnostic_native_pipe_result", ok({
            "available": True, "running": False,
            "result": {"status": "no_native_pipe_in_diff", "new_objects": []}})),
    ])

    with pytest.raises(TianzhengBackendError) as excinfo:
        backend.create_pipe("tok", TianzhengPipeSpec((0, 0, 0), (1, 0, 0)), idempotency_key="k")

    assert excinfo.value.error_code == NATIVE_IDENTITY_MISMATCH


def test_idempotency_conflict_is_reported_with_its_own_code():
    backend, _client = make_backend([
        ("tianzheng_create_pipe", ok({"started": True})),
        ("diagnostic_native_pipe_result", ok({
            "available": True, "running": False,
            "result": {"status": "failed", "error_code": IDEMPOTENCY_CONFLICT,
                       "error": "key reused"}})),
    ])

    with pytest.raises(TianzhengBackendError) as excinfo:
        backend.create_pipe("tok", TianzhengPipeSpec((0, 0, 0), (1, 0, 0)), idempotency_key="k")

    assert excinfo.value.error_code == IDEMPOTENCY_CONFLICT


def test_validate_identity_rejects_a_proxy():
    backend, _client = make_backend([
        ("tianzheng_validate_pipe_identity",
         ok({"runtime_class": "AcDbProxyEntity", "native_identity_confirmed": False})),
    ])

    with pytest.raises(TianzhengBackendError) as excinfo:
        backend.validate_identity("tok", "211")

    assert excinfo.value.error_code == NATIVE_IDENTITY_MISMATCH


def test_query_is_non_mutating_and_returns_no_native_pointer():
    backend, client = make_backend([
        ("tianzheng_query_pipe", ok({"runtime_class": "TDbPipe", "primary_handle": "211"})),
    ])

    result = backend.query_pipe("tok", "211", ["212"])

    assert client.calls[0]["mutating"] is False
    assert result["runtime_class"] == "TDbPipe"
    for banned in ("unmanaged", "pointer", "dbobject"):
        assert banned not in json.dumps(result).lower()


def test_plugin_error_is_translated_into_a_structured_backend_error():
    client = FakeClient([("tianzheng_query_pipe",
                          {"success": False, "error_code": PIPE_NOT_FOUND,
                           "sanitized_message": "no such handle"})])
    backend = TianzhengBackend(client)

    with pytest.raises(TianzhengBackendError) as excinfo:
        backend.query_pipe("tok", "FFFF")

    assert excinfo.value.error_code == PIPE_NOT_FOUND
    assert excinfo.value.recoverable is False

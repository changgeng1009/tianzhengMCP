"""S7.2 entity-MVP acceptance probe.

Drives the real AutoCAD plugin over loopback and asserts the entity vertical closed loop:

  create_synthetic_document -> ownership token
    -> batch A (layer + line + circle + polyline)  -> COMMITTED
    -> query_entities                              -> verifies persisted geometry
    -> batch B (valid line + invalid circle)       -> ABORTED / ROLLED_BACK
    -> query_entities                              -> proves batch B's line is ABSENT
    -> random token write                          -> rejected, active document untouched

This is a diagnostic client, not AutoCadPluginBackend: it implements no ICadBackend and no
MCP route. It never opens a user DWG/DXF and never saves anything.

The token is read from TIANZHENG_PLUGIN_TOKEN and never printed -- only a digest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugin_host_probe import (  # noqa: E402
    PluginConnection,
    build_request,
    redact,
    sanitize,
)

LAYER = "S7_ENTITY_MVP"
JOB_ID = "s7-2-entity-mvp"

# Fixed synthetic test geometry. Not derived from any real drawing.
LINE_START = [0.0, 0.0, 0.0]
LINE_END = [1000.0, 500.0, 0.0]
CIRCLE_CENTER = [2000.0, 1000.0, 0.0]
CIRCLE_RADIUS = 250.0
POLY_VERTICES = [[0.0, 0.0], [500.0, 0.0], [500.0, 400.0], [0.0, 400.0]]

TOL = 1e-6


def close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= TOL


class Session:
    """One authenticated connection carrying the session nonce and document token."""

    def __init__(self, port: int, token: str) -> None:
        self._conn = PluginConnection(port, timeout=60.0)
        auth = self._conn.authenticate(token)
        if not (auth or {}).get("success"):
            raise RuntimeError("authentication failed")
        caps = sanitize(self._conn.roundtrip(build_request("capabilities"))) or {}
        self.capabilities = caps
        self.nonce: str = (caps.get("result") or {}).get("session_nonce", "")
        self.document_token: str | None = None

    def close(self) -> None:
        self._conn.close()

    def call(
        self,
        operation_type: str,
        parameters: dict[str, Any] | None = None,
        *,
        document_token: str | None = "__owned__",
        job_id: str = JOB_ID,
        timeout_ms: int = 60_000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        request = build_request(operation_type, session_nonce=self.nonce, timeout_ms=timeout_ms)
        request["job_id"] = job_id
        request["parameters"] = parameters or {}
        request["dry_run"] = dry_run
        token = self.document_token if document_token == "__owned__" else document_token
        request["document_context"] = {"document_token": token} if token else {}
        return sanitize(self._conn.roundtrip(request)) or {}


def op(operation_type: str, parameters: dict[str, Any], operation_id: str) -> dict[str, Any]:
    return {
        "operation_type": operation_type,
        "operation_id": operation_id,
        "parameters": parameters,
    }


# ----------------------------- checks -----------------------------


def check_create_document(session: Session) -> dict[str, Any]:
    response = session.call("create_synthetic_document", document_token=None)
    result = response.get("result") or {}
    session.document_token = result.get("document_token")

    return {
        "name": "create_synthetic_document",
        "response_summary": {
            "success": response.get("success"),
            "document_status": result.get("document_status"),
            "created_by_job": result.get("created_by_job"),
            "creation_method": result.get("creation_method"),
            "synthetic": result.get("synthetic"),
            "database_fingerprint": redact(result.get("database_fingerprint") or ""),
            "document_token": redact(result.get("document_token") or ""),
            "warnings": response.get("warnings"),
        },
        "assertions": {
            "success": response.get("success") is True,
            "token_returned": bool(result.get("document_token")),
            "token_is_unguessable_length": len(result.get("document_token") or "") == 64,
            "status_job_owned": result.get("document_status") == "JOB_OWNED_SYNTHETIC",
            "synthetic_flag": result.get("synthetic") is True,
            "fingerprint_present": bool(result.get("database_fingerprint")),
            "job_bound": result.get("created_by_job") == JOB_ID,
            "executed_on_main_thread": any(
                "on_main_thread=true" in w for w in (response.get("warnings") or [])
            ),
        },
    }


def check_batch_success(session: Session) -> dict[str, Any]:
    response = session.call(
        "batch_execute",
        {
            "transaction_mode": "all_or_nothing",
            "operations": [
                op("create_layer", {"layer": LAYER, "color_index": 3}, "a0-layer"),
                op("create_line", {"layer": LAYER, "start": LINE_START, "end": LINE_END}, "a1-line"),
                op("create_circle", {"layer": LAYER, "center": CIRCLE_CENTER, "radius": CIRCLE_RADIUS}, "a2-circle"),
                op("create_polyline", {"layer": LAYER, "vertices": POLY_VERTICES, "closed": True}, "a3-poly"),
            ],
        },
    )
    result = response.get("result") or {}
    handles = response.get("handles") or []

    return {
        "name": "batch_a_all_or_nothing_success",
        "batch_result": result,
        "handles": handles,
        "assertions": {
            "success": response.get("success") is True,
            "transaction_mode_all_or_nothing": result.get("transaction_mode") == "all_or_nothing",
            "transaction_committed": result.get("transaction_status") == "COMMITTED",
            "no_failed_operation": result.get("failed_operation_index") == -1,
            "no_partial_commit": result.get("partial_commit_status") is False,
            "rollback_not_applicable": result.get("rollback_status") == "NOT_APPLICABLE",
            "four_operation_results": len(result.get("operation_results") or []) == 4,
            "three_entities_created": result.get("created_count") == 3,
            "handles_non_empty": len(handles) == 3 and all(handles),
            "handles_unique": len(set(handles)) == len(handles),
            "executed_on_main_thread": any(
                "on_main_thread=true" in w for w in (response.get("warnings") or [])
            ),
        },
    }


def check_query_after_success(session: Session) -> dict[str, Any]:
    response = session.call("query_entities", {"layer": LAYER})
    result = response.get("result") or {}
    entities = result.get("entities") or []
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(entity.get("entity_type", ""), []).append(entity)

    line = (by_type.get("line") or [{}])[0]
    circle = (by_type.get("circle") or [{}])[0]
    poly = (by_type.get("polyline") or [{}])[0]

    line_geom = line.get("geometry") or {}
    circle_geom = circle.get("geometry") or {}
    poly_geom = poly.get("geometry") or {}
    poly_vertices = poly_geom.get("vertices") or []

    return {
        "name": "query_after_successful_batch",
        "entity_count": result.get("entity_count"),
        "entities": entities,
        "assertions": {
            "success": response.get("success") is True,
            "exactly_three_entities": result.get("entity_count") == 3,
            "one_line": len(by_type.get("line") or []) == 1,
            "one_circle": len(by_type.get("circle") or []) == 1,
            "one_polyline": len(by_type.get("polyline") or []) == 1,
            "all_on_requested_layer": all(e.get("layer") == LAYER for e in entities),
            "handles_non_empty": all(e.get("handle") for e in entities),
            "handles_unique": len({e.get("handle") for e in entities}) == len(entities),
            "line_start_matches": close((line_geom.get("start") or {}).get("x", -1), LINE_START[0])
            and close((line_geom.get("start") or {}).get("y", -1), LINE_START[1]),
            "line_end_matches": close((line_geom.get("end") or {}).get("x", -1), LINE_END[0])
            and close((line_geom.get("end") or {}).get("y", -1), LINE_END[1]),
            "circle_center_matches": close((circle_geom.get("center") or {}).get("x", -1), CIRCLE_CENTER[0])
            and close((circle_geom.get("center") or {}).get("y", -1), CIRCLE_CENTER[1]),
            "circle_radius_matches": close(circle_geom.get("radius", -1), CIRCLE_RADIUS),
            "polyline_vertex_count_matches": len(poly_vertices) == len(POLY_VERTICES),
            "polyline_vertices_match": all(
                close(actual.get("x", -1), expected[0]) and close(actual.get("y", -1), expected[1])
                for actual, expected in zip(poly_vertices, POLY_VERTICES)
            ),
            "polyline_closed": poly_geom.get("closed") is True,
        },
    }


def check_batch_rollback(session: Session) -> dict[str, Any]:
    """op0 valid line, op1 invalid circle -> the whole transaction must abort."""
    response = session.call(
        "batch_execute",
        {
            "transaction_mode": "all_or_nothing",
            "operations": [
                op("create_line", {"layer": LAYER, "start": [9000.0, 9000.0], "end": [9500.0, 9500.0]}, "b0-line"),
                op("create_circle", {"layer": LAYER, "center": [9000.0, 9000.0], "radius": -50.0}, "b1-bad-circle"),
            ],
        },
    )
    result = response.get("result") or {}

    op_results = result.get("operation_results") or []

    return {
        "name": "batch_b_rollback",
        "batch_result": result,
        "error_code": response.get("error_code"),
        "assertions": {
            "batch_failed": response.get("success") is False,
            "error_is_batch_rolled_back": response.get("error_code") == "BATCH_ROLLED_BACK",
            # A REAL transaction must have started and then aborted. NOT_STARTED would mean
            # the batch was rejected before any transaction, which proves nothing about rollback.
            "transaction_actually_started_then_aborted": result.get("transaction_status") == "ABORTED",
            "rollback_status_rolled_back": result.get("rollback_status") == "ROLLED_BACK",
            "failed_operation_index_is_1": result.get("failed_operation_index") == 1,
            "failed_operation_id_reported": bool(result.get("failed_operation_id")),
            "no_partial_commit": result.get("partial_commit_status") is False,
            "created_count_zero": result.get("created_count") == 0,
            "no_handles_returned": not (response.get("handles") or []),
            # op0 must have been attempted (reached execution) before the abort.
            "op0_reached_execution": len(op_results) >= 1,
            "op0_reports_no_surviving_entity": all(
                not (r.get("entities") or []) for r in op_results
            ),
        },
    }


def check_query_after_rollback(session: Session) -> dict[str, Any]:
    """The decisive check: batch B's *valid* line must NOT exist."""
    response = session.call("query_entities", {"layer": LAYER})
    result = response.get("result") or {}
    entities = result.get("entities") or []

    rollback_line_present = False
    for entity in entities:
        if entity.get("entity_type") != "line":
            continue
        start = (entity.get("geometry") or {}).get("start") or {}
        if close(start.get("x", -1), 9000.0) and close(start.get("y", -1), 9000.0):
            rollback_line_present = True

    return {
        "name": "query_after_rollback",
        "entity_count": result.get("entity_count"),
        "assertions": {
            "success": response.get("success") is True,
            "still_exactly_three_entities": result.get("entity_count") == 3,
            "rolled_back_line_absent": rollback_line_present is False,
        },
    }


def check_unknown_document(session: Session) -> dict[str, Any]:
    random_token = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars, never registered
    response = session.call(
        "create_line",
        {"layer": LAYER, "start": [1.0, 1.0], "end": [2.0, 2.0]},
        document_token=random_token,
    )
    missing = session.call(
        "create_line",
        {"layer": LAYER, "start": [1.0, 1.0], "end": [2.0, 2.0]},
        document_token=None,
    )
    wrong_job = session.call(
        "create_line",
        {"layer": LAYER, "start": [1.0, 1.0], "end": [2.0, 2.0]},
        job_id="some-other-job",
    )

    ownership_errors = {
        "DOCUMENT_TOKEN_INVALID", "DOCUMENT_NOT_JOB_OWNED",
        "DOCUMENT_SESSION_MISMATCH", "DOCUMENT_DATABASE_MISMATCH",
    }

    return {
        "name": "unknown_document_rejected",
        "random_token_error": response.get("error_code"),
        "missing_token_error": missing.get("error_code"),
        "wrong_job_error": wrong_job.get("error_code"),
        "assertions": {
            "random_token_rejected": response.get("error_code") in ownership_errors,
            "random_token_no_write": response.get("created_count") == 0,
            "random_token_no_transaction": response.get("transaction_status") in ("none", "NOT_STARTED"),
            "missing_token_rejected": missing.get("error_code") == "DOCUMENT_TOKEN_REQUIRED",
            "wrong_job_rejected": wrong_job.get("error_code") == "DOCUMENT_JOB_MISMATCH",
        },
    }


def check_final_isolation(session: Session) -> dict[str, Any]:
    """All entities must live in the plugin-created document and nowhere else."""
    response = session.call("query_entities", {})
    result = response.get("result") or {}
    entities = result.get("entities") or []

    return {
        "name": "synthetic_document_isolation",
        "total_entities_in_owned_document": result.get("entity_count"),
        "assertions": {
            "success": response.get("success") is True,
            "only_expected_entities": result.get("entity_count") == 3,
            "all_on_test_layer": all(e.get("layer") == LAYER for e in entities),
        },
    }


# ----------------------------- driver -----------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="S7.2 entity MVP probe (loopback only)")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    if not token:
        print("TIANZHENG_PLUGIN_TOKEN is not set", file=sys.stderr)
        return 2

    session = Session(args.port, token)
    try:
        caps_result = (session.capabilities.get("result") or {})
        checks = [
            {
                "name": "handshake",
                "capabilities": {
                    "readiness": caps_result.get("readiness"),
                    "readiness_state": caps_result.get("readiness_state"),
                    "protocol_version": caps_result.get("protocol_version"),
                    "capability_version": caps_result.get("capability_version"),
                    "supported_operations": caps_result.get("supported_operations"),
                    "supported_entity_types": caps_result.get("supported_entity_types"),
                    "transaction_support": caps_result.get("transaction_support"),
                    "batch_support": caps_result.get("batch_support"),
                    "batch_transaction_mode": caps_result.get("batch_transaction_mode"),
                    "idempotency_support": caps_result.get("idempotency_support"),
                    "tianzheng_support": caps_result.get("tianzheng_support"),
                    "process_id": caps_result.get("process_id"),
                    "autocad_version": caps_result.get("autocad_version"),
                },
                "assertions": {
                    "readiness_is_boolean": isinstance(caps_result.get("readiness"), bool),
                    "readiness_true": caps_result.get("readiness") is True,
                    "idempotency_not_implemented": caps_result.get("idempotency_support") == "NOT_IMPLEMENTED",
                    "tianzheng_not_available": caps_result.get("tianzheng_support") == "NOT_AVAILABLE",
                },
            },
            check_create_document(session),
            check_batch_success(session),
            check_query_after_success(session),
            check_batch_rollback(session),
            check_query_after_rollback(session),
            check_unknown_document(session),
            check_final_isolation(session),
        ]
    finally:
        session.close()

    report: dict[str, Any] = {
        "probe": "s7_2_entity_mvp_probe",
        "endpoint": f"127.0.0.1:{args.port}",
        "job_id": JOB_ID,
        "layer": LAYER,
        "token_digest": redact(token),
        "checks": checks,
    }

    failures = [
        f"{check['name']}.{name}"
        for check in checks
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

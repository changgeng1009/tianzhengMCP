"""S7.2 closure smoke: capability, rollback result semantics, and real dry_run.

Minimal run against the FINAL binary. It does not repeat the full S7.2 acceptance; it
verifies only the four items closed in this round:

  1. capabilities  -> protocol 2.0.0, readiness boolean, AVAILABLE_SANDBOX_ENTITY_MVP
  2. synthetic doc -> a fresh job-owned document
  3. rollback      -> ABORTED / ROLLED_BACK, op0 success=false + ROLLED_BACK + no handles,
                      and the line really is absent afterwards
  4. dry_run       -> entity count unchanged, no write transaction, created_count 0

Never opens a user DWG/DXF, never saves.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugin_host_probe import (  # noqa: E402
    LEGACY_PROTOCOL_VERSION,
    PluginConnection,
    redact,
    sanitize,
)
from s7_2_entity_probe import LAYER, Session, op  # noqa: E402

JOB_ID = "s7-2-closure"


def check_legacy_protocol_rejected(port: int, token: str) -> dict[str, Any]:
    """A 1.x client must be refused: it cannot parse a 2.x response."""
    with PluginConnection(port, timeout=15.0) as conn:
        response = sanitize(
            conn.roundtrip(
                {
                    "type": "auth",
                    "auth_token": token,
                    "protocol_version": LEGACY_PROTOCOL_VERSION,
                }
            )
        ) or {}

    return {
        "name": "legacy_protocol_rejected",
        "declared_version": LEGACY_PROTOCOL_VERSION,
        "response": response,
        "assertions": {
            "rejected": response.get("success") is False,
            "no_capability_disclosed": "supported_operations" not in json.dumps(response),
        },
    }


def check_capabilities(session: Session) -> dict[str, Any]:
    result = (session.capabilities.get("result") or {})
    ops = result.get("supported_operations") or []
    required = [
        "create_synthetic_document", "create_layer", "create_line",
        "create_circle", "create_polyline", "query_entities", "batch_execute",
    ]

    return {
        "name": "capabilities",
        "snapshot": {
            "protocol_version": result.get("protocol_version"),
            "capability_version": result.get("capability_version"),
            "plugin_version": result.get("plugin_version"),
            "readiness": result.get("readiness"),
            "readiness_state": result.get("readiness_state"),
            "supported_operations": ops,
            "supported_entity_types": result.get("supported_entity_types"),
            "transaction_support": result.get("transaction_support"),
            "batch_support": result.get("batch_support"),
            "document_ownership_support": result.get("document_ownership_support"),
            "batch_transaction_mode": result.get("batch_transaction_mode"),
            "dry_run_support": result.get("dry_run_support"),
            "idempotency_support": result.get("idempotency_support"),
            "tianzheng_support": result.get("tianzheng_support"),
            "process_id": result.get("process_id"),
            "autocad_version": result.get("autocad_version"),
        },
        "assertions": {
            "protocol_is_2_0_0": result.get("protocol_version") == "2.0.0",
            "readiness_is_boolean": isinstance(result.get("readiness"), bool),
            "readiness_true": result.get("readiness") is True,
            "readiness_state_available": result.get("readiness_state") == "AVAILABLE_SANDBOX_ENTITY_MVP",
            "all_required_operations_present": all(o in ops for o in required),
            "save_not_advertised": "save" not in ops,
            "close_not_advertised": "close" not in ops,
            "reopen_not_advertised": "reopen" not in ops,
            "entity_types_exact": result.get("supported_entity_types") == ["circle", "line", "polyline"],
            "transaction_support_true": result.get("transaction_support") is True,
            "batch_support_true": result.get("batch_support") is True,
            "document_ownership_support_true": result.get("document_ownership_support") is True,
            "batch_mode_all_or_nothing": result.get("batch_transaction_mode") == "all_or_nothing",
            "dry_run_support_is_boolean": isinstance(result.get("dry_run_support"), bool),
            "idempotency_not_implemented": result.get("idempotency_support") == "NOT_IMPLEMENTED",
            "tianzheng_not_available": result.get("tianzheng_support") == "NOT_AVAILABLE",
        },
    }


def check_document(session: Session) -> dict[str, Any]:
    response = session.call("create_synthetic_document", document_token=None, job_id=JOB_ID)
    result = response.get("result") or {}
    session.document_token = result.get("document_token")

    return {
        "name": "synthetic_document",
        "document_token_digest": redact(result.get("document_token") or ""),
        "document_status": result.get("document_status"),
        "assertions": {
            "success": response.get("success") is True,
            "job_owned": result.get("document_status") == "JOB_OWNED_SYNTHETIC",
            "token_returned": len(result.get("document_token") or "") == 64,
        },
    }


def entity_count(session: Session) -> int:
    response = session.call("query_entities", {}, job_id=JOB_ID)
    return ((response.get("result") or {}).get("entity_count")) or 0


def check_rollback_semantics(session: Session) -> dict[str, Any]:
    before = entity_count(session)

    response = session.call(
        "batch_execute",
        {
            "transaction_mode": "all_or_nothing",
            "operations": [
                op("create_layer", {"layer": LAYER}, "c0-layer"),
                op("create_line", {"layer": LAYER, "start": [100.0, 100.0], "end": [700.0, 700.0]}, "c1-line"),
                op("create_circle", {"layer": LAYER, "center": [100.0, 100.0], "radius": -25.0}, "c2-bad-circle"),
            ],
        },
        job_id=JOB_ID,
    )
    result = response.get("result") or {}
    ops = result.get("operation_results") or []

    by_index = {o.get("operation_index"): o for o in ops}
    op0 = by_index.get(0) or {}
    op1 = by_index.get(1) or {}
    op2 = by_index.get(2) or {}

    after = entity_count(session)

    # The valid line must be absent.
    query = session.call("query_entities", {"entity_type": "line"}, job_id=JOB_ID)
    lines = ((query.get("result") or {}).get("entities")) or []
    rollback_line_present = any(
        abs(((e.get("geometry") or {}).get("start") or {}).get("x", -1) - 100.0) < 1e-6
        and abs(((e.get("geometry") or {}).get("start") or {}).get("y", -1) - 100.0) < 1e-6
        for e in lines
    )

    return {
        "name": "rollback_result_semantics",
        "batch_result": result,
        "entity_count_before": before,
        "entity_count_after": after,
        "assertions": {
            "batch_success_false": response.get("success") is False,
            "error_batch_rolled_back": response.get("error_code") == "BATCH_ROLLED_BACK",
            "transaction_aborted": result.get("transaction_status") == "ABORTED",
            "rollback_status_rolled_back": result.get("rollback_status") == "ROLLED_BACK",
            "partial_commit_false": result.get("partial_commit_status") is False,
            "batch_created_count_zero": result.get("created_count") == 0,
            "failed_index_is_2": result.get("failed_operation_index") == 2,
            # No operation in an aborted batch may claim success.
            "no_operation_reports_success": all(o.get("success") is False for o in ops),
            "op0_success_false": op0.get("success") is False,
            "op0_entity_status_rolled_back": op0.get("entity_status") == "ROLLED_BACK",
            "op0_execution_status_rolled_back": op0.get("execution_status") == "EXECUTED_THEN_ROLLED_BACK",
            "op0_handles_empty": not (op0.get("handles") or []),
            "op0_entity_ids_empty": not (op0.get("entity_ids") or []),
            "op0_created_count_zero": op0.get("created_count") == 0,
            "op1_success_false": op1.get("success") is False,
            "op1_entity_status_rolled_back": op1.get("entity_status") == "ROLLED_BACK",
            "op1_handles_empty": not (op1.get("handles") or []),
            "op2_failed": op2.get("success") is False and op2.get("entity_status") == "FAILED",
            "op2_has_specific_error": op2.get("error_code") == "INVALID_GEOMETRY",
            # Real rollback, not just result shaping.
            "entity_count_unchanged": before == after,
            "rolled_back_line_absent": rollback_line_present is False,
        },
    }


def check_dry_run(session: Session) -> dict[str, Any]:
    before = entity_count(session)

    request = {
        "transaction_mode": "all_or_nothing",
        "operations": [
            op("create_layer", {"layer": LAYER}, "d0-layer"),
            op("create_line", {"layer": LAYER, "start": [10.0, 10.0], "end": [20.0, 20.0]}, "d1-line"),
        ],
    }
    response = session.call("batch_execute", request, job_id=JOB_ID, dry_run=True)
    result = response.get("result") or {}
    ops = result.get("operation_results") or []

    after = entity_count(session)

    return {
        "name": "dry_run",
        "batch_result": result,
        "entity_count_before": before,
        "entity_count_after": after,
        "assertions": {
            "transaction_status_dry_run": result.get("transaction_status") == "DRY_RUN_NOT_STARTED",
            "created_count_zero": response.get("created_count") == 0,
            "batch_created_count_zero": result.get("created_count") == 0,
            "no_handles": not (response.get("handles") or []),
            "entity_count_unchanged": before == after,
            "all_ops_marked_dry_run": all(
                o.get("execution_status") == "DRY_RUN_VALIDATED_NOT_EXECUTED" for o in ops
            ),
            "no_op_claims_success": all(o.get("success") is False for o in ops),
            "document_still_job_owned": response.get("document_status") == "JOB_OWNED_SYNTHETIC",
        },
    }


def check_dry_run_rejects_invalid(session: Session) -> dict[str, Any]:
    """Dry run must really validate, not merely echo."""
    before = entity_count(session)
    response = session.call(
        "batch_execute",
        {
            "operations": [
                op("create_circle", {"layer": LAYER, "center": [0.0, 0.0], "radius": -1.0}, "e0-bad"),
            ],
        },
        job_id=JOB_ID,
        dry_run=True,
    )
    result = response.get("result") or {}
    after = entity_count(session)

    return {
        "name": "dry_run_validates_geometry",
        "error_code": response.get("error_code"),
        "assertions": {
            "rejected": response.get("success") is False,
            "still_no_transaction": result.get("transaction_status") == "DRY_RUN_NOT_STARTED",
            "entity_count_unchanged": before == after,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="S7.2 closure smoke (loopback only)")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    if not token:
        print("TIANZHENG_PLUGIN_TOKEN is not set", file=sys.stderr)
        return 2

    legacy = check_legacy_protocol_rejected(args.port, token)

    session = Session(args.port, token)
    try:
        checks = [
            legacy,
            check_capabilities(session),
            check_document(session),
            check_rollback_semantics(session),
            check_dry_run(session),
            check_dry_run_rejects_invalid(session),
        ]
    finally:
        session.close()

    report: dict[str, Any] = {
        "probe": "s7_2_closure_smoke",
        "endpoint": f"127.0.0.1:{args.port}",
        "job_id": JOB_ID,
        "token_digest": redact(token),
        "checks": checks,
    }
    failures = [
        f"{c['name']}.{n}"
        for c in checks
        for n, ok in c.get("assertions", {}).items()
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

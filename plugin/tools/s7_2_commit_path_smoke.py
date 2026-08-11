"""S7.2 final-binary COMMIT path smoke.

The one path the final AVAILABLE binary had not yet re-proven for itself: a successful
all_or_nothing batch that really COMMITs, followed by a query that reads the geometry back
out of the AutoCAD Database (not echoed from the request).

  capabilities -> create_synthetic_document
    -> batch(layer + line + circle + polyline)  -> COMMITTED, 3 handles
    -> query_entities                           -> 3 entities, geometry read from the DB

Rollback and dry-run are NOT repeated here; the same binary proved those in the closure run.
Never opens a user DWG/DXF, never saves. The token is never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugin_host_probe import redact  # noqa: E402
from s7_2_entity_probe import Session, op  # noqa: E402

JOB_ID = "s7-2-final-binary-smoke"
LAYER = "S7_FINAL_BINARY_SMOKE"

# Simple, distinct, non-overlapping synthetic geometry. Not derived from any real drawing.
LINE_START = [0.0, 0.0, 0.0]
LINE_END = [400.0, 0.0, 0.0]
CIRCLE_CENTER = [1200.0, 0.0, 0.0]
CIRCLE_RADIUS = 150.0
POLY_VERTICES = [[0.0, 800.0], [300.0, 800.0], [300.0, 1100.0]]
POLY_CLOSED = False

TOL = 1e-6


def close(a: Any, b: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= TOL
    except (TypeError, ValueError):
        return False


def check_capabilities(session: Session, expected_pid: int | None) -> dict[str, Any]:
    r = session.capabilities.get("result") or {}
    return {
        "name": "capability_confirmation",
        "snapshot": {
            "protocol_version": r.get("protocol_version"),
            "capability_version": r.get("capability_version"),
            "plugin_version": r.get("plugin_version"),
            "readiness": r.get("readiness"),
            "readiness_state": r.get("readiness_state"),
            "transaction_support": r.get("transaction_support"),
            "batch_support": r.get("batch_support"),
            "batch_transaction_mode": r.get("batch_transaction_mode"),
            "tianzheng_support": r.get("tianzheng_support"),
            "process_id": r.get("process_id"),
            "autocad_version": r.get("autocad_version"),
        },
        "assertions": {
            "protocol_2_0_0": r.get("protocol_version") == "2.0.0",
            "readiness_true": r.get("readiness") is True,
            "readiness_state_available": r.get("readiness_state") == "AVAILABLE_SANDBOX_ENTITY_MVP",
            "process_id_matches_test_owned_pid": (
                expected_pid is None or r.get("process_id") == expected_pid
            ),
            "transaction_support_true": r.get("transaction_support") is True,
            "batch_support_true": r.get("batch_support") is True,
            "batch_mode_all_or_nothing": r.get("batch_transaction_mode") == "all_or_nothing",
            "tianzheng_not_available": r.get("tianzheng_support") == "NOT_AVAILABLE",
        },
    }


def check_document(session: Session) -> dict[str, Any]:
    response = session.call("create_synthetic_document", document_token=None, job_id=JOB_ID)
    result = response.get("result") or {}
    session.document_token = result.get("document_token")

    return {
        "name": "synthetic_document",
        "document_status": result.get("document_status"),
        "created_by_job": result.get("created_by_job"),
        "creation_method": result.get("creation_method"),
        "document_token_digest": redact(result.get("document_token") or ""),
        "database_fingerprint_digest": redact(result.get("database_fingerprint") or ""),
        "assertions": {
            "success": response.get("success") is True,
            "job_owned_synthetic": result.get("document_status") == "JOB_OWNED_SYNTHETIC",
            "token_non_empty": bool(result.get("document_token")),
            "token_unguessable_length": len(result.get("document_token") or "") == 64,
            "job_bound": result.get("created_by_job") == JOB_ID,
            "fingerprint_present": bool(result.get("database_fingerprint")),
        },
    }


def check_commit_batch(session: Session) -> dict[str, Any]:
    response = session.call(
        "batch_execute",
        {
            "transaction_mode": "all_or_nothing",
            "operations": [
                op("create_layer", {"layer": LAYER, "color_index": 5}, "f0-layer"),
                op("create_line", {"layer": LAYER, "start": LINE_START, "end": LINE_END}, "f1-line"),
                op("create_circle", {"layer": LAYER, "center": CIRCLE_CENTER, "radius": CIRCLE_RADIUS}, "f2-circle"),
                op("create_polyline", {"layer": LAYER, "vertices": POLY_VERTICES, "closed": POLY_CLOSED}, "f3-poly"),
            ],
        },
        job_id=JOB_ID,
    )
    result = response.get("result") or {}
    ops = result.get("operation_results") or []
    handles = response.get("handles") or []

    by_index = {o.get("operation_index"): o for o in ops}
    layer_op = by_index.get(0) or {}
    entity_ops = [by_index.get(i) or {} for i in (1, 2, 3)]

    committed_states = {"EXECUTED_AND_COMMITTED"}
    op_handles = [h for o in entity_ops for h in (o.get("handles") or [])]

    return {
        "name": "successful_commit_batch",
        "batch_result": result,
        "handles": handles,
        "dispatch_markers": [w for w in (response.get("warnings") or []) if "dispatch" in w],
        "assertions": {
            "batch_success": response.get("success") is True,
            "transaction_mode_all_or_nothing": result.get("transaction_mode") == "all_or_nothing",
            "transaction_committed": result.get("transaction_status") == "COMMITTED",
            "partial_commit_false": result.get("partial_commit_status") is False,
            "rollback_not_applicable": result.get("rollback_status") == "NOT_APPLICABLE",
            "failed_operation_index_minus_one": result.get("failed_operation_index") == -1,
            "created_count_is_3": result.get("created_count") == 3,
            "four_operation_results": len(ops) == 4,
            "all_four_operations_success": all(o.get("success") is True for o in ops),
            "layer_operation_succeeded": layer_op.get("entity_status") in ("CREATED", "EXISTING_EQUIVALENT"),
            "three_entities_created": all(o.get("entity_status") == "CREATED" for o in entity_ops),
            "entity_execution_status_committed": all(
                o.get("execution_status") in committed_states for o in entity_ops
            ),
            "entity_ops_have_handles": all(o.get("handles") for o in entity_ops),
            "top_level_three_handles": len(handles) == 3,
            "handles_non_empty": all(bool(h) for h in handles),
            "handles_unique": len(set(handles)) == 3,
            "operation_handles_match_top_level": sorted(op_handles) == sorted(handles),
            "executed_on_main_thread": any(
                "on_main_thread=true" in w for w in (response.get("warnings") or [])
            ),
        },
    }


def check_query(session: Session) -> dict[str, Any]:
    """Geometry MUST come from the query response, i.e. read back out of the Database."""
    response = session.call("query_entities", {"layer": LAYER}, job_id=JOB_ID)
    result = response.get("result") or {}
    entities = result.get("entities") or []

    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        by_type.setdefault(e.get("entity_type", ""), []).append(e)

    line = (by_type.get("line") or [{}])[0]
    circle = (by_type.get("circle") or [{}])[0]
    poly = (by_type.get("polyline") or [{}])[0]

    lg = line.get("geometry") or {}
    cg = circle.get("geometry") or {}
    pg = poly.get("geometry") or {}
    pv = pg.get("vertices") or []

    line_start = lg.get("start") or {}
    line_end = lg.get("end") or {}
    circle_center = cg.get("center") or {}

    return {
        "name": "query_from_database",
        "entity_count": result.get("entity_count"),
        "entities": entities,
        "geometry_comparison": {
            "line_start_expected": LINE_START[:2], "line_start_actual": [line_start.get("x"), line_start.get("y")],
            "line_end_expected": LINE_END[:2], "line_end_actual": [line_end.get("x"), line_end.get("y")],
            "circle_center_expected": CIRCLE_CENTER[:2], "circle_center_actual": [circle_center.get("x"), circle_center.get("y")],
            "circle_radius_expected": CIRCLE_RADIUS, "circle_radius_actual": cg.get("radius"),
            "polyline_vertices_expected": POLY_VERTICES,
            "polyline_vertices_actual": [[v.get("x"), v.get("y")] for v in pv],
            "polyline_closed_expected": POLY_CLOSED, "polyline_closed_actual": pg.get("closed"),
        },
        "assertions": {
            "query_success": response.get("success") is True,
            "entity_count_is_3": result.get("entity_count") == 3,
            "exactly_one_line": len(by_type.get("line") or []) == 1,
            "exactly_one_circle": len(by_type.get("circle") or []) == 1,
            "exactly_one_polyline": len(by_type.get("polyline") or []) == 1,
            "all_on_smoke_layer": all(e.get("layer") == LAYER for e in entities),
            "all_handles_non_empty": all(e.get("handle") for e in entities),
            "all_handles_unique": len({e.get("handle") for e in entities}) == 3,
            "line_start_matches_db": close(line_start.get("x"), LINE_START[0]) and close(line_start.get("y"), LINE_START[1]),
            "line_end_matches_db": close(line_end.get("x"), LINE_END[0]) and close(line_end.get("y"), LINE_END[1]),
            "circle_center_matches_db": close(circle_center.get("x"), CIRCLE_CENTER[0]) and close(circle_center.get("y"), CIRCLE_CENTER[1]),
            "circle_radius_matches_db": close(cg.get("radius"), CIRCLE_RADIUS),
            "polyline_vertex_count_matches_db": len(pv) == len(POLY_VERTICES),
            "polyline_vertices_match_db": len(pv) == len(POLY_VERTICES) and all(
                close(a.get("x"), e[0]) and close(a.get("y"), e[1]) for a, e in zip(pv, POLY_VERTICES)
            ),
            "polyline_closed_matches_db": pg.get("closed") is POLY_CLOSED,
        },
    }


def check_isolation(session: Session) -> dict[str, Any]:
    """Nothing beyond the smoke entities exists in the owned document."""
    response = session.call("query_entities", {}, job_id=JOB_ID)
    result = response.get("result") or {}
    entities = result.get("entities") or []
    return {
        "name": "document_isolation",
        "total_entities": result.get("entity_count"),
        "assertions": {
            "only_the_three_smoke_entities": result.get("entity_count") == 3,
            "all_on_smoke_layer": all(e.get("layer") == LAYER for e in entities),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="S7.2 final-binary commit path smoke")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--expect-pid", type=int, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    if not token:
        print("TIANZHENG_PLUGIN_TOKEN is not set", file=sys.stderr)
        return 2

    session = Session(args.port, token)
    try:
        checks = [
            check_capabilities(session, args.expect_pid),
            check_document(session),
            check_commit_batch(session),
            check_query(session),
            check_isolation(session),
        ]
    finally:
        session.close()

    report: dict[str, Any] = {
        "probe": "s7_2_final_binary_commit_path_smoke",
        "endpoint": f"127.0.0.1:{args.port}",
        "job_id": JOB_ID,
        "layer": LAYER,
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

"""S7.6 full-chain real AutoCAD acceptance.

Drives the OFFICIAL path only:

    structured request -> S6 CadOperationPlan -> CapabilityRouter
      -> AutoCadPluginBackend -> PluginTransportClient -> AutoCAD plugin

No diagnostic probe is used for any acceptance assertion. Requires a running AutoCAD with
the plugin NETLOADed, and the session token/port in the environment.

Environment:
    TIANZHENG_PLUGIN_TOKEN, TIANZHENG_PLUGIN_PORT
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.autocad_plugin import AutoCadPluginBackend, PluginBackendError
from mcp_nextgen.backends.capability_router import PLUGIN_BACKEND
from mcp_nextgen.backends.plugin_transport import (
    PluginTransportClient,
    PluginTransportConfig,
    redact_token,
)
from mcp_nextgen.s6.contracts import (
    S6_SYNTHETIC_LAYER,
    CadOperation,
    CadOperationPlan,
    EntitySpec,
    LayerSpec,
)
from mcp_nextgen.control_server.dispatcher import configure_plugin_route_service, dispatch_tool
from mcp_nextgen.protocol.version import PROTOCOL_VERSION
from mcp_nextgen.s7.plugin_route import build_plugin_route_service

#: The S6 contract mandates its dedicated synthetic layer, and S6 is authoritative:
#: the plugin adapts to S6, never the reverse.
LAYER = S6_SYNTHETIC_LAYER
JOB_ID = "s7-6-full-chain"
TOL = 1e-6


def close(a: Any, b: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= TOL
    except (TypeError, ValueError):
        return False


def build_plan(document_token: str, *, radius: float = 200.0, job_id: str = JOB_ID) -> CadOperationPlan:
    """The canonical S7 acceptance plan: layer + line + circle + polyline."""
    return CadOperationPlan(
        job_id=job_id,
        document_token=document_token,
        batch_policy="all_or_nothing",
        operations=(
            CadOperation(f"{job_id}.layer", "ENSURE_LAYER",
                         parameters={"layer": LayerSpec(name=LAYER, color_index=4).to_dict()}),
            CadOperation(f"{job_id}.line", "CREATE_LINE", entity=EntitySpec(
                "line", {"start": {"x": 0, "y": 0}, "end": {"x": 600, "y": 300}}, layer=LAYER)),
            CadOperation(f"{job_id}.circle", "CREATE_CIRCLE", entity=EntitySpec(
                "circle", {"center": {"x": 1500, "y": 400}, "radius": radius}, layer=LAYER)),
            CadOperation(f"{job_id}.poly", "CREATE_POLYLINE", entity=EntitySpec(
                "polyline", {"vertices": [{"x": 0, "y": 900}, {"x": 400, "y": 900},
                                          {"x": 400, "y": 1200}], "closed": False}, layer=LAYER)),
        ),
    )


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT are required", file=sys.stderr)
        return 2

    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    checks: list[dict[str, Any]] = []

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)
    backend = AutoCadPluginBackend(client, job_id=JOB_ID)
    service = build_plugin_route_service(plugin_backend=backend, mock_available=True, com_available=False)

    # Record the binary identity of the plugin actually loaded, so evidence is tied to a
    # specific Host DLL rather than merely to "some build".
    import hashlib as _hashlib
    host_dll = (Path(__file__).resolve().parents[1] / "plugin" / "src" / "TianzhengCadPlugin"
                / "bin" / "Release" / "net8.0-windows" / "TianzhengCadPlugin.dll")
    binary_identity: dict[str, Any] = {}
    for name in ("TianzhengCadPlugin.dll", "TianzhengCadPlugin.Protocol.dll",
                 "TianzhengCadPlugin.Transport.dll"):
        candidate = host_dll.parent / name
        if candidate.is_file():
            binary_identity[name] = {
                "sha256": _hashlib.sha256(candidate.read_bytes()).hexdigest().upper(),
                "bytes": candidate.stat().st_size,
            }

    report: dict[str, Any] = {
        "acceptance": "s7_6_full_chain_mcp_to_autocad",
        "binary_identity": binary_identity,
        "path": "structured request -> S6 plan -> CapabilityRouter -> AutoCadPluginBackend "
                "-> PluginTransportClient -> AutoCAD plugin",
        "token_digest": redact_token(token),
        "job_id": JOB_ID,
        "layer": LAYER,
    }

    try:
        # ---- 1. capabilities via the backend (runtime handshake) ----
        capabilities = backend._ensure_connected()
        caps_entries = {c.operation: c.available for c in backend.get_capabilities()}
        checks.append({
            "name": "capabilities",
            "snapshot": capabilities.to_dict(),
            "s6_capability_map": caps_entries,
            "assertions": {
                "protocol_2_0_0": capabilities.protocol_version == "2.0.0",
                "readiness_true": capabilities.readiness is True,
                "readiness_state_available": capabilities.readiness_state == "AVAILABLE_SANDBOX_ENTITY_MVP",
                "transaction_support": capabilities.transaction_support is True,
                "batch_all_or_nothing": capabilities.batch_transaction_mode == "all_or_nothing",
                "persistence_support": capabilities.persistence_support is True,
                "idempotency_support_available": capabilities.idempotency_support.startswith("AVAILABLE"),
                "tianzheng_not_available": capabilities.tianzheng_support == "NOT_AVAILABLE",
                "s6_line_capability_available": caps_entries.get("CREATE_LINE") is True,
                "s6_save_capability_available": caps_entries.get("SAVE_SYNTHETIC_DOCUMENT") is True,
            },
        })

        # ---- 2. synthetic document via the backend ----
        session = backend.create_synthetic_document()
        binding = backend._binding(session.session_id)
        checks.append({
            "name": "synthetic_document",
            "document_id": session.opened_identity.document_id,
            "document_role": session.opened_identity.document_role.value,
            "assertions": {
                "session_created": bool(session.session_id),
                "document_open": session.document_open is True,
                "identity_is_not_a_user_path": session.opened_identity.document_full_path.startswith(
                    "plugin-synthetic://"),
                "token_not_exposed_in_identity": binding.document_token
                not in session.opened_identity.document_full_path,
            },
        })

        # ---- 3. routing decision (must choose the plugin) ----
        plan = build_plan(binding.document_token)
        decision = service.route(plan, require_atomic_batch=True)
        checks.append({
            "name": "routing",
            "decision": decision.to_dict(),
            "assertions": {
                "selected_plugin": decision.selected_backend == PLUGIN_BACKEND,
                "actual_backend_reported": decision.actual_backend_used == PLUGIN_BACKEND,
                "status_selected": decision.status == "selected",
            },
        })

        # ---- 4. execute through the MCP route service ----
        idempotency_key = f"{JOB_ID}-key-1"
        routed = service.execute(plan, session_id=session.session_id, idempotency_key=idempotency_key)
        execution = routed.execution
        checks.append({
            "name": "full_chain_batch",
            "status": routed.status,
            "actual_backend_used": routed.actual_backend_used,
            "execution": {k: execution.get(k) for k in (
                "status", "data")} if execution else {},
            "assertions": {
                "completed": routed.status == "completed",
                "backend_is_plugin": routed.actual_backend_used == PLUGIN_BACKEND,
                "transaction_committed": (execution.get("data") or {}).get("transaction_status") == "COMMITTED",
                "all_or_nothing": (execution.get("data") or {}).get("transaction_mode") == "all_or_nothing",
                "no_partial_commit": (execution.get("data") or {}).get("partial_commit_status") is False,
                "created_three": (execution.get("data") or {}).get("created_count") == 3,
                "three_handles": len((execution.get("data") or {}).get("handles") or []) == 3,
                "idempotency_applied": (execution.get("data") or {}).get("idempotency_status") == "APPLIED",
            },
        })

        # ---- 5. query before save ----
        before = backend.list_entities(session.session_id)
        checks.append({
            "name": "query_before_save",
            "entity_count": len(before),
            "assertions": {"three_entities": len(before) == 3},
        })

        # ---- 6. save -> close -> reopen ----
        save_result = backend.save_document(session.session_id)
        sandbox_identity = (save_result.data or {}).get("sandbox_identity", "")
        close_result = backend.close_document(session.session_id)
        reopened = backend.reopen_document(session.opened_identity)
        new_binding = backend._binding(reopened.session_id)

        checks.append({
            "name": "persistence_lifecycle",
            "sandbox_identity": sandbox_identity,
            "assertions": {
                "saved": (save_result.data or {}).get("save_status") == "SAVED",
                "sandbox_identity_is_bare_filename": "/" not in sandbox_identity and "\\" not in sandbox_identity,
                "closed": close_result.status == "COMPLETED",
                "reopened_session": bool(reopened.session_id),
                "new_token_issued": new_binding.document_token != binding.document_token,
                "old_session_invalidated": reopened.session_id != session.session_id,
            },
        })

        # ---- 7. query after reopen: entities must have persisted ----
        after = backend.list_entities(reopened.session_id)
        by_type: dict[str, list[dict[str, Any]]] = {}
        for entity in after:
            by_type.setdefault(entity.get("entity_type", ""), []).append(entity)
        line = (by_type.get("line") or [{}])[0].get("geometry") or {}
        circle = (by_type.get("circle") or [{}])[0].get("geometry") or {}
        poly = (by_type.get("polyline") or [{}])[0].get("geometry") or {}

        checks.append({
            "name": "query_after_reopen",
            "entity_count": len(after),
            "entities": after,
            "assertions": {
                "three_entities_persisted": len(after) == 3,
                "one_line": len(by_type.get("line") or []) == 1,
                "one_circle": len(by_type.get("circle") or []) == 1,
                "one_polyline": len(by_type.get("polyline") or []) == 1,
                "all_on_layer": all(e.get("layer") == LAYER for e in after),
                "line_geometry_persisted": close((line.get("end") or {}).get("x"), 600.0)
                and close((line.get("end") or {}).get("y"), 300.0),
                "circle_geometry_persisted": close(circle.get("radius"), 200.0)
                and close((circle.get("center") or {}).get("x"), 1500.0),
                "polyline_geometry_persisted": len(poly.get("vertices") or []) == 3,
                "handles_non_empty": all(e.get("handle") for e in after),
            },
        })

        # ---- 8. persistent idempotency: replay the SAME plan after reopen ----
        replay_plan = build_plan(new_binding.document_token)
        replay = service.execute(replay_plan, session_id=reopened.session_id,
                                 idempotency_key=idempotency_key)
        replay_data = (replay.execution or {}).get("data") or {}
        after_replay = backend.list_entities(reopened.session_id)

        checks.append({
            "name": "persistent_idempotency_replay",
            "idempotency_status": replay_data.get("idempotency_status"),
            "created_count": replay_data.get("created_count"),
            "entity_count_after_replay": len(after_replay),
            "assertions": {
                "already_applied": replay_data.get("idempotency_status") == "ALREADY_APPLIED",
                "created_nothing": replay_data.get("created_count") == 0,
                "entity_total_unchanged": len(after_replay) == 3,
            },
        })

        # ---- 9. idempotency conflict: same key, different payload ----
        conflict_plan = build_plan(new_binding.document_token, radius=999.0)
        conflict_error: str | None = None
        try:
            conflict = service.execute(conflict_plan, session_id=reopened.session_id,
                                       idempotency_key=idempotency_key)
            conflict_error = (conflict.execution or {}).get("error_code")
        except PluginBackendError as exc:
            conflict_error = exc.error_code
        after_conflict = backend.list_entities(reopened.session_id)

        checks.append({
            "name": "idempotency_conflict",
            "error_code": conflict_error,
            "entity_count_after_conflict": len(after_conflict),
            "assertions": {
                "conflict_reported": conflict_error == "IDEMPOTENCY_CONFLICT",
                "nothing_executed": len(after_conflict) == 3,
            },
        })

        # ---- 10. THE REAL MCP MAIN PATH: dispatch_tool -> plugin -> AutoCAD ----
        # Proves the plugin is reachable from the registered MCP dispatcher, not only from
        # a parallel service object.
        configure_plugin_route_service(service)
        import uuid as _uuid

        def _envelope(**extra):
            payload = {
                "schema_version": PROTOCOL_VERSION,
                "request_id": "mcp-" + _uuid.uuid4().hex[:10],
                "idempotency_key": "mcp-key-" + _uuid.uuid4().hex[:8],
            }
            payload.update(extra)
            return payload

        mcp_caps = dispatch_tool("cad.plugin.capabilities", _envelope())
        before_mcp = len(backend.list_entities(reopened.session_id))
        mcp_exec = dispatch_tool("cad.plugin.execute", _envelope(
            job_id=JOB_ID,
            session_id=reopened.session_id,
            layer=LAYER,
            entities=[{"type": "circle",
                       "geometry": {"center": {"x": 3000, "y": 3000}, "radius": 120}}],
            require_atomic_batch=True,
        ))
        after_mcp = backend.list_entities(reopened.session_id)
        mcp_data = mcp_exec.get("data") or {}

        checks.append({
            "name": "mcp_dispatch_tool_main_path",
            "capabilities_status": mcp_caps.get("status"),
            "execute_status": mcp_exec.get("status"),
            "backend_kind": mcp_exec.get("backend_kind"),
            "actual_backend_used": mcp_data.get("actual_backend_used"),
            "assertions": {
                "caps_tool_ok": mcp_caps.get("status") == "OK",
                "caps_reports_plugin_configured": bool(
                    (mcp_caps.get("data") or {}).get("capabilities", {}).get("plugin_backend_configured")),
                "execute_completed": mcp_exec.get("status") == "COMPLETED",
                "provenance_is_real_plugin": mcp_exec.get("backend_kind") == "REAL_PLUGIN",
                "actual_backend_is_plugin": mcp_data.get("actual_backend_used") == PLUGIN_BACKEND,
                "entity_created_via_mcp": len(after_mcp) == before_mcp + 1,
            },
        })

        # ---- 11. unsupported plan is refused before sending ----
        text_plan = CadOperationPlan(
            job_id=JOB_ID, document_token=new_binding.document_token,
            batch_policy="all_or_nothing",
            operations=(
                CadOperation(f"{JOB_ID}.t", "CREATE_TEXT", entity=EntitySpec(
                    "text", {"text": "no", "insertion_point": {"x": 0, "y": 0}, "height": 10},
                    layer=LAYER)),
            ))
        entities_before_unsupported = len(backend.list_entities(reopened.session_id))
        unsupported_decision = service.route(text_plan, require_atomic_batch=True)
        after_unsupported = backend.list_entities(reopened.session_id)
        checks.append({
            "name": "unsupported_plan_not_routed_to_plugin",
            "selected_backend": unsupported_decision.selected_backend,
            "entity_count": len(after_unsupported),
            "assertions": {
                "plugin_not_selected": unsupported_decision.selected_backend != PLUGIN_BACKEND,
                "nothing_created": len(after_unsupported) == entities_before_unsupported,
            },
        })

    finally:
        client.disconnect()

    report["checks"] = checks
    failures = [f"{c['name']}.{n}" for c in checks for n, ok in c.get("assertions", {}).items() if not ok]
    report["failed_assertions"] = failures
    report["all_assertions_passed"] = not failures

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

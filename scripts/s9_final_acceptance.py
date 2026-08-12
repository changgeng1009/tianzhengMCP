"""S9.7 final acceptance — an engineering task, closed loop, against real Tianzheng.

Entered from the TASK layer, never by calling cad.tianzheng.create_pipe directly:

    EngineeringTask -> Planner -> Dry Run -> Validate -> Approve
        -> Execute (through MCP cad.tianzheng.* tools)
            -> post-execution query -> Verify

Requires a live Tianzheng session started by TGStart.exe with the plugin NETLOADed, plus
TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.plugin_transport import (  # noqa: E402
    PluginTransportClient,
    PluginTransportConfig,
    redact_token,
)
from mcp_nextgen.control_server.dispatcher import (  # noqa: E402
    configure_engineering_route_service,
    configure_tianzheng_route_service,
    dispatch_tool,
)
from mcp_nextgen.protocol.version import PROTOCOL_VERSION  # noqa: E402
from mcp_nextgen.s8.tianzheng_backend import TianzhengBackend  # noqa: E402
from mcp_nextgen.s8.tianzheng_route import build_tianzheng_route_service  # noqa: E402
from mcp_nextgen.s9.contracts import ENGINEERING_TASK_PASS  # noqa: E402
from mcp_nextgen.s9.execution import (  # noqa: E402
    EngineeringResultVerifier,
    EngineeringTaskExecutor,
)
from mcp_nextgen.s9.planner import MockEngineeringPlanner, build_capability_snapshot  # noqa: E402
from mcp_nextgen.s9.route import build_engineering_route_service  # noqa: E402
from mcp_nextgen.s9.scenario import (  # noqa: E402
    ANCHOR_A,
    ANCHOR_B,
    McpEngineeringGateway,
    build_context,
    build_semantic_model,
    build_task,
)
from mcp_nextgen.s9.validation import EngineeringPlanValidator, dry_run  # noqa: E402


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s9_engineering_task_loop") / run_id
    out.mkdir(parents=True, exist_ok=True)

    job_id = f"s9-{uuid.uuid4().hex[:8]}"
    task_id = f"s9-task-{uuid.uuid4().hex[:8]}"
    sandbox_file = f"s9_{uuid.uuid4().hex[:8]}.dwg"

    def write(name: str, payload: Any) -> None:
        (out / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8")

    summary: dict[str, Any] = {
        "run_id": run_id, "task_id": task_id, "job_id": job_id,
        "sandbox_file": sandbox_file, "token_digest": redact_token(token),
        "entry_point": "EngineeringTask -> Planner -> Validate -> Approve -> Execute -> Verify",
        "stages": {}, "warnings": [],
    }

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)

    def plugin(op: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        response = client.call(op, mutating=mutating, job_id=job_id, **kwargs)
        if not response.get("success"):
            raise RuntimeError(f"{op}: {response.get('error_code')} "
                               f"{response.get('sanitized_message')}")
        return response.get("result") or {}

    try:
        # --- 1-3. the engineering task and its drawing context ---------------------------
        task = build_task(task_id)
        context = build_context()
        model = build_semantic_model(context)
        write("engineering_task.json", task.to_dict())
        write("drawing_context.json", context.to_dict())
        write("semantic_model.json", model.to_dict())
        print(f"task: {task.intent}")

        # --- real environment and capability snapshot ------------------------------------
        handshake = dict(client.connect().to_dict())
        if not handshake.get("tianzheng_loaded"):
            raise RuntimeError("tianzheng_loaded=false; aborting")

        backend = TianzhengBackend(client, job_id=job_id)
        tianzheng_route = build_tianzheng_route_service(backend, handshake=handshake)
        configure_tianzheng_route_service(tianzheng_route)
        capabilities = build_capability_snapshot(tianzheng_route.capability_snapshot())
        configure_engineering_route_service(
            build_engineering_route_service(MockEngineeringPlanner(), capabilities=capabilities))
        write("capability_validation.json",
              {"handshake": handshake, "capability_snapshot": capabilities})
        print(f"capabilities: pipe_create="
              f"{capabilities.get('tianzheng_native_pipe_create')} "
              f"valve={capabilities.get('tianzheng_valve')}")

        # --- 4-5. plan + dry run, through the MCP engineering tool ------------------------
        planned = dispatch_tool("cad.engineering.plan", {
            "schema_version": PROTOCOL_VERSION, "request_id": f"{job_id}-plan",
            "idempotency_key": task_id, "task_id": task_id,
            "start": list(ANCHOR_A), "end": list(ANCHOR_B)})
        write("engineering_plan.json", planned["data"]["plan"])
        write("dry_run_result.json", planned["data"]["dry_run"])
        if planned["data"]["plan"]["blocked"]:
            raise RuntimeError(f"plan blocked: {planned['data']['plan']['missing_capabilities']}")
        print(f"plan: {len(planned['data']['plan']['operations'])} operations, "
              f"dry run {planned['data']['dry_run']['validation']['status']}")

        # The executor needs the real objects, not their JSON shadow.
        plan = MockEngineeringPlanner().plan(task, context, model, capabilities)
        validation = EngineeringPlanValidator().validate(task, plan, model, capabilities, context)
        run = dry_run(task, plan, model, capabilities, context)
        if not validation.ok:
            raise RuntimeError(f"validation failed: {validation.errors}")

        # --- 6-7. approval ----------------------------------------------------------------
        approval = {
            "required": task.constraints.execution.require_approval,
            "approval_level": plan.approval_requirement,
            "granted": True,
            "granted_for_plan_hash": plan.plan_hash(),
            "sandbox_only": task.constraints.safety.sandbox_only,
            "production_write_allowed": False,
            "user_dwg_write_allowed": False,
            "note": "S9 uses the existing control-plane sandbox approval level; no second "
                    "approval system and no new privilege.",
        }
        write("approval_result.json", approval)

        # --- 8-12. execute through MCP ----------------------------------------------------
        document = plugin("create_synthetic_document", mutating=True, parameters={})
        document_token = document["document_token"]

        gateway = McpEngineeringGateway(
            dispatch_tool, plugin, job_id=job_id, schema_version=PROTOCOL_VERSION,
            sandbox_file=sandbox_file, backend=backend)
        execution = EngineeringTaskExecutor(gateway).execute(task, plan, document_token)
        write("execution_result.json", execution.to_dict())
        print(f"execution: {len(execution.succeeded_operations)}/{len(plan.operations)} "
              f"operations, handle={execution.primary_handle}, backend={execution.backend_used}")
        if execution.failed:
            raise RuntimeError("execution reported a failure")

        # --- 13. post-execution snapshot, re-queried from the drawing ----------------------
        snapshot = dict(backend.query_pipe(
            execution.document_token, execution.primary_handle or "",
            execution.related_handles))
        inventory = backend.inventory(execution.document_token)
        snapshot["pipe_count"] = inventory.get("pipe_count")
        snapshot["fitting_count"] = inventory.get("fitting_count")
        write("post_execution_snapshot.json", snapshot)
        print(f"post-execution: class={snapshot.get('runtime_class')} "
              f"pipes={snapshot['pipe_count']} fittings={snapshot['fitting_count']}")

        # --- 14-24. verification ----------------------------------------------------------
        verdict = EngineeringResultVerifier().verify(task, plan, execution, snapshot, model)
        write("engineering_verification_result.json", verdict.to_dict())
        replay = execution.outcome("op-5-replay")
        write("idempotency_result.json", replay.result if replay else {"error": "no replay"})
        print(f"verification: {verdict.status} "
              f"({len(verdict.checks) - len(verdict.failed_checks)}/{len(verdict.checks)} checks)")

        summary["stages"] = {
            "task": task.to_dict(),
            "plan_hash": plan.plan_hash(),
            "dry_run": run.to_dict(),
            "validation": validation.to_dict(),
            "approval": approval,
            "execution": execution.to_dict(),
            "post_execution_snapshot": snapshot,
            "verification": verdict.to_dict(),
        }
        summary["status"] = ("S9_ENGINEERING_TASK_CLOSED_LOOP_MVP_COMPLETE"
                             if verdict.status == ENGINEERING_TASK_PASS
                             else "S9_ENGINEERING_TASK_LOOP_PARTIAL")
    except Exception as exc:  # noqa: BLE001 - always leave evidence
        summary["status"] = "S9_ENGINEERING_TASK_LOOP_PARTIAL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {summary['error']}", file=sys.stderr)
    finally:
        configure_engineering_route_service(None)
        configure_tianzheng_route_service(None)
        client.disconnect()

    write("s9_execution_summary.json", summary)
    print(f"\nstatus: {summary['status']}\nevidence: {out}")
    return 0 if summary["status"] == "S9_ENGINEERING_TASK_CLOSED_LOOP_MVP_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

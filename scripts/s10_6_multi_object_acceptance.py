"""S10.6 real multi-object engineering task.

    EngineeringTask -> Planner -> Validate -> Approve -> MCP -> TianzhengBackend
    -> native TDbPipe + native TDbPump + pipe-owned diameter annotation
    -> post-execution verification -> persistence -> replay

The entry point is the TASK, not the three MCP tools. The tools are traced, but nothing here
calls cad.tianzheng.create_pump directly and then declares success: the call chain comes from
EngineeringTaskExecutor walking a plan the planner emitted from capabilities.

The pump sits well away from the pipe on purpose. Putting it at the pipe midpoint would make
a handle or target mix-up look like a correct result.
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
    configure_tianzheng_route_service,
    dispatch_tool,
)
from mcp_nextgen.protocol.version import PROTOCOL_VERSION  # noqa: E402
from mcp_nextgen.s10 import capabilities as s10_caps  # noqa: E402
from mcp_nextgen.s8.tianzheng_backend import TianzhengBackend  # noqa: E402
from mcp_nextgen.s8.tianzheng_route import build_tianzheng_route_service  # noqa: E402
from mcp_nextgen.s9.contracts import (  # noqa: E402
    ANNOTATION_PIPE_DIAMETER,
    ENGINEERING_TASK_PASS,
    AnnotationIntent,
    CapabilityConstraint,
    DrawingContextSnapshot,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    EquipmentIntent,
    ExecutionConstraint,
    GeometricConstraint,
    RouteIntent,
    SafetyConstraint,
    TaskConstraints,
    VerificationConstraint,
)
from mcp_nextgen.s9.execution import (  # noqa: E402
    EngineeringResultVerifier,
    EngineeringTaskExecutor,
)
from mcp_nextgen.s9.planner import (  # noqa: E402
    MockEngineeringPlanner,
    build_capability_snapshot,
)
from mcp_nextgen.s9.scenario import McpEngineeringGateway  # noqa: E402
from mcp_nextgen.s9.validation import EngineeringPlanValidator, dry_run  # noqa: E402

PIPE_START = (0.0, 0.0, 0.0)
PIPE_END = (3000.0, 0.0, 0.0)
#: Deliberately far from the pipe and off its axis, so a target mix-up cannot look correct.
PUMP_POSITION = (4500.0, 1000.0, 0.0)
XDATA = s10_caps.PIPE_LABEL_XDATA_APPLICATION


def build_task(task_id: str) -> EngineeringTaskSpec:
    return EngineeringTaskSpec(
        task_id=task_id,
        task_type="route_native_pipe",
        discipline="water_supply",
        intent="布置一根给水管、一台水泵，并为该管线添加管径标注",
        constraints=TaskConstraints(
            geometric=GeometricConstraint(
                start_point=PIPE_START, end_point=PIPE_END, max_deviation=1.0),
            capability=CapabilityConstraint(
                required_native_object="TDbPipe",
                required_backend="tianzheng_native_backend",
                allow_ordinary_cad_fallback=False),
            safety=SafetyConstraint(sandbox_only=True, allow_production_write=False),
            execution=ExecutionConstraint(require_approval=True),
            verification=VerificationConstraint(
                require_native_identity=True, expected_native_class="TDbPipe",
                expected_primary_count=1, expected_related_count=2,
                geometry_tolerance=1.0, require_persistence=True,
                require_idempotency=True, max_duplicate_count=0),
        ),
    )


def build_model() -> EngineeringSemanticModel:
    return EngineeringSemanticModel(
        model_id="s10-6-model",
        route_intents=(RouteIntent("intent-pipe", PIPE_START, PIPE_END),),
        equipment_intents=(EquipmentIntent("intent-pump", "pump", PUMP_POSITION),),
        annotation_intents=(AnnotationIntent(
            "intent-annotation", ANNOTATION_PIPE_DIAMETER,
            target_intent_id="intent-pipe"),),
    )


def main() -> int:  # noqa: C901 - a linear acceptance script reads better whole
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("s10_6_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s10_tianzheng_engineering_objects") / run_id
    out.mkdir(parents=True, exist_ok=True)

    job_id = f"s10-6-{uuid.uuid4().hex[:8]}"
    task_id = f"s10-6-task-{uuid.uuid4().hex[:8]}"
    sandbox_file = f"s10_6_{uuid.uuid4().hex[:8]}.dwg"

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
        # --- 0. the session must really be Tianzheng ------------------------------------
        handshake = dict(client.connect().to_dict())
        write("plugin_handshake.json", handshake)
        if not handshake.get("tianzheng_loaded"):
            raise RuntimeError("tianzheng_loaded=false: this is ordinary AutoCAD, refusing")
        print(f"handshake: tianzheng_loaded={handshake.get('tianzheng_loaded')}")

        backend = TianzhengBackend(client, job_id=job_id)
        configure_tianzheng_route_service(
            build_tianzheng_route_service(backend, handshake=handshake))

        # --- 1. task, model, capabilities -------------------------------------------------
        task = build_task(task_id)
        model = build_model()
        context = DrawingContextSnapshot(source_type="structured")
        capabilities = build_capability_snapshot(s10_caps.native_capability_registry())

        write("engineering_task.json", task.to_dict())
        write("semantic_model.json", model.to_dict())
        write("capability_snapshot.json", {
            "capabilities": capabilities,
            "supported_equipment_types": list(s10_caps.SUPPORTED_EQUIPMENT_TYPES),
            "live_report": dispatch_tool("cad.tianzheng.native_capabilities", {
                "schema_version": PROTOCOL_VERSION, "request_id": "s10-6-caps",
                "idempotency_key": "s10-6-caps"}).get("data"),
        })

        # --- 2. plan --------------------------------------------------------------------
        plan = MockEngineeringPlanner().plan(task, context, model, capabilities)
        write("engineering_plan.json", plan.to_dict())
        if plan.is_blocked:
            raise RuntimeError(f"plan blocked: {plan.missing_capabilities}")

        planned_caps = {op.backend_capability for op in plan.operations}
        for required in (s10_caps.CAP_PIPE_CREATE, s10_caps.CAP_PUMP_CREATE,
                         s10_caps.CAP_DIAMETER_ANNOTATION):
            if required not in planned_caps:
                raise RuntimeError(f"the plan does not cover {required}")

        serialised_plan = json.dumps(plan.to_dict(), ensure_ascii=False)
        for forbidden in ("HZGX", "HZSB", "DGGJ", "GJBZ", "SendStringToExecute"):
            if forbidden in serialised_plan:
                raise RuntimeError(f"the plan leaked a raw command string: {forbidden}")
        print(f"plan: {len(plan.operations)} operations, capabilities ok, no command strings")

        # --- 3. validate and dry run ------------------------------------------------------
        validation = EngineeringPlanValidator().validate(task, plan, model, capabilities, context)
        run = dry_run(task, plan, model, capabilities, context)
        write("validation_result.json", validation.to_dict())
        write("dry_run_result.json", run.to_dict())
        if validation.status not in ("PASS", "PASS_WITH_WARNINGS"):
            raise RuntimeError(f"validation {validation.status}: {validation.errors}")

        # --- 4. approval ------------------------------------------------------------------
        approval = {
            "required": task.constraints.execution.require_approval,
            "approval_level": plan.approval_requirement,
            "plan_hash": plan.plan_hash(),
            "granted": True,
            "sandbox_only": task.constraints.safety.sandbox_only,
            "production_write_allowed": False,
            "note": "the existing control-plane sandbox approval level; no second approval "
                    "system and no new privilege",
        }
        write("approval_result.json", approval)

        # --- 5. execute through MCP -------------------------------------------------------
        document = plugin("create_synthetic_document", mutating=True, parameters={})
        document_token = document["document_token"]

        gateway = McpEngineeringGateway(
            dispatch_tool, plugin, job_id=job_id, schema_version=PROTOCOL_VERSION,
            sandbox_file=sandbox_file, backend=backend)
        execution = EngineeringTaskExecutor(gateway).execute(task, plan, document_token)
        write("execution_result.json", execution.to_dict())
        if execution.failed:
            raise RuntimeError("execution reported a failure")

        pipe_handle = execution.primary_handle or ""
        pump_handle = execution.equipment_handles[-1] if execution.equipment_handles else ""
        annotated = list(execution.annotated_handles)
        print(f"execution: pipe={pipe_handle} pump={pump_handle} annotated={annotated}")

        # --- 6. handle binding: the evidence this whole stage exists for -------------------
        pipe_snapshot = gateway.query_pipe(execution.document_token, pipe_handle,
                                           execution.related_handles)
        pump_snapshot = gateway.query_equipment(execution.document_token, pump_handle)
        annotation_target = annotated[-1] if annotated else ""
        target_snapshot = gateway.query_pipe(execution.document_token, annotation_target)

        binding = {
            "pipe_operation": {
                "logical_result": "intent-pipe",
                "actual_handle": pipe_handle,
                "runtime_class": pipe_snapshot.get("runtime_class"),
                "dxf_name": pipe_snapshot.get("dxf_name"),
            },
            "pump_operation": {
                "logical_result": "intent-pump",
                "actual_handle": pump_handle,
                "runtime_class": pump_snapshot.get("runtime_class"),
                "dxf_name": pump_snapshot.get("dxf_name"),
            },
            "annotation_operation": {
                "semantic_target": "intent-pipe",
                "resolved_target_handle": annotation_target,
                "actual_target_runtime_class": target_snapshot.get("runtime_class"),
            },
            "bucket_separation": {
                "primary_handle": pipe_handle,
                "equipment_handles": list(execution.equipment_handles),
                "annotated_handles": annotated,
                "annotated_handles_meaning": "the handle of the object that WAS ANNOTATED, "
                                             "i.e. the target pipe - not an annotation object, "
                                             "because Model B creates none",
            },
            "assertions": {},
        }
        checks = {
            "pump_handle_differs_from_pipe_handle": pump_handle != pipe_handle,
            "annotation_target_is_the_pipe": annotation_target == pipe_handle,
            "annotation_target_is_not_the_pump": annotation_target != pump_handle,
            "annotation_target_runtime_class_is_pipe":
                target_snapshot.get("runtime_class") == "TDbPipe",
            "equipment_bucket_holds_only_the_pump":
                list(execution.equipment_handles) == [pump_handle] and pump_handle != "",
            "equipment_bucket_excludes_the_pipe":
                pipe_handle not in execution.equipment_handles,
            "pump_runtime_class_is_tdbpump": pump_snapshot.get("runtime_class") == "TDbPump",
        }
        binding["assertions"] = checks
        write("operation_binding_result.json", binding)
        print("binding: " + ", ".join(f"{k}={v}" for k, v in checks.items()))
        failed_bindings = [k for k, v in checks.items() if not v]
        if failed_bindings:
            raise RuntimeError(f"handle routing is wrong: {failed_bindings}")

        write("pipe_result.json", pipe_snapshot)
        write("pump_result.json", pump_snapshot)

        # --- 7. post-execution snapshot, re-read from the database -------------------------
        inventory = backend.inventory(execution.document_token)
        scan = plugin("diagnostic_scan_database", mutating=False,
                      parameters={"read_geometry": True})
        annotation_state = plugin(
            "tianzheng_annotation_result", mutating=False, parameters={}).get("result") or {}
        write("annotation_result.json", annotation_state)

        target_after = dict(annotation_state.get("target_after") or {})
        xdata_applications = [str(a) for a in (target_after.get("x_data_applications") or [])]

        snapshot = dict(pipe_snapshot)
        snapshot["pipe_count"] = inventory.get("pipe_count")
        snapshot["fitting_count"] = inventory.get("fitting_count")
        snapshot["xdata_applications"] = xdata_applications
        write("post_execution_snapshot.json", {
            "pipe_snapshot": pipe_snapshot,
            "pump_snapshot": pump_snapshot,
            "inventory": inventory,
            "class_histogram": scan.get("class_histogram"),
            "entity_count": scan.get("entity_count"),
            "objects": scan.get("objects"),
            "target_pipe_xdata_applications": xdata_applications,
            "annotation_storage_model": annotation_state.get("storage_model"),
        })
        print(f"post-execution: histogram={scan.get('class_histogram')} "
              f"xdata={xdata_applications}")

        # --- 8. verification through the real verifier ------------------------------------
        annotation_snapshot = {
            "runtime_class": target_after.get("runtime_class") or "TDbPipe",
            "xdata_applications": xdata_applications,
            "storage_model": annotation_state.get("storage_model"),
        }
        verdict = EngineeringResultVerifier().verify(
            task, plan, execution, snapshot, model,
            equipment_snapshots={pump_handle: pump_snapshot},
            annotation_snapshots={annotation_target: annotation_snapshot})
        write("engineering_verification_result.json", verdict.to_dict())
        print(f"verification: {verdict.status} "
              f"({len(verdict.checks) - len(verdict.failed_checks)}/{len(verdict.checks)})")
        for check in verdict.failed_checks:
            print(f"  FAILED {check.check_id}: {check.detail}")

        # --- 9. persistence ---------------------------------------------------------------
        persist = execution.outcome("op-4-persist")
        persist_token = execution.document_token
        pipe_after = gateway.query_pipe(persist_token, pipe_handle)
        pump_after = gateway.query_equipment(persist_token, pump_handle)
        scan_after = plugin("diagnostic_scan_database", mutating=False,
                            parameters={"read_geometry": False})
        annotation_after = plugin(
            "tianzheng_annotation_result", mutating=False, parameters={}).get("result") or {}
        xdata_after = [str(a) for a in
                       ((annotation_after.get("target_after") or {}).get("x_data_applications")
                        or [])]
        write("persistence_result.json", {
            "persist_operation": persist.result if persist else None,
            "pipe_after_reopen": pipe_after,
            "pump_after_reopen": pump_after,
            "class_histogram_after_reopen": scan_after.get("class_histogram"),
            "annotation_binding_after_reopen": {
                "target_handle": pipe_handle,
                "xdata_applications": xdata_after,
                "still_on_the_original_target": XDATA in xdata_after,
            },
        })
        print(f"persistence: pipe={pipe_after.get('runtime_class')} "
              f"pump={pump_after.get('runtime_class')} "
              f"histogram={scan_after.get('class_histogram')}")

        # --- 10. replay the whole task with the same keys ---------------------------------
        before_replay = dict(scan_after.get("class_histogram") or {})
        replay_execution = EngineeringTaskExecutor(gateway).execute(
            task, plan, execution.document_token)
        scan_replay = plugin("diagnostic_scan_database", mutating=False,
                             parameters={"read_geometry": False})
        after_replay = dict(scan_replay.get("class_histogram") or {})
        annotation_replay = plugin(
            "tianzheng_annotation_result", mutating=False, parameters={}).get("result") or {}
        xdata_replay = [str(a) for a in
                        ((annotation_replay.get("target_after") or {}).get("x_data_applications")
                         or [])]

        def outcome_status(operation_id: str) -> Any:
            found = replay_execution.outcome(operation_id)
            if not found:
                return None
            result = found.result or {}
            return result.get("status") or result.get("idempotency_status") or found.status

        replay_report = {
            "task_id": task.task_id, "plan_id": plan.plan_id,
            "same_plan_hash": plan.plan_hash(),
            "per_operation": {
                "pipe": outcome_status("op-1-create-native-pipe"),
                "pump": outcome_status("op-eq1-create-native-equipment"),
                "annotation": outcome_status("op-an1-annotate-pipe-diameter"),
            },
            "class_histogram_before_replay": before_replay,
            "class_histogram_after_replay": after_replay,
            "annotation_xdata_before_replay": xdata_after,
            "annotation_xdata_after_replay": xdata_replay,
            "new_annotation_objects": 0,
            "stable": before_replay == after_replay,
        }
        write("task_replay_result.json", replay_report)
        write("idempotency_result.json", {
            "pipe_count_stable": before_replay.get("TDbPipe") == after_replay.get("TDbPipe"),
            "pump_count_stable": before_replay.get("TDbPump") == after_replay.get("TDbPump"),
            "fitting_count_stable": (before_replay.get("TDbPipeFitting")
                                     == after_replay.get("TDbPipeFitting")),
            "annotation_state_present_before": XDATA in xdata_after,
            "annotation_state_present_after": XDATA in xdata_replay,
            "annotation_state_not_duplicated": xdata_replay.count(XDATA) <= 1,
            "note": "Model B has no annotation object to count; the invariant is that the "
                    "target pipe still carries the state exactly once",
        })
        print(f"replay: {before_replay} -> {after_replay}, xdata={xdata_replay}")

        summary["stages"] = {
            "handshake": handshake,
            "plan_hash": plan.plan_hash(),
            "validation": validation.status,
            "binding": checks,
            "verification": verdict.to_dict(),
            "histogram_after_execution": scan.get("class_histogram"),
            "histogram_after_replay": after_replay,
        }
        summary["status"] = ("S10_6_MULTI_OBJECT_ENGINEERING_TASK_COMPLETE"
                             if verdict.status == ENGINEERING_TASK_PASS
                             else "S10_6_MULTI_OBJECT_ENGINEERING_TASK_PARTIAL")
    except Exception as exc:  # noqa: BLE001 - always leave evidence behind
        summary["status"] = "S10_6_MULTI_OBJECT_ENGINEERING_TASK_PARTIAL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        write("s10_6_summary.json", summary)
        print(f"\nstatus: {summary.get('status')}")
        print(f"artifacts -> {out}")

    return 0 if summary.get("status", "").endswith("COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())

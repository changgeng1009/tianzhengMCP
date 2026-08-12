"""MCP route for the S9 engineering task layer.

Planning and validation are pure — they touch no CAD — so they are exposed as MCP tools.
Execution deliberately is NOT a tool: the executor is a *client* of the existing
``cad.tianzheng.*`` tools, and making it a tool too would mean the dispatcher re-entering
itself. Verification is likewise pure and exposed.

The tools accept a task descriptor, never free text and never an operation list, so an MCP
caller cannot hand-craft operations that bypass the planner's capability gate.
"""
from __future__ import annotations

from typing import Any, Mapping

from mcp_nextgen.s9.contracts import (
    CapabilityConstraint,
    EngineeringContractError,
    EngineeringTaskSpec,
    GeometricConstraint,
    TaskConstraints,
    VerificationConstraint,
    make_point,
)
from mcp_nextgen.s9.planner import MockEngineeringPlanner, build_capability_snapshot
from mcp_nextgen.s9.scenario import build_context, build_semantic_model, build_task
from mcp_nextgen.s9.validation import EngineeringPlanValidator, dry_run

ENGINEERING_BACKEND = "s9_engineering_planner"


class EngineeringRouteError(RuntimeError):
    def __init__(self, error_code: str, message: str, *,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.details = dict(details or {})


def _task_from_payload(payload: Mapping[str, Any]) -> EngineeringTaskSpec:
    """Build a task from the structured descriptor an MCP caller may send.

    The caller may choose the endpoints and the task id. Everything safety-relevant —
    sandbox-only, required native object, verification expectations — comes from the S9
    scenario contract, not from the caller.
    """
    base = build_task(str(payload.get("task_id") or "s9-mcp-task"))
    start = payload.get("start")
    end = payload.get("end")
    if start is None and end is None:
        return base

    try:
        geometric = GeometricConstraint(
            start_point=make_point(start) if start is not None
            else base.constraints.geometric.start_point,
            end_point=make_point(end) if end is not None
            else base.constraints.geometric.end_point,
            allowed_region=base.constraints.geometric.allowed_region,
            forbidden_regions=base.constraints.geometric.forbidden_regions,
            max_deviation=base.constraints.geometric.max_deviation,
        )
    except (ValueError, TypeError) as exc:
        raise EngineeringRouteError("ENGINEERING_TASK_INVALID", str(exc)) from exc

    return EngineeringTaskSpec(
        task_id=base.task_id, task_type=base.task_type, discipline=base.discipline,
        intent=str(payload.get("intent") or base.intent),
        source_context={"position": list(geometric.start_point or ())},
        target_context={"position": list(geometric.end_point or ())},
        constraints=TaskConstraints(
            geometric=geometric,
            capability=base.constraints.capability,
            safety=base.constraints.safety,
            execution=base.constraints.execution,
            verification=base.constraints.verification),
        required_capabilities=base.required_capabilities,
        expected_outputs=base.expected_outputs,
        verification_requirements=base.verification_requirements,
        approval_level=base.approval_level,
        metadata={"source": "mcp"},
    )


class S9EngineeringRouteService:
    """MCP-facing planning and validation for engineering tasks."""

    def __init__(self, planner=None, *, capabilities: Mapping[str, str] | None = None) -> None:
        self._planner = planner or MockEngineeringPlanner()
        self._capabilities = dict(capabilities or {})
        self._validator = EngineeringPlanValidator()

    def set_capabilities(self, capabilities: Mapping[str, Any]) -> None:
        self._capabilities = build_capability_snapshot(capabilities)

    @property
    def capabilities(self) -> dict[str, str]:
        return dict(self._capabilities)

    def plan_task(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Task -> plan, with a dry run attached. No CAD work happens here."""
        try:
            task = _task_from_payload(payload)
        except EngineeringContractError as exc:
            raise EngineeringRouteError("ENGINEERING_TASK_INVALID", str(exc)) from exc

        context = build_context()
        # The model must describe the route that was actually asked for, otherwise the
        # validator compares the caller's endpoints against the fixture's.
        model = build_semantic_model(
            context,
            include_valve_intent=bool(payload.get("include_valve_intent")),
            start=task.constraints.geometric.start_point,
            end=task.constraints.geometric.end_point)
        plan = self._planner.plan(task, context, model, self._capabilities)
        result = dry_run(task, plan, model, self._capabilities, context)

        return {
            "task": task.to_dict(),
            "drawing_context": context.to_dict(),
            "semantic_model": model.to_dict(),
            "plan": plan.to_dict(),
            "dry_run": result.to_dict(),
            "planner": type(self._planner).__name__,
            "actual_backend_used": ENGINEERING_BACKEND,
        }

    def validate_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Re-validate a plan the caller already holds, without executing it."""
        planned = self.plan_task(payload)
        validation = planned["dry_run"]["validation"]
        return {
            "validation": validation,
            "blocked": planned["plan"]["blocked"],
            "missing_capabilities": planned["plan"]["missing_capabilities"],
            "actual_backend_used": ENGINEERING_BACKEND,
        }


def build_engineering_route_service(
    planner=None, *, capabilities: Mapping[str, Any] | None = None
) -> S9EngineeringRouteService:
    service = S9EngineeringRouteService(planner)
    if capabilities:
        service.set_capabilities(capabilities)
    return service

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Callable

from mcp.adapter_t30 import T30WritebackAdapter
from mcp.executor import RepairPlanExecutor
from mcp.probe import probe_t30_capabilities as _probe_t30_capabilities
from mcp.session import MCPSession
from mcp.state import STAGE_ORDER


StageHandler = Callable[[MCPSession], dict[str, Any]]


class PipelineEngine:
    def __init__(
        self,
        adapter: T30WritebackAdapter | None = None,
        stage_overrides: dict[str, StageHandler] | None = None,
    ) -> None:
        self.sessions: dict[str, MCPSession] = {}
        self.adapter = adapter or T30WritebackAdapter(real_com_mode=False)
        self.executor = RepairPlanExecutor(adapter=self.adapter)
        self.stage_overrides = stage_overrides or {}

    def create_session(self, dwg_path: str, png_path: str) -> MCPSession:
        session = MCPSession(dwg_path=dwg_path, png_path=png_path)
        session.cad_connection = {
            "mode": "pipeline_session",
            "real_com_mode": self.adapter.real_com_mode,
            "capabilities": dict(self.adapter.capabilities),
        }
        self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> MCPSession:
        return deepcopy(self._require_session(session_id))

    def _require_session(self, session_id: str) -> MCPSession:
        if session_id not in self.sessions:
            raise KeyError(f"session not found: {session_id}")
        return self.sessions[session_id]

    def run(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        start_index = session.pipeline_state.next_stage_index()
        if start_index >= len(STAGE_ORDER):
            return self._envelope(
                session,
                STAGE_ORDER[-1],
                "success",
                {"session": session.to_dict()},
            )

        for stage in STAGE_ORDER[start_index:]:
            try:
                data = self._handler(stage)(session)
                self._apply_stage_data(session, stage, data)
                session.pipeline_state.record_success(stage, data)
            except Exception as exc:
                session.pipeline_state.record_failure(stage, str(exc))
                return self._envelope(session, stage, "failed", {}, str(exc))

        return self._envelope(
            session,
            STAGE_ORDER[-1],
            "success",
            {"report": session.repair_plan.get("report", {})},
        )

    def retry(self, session_id: str) -> dict[str, Any]:
        return self.run(session_id)

    def _handler(self, stage: str) -> StageHandler:
        if stage in self.stage_overrides:
            return self.stage_overrides[stage]
        handlers: dict[str, StageHandler] = {
            "load_dwg": self._load_dwg,
            "load_png": self._load_png,
            "build_semantic_graph": self._build_semantic_graph,
            "align_buildings": self._align_buildings,
            "detect_missing_elements": self._detect_missing_elements,
            "generate_repair_plan": self._generate_repair_plan,
            "validate_repair_plan": self._validate_repair_plan,
            "apply_to_cad": self._apply_to_cad,
            "generate_report": self._generate_report,
        }
        return handlers[stage]

    def _apply_stage_data(
        self,
        session: MCPSession,
        stage: str,
        data: dict[str, Any],
    ) -> None:
        if stage == "load_dwg":
            session.dwg_graph = data
        elif stage == "load_png":
            session.png_graph = data
        elif stage == "build_semantic_graph":
            session.dwg_graph = data.get("dwg_graph", session.dwg_graph)
            session.png_graph = data.get("png_graph", session.png_graph)
        elif stage == "align_buildings":
            session.alignment_map = data
        elif stage == "detect_missing_elements":
            session.missing_result = data
        elif stage == "generate_repair_plan":
            session.repair_plan = data
        elif stage == "validate_repair_plan":
            session.repair_plan["validation"] = data
        elif stage == "apply_to_cad":
            session.applied_actions = data.get("applied_actions", [])
        elif stage == "generate_report":
            session.repair_plan["report"] = data

    def _load_dwg(self, session: MCPSession) -> dict[str, Any]:
        return {
            "source": {"kind": "dwg", "path": session.dwg_path},
            "nodes": [],
            "edges": [],
            "systems": [],
            "buildings": [{"id": "dwg_bldg_01", "label": "A栋"}],
        }

    def _load_png(self, session: MCPSession) -> dict[str, Any]:
        return {
            "source": {"kind": "png", "path": session.png_path},
            "nodes": [
                {
                    "id": "png_node_001",
                    "node_type": "endpoint",
                    "position": [0.0, 0.0, 0.0],
                },
                {
                    "id": "png_node_002",
                    "node_type": "endpoint",
                    "position": [1000.0, 0.0, 0.0],
                },
            ],
            "edges": [
                {
                    "id": "png_edge_001",
                    "semantic_type": "pipe",
                    "start_node_id": "png_node_001",
                    "end_node_id": "png_node_002",
                    "diameter": "DN50",
                    "system_type": "给水",
                    "layer": "PIPE-给水",
                    "geometry": {
                        "start_point": [0.0, 0.0, 0.0],
                        "end_point": [1000.0, 0.0, 0.0],
                    },
                }
            ],
            "systems": [{"system_type": "给水", "edge_count": 1}],
            "buildings": [{"id": "png_bldg_a", "label": "A栋"}],
        }

    def _build_semantic_graph(self, session: MCPSession) -> dict[str, Any]:
        return {
            "dwg_graph": _ensure_graph(session.dwg_graph),
            "png_graph": _ensure_graph(session.png_graph),
        }

    def _align_buildings(self, session: MCPSession) -> dict[str, Any]:
        mapping: list[dict[str, Any]] = []
        dwg_buildings = session.dwg_graph.get("buildings", [])
        png_buildings = session.png_graph.get("buildings", [])
        for reference in png_buildings:
            match = _match_building(reference, dwg_buildings)
            if match is None:
                continue
            confidence = 0.92 if reference.get("label") == match.get("label") else 0.75
            mapping.append(
                {
                    "reference_building": reference.get("label") or reference.get("id"),
                    "dwg_building": match.get("id") or match.get("label"),
                    "confidence": confidence,
                    "method": "label_topology_fallback",
                }
            )
        return {"mapping": mapping}

    def _detect_missing_elements(self, session: MCPSession) -> dict[str, Any]:
        dwg_pipe_signatures = {
            _edge_signature(edge)
            for edge in session.dwg_graph.get("edges", [])
            if edge.get("semantic_type") == "pipe"
        }
        png_pipe_edges = [
            edge for edge in session.png_graph.get("edges", []) if edge.get("semantic_type") == "pipe"
        ]
        missing_pipes = [
            {
                "reference_edge_id": edge.get("id"),
                "reference_edge": edge,
                "reason": "png_reference_pipe_missing_in_dwg",
            }
            for edge in png_pipe_edges
            if _edge_signature(edge) not in dwg_pipe_signatures
        ]
        return {
            "missing_pipes": missing_pipes,
            "missing_sprinklers": [],
            "missing_valves": [],
            "extra_elements": [],
            "mismatch": [],
        }

    def _generate_repair_plan(self, session: MCPSession) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for index, missing in enumerate(session.missing_result.get("missing_pipes", []), start=1):
            edge = missing["reference_edge"]
            geometry = edge.get("geometry", {})
            actions.append(
                {
                    "action_id": f"repair_pipe_{index:03d}",
                    "type": "add_pipe",
                    "start_node": edge.get("start_node_id"),
                    "end_node": edge.get("end_node_id"),
                    "start": geometry.get("start_point", [0.0, 0.0, 0.0]),
                    "end": geometry.get("end_point", [0.0, 0.0, 0.0]),
                    "dn": _dn_to_int(edge.get("diameter")),
                    "layer": edge.get("layer") or "0",
                    "system_type": edge.get("system_type"),
                    "reference_edge_id": edge.get("id"),
                    "requires_commit": True,
                }
            )
        return {
            "plan_id": f"repair_plan_{session.session_id}",
            "actions": actions,
            "status": "generated",
        }

    def _validate_repair_plan(self, session: MCPSession) -> dict[str, Any]:
        return self.executor.validate(session)

    def _apply_to_cad(self, session: MCPSession) -> dict[str, Any]:
        return self.executor.apply(session)

    def _generate_report(self, session: MCPSession) -> dict[str, Any]:
        total_issues = sum(
            len(session.missing_result.get(key, []))
            for key in (
                "missing_pipes",
                "missing_sprinklers",
                "missing_valves",
                "extra_elements",
                "mismatch",
            )
        )
        auto_fixed = sum(1 for item in session.applied_actions if item.get("status") == "committed")
        remaining = max(total_issues - auto_fixed, 0)
        risk_level = "low" if remaining == 0 else "medium"
        return {
            "summary": {
                "total_issues": total_issues,
                "auto_fixed": auto_fixed,
                "remaining": remaining,
            },
            "risk_level": risk_level,
            "changes": list(session.applied_actions),
        }

    def _envelope(
        self,
        session: MCPSession,
        stage: str,
        status: str,
        data: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "stage": stage,
            "status": status,
            "data": data,
            "error": error,
            "action_log": list(session.pipeline_state.action_log),
        }


default_pipeline_engine = PipelineEngine()


def create_pipeline_session(dwg_path: str, png_path: str) -> dict[str, Any]:
    session = default_pipeline_engine.create_session(dwg_path, png_path)
    return {
        "session_id": session.session_id,
        "stage": "create_session",
        "status": "success",
        "data": {"session": session.to_dict()},
        "error": None,
        "action_log": [],
    }


def run_pipeline(session_id: str) -> dict[str, Any]:
    return default_pipeline_engine.run(session_id)


def retry_pipeline_stage(session_id: str) -> dict[str, Any]:
    return default_pipeline_engine.retry(session_id)


def get_pipeline_session(session_id: str) -> dict[str, Any]:
    session = default_pipeline_engine.get_session(session_id)
    return {
        "session_id": session.session_id,
        "stage": "get_pipeline_session",
        "status": "success",
        "data": {"session": session.to_dict()},
        "error": None,
        "action_log": list(session.pipeline_state.action_log),
    }


def probe_t30_capabilities() -> dict[str, Any]:
    capabilities = _probe_t30_capabilities()
    return {
        "session_id": "",
        "stage": "probe_t30_capabilities",
        "status": "success",
        "data": capabilities,
        "error": None,
        "action_log": [],
    }


def _ensure_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": graph.get("source", {}),
        "nodes": list(graph.get("nodes", [])),
        "edges": list(graph.get("edges", [])),
        "systems": list(graph.get("systems", [])),
        "buildings": list(graph.get("buildings", [])),
    }


def _match_building(
    reference: dict[str, Any],
    dwg_buildings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for building in dwg_buildings:
        if reference.get("label") and reference.get("label") == building.get("label"):
            return building
    return dwg_buildings[0] if dwg_buildings else None


def _edge_signature(edge: dict[str, Any]) -> tuple[Any, ...]:
    return (
        edge.get("semantic_type"),
        edge.get("diameter"),
        edge.get("system_type"),
        tuple(edge.get("geometry", {}).get("start_point", [])),
        tuple(edge.get("geometry", {}).get("end_point", [])),
    )


def _dn_to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        raise ValueError(f"invalid DN value: {value}")
    return int(match.group(1))

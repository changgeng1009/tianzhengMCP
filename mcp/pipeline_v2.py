from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from mcp.alignment_v2 import BuildingAlignmentV2, StructuralFingerprintBuilder
from mcp.diff_v2 import SemanticDiffV2
from mcp.diagnostics.input_graph import input_readiness_status
from mcp.repair_v2 import ConfidenceAwareRepairEngine, RepairPlanOptimizer
from mcp.repair_actions.action_builder import build_repair_actions
from mcp.repair_actions.action_builder import build_review_only_repair_actions
from mcp.repair_actions.action_optimizer import optimize_repair_plan_v2
from mcp.repair_actions.conflict_checker import check_repair_action_conflicts
from mcp.repair_actions.dry_run import dry_run_repair_plan
from mcp.repair_actions.missing_detector import detect_coordinate_missing
from mcp.repair_actions.report import generate_repair_action_report
from mcp.repair_actions.snapper import snap_repair_actions_to_target_graph
from mcp.session import MCPSession
from mcp.source_loader import MultiSourceSemanticLoader
from mcp.spatial.spatial_alignment import align_reference_graph_to_target
from mcp.t30_writeback.real_adapter import RealT30WritebackAdapter
from mcp.writeback_v2 import SafeT30WritebackV2


STAGE_ORDER_V2 = [
    "build_multi_source_graph",
    "compute_structural_fingerprint",
    "align_buildings_v2",
    "semantic_diff_v2",
    "optimize_repair_plan",
    "confidence_filter",
    "safe_apply_to_cad_v2",
    "generate_report_v2",
]

STAGE_ORDER_V2_WITH_SPATIAL = [
    "build_multi_source_graph",
    "compute_structural_fingerprint",
    "align_buildings_v2",
    "align_reference_to_target_coordinates",
    "semantic_diff_v2",
    "optimize_repair_plan",
    "confidence_filter",
    "safe_apply_to_cad_v2",
    "generate_report_v2",
]

STAGE_ORDER_V2_WITH_COORDINATE_REPAIR = [
    "build_multi_source_graph",
    "compute_structural_fingerprint",
    "align_buildings_v2",
    "generate_coordinate_repair_actions",
    "semantic_diff_v2",
    "optimize_repair_plan",
    "confidence_filter",
    "safe_apply_to_cad_v2",
    "generate_report_v2",
]

STAGE_ORDER_V2_WITH_SPATIAL_AND_COORDINATE_REPAIR = [
    "build_multi_source_graph",
    "compute_structural_fingerprint",
    "align_buildings_v2",
    "align_reference_to_target_coordinates",
    "generate_coordinate_repair_actions",
    "semantic_diff_v2",
    "optimize_repair_plan",
    "confidence_filter",
    "safe_apply_to_cad_v2",
    "generate_report_v2",
]


def _with_t30_writeback(stage_order: list[str]) -> list[str]:
    order = list(stage_order)
    if "apply_t30_writeback_v2" not in order:
        insert_at = order.index("generate_report_v2") if "generate_report_v2" in order else len(order)
        order.insert(insert_at, "apply_t30_writeback_v2")
    return order


@dataclass
class Phase8PipelineState:
    current_stage: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None
    checkpoint_index: int = 0
    action_log: list[dict[str, Any]] = field(default_factory=list)
    stage_order: list[str] = field(default_factory=lambda: list(STAGE_ORDER_V2))

    def next_stage_index(self) -> int:
        if self.failed_stage:
            return self.stage_order.index(self.failed_stage)
        return self.checkpoint_index

    def record_success(self, stage: str, data: dict[str, Any], confidence: float) -> None:
        self.current_stage = stage
        self.failed_stage = None
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.checkpoint_index = max(self.checkpoint_index, self.stage_order.index(stage) + 1)
        self.action_log.append(
            {
                "stage": stage,
                "status": "success",
                "confidence": confidence,
                "data_keys": sorted(data.keys()),
            }
        )

    def record_failure(self, stage: str, error: str) -> None:
        self.current_stage = stage
        self.failed_stage = stage
        self.action_log.append({"stage": stage, "status": "failed", "error": error})

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "failed_stage": self.failed_stage,
            "checkpoint_index": self.checkpoint_index,
            "action_log": list(self.action_log),
            "stage_order": list(self.stage_order),
        }


class Phase8PipelineEngine:
    def __init__(
        self,
        loader: MultiSourceSemanticLoader | None = None,
        writeback: SafeT30WritebackV2 | None = None,
        enable_spatial_alignment: bool = False,
        enable_coordinate_repair_actions: bool = False,
        enable_t30_real_writeback: bool = False,
        t30_writeback_adapter: RealT30WritebackAdapter | None = None,
        t30_writeback_options: dict[str, Any] | None = None,
    ) -> None:
        self.sessions: dict[str, MCPSession] = {}
        self.loader = loader or MultiSourceSemanticLoader()
        self.fingerprint_builder = StructuralFingerprintBuilder()
        self.aligner = BuildingAlignmentV2(self.fingerprint_builder)
        self.diff_engine = SemanticDiffV2()
        self.repair_engine = ConfidenceAwareRepairEngine()
        self.optimizer = RepairPlanOptimizer()
        self.writeback = writeback or SafeT30WritebackV2()
        self.t30_writeback_adapter = t30_writeback_adapter or RealT30WritebackAdapter(real_com_mode=False)
        self.t30_writeback_options = dict(t30_writeback_options or {"dry_run_only": True})
        self.enable_spatial_alignment = enable_spatial_alignment
        self.enable_coordinate_repair_actions = enable_coordinate_repair_actions
        self.enable_t30_real_writeback = enable_t30_real_writeback

    def create_session(self, sources: list[dict[str, Any]]) -> MCPSession:
        session = MCPSession(session_id=f"phase8_{uuid4().hex}")
        session.pipeline_state = Phase8PipelineState(
            stage_order=self._stage_order()
        )
        session.cad_connection = {"mode": "phase8_pipeline"}
        session.phase8_sources = deepcopy(sources)  # type: ignore[attr-defined]
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
        warnings: list[str] = []
        start_index = session.pipeline_state.next_stage_index()
        for stage in session.pipeline_state.stage_order[start_index:]:
            try:
                data, confidence, stage_warnings = self._run_stage(session, stage)
                warnings.extend(stage_warnings)
                self._apply_stage_data(session, stage, data)
                session.pipeline_state.record_success(stage, data, confidence)
            except Exception as exc:
                session.pipeline_state.record_failure(stage, str(exc))
                return self._envelope(session, stage, "failed", {}, 0.0, [str(exc)])

        report = session.repair_plan.get("report", {})
        return self._envelope(
            session,
            "generate_report_v2",
            "success",
            {"report": report},
            _report_confidence(report),
            warnings,
        )

    def _run_stage(self, session: MCPSession, stage: str) -> tuple[dict[str, Any], float, list[str]]:
        if stage == "build_multi_source_graph":
            return self._build_multi_source_graph(session)
        if stage == "compute_structural_fingerprint":
            return self._compute_structural_fingerprint(session)
        if stage == "align_buildings_v2":
            return self._align_buildings_v2(session)
        if stage == "semantic_diff_v2":
            return self._semantic_diff_v2(session)
        if stage == "align_reference_to_target_coordinates":
            return self._align_reference_to_target_coordinates(session)
        if stage == "generate_coordinate_repair_actions":
            return self._generate_coordinate_repair_actions(session)
        if stage == "optimize_repair_plan":
            return self._optimize_repair_plan(session)
        if stage == "confidence_filter":
            return self._confidence_filter(session)
        if stage == "safe_apply_to_cad_v2":
            return self._safe_apply_to_cad_v2(session)
        if stage == "apply_t30_writeback_v2":
            return self._apply_t30_writeback_v2(session)
        if stage == "generate_report_v2":
            return self._generate_report_v2(session)
        raise ValueError(f"unsupported phase8 stage: {stage}")

    def _apply_stage_data(self, session: MCPSession, stage: str, data: dict[str, Any]) -> None:
        if stage == "build_multi_source_graph":
            session.phase8_reference_graph = data["reference_graph"]  # type: ignore[attr-defined]
            session.phase8_target_graph = data["target_graph"]  # type: ignore[attr-defined]
            session.phase8_multi_source_graph = data["semantic_graph"]  # type: ignore[attr-defined]
            session.phase16_2_input_diagnostics = data.get("input_diagnostics", {})  # type: ignore[attr-defined]
        elif stage == "compute_structural_fingerprint":
            session.phase8_fingerprints = data  # type: ignore[attr-defined]
        elif stage == "align_buildings_v2":
            session.alignment_map = data
        elif stage == "align_reference_to_target_coordinates":
            session.phase11_spatial_alignment = data  # type: ignore[attr-defined]
            if data.get("aligned_reference_graph"):
                session.phase8_reference_graph = data["aligned_reference_graph"]  # type: ignore[attr-defined]
            if data.get("errors"):
                session.phase11_spatial_failed = True  # type: ignore[attr-defined]
        elif stage == "generate_coordinate_repair_actions":
            session.phase12_repair_plan_v2 = data["repair_plan_v2"]  # type: ignore[attr-defined]
            session.phase12_dry_run = data["dry_run"]  # type: ignore[attr-defined]
            session.phase12_report = data["report"]  # type: ignore[attr-defined]
        elif stage == "semantic_diff_v2":
            session.missing_result = data
        elif stage in {"optimize_repair_plan", "confidence_filter"}:
            session.repair_plan = data
        elif stage == "safe_apply_to_cad_v2":
            session.applied_actions = data.get("committed_actions", [])
            session.phase8_writeback_result = data  # type: ignore[attr-defined]
        elif stage == "apply_t30_writeback_v2":
            session.phase13_t30_writeback_result = data  # type: ignore[attr-defined]
        elif stage == "generate_report_v2":
            session.repair_plan["report"] = data

    def _build_multi_source_graph(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        sources = getattr(session, "phase8_sources")
        loaded = self.loader.load_sources(sources)
        reference_loaded = self.loader.load_sources([source for source in sources if source.get("role") != "target"])
        target_loaded = self.loader.load_sources([source for source in sources if source.get("role") == "target"])
        reference_graph = reference_loaded["semantic_graph"]
        target_graph = target_loaded["semantic_graph"]
        target_diag = target_loaded.get("target_graph_diagnostics", {})
        reference_diag = reference_loaded.get("reference_graph_diagnostics", {})
        manual_anchor_pairs = getattr(session, "phase11_manual_anchor_pairs", None)
        scope = _first_scope(sources)
        readiness = input_readiness_status(
            target_graph,
            reference_graph,
            scope_enabled=bool((scope or {}).get("enabled")),
            manual_anchor_pairs=manual_anchor_pairs,
        )
        data = {
            "semantic_graph": loaded["semantic_graph"],
            "reference_graph": reference_graph,
            "target_graph": target_graph,
            "source_types": loaded["source_types"],
            "input_diagnostics": {
                "target_graph_diagnostics": target_diag,
                "reference_graph_diagnostics": reference_diag,
                "target_graph_empty_reason": target_diag.get("empty_reason", ""),
                "reference_graph_empty_reason": reference_diag.get("empty_reason", ""),
                "input_readiness_status": readiness,
                "readiness_status": readiness,
                "scope_summary": {
                    "enabled": bool((scope or {}).get("enabled")),
                    "target": target_diag.get("scope_summary", {}),
                    "reference": reference_diag.get("scope_summary", {}),
                },
                "manual_anchor_summary": {
                    "used_manual_anchors": bool(manual_anchor_pairs),
                    "manual_anchor_count": len(manual_anchor_pairs or []),
                },
                "pdf_line_candidate_summary": reference_diag.get("pdf_line_candidate_summary", {}),
                "dwg_primitive_graph_summary": {
                    "loader_strategy": target_diag.get("loader_strategy"),
                    "graph_nodes": target_diag.get("graph_nodes", 0),
                    "graph_edges": target_diag.get("graph_edges", 0),
                    "primitive_object_count": target_diag.get("primitive_object_count", 0),
                },
            },
        }
        warnings = list(loaded["warnings"])
        warnings.extend(reference_loaded.get("warnings", []))
        warnings.extend(target_loaded.get("warnings", []))
        return data, float(loaded["confidence"]), list(dict.fromkeys(warnings))

    def _stage_order(self) -> list[str]:
        if self.enable_spatial_alignment and self.enable_coordinate_repair_actions:
            order = list(STAGE_ORDER_V2_WITH_SPATIAL_AND_COORDINATE_REPAIR)
        elif self.enable_spatial_alignment:
            order = list(STAGE_ORDER_V2_WITH_SPATIAL)
        elif self.enable_coordinate_repair_actions:
            order = list(STAGE_ORDER_V2_WITH_COORDINATE_REPAIR)
        else:
            order = list(STAGE_ORDER_V2)
        if self.enable_t30_real_writeback:
            return _with_t30_writeback(order)
        return order

    def _compute_structural_fingerprint(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        reference = self.fingerprint_builder.build_graph_fingerprints(session.phase8_reference_graph)  # type: ignore[attr-defined]
        target = self.fingerprint_builder.build_graph_fingerprints(session.phase8_target_graph)  # type: ignore[attr-defined]
        return {"reference": reference, "target": target}, 0.9, []

    def _align_buildings_v2(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        result = self.aligner.align(session.phase8_reference_graph, session.phase8_target_graph)  # type: ignore[attr-defined]
        confidence = _first_mapping_confidence(result)
        return result, confidence, []

    def _semantic_diff_v2(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        diff = self.diff_engine.compare(
            session.phase8_reference_graph,  # type: ignore[attr-defined]
            session.phase8_target_graph,  # type: ignore[attr-defined]
            _first_mapping_confidence(session.alignment_map),
        )
        confidence = _diff_confidence(diff)
        return diff, confidence, []

    def _generate_coordinate_repair_actions(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        reference_graph = session.phase8_reference_graph  # type: ignore[attr-defined]
        target_graph = session.phase8_target_graph  # type: ignore[attr-defined]
        if reference_graph.get("metadata", {}).get("coordinate_space") != "cad_modelspace":
            warning = "reference graph is not cad_modelspace; coordinate repair actions skipped"
            return {
                "skipped": True,
                "reason": warning,
                "repair_plan_v2": {"actions": [], "review_actions": [], "rejected_actions": []},
                "dry_run": {"valid": False, "executable_actions": []},
                "report": {"summary": {"total_actions": 0}},
            }, 0.0, [warning]
        missing = detect_coordinate_missing(reference_graph, target_graph)
        plan = build_repair_actions(missing, reference_graph, target_graph)
        if not plan.actions and not plan.review_actions and _low_confidence_fallback_context(reference_graph, target_graph):
            plan = build_review_only_repair_actions(missing, reference_graph, target_graph)
        plan = snap_repair_actions_to_target_graph(plan, target_graph)
        plan = check_repair_action_conflicts(plan, target_graph)
        plan = optimize_repair_plan_v2(plan, target_graph)
        dry_run = dry_run_repair_plan(plan, target_graph)
        report = generate_repair_action_report(plan, dry_run)
        return {
            "missing_result": missing,
            "repair_plan_v2": plan.to_dict(),
            "dry_run": dry_run.to_dict(),
            "report": report,
        }, plan.confidence, list(plan.warnings) + list(dry_run.warnings)

    def _align_reference_to_target_coordinates(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        reference_graph = session.phase8_reference_graph  # type: ignore[attr-defined]
        target_graph = session.phase8_target_graph  # type: ignore[attr-defined]
        if reference_graph.get("metadata", {}).get("coordinate_space") == "cad_modelspace":
            return {
                "skipped": True,
                "reason": "reference graph already in cad_modelspace",
                "aligned_reference_graph": reference_graph,
                "errors": [],
            }, 1.0, []
        result = align_reference_graph_to_target(
            reference_graph,
            target_graph,
            manual_anchor_pairs=getattr(session, "phase11_manual_anchor_pairs", None),
        )
        data = result.to_dict()
        return data, float(data["confidence"]), list(data.get("warnings", []))

    def _optimize_repair_plan(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        plan = self.repair_engine.generate(session.missing_result)
        optimized = self.optimizer.optimize(plan)
        return optimized, _plan_confidence(optimized), []

    def _confidence_filter(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        actions = session.repair_plan.get("actions", [])
        if getattr(session, "phase11_spatial_failed", False):
            actions = [
                {**action, "auto_execute": False, "execution_decision": "blocked_spatial_alignment"}
                for action in actions
            ]
        summary = {
            "auto_execute": sum(1 for action in actions if action.get("execution_decision") == "auto_execute"),
            "needs_review": sum(1 for action in actions if action.get("execution_decision") == "needs_review"),
            "blocked": sum(1 for action in actions if action.get("execution_decision") == "blocked"),
        }
        return {**session.repair_plan, "actions": actions, "confidence_summary": summary}, _plan_confidence({"actions": actions}), []

    def _safe_apply_to_cad_v2(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        result = self.writeback.safe_apply(session.repair_plan, session.phase8_target_graph)  # type: ignore[attr-defined]
        confidence = 0.95 if result["status"] == "success" else 0.0
        return result, confidence, list(result.get("warnings", []))

    def _apply_t30_writeback_v2(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        repair_plan_v2 = getattr(session, "phase12_repair_plan_v2", None)
        if not repair_plan_v2:
            warning = "phase12 repair_plan_v2 missing; t30 writeback skipped"
            return {"status": "skipped", "reason": warning}, 0.0, [warning]

        original_dwg_path = self._target_dwg_path(session)
        if not original_dwg_path:
            warning = "target DWG path missing; t30 writeback skipped"
            return {"status": "skipped", "reason": warning}, 0.0, [warning]

        options = dict(self.t30_writeback_options)
        options.setdefault("session_id", session.session_id)
        result = self.t30_writeback_adapter.apply_repair_plan_v2(
            repair_plan_v2,
            original_dwg_path,
            options,
        )
        data = result.to_dict()
        confidence = 0.95 if data["status"] in {"committed", "dry_run"} else 0.0
        return data, confidence, list(data.get("warnings", []))

    def _target_dwg_path(self, session: MCPSession) -> str | None:
        if session.dwg_path:
            return session.dwg_path
        for source in getattr(session, "phase8_sources", []):
            if source.get("role") == "target" and str(source.get("type") or "").lower() == "dwg":
                return str(source.get("path") or "")
        return None

    def _generate_report_v2(self, session: MCPSession) -> tuple[dict[str, Any], float, list[str]]:
        diff = session.missing_result
        writeback = getattr(session, "phase8_writeback_result", {})
        t30_writeback = getattr(session, "phase13_t30_writeback_result", {})
        report = {
            "summary": {
                "true_missing": len(diff.get("true_missing", [])),
                "design_variation": len(diff.get("design_variation", [])),
                "uncertain": len(diff.get("uncertain", [])),
                "auto_fixed": len(session.applied_actions),
                "needs_review": len(writeback.get("blocked_actions", [])),
                "t30_writeback_status": t30_writeback.get("status"),
            },
            "risk_level": "low" if not writeback.get("blocked_actions") else "medium",
            "changes": list(session.applied_actions),
            "alignment": session.alignment_map,
            "t30_writeback": t30_writeback,
        }
        input_diagnostics = getattr(session, "phase16_2_input_diagnostics", {})
        report.update(
            {
                "target_graph_diagnostics": input_diagnostics.get("target_graph_diagnostics", {}),
                "reference_graph_diagnostics": input_diagnostics.get("reference_graph_diagnostics", {}),
                "target_graph_empty_reason": input_diagnostics.get("target_graph_empty_reason", ""),
                "reference_graph_empty_reason": input_diagnostics.get("reference_graph_empty_reason", ""),
                "input_readiness_status": input_diagnostics.get("input_readiness_status", ""),
                "readiness_status": _readiness_with_review(
                    input_diagnostics.get("input_readiness_status", ""),
                    getattr(session, "phase12_repair_plan_v2", {}),
                    getattr(session, "phase11_spatial_alignment", {}),
                ),
                "scope_summary": input_diagnostics.get("scope_summary", {}),
                "manual_anchor_summary": _manual_anchor_summary(
                    input_diagnostics.get("manual_anchor_summary", {}),
                    getattr(session, "phase11_spatial_alignment", {}),
                ),
                "pdf_line_candidate_summary": input_diagnostics.get("pdf_line_candidate_summary", {}),
                "dwg_primitive_graph_summary": input_diagnostics.get("dwg_primitive_graph_summary", {}),
                "review_only_repair_summary": _review_only_repair_summary(
                    getattr(session, "phase12_repair_plan_v2", {})
                ),
            }
        )
        return report, _report_confidence(report), []

    def _envelope(
        self,
        session: MCPSession,
        stage: str,
        status: str,
        data: dict[str, Any],
        confidence: float,
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "stage": stage,
            "status": status,
            "data": data,
            "confidence": round(confidence, 4),
            "action_log": list(session.pipeline_state.action_log),
            "warnings": warnings,
        }


default_phase8_engine = Phase8PipelineEngine()


def run_phase8_pipeline(sources: list[dict[str, Any]]) -> dict[str, Any]:
    session = default_phase8_engine.create_session(sources)
    return default_phase8_engine.run(session.session_id)


def _first_mapping_confidence(alignment: dict[str, Any]) -> float:
    mapping = alignment.get("mapping", [])
    if not mapping:
        return 0.0
    return float(mapping[0].get("confidence", 0.0))


def _diff_confidence(diff: dict[str, list[dict[str, Any]]]) -> float:
    items = diff.get("true_missing", []) + diff.get("design_variation", []) + diff.get("uncertain", [])
    if not items:
        return 1.0
    return sum(float(item.get("confidence", 0.0)) for item in items) / len(items)


def _plan_confidence(plan: dict[str, Any]) -> float:
    actions = plan.get("actions", [])
    if not actions:
        return 1.0
    return sum(float(action.get("confidence", 0.0)) for action in actions) / len(actions)


def _report_confidence(report: dict[str, Any]) -> float:
    summary = report.get("summary", {})
    if summary.get("uncertain", 0):
        return 0.65
    if summary.get("design_variation", 0) or summary.get("needs_review", 0):
        return 0.8
    return 0.95


def _first_scope(sources: list[dict[str, Any]]) -> dict[str, Any]:
    for source in sources:
        if source.get("scope"):
            return dict(source["scope"])
    return {}


def _low_confidence_fallback_context(reference_graph: dict[str, Any], target_graph: dict[str, Any]) -> bool:
    return (
        reference_graph.get("metadata", {}).get("fallback")
        or target_graph.get("metadata", {}).get("not_t30_semantic")
        or reference_graph.get("metadata", {}).get("source") == "pdf_line_candidate_fallback"
    )


def _review_only_repair_summary(plan: dict[str, Any]) -> dict[str, Any]:
    review = plan.get("review_actions", [])
    return {
        "generated": bool(review),
        "review_required_count": len(review),
        "auto_executable_count": len(plan.get("actions", [])),
    }


def _readiness_with_review(status: str, plan: dict[str, Any], alignment: dict[str, Any]) -> str:
    if plan.get("review_actions"):
        return "ready_for_review_only_repair"
    if alignment.get("confidence", 0.0) and status == "ready_for_manual_anchor_alignment":
        return "ready_for_manual_anchor_alignment"
    return status


def _manual_anchor_summary(summary: dict[str, Any], alignment: dict[str, Any]) -> dict[str, Any]:
    merged = dict(summary)
    if alignment.get("metadata", {}).get("manual_anchor_summary"):
        merged.update(alignment["metadata"]["manual_anchor_summary"])
    return merged

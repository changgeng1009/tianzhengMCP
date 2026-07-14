from __future__ import annotations

from mcp.e2e.dataset import E2EDatasetRegistry
from mcp.e2e.metrics import calculate_e2e_metrics
from mcp.e2e.models import E2ERunConfig, E2ERunResult, E2EScenario
from mcp.e2e.reread_verifier import verify_sandbox_dwg_after_writeback
from mcp.pipeline_v2 import Phase8PipelineEngine
from mcp.t30_writeback.real_adapter import RealT30WritebackAdapter


class E2EScenarioRunner:
    def __init__(self, pipeline_engine_factory=None) -> None:
        self.pipeline_engine_factory = pipeline_engine_factory or Phase8PipelineEngine

    def run_scenario(
        self,
        scenario: E2EScenario,
        config: E2ERunConfig,
    ) -> E2ERunResult:
        warnings: list[str] = []
        errors: list[str] = []
        validation = E2EDatasetRegistry().validate_scenario(scenario, require_existing_target=True)
        if not validation["valid"]:
            return E2ERunResult(
                run_id=config.run_id,
                scenario_id=scenario.scenario_id,
                status="failed",
                warnings=list(validation["warnings"]),
                errors=list(validation["errors"]),
            )

        sources = self._build_sources(scenario)
        adapter = RealT30WritebackAdapter(real_com_mode=config.real_com_mode)
        engine = self.pipeline_engine_factory(
            enable_spatial_alignment=config.enable_spatial_alignment,
            enable_coordinate_repair_actions=config.enable_coordinate_repair_actions,
            enable_t30_real_writeback=config.enable_t30_writeback,
            t30_writeback_adapter=adapter,
            t30_writeback_options={
                "dry_run_only": config.dry_run_only,
                "sandbox_dir": config.sandbox_dir,
                "session_id": config.run_id,
            },
        )
        session = engine.create_session(sources)
        if scenario.manual_anchor_pairs:
            engine.sessions[session.session_id].phase11_manual_anchor_pairs = scenario.manual_anchor_pairs  # type: ignore[attr-defined]
        pipeline_result = engine.run(session.session_id)
        stored = engine.get_session(session.session_id)
        repair_plan_v2 = getattr(stored, "phase12_repair_plan_v2", {})
        writeback_result = getattr(stored, "phase13_t30_writeback_result", {})
        reread = {}
        if config.enable_t30_writeback and not config.dry_run_only:
            sandbox_path = writeback_result.get("metadata", {}).get("sandbox", {}).get("sandbox_dwg_path", "")
            reread = verify_sandbox_dwg_after_writeback(
                sandbox_path,
                writeback_result,
                target_graph_before=getattr(stored, "phase8_target_graph", None),
                options={"verification_mode": config.verification_mode},
            )
            warnings.extend(reread.get("warnings", []))
            errors.extend(reread.get("errors", []))

        result = E2ERunResult(
            run_id=config.run_id,
            scenario_id=scenario.scenario_id,
            status="success" if not errors else "failed",
            pipeline_result=pipeline_result,
            repair_plan_v2=repair_plan_v2,
            writeback_result=writeback_result,
            reread_verification=reread,
            warnings=warnings + list(pipeline_result.get("warnings", [])),
            errors=errors,
            metadata={"config": config.to_dict()},
        )
        result.metrics = calculate_e2e_metrics(scenario, result).to_dict()
        if result.warnings and result.status == "success":
            result.status = "warning" if not (config.enable_t30_writeback and config.verification_mode == "fake") else "success"
        return result

    def _build_sources(self, scenario: E2EScenario) -> list[dict]:
        sources = [dict(source) for source in scenario.reference_sources]
        if scenario.options.get("scope"):
            for source in sources:
                source["scope"] = scenario.options["scope"]
        target_source = {
            "type": "dwg",
            "role": "target",
            "path": scenario.target_dwg_path,
            "enable_cad_reader": scenario.options.get("enable_dwg_cad_reader", True),
            "scope": scenario.options.get("scope"),
        }
        if scenario.options.get("target_semantic_graph"):
            target_source["semantic_graph"] = scenario.options["target_semantic_graph"]
        sources.append(target_source)
        return sources

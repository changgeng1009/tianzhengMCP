from __future__ import annotations

import json
from pathlib import Path

from mcp.e2e.models import E2EScenario, scenario_from_dict


class E2EDatasetRegistry:
    def __init__(self) -> None:
        self._scenarios: dict[str, E2EScenario] = {}

    def register_scenario(self, scenario: E2EScenario) -> None:
        self._scenarios[scenario.scenario_id] = scenario

    def load_scenarios_from_json(self, path: str) -> list[E2EScenario]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        raw_scenarios = payload.get("scenarios", payload if isinstance(payload, list) else [])
        scenarios = [scenario_from_dict(item) for item in raw_scenarios]
        for scenario in scenarios:
            self.register_scenario(scenario)
        return scenarios

    def export_scenarios_json(self) -> dict:
        return {"scenarios": [scenario.to_dict() for scenario in self._scenarios.values()]}

    def validate_scenario(self, scenario: E2EScenario, require_existing_target: bool = True) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        dwg_candidates: list[str] = []
        resolved_target_dwg_path = scenario.target_dwg_path
        if not scenario.scenario_id:
            errors.append("scenario_id is required")
        if not scenario.reference_sources:
            errors.append("reference_sources is required")
        for source in scenario.reference_sources:
            if source.get("type") not in {"pdf", "png", "dwg"}:
                errors.append(f"unsupported reference source type: {source.get('type')}")
        if not scenario.target_dwg_path:
            errors.append("target_dwg_path is required")
        elif require_existing_target and not Path(scenario.target_dwg_path).exists():
            target = Path(scenario.target_dwg_path)
            if target.parent.exists():
                dwg_candidates = sorted(str(path) for path in target.parent.glob("*.dwg"))
            if len(dwg_candidates) == 1:
                warnings.append(f"DWG 候选: {dwg_candidates[0]}，请确认是否为目标图纸")
                if scenario.options.get("allow_single_dwg_fallback") is True:
                    scenario.target_dwg_path = dwg_candidates[0]
                    resolved_target_dwg_path = scenario.target_dwg_path
                    warnings.append("allow_single_dwg_fallback=true; 使用唯一 DWG 候选作为 target_dwg_path")
                else:
                    errors.append(f"target DWG not found: {scenario.target_dwg_path}")
            else:
                if dwg_candidates:
                    warnings.append(f"DWG 候选数量: {len(dwg_candidates)}，请显式修正 target_dwg_path")
                errors.append(f"target DWG not found: {scenario.target_dwg_path}")
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "scenario_id": scenario.scenario_id,
            "dwg_candidates": dwg_candidates,
            "resolved_target_dwg_path": resolved_target_dwg_path,
        }

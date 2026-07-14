from __future__ import annotations

import json


def test_dataset_registry_loads_and_validates_scenario(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.dataset import E2EDatasetRegistry

    dwg = synthetic_cad_factory(tmp_path / "target.dwg")
    path = tmp_path / "scenarios.json"
    path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "scenario_id": "scn1",
                        "name": "场景",
                        "reference_sources": [{"type": "png", "path": "ref.png", "semantic_graph": {"pipes": []}}],
                        "target_dwg_path": str(dwg),
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry = E2EDatasetRegistry()
    scenarios = registry.load_scenarios_from_json(str(path))
    validation = registry.validate_scenario(scenarios[0])

    assert validation["valid"] is True
    assert registry.export_scenarios_json()["scenarios"][0]["scenario_id"] == "scn1"


def test_dataset_validation_requires_existing_target_for_real_run(tmp_path) -> None:
    from mcp.e2e.dataset import E2EDatasetRegistry
    from mcp.e2e.models import E2EScenario

    scenario = E2EScenario(
        scenario_id="missing",
        name="缺失目标",
        reference_sources=[{"type": "png", "path": "ref.png"}],
        target_dwg_path=str(tmp_path / "missing.dwg"),
    )

    validation = E2EDatasetRegistry().validate_scenario(scenario, require_existing_target=True)

    assert validation["valid"] is False
    assert validation["errors"]

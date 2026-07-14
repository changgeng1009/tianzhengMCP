from __future__ import annotations

import json


def _write_inputs(tmp_path, synthetic_cad_factory):
    scenario_path = tmp_path / "scenario.json"
    dwg = synthetic_cad_factory(tmp_path / "target.dwg", payload=b"original")
    scenario_path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "scenario_id": "scn1",
                        "name": "acceptance fake",
                        "reference_sources": [
                            {
                                "type": "png",
                                "role": "reference",
                                "path": "reference.png",
                                "semantic_graph": {
                                    "metadata": {"coordinate_space": "cad_modelspace"},
                                    "pipes": [
                                        {
                                            "id": "p1",
                                            "mapped_geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                                            "mapped_confidence": 0.92,
                                            "dn": "DN50",
                                            "system_type": "给水",
                                            "layer": "PIPE",
                                        }
                                    ],
                                },
                            }
                        ],
                        "target_dwg_path": str(dwg),
                        "options": {
                            "target_semantic_graph": {
                                "metadata": {"coordinate_space": "cad_modelspace"},
                                "pipes": [],
                            }
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "object_type": "TDbPipe",
                        "method_name": "Insert",
                        "available": True,
                        "probe_status": "confirmed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manual_path = tmp_path / "manual_confirmation.json"
    manual_path.write_text(
        json.dumps(
            {
                "TDbPipe.Insert": {
                    "confirmed": True,
                    "parameters": [
                        {"name": "geometry", "type": "json", "required": True},
                        {"name": "dn", "type": "string", "required": True},
                        {"name": "system", "type": "string", "required": True},
                        {"name": "layer", "type": "string", "required": True},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    return scenario_path, probe_path, manual_path, dwg


def test_checklist_blocks_missing_files_and_disabled_real_mode(tmp_path) -> None:
    from mcp.acceptance.models import AcceptanceRunConfig
    from mcp.acceptance.real_writeback_checklist import generate_real_writeback_checklist

    config = AcceptanceRunConfig(
        run_id="run1",
        scenario_path=str(tmp_path / "missing_scenario.json"),
        probe_result_path=str(tmp_path / "missing_probe.json"),
        manual_confirmation_path=str(tmp_path / "missing_manual.json"),
    )

    checklist = generate_real_writeback_checklist(config)

    assert checklist["ready"] is False
    assert checklist["blocking_items"]


def test_acceptance_runner_default_dry_run_does_not_real_write(tmp_path, synthetic_cad_factory) -> None:
    from mcp.acceptance.acceptance_runner import Phase15AcceptanceRunner
    from mcp.acceptance.models import AcceptanceRunConfig

    scenario_path, probe_path, manual_path, dwg = _write_inputs(tmp_path, synthetic_cad_factory)
    config = AcceptanceRunConfig(
        run_id="run-dry",
        scenario_path=str(scenario_path),
        probe_result_path=str(probe_path),
        manual_confirmation_path=str(manual_path),
        output_dir=str(tmp_path / "reports"),
    )

    result = Phase15AcceptanceRunner().run_acceptance(config)

    assert result.status in {"warning", "success"}
    assert result.writeback_result in ({}, None)
    assert dwg.read_bytes() == b"original"


def test_acceptance_runner_fake_mode_generates_report(tmp_path, synthetic_cad_factory, register_t30_sandbox_outputs) -> None:
    from mcp.acceptance.acceptance_runner import Phase15AcceptanceRunner
    from mcp.acceptance.models import AcceptanceRunConfig

    scenario_path, probe_path, manual_path, dwg = _write_inputs(tmp_path, synthetic_cad_factory)
    register_t30_sandbox_outputs(tmp_path / "sandbox", dwg.name)
    config = AcceptanceRunConfig(
        run_id="run-fake",
        scenario_path=str(scenario_path),
        probe_result_path=str(probe_path),
        manual_confirmation_path=str(manual_path),
        sandbox_dir=str(tmp_path / "sandbox"),
        output_dir=str(tmp_path / "reports"),
        enable_real_writeback=True,
        real_com_mode=False,
        dry_run_only=False,
        verification_mode="fake",
    )

    result = Phase15AcceptanceRunner().run_acceptance(config)

    assert result.status == "success"
    assert result.acceptance_report_path
    assert dwg.read_bytes() == b"original"

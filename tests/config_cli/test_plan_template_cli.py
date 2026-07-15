from __future__ import annotations

import json

from scripts.skill_cli import main


def _invoke(capsys, *args):
    code = main(["--json", *map(str, args)])
    return code, json.loads(capsys.readouterr().out)


def test_req_083_plan_build(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "plan", "build", path)
    assert code == 0
    assert len(output["plan_hash"]) == 64
    assert output["plan_id"].startswith("plan-")


def test_req_084_plan_verify(capsys, cli_manifest, tmp_path):
    manifest_path, _ = cli_manifest
    code, plan = _invoke(capsys, "plan", "build", manifest_path)
    assert code == 0
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    code, output = _invoke(capsys, "plan", "verify", plan_path)
    assert code == 0
    assert output["ok"] is True


def test_req_085_simulate_offline(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "simulate", path, "--backend", "offline")
    assert code == 0
    assert output["simulation_kind"] == "OFFLINE_ONLY"
    assert output["real_execution"] is False


def test_req_086_simulate_nextgen_mock(capsys, cli_manifest, tmp_path):
    path, value = cli_manifest
    value["runtime"]["runtime_mode"] = "offline_analysis"
    value["product"]["requested_product"] = "unknown"
    value["product"]["prohibited_products"] = []
    value["backend"]["preferred_backend"] = "nextgen_mock"
    value["backend"]["mock_allowed"] = True
    value["workflow"]["workflow_id"] = "nextgen_mock_job_simulation"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    code, output = _invoke(capsys, "simulate", path, "--backend", "nextgen_mock")
    assert code == 0
    assert output["simulation_kind"] == "NEXTGEN_MOCK_ONLY"
    assert output["real_execution"] is False


def test_req_087_templates_list(capsys):
    code, output = _invoke(capsys, "templates", "list")
    assert code == 0
    assert len(output["templates"]) == 10


def test_req_088_templates_create(capsys, tmp_path):
    output_dir = tmp_path / "created-template"
    code, output = _invoke(
        capsys,
        "templates",
        "create",
        "offline_analysis",
        "--output",
        output_dir,
    )
    assert code == 0
    assert output["created"] is True
    assert (output_dir / "project_manifest.json").is_file()

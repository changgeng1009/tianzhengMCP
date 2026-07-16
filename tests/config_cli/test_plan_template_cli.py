from __future__ import annotations

import json
from pathlib import Path

from tests.config_cli import _cli_loader
from tests.config_cli._cli_loader import main


def _invoke(capsys, *args):
    code, envelope = _invoke_envelope(capsys, *args)
    return code, envelope["result"]


def _invoke_envelope(capsys, *args):
    code = main(["--json", *map(str, args)])
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope


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
    assert output["simulation"]["simulation_kind"] == "OFFLINE_ONLY"
    assert output["simulation"]["real_execution"] is False


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
    assert output["simulation"]["simulation_kind"] == "NEXTGEN_MOCK_ONLY"
    assert output["simulation"]["real_execution"] is False


def test_req_087_templates_list(capsys):
    code, output = _invoke(capsys, "templates", "list")
    assert code == 0
    assert len(output["templates"]) == 10


def test_req_088_templates_create(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = "created-template"
    code, output = _invoke(
        capsys,
        "templates",
        "create",
        "offline_analysis",
        "--output",
        output_dir,
    )
    assert code == 0
    assert output["template_id"] == "offline_analysis"
    assert output["cad_connected"] is False
    assert (tmp_path / output_dir / "project_manifest.json").is_file()


def test_req_088a_templates_create_allows_explicit_external_temporary_output(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path.parent / f"cad-config-template-{tmp_path.name}"
    code, output = _invoke(
        capsys,
        "templates",
        "create",
        "offline_analysis",
        "--output",
        output_dir,
    )
    assert code == 0
    assert Path(output["output"]).is_file()
    assert output_dir != _cli_loader._MODULE.ROOT
    assert output_dir != Path(_cli_loader._MODULE.INSTALL_ROOT)


def test_req_088b_templates_create_rejects_source_and_install_output(capsys):
    module = _cli_loader._MODULE
    for forbidden_root in (module.ROOT, Path(module.INSTALL_ROOT)):
        code, envelope = _invoke_envelope(
            capsys,
            "templates",
            "create",
            "offline_analysis",
            "--output",
            forbidden_root / "forbidden-template-output",
        )
        assert code == 6
        assert envelope["error"]["code"] == "PATH_EXTERNAL_NOT_ALLOWED"


def test_req_088c_templates_create_rejects_traversal_unc_and_cad_output(capsys):
    for output_dir in ("..\\outside", "\\\\server\\share", "unsafe-output.dwg", "unsafe-output.dxf"):
        code, envelope = _invoke_envelope(
            capsys,
            "templates",
            "create",
            "offline_analysis",
            "--output",
            output_dir,
        )
        assert code in {2, 3}
        assert envelope["ok"] is False

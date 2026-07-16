from __future__ import annotations

import json

from tests.config_cli._cli_loader import main


def _invoke(capsys, *args):
    code = main(["--json", *map(str, args)])
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope["result"]


def test_req_079_config_resolve(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "config", "resolve", path)
    assert code == 0
    assert output["manifest"]["safety"]["production_allowed"] is False
    assert output["resolution"]["source_trace"]
    assert output["paths"]["filesystem_accessed"] is False


def test_req_080_runtime_select(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "runtime", "select", path)
    assert code == 0
    assert output["runtime_mode"] == "plain_autocad"
    assert output["trace"]


def test_s3_product_select_exposes_independent_product_runtime_evidence(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "product", "select", path)
    assert code == 0
    assert output["product"] == "generic_autocad"
    assert output["product_profile"]["product"] == "generic_autocad"
    assert output["product_profile"]["execution_runtime"] == "offline"
    assert output["product_profile"]["execution_allowed"] is False


def test_req_081_backend_select(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "backend", "select", path)
    assert code == 0
    assert output["backend"] == "offline"
    assert output["real_execution_supported"] is False


def test_req_082_workflow_select(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "workflow", "select", path)
    assert code == 0
    assert output["definition"]["workflow_id"] == "generic_autocad_redraw_offline"
    assert output["trace"]

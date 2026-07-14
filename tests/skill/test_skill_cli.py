from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcp.skill_cli import build_dry_run_manifest, build_parser, load_config, run_cli


def test_cli_backend_list_is_static_and_does_not_connect_autocad(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcp.backends.com_backend.importlib.util.find_spec", lambda _name: object()
    )
    result = run_cli(["backend-list"])
    assert {item["backend_id"] for item in result["backends"]} == {"com", "mock", "net_bridge", "tianzheng_api"}
    assert result["autocad_connected"] is False


def test_cli_backend_capabilities_reports_com_without_connecting(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcp.backends.com_backend.importlib.util.find_spec", lambda _name: object()
    )
    result = run_cli(["backend-capabilities", "--backend", "com"])
    assert result["backend_id"] == "com"
    assert result["capabilities"]["create_tdb_pipe"] is False


def test_cli_execute_sandbox_requires_working_copy() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["execute-sandbox", "--backend", "mock"])


def test_cli_execute_flag_is_disabled_in_stage2() -> None:
    with pytest.raises(SystemExit):
        run_cli(["execute-sandbox", "--backend", "mock", "--working-copy", "safe.dwg", "--execute"])


def test_cli_supports_all_common_arguments() -> None:
    args = build_parser().parse_args([
        "inspect", "--backend", "mock", "--config", "skill/configs/default.yaml", "--dry-run",
        "--reference", "ref.pdf", "--source", "source.dwg", "--working-copy", "copy.dwg",
        "--reports-dir", "reports2", "--run-id", "run-1",
    ])
    assert args.backend == "mock"
    assert args.reference == ["ref.pdf"]
    assert args.run_id == "run-1"


def test_json_compatible_yaml_config_loads_without_pyyaml() -> None:
    config = load_config("skill/configs/default.yaml")
    assert config["stage3_sample"]["reference_dwg"] is None
    assert config["stage3_sample"]["target_dwg"] is None


def test_utf8_paths_round_trip_in_manifest() -> None:
    args = argparse.Namespace(
        command="inspect", backend="mock", reference=["D:/资料/参考图.pdf"], source="D:/资料/源图.dwg",
        working_copy="D:/资料/安全副本.dwg", reports_dir="报告", run_id="中文-run", dry_run=True,
    )
    result = build_dry_run_manifest(args, load_config("skill/configs/default.yaml"), ["mock"])
    assert result["reference_inputs"] == ["D:/资料/参考图.pdf"]
    assert result["working_copy"] == "D:/资料/安全副本.dwg"
    assert result["safety"]["autocad_connected"] is False

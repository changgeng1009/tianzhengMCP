from __future__ import annotations

import argparse
import json

from tests.config_cli._cli_loader import build_parser, main


def _invoke(capsys, *args):
    code = main(["--json", *map(str, args)])
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope


def _leaf_count(parser: argparse.ArgumentParser) -> int:
    subparsers = [
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if not subparsers:
        return 1
    return sum(_leaf_count(child) for child in subparsers[0].choices.values())


def test_cli_registers_twenty_one_leaf_commands():
    assert _leaf_count(build_parser()) == 21


def test_product_select_command(capsys, cli_manifest):
    path, _ = cli_manifest
    code, envelope = _invoke(capsys, "product", "select", path)
    assert code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["adapter"] == "GenericAutoCadAdapter"


def test_plan_hash_command(capsys, cli_manifest, tmp_path):
    manifest_path, _ = cli_manifest
    code, envelope = _invoke(capsys, "plan", "build", manifest_path)
    assert code == 0
    plan = envelope["result"]
    plan_path = tmp_path / "plan-for-hash.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    code, envelope = _invoke(capsys, "plan", "hash", plan_path)
    assert code == 0
    assert envelope["result"]["plan_hash"] == plan["plan_hash"]
    assert envelope["result"]["stored_plan_hash"] == plan["plan_hash"]


def test_five_legacy_commands_remain_available(capsys, cli_legacy_manifest):
    commands = [
        ("inspect-manifest", cli_legacy_manifest),
        ("validate-manifest", cli_legacy_manifest),
        ("select-runtime", cli_legacy_manifest),
        ("build-plan", cli_legacy_manifest, "--dry-run"),
        ("capabilities", "--mode", "plain_autocad"),
    ]
    for command in commands:
        code, envelope = _invoke(capsys, *command)
        assert code == 0
        assert envelope["ok"] is True


def test_legacy_default_output_shape_is_preserved(capsys, cli_legacy_manifest):
    code = main(["inspect-manifest", str(cli_legacy_manifest)])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert "ok" not in output
    assert output["cad_connected"] is False
    assert output["dwg_read"] is False

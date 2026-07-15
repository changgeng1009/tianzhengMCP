from __future__ import annotations

import json

from scripts.skill_cli import main


def _invoke(capsys, *args):
    code = main(["--json", *map(str, args)])
    output = json.loads(capsys.readouterr().out)
    return code, output


def test_req_074_manifest_validate(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "manifest", "validate", path)
    assert code == 0
    assert output["ok"] is True


def test_req_075_manifest_normalize(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "manifest", "normalize", path)
    assert code == 0
    assert output["manifest"]["schema_version"] == "1.1.0"


def test_req_076_manifest_explain(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "manifest", "explain", path)
    assert code == 0
    assert output["resolution_trace"]
    assert output["routing_trace"]


def test_req_077_manifest_migrate_is_non_destructive(capsys, cli_legacy_manifest):
    original = cli_legacy_manifest.read_text(encoding="utf-8")
    code, output = _invoke(
        capsys, "manifest", "migrate", cli_legacy_manifest, "--to-version", "1.1.0"
    )
    assert code == 0
    assert output["to_version"] == "1.1.0"
    assert cli_legacy_manifest.read_text(encoding="utf-8") == original


def test_req_078_manifest_diff(capsys, cli_manifest, tmp_path):
    first, value = cli_manifest
    value["task"]["task_description"] = "变化后的任务"
    second = tmp_path / "second.json"
    second.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    code, output = _invoke(capsys, "manifest", "diff", first, second)
    assert code == 0
    assert output["different"] is True
    assert output["changes"]


def test_req_089_cli_json_output(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output = _invoke(capsys, "manifest", "validate", path)
    assert code == 0
    assert isinstance(output, dict)


def test_req_090_cli_structured_exit_code(capsys, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")
    code, output = _invoke(capsys, "manifest", "validate", path)
    assert code == 2
    assert output["ok"] is False
    assert output["error"]["code"] == "MANIFEST_INVALID"

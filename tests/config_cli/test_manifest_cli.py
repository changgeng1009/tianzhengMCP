from __future__ import annotations

import json

from tests.config_cli._cli_loader import main


def _invoke(capsys, *args):
    code = main(["--json", *map(str, args)])
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope, envelope.get("result")


def test_req_074_manifest_validate(capsys, cli_manifest):
    path, _ = cli_manifest
    code, envelope, output = _invoke(capsys, "manifest", "validate", path)
    assert code == 0
    assert envelope["ok"] is True
    assert output["valid"] is True


def test_req_075_manifest_normalize(capsys, cli_manifest):
    path, _ = cli_manifest
    code, _, output = _invoke(capsys, "manifest", "normalize", path)
    assert code == 0
    assert output["manifest"]["schema_version"] == "1.1.0"


def test_req_076_manifest_explain(capsys, cli_manifest):
    path, _ = cli_manifest
    code, _, output = _invoke(capsys, "manifest", "explain", path)
    assert code == 0
    assert output["resolution"]["source_trace"]
    assert output["runtime"]["trace"]
    assert output["workflow"]["trace"]
    assert output["filesystem_accessed_by_path_resolver"] is False


def test_req_077_manifest_migrate_is_non_destructive(capsys, cli_legacy_manifest):
    original = cli_legacy_manifest.read_text(encoding="utf-8")
    code, _, output = _invoke(
        capsys, "manifest", "migrate", cli_legacy_manifest, "--to-version", "1.1.0"
    )
    assert code == 0
    assert output["to_version"] == "1.1.0"
    assert output["written"] is True
    assert cli_legacy_manifest.read_text(encoding="utf-8") == original


def test_req_078_manifest_diff(capsys, cli_manifest, tmp_path):
    first, value = cli_manifest
    value["task"]["task_description"] = "变化后的任务"
    second = tmp_path / "second.json"
    second.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    code, _, output = _invoke(capsys, "manifest", "diff", first, second)
    assert code == 0
    assert output["equal"] is False
    assert output["change_count"] > 0
    assert output["changes"]


def test_req_089_cli_json_output(capsys, cli_manifest):
    path, _ = cli_manifest
    code, output, result = _invoke(capsys, "manifest", "validate", path)
    assert code == 0
    assert isinstance(output, dict)
    assert output["ok"] is True
    assert result["valid"] is True


def test_req_090_cli_structured_exit_code(capsys, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"schema_version":"1.1.0"}', encoding="utf-8")
    code, output, result = _invoke(capsys, "manifest", "validate", path)
    assert code == 2
    assert output["ok"] is False
    assert output["error"]["code"] == "MANIFEST_INVALID"
    assert result is None

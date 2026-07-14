from __future__ import annotations

import json


def test_probe_loader_missing_file_returns_structured_failure(tmp_path) -> None:
    from mcp.e2e.probe_loader import load_manual_probe_result

    result = load_manual_probe_result(str(tmp_path / "missing.json"))

    assert result["status"] == "failed"
    assert result["errors"]


def test_probe_loader_reads_fake_probe_result(tmp_path) -> None:
    from mcp.e2e.probe_loader import load_manual_probe_result

    path = tmp_path / "probe.json"
    path.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "TDbPipe.Insert",
                        "object_type": "TDbPipe",
                        "method_name": "Insert",
                        "available": True,
                        "probe_status": "confirmed",
                        "signature": {"parameters": ["geometry"]},
                    },
                    {
                        "capability_id": "TDbSprinkler.Insert",
                        "object_type": "TDbSprinkler",
                        "method_name": "Insert",
                        "available": True,
                        "probe_status": "unconfirmed",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = load_manual_probe_result(str(path))

    assert result["status"] == "success"
    assert result["confirmed_capabilities"] == ["TDbPipe.Insert"]
    assert result["candidate_methods"][0]["method"] == "TDbPipe.Insert"


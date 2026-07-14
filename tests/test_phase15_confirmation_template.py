from __future__ import annotations


def test_confirmation_template_defaults_all_items_to_unconfirmed(tmp_path) -> None:
    from mcp.acceptance.confirmation_template import generate_manual_confirmation_template

    output = tmp_path / "manual_confirmation.json"
    result = generate_manual_confirmation_template(
        {
            "metadata": {"path": "probe.json"},
            "capabilities": [
                {
                    "object_type": "TDbPipe",
                    "method_name": "Insert",
                    "probe_status": "confirmed",
                    "available": True,
                }
            ],
        },
        str(output),
    )

    assert result["status"] == "success"
    assert result["template"]["TDbPipe.Insert"]["confirmed"] is False
    assert output.exists()


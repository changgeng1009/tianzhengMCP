from __future__ import annotations


def test_review_list_generates_markdown_and_json(tmp_path) -> None:
    from mcp.acceptance_pack.review_list import generate_manual_review_list

    acceptance_result = {
        "run_id": "run1",
        "e2e_result": {
            "repair_plan_v2": {
                "actions": [
                    {
                        "action_id": "a1",
                        "action_type": "add_pipe",
                        "geometry": {"start": [0, 0, 0], "end": [10, 0, 0]},
                        "system": "给水",
                        "dn": "DN50",
                        "layer": "PIPE",
                        "confidence": 0.92,
                        "reason": "true_missing",
                    }
                ],
                "review_actions": [{"action_id": "r1", "action_type": "add_valve", "confidence": 0.7}],
                "rejected_actions": [{"action_id": "x1", "action_type": "add_sprinkler", "confidence": 0.4}],
            }
        },
        "writeback_result": {"created_entities": [{"handle": "FAKE-1"}]},
        "reread_verification": {"status": "verified"},
        "warnings": ["人工复核"],
    }

    result = generate_manual_review_list(acceptance_result, str(tmp_path / "review"))

    assert result["status"] == "success"
    assert result["json_path"].endswith(".json")
    markdown = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "add_pipe" in markdown
    assert "DN50" in markdown
    assert "rejected" in markdown


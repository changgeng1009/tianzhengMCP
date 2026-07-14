from __future__ import annotations


def test_action_builder_creates_auto_review_and_rejected_actions() -> None:
    from mcp.repair_actions.action_builder import build_repair_actions

    missing = {
        "true_missing": [
            {
                "element_type": "pipe",
                "element": {
                    "id": "p_high",
                    "source_element_id": "p_high",
                    "mapped_geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                    "mapped_confidence": 0.91,
                    "dn": "DN50",
                    "system_type": "给水",
                    "layer": "PIPE-给水",
                },
            },
            {
                "element_type": "sprinkler",
                "element": {
                    "id": "s_mid",
                    "source_element_id": "s_mid",
                    "mapped_geometry": {"position": [50, 50, 0]},
                    "mapped_confidence": 0.7,
                    "system_type": "喷淋",
                },
            },
            {
                "element_type": "valve",
                "element": {
                    "id": "v_low",
                    "source_element_id": "v_low",
                    "mapped_geometry": {"position": [30, 0, 0]},
                    "mapped_confidence": 0.4,
                    "system_type": "给水",
                },
            },
        ]
    }

    plan = build_repair_actions(missing, {}, {})

    assert plan.actions[0].action_type == "add_pipe"
    assert plan.actions[0].auto_execute is True
    assert plan.review_actions[0].action_type == "add_sprinkler"
    assert plan.rejected_actions[0].action_type == "add_valve"


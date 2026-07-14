from __future__ import annotations

import json


def test_template_loader_disables_missing_image_with_warning(tmp_path) -> None:
    from mcp.vision_templates.template_loader import load_template_library

    path = tmp_path / "templates.json"
    path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "sprinkler_missing",
                        "template_type": "sprinkler",
                        "name": "缺失图片喷头",
                        "image_path": str(tmp_path / "missing.png"),
                        "expected_symbol_type": "sprinkler_candidate",
                        "enabled": True,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = load_template_library(str(path))
    template = store.get_template("sprinkler_missing")

    assert template.enabled is False
    assert template.metadata["warnings"]


def test_default_template_builders_create_disabled_metadata_templates() -> None:
    from mcp.vision_templates.fitting_templates import build_default_fitting_template_store
    from mcp.vision_templates.legend_templates import build_default_legend_template_store
    from mcp.vision_templates.sprinkler_templates import build_default_sprinkler_template_store
    from mcp.vision_templates.valve_templates import build_default_valve_template_store

    stores = [
        build_default_sprinkler_template_store(),
        build_default_valve_template_store(),
        build_default_fitting_template_store(),
        build_default_legend_template_store(),
    ]

    assert all(store.list_templates() for store in stores)
    assert all(template.enabled is False for store in stores for template in store.list_templates())


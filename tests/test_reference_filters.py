from __future__ import annotations


def test_title_block_filter_removes_non_design_content():
    from reference.filters import ReferenceEntityFilter

    entities = [
        {"id": "design_line", "type": "line", "layer": "A-PIPE", "properties": {}},
        {"id": "title_text", "type": "text", "layer": "TITLE", "properties": {"text": "图签"}},
    ]

    filtered = ReferenceEntityFilter(
        {"ignored_layers": ["TITLE"], "ignored_text_patterns": ["图签"]}
    ).filter_entities(entities)

    assert [entity["id"] for entity in filtered] == ["design_line"]

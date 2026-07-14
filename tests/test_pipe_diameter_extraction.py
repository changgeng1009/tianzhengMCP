from __future__ import annotations


def test_dn200_is_recognized_and_normalized():
    from reference.pipe_diameter import PipeDiameterExtractor

    result = PipeDiameterExtractor().extract_from_text("DN200")

    assert result[0]["diameter"] == "DN200"
    assert result[0]["status"] == "Need User Confirmation"


def test_dn_with_space_is_normalized_to_dn200():
    from reference.pipe_diameter import PipeDiameterExtractor

    assert PipeDiameterExtractor().extract_from_text("DN 200")[0]["diameter"] == "DN200"


def test_de110_is_recognized():
    from reference.pipe_diameter import PipeDiameterExtractor

    assert PipeDiameterExtractor().extract_from_text("De110")[0]["diameter"] == "De110"


def test_extract_from_reference_model_reads_text_entities_only():
    from reference.pipe_diameter import PipeDiameterExtractor

    model = {
        "entities": [
            {
                "id": "text_1",
                "handle": "T1",
                "type": "text",
                "properties": {"text": "DN 200"},
            },
            {"id": "line_1", "handle": "L1", "type": "line", "properties": {}},
        ]
    }

    result = PipeDiameterExtractor().extract_from_model(model)

    assert result == [
        {
            "entity_id": "text_1",
            "handle": "T1",
            "raw_text": "DN 200",
            "diameter": "DN200",
            "confidence": 0.9,
            "status": "Need User Confirmation",
            "reason": "Diameter text recognized, but pipe association is not determined in Phase 5.5.",
        }
    ]

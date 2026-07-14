def test_current_cad_model_loads_mock_data_without_cad_world_assumption() -> None:
    from vision.current_cad_model import CurrentCADModelLoader

    data = {
        "source": {"kind": "mock", "name": "current-cad"},
        "entities": [
            {
                "id": "cad_pipe_001",
                "type": "pipe",
                "geometry": {
                    "coordinate_system": "normalized",
                    "points": [
                        {"x": 0.2, "y": 0.4},
                        {"x": 0.58, "y": 0.4},
                    ],
                    "bounding_box": {
                        "x_min": 0.2,
                        "y_min": 0.38,
                        "x_max": 0.58,
                        "y_max": 0.42,
                        "coordinate_system": "normalized",
                    },
                },
                "confidence": 1.0,
                "status": "Confirmed",
                "evidence": "来自 Mock Current CAD Model，非图像识别。",
                "uncertainties": [],
                "properties": {"system": "排水", "dn": 100},
            }
        ],
    }

    model = CurrentCADModelLoader().load_from_mock_data(data)

    assert model.source["kind"] == "mock"
    assert model.entities[0].geometry.coordinate_system.value == "normalized"
    assert model.entities[0].geometry.coordinate_system.value != "cad_world"

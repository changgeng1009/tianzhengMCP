VISION_REFERENCE_MODEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source", "image_quality", "global_uncertainties", "entities"],
    "properties": {
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "name"],
            "properties": {
                "kind": {"type": "string"},
                "name": {"type": "string"},
            },
        },
        "image_quality": {
            "type": "object",
            "additionalProperties": False,
            "required": ["confidence", "issues"],
            "properties": {
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "issues": {"type": "array", "items": {"type": "string"}},
            },
        },
        "global_uncertainties": {
            "type": "array",
            "items": {"type": "string"},
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "type",
                    "geometry",
                    "confidence",
                    "status",
                    "evidence",
                    "uncertainties",
                    "properties",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "geometry": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["coordinate_system", "points", "bounding_box"],
                        "properties": {
                            "coordinate_system": {
                                "type": "string",
                                "enum": ["image_pixel", "normalized"],
                            },
                            "points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["x", "y"],
                                    "properties": {
                                        "x": {"type": "number"},
                                        "y": {"type": "number"},
                                    },
                                },
                            },
                            "bounding_box": {
                                "anyOf": [
                                    {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": [
                                            "x_min",
                                            "y_min",
                                            "x_max",
                                            "y_max",
                                            "coordinate_system",
                                        ],
                                        "properties": {
                                            "x_min": {"type": "number"},
                                            "y_min": {"type": "number"},
                                            "x_max": {"type": "number"},
                                            "y_max": {"type": "number"},
                                            "coordinate_system": {
                                                "type": "string",
                                                "enum": ["image_pixel", "normalized"],
                                            },
                                        },
                                    },
                                    {"type": "null"},
                                ]
                            },
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "status": {
                        "type": "string",
                        "enum": ["Confirmed", "Need User Confirmation", "Uncertain"],
                    },
                    "evidence": {"type": "string"},
                    "uncertainties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "properties": {
                        "type": "object",
                        "additionalProperties": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                            ]
                        },
                    },
                },
            },
        },
    },
}

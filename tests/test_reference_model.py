from __future__ import annotations

from typing import Any


class FakeVisionProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[Any] = []

    def analyze_image(self, image: Any) -> dict[str, Any]:
        self.calls.append(image)
        return self.payload


def test_reference_model_builder_uses_fake_provider_and_keeps_structured_entities() -> None:
    from vision.reference_model import ReferenceModelBuilder
    from vision.provider import ImageInput

    payload = {
        "source": {"kind": "image", "name": "reference.png"},
        "image_quality": {
            "confidence": 0.64,
            "issues": ["轻微旋转", "局部模糊"],
        },
        "global_uncertainties": ["右下角标注模糊，需要用户确认。"],
        "entities": [
            {
                "id": "ref_pipe_001",
                "type": "pipe",
                "geometry": {
                    "coordinate_system": "normalized",
                    "points": [
                        {"x": 0.2, "y": 0.4},
                        {"x": 0.6, "y": 0.4},
                    ],
                    "bounding_box": {
                        "x_min": 0.2,
                        "y_min": 0.38,
                        "x_max": 0.6,
                        "y_max": 0.42,
                        "coordinate_system": "normalized",
                    },
                },
                "confidence": 0.52,
                "status": "Need User Confirmation",
                "evidence": "可见水平管线和 DN100 标注，但截图模糊。",
                "uncertainties": ["DN 数字边缘模糊。"],
                "properties": {"system": "排水", "dn": 100},
            }
        ],
    }
    provider = FakeVisionProvider(payload)

    model = ReferenceModelBuilder(provider).build_from_image(
        ImageInput.from_url("https://example.com/reference.png")
    )

    assert provider.calls
    assert model.entities[0].entity_id == "ref_pipe_001"
    assert model.entities[0].confidence == 0.52
    assert model.global_uncertainties == ["右下角标注模糊，需要用户确认。"]

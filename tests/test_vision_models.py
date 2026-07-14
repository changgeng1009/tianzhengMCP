import pytest


def test_entity_requires_confidence_status_evidence_and_uncertainty() -> None:
    from vision.models import (
        BoundingBox,
        ConfidenceStatus,
        CoordinateSystem,
        EntityGeometry,
        VisionEntity,
    )

    entity = VisionEntity(
        entity_id="ref_pipe_001",
        type="pipe",
        geometry=EntityGeometry(
            coordinate_system=CoordinateSystem.IMAGE_PIXEL,
            bounding_box=BoundingBox(
                x_min=10,
                y_min=20,
                x_max=110,
                y_max=40,
                coordinate_system=CoordinateSystem.IMAGE_PIXEL,
            ),
        ),
        confidence=0.52,
        status=ConfidenceStatus.NEED_USER_CONFIRMATION,
        evidence="线型像排水管，但截图略模糊。",
        uncertainties=["DN 标注边缘模糊，无法确认是否为 DN100。"],
        properties={"system": "排水", "dn": 100},
    )

    assert entity.to_dict()["confidence"] == 0.52
    assert entity.to_dict()["status"] == "Need User Confirmation"
    assert entity.to_dict()["geometry"]["coordinate_system"] == "image_pixel"


def test_uncertain_entity_without_uncertainties_is_rejected() -> None:
    from vision.models import (
        ConfidenceStatus,
        CoordinateSystem,
        EntityGeometry,
        VisionEntity,
    )

    with pytest.raises(ValueError, match="uncertainties"):
        VisionEntity(
            entity_id="ref_valve_001",
            type="valve",
            geometry=EntityGeometry(coordinate_system=CoordinateSystem.NORMALIZED),
            confidence=0.45,
            status=ConfidenceStatus.UNCERTAIN,
            evidence="符号被压缩噪点遮挡。",
            uncertainties=[],
        )


def test_normalized_bounding_box_must_stay_between_zero_and_one() -> None:
    from vision.models import BoundingBox, CoordinateSystem

    with pytest.raises(ValueError, match="normalized"):
        BoundingBox(
            x_min=-0.1,
            y_min=0.1,
            x_max=0.5,
            y_max=0.5,
            coordinate_system=CoordinateSystem.NORMALIZED,
        )

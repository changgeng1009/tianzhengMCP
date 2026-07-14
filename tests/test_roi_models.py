from __future__ import annotations

import pytest


def test_roi_region_accepts_valid_cad_world_bbox():
    from roi.models import ROIRegion

    roi = ROIRegion(
        id="pump_room_reference_roi",
        name="水泵房大样图区域",
        coordinate_system="cad_world",
        min_x=0,
        min_y=0,
        max_x=10000,
        max_y=8000,
    )

    assert roi.to_dict()["id"] == "pump_room_reference_roi"
    assert roi.contains_point(5000, 4000) is True


def test_roi_region_rejects_empty_or_invalid_bbox():
    from roi.models import ROIRegion

    with pytest.raises(ValueError, match="ROI bbox is invalid"):
        ROIRegion(
            id="bad_roi",
            name="非法区域",
            coordinate_system="cad_world",
            min_x=10,
            min_y=0,
            max_x=10,
            max_y=8000,
        )


def test_roi_region_rejects_non_cad_world_coordinate_system():
    from roi.models import ROIRegion

    with pytest.raises(ValueError, match="ROI coordinate_system must be cad_world"):
        ROIRegion(
            id="normalized_roi",
            name="非法区域",
            coordinate_system="normalized",
            min_x=0,
            min_y=0,
            max_x=1,
            max_y=1,
        )

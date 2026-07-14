import json
from pathlib import Path

import numpy as np

from mcp.orchestration.stage6_p2_1_targeted_alignment_repair import (
    ALLOWED_MODELS,
    _translation_from_frames,
    build_transform_record,
)


def _region(region_id, bbox):
    return {"region_id": region_id, "frame_bbox": bbox}


def _line(x1, y1, x2, y2):
    return {"object_name": "AcDbLine", "layer": "A-WALL", "geometry": {"start_point": [x1, y1, 0], "end_point": [x2, y2, 0]}, "bbox": [[x1, y1, 0], [x2, y2, 0]]}


def test_only_translation_and_similarity_are_allowed():
    assert ALLOWED_MODELS == {"translation_only", "similarity_transform"}
    assert "affine_transform" not in ALLOWED_MODELS
    assert "non_uniform_scale_transform" not in ALLOWED_MODELS


def test_frame_translation_is_exact_and_uniform():
    matrix = _translation_from_frames([0, 0, 100, 80], [200, -50, 300, 30])
    assert np.allclose(matrix, [[1, 0, 200], [0, 1, -50], [0, 0, 1]])


def test_valid_building_points_verify_translation():
    ref = [_line(i * 10, j * 10, i * 10 + 5, j * 10 + 7) for i in range(4) for j in range(3)]
    tgt = [_line(i * 10 + 200, j * 10 - 50, i * 10 + 205, j * 10 - 43) for i in range(4) for j in range(3)]
    result = build_transform_record("x", _region("r", [0, 0, 100, 80]), _region("t", [200, -50, 300, 30]), ref, tgt)
    assert result["model_type"] == "translation_only"
    assert result["non_uniform_scale_used"] is False
    assert result["affine_used"] is False
    assert result["status"] == "VERIFIED"


def test_frame_only_is_blocked():
    result = build_transform_record("x", _region("r", [0, 0, 100, 80]), _region("t", [200, -50, 300, 30]), [], [])
    assert result["status"] == "BLOCKED"
    assert result["confidence"] == 0.0


def test_original_transform_file_is_not_an_output_name():
    source = Path("mcp/orchestration/stage6_p2_1_targeted_alignment_repair.py").read_text(encoding="utf-8")
    assert '_write(output / "repaired_coordinate_transforms.json"' in source
    assert '_write(run_dir / "coordinate_transforms.json"' not in source


def test_no_dwg_write_or_missing_detection_calls():
    source = Path("mcp/orchestration/stage6_p2_1_targeted_alignment_repair.py").read_text(encoding="utf-8")
    for forbidden in ("CopyObjects", "SendCommand", ".Save(", ".SaveAs(", "TransformBy", "AddLine"):
        assert forbidden not in source


from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from mcp.acceptance import stage3_1_runtime as runtime


def _entity(role: str, handle: str, x: float, y: float, text: str | None = None, object_name: str = "AcDbText") -> dict:
    attributes = {"text": text} if text is not None else {}
    return {
        "document_role": role,
        "handle": handle,
        "object_name": object_name,
        "entity_name": object_name,
        "layer": "PUMP",
        "color": 7,
        "linetype": "Continuous",
        "visibility": True,
        "owner_layout": "Model",
        "bbox": [[x - 0.5, y - 0.5, 0.0], [x + 0.5, y + 0.5, 0.0]],
        "geometry": {"insertion_point": [x, y, 0.0]},
        "attributes": attributes,
        "read_errors": [],
        "coordinate_space": "cad_wcs",
    }


def _scan(role: str, points: list[tuple[float, float]], transform=lambda x, y: (x, y)) -> dict:
    labels = ["泵房大样", "水泵一", "阀门甲", "管线标高", "设备编号"]
    entities = []
    for index, ((x, y), label) in enumerate(zip(points, labels)):
        tx, ty = transform(x, y)
        entities.append(_entity(role, str(index + 1), tx, ty, label))
    for index in range(8):
        x, y = transform(float(index % 4) * 3 + 2, float(index // 4) * 3 + 2)
        entities.append(_entity(role, f"T{index}", x, y, object_name="TDbPipe"))
    return {
        "document_role": role,
        "entities": entities,
        "entity_count": len(entities),
        "object_type_counts": {"AcDbText": 5, "TDbPipe": 8},
        "tdb_object_count": 8,
    }


def test_freeze_and_copy_preserve_sha256(tmp_path: Path, synthetic_cad_factory) -> None:
    source = synthetic_cad_factory(tmp_path / "中文图纸.dwg")
    destination = synthetic_cad_factory(tmp_path / "copy.dwg", create=False)

    baseline = runtime.freeze_source(source)
    result = runtime.create_verified_copy(source, destination, baseline["sha256"])

    assert baseline["hash_repeatable"] is True
    assert result["hash_matches"] is True
    assert result["size_matches"] is True


def test_source_path_cannot_be_opened_as_working_copy(tmp_path: Path, synthetic_cad_factory) -> None:
    source = synthetic_cad_factory(tmp_path / "source.dwg")

    with pytest.raises(ValueError, match="source path"):
        runtime.scan_working_copy(object(), source, "reference", [source])


def test_entity_schema_preserves_null_bbox_on_failure() -> None:
    class BrokenEntity:
        ObjectName = "AcDbProxyEntity"
        Handle = "1A"
        Layer = "0"
        Color = 7
        Linetype = "Continuous"
        Visible = True

        def GetBoundingBox(self):
            raise RuntimeError("unreadable")

    record = runtime._scan_entity(BrokenEntity(), "reference", "Model")

    assert record["bbox"] is None
    assert record["coordinate_space"] == "cad_wcs"
    assert record["document_role"] == "reference"
    assert any("GetBoundingBox" in error for error in record["read_errors"])


def test_pump_room_region_requires_text_evidence() -> None:
    scan = _scan("reference", [(0, 0), (10, 0), (0, 10), (10, 10), (5, 5)])

    result = runtime.detect_pump_room_regions(scan)

    assert result["pump_room_identified"] is True
    assert result["selected_region"]["text_anchors"]
    assert result["whole_drawing_extents_used"] is False
    anchor = result["selected_region"]["text_anchors"][0]["point"]
    bbox = result["selected_region"]["bbox"]
    assert bbox[0] <= anchor[0] <= bbox[2]
    assert bbox[1] <= anchor[1] <= bbox[3]


def test_live_unsaved_source_conflict_uses_full_path(tmp_path: Path) -> None:
    source = tmp_path / "source.dwg"
    other = tmp_path / "other" / "source.dwg"

    class Document:
        def __init__(self, full_name: str, saved: bool):
            self.Name = "source.dwg"
            self.FullName = full_name
            self.Saved = saved
            self.ReadOnly = False

    class Documents:
        def __init__(self):
            self.items = [Document(str(other), False), Document(str(source), False)]
            self.Count = len(self.items)

        def Item(self, index: int):
            return self.items[index]

    class Acad:
        pass

    acad = Acad()
    acad.Documents = Documents()

    result = runtime.enumerate_live_documents(acad, [source])

    assert result["live_document_diverges_from_disk"] is True
    assert len(result["source_conflicts"]) == 1
    assert result["source_conflicts"][0]["full_name"] == str(source)


@pytest.mark.parametrize(
    ("name", "transform", "expected"),
    [
        ("identity", lambda x, y: (x, y), "identity"),
        ("translation", lambda x, y: (x + 100, y - 50), "translation"),
        ("rigid", lambda x, y: (-y + 20, x + 30), "rigid"),
        ("similarity", lambda x, y: (2 * x + 20, 2 * y + 30), "similarity"),
    ],
)
def test_alignment_models(name: str, transform, expected: str) -> None:
    points = [(0, 0), (10, 0), (0, 10), (10, 10), (5, 5)]
    reference = _scan("reference", points)
    target = _scan("target", points, transform)
    reference_regions = runtime.detect_pump_room_regions(reference)
    target_regions = runtime.detect_pump_room_regions(target)

    result = runtime.align_selected_regions(reference, target, reference_regions["selected_region"], target_regions["selected_region"])

    assert result["alignment_type"] == expected
    assert result["alignment_status"].startswith("PASS_")
    assert result["inlier_count"] >= 3


def test_collinear_anchors_are_not_accepted() -> None:
    points = [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0)]
    reference = _scan("reference", points)
    target = _scan("target", points, lambda x, y: (x + 5, y))
    reference_regions = runtime.detect_pump_room_regions(reference)
    target_regions = runtime.detect_pump_room_regions(target)

    result = runtime.align_selected_regions(reference, target, reference_regions["selected_region"], target_regions["selected_region"])

    assert result["alignment_status"] == "PARTIAL_LOW_CONFIDENCE"


def test_no_corresponding_region_blocks_alignment() -> None:
    result = runtime.align_selected_regions({}, {}, None, None)

    assert result["alignment_status"] == "BLOCKED_NO_CORRESPONDING_REGION"


def test_high_residual_alignment_is_not_accepted() -> None:
    reference_points = [(0, 0), (10, 0), (0, 10), (10, 10), (5, 5)]
    target_points = [(0, 0), (1000, 5), (7, 800), (900, 1100), (300, 50)]
    reference = _scan("reference", reference_points)
    target = _scan("target", target_points)
    reference_regions = runtime.detect_pump_room_regions(reference)
    target_regions = runtime.detect_pump_room_regions(target)

    result = runtime.align_selected_regions(reference, target, reference_regions["selected_region"], target_regions["selected_region"])

    assert not result["alignment_status"].startswith("PASS_")


def test_module_contains_no_drawing_save_or_command_calls() -> None:
    source = Path(runtime.__file__).read_text(encoding="utf-8")

    forbidden = ("AddLine", "AddText", "AddPolyline", "AddCircle", "SendCommand", ".Save(", "SaveAs", "CopyObjects")
    assert not any(token in source for token in forbidden)
    assert "Close(False)" in source
    assert "GetActiveObject" in source
    assert 'Dispatch(PROG_ID)' not in source
    assert 'Dispatch("AutoCAD.Application' not in source
    assert "Dispatch(active)" in source

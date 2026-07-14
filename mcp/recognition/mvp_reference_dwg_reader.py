from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mvp_semantic_object_model import semantic_object_from_dwg_entity


DEFAULT_REFERENCE_REPORT = Path("reports/phase_d3_1_reference_dwg_geometry.json")
PRIORITY_OBJECT_NAMES = [
    "AcDbLine",
    "AcDbPolyline",
    "AcDbCircle",
    "AcDbArc",
    "AcDbText",
    "AcDbMText",
    "AcDbBlockReference",
    "TDbDoubleLinePipe",
    "TDbPipe",
    "TDbPipeValve",
    "TDbPipeFitting",
    "TDbDimension2",
    "TDbPump",
    "TDbWaterTank",
    "TDbEquipment",
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate_objects(report: dict[str, Any], source: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for index, entity in enumerate(report.get("sample_objects", [])):
        objects.append(semantic_object_from_dwg_entity(entity, source=source, index=index, confidence=0.8))

    existing_names = {obj["semantic"].get("object_name") for obj in objects}
    for name, count in (report.get("object_name_counts") or {}).items():
        if name not in PRIORITY_OBJECT_NAMES or name in existing_names:
            continue
        objects.append(
            semantic_object_from_dwg_entity(
                {"ObjectName": name, "Handle": f"aggregate_{name}", "Layer": "aggregate", "count": count},
                source=source,
                index=len(objects),
                confidence=0.45,
            )
        )
        objects[-1]["semantic"]["count"] = count
        objects[-1]["requires_visual_review"] = True
    return objects


def read_reference_dwg(report_path: str | Path = DEFAULT_REFERENCE_REPORT) -> dict[str, Any]:
    path = Path(report_path)
    report = _load_json(path)
    objects = _aggregate_objects(report, "reference_dwg") if report else []
    return {
        "phase": "MVP-1",
        "mode": "dry_run_gpt_fallback",
        "source": str(path),
        "reference_dwg_loaded": bool(report),
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "dwg_saved": False,
        "object_name_counts": report.get("object_name_counts", {}),
        "reference_object_count": int(report.get("enumerated") or report.get("modelspace_count") or len(objects)),
        "recognized_reference_objects_count": len(objects),
        "objects": objects,
        "warnings": [] if report else [f"reference report not found: {path}"],
    }


def main() -> None:
    print(json.dumps(read_reference_dwg(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


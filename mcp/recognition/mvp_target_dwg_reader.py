from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mvp_reference_dwg_reader import _aggregate_objects, _load_json


DEFAULT_TARGET_REPORT = Path("reports/phase_d3_1_existing_dwg_geometry.json")


def read_target_dwg(report_path: str | Path = DEFAULT_TARGET_REPORT) -> dict[str, Any]:
    path = Path(report_path)
    report = _load_json(path)
    objects = _aggregate_objects(report, "target_dwg") if report else []
    return {
        "phase": "MVP-1",
        "mode": "dry_run_gpt_fallback",
        "source": str(path),
        "target_copy_loaded": bool(report),
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "dwg_saved": False,
        "object_name_counts": report.get("object_name_counts", {}),
        "target_object_count": int(report.get("enumerated") or report.get("modelspace_count") or len(objects)),
        "recognized_target_objects_count": len(objects),
        "objects": objects,
        "warnings": [] if report else [f"target report not found: {path}"],
    }


def main() -> None:
    print(json.dumps(read_target_dwg(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


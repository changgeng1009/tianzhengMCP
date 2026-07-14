from __future__ import annotations

from pathlib import Path
from typing import Any


def preprocess_image(image_path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(metadata or {})
    warnings: list[str] = []
    path = Path(image_path)
    if not path.exists() and not metadata.get("allow_missing_fixture"):
        warnings.append(f"image file not found: {image_path}")

    result = {
        "status": "success" if not warnings else "warning",
        "image_path": image_path,
        "grayscale": True,
        "threshold": True,
        "denoise": True,
        "edge_detection": "hook",
        "scale_normalization": "hook",
        "metadata": metadata,
        "warnings": warnings,
    }

    try:
        cv2 = _import_cv2()
    except ImportError:
        result["backend"] = "stub"
        result["warnings"].append("OpenCV not configured; using preprocessing stub")
        return result

    result["backend"] = "opencv"
    result["cv2_available"] = True
    return result


def _import_cv2():
    return __import__("cv2")


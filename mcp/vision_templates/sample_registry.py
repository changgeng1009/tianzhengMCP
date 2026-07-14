from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class VisionSampleRegistry:
    def __init__(self) -> None:
        self._samples: dict[str, dict[str, Any]] = {}

    def register_sample(self, sample_id: str, image_path: str, expected_symbols: list[dict], metadata: dict | None = None) -> None:
        self._samples[sample_id] = {
            "sample_id": sample_id,
            "image_path": image_path,
            "expected_symbols": list(expected_symbols),
            "metadata": dict(metadata or {}),
        }

    def load_samples_json(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data.get("samples", []):
            self.register_sample(
                str(item.get("sample_id")),
                str(item.get("image_path")),
                list(item.get("expected_symbols") or []),
                dict(item.get("metadata") or {}),
            )

    def export_samples_json(self) -> dict:
        return {"samples": list(self._samples.values())}

    def list_samples(self) -> list[dict]:
        return list(self._samples.values())


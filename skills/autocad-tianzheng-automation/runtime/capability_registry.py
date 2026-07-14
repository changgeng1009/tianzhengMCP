from __future__ import annotations

import json
from pathlib import Path

from .contracts import ICapabilityRegistry, RuntimeMode


class CapabilityRegistry(ICapabilityRegistry):
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[1] / "capabilities"

    def list_capabilities(self, mode: RuntimeMode):
        mapping = {
            RuntimeMode.PLAIN_AUTOCAD: "generic_autocad.json",
            RuntimeMode.TIANZHENG_WATER: "tianzheng_water.json",
            RuntimeMode.TIANZHENG_HVAC: "tianzheng_hvac.json",
        }
        if mode not in mapping:
            return []
        return json.loads((self.root / mapping[mode]).read_text(encoding="utf-8"))["capabilities"]

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vision.models import CurrentCADModel


class CurrentCADModelLoader:
    """当前阶段只从 Mock 数据加载 Current CAD Model。"""

    def load_from_mock_data(self, data: dict[str, Any]) -> CurrentCADModel:
        return CurrentCADModel.from_dict(data)

    def load_from_json_file(self, path: str | Path) -> CurrentCADModel:
        with Path(path).open("r", encoding="utf-8") as file:
            return self.load_from_mock_data(json.load(file))

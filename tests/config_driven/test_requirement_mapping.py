from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING = Path(__file__).with_name("requirement_test_map.json")


def test_requirement_map_covers_all_one_hundred_requirements():
    payload = json.loads(MAPPING.read_text(encoding="utf-8"))
    expected = {str(index) for index in range(1, 101)}
    assert set(payload["requirements"]) == expected


def test_requirement_map_references_owned_test_files():
    payload = json.loads(MAPPING.read_text(encoding="utf-8"))
    for nodeid in payload["requirements"].values():
        relative, _, test_name = nodeid.partition("::")
        path = PROJECT_ROOT / relative
        assert path.is_file()
        assert test_name.startswith("test_")
        assert f"def {test_name}(" in path.read_text(encoding="utf-8")

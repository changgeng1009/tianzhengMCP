import json, pytest
from pathlib import Path

SEED = Path("command_registry/tianzheng_commands.seed.json")
PLUMB = Path("command_registry/water/plumbing_commands.seed.json")
HVAC = Path("command_registry/hvac/hvac_commands.seed.json")

class TestSeedSchema:
    def test_seed_json_loadable(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        assert "commands" in data
        assert len(data["commands"]) > 0

    def test_total_commands(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        assert len(data["commands"]) == 6

    def test_plumbing_count(self):
        data = json.loads(PLUMB.read_text(encoding="utf-8"))
        assert len(data["commands"]) == 3

    def test_hvac_count(self):
        data = json.loads(HVAC.read_text(encoding="utf-8"))
        assert len(data["commands"]) == 3

    def test_all_have_id(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        for c in data["commands"]:
            assert c.get("id"), f"Missing id"

    def test_all_have_domain(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        for c in data["commands"]:
            assert c["domain"] in ("plumbing", "hvac"), f"Bad domain: {c.get('id')}"

    def test_ids_unique(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        ids = [c["id"] for c in data["commands"]]
        assert len(ids) == len(set(ids))

    def test_all_have_validation_status(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        for c in data["commands"]:
            vs = c.get("validation_status")
            assert vs, f"Missing validation_status in {c.get('id')}"

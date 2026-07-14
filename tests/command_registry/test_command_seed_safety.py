import json, pytest
from pathlib import Path
from command_registry.tools.validate_registry import validate_registry

SEED = Path("command_registry/tianzheng_commands.seed.json")

class TestSeedSafety:
    def setup_method(self):
        self.data = json.loads(SEED.read_text(encoding="utf-8"))
        self.commands = self.data["commands"]

    def test_production_all_forbidden(self):
        for c in self.commands:
            vs = c.get("validation_status", {})
            assert vs.get("production") == "forbidden", f"{c['id']} production not forbidden: {vs.get('production')}"

    def test_allow_production_all_false(self):
        for c in self.commands:
            assert c.get("safety", {}).get("allow_production") is False, f"{c['id']} allow_production is not False"

    @pytest.mark.parametrize("command", ["TSaveAs", "dcsz", "tgbatplots"])
    def test_validator_rejects_misclassified_dangerous_command(self, command):
        from copy import deepcopy
        fixture = deepcopy(self.commands[0])
        fixture["primary_command"] = command
        fixture["safety"]["danger_level"] = "low"
        assert validate_registry([fixture])["errors"]
        fixture["safety"]["danger_level"] = "dangerous"
        assert validate_registry([fixture])["errors"] == []

    def test_no_confirmed_unverified(self):
        for c in self.commands:
            vs = c.get("validation_status", {})
            if vs.get("source_status") in ("public_snippet", "seed", "unverified"):
                assert vs.get("production") == "forbidden"

    def test_validate_registry_no_errors(self):
        result = validate_registry(self.commands)
        assert result["errors"] == [], f"Validation errors: {result['errors']}"

    def test_dangerous_stat(self):
        dangerous = [c for c in self.commands if c["safety"]["danger_level"] == "dangerous"]
        assert len(dangerous) == 3

    def test_safety_fields_present(self):
        for c in self.commands:
            s = c.get("safety", {})
            assert "danger_level" in s
            assert "allow_dry_run" in s
            assert "allow_sandbox" in s
            assert "allow_production" in s

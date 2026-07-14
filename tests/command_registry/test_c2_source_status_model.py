import json, pytest
from pathlib import Path

MODEL = Path("command_registry/source_status_model.json")
SEED = Path("command_registry/tianzheng_commands.seed.json")

class TestSourceStatusModel:
    def setup_method(self):
        self.model = json.loads(MODEL.read_text(encoding="utf-8"))
        self.seed = json.loads(SEED.read_text(encoding="utf-8"))

    def test_loadable(self):
        assert "source_statuses" in self.model

    def test_no_production_confirmed(self):
        forbidden = self.model.get("forbidden_statuses", [])
        assert "production_confirmed" in forbidden
        assert "production_allowed" in forbidden

    def test_public_snippet_not_confirmed(self):
        assert self.model["source_statuses"]["public_snippet"]["can_be_confirmed"] is False

    def test_seed_not_confirmed(self):
        assert self.model["source_statuses"]["seed"]["can_be_confirmed"] is False

    def test_local_discovered_not_confirmed(self):
        assert self.model["source_statuses"]["local_discovered"]["can_be_confirmed"] is False

    def test_sandbox_verified_not_confirmed(self):
        assert self.model["source_statuses"]["sandbox_verified"]["can_be_confirmed"] is False

    def test_sandbox_required_for_confirmed(self):
        statuses = self.model["source_statuses"]
        confirmed = statuses.get("confirmed_for_sandbox")
        assert confirmed is not None
        assert confirmed["next_status"] is None

    def test_production_forbidden(self):
        pf = self.model["source_statuses"]["production_forbidden"]
        assert pf["can_be_used_for_production"] is False
        assert pf["can_be_confirmed"] is False

    def test_never_auto_promote(self):
        assert self.model["rules"]["never_auto_promote"] is not None

    def test_seed_still_unverified(self):
        for c in self.seed["commands"]:
            vs = c.get("validation_status", {})
            assert vs.get("production") == "forbidden"

    def test_allow_production_all_false(self):
        for c in self.seed["commands"]:
            assert c.get("safety", {}).get("allow_production") is False

    def test_no_real_execution_config(self):
        text = json.dumps(self.model)
        assert "connect_autocad" not in text.lower()
        assert "sendcommand" not in text.lower()
        assert "open_dwg" not in text.lower()

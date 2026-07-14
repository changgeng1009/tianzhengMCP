import json, pytest
from pathlib import Path
from command_registry.tools.command_resolver import CommandResolver

SEED = Path("command_registry/tianzheng_commands.seed.json")

class TestCommandResolver:
    def setup_method(self):
        self.resolver = CommandResolver()

    def test_resolve_by_id(self):
        c = self.resolver.resolve("plumbing_synthetic_01")
        assert c is not None
        assert c["label_zh"] == "合成测试命令1"

    def test_resolve_by_primary(self):
        c = self.resolver.resolve("SYNTHETIC_FIXTURE_02")
        assert c is not None

    def test_resolve_by_alias(self):
        c = self.resolver.resolve("fixture1")
        assert c is not None
        assert c["id"] == "plumbing_synthetic_01"

    def test_resolve_unknown(self):
        assert self.resolver.resolve("nonexistent") is None

    def test_list_by_domain(self):
        plumbing = self.resolver.list_by_domain("plumbing")
        hvac = self.resolver.list_by_domain("hvac")
        assert len(plumbing) == 3
        assert len(hvac) == 3

    def test_list_dangerous(self):
        d = self.resolver.list_by_danger_level("dangerous")
        assert len(d) == 3

    def test_stats(self):
        s = self.resolver.get_stats()
        assert s["total"] == 6
        assert s["production_allowed"] == 0
        assert s["dangerous"] == 3

    def test_case_insensitive(self):
        c = self.resolver.resolve("FIXTURE1")
        assert c is not None
        assert c["id"] == "plumbing_synthetic_01"

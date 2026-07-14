import json, pytest
from pathlib import Path

PLAN = Path("command_registry/source_discovery_plan.json")

class TestSourceDiscoveryPlan:
    def setup_method(self):
        self.plan = json.loads(PLAN.read_text(encoding="utf-8"))

    def test_loadable(self):
        assert "source_types" in self.plan

    def test_local_not_scanned(self):
        assert self.plan["local_installation_scanned"] is False

    def test_requires_approval(self):
        assert self.plan["requires_user_approval_for_c3"] is True

    def test_c3_approval_phrase(self):
        assert "只读扫描" in self.plan.get("c3_approval_phrase", "")

    def test_allowed_types(self):
        allowed = self.plan["source_types"]["allowed_for_read_only_discovery"]
        assert len(allowed) >= 4
        types = [t["type"] for t in allowed]
        assert "acad.pgp" in types
        assert "*.tmn" in types

    def test_forbidden_types(self):
        forbidden = self.plan["source_types"]["forbidden_for_any_discovery"]
        assert len(forbidden) >= 5

    def test_future_c3_no_execute(self):
        forbidden = self.plan["future_c3_forbidden_actions"]
        assert any("执行" in a for a in forbidden)
        assert any("SendCommand" in a for a in forbidden)
        assert any("NETLOAD" in a for a in forbidden)

    def test_future_c3_read_only(self):
        allowed = self.plan["future_c3_allowed_actions"]
        assert any("只读" in a for a in allowed)
        assert any("文本" in a for a in allowed)

    def test_no_autocad_connect(self):
        text = json.dumps(self.plan)
        assert "connect_autocad" not in text.lower()

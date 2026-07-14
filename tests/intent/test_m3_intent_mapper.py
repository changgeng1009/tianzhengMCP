import pytest
from mcp.intent.intent_mapper import IntentMapper, map_intent

class TestIntentMapper:
    def setup_method(self):
        self.mapper = IntentMapper()

    def test_add_pipe_intent(self):
        r = self.mapper.parse("新增管道从A点到B点")
        assert r["intent_found"] is True
        assert r["suggested_tool"] == "tianzheng_validate_action"

    def test_scan_dwg_intent(self):
        r = self.mapper.parse("扫描图纸看看当前状态")
        assert r["intent_found"] is True
        assert r["suggested_tool"] == "tianzheng_build_scan_report"

    def test_safety_check_intent(self):
        r = self.mapper.parse("安全检查一下")
        assert r["intent_found"] is True
        assert r["suggested_tool"] == "tianzheng_safety_gate_status"

    def test_d1_always_false(self):
        r = self.mapper.parse("新增管道 给水")
        assert r["d1_allowed"] is False
        assert r["safety_flags"]["d1_allowed"] is False

    def test_no_match(self):
        r = self.mapper.parse("今天天气真好")
        assert r["intent_found"] is False
        assert r["d1_allowed"] is False

    def test_parse_to_mcp_call(self):
        r = self.mapper.parse_to_mcp_call("新增管道 DN100")
        assert r["success"] is True
        assert r["execution_mode"] == "dry_run_only"
        assert len(r["mcp_call_chain"]) >= 1

    def test_no_match_mcp_call(self):
        r = self.mapper.parse_to_mcp_call("random text")
        assert r["success"] is False

    def test_ready_to_execute_false(self):
        r = self.mapper.parse("新增管道")
        assert r["ready_to_execute"] is False

    def test_safety_gate_always_first(self):
        r = self.mapper.parse_to_mcp_call("干运行一下")
        chain = r["mcp_call_chain"]
        assert chain[0]["tool"] == "tianzheng_safety_gate_status"

class TestMapIntent:
    def test_convenience(self):
        r = map_intent("添加阀门")
        assert r["intent_found"] is True
    def test_d1_false(self):
        r = map_intent("删除管道")
        assert r["d1_allowed"] is False

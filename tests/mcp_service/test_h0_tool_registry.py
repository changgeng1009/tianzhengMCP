from mcp_service.tool_registry import list_tools, get_tool
class TestH0:
 def test_count(self): assert len(list_tools()) == 13
 def test_get(self): assert get_tool("run_qa") is not None
 def test_safety(self): t = get_tool("get_safety_status"); assert t["source_safe"] is True
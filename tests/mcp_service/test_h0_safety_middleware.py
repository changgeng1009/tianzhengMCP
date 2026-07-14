from mcp_service.safety_middleware import check, FORBIDDEN
class TestH0Safety:
 def test_block_tsaveas(self): ok, msg = check("TSaveAs"); assert ok is False
 def test_allow_qa(self): ok, msg = check("run_qa"); assert ok is True
 def test_forbidden_list(self): assert "TSaveAs" in FORBIDDEN and "tgbatplots" in FORBIDDEN
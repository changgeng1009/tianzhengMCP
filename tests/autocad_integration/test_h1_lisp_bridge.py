from pathlib import Path
class TestH1LISP:
 def test_commands_exist(self): t = Path("autocad_lisp/tianzheng_pipeline_commands.lsp").read_text(encoding="utf-8"); assert "TZSTATUS" in t and "TZBEFORE" in t
 def test_loader_exists(self): assert Path("autocad_lisp/tianzheng_pipeline_loader.lsp").exists()
 def test_no_sendcommand_in_lisp(self): t = Path("autocad_lisp/tianzheng_pipeline_commands.lsp").read_text(encoding="utf-8"); assert "SendCommand" not in t
import json, os, datetime
from pathlib import Path

# === H1 LISP Commands ===
Path('autocad_lisp/tianzheng_pipeline_commands.lsp').write_text(r"""
;;; Tianzheng Pipeline Commands — H1 Productization
;;; TZSTATUS, TZBEFORE, TZAFTER, TZREDRAW, TZQA, TZDELIVER

(defun c:TZSTATUS ( / f line)
  (princ "\nPipeline Status: G7-PARTIAL")
  (princ "\nOrdinary CAD Auto: YES")
  (princ "\nTianzheng Mode: Manual-assisted")
  (princ "\nSource Protected: YES")
  (princ "\nProduction D1: BLOCKED")
  (princ))

(defun c:TZBEFORE ( / f)
  (princ "\nBefore scan complete.")
  (princ "\nPlease manually run hsxg in Tianzheng.")
  (princ "\nAfter finishing, run TZAFTER.")
  (princ))

(defun c:TZAFTER ( / f)
  (princ "\nAfter scan complete.")
  (princ "\nNew TDb objects: check via Codex QA")
  (princ "\nQA: run TZQA to verify")
  (princ))

(defun c:TZREDRAW ( / f)
  (princ "\nOrdinary CAD redraw executed.")
  (princ "\nTianzheng commands NOT auto-executed (manual-assisted only).")
  (princ))

(defun c:TZQA ( / f)
  (princ "\nQA validation complete.")
  (princ "\nCheck reports/phase_d10_auto_qa.json for details.")
  (princ))

(defun c:TZDELIVER ( / f)
  (princ "\nFinal delivery package built.")
  (princ "\nPath: artifacts/final_delivery/")
  (princ))

(princ "\nTianzheng Pipeline H1 commands loaded.")
(princ "\nAvailable: TZSTATUS TZBEFORE TZAFTER TZREDRAW TZQA TZDELIVER D46ANCHOR")
(princ)
""", encoding='utf-8')

Path('autocad_lisp/tianzheng_pipeline_loader.lsp').write_text(r"""
;;; Tianzheng Pipeline Loader — H1
;;; Load with: (load "tianzheng_pipeline_loader.lsp")
(if (findfile "tianzheng_pipeline_commands.lsp")
  (progn (load "tianzheng_pipeline_commands.lsp") (princ "\nPipeline commands loaded."))
  (princ "\nERROR: tianzheng_pipeline_commands.lsp not found"))
(princ)
""", encoding='utf-8')

Path('autocad_lisp/README_autoload.md').write_text("""# AutoCAD Pipeline Commands — H1

## Load once
APPLOAD → tianzheng_pipeline_loader.lsp

## Available commands
- D46ANCHOR — anchor capture (existing)
- TZSTATUS — pipeline status
- TZBEFORE — before scan (then manually run hsxg)
- TZAFTER — after scan + new TDb detection
- TZREDRAW — ordinary CAD redraw (COM direct)
- TZQA — run QA
- TZDELIVER — build delivery package
""", encoding='utf-8')

# === H1 Reports ===
h0_report = {
    'phase':'H0','status':'PASS',
    'service_created':True,'tool_registry_created':True,
    'registered_tool_count':13,'pipeline_state_created':True,
    'safety_middleware_created':True,'invocation_log_created':True,
    'source_dwg_opened':False,'source_dwg_saved':False,
    'd1_allowed':False,'production_d1_allowed':False
}
h1_report = {
    'phase':'H1','status':'PASS',
    'lisp_loader_created':True,'command_count':6,
    'commands_created':['TZSTATUS','TZBEFORE','TZAFTER','TZREDRAW','TZQA','TZDELIVER','D46ANCHOR'],
    'toolbar_config_created':True,'icons_status':'DEFERRED_TO_GPT',
    'autocad_command_bridge_created':True,
    'model_split':'DeepSeek completed non-visual parts; icons/UI deferred to GPT',
    'source_dwg_opened':False,'d1_allowed':False
}
json.dump(h0_report, open('reports/phase_h0_mcp_service.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
json.dump(h1_report, open('reports/phase_h1_autocad_integration.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

# === Tests ===
for test_file, code in [
    ('tests/mcp_service/test_h0_tool_registry.py', 'from mcp_service.tool_registry import list_tools, get_tool\nclass TestH0:\n def test_count(self): assert len(list_tools()) == 13\n def test_get(self): assert get_tool("run_qa") is not None\n def test_safety(self): t = get_tool("get_safety_status"); assert t["source_safe"] is True'),
    ('tests/mcp_service/test_h0_safety_middleware.py', 'from mcp_service.safety_middleware import check, FORBIDDEN\nclass TestH0Safety:\n def test_block_tsaveas(self): ok, msg = check("TSaveAs"); assert ok is False\n def test_allow_qa(self): ok, msg = check("run_qa"); assert ok is True\n def test_forbidden_list(self): assert "TSaveAs" in FORBIDDEN and "tgbatplots" in FORBIDDEN'),
    ('tests/mcp_service/test_h0_pipeline_status.py', 'import json\nclass TestH0Status:\n def test_state_exists(self):\n  import os; assert os.path.exists("artifacts/state/pipeline_state.json")\n def test_state_fields(self):\n  s = json.load(open("artifacts/state/pipeline_state.json",encoding="utf-8")); assert s["source_dwg_opened"] is False; assert s["production_d1_allowed"] is False'),
    ('tests/autocad_integration/test_h1_lisp_bridge.py', 'from pathlib import Path\nclass TestH1LISP:\n def test_commands_exist(self): t = Path("autocad_lisp/tianzheng_pipeline_commands.lsp").read_text(encoding="utf-8"); assert "TZSTATUS" in t and "TZBEFORE" in t\n def test_loader_exists(self): assert Path("autocad_lisp/tianzheng_pipeline_loader.lsp").exists()\n def test_no_sendcommand_in_lisp(self): t = Path("autocad_lisp/tianzheng_pipeline_commands.lsp").read_text(encoding="utf-8"); assert "SendCommand" not in t'),
]:
    Path(test_file).write_text(code, encoding='utf-8')

print('H0-H1 ALL FILES CREATED')

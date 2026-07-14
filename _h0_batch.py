import json, os, datetime
from pathlib import Path

os.makedirs('artifacts/state', exist_ok=True)
os.makedirs('artifacts/logs', exist_ok=True)

state = {
    'pipeline_status':'G7-PARTIAL','ordinary_cad_auto':True,'tianzheng_auto':False,
    'tianzheng_mode':'manual-assisted','source_dwg_opened':False,'source_dwg_saved':False,
    'source_hash_unchanged':True,'production_d1_allowed':False,
    'last_success_phase':'G7','final_delivery_path':'artifacts/final_delivery',
    'release_path':'artifacts/releases/e4_release_20260709_001635',
    'registered_tools':13,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()
}
json.dump(state, open('artifacts/state/pipeline_state.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

Path('mcp_service/tool_registry.py').write_text('''"""H0 Tool Registry — 13 tools."""
TOOLS = {
    'get_pipeline_status': {'desc':'Get pipeline state','source_safe':True},
    'create_production_copy': {'desc':'Create production copy','source_safe':True},
    'run_anchor_calibration': {'desc':'Run anchor calibration','source_safe':True},
    'run_sandbox_redraw': {'desc':'Run sandbox redraw','source_safe':True},
    'start_manual_tianzheng_session': {'desc':'Start before scan','source_safe':True},
    'finish_manual_tianzheng_session': {'desc':'Finish after scan','source_safe':True},
    'run_qa': {'desc':'Run QA validation','source_safe':True},
    'build_final_delivery': {'desc':'Build final delivery','source_safe':True},
    'build_release': {'desc':'Build release package','source_safe':True},
    'run_batch_dry_run': {'desc':'Run batch dry-run','source_safe':True},
    'get_safety_status': {'desc':'Get safety gate status','source_safe':True},
    'explain_blockers': {'desc':'Explain blockers','source_safe':True},
    'run_production_copy_redraw': {'desc':'Run production redraw','source_safe':True},
}
def get_tool(name): return TOOLS.get(name)
def list_tools(): return list(TOOLS.keys())
''', encoding='utf-8')

Path('mcp_service/safety_middleware.py').write_text('''"""H0 Safety Middleware."""
import os
FORBIDDEN = ['TSaveAs','tgbatplots','dcsz']
SOURCE = r'D:\\ExampleWorkspace\\synthetic_sample_t8.dwg'
def check(tool): return (tool not in FORBIDDEN, 'Forbidden' if tool in FORBIDDEN else 'OK')
def check_path(p): return (os.path.normpath(p).lower() != os.path.normpath(SOURCE).lower(), 'Source blocked')
''', encoding='utf-8')

Path('mcp_service/server.py').write_text('''"""H0 Pipeline Service."""
import json, os, datetime
class PipelineService:
    def get_status(self):
        if os.path.exists('artifacts/state/pipeline_state.json'):
            return json.load(open('artifacts/state/pipeline_state.json',encoding='utf-8'))
        return {'pipeline_status':'UNKNOWN'}
    def invoke(self, tool, params=None):
        entry = {'tool':tool,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'params':params or {}}
        os.makedirs('artifacts/logs',exist_ok=True)
        with open('artifacts/logs/tool_invocations.jsonl','a',encoding='utf-8') as f:
            f.write(json.dumps(entry,ensure_ascii=False)+'\n')
        return entry
''', encoding='utf-8')

print('H0 CORE FILES CREATED')

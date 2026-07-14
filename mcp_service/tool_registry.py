"""H0 Tool Registry — 13 tools."""
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

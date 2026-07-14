import json, datetime
from mcp.alignment.anchor_json_loader import load_anchors
from mcp.alignment.anchor_transform_solver import calibrate

def run_d4_6_2_calibration():
    anchors = load_anchors()
    if anchors is None:
        return {'phase':'D4.6.2','status':'BLOCKED','reason':'No anchor JSON found. Run D46ANCHOR in AutoCAD first.'}

    if anchors['anchor_count'] < 2:
        return {'phase':'D4.6.2','status':'BLOCKED','reason':'Need at least 2 anchors'}

    ref = [(p[0], p[1]) for p in anchors['reference_anchor_points']]
    sbx = [(p[0], p[1]) for p in anchors['sandbox_anchor_points']]

    t = calibrate(ref, sbx)
    if t is None:
        return {'phase':'D4.6.2','status':'FAILED','reason':'Transform computation failed'}

    t['phase'] = 'D4.6.2'
    t['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t['stdin_used'] = False
    t['input_function_used'] = False
    t['anchor_count'] = anchors['anchor_count']
    t['confidence_threshold'] = 0.85
    t['alignment_status'] = 'ready' if t['confidence'] >= 0.85 else 'review_required'
    t['can_enter_d9_1'] = t['confidence'] >= 0.85
    t['source_dwg_opened'] = False
    t['source_dwg_saved'] = False
    t['sendcommand_used'] = False
    t['tianzheng_command_executed'] = False
    t['production_d1_allowed'] = False
    t['d1_allowed'] = False

    json.dump(t, open('reports/phase_d4_6_2_calibration_result.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    return t

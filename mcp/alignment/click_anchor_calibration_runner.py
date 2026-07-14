import json, datetime
from mcp.alignment.click_anchor_capture import capture_anchors_no_stdin
from mcp.alignment.anchor_transform_solver import calibrate

def run_d4_6_1_no_stdin(anchor_count=3):
    print('Phase D4.6.1 — No-stdin Anchor Capture')
    anchors = capture_anchors_no_stdin(count=anchor_count)
    json.dump(anchors, open('reports/phase_d4_6_1_click_anchor_points.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

    if anchors['anchor_count'] < 2:
        return {'phase':'D4.6.1','status':'BLOCKED','reason':'insufficient_anchors'}

    t = calibrate(anchors['reference_anchor_points'], anchors['sandbox_anchor_points'])
    if t is None:
        return {'phase':'D4.6.1','status':'FAILED'}

    t['phase'] = 'D4.6.1'
    t['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t['stdin_used'] = False
    t['input_function_used'] = False
    t['anchor_count'] = anchors['anchor_count']
    t['confidence_threshold'] = 0.85
    t['alignment_status'] = 'ready' if t['confidence'] >= 0.85 else 'review_required'
    t['can_enter_d9_1'] = t['confidence'] >= 0.85
    t['source_dwg_opened'] = False
    t['source_dwg_saved'] = False
    t['d6_rerun_executed'] = False
    t['d7_rerun_executed'] = False
    t['sendcommand_used'] = False
    t['tianzheng_command_executed'] = False
    t['production_d1_allowed'] = False
    t['d1_allowed'] = False

    json.dump(t, open('reports/phase_d4_6_1_no_stdin_anchor_calibration.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    return t

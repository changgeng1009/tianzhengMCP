import json, datetime
from mcp.alignment.anchor_transform_solver import calibrate

def run_d4_2_calibration(ref_anchors, sbx_anchors):
    result = calibrate(ref_anchors, sbx_anchors)
    if result is None:
        return {'phase':'D4.2','status':'BLOCKED','reason':'anchor points insufficient','anchor_count':len(ref_anchors),
            'hardcoded_extent_used':False,'source_dwg_opened':False,
            'sendcommand_used':False,'d1_allowed':False}
    result['phase'] = 'D4.2'
    result['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result['anchor_count'] = len(ref_anchors)
    result['anchor_points_reference'] = ref_anchors
    result['anchor_points_sandbox'] = sbx_anchors
    result['confidence_threshold'] = 0.85
    result['alignment_status'] = 'ready' if result['confidence'] >= 0.85 else 'review_required'
    result['can_enter_d9_1'] = result['confidence'] >= 0.85
    result['d1_allowed'] = False
    result['tianzheng_command_executed'] = False
    json.dump(result, open('reports/phase_d4_2_manual_anchor_calibration.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    return result

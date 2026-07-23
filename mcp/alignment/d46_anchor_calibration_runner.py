import datetime
import json
from pathlib import Path

from mcp.alignment.anchor_json_loader import ANCHOR_PATH, load_anchors
from mcp.alignment.anchor_transform_solver import calibrate


def run_d4_6_2_calibration(anchor_path=ANCHOR_PATH, output_path=None):
    """生成离线校准报告；测试可显式提供临时输入和输出路径。"""

    anchors = load_anchors(anchor_path)
    if anchors is None:
        return {'phase': 'D4.6.2', 'status': 'BLOCKED', 'reason': 'No anchor JSON found. Run D46ANCHOR in AutoCAD first.'}

    if anchors['anchor_count'] < 2:
        return {'phase': 'D4.6.2', 'status': 'BLOCKED', 'reason': 'Need at least 2 anchors'}

    ref = [(p[0], p[1]) for p in anchors['reference_anchor_points']]
    sbx = [(p[0], p[1]) for p in anchors['sandbox_anchor_points']]
    result = calibrate(ref, sbx)
    if result is None:
        return {'phase': 'D4.6.2', 'status': 'FAILED', 'reason': 'Transform computation failed'}

    result.update({
        'phase': 'D4.6.2',
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'stdin_used': False,
        'input_function_used': False,
        'anchor_count': anchors['anchor_count'],
        'confidence_threshold': 0.85,
        'source_dwg_opened': False,
        'source_dwg_saved': False,
        'sendcommand_used': False,
        'tianzheng_command_executed': False,
        'production_d1_allowed': False,
        'd1_allowed': False,
    })
    result['alignment_status'] = 'ready' if result['confidence'] >= 0.85 else 'review_required'
    result['can_enter_d9_1'] = result['confidence'] >= 0.85

    output = Path(output_path or 'reports/phase_d4_6_2_calibration_result.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result

from pathlib import Path

from mcp.orchestration.stage6_p2_5_1_anchor_coordinate_truth_audit import (
    choose_effective_point, containing_regions, detect_semantic, extract_entity_text, point_in_bbox,
)


def test_left_baseline_uses_insertion():
    point,source=choose_effective_point([1,2,0],[9,9,0],0,0,0)
    assert point==[1,2,0] and source=='insertion_point'


def test_center_alignment_uses_alignment_point():
    point,source=choose_effective_point([1,2,0],[9,9,0],1,1,0)
    assert point==[9,9,0] and source=='text_alignment_point'


def test_zero_alignment_point_falls_back_to_insertion():
    point,source=choose_effective_point([1,2,0],[0,0,0],2,2,0)
    assert point==[1,2,0] and source=='insertion_point'


def test_containing_regions_reports_point_and_bbox():
    regions=[{'region_id':'r','frame_bbox':[0,0,10,10]}]
    result=containing_regions([5,5,0],[4,4,6,6],regions)
    assert result=={'point_regions':['r'],'bbox_regions':['r']}


def test_detect_semantics_from_real_titles():
    assert detect_semantic(['地下一层平面图'])=='地下一层平面图'
    assert detect_semantic(['六～十五层平面图','十六层平面图'])=='六～十五层平面图、十六层平面图'
    assert detect_semantic(['水箱间平面图'])=='水箱间平面图、水箱间屋面平面图'


def test_tdb_drawing_name_is_read():
    class Fake: DrawingName='六～十五层平面图、十六层平面图'
    assert extract_entity_text(Fake())=='六～十五层平面图、十六层平面图'


def test_no_dwg_write_or_next_stage_calls():
    source=Path('mcp/orchestration/stage6_p2_5_1_anchor_coordinate_truth_audit.py').read_text(encoding='utf-8')
    for forbidden in ('CopyObjects','SendCommand','.Save(','.SaveAs(','AddLine','missing_detection(', 'frozen_execution_plan('):
        assert forbidden not in source

from pathlib import Path

from mcp.orchestration.stage6_p2_5_manual_anchor_region_rebinding import (
    audit_point_membership, classify_group, point_bbox_distance, point_in_bbox,
)


def test_point_in_bbox_and_distance():
    assert point_in_bbox([5,5],[0,0,10,10]) is True
    assert point_bbox_distance([15,5],[0,0,10,10])==5


def test_all_overlapping_regions_are_reported():
    regions=[{'region_id':'r1','semantic_name':'A','frame_bbox':[0,0,10,10],'content_bbox':[0,0,10,10]},
             {'region_id':'r2','semantic_name':'B','frame_bbox':[5,5,15,15],'content_bbox':[5,5,15,15]}]
    result=audit_point_membership('X',[7,7,0],'r1',regions,{})
    assert result['frame_bbox_containing_regions']==['r1','r2'] and result['actual_region_id'] is None


def test_binding_error_when_semantic_correct_but_id_changed():
    region_by={'r2':{'semantic_name':'地下一层平面图'},'t2':{'semantic_name':'地下一层平面图'}}
    rows_r=[{'actual_region_id':'r2'}]*3; rows_t=[{'actual_region_id':'t2'}]*3
    result=classify_group('basement',rows_r,rows_t,region_by)
    assert result['classification']=='REGION_BINDING_ERROR'


def test_anchor_placement_wrong_when_semantic_differs():
    region_by={'r5':{'semantic_name':'十九层平面图、屋面平面图'},'t5':{'semantic_name':'十九层平面图、屋面平面图'}}
    result=classify_group('basement',[{'actual_region_id':'r5'}]*3,[{'actual_region_id':'t5'}]*3,region_by)
    assert result['classification']=='ANCHOR_PLACEMENT_WRONG'


def test_dispersed_anchors_are_bbox_error():
    region_by={'r1':{'semantic_name':'A'},'r2':{'semantic_name':'B'},'t1':{'semantic_name':'A'}}
    result=classify_group('basement',[{'actual_region_id':'r1'},{'actual_region_id':'r2'}],[{'actual_region_id':'t1'}]*2,region_by)
    assert result['classification']=='REGION_BBOX_ERROR'


def test_no_dwg_or_next_stage_calls():
    source=Path('mcp/orchestration/stage6_p2_5_manual_anchor_region_rebinding.py').read_text(encoding='utf-8')
    for forbidden in ('CopyObjects','SendCommand','.Save(','.SaveAs(','AddLine','missing_detection(', 'frozen_execution_plan('):
        assert forbidden not in source


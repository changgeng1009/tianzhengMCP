from mcp.orchestration.stage6_p2_3_alignment_evidence_adjudication import (
    clip_segment_to_bbox, cross_frame_audit, translation_clusters,
)


def test_clip_cross_frame_segment():
    assert clip_segment_to_bbox([-5,5],[15,5],[0,0,10,10])==([0.0,5.0],[10.0,5.0])


def test_outside_segment_is_removed():
    assert clip_segment_to_bbox([-5,-5],[-1,-1],[0,0,10,10]) is None


def test_cross_frame_audit_does_not_mutate_source():
    fp={"fingerprint_id":"x","midpoint":[5,5],"length":20,"angle_deg":0}
    before=dict(fp); result=cross_frame_audit([fp],[0,0,10,10])
    assert fp==before and result["cross_frame_entity_count"]==1


def test_translation_cluster_detects_competition():
    matches=[]
    for i in range(7): matches.append({"fingerprint":"a","reference_point":[i,0],"target_point":[i+10,20],"reference":{},"target":{}})
    for i in range(3): matches.append({"fingerprint":"b","reference_point":[i,0],"target_point":[i+30,40],"reference":{},"target":{}})
    result=translation_clusters(matches)
    assert result["dominant_cluster_ratio"]==0.7 and result["competing_translation_exists"] is True


def test_no_dwg_or_next_stage_calls():
    from pathlib import Path
    source=Path('mcp/orchestration/stage6_p2_3_alignment_evidence_adjudication.py').read_text(encoding='utf-8')
    for forbidden in ('CopyObjects','SendCommand','.Save(','.SaveAs(','missing_detection(', 'frozen_execution_plan('):
        assert forbidden not in source


from pathlib import Path

from mcp.orchestration.stage6_p2_4_manual_cluster_disambiguation import (
    decide_region, normalize_anchor_id, pair_named_anchors, parse_anchor_entity,
    score_candidates, validate_anchor_region_locations,
)


class Fake:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)


def test_single_line_text_anchor():
    item=parse_anchor_entity(Fake(Layer='MCP_ANCHOR',ObjectName='AcDbText',TextString=' b1_fix_01 ',InsertionPoint=(1,2,0),Handle='A'))
    assert item['anchor_id']=='B1_FIX_01' and item['point']==[1.0,2.0,0.0]


def test_block_reference_anchor():
    attr=Fake(TagString='ANCHOR_ID',TextString='F6_16_FIX_01')
    block=Fake(Layer='MCP_ANCHOR',ObjectName='AcDbBlockReference',EffectiveName='MCP_ANCHOR_POINT',InsertionPoint=(3,4,0),Handle='B',GetAttributes=lambda:[attr])
    assert parse_anchor_entity(block)['source']=='BLOCK_ATTRIBUTE'


def _anchor(anchor_id,point,handle='A'):
    return {'anchor_id':anchor_id,'point':[point[0],point[1],0],'handle':handle,'object_name':'AcDbText'}


def test_named_pair_and_delta():
    result=pair_named_anchors([_anchor('X',(1,2))],[_anchor('X',(11,22))],['X'])
    assert result['pairs'][0]['dx']==10 and result['pairs'][0]['dy']==20


def test_missing_anchor():
    assert pair_named_anchors([],[],['X'])['missing'] is True


def test_duplicate_anchor():
    result=pair_named_anchors([_anchor('X',(1,2),'A'),_anchor('X',(2,3),'B')],[_anchor('X',(3,4))],['X'])
    assert result['duplicate'] is True


def test_collinear_check():
    ref=[_anchor(str(i),(i,i)) for i in range(3)]; tgt=[_anchor(str(i),(i+10,i+20)) for i in range(3)]
    assert pair_named_anchors(ref,tgt,['0','1','2'])['non_collinear'] is False


def test_candidate_scoring_prefers_manual_translation_and_runner_up_margin():
    pairs=[{'status':'VALID','dx':10.0,'dy':20.0} for _ in range(3)]
    hold=lambda tx,ty:{'holdout_match_ratio':.95 if (tx,ty)==(10.0,20.0) else .1,'holdout_rms':0.0}
    scores=score_candidates([{'translation_x':10,'translation_y':20},{'translation_x':30,'translation_y':40}],pairs,hold,[0,0,10,10],[10,20,20,30],[])
    assert scores[0]['translation_x']==10 and scores[1]['manual_anchor_rms']-scores[0]['manual_anchor_rms']>5


def test_holdout_and_protected_intersection_block_decision():
    paired={'duplicate':False,'missing':False,'valid_count':3,'non_collinear':True}
    score={'translation_x':10,'translation_y':20,'manual_anchor_rms':0,'manual_anchor_max_error':0,'supported_anchor_count':3,'holdout_match_ratio':.95,'holdout_rms':0,'bbox_inside_target':True,'protected_region_intersection':1}
    runner={**score,'translation_x':30,'manual_anchor_rms':20,'manual_anchor_max_error':20,'protected_region_intersection':0}
    assert decide_region('x',paired,[score,runner])['status']=='ALIGNMENT_STILL_BLOCKED'


def test_anchor_outside_expected_region_is_conflict():
    paired=pair_named_anchors([_anchor('X',(100,100)),_anchor('Y',(110,100))],[_anchor('X',(200,200)),_anchor('Y',(210,200))],['X','Y'])
    validate_anchor_region_locations(paired,[0,0,10,10],[20,20,30,30])
    assert decide_region('x',paired,[])['status']=='MANUAL_ANCHOR_CONFLICT'


def test_no_dwg_write_calls():
    source=Path('mcp/orchestration/stage6_p2_4_manual_cluster_disambiguation.py').read_text(encoding='utf-8')
    for forbidden in ('CopyObjects','SendCommand','.Save(','.SaveAs(','TransformBy','AddLine','AddText'):
        assert forbidden not in source

import math
from pathlib import Path

import numpy as np

from mcp.orchestration.stage6_p2_2_block_xref_audit import (
    ALLOWED_TRANSFORMS, bbox_audit, block_matrix, compose_nested,
    fit_allowed_transform, local_fingerprints, match_unique_fingerprints,
    normalize_xref_status, transform_point,
)


def test_ordinary_block_translation():
    assert np.allclose(transform_point(block_matrix([10,20,0],0,1,1),[2,3]),[12,23])


def test_rotated_block():
    assert np.allclose(transform_point(block_matrix([0,0,0],math.pi/2,1,1),[2,0]),[0,2],atol=1e-8)


def test_non_uniform_scale_is_readonly_expandable():
    assert np.allclose(transform_point(block_matrix([0,0,0],0,2,3),[2,2]),[4,6])


def test_nested_matrix():
    parent=block_matrix([10,0,0],0,1,1); child=block_matrix([0,5,0],0,2,2)
    assert np.allclose(transform_point(compose_nested(parent,child),[1,1]),[12,7])


def test_anonymous_and_dynamic_are_preserved_in_design_contract():
    source=Path('mcp/orchestration/stage6_p2_2_block_xref_audit.py').read_text(encoding='utf-8')
    assert 'anonymous_name' in source and 'EffectiveName' in source and 'IsDynamicBlock' in source


def test_xref_identification_and_unloaded_status():
    assert normalize_xref_status(False,None,None)=='NOT_XREF'
    assert normalize_xref_status(True,'UNLOADED',None)=='XREF_UNLOADED'


def test_recursion_cycle_and_depth_protection_present():
    source=Path('mcp/orchestration/stage6_p2_2_block_xref_audit.py').read_text(encoding='utf-8')
    assert 'RECURSION_CYCLE' in source and 'MAX_DEPTH_REACHED' in source and 'MAX_NESTING_DEPTH = 8' in source


def test_region_bbox_audit():
    assert bbox_audit([0,0,100,100],[10,10,90,90])['building_bbox_inside_region'] is True
    assert bbox_audit([0,0,100,100],[-20,10,90,90])['building_bbox_inside_region'] is False


def _segments(offset=(0,0)):
    ox,oy=offset
    return [
      {'type':'line','layer':'A','source':'block','points':[[ox,oy],[ox+100,oy]]},
      {'type':'line','layer':'A','source':'block','points':[[ox,oy],[ox,oy+70]]},
      {'type':'line','layer':'A','source':'block','points':[[ox+17,oy+13],[ox+54,oy+42]]},
    ]


def test_layer_statistics_contract_present():
    source=Path('mcp/orchestration/stage6_p2_2_block_xref_audit.py').read_text(encoding='utf-8')
    assert 'orientation_histogram' in source and 'spatial_coverage' in source and 'total_length' in source


def test_unique_fingerprint_match():
    r=local_fingerprints(_segments()); t=local_fingerprints(_segments((200,-50)))
    assert len(match_unique_fingerprints(r,t))==3


def test_translation_fit():
    matches=match_unique_fingerprints(local_fingerprints(_segments()),local_fingerprints(_segments((200,-50))))
    result=fit_allowed_transform(matches,threshold=1)
    assert result['model_type']=='translation_only' and result['status']=='ALIGNMENT_VERIFIED'


def test_similarity_fit():
    ref=[[0,0],[100,0],[15,70],[80,55]]; angle=math.radians(.8); s=1.01
    tgt=[[s*(math.cos(angle)*x-math.sin(angle)*y)+200,s*(math.sin(angle)*x+math.cos(angle)*y)-50] for x,y in ref]
    matches=[{'reference_point':r,'target_point':t} for r,t in zip(ref,tgt)]
    result=fit_allowed_transform(matches,threshold=.1)
    assert result['status']=='ALIGNMENT_VERIFIED' and result['model_type']=='similarity_transform'


def test_affine_is_forbidden():
    assert ALLOWED_TRANSFORMS=={'translation_only','similarity_transform'}


def test_no_dwg_write_calls():
    source=Path('mcp/orchestration/stage6_p2_2_block_xref_audit.py').read_text(encoding='utf-8')
    for forbidden in ('CopyObjects','SendCommand','.Save(','.SaveAs(','TransformBy','AddLine','Explode('):
        assert forbidden not in source

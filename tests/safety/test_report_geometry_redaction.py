"""Publication redaction checks, not a real-CAD acceptance test."""
import json
from pathlib import Path


def load(name):
    return json.loads((Path('reports') / name).read_text(encoding='utf-8'))


def test_native_reconstruction_does_not_publish_native_geometry_tables():
    report = load('stage5_1_mvp2_native_full_reconstruction.json')
    assert report['capability_matrix'] == {}
    assert report['geometry_cleanup']['status'] == 'redacted'
    assert report['geometry_cleanup']['validation_status'] == 'not_rerun'
    assert report['geometry_cleanup']['real_geometry_included'] is False


def test_dwg_extracts_keep_no_extents_or_object_snapshots():
    for name in ['phase_d3_1_reference_dwg_geometry.json', 'phase_d3_1_existing_dwg_geometry.json']:
        report = load(name)
        assert report['extents'] == {}
        assert report['sample_objects'] == []
        assert report['geometry_cleanup']['validation_status'] == 'not_rerun'


def test_alignment_parameters_are_not_published():
    report = load('phase_d4_1_real_alignment.json')
    for key in ['scale_x', 'scale_y', 'offset_x', 'offset_y']:
        assert report[key] is None
    assert report['reference_extents'] == {}
    assert report['sandbox_extents'] == {}


def test_qa_handles_are_redacted_without_new_execution_claim():
    report = load('phase_d10_auto_qa.json')
    assert report['detected_handles'] == []
    assert report['geometry_cleanup']['validation_status'] == 'not_rerun'


def test_redacted_reports_do_not_contain_coordinate_vectors():
    found = 0
    def check(value):
        if isinstance(value, dict):
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            assert not (len(value) >= 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value))
            for child in value:
                check(child)
    for path in Path('reports').glob('*.json'):
        report = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(report, dict) and 'geometry_cleanup' in report:
            found += 1
            assert report['geometry_cleanup']['status'] == 'redacted'
            assert report['geometry_cleanup']['validation_status'] == 'not_rerun'
            check(report)
    assert found >= 45

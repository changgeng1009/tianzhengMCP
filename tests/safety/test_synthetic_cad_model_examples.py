"""CAD model examples are authored fixtures, not captured drawing exports."""
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize('name', [
    'current_cad_model_from_real_sample.json',
    'reference_cad_model_sample.json',
])
def test_cad_model_is_original_single_line(name):
    path = Path(__file__).resolve().parents[2] / 'examples' / name
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['fixture_kind'] == 'original_synthetic'
    assert data['status'] == 'not_run'
    assert data['source'] == {
        'kind': 'original_synthetic_fixture',
        'active_document': 'synthetic_sample.dwg',
        'full_name': 'synthetic_sample.dwg',
        'reader': 'not_run',
    }
    assert len(data['entities']) == 1
    line = data['entities'][0]
    assert line['type'] == 'line'
    assert line['geometry']['start'] == [0.0, 0.0, 0.0]
    assert line['geometry']['end'] == [10.0, 0.0, 0.0]
    assert line['geometry']['bounding_box'] == line['bounding_box']
    assert line['id'] == line['handle'] == line['properties']['handle'] == 'synthetic_line_001'
    assert line['status'] == 'not_run'
    assert line['confidence'] == 0.0
    assert line['source'] == 'original_synthetic_fixture'
    assert 'no CAD application or COM reader was used' in line['evidence']
    assert 'Confirmed' not in path.read_text(encoding='utf-8')


@pytest.mark.parametrize('name, records_key', [
    ('real_current_vs_reference_diff_sample.json', 'items'),
    ('cad_to_cad_execution_plan_sample.json', 'operations'),
])
def test_derived_example_is_empty_not_run(name, records_key):
    path = Path(__file__).resolve().parents[2] / 'examples' / name
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['fixture_kind'] == 'original_synthetic'
    assert data['status'] == 'not_run'
    assert data[records_key] == []
    if records_key == 'operations':
        assert data['confirmed'] is False
        assert data['previewed'] is False
        assert data['operation_count'] == 0
    else:
        assert all(count == 0 for count in data['summary'].values())


@pytest.mark.parametrize('name', [
    'manual_read_current_drawing_test.py',
    'manual_reference_dwg_diff_test.py',
    'manual_tianzheng_semantic_reader_test.py',
    'manual_tianzheng_selection_reader.py',
    'manual_tianzheng_object_inspect.py',
    'manual_tianzheng_diameter_association_test.py',
    'manual_tdbpipe_deep_probe.py',
])
def test_live_diagnostic_exports_do_not_overwrite_public_examples(name):
    root = Path(__file__).resolve().parents[2]
    source = (root / 'scripts' / name).read_text(encoding='utf-8')
    assert 'PROJECT_ROOT / "examples" /' not in source
    assert 'PROJECT_ROOT / "artifacts" / "local_diagnostics" /' in source
    assert 'mkdir(parents=True, exist_ok=True)' in source
    compile(source, name, 'exec')
    assert 'artifacts/' in (root / '.gitignore').read_text(encoding='utf-8').splitlines()


def test_mapped_execution_result_has_no_live_result():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / 'examples/mapped_execution_result_sample.json').read_text(encoding='utf-8'))
    assert data['fixture_kind'] == 'original_synthetic'
    assert data['status'] == 'not_run'
    assert data['success'] is False
    assert data['executed'] is False
    assert data['active_document'] is None
    assert data['operations'] == []
    assert data['operation_count'] == 0


def test_manual_cleanup_report_has_no_entity_handle_details():
    root = Path(__file__).resolve().parents[2]
    text = (root / 'reports/stage6_p1_emergency_manual_cleanup.md').read_text(encoding='utf-8')
    assert '- Handle `' not in text
    assert '[redacted: six historical entity-handle/type/layer detail records removed;' in text

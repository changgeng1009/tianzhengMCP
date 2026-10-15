"""Published diagnostic examples contain schemas, not private live-CAD data."""
import json
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'
NAMES = [
    'tdbpipe_deep_probe_sample',
    'tianzheng_diameter_association_sample',
    'tianzheng_object_inspection_sample',
    'tianzheng_semantic_model_sample',
    'selected_tianzheng_model_sample',
    'tianzheng_t30_diagnostic_sample',
]


@pytest.mark.parametrize('name', NAMES)
def test_diagnostic_example_is_empty_and_not_run(name):
    data = json.loads((EXAMPLES / f'{name}.json').read_text(encoding='utf-8'))
    assert data['fixture_kind'] == 'original_synthetic'
    assert data['status'] == 'not_run'
    assert 'not an acceptance result' in data['fixture_notice']

    def verify(value, key=''):
        if isinstance(value, dict):
            for child_key, child in value.items():
                verify(child, child_key)
        elif isinstance(value, list):
            assert value == [], f'{name}: captured records remain in {key}'
        elif isinstance(value, bool):
            assert value is False, f'{name}: execution/detection claim remains in {key}'
        elif isinstance(value, (int, float)):
            assert value == 0, f'{name}: observed numeric data remain in {key}'
        elif isinstance(value, str) and key in {'active_document', 'active_document_name', 'active_document_full_name'}:
            assert value == 'synthetic_sample.dwg'

    verify(data)

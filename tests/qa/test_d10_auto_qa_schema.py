"""Exercise D10 QA with explicit original fake-backend input, not real CAD.

A separate live-CAD integration run needs private authorized inputs and an
actual scanner. Passing here establishes only injected-backend QA behavior.
"""
import json

import pytest

from mcp.qa.d10_auto_qa_validator import run_d10_qa


@pytest.fixture
def synthetic_qa_report(tmp_path):
    source = tmp_path / 'synthetic_source.txt'
    sandbox = tmp_path / 'synthetic_sandbox.json'
    source.write_text('Original synthetic source; this is not a DWG.', encoding='utf-8')
    # Preserve the former cardinality assertion with wholly original objects.
    entities = [{'handle': f'SYNTHETIC_{i:04d}', 'start': [i, 0, 0],
                 'end': [i, 1, 0]} for i in range(607)]
    sandbox.write_text(json.dumps({'fixture_kind': 'original_synthetic',
                                  'entities': entities}), encoding='utf-8')
    calls = []

    def fake_scanner(path):
        calls.append(path)
        data = json.loads(sandbox.read_text(encoding='utf-8'))
        assert data['fixture_kind'] == 'original_synthetic'
        return {'sandbox_opened': True, 'modelspace_accessible': True,
                'total_entities': len(data['entities']),
                'detected_handles': [item['handle'] for item in data['entities']],
                'scan_backend_id': 'original_synthetic_fake_scanner'}

    output = tmp_path / 'synthetic_qa_report.json'
    result = run_d10_qa(source_path=str(source), sandbox_path=str(sandbox),
                       live_scanner=fake_scanner, report_path=output)
    assert calls == [str(sandbox)]
    assert json.loads(output.read_text(encoding='utf-8')) == result
    return result


class TestD10SyntheticSchema:
    def test_report_exists(self, synthetic_qa_report):
        r = synthetic_qa_report
        assert r['phase'] == 'D10'
        assert r['source_hash_unchanged'] is True
        assert r['qa_passed'] is True
        assert r['d1_allowed'] is False
        assert r['production_d1_allowed'] is False
        assert r['sendcommand_used'] is False
        assert r['source_dwg_opened'] is False
        assert r['scan_backend_id'] == 'original_synthetic_fake_scanner'

    def test_gate_checks(self, synthetic_qa_report):
        r = synthetic_qa_report
        assert r['gate']['d9_1_passed'] is True
        assert r['gate']['d9_2_passed'] is True

    def test_sandbox_accessible(self, synthetic_qa_report):
        r = synthetic_qa_report
        assert r['total_entities'] == 607
        assert len(r['detected_handles']) > 0
        assert len(r['detected_handles']) == 607
        assert all(handle.startswith('SYNTHETIC_') for handle in r['detected_handles'])
        assert r['persisted_object_detected'] is True
        assert r['live_scan_attempted'] is True  # injected fake scanner only

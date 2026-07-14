import json, pytest
from pathlib import Path

class TestD1ReportSchema:
    def test_required_fields(self):
        r = json.loads(Path('reports/phase_d1_real_aware_dry_run_acceptance.json').read_text(encoding='utf-8'))
        for field in ['phase','sample_count','dry_run_accepted_count','blocked_request_count',
            'dangerous_request_count','TDbDoubleLinePipe_supported','count_based_diff_supported',
            'sandbox_persistence_policy_supported','source_write_blocked','production_blocked',
            'd1_allowed','production_d1_allowed','source_modification_allowed']:
            assert field in r, f"Missing field: {field}"

    def test_all_d1_flags_false(self):
        r = json.loads(Path('reports/phase_d1_real_aware_dry_run_acceptance.json').read_text(encoding='utf-8'))
        for flag in ['d1_allowed','production_d1_allowed','source_modification_allowed']:
            assert r[flag] is False

    def test_samples_count_matches(self):
        r = json.loads(Path('reports/phase_d1_real_aware_dry_run_acceptance.json').read_text(encoding='utf-8'))
        assert len(r['samples']) == r['sample_count']

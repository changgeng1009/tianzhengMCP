import json, pytest
from pathlib import Path

class TestD1Pipeline:
    def setup_method(self):
        from mcp.execution.d1_real_aware_dry_run_pipeline import run_d1_pipeline
        self.report = run_d1_pipeline()

    def test_sample_count(self):
        assert self.report['sample_count'] == 12

    def test_dry_run_accepted(self):
        assert self.report['dry_run_accepted_count'] == 7

    def test_blocked(self):
        assert self.report['blocked_request_count'] == 5

    def test_TDbDoubleLinePipe_supported(self):
        assert self.report['TDbDoubleLinePipe_supported'] is True

    def test_count_based_diff(self):
        assert self.report['count_based_diff_supported'] is True

    def test_source_write_blocked(self):
        assert self.report['source_write_blocked'] is True

    def test_production_blocked(self):
        assert self.report['production_blocked'] is True

    def test_d1_allowed_false(self):
        assert self.report['d1_allowed'] is False
        assert self.report['production_d1_allowed'] is False

    def test_report_saved(self):
        p = Path('reports/phase_d1_real_aware_dry_run_acceptance.json')
        assert p.exists()
        d = json.loads(p.read_text(encoding='utf-8'))
        assert d['phase'] == 'D1'

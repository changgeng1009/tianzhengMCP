import json, pytest
from pathlib import Path

class TestD1SafetyBlockers:
    def setup_method(self):
        from mcp.execution.d1_real_aware_dry_run_pipeline import run_d1_pipeline
        self.report = run_d1_pipeline()

    def test_save_blocked(self):
        save = [s for s in self.report['samples'] if '保存' in s['natural_language']]
        assert any(s['blocked'] for s in save)

    def test_export_blocked(self):
        export = [s for s in self.report['samples'] if '导出' in s['natural_language']]
        assert any(s['blocked'] for s in export)

    def test_source_blocked(self):
        src = [s for s in self.report['samples'] if '正式' in s['natural_language']]
        assert any(s['blocked'] for s in src)

    def test_tsaveas_blocked(self):
        ts = [s for s in self.report['samples'] if 'TSaveAs' in s['natural_language']]
        assert any(s['blocked'] for s in ts)

    def test_dangerous_blocked(self):
        batch = [s for s in self.report['samples'] if '批打印' in s['natural_language']]
        assert any(s['blocked'] for s in batch)

import json, pytest
from pathlib import Path

class TestD45Safety:
    def test_report_exists(self):
        r = json.loads(Path('reports/phase_d4_5_reference_overlay_copy_probe.json').read_text(encoding='utf-8'))
        assert r['phase'] == 'D4.5'

    def test_source_not_opened(self):
        r = json.loads(Path('reports/phase_d4_5_reference_overlay_copy_probe.json').read_text(encoding='utf-8'))
        assert r['source_dwg_opened'] is False
        assert r['d1_allowed'] is False

    def test_no_sendcommand(self):
        r = json.loads(Path('reports/phase_d4_5_reference_overlay_copy_probe.json').read_text(encoding='utf-8'))
        assert r['sendcommand_used'] is False
        assert r['tianzheng_command_executed'] is False

    def test_no_save(self):
        r = json.loads(Path('reports/phase_d4_5_reference_overlay_copy_probe.json').read_text(encoding='utf-8'))
        assert r['saved_source_dwg'] is False
        assert r['saved_sandbox_dwg'] is False

    def test_reference_opened(self):
        r = json.loads(Path('reports/phase_d4_5_reference_overlay_copy_probe.json').read_text(encoding='utf-8'))
        assert r['reference_dwg_opened'] is True

import json, pytest
from pathlib import Path

class TestPersistenceSchema:
    def test_r6_persistence_loaded(self):
        r = json.loads(Path('artifacts/t30_r6_persistence.json').read_text(encoding='utf-8'))
        assert r['phase'] == 'R6'
        assert r['save_called_on_sandbox'] is True
        assert r['save_called_on_source'] is False
        assert r['persistence_success'] is True
        assert r['after_reopen_total'] == 622
        assert r['after_reopen_TDbDoubleLinePipe'] == 7
        assert r['d1_allowed'] is False
        assert r['source_dwg_opened'] is False

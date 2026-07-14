import json, pytest
from pathlib import Path

class TestMergeRegistry:
    def setup_method(self):
        self.data = json.loads(Path('command_registry/tianzheng_commands.merged.local.json').read_text(encoding='utf-8'))
        self.cmds = self.data['commands']
        self.mi = self.data.get('merge_info', {})

    def test_loadable(self):
        assert len(self.cmds) == 6

    def test_total_commands(self):
        assert len(self.cmds) == 6

    def test_matched_count(self):
        assert self.mi.get('local_discovered_total') == 0

    def test_unmatched_count(self):
        assert self.mi.get('unmatched_seed_total') == 6

    def test_confirmed_zero(self):
        assert self.mi.get('confirmed_total') == 0

    def test_production_true_zero(self):
        assert self.mi.get('allow_production_true_total') == 0

    def test_all_production_forbidden(self):
        for c in self.cmds:
            assert c.get('validation_status', {}).get('production') == 'forbidden'

    def test_all_allow_production_false(self):
        for c in self.cmds:
            assert c.get('safety', {}).get('allow_production') is False

    def test_all_confirmed_false(self):
        for c in self.cmds:
            assert c.get('confirmed') is False
            assert c.get('confirmed_for_sandbox') is False

    def test_synthetic_not_scanned(self):
        assert self.mi['synthetic'] is True
        assert self.mi['local_installation_scanned'] is False

    def test_d1_allowed_false(self):
        assert self.mi.get('d1_allowed') is False
        assert self.mi.get('production_d1_allowed') is False

    def test_discovered_have_evidence(self):
        for c in self.cmds:
            if c.get('source_status') == 'local_discovered':
                assert len(c.get('local_discovery_evidence', [])) > 0

import json
from pathlib import Path

class TestDiscoveryManifest:
    def setup_method(self):
        self.m = json.loads(Path('command_registry/local_discovery_manifest.json').read_text(encoding='utf-8'))

    def test_no_real_installation_evidence(self):
        assert self.m['status'] == 'not_scanned'
        assert self.m['local_installation_scanned'] is False
        assert self.m['synthetic'] is True
        assert self.m['total_files'] == 0
        assert self.m['files'] == []
        assert self.m['by_domain'] == {'plumbing': 0, 'hvac': 0}

    def test_global_flags(self):
        assert self.m['all_read_only'] is True
        assert self.m['any_executed'] is False
        assert self.m['any_loaded'] is False

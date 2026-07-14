import json, pytest, os
from pathlib import Path
from mcp.intake.file_fingerprint import fingerprint, verify

class TestD2Sandbox:
    def test_sandbox_exists(self, d2_synthetic_intake):
        r = d2_synthetic_intake.result
        s = r['sandbox']
        assert s is not None and s['exists'] is True
        assert os.path.exists(s['path'])

    def test_sandbox_diff_from_source(self, d2_synthetic_intake):
        r = d2_synthetic_intake.result
        assert r['sandbox']['path'] != r['source']['path']

    def test_hash_verification(self, d2_synthetic_intake):
        r = d2_synthetic_intake.result
        assert verify(r['source']['sha256'], r['sandbox']['path']) is True

    def test_fingerprint_file_not_found(self):
        fp = fingerprint('nonexistent_file_12345.xyz')
        assert fp['exists'] is False

    def test_sandbox_size_matches(self, d2_synthetic_intake):
        r = d2_synthetic_intake.result
        assert r['sandbox']['size'] == r['source']['size']

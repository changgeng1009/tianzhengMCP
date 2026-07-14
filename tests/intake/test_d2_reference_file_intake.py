import json, pytest, os
from pathlib import Path

class TestD2Intake:
    def test_source_exists(self, d2_synthetic_intake):
        assert d2_synthetic_intake.result['source']['exists'] is True
    def test_source_has_hash(self, d2_synthetic_intake):
        assert len(d2_synthetic_intake.result['source']['sha256']) == 64
    def test_ref_pdf(self, d2_synthetic_intake):
        refs = d2_synthetic_intake.result['references']
        pdf = [r for r in refs if r['path'].endswith('.pdf')]
        assert len(pdf) >= 1 and pdf[0]['exists'] is True
    def test_ref_dwg(self, d2_synthetic_intake):
        refs = d2_synthetic_intake.result['references']
        dwg = [r for r in refs if r['path'].endswith('.dwg') and 'reference' not in r.get('path','')]
        dwg2 = [r for r in refs if r['path'].endswith('.dwg')]
        assert len(dwg2) >= 1
    def test_sandbox_created(self, d2_synthetic_intake):
        assert d2_synthetic_intake.result['sandbox_created'] is True
    def test_hash_match(self, d2_synthetic_intake):
        assert d2_synthetic_intake.result['hash_match'] is True
    def test_source_not_opened(self, d2_synthetic_intake):
        assert d2_synthetic_intake.result['source_dwg_opened'] is False
    def test_d1_false(self, d2_synthetic_intake):
        assert d2_synthetic_intake.result['d1_allowed'] is False
        assert d2_synthetic_intake.result['production_d1_allowed'] is False
    def test_report_saved(self, d2_synthetic_intake):
        assert d2_synthetic_intake.report_path.exists()

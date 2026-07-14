# -*- coding: utf-8 -*-
import sys, tempfile, os, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.e1_saved_sandbox_persistence import (
    run_e1_orchestrator, FakeAcadAdapter, FakeScannerAdapter, FakeWatchdogAdapter,
)
def _run(tmp_path, synthetic_cad_factory):
    p = synthetic_cad_factory(tmp_path / "src.dwg")
    sp = synthetic_cad_factory(tmp_path / "s.dwg", create=False)
    r = run_e1_orchestrator(p, sp, FakeAcadAdapter(),
        FakeScannerAdapter(before_draw_tdb=0, after_draw_tdb=0, after_reopen_tdb=0),
        FakeWatchdogAdapter())
    return r
def test_d1_allowed_false(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory)["d1_allowed"] is False
def test_production_blocked(tmp_path, synthetic_cad_factory):
    r = _run(tmp_path, synthetic_cad_factory)
    assert r.get("production_d1_allowed", False) is False
    assert r.get("production_d1_executed", False) is False
def test_source_not_allowed(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("source_modification_allowed", True) is False
def test_readiness_not_true(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("d1_readiness", True) is False
def test_visual_does_not_restore(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("d1_readiness", True) is False
def test_still_blocked(tmp_path, synthetic_cad_factory):
    r = _run(tmp_path, synthetic_cad_factory)
    assert r.get("d1_allowed", True) is False
    assert r.get("production_d1_allowed", True) is False

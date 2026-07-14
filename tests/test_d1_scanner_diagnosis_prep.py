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
def test_pass_visual_not_d1_allowed(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory)["d1_allowed"] is False
def test_pass_visual_not_production(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("production_d1_allowed", False) is False
def test_acceptance_needs_review(tmp_path, synthetic_cad_factory):
    r = _run(tmp_path, synthetic_cad_factory)
    assert r["acceptance"] in ("needs_manual_review", "inconclusive"), r["acceptance"]
def test_zero_delta_e1_blocked(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("e1_1_real_complete", True) is False
def test_pre_existing_not_evidence(tmp_path, synthetic_cad_factory):
    p = synthetic_cad_factory(tmp_path / "src.dwg")
    sp = synthetic_cad_factory(tmp_path / "s.dwg", create=False)
    r = run_e1_orchestrator(p, sp, FakeAcadAdapter(),
        FakeScannerAdapter(before_draw_tdb=100, after_draw_tdb=100, after_reopen_tdb=0),
        FakeWatchdogAdapter())
    if r.get("fallback_used") and r.get("draw_delta", 0) == 0:
        assert r["acceptance"] != "success"
def test_missing_handle_unverified(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("three_segments_independently_verified", True) is False
def test_d1_readiness_false(tmp_path, synthetic_cad_factory):
    assert _run(tmp_path, synthetic_cad_factory).get("d1_readiness", True) is False
def test_production_still_blocked(tmp_path, synthetic_cad_factory):
    r = _run(tmp_path, synthetic_cad_factory)
    assert r.get("d1_allowed", True) is False
    assert r.get("production_d1_allowed", True) is False

from mcp.diff_engine.reference_target_diff import run_d6_diff, compute_diff

class TestD6Diff:
    def test_compute_diff_equal(self):
        d = compute_diff({'TDbPipe': 10}, {'TDbPipe': 10})
        assert len(d) == 0

    def test_compute_diff_different(self):
        d = compute_diff({'TDbPipe': 10}, {'TDbPipe': 15})
        assert len(d) == 1
        assert d['TDbPipe']['delta'] == 5

    def test_run_d6(self):
        r = run_d6_diff()
        assert r['phase'] == 'D6'
        assert r['source_dwg_opened'] is False
        assert r['d1_allowed'] is False

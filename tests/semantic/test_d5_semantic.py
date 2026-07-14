from mcp.semantic.reference_semantic_reader import run_d5_semantic, parse_pipe_labels

class TestD5Semantic:
    def test_parse_labels_empty(self):
        assert parse_pipe_labels('') == []

    def test_parse_dn_labels(self):
        r = parse_pipe_labels('DN100 给水管\nDN50 排水管')
        assert len(r) == 2

    def test_run_d5(self):
        r = run_d5_semantic()
        assert r['phase'] == 'D5'
        assert r.get('source_dwg_opened') is False
        assert r['d1_allowed'] is False

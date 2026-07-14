import json, pytest
from pathlib import Path
from mcp.extraction.dwg_geometry_extractor import extract_dwg_geometry

class TestD3DWG:
    def test_extract_runs(self):
        r = extract_dwg_geometry()
        assert r['phase'] == 'D3'
        assert 'source' in r

    def test_no_source_opened(self):
        r = extract_dwg_geometry()
        assert r.get('source_dwg_opened') is False or r.get('source_dwg_opened') != True

    def test_serialized_backend_entities_are_summarized(self):
        r = extract_dwg_geometry('safe-copy.dwg', entities=[
            {'object_name':'TDbPipe','handle':'1','layer':'PIPE','diameter':100},
            {'object_name':'AcDbLine','handle':'2','layer':'AUX'},
        ])
        assert r['status'] == 'PASS'
        assert r['tdb_pipe_count'] == 1
        assert r['total_entities'] == 2

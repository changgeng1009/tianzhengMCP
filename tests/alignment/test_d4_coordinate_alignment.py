import json, pytest
from pathlib import Path
from mcp.alignment.coordinate_alignment import CoordinateAligner, pdf_to_dwg_aligner, generate_alignment_report

class TestD4Alignment:
    def test_2point_transform(self):
        a = CoordinateAligner()
        a.compute_2point_transform([(0,0),(10,10)], [(0,0),(100,100)])
        assert abs(a.scale_x - 10) < 1
        assert abs(a.scale_y - 10) < 1

    def test_transform_point(self):
        a = CoordinateAligner()
        a.compute_2point_transform([(0,0),(10,10)], [(0,0),(100,100)])
        tx, ty = a.transform_point(5, 5)
        assert abs(tx - 50) < 1 and abs(ty - 50) < 1

    def test_pdf_aligner(self):
        a = pdf_to_dwg_aligner(2384, 3370)
        assert a.scale_x > 10
        assert a.scale_y > 10

    def test_report_generated(self, tmp_path):
        r = generate_alignment_report(str(Path(__file__).resolve().parents[2] / 'reports/phase_d3_pdf_geometry.json'), str(tmp_path / 'phase_d4_test.json'))
        assert r['phase'] == 'D4'
        assert r['alignment']['confidence'] > 0.5
        assert r['pdf_dimensions'] == {'width': 2100.0, 'height': 3100.0}
        assert r['alignment']['scale_x'] == pytest.approx(42000 / 2100)
        assert r['alignment']['scale_y'] == pytest.approx(59400 / 3100)

    def test_source_not_opened(self, tmp_path):
        r = generate_alignment_report(str(Path(__file__).resolve().parents[2] / 'reports/phase_d3_pdf_geometry.json'), str(tmp_path / 'phase_d4_test.json'))
        assert r['source_dwg_opened'] is False

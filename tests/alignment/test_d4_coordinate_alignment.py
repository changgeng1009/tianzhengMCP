from mcp.alignment.coordinate_alignment import CoordinateAligner, generate_alignment_report, pdf_to_dwg_aligner


class TestD4Alignment:
    def test_2point_transform(self):
        aligner = CoordinateAligner()
        aligner.compute_2point_transform([(0, 0), (10, 10)], [(0, 0), (100, 100)])
        assert abs(aligner.scale_x - 10) < 1
        assert abs(aligner.scale_y - 10) < 1

    def test_transform_point(self):
        aligner = CoordinateAligner()
        aligner.compute_2point_transform([(0, 0), (10, 10)], [(0, 0), (100, 100)])
        tx, ty = aligner.transform_point(5, 5)
        assert abs(tx - 50) < 1 and abs(ty - 50) < 1

    def test_pdf_aligner(self):
        assert pdf_to_dwg_aligner(2384, 3370).scale_x > 10

    def test_report_generated(self, tmp_path):
        report = generate_alignment_report('reports/phase_d3_pdf_geometry.json', tmp_path / 'phase_d4_test.json')
        assert report['phase'] == 'D4'
        assert report['alignment']['confidence'] > 0.5

    def test_source_not_opened(self, tmp_path):
        report = generate_alignment_report('reports/phase_d3_pdf_geometry.json', tmp_path / 'phase_d4_test.json')
        assert report['source_dwg_opened'] is False

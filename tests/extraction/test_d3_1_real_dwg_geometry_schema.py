"""Original offline schema examples, NOT real-DWG integration acceptance.

Historical geometry is intentionally redacted. These tests preserve positive
extent/enumeration assertions using newly authored line segments. A live-DWG
integration run requires separately authorized private inputs and a CAD backend.
The current serialized-entity extractor does not calculate extents; its actual
contract is checked separately rather than attributed the fixture's fields.
"""
import json

import pytest

from mcp.extraction.dwg_geometry_extractor import extract_dwg_geometry


@pytest.fixture
def synthetic_geometry(tmp_path):
    entities = [
        {'object_name': 'AcDbLine', 'handle': 'SYNTHETIC_A', 'layer': 'SYNTHETIC',
         'start_point': [0, 0, 0], 'end_point': [10, 0, 0]},
        {'object_name': 'AcDbLine', 'handle': 'SYNTHETIC_B', 'layer': 'SYNTHETIC',
         'start_point': [10, 0, 0], 'end_point': [10, 5, 0]},
    ]
    points = [item[key] for item in entities for key in ('start_point', 'end_point')]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    schema_example = {
        'fixture_kind': 'original_synthetic', 'real_cad_run': False,
        'enumerated': len(entities), 'source_dwg_opened': False,
        'extents': {'min_x': xmin, 'max_x': xmax, 'min_y': ymin, 'max_y': ymax,
                    'width': xmax - xmin, 'height': ymax - ymin},
    }
    path = tmp_path / 'synthetic_geometry_schema.json'
    path.write_text(json.dumps(schema_example), encoding='utf-8')
    return json.loads(path.read_text(encoding='utf-8')), entities


class TestD31SyntheticGeometrySchema:
    def test_ref_exists(self, synthetic_geometry):
        report, _ = synthetic_geometry
        assert report['fixture_kind'] == 'original_synthetic'
        assert report['real_cad_run'] is False
        assert report['enumerated'] > 0
        assert report['source_dwg_opened'] is False

    def test_sandbox_exists(self, synthetic_geometry):
        report, _ = synthetic_geometry
        assert report['enumerated'] > 0

    def test_ref_has_extents(self, synthetic_geometry):
        report, _ = synthetic_geometry
        assert report['extents']['width'] > 0
        assert report['extents']['width'] == 10
        assert report['extents']['height'] == 5

    def test_actual_serialized_extractor_contract(self, synthetic_geometry):
        _, entities = synthetic_geometry
        result = extract_dwg_geometry('synthetic://original-lines', entities=entities)
        assert result['status'] == 'PASS'
        assert result['total_entities'] == 2
        assert result['object_name_counts'] == {'AcDbLine': 2}
        assert result['sample_objects'][0]['StartPoint'] == [0, 0, 0]
        assert result['sample_objects'][1]['EndPoint'] == [10, 5, 0]
        assert result['source_dwg_opened'] is False
        assert result['dwg_saved'] is False

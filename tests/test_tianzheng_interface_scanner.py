"""测试 tianzheng_interface.scanner — DWG 扫描器。

Phase M1 约束:
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
"""

import json
import pytest
from tianzheng_interface.scanner import DWGScanner, scan_empty, quick_scan
from tianzheng_interface.model import DWGScanResult


def _make_entities():
    return [
        {"object_name": "TDbPipe", "layer": "PIPE-给水", "handle": "A1"},
        {"object_name": "TDbPipe", "layer": "PIPE-给水", "handle": "A2"},
        {"object_name": "TDbPipe", "layer": "PIPE-消防", "handle": "B1"},
        {"object_name": "TDbPipeValve", "layer": "VALV-给水", "handle": "V1"},
        {"object_name": "TDbPipeFitting", "layer": "FITT-给水", "handle": "F1"},
        {"object_name": "TDbDimension2", "layer": "DIM-标注", "handle": "D1"},
        {"object_name": "AcDbLine", "layer": "0", "handle": "L1"},
        {"object_name": "AcDbText", "layer": "0", "handle": "T1"},
        {"object_name": "UnknownProxy", "layer": "0", "handle": "U1"},
    ]


def _make_pipes():
    return [
        {"handle": "A1", "object_name": "TDbPipe", "semantic_type": "pipe",
         "layer": "PIPE-给水", "system_type": "给水", "dn": "DN50",
         "start_point": {"x": 0, "y": 0, "z": 0},
         "end_point": {"x": 1000, "y": 0, "z": 0},
         "length": 1000, "elevation_start": 3000, "elevation_end": 3000},
        {"handle": "A2", "object_name": "TDbPipe", "semantic_type": "pipe",
         "layer": "PIPE-给水", "system_type": "给水", "dn": "DN100",
         "start_point": {"x": 1000, "y": 0, "z": 0},
         "end_point": {"x": 2000, "y": 0, "z": 0},
         "length": 1000, "elevation_start": 3000, "elevation_end": 3000},
        {"handle": "B1", "object_name": "TDbPipe", "semantic_type": "pipe",
         "layer": "PIPE-消防", "system_type": "消防", "dn": "DN200",
         "start_point": {"x": 0, "y": 100, "z": 0},
         "end_point": {"x": 1000, "y": 100, "z": 0},
         "length": 1000, "elevation_start": 0, "elevation_end": 0},
    ]


def _make_valves():
    return [
        {"handle": "V1", "object_name": "TDbPipeValve",
         "semantic_type": "valve", "layer": "VALV-给水",
         "system_type": "给水", "valve_type_guess": "gate_valve",
         "center": {"x": 500, "y": 0, "z": 0}},
    ]


class TestScanEmpty:
    def test_returns_dwg_scan_result(self):
        result = scan_empty("test.dwg")
        assert isinstance(result, DWGScanResult)
        assert result.source_dwg == "test.dwg"

    def test_has_timestamp(self):
        result = scan_empty()
        assert result.scan_timestamp != ""


class TestQuickScan:
    def test_returns_result(self):
        result = quick_scan(_make_entities(), source_dwg="test.dwg")
        assert isinstance(result, DWGScanResult)
        assert result.entity_statistics.total_entities == 9


class TestDWGSscanner:
    def test_scan_basic(self):
        scanner = DWGScanner(source_dwg="test.dwg")
        result = scanner.scan(
            entities=_make_entities(),
            pipes=_make_pipes(),
            valves=_make_valves(),
            tianzheng_detected=True,
            tianzheng_version="T30 V1.0",
        )
        assert result.tianzheng_detected is True
        assert result.tianzheng_version == "T30 V1.0"
        stats = result.entity_statistics
        assert stats.total_entities == 9
        assert stats.tianzheng_object_count == 6

    def test_systems_grouping(self):
        scanner = DWGScanner(source_dwg="test.dwg")
        result = scanner.scan(
            entities=_make_entities(),
            pipes=_make_pipes(),
            valves=_make_valves(),
        )
        assert len(result.systems) >= 2
        system_names = {s.system_type for s in result.systems}
        assert "给水" in system_names
        assert "消防" in system_names

    def test_network_summary_from_data(self):
        scanner = DWGScanner(source_dwg="test.dwg")
        result = scanner.scan(
            entities=_make_entities(),
            pipes=_make_pipes(),
            pipe_network_data={
                "node_count": 10, "edge_count": 8,
                "connected_component_count": 1,
                "system_summaries": {
                    "给水": {"pipes": 2, "valves": 1, "fittings": 0, "annotations": 0},
                },
            },
        )
        net = result.pipe_network_summary
        assert net.node_count == 10
        assert net.edge_count == 8

    def test_warnings_collected(self):
        scanner = DWGScanner(source_dwg="test.dwg")
        pipes = [{"handle": "W1", "object_name": "TDbPipe",
                   "semantic_type": "pipe", "system_type": "unknown",
                   "dn": "DN50", "start_point": {"x": 0, "y": 0, "z": 0},
                   "end_point": {"x": 1, "y": 0, "z": 0},
                   "warnings": ["管径无法确认"]}]
        result = scanner.scan(entities=_make_entities(), pipes=pipes)
        assert len(result.warnings) > 0
        assert any("管径无法确认" in w for w in result.warnings)

    def test_json_roundtrip(self):
        scanner = DWGScanner(source_dwg="test.dwg")
        result = scanner.scan(
            entities=_make_entities(), pipes=_make_pipes(),
            valves=_make_valves(), tianzheng_detected=True)
        json_str = result.to_json()
        loaded = DWGScanResult.from_dict(json.loads(json_str))
        assert loaded.source_dwg == "test.dwg"
        assert loaded.tianzheng_detected is True

    def test_no_autocad_import(self):
        from tianzheng_interface import scanner

        assert "win32com" not in scanner.__dict__

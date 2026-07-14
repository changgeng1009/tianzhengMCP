"""测试 tianzheng_interface.model — 数据模型 to_dict / from_dict / JSON roundtrip。

Phase 1 约束:
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
- 不访问 target.dwg
"""

import json
import pytest
from tianzheng_interface.model import (
    Point3D,
    PipeSegment,
    ValveInfo,
    FittingInfo,
    DimensionInfo,
    UnknownProxyInfo,
    EntityStatistics,
    WaterSupplySystem,
    PipeNetworkSummary,
    DWGScanResult,
)


class TestPoint3D:
    def test_defaults(self):
        p = Point3D()
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0
        assert p.coordinate_system == "cad_world"

    def test_to_tuple(self):
        p = Point3D(100.0, 200.0, 300.0)
        assert p.to_tuple() == (100.0, 200.0, 300.0)

    def test_to_dict(self):
        p = Point3D(1.0, 2.0, 3.0)
        d = p.to_dict()
        assert d == {"x": 1.0, "y": 2.0, "z": 3.0, "coordinate_system": "cad_world"}

    def test_from_dict(self):
        d = {"x": 10.0, "y": 20.0, "z": 30.0, "coordinate_system": "cad_world"}
        p = Point3D.from_dict(d)
        assert p.x == 10.0
        assert p.y == 20.0
        assert p.z == 30.0

    def test_from_dict_defaults(self):
        p = Point3D.from_dict({})
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0

    def test_json_roundtrip(self):
        p = Point3D(5.5, 6.6, 7.7)
        d = p.to_dict()
        j = json.dumps(d)
        restored = Point3D.from_dict(json.loads(j))
        assert restored.x == 5.5
        assert restored.y == 6.6
        assert restored.z == 7.7


class TestPipeSegment:
    def test_defaults(self):
        ps = PipeSegment()
        assert ps.semantic_type == "pipe"
        assert ps.system_type == "unknown"
        assert ps.dn is None
        assert ps.handle == ""

    def test_with_dn_and_system(self):
        ps = PipeSegment(
            handle="ABC123",
            dn="DN100",
            dn_source="TDbPipe.DNDiameter",
            system_type="给水",
            system_type_source="TDbPipe.SysType",
            layer="PIPE-给水",
            start_point=Point3D(0, 0, 3000),
            end_point=Point3D(5000, 0, 3000),
        )
        d = ps.to_dict()
        assert d["handle"] == "ABC123"
        assert d["dn"] == "DN100"
        assert d["system_type"] == "给水"
        assert d["start_point"]["x"] == 0.0
        assert d["end_point"]["x"] == 5000.0

    def test_json_roundtrip(self):
        ps = PipeSegment(
            handle="P001",
            dn="DN50",
            dn_source="TDbPipe.DNDiameter",
            system_type="消防",
            layer="PIPE-消防",
            start_point=Point3D(100, 200, 0),
            end_point=Point3D(5000, 200, 0),
            elevation_start=0.0,
            elevation_end=0.0,
            warnings=["test warning"],
        )
        j = ps.to_dict()
        restored = PipeSegment.from_dict(j)
        assert restored.handle == "P001"
        assert restored.dn == "DN50"
        assert restored.system_type == "消防"
        assert restored.start_point.x == 100.0
        assert restored.end_point.x == 5000.0
        assert restored.warnings == ["test warning"]

    def test_roundtrip_with_null_points(self):
        ps = PipeSegment(handle="P002", dn="DN25")
        j = ps.to_dict()
        restored = PipeSegment.from_dict(j)
        assert restored.handle == "P002"
        assert restored.dn == "DN25"
        assert restored.start_point is None
        assert restored.end_point is None


class TestValveInfo:
    def test_roundtrip(self):
        v = ValveInfo(
            handle="V001",
            system_type="消防",
            valve_type_guess="消防阀门",
            center=Point3D(2500, 0, 0),
            width=200.0,
            height=300.0,
        )
        j = v.to_dict()
        restored = ValveInfo.from_dict(j)
        assert restored.handle == "V001"
        assert restored.system_type == "消防"
        assert restored.center.x == 2500.0


class TestFittingInfo:
    def test_roundtrip(self):
        f = FittingInfo(
            handle="F001",
            system_type="给水",
            fitting_type_guess="弯头",
            center=Point3D(1000, 500, 3000),
        )
        j = f.to_dict()
        restored = FittingInfo.from_dict(j)
        assert restored.handle == "F001"
        assert restored.fitting_type_guess == "弯头"


class TestDimensionInfo:
    def test_roundtrip(self):
        d = DimensionInfo(
            handle="D001",
            text="DN100",
            measurement=100.0,
            layer="DIM-给水",
        )
        j = d.to_dict()
        restored = DimensionInfo.from_dict(j)
        assert restored.handle == "D001"
        assert restored.text == "DN100"


class TestUnknownProxyInfo:
    def test_roundtrip(self):
        u = UnknownProxyInfo(
            handle="U001",
            object_name="SomeCustomObject",
            classification="unknown_proxy",
            classification_reason="Not in known types",
        )
        j = u.to_dict()
        restored = UnknownProxyInfo.from_dict(j)
        assert restored.classification == "unknown_proxy"


class TestEntityStatistics:
    def test_roundtrip(self):
        es = EntityStatistics(
            total_entities=100,
            pipe_count=30,
            valve_count=5,
        )
        j = es.to_dict()
        restored = EntityStatistics.from_dict(j)
        assert restored.pipe_count == 30
        assert restored.valve_count == 5


class TestWaterSupplySystem:
    def test_roundtrip(self):
        system = WaterSupplySystem(
            system_type="消防",
            pipes=[PipeSegment(handle="P1", dn="DN150")],
            valves=[ValveInfo(handle="V1", valve_type_guess="消防阀门")],
        )
        j = system.to_dict()
        restored = WaterSupplySystem.from_dict(j)
        assert restored.system_type == "消防"
        assert restored.pipes[0].dn == "DN150"


class TestPipeNetworkSummary:
    def test_roundtrip(self):
        pns = PipeNetworkSummary(
            node_count=25,
            edge_count=30,
            connected_component_count=2,
        )
        j = pns.to_dict()
        restored = PipeNetworkSummary.from_dict(j)
        assert restored.node_count == 25
        assert restored.edge_count == 30


class TestDWGScanResult:
    def test_to_json(self):
        result = DWGScanResult(
            source_dwg="test.dwg",
            scan_timestamp="2026-07-07T00:00:00Z",
            tianzheng_detected=True,
        )
        j = result.to_json()
        assert "test.dwg" in j
        assert "2026" in j

    def test_json_roundtrip(self):
        original = DWGScanResult(
            source_dwg="pump_room.dwg",
            tianzheng_detected=True,
            tianzheng_version="T30 V1.0",
            entity_statistics=EntityStatistics(total_entities=50, pipe_count=20),
            warnings=["test"],
        )
        j_str = original.to_json()
        restored = DWGScanResult.from_dict(json.loads(j_str))
        assert restored.source_dwg == "pump_room.dwg"
        assert restored.tianzheng_detected is True
        assert restored.entity_statistics.pipe_count == 20
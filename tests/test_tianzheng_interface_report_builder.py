"""测试 tianzheng_interface.report_builder — Markdown+JSON 报告。

Phase M1 约束:
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
"""

import json
import os
import tempfile
import pytest
from tianzheng_interface.report_builder import (
    ReportBuilder, build_markdown_report, build_json_report, save_report
)
from tianzheng_interface.model import (
    DWGScanResult, EntityStatistics, WaterSupplySystem,
    PipeSegment, PipeNetworkSummary,
)


def _make_scan_result():
    stats = EntityStatistics(
        total_entities=10, basic_cad_count=3,
        tianzheng_object_count=7, pipe_count=5,
        valve_count=2, fitting_count=0,
        dimension_count=0, unknown_proxy_count=0,
        object_name_distribution={"TDbPipe": 5, "TDbPipeValve": 2},
        layer_distribution={"PIPE-给水": 5, "VALV-给水": 2, "0": 3},
    )

    pipes = [
        PipeSegment(handle="A1", dn="DN50", system_type="给水",
                    elevation_start=3000, elevation_end=3000),
        PipeSegment(handle="A2", dn="DN100", system_type="给水",
                    elevation_start=3000, elevation_end=3000),
    ]

    sys1 = WaterSupplySystem(
        system_type="给水", pipes=pipes, warnings=["测试警告"],
    )

    net = PipeNetworkSummary(
        node_count=4, edge_count=2, connected_component_count=1,
        system_summaries={"给水": {"pipes": 2, "valves": 0, "fittings": 0, "annotations": 0}},
    )

    return DWGScanResult(
        source_dwg="test.dwg",
        scan_timestamp="2026-07-08T12:00:00",
        tianzheng_detected=True,
        tianzheng_version="T30 V1.0",
        entity_statistics=stats,
        systems=[sys1],
        pipe_network_summary=net,
        warnings=["dry-run only"],
    )


class TestReportBuilder:
    def test_markdown_contains_sections(self):
        scan = _make_scan_result()
        md = build_markdown_report(scan)
        assert "# 天正 DWG 扫描报告" in md
        assert "## 1. 实体统计" in md
        assert "## 2. 系统分组" in md
        assert "## 3. 管网摘要" in md
        assert "## 4. 警告" in md

    def test_markdown_has_stats(self):
        scan = _make_scan_result()
        md = build_markdown_report(scan)
        assert "| 实体总数 | 10 |" in md
        assert "| 管道 (pipe) | 5 |" in md

    def test_markdown_no_tianzheng(self):
        scan = _make_scan_result()
        scan.tianzheng_detected = False
        md = build_markdown_report(scan)
        assert "未检测" in md

    def test_json_report(self):
        scan = _make_scan_result()
        js = build_json_report(scan)
        data = json.loads(js)
        assert data["source_dwg"] == "test.dwg"
        assert data["tianzheng_detected"] is True

    def test_save_report_creates_files(self):
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmp:
            output = save_report(scan, output_dir=tmp, basename="test_scan")
            assert os.path.exists(output.markdown_path)
            assert os.path.exists(output.json_path)
            with open(output.markdown_path, "r", encoding="utf-8") as f:
                assert "# 天正 DWG" in f.read()

    def test_save_auto_basename(self):
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmp:
            output = save_report(scan, output_dir=tmp)
            assert output.markdown_path.endswith(".md")
            assert output.json_path.endswith(".json")

    def test_empty_systems(self):
        scan = _make_scan_result()
        scan.systems = []
        md = build_markdown_report(scan)
        assert "*(未检测到系统分组)*" in md

    def test_no_warnings(self):
        scan = _make_scan_result()
        scan.warnings = []; scan.systems[0].warnings = []
        md = build_markdown_report(scan)
        assert "✅ 无警告" in md

    def test_no_autocad_import(self):
        from tianzheng_interface import report_builder

        assert "win32com" not in report_builder.__dict__

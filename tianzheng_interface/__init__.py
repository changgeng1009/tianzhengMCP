"""天正给排水接口层 — Phase M1 只读分析 + 扫描/报告框架"""

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
from tianzheng_interface.action_schema import ActionDefinition, RiskLevel
from tianzheng_interface.proxy_handler import ProxyObjectHandler, ProxyClassification
from tianzheng_interface.dry_run_engine import DryRunEngine, DryRunResult
from tianzheng_interface.scanner import DWGScanner, scan_empty, quick_scan
from tianzheng_interface.report_builder import (
    ReportBuilder,
    ReportOutput,
    build_markdown_report,
    build_json_report,
    save_report,
)

__all__ = [
    "ActionDefinition",
    "RiskLevel",
    "DWGScanResult",
    "DWGScanner",
    "DryRunEngine",
    "DryRunResult",
    "EntityStatistics",
    "PipeNetworkSummary",
    "PipeSegment",
    "Point3D",
    "ProxyClassification",
    "ProxyObjectHandler",
    "ReportBuilder",
    "ReportOutput",
    "FittingInfo",
    "DimensionInfo",
    "UnknownProxyInfo",
    "ValveInfo",
    "WaterSupplySystem",
    "build_markdown_report",
    "build_json_report",
    "quick_scan",
    "save_report",
    "scan_empty",
]

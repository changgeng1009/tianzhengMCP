"""天正给排水接口层 — 只读语义数据模型

Phase 1: 纯数据结构，不含 COM 对象引用，不含写 DWG 能力。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ════════════════════════════════════════════════════════════════
# 基础几何类型
# ════════════════════════════════════════════════════════════════

@dataclass
class Point3D:
    """三维点，WCS 坐标。"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    coordinate_system: str = "cad_world"

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "coordinate_system": self.coordinate_system,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Point3D":
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            z=float(data.get("z", 0.0)),
            coordinate_system=str(data.get("coordinate_system", "cad_world")),
        )

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)
# ════════════════════════════════════════════════════════════════
# 管道 / 阀门 / 管件 / 标注 语义实体
# ════════════════════════════════════════════════════════════════

@dataclass
class PipeSegment:
    """天正给排水管道 (TDbPipe) 语义模型。"""
    handle: str = ""
    object_name: str = "TDbPipe"
    semantic_type: str = "pipe"
    layer: str = ""
    system_type: str = "unknown"
    system_type_source: str = "unknown"
    dn: str | None = None
    dn_source: str | None = None
    start_point: Point3D | None = None
    end_point: Point3D | None = None
    length: float | None = None
    elevation_start: float | None = None
    elevation_end: float | None = None
    bounding_box: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "object_name": self.object_name,
            "semantic_type": self.semantic_type,
            "layer": self.layer,
            "system_type": self.system_type,
            "system_type_source": self.system_type_source,
            "dn": self.dn,
            "dn_source": self.dn_source,
            "start_point": self.start_point.to_dict() if self.start_point else None,
            "end_point": self.end_point.to_dict() if self.end_point else None,
            "length": self.length,
            "elevation_start": self.elevation_start,
            "elevation_end": self.elevation_end,
            "bounding_box": list(self.bounding_box),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipeSegment":
        start = data.get("start_point")
        end = data.get("end_point")
        return cls(
            handle=str(data.get("handle", "")),
            object_name=str(data.get("object_name", "TDbPipe")),
            semantic_type=str(data.get("semantic_type", "pipe")),
            layer=str(data.get("layer", "")),
            system_type=str(data.get("system_type", "unknown")),
            system_type_source=str(data.get("system_type_source", "unknown")),
            dn=data.get("dn"),
            dn_source=data.get("dn_source"),
            start_point=Point3D.from_dict(start) if isinstance(start, dict) else None,
            end_point=Point3D.from_dict(end) if isinstance(end, dict) else None,
            length=float(data["length"]) if data.get("length") is not None else None,
            elevation_start=float(data["elevation_start"]) if data.get("elevation_start") is not None else None,
            elevation_end=float(data["elevation_end"]) if data.get("elevation_end") is not None else None,
            bounding_box=list(data.get("bounding_box", [])),
            warnings=list(data.get("warnings", [])),
        )

@dataclass
class ValveInfo:
    """天正阀门 (TDbPipeValve) 语义模型。"""
    handle: str = ""
    object_name: str = "TDbPipeValve"
    semantic_type: str = "valve"
    layer: str = ""
    system_type: str = "unknown"
    valve_type_guess: str = "unknown"
    center: Point3D | None = None
    width: float = 0.0
    height: float = 0.0
    bounding_box: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "object_name": self.object_name,
            "semantic_type": self.semantic_type,
            "layer": self.layer,
            "system_type": self.system_type,
            "valve_type_guess": self.valve_type_guess,
            "center": self.center.to_dict() if self.center else None,
            "width": self.width,
            "height": self.height,
            "bounding_box": list(self.bounding_box),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValveInfo":
        center = data.get("center")
        return cls(
            handle=str(data.get("handle", "")),
            object_name=str(data.get("object_name", "TDbPipeValve")),
            semantic_type=str(data.get("semantic_type", "valve")),
            layer=str(data.get("layer", "")),
            system_type=str(data.get("system_type", "unknown")),
            valve_type_guess=str(data.get("valve_type_guess", "unknown")),
            center=Point3D.from_dict(center) if isinstance(center, dict) else None,
            width=float(data.get("width", 0.0)),
            height=float(data.get("height", 0.0)),
            bounding_box=list(data.get("bounding_box", [])),
            warnings=list(data.get("warnings", [])),
        )


@dataclass
class FittingInfo:
    """天正管件 (TDbPipeFitting) 语义模型。"""
    handle: str = ""
    object_name: str = "TDbPipeFitting"
    semantic_type: str = "fitting"
    layer: str = ""
    system_type: str = "unknown"
    fitting_type_guess: str = "unknown"
    center: Point3D | None = None
    width: float = 0.0
    height: float = 0.0
    bounding_box: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "object_name": self.object_name,
            "semantic_type": self.semantic_type,
            "layer": self.layer,
            "system_type": self.system_type,
            "fitting_type_guess": self.fitting_type_guess,
            "center": self.center.to_dict() if self.center else None,
            "width": self.width,
            "height": self.height,
            "bounding_box": list(self.bounding_box),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FittingInfo":
        center = data.get("center")
        return cls(
            handle=str(data.get("handle", "")),
            object_name=str(data.get("object_name", "TDbPipeFitting")),
            semantic_type=str(data.get("semantic_type", "fitting")),
            layer=str(data.get("layer", "")),
            system_type=str(data.get("system_type", "unknown")),
            fitting_type_guess=str(data.get("fitting_type_guess", "unknown")),
            center=Point3D.from_dict(center) if isinstance(center, dict) else None,
            width=float(data.get("width", 0.0)),
            height=float(data.get("height", 0.0)),
            bounding_box=list(data.get("bounding_box", [])),
            warnings=list(data.get("warnings", [])),
        )


@dataclass
class DimensionInfo:
    """天正标注 (TDbDimension2) 语义模型。"""
    handle: str = ""
    object_name: str = "TDbDimension2"
    semantic_type: str = "dimension"
    layer: str = ""
    text: str | None = None
    measurement: float | None = None
    bounding_box: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "object_name": self.object_name,
            "semantic_type": self.semantic_type,
            "layer": self.layer,
            "text": self.text,
            "measurement": self.measurement,
            "bounding_box": list(self.bounding_box),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DimensionInfo":
        return cls(
            handle=str(data.get("handle", "")),
            object_name=str(data.get("object_name", "TDbDimension2")),
            semantic_type=str(data.get("semantic_type", "dimension")),
            layer=str(data.get("layer", "")),
            text=data.get("text"),
            measurement=float(data["measurement"]) if data.get("measurement") is not None else None,
            bounding_box=list(data.get("bounding_box", [])),
            warnings=list(data.get("warnings", [])),
        )

# ════════════════════════════════════════════════════════════════
# 未知对象
# ════════════════════════════════════════════════════════════════

@dataclass
class UnknownProxyInfo:
    """无法归类的 proxy / custom object。"""
    handle: str = ""
    object_name: str = ""
    layer: str = ""
    classification: str = "unknown_custom"
    classification_reason: str = ""
    bounding_box: list[float] = field(default_factory=list)
    xdata_summary: dict[str, Any] = field(default_factory=dict)
    extension_dictionary_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "object_name": self.object_name,
            "layer": self.layer,
            "classification": self.classification,
            "classification_reason": self.classification_reason,
            "bounding_box": list(self.bounding_box),
            "xdata_summary": dict(self.xdata_summary),
            "extension_dictionary_keys": list(self.extension_dictionary_keys),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnknownProxyInfo":
        return cls(
            handle=str(data.get("handle", "")),
            object_name=str(data.get("object_name", "")),
            layer=str(data.get("layer", "")),
            classification=str(data.get("classification", "unknown_custom")),
            classification_reason=str(data.get("classification_reason", "")),
            bounding_box=list(data.get("bounding_box", [])),
            xdata_summary=dict(data.get("xdata_summary", {})),
            extension_dictionary_keys=list(data.get("extension_dictionary_keys", [])),
            warnings=list(data.get("warnings", [])),
        )


# ════════════════════════════════════════════════════════════════
# 统计类型
# ════════════════════════════════════════════════════════════════

@dataclass
class EntityStatistics:
    """实体分类统计。"""
    total_entities: int = 0
    basic_cad_count: int = 0
    tianzheng_object_count: int = 0
    pipe_count: int = 0
    valve_count: int = 0
    fitting_count: int = 0
    dimension_count: int = 0
    unknown_proxy_count: int = 0
    model_space_count: int = 0
    paper_space_count: int = 0
    object_name_distribution: dict[str, int] = field(default_factory=dict)
    layer_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entities": self.total_entities,
            "basic_cad_count": self.basic_cad_count,
            "tianzheng_object_count": self.tianzheng_object_count,
            "pipe_count": self.pipe_count,
            "valve_count": self.valve_count,
            "fitting_count": self.fitting_count,
            "dimension_count": self.dimension_count,
            "unknown_proxy_count": self.unknown_proxy_count,
            "model_space_count": self.model_space_count,
            "paper_space_count": self.paper_space_count,
            "object_name_distribution": dict(self.object_name_distribution),
            "layer_distribution": dict(self.layer_distribution),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityStatistics":
        return cls(
            total_entities=int(data.get("total_entities", 0)),
            basic_cad_count=int(data.get("basic_cad_count", 0)),
            tianzheng_object_count=int(data.get("tianzheng_object_count", 0)),
            pipe_count=int(data.get("pipe_count", 0)),
            valve_count=int(data.get("valve_count", 0)),
            fitting_count=int(data.get("fitting_count", 0)),
            dimension_count=int(data.get("dimension_count", 0)),
            unknown_proxy_count=int(data.get("unknown_proxy_count", 0)),
            model_space_count=int(data.get("model_space_count", 0)),
            paper_space_count=int(data.get("paper_space_count", 0)),
            object_name_distribution=dict(data.get("object_name_distribution", {})),
            layer_distribution=dict(data.get("layer_distribution", {})),
        )

# ════════════════════════════════════════════════════════════════
# 给排水系统与管网摘要
# ════════════════════════════════════════════════════════════════

@dataclass
class WaterSupplySystem:
    """单个给排水系统 (给水 / 排水 / 消防 / 喷淋)。"""
    system_type: str = "unknown"
    pipes: list[PipeSegment] = field(default_factory=list)
    valves: list[ValveInfo] = field(default_factory=list)
    fittings: list[FittingInfo] = field(default_factory=list)
    annotations: list[DimensionInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_type": self.system_type,
            "pipes": [p.to_dict() for p in self.pipes],
            "valves": [v.to_dict() for v in self.valves],
            "fittings": [f.to_dict() for f in self.fittings],
            "annotations": [a.to_dict() for a in self.annotations],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WaterSupplySystem":
        return cls(
            system_type=str(data.get("system_type", "unknown")),
            pipes=[PipeSegment.from_dict(p) for p in data.get("pipes", [])],
            valves=[ValveInfo.from_dict(v) for v in data.get("valves", [])],
            fittings=[FittingInfo.from_dict(f) for f in data.get("fittings", [])],
            annotations=[DimensionInfo.from_dict(a) for a in data.get("annotations", [])],
            warnings=list(data.get("warnings", [])),
        )


@dataclass
class PipeNetworkSummary:
    """管网图摘要。"""
    node_count: int = 0
    edge_count: int = 0
    connected_component_count: int = 0
    system_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "connected_component_count": self.connected_component_count,
            "system_summaries": dict(self.system_summaries),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipeNetworkSummary":
        return cls(
            node_count=int(data.get("node_count", 0)),
            edge_count=int(data.get("edge_count", 0)),
            connected_component_count=int(data.get("connected_component_count", 0)),
            system_summaries=dict(data.get("system_summaries", {})),
        )


# ════════════════════════════════════════════════════════════════
# 完整扫描结果
# ════════════════════════════════════════════════════════════════

@dataclass
class DWGScanResult:
    """天正 DWG 完整扫描结果。"""
    source_dwg: str = ""
    scan_timestamp: str = ""
    tianzheng_detected: bool = False
    tianzheng_version: str = ""
    entity_statistics: EntityStatistics = field(default_factory=EntityStatistics)
    systems: list[WaterSupplySystem] = field(default_factory=list)
    pipe_network_summary: PipeNetworkSummary = field(default_factory=PipeNetworkSummary)
    proxy_objects: list[UnknownProxyInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dwg": self.source_dwg,
            "scan_timestamp": self.scan_timestamp,
            "tianzheng_detected": self.tianzheng_detected,
            "tianzheng_version": self.tianzheng_version,
            "entity_statistics": self.entity_statistics.to_dict(),
            "systems": [s.to_dict() for s in self.systems],
            "pipe_network_summary": self.pipe_network_summary.to_dict(),
            "proxy_objects": [p.to_dict() for p in self.proxy_objects],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DWGScanResult":
        return cls(
            source_dwg=str(data.get("source_dwg", "")),
            scan_timestamp=str(data.get("scan_timestamp", "")),
            tianzheng_detected=bool(data.get("tianzheng_detected", False)),
            tianzheng_version=str(data.get("tianzheng_version", "")),
            entity_statistics=EntityStatistics.from_dict(data.get("entity_statistics", {})),
            systems=[WaterSupplySystem.from_dict(s) for s in data.get("systems", [])],
            pipe_network_summary=PipeNetworkSummary.from_dict(data.get("pipe_network_summary", {})),
            proxy_objects=[UnknownProxyInfo.from_dict(p) for p in data.get("proxy_objects", [])],
            warnings=list(data.get("warnings", [])),
        )

    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save_json(self, path: str) -> None:
        """保存为 JSON 文件。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "DWGScanResult":
        """从 JSON 文件加载。"""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
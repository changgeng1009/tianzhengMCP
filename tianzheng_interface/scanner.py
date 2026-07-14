
"""天正给排水接口层 — DWG 一键扫描器

Phase M1: 纯数据流水线，不连接 AutoCAD。

扫描流程:
1. 实体分类 (ProxyObjectHandler)
2. 统计数据 (EntityStatistics)
3. 系统分组 (WaterSupplySystem 按 system_type)
4. 管网摘要 (PipeNetworkSummary)
5. 报告生成 (report_builder)

约束:
- 禁止连接 AutoCAD
- 禁止打开 DWG
- 禁止执行天正命令
- 所有操作 dry-run only
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from tianzheng_interface.model import (
    DWGScanResult,
    EntityStatistics,
    WaterSupplySystem,
    PipeNetworkSummary,
    PipeSegment,
    ValveInfo,
    FittingInfo,
    DimensionInfo,
    UnknownProxyInfo,
    Point3D,
)
from tianzheng_interface.proxy_handler import ProxyObjectHandler, ProxyClassification

logger = logging.getLogger(__name__)


class DWGScanner:
    """天正 DWG 一键扫描器 — 纯数据流水线。

    Phase M1 模式: dry-run only，不连接 AutoCAD。
    接受外部提供的已分类实体和语义模型数据，组装完整的 DWGScanResult。
    """

    def __init__(self, source_dwg: str = ""):
        """初始化扫描器。

        Args:
            source_dwg: 源 DWG 文件名或路径（可选，仅用于报告标识）。
        """
        self.source_dwg = source_dwg
        self._handler = ProxyObjectHandler()

    # ── 入口 ───────────────────────────────────────────────

    def scan(
        self,
        entities: list[dict[str, Any]],
        pipes: list[dict[str, Any]] | None = None,
        valves: list[dict[str, Any]] | None = None,
        fittings: list[dict[str, Any]] | None = None,
        dimensions: list[dict[str, Any]] | None = None,
        unknown_proxies: list[dict[str, Any]] | None = None,
        pipe_network_data: dict[str, Any] | None = None,
        tianzheng_detected: bool = False,
        tianzheng_version: str = "",
    ) -> DWGScanResult:
        """执行完整扫描流水线。

        Args:
            entities: 原始实体列表，每条含 object_name/layer/handle。
            pipes: 已解析的管道数据 (可选)。
            valves: 已解析的阀门数据 (可选)。
            fittings: 已解析的管件数据 (可选)。
            dimensions: 已解析的标注数据 (可选)。
            unknown_proxies: 未识别对象数据 (可选)。
            pipe_network_data: 管网图数据 (可选)。
            tianzheng_detected: 是否检测到天正环境。
            tianzheng_version: 天正版本字符串。

        Returns:
            DWGScanResult 完整扫描结果。
        """
        # 1) 分类
        classifications = self._classify_entities(entities)

        # 2) 统计
        statistics = self._build_statistics(classifications)

        # 3) 系统分组
        pipe_objs = self._parse_pipes(pipes or [])
        valve_objs = self._parse_valves(valves or [])
        fitting_objs = self._parse_fittings(fittings or [])
        dim_objs = self._parse_dimensions(dimensions or [])
        proxy_objs = self._parse_unknown(unknown_proxies or [])

        systems = self._group_by_system(
            pipe_objs, valve_objs, fitting_objs, dim_objs
        )

        # 4) 管网摘要
        network_summary = self._build_network_summary(
            pipe_network_data, systems
        )

        # 5) 汇总警告
        all_warnings: list[str] = []
        for c in classifications:
            all_warnings.extend(c.warnings)
        for p in pipe_objs:
            all_warnings.extend(p.warnings)
        for v in valve_objs:
            all_warnings.extend(v.warnings)
        for f in fitting_objs:
            all_warnings.extend(f.warnings)

        return DWGScanResult(
            source_dwg=self.source_dwg,
            scan_timestamp=datetime.now(timezone.utc).isoformat(),
            tianzheng_detected=tianzheng_detected,
            tianzheng_version=tianzheng_version,
            entity_statistics=statistics,
            systems=systems,
            pipe_network_summary=network_summary,
            proxy_objects=proxy_objs,
            warnings=all_warnings,
        )

    def scan_from_semantic_model(
        self,
        semantic_model: dict[str, Any],
        classifications: list[ProxyClassification] | None = None,
        pipe_network_data: dict[str, Any] | None = None,
    ) -> DWGScanResult:
        """从已构建的语义模型创建扫描结果。

        Args:
            semantic_model: tianzheng_semantic_model 格式的字典。
            classifications: 预分类结果 (可选)。
            pipe_network_data: 预构建的管网图数据 (可选)。
        """
        pipes_data = semantic_model.get("pipes", [])
        valves_data = semantic_model.get("valves", [])
        fittings_data = semantic_model.get("fittings", [])
        dimensions_data = semantic_model.get("annotations", [])
        all_entities = semantic_model.get("entities", [])

        return self.scan(
            entities=all_entities,
            pipes=pipes_data,
            valves=valves_data,
            fittings=fittings_data,
            dimensions=dimensions_data,
            unknown_proxies=semantic_model.get("unknown_objects", []),
            pipe_network_data=pipe_network_data,
            tianzheng_detected=semantic_model.get("tianzheng_detected", False),
            tianzheng_version=semantic_model.get("tianzheng_version", ""),
        )

    # ── 分类 ───────────────────────────────────────────────

    def _classify_entities(
        self,
        entities: list[dict[str, Any]],
    ) -> list[ProxyClassification]:
        """使用 ProxyObjectHandler 批量分类。"""
        return self._handler.classify_batch(entities)

    # ── 统计 ───────────────────────────────────────────────

    def _build_statistics(
        self,
        classifications: list[ProxyClassification],
    ) -> EntityStatistics:
        """根据分类结果构建统计信息。"""
        stats = EntityStatistics()
        stats.total_entities = len(classifications)

        obj_name_counter: Counter[str] = Counter()
        layer_counter: Counter[str] = Counter()

        for c in classifications:
            obj_name_counter[c.object_name] += 1
            layer_counter[c.layer] += 1

            if c.is_basic_cad:
                stats.basic_cad_count += 1
            elif c.is_tianzheng:
                stats.tianzheng_object_count += 1
            elif c.classification == "unknown_proxy":
                stats.unknown_proxy_count += 1

        # 管/阀/件/标注计数由后续解析填充
        stats.object_name_distribution = dict(obj_name_counter)
        stats.layer_distribution = dict(layer_counter)
        return stats

    # ── 解析 ───────────────────────────────────────────────

    def _parse_pipes(self, raw: list[dict[str, Any]]) -> list[PipeSegment]:
        result: list[PipeSegment] = []
        for item in raw:
            try:
                result.append(PipeSegment.from_dict(item))
            except Exception:
                logger.warning("无法解析管道数据: %s", item.get("handle", "?"))
        return result

    def _parse_valves(self, raw: list[dict[str, Any]]) -> list[ValveInfo]:
        result: list[ValveInfo] = []
        for item in raw:
            try:
                result.append(ValveInfo.from_dict(item))
            except Exception:
                logger.warning("无法解析阀门数据: %s", item.get("handle", "?"))
        return result

    def _parse_fittings(self, raw: list[dict[str, Any]]) -> list[FittingInfo]:
        result: list[FittingInfo] = []
        for item in raw:
            try:
                result.append(FittingInfo.from_dict(item))
            except Exception:
                logger.warning("无法解析管件数据: %s", item.get("handle", "?"))
        return result

    def _parse_dimensions(self, raw: list[dict[str, Any]]) -> list[DimensionInfo]:
        result: list[DimensionInfo] = []
        for item in raw:
            try:
                result.append(DimensionInfo.from_dict(item))
            except Exception:
                logger.warning("无法解析标注数据: %s", item.get("handle", "?"))
        return result

    def _parse_unknown(self, raw: list[dict[str, Any]]) -> list[UnknownProxyInfo]:
        result: list[UnknownProxyInfo] = []
        for item in raw:
            try:
                result.append(UnknownProxyInfo.from_dict(item))
            except Exception:
                logger.warning("无法解析未知对象: %s", item.get("handle", "?"))
        return result

    # ── 系统分组 ───────────────────────────────────────────

    def _group_by_system(
        self,
        pipes: list[PipeSegment],
        valves: list[ValveInfo],
        fittings: list[FittingInfo],
        dimensions: list[DimensionInfo],
    ) -> list[WaterSupplySystem]:
        """按 system_type 将实体分组为 WaterSupplySystem 列表。"""
        sys_map: dict[str, WaterSupplySystem] = {}

        # 处理管道
        for p in pipes:
            st = p.system_type or "unknown"
            self._ensure_system(sys_map, st).pipes.append(p)

        # 处理阀门
        for v in valves:
            st = v.system_type or "unknown"
            self._ensure_system(sys_map, st).valves.append(v)

        # 处理管件
        for f in fittings:
            st = f.system_type or "unknown"
            self._ensure_system(sys_map, st).fittings.append(f)

        # 处理标注（标注可能属于特定系统或通用）
        for d in dimensions:
            st = "通用标注"
            self._ensure_system(sys_map, st).annotations.append(d)

        # 收集警告
        for st, sys_obj in sys_map.items():
            if st == "unknown":
                sys_obj.warnings.append(
                    f"存在 {len(sys_obj.pipes)} 条管道的系统类型为 unknown"
                )

        return sorted(sys_map.values(), key=lambda s: len(s.pipes), reverse=True)

    @staticmethod
    def _ensure_system(
        sys_map: dict[str, WaterSupplySystem],
        system_type: str,
    ) -> WaterSupplySystem:
        if system_type not in sys_map:
            sys_map[system_type] = WaterSupplySystem(system_type=system_type)
        return sys_map[system_type]

    # ── 管网摘要 ───────────────────────────────────────────

    def _build_network_summary(
        self,
        network_data: dict[str, Any] | None,
        systems: list[WaterSupplySystem],
    ) -> PipeNetworkSummary:
        """从管网图数据或系统列表构建管网摘要。"""
        if network_data:
            return PipeNetworkSummary.from_dict(network_data)

        # 从系统列表推导基本摘要
        node_count = 0
        edge_count = 0
        comp_count = 0
        system_summaries: dict[str, dict[str, Any]] = {}

        for sys_obj in systems:
            pipes_n = len(sys_obj.pipes)
            valves_n = len(sys_obj.valves)
            fittings_n = len(sys_obj.fittings)
            edge_count += pipes_n
            node_count += pipes_n * 2  # 每条管道 2 个端点（粗略估计）

            if pipes_n > 0:
                comp_count += 1

            system_summaries[sys_obj.system_type] = {
                "pipes": pipes_n,
                "valves": valves_n,
                "fittings": fittings_n,
                "annotations": len(sys_obj.annotations),
            }

        return PipeNetworkSummary(
            node_count=node_count,
            edge_count=edge_count,
            connected_component_count=comp_count,
            system_summaries=system_summaries,
        )


# ── 便捷工厂函数 ──────────────────────────────────────────

def scan_empty(source_dwg: str = "") -> DWGScanResult:
    """生成一个空的扫描结果（用于测试/占位）。"""
    return DWGScanResult(
        source_dwg=source_dwg,
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
    )


def quick_scan(
    entities: list[dict[str, Any]],
    source_dwg: str = "",
) -> DWGScanResult:
    """快速扫描 — 只输入实体列表，其余默认。"""
    scanner = DWGScanner(source_dwg=source_dwg)
    return scanner.scan(entities=entities)

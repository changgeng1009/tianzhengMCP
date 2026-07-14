
"""天正给排水接口层 — 报告生成器

Phase M1: Markdown + JSON 双格式报告。

约束:
- 纯数据转换，不访问 AutoCAD/DWG。
- 不导入 win32com。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from tianzheng_interface.model import DWGScanResult


# ── Markdown 模板 ─────────────────────────────────────────

MD_TEMPLATE = """# 天正 DWG 扫描报告

**源文件**: {source_dwg}
**扫描时间**: {scan_timestamp}
**天正环境**: {tianzheng_status}

{toc}

---

## 1. 实体统计

| 指标 | 数量 |
|------|------|
| 实体总数 | {total_entities} |
| 基础 CAD 实体 | {basic_cad_count} |
| 天正对象 | {tianzheng_object_count} |
| 管道 (pipe) | {pipe_count} |
| 阀门 (valve) | {valve_count} |
| 管件 (fitting) | {fitting_count} |
| 标注 (dimension) | {dimension_count} |
| 未知代理对象 | {unknown_proxy_count} |

{object_name_table}

{layer_table}

---

## 2. 系统分组

{systems_section}

---

## 3. 管网摘要

| 指标 | 数量 |
|------|------|
| 节点数 | {node_count} |
| 边数 (管道) | {edge_count} |
| 连通分量 | {connected_component_count} |

{network_system_table}

---

## 4. 警告

{warnings_section}

---

*报告由天正 MCP 接口系统自动生成 | Phase M1 — Dry Run Only*
"""


@dataclass
class ReportOutput:
    """报告输出结构。"""
    markdown: str = ""
    json_str: str = ""
    markdown_path: str = ""
    json_path: str = ""


class ReportBuilder:
    """天正 DWG 扫描报告生成器。

    支持:
    - build_markdown_report(): 生成 Markdown 格式报告
    - build_json_report(): 生成 JSON 格式报告
    - save_report(): 保存 md + json 到指定目录
    """

    def build_markdown_report(self, scan_result: DWGScanResult) -> str:
        """将 DWGScanResult 转换为 Markdown 报告文本。"""
        stats = scan_result.entity_statistics
        network = scan_result.pipe_network_summary

        # 天正状态
        tianzheng_status = (
            f"已检测 — {scan_result.tianzheng_version}"
            if scan_result.tianzheng_detected
            else "未检测（dry-run / mock 模式）"
        )

        # 目录
        toc = self._build_toc(scan_result)

        # 对象分布表
        obj_table = self._build_dist_table(
            "### 对象类型分布",
            stats.object_name_distribution,
        )

        # 图层分布表
        layer_table = self._build_dist_table(
            "### 图层分布 (Top 20)",
            dict(
                sorted(
                    stats.layer_distribution.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:20]
            ),
        )

        # 系统分组段落
        systems_section = self._build_systems_section(scan_result)

        # 管网系统表
        network_system_table = self._build_network_system_table(network)

        # 警告段落
        warnings_section = self._build_warnings_section(scan_result)

        md = MD_TEMPLATE.format(
            source_dwg=scan_result.source_dwg or "(未指定)",
            scan_timestamp=scan_result.scan_timestamp or "(未知)",
            tianzheng_status=tianzheng_status,
            toc=toc,
            total_entities=stats.total_entities,
            basic_cad_count=stats.basic_cad_count,
            tianzheng_object_count=stats.tianzheng_object_count,
            pipe_count=stats.pipe_count,
            valve_count=stats.valve_count,
            fitting_count=stats.fitting_count,
            dimension_count=stats.dimension_count,
            unknown_proxy_count=stats.unknown_proxy_count,
            object_name_table=obj_table,
            layer_table=layer_table,
            systems_section=systems_section,
            node_count=network.node_count,
            edge_count=network.edge_count,
            connected_component_count=network.connected_component_count,
            network_system_table=network_system_table,
            warnings_section=warnings_section,
        )

        return md.strip() + "\n"

    def build_json_report(self, scan_result: DWGScanResult) -> str:
        """将 DWGScanResult 序列化为 JSON 字符串。"""
        return scan_result.to_json(indent=2)

    def save_report(
        self,
        scan_result: DWGScanResult,
        output_dir: str = "reports",
        basename: str | None = None,
    ) -> ReportOutput:
        """保存 Markdown + JSON 双格式报告。

        Args:
            scan_result: 扫描结果。
            output_dir: 输出目录。
            basename: 基础文件名 (不含扩展名)，默认自动生成。

        Returns:
            ReportOutput 含两格式路径和内容。
        """
        os.makedirs(output_dir, exist_ok=True)

        if basename is None:
            ts = scan_result.scan_timestamp.replace(":", "-")[:19] if scan_result.scan_timestamp else "scan"
            basename = f"tianzheng_scan_{ts}"

        md_content = self.build_markdown_report(scan_result)
        json_content = self.build_json_report(scan_result)

        md_path = os.path.join(output_dir, f"{basename}.md")
        json_path = os.path.join(output_dir, f"{basename}.json")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_content)

        return ReportOutput(
            markdown=md_content,
            json_str=json_content,
            markdown_path=md_path,
            json_path=json_path,
        )

    # ── 辅助方法 ───────────────────────────────────────────

    def _build_toc(self, scan_result: DWGScanResult) -> str:
        """构建目录。"""
        lines = [
            "## 目录",
            "",
            "1. [实体统计](#1-实体统计)",
            "2. [系统分组](#2-系统分组)",
            "3. [管网摘要](#3-管网摘要)",
            "4. [警告](#4-警告)",
            "",
        ]
        return "\n".join(lines)

    def _build_dist_table(
        self,
        heading: str,
        dist: dict[str, int],
    ) -> str:
        """构建分布表格。"""
        if not dist:
            return f"{heading}\n\n*(无数据)*\n"

        rows = [heading, "", "| 名称 | 数量 |", "|------|------|"]
        for name, count in dist.items():
            rows.append(f"| {name} | {count} |")
        rows.append("")
        return "\n".join(rows)

    def _build_systems_section(self, scan_result: DWGScanResult) -> str:
        """构建系统分组段落。"""
        if not scan_result.systems:
            return "*(未检测到系统分组)*\n"

        blocks: list[str] = []
        for sys_obj in scan_result.systems:
            pipe_n = len(sys_obj.pipes)
            valve_n = len(sys_obj.valves)
            fit_n = len(sys_obj.fittings)
            ann_n = len(sys_obj.annotations)

            block = f"### {sys_obj.system_type}\n"
            block += f"- 管道: {pipe_n} | 阀门: {valve_n} | 管件: {fit_n} | 标注: {ann_n}\n"

            if sys_obj.warnings:
                block += "- **警告**:\n"
                for w in sys_obj.warnings:
                    block += f"  - ⚠ {w}\n"

            if pipe_n > 0:
                block += "\n**管道明细** (前 10 条):\n\n"
                block += "| Handle | DN | 系统 | 标高(起/终) |\n"
                block += "|--------|----|------|-------------|\n"
                for p in sys_obj.pipes[:10]:
                    dn = p.dn or "?"
                    elev = (
                        f"{p.elevation_start or '?'}/{p.elevation_end or '?'}"
                    )
                    block += f"| {p.handle} | {dn} | {p.system_type} | {elev} |\n"
                if pipe_n > 10:
                    block += f"| ... | ... | ... | (共 {pipe_n} 条) |\n"

            block += "\n"
            blocks.append(block)

        return "\n".join(blocks)

    def _build_network_system_table(
        self,
        network_summary: Any,
    ) -> str:
        """构建管网系统详细表。"""
        system_summaries = getattr(network_summary, "system_summaries", {})
        if not system_summaries:
            return "*(无管网系统数据)*\n"

        rows = [
            "### 各系统管网统计",
            "",
            "| 系统 | 管道 | 阀门 | 管件 | 标注 |",
            "|------|------|------|------|------|",
        ]
        for sys_name, info in sorted(system_summaries.items()):
            p = info.get("pipes", 0)
            v = info.get("valves", 0)
            f = info.get("fittings", 0)
            a = info.get("annotations", 0)
            rows.append(f"| {sys_name} | {p} | {v} | {f} | {a} |")
        rows.append("")
        return "\n".join(rows)

    def _build_warnings_section(self, scan_result: DWGScanResult) -> str:
        """构建警告段落。"""
        all_warnings = list(scan_result.warnings)

        for sys_obj in scan_result.systems:
            for w in sys_obj.warnings:
                all_warnings.append(f"[{sys_obj.system_type}] {w}")

        for proxy in scan_result.proxy_objects:
            for w in proxy.warnings:
                all_warnings.append(f"[{proxy.handle}] {w}")

        if not all_warnings:
            return "✅ 无警告。\n"

        lines = [f"共 {len(all_warnings)} 条警告:\n", ""]
        for i, w in enumerate(all_warnings, 1):
            lines.append(f"{i}. ⚠ {w}")
        lines.append("")
        return "\n".join(lines)


# ── 便捷函数 ──────────────────────────────────────────────

def build_markdown_report(scan_result: DWGScanResult) -> str:
    """便捷函数：生成 Markdown 报告。"""
    return ReportBuilder().build_markdown_report(scan_result)


def build_json_report(scan_result: DWGScanResult) -> str:
    """便捷函数：生成 JSON 报告。"""
    return ReportBuilder().build_json_report(scan_result)


def save_report(
    scan_result: DWGScanResult,
    output_dir: str = "reports",
    basename: str | None = None,
) -> ReportOutput:
    """便捷函数：保存双格式报告。"""
    return ReportBuilder().save_report(scan_result, output_dir, basename)

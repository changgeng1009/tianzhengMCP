# 天正给排水接口层 API 文档

> Phase M4 — 覆盖 tianzheng_interface/ 全部公开接口

## 模块总览

| 模块 | 职责 | 公开类/函数 |
|------|------|------------|
| `model.py` | 数据类型 | Point3D, PipeSegment, ValveInfo, FittingInfo, DimensionInfo, UnknownProxyInfo, EntityStatistics, WaterSupplySystem, PipeNetworkSummary, DWGScanResult |
| `action_schema.py` | Action 定义 | ActionDefinition, ActionBatch, ActionConflict, DependencyGraph, ConflictType, RiskLevel, VALID_ACTION_TYPES |
| `proxy_handler.py` | 实体分类 | ProxyObjectHandler, ProxyClassification, ProxyDiscovery, classify_with_confidence |
| `dry_run_engine.py` | 干运行引擎 | DryRunEngine, EnhancedDryRunEngine, ConflictDetector, DryRunResult |
| `scanner.py` | 一键扫描 | DWGScanner, scan_empty, quick_scan |
| `report_builder.py` | 报告生成 | ReportBuilder, ReportOutput, build_markdown_report, build_json_report, save_report |

## model.py

### DWGScanResult
完整扫描结果。包含 source_dwg、scan_timestamp、tianzheng_detected、entity_statistics、systems、pipe_network_summary、proxy_objects、warnings。

主要方法：
- `to_dict()` → dict
- `to_json(indent=2)` → str
- `save_json(path)` → None
- `from_json(path)` → DWGScanResult

### PipeSegment
管道语义模型。字段：handle、object_name、semantic_type、layer、system_type、dn、start_point、end_point、length、elevation_start、elevation_end、warnings。

### EntityStatistics
实体分类统计。字段：total_entities、basic_cad_count、tianzheng_object_count、pipe_count、valve_count、fitting_count、dimension_count、unknown_proxy_count、object_name_distribution、layer_distribution。

## action_schema.py

### ActionDefinition
单个 Action 定义。核心字段：
- `action_type`: add_pipe | add_valve | add_fitting | add_label | connect_pipe | update_diameter | update_elevation | update_system_type | move_candidate | delete_candidate | review_only
- `ready_to_execute`: Phase M1-M4 强制 False
- `requires_confirmation`: 强制 True
- `risk_level`: LOW | MEDIUM | HIGH | CRITICAL

### ActionBatch
批量操作。`from_actions(actions)` 批量统计，含 conflicts、dependencies、execution_order。

### ConflictDetector
冲突检测器。4 种检测：
- `detect_spatial()` — 空间重叠（容差 50mm）
- `detect_diameter()` — 管径不匹配（容差 5mm）
- `detect_elevation()` — 标高冲突（容差 100mm）
- `detect_system_mismatch()` — 系统类型不匹配

## scanner.py

### DWGScanner
```python
scanner = DWGScanner(source_dwg="target.dwg")
result = scanner.scan(
    entities=entities,
    pipes=pipes,
    valves=valves,
    fittings=fittings,
    dimensions=dimensions,
    unknown_proxies=proxies,
    pipe_network_data=network,
    tianzheng_detected=True,
    tianzheng_version="T30 V1.0",
)
```

便捷函数：`scan_empty()`, `quick_scan(entities, source_dwg)`

## report_builder.py

### ReportBuilder
```python
builder = ReportBuilder()
md = builder.build_markdown_report(scan_result)
json_str = builder.build_json_report(scan_result)
output = builder.save_report(scan_result, output_dir="reports")
```

## 安全约束

所有 tianzheng_interface 模块：
- 禁止连接 AutoCAD
- 禁止打开 DWG
- 禁止 SendCommand
- 禁止执行天正命令
- 所有 action ready_to_execute=False

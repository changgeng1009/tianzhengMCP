> redacted / not_rerun: Historical artifact redacted for redistribution. Captured drawing geometry, native object properties, handles and input fingerprints are withheld. This cleanup did not connect to CAD or rerun/revalidate the original assertions. Historical outcomes are not current acceptance or synthetic-run evidence.

> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

﻿# 天正给排水接口层 — 混合架构方案 + Phase 1 实施计划

## 概述

本文档设计一个 "AutoCAD 基础图元 + 天正给排水语义对象" 的混合架构，基于已安装并验证的 `autocad-dwg-redraw` skill 和已完成的 Phase 1-6.4 项目基础设施，扩展天正给排水接口层。

当前阶段为 **Phase 1: 只读分析 + 接口框架设计**，严格禁止任何写 DWG 操作。

---

## 第一部分：三层架构分工

### 1. 原 skill (autocad-dwg-redraw) 负责

| 职责 | 说明 |
|------|------|
| 通用 DWG 分析与提示生成 | `dwg_prompt_builder.py` 的 profile 模式 (图层/实体/块/样式统表) 用于天正 DWG 的初步实体清单扫描 |
| 基础 CAD 实体精确复制 | `dwg_redraw.py` 的 `CopyObjects` 仅在非天正对象的辅助图元复制时使用 (如复制边框/图框/通用标注) |
| 报告模板结构 | Markdown 表格化报告模式借鉴用于天正分析报告 |

不可用于天正对象的部分: `CopyObjects` 批量复制天正智能对象；AutoLISP 重建天正对象 (无天正 API)。

### 2. 已有项目 MCP 接口负责

| 职责 | 说明 |
|------|------|
| AutoCAD COM 连接管理 | `cad/connection.py`: 多 ProgID 探测、多版本兼容 |
| 基础 CAD 实体读取 | `cad/reader.py`: 8 种类型 → `CurrentCADModel` JSON |
| 天正环境检测 | `tianzheng/environment.py`: MenuGroups/Caption/SupportPath |
| 天正对象语义读取 | `tianzheng/semantic_reader.py`: TDbPipe → pipe, TDbPipeValve → valve, TDbPipeFitting → fitting, TDbDimension2 → dimension |
| 管径深度探测 | `tianzheng/tdbpipe_deep_probe.py`: XData/ExtDict/TypeInfo/DNDiameter |
| 管道网络图构建 | `pipe_network/graph_builder.py`: nodes/edges/systems |
| 语义差异比较 | `semantic_diff/diff_engine.py`: add_pipe/remove_pipe 等 |
| 安全执行队列 | `execution/`: preview → confirm → execute |
| T30 写回预留 | `mcp/t30_writeback/`: 沙箱+事务+参数schema |

### 3. 新增天正接口层负责

| 职责 | 说明 |
|------|------|
| 天正 DWG 一键扫描 | 打开天正 DWG 后自动完成: 环境检测 → 实体分类 → 语义分析 → 管网图 → 报告 |
| 给排水语义模型输出 | 结构化 JSON: 系统分类 (给水/排水/消防/喷淋) + 管径分布 + 阀门/管件清单 |
| Action Schema 定义 | 定义天正给排水对象的 action schema (dry-run only): add_pipe/add_valve/modify_diameter 等 |
| Dry-run 报告生成 | 模拟执行计划、预测实体变更、标记风险、输出审核报告 |
| 天正对象 proxy 处理策略 | 统一 proxy/custom object 的读取/识别/归类逻辑 |
| 接口框架设计 | 定义新增模块的 API 契约、数据模型、文件组织 |
---

## 第二部分：天正 Proxy/Custom Object 处理策略

### 2.1 现状

天正 T30 V1.0 创建的对象 (TDbPipe, TDbPipeValve, TDbPipeFitting, TDbDimension2) 在 AutoCAD 中表现为 proxy entity (custom object)。它们有自定义 ObjectName，属性行为与基础 CAD 实体不同，内部状态通过 XData (TWT/TCH/TANGENT 等 RegAppName) 和 ExtensionDictionary 存储。

### 2.2 Phase 1 处理策略

```
Proxy/Custom Object 检测
  → ObjectName 匹配已知天正类型? (TDbPipe/TDbPipeValve/...)
    是 → 走 semantic_reader 专用路径 (已有)
    否 → 走通用检查器 inspect_entity() (已有)
  → COM 属性探测 (probe_entity_properties)
    成功 → 记录 known_properties
    失败 → 记录 failed_properties + 原因
  → XData 探测 (GetXData 多 AppName)
  → ExtensionDictionary 探测 (GetExtensionDictionary)
  → 归类为 unknown_tianzheng (保留 Handle/ObjectName/Layer/BBox)
    写入 dry-run 报告"待确认对象"列表
```

### 2.3 后续阶段 (Phase 2+) 策略方向

| 策略 | 适用场景 |
|------|----------|
| 通过 T30 API 创建新天正对象 | 新建 pipe/valve/fitting |
| 通过 COM 属性修改现有对象 | 修改直径/标高/系统类型 |
| 通过 Sandbox DWG + CopyObjects | 复制已验证安全的天正对象 |
| 回退为基础 CAD 图元 + 注释 | T30 API 不可用时的降级方案 |

---

## 第三部分：Phase 1 实施计划

### 3.1 总体原则

- 严禁修改 target.dwg
- 严禁运行 run_real_sandbox_acceptance.bat
- 严禁使用 dwg_redraw.py 的 CopyObjects 处理天正对象
- 严禁直接写 DWG
- 所有操作使用副本或 dry-run
- 所有输出写入 logs/、reports/、examples/、outputs/

### 3.2 新增模块清单

```
D:\ExampleWorkspace\天正\
├── tianzheng_interface/           # 新 天正给排水接口层
│   ├── __init__.py                # 模块导出
│   ├── scanner.py                 # 天正 DWG 一键扫描器
│   ├── model.py                   # 给排水语义模型 (dataclass)
│   ├── action_schema.py           # Action schema 定义 (dry-run 用)
│   ├── dry_run_engine.py          # Dry-run 模拟执行引擎
│   ├── report_builder.py          # 分析报告生成器 (Markdown + JSON)
│   └── proxy_handler.py           # Proxy/Custom object 统一处理
│
├── tests/                         # 新增测试
│   ├── test_tianzheng_scanner.py
│   ├── test_water_supply_model.py
│   ├── test_action_schema.py
│   ├── test_dry_run_engine.py
│   ├── test_proxy_handler.py
│   └── test_report_builder.py
│
├── examples/                      # 新增样例
│   ├── water_supply_semantic_model_sample.json
│   ├── action_schema_sample.json
│   ├── dry_run_report_sample.json
│   └── tianzheng_dwg_scan_report.md
│
├── config/                        # 新增配置
│   ├── tianzheng_system_types.json
│   └── tianzheng_action_templates.json
│
├── reports/                       # Phase 1 输出报告 (已生成)
│   ├── 01_project_structure_analysis.md
│   ├── 02_skill_capability_analysis.md
│   └── 03_combined_architecture_and_phase1_plan.md
│
└── logs/                          # 运行日志
    └── phase1_scan.log
```

### 3.3 新增模块设计

#### scanner.py — 天正 DWG 一键扫描器

```
class TianzhengDWGScanner:
    def scan(self, dwg_path: Path, *, use_copy: bool = True) -> ScanResult:
        完整扫描流程:
        1. 创建 DWG 副本 (如果 use_copy=True)
        2. 天正环境检测 (tianzheng/environment.py)
        3. DWG 基础实体扫描 (cad/reader.py + skill profile 模式)
        4. 天正对象语义分析 (tianzheng/semantic_reader.py)
        5. 管径分布统计
        6. 系统分类 (给水/排水/消防/喷淋)
        7. 管网图构建 (pipe_network/graph_builder.py)
        8. Action schema 生成 (dry-run 用)
        9. Dry-run 模拟执行
        10. 报告生成
```

输入: 天正 DWG 路径
输出: ScanResult (结构化 JSON + Markdown 报告)
关键安全措施: 始终在副本上操作 (use_copy=True)；scan() 内部禁止任何 COM 写操作

#### model.py — 给排水语义模型

```
@dataclass
class WaterSupplySystem:
    system_type: str          # 给水 / 排水 / 消防 / 喷淋 / unknown
    pipes: list[PipeSegment]
    valves: list[ValveInfo]
    fittings: list[FittingInfo]
    annotations: list[DimensionInfo]

@dataclass
class PipeSegment:
    handle: str
    dn: str | None            # DN25/DN50/DN100 (来自 DNDiameter)
    diameter_source: str      # "TDbPipe.DNDiameter" / "label_inference"
    start_point: Point3D | None
    end_point: Point3D | None
    length: float | None
    elevation_start: float | None
    elevation_end: float | None
    layer: str
    system_type: str
    connected_valves: list[str]
    connected_fittings: list[str]

@dataclass
class DWGScanResult:
    source_dwg: str
    scan_timestamp: str
    tianzheng_environment: dict
    entity_statistics: EntityStatistics
    systems: list[WaterSupplySystem]
    pipe_network_graph: dict
    proxy_objects: list[UnknownProxyInfo]
    action_schema: list[ActionDefinition]
    dry_run_result: DryRunResult
    warnings: list[str]
```

#### action_schema.py — Action Schema 定义

```
@dataclass
class ActionDefinition:
    action_id: str
    action_type: str          # add_pipe / add_valve / modify_diameter
    object_type: str          # TDbPipe / TDbPipeValve
    parameters: dict
    geometry: dict
    system: str | None
    dn: str | None
    layer: str | None
    confidence: float
    ready_to_execute: bool     # Phase 1 始终为 False
    requires_confirmation: bool
    warnings: list[str]
```

Phase 1 约束: 所有 action 的 ready_to_execute = False，requires_confirmation = True。

#### dry_run_engine.py — 干运行引擎

```
class DryRunEngine:
    def simulate(self, actions: list[ActionDefinition]) -> DryRunResult:
        模拟执行流程:
        1. 验证 action schema 完整性
        2. 检查冲突 (geometry overlap / layer conflict)
        3. 预估实体变更 (新增实体数/修改属性数)
        4. 标记风险 (proxy object / unsupported type / low confidence)
        5. 生成审核动作列表
```

#### report_builder.py — 报告生成器 (借鉴 skill 的 Markdown 报告模式)

报告结构:
1. DWG 指纹 (文件名/大小/版本/天正环境)
2. 实体分类统计 (基础CAD/天正对象/proxy对象)
3. 给排水系统分析 (给水/排水/消防/喷淋)
4. 管径分布表
5. 管网图摘要 (节点数/边数/连通分量)
6. Action Schema 清单
7. Dry-run 模拟结果
8. 风险与待确认项
9. 验证标准

#### proxy_handler.py — Proxy 对象处理

```
class ProxyObjectHandler:
    KNOWN_TIANZHENG_TYPES = {
        "TDbPipe", "TDbPipeValve", "TDbPipeFitting", "TDbDimension2"
    }
    def classify(self, entity) -> ProxyClassification
    def safe_read(self, entity) -> ProxyReadResult
    def is_modifiable(self, entity) -> bool  # Phase 1 始终 False
```

### 3.4 测试计划

#### 单元测试 (无需 AutoCAD)

| 测试文件 | 测试内容 |
|----------|----------|
| test_water_supply_model.py | WaterSupplySystem/PipeSegment 数据模型序列化/验证 |
| test_action_schema.py | ActionDefinition 校验、JSON 序列化、必填字段检查 |
| test_dry_run_engine.py | 模拟执行的冲突检测、变更预估、风险标记 |
| test_proxy_handler.py | Proxy 对象分类逻辑、已知天正类型匹配 |
| test_report_builder.py | Markdown/JSON 报告格式校验 |

#### 集成测试 (需 AutoCAD + 天正环境)

| 测试文件 | 测试内容 | 安全级别 |
|----------|----------|----------|
| test_tianzheng_scanner.py | 对副本 DWG 执行完整扫描流程 | 只读 (副本) |

#### 手工验证脚本

| 脚本 | 功能 |
|------|------|
| scripts/manual_tianzheng_scan.py | 交互式天正 DWG 扫描 (用户选择区域后扫描) |
| scripts/manual_dry_run_report.py | 基于扫描结果生成 dry-run 报告 |

### 3.5 样例数据

| 文件 | 内容 |
|------|------|
| examples/water_supply_semantic_model_sample.json | 完整给排水语义模型样例 |
| examples/action_schema_sample.json | Action 定义样例 (add_pipe/add_valve/...) |
| examples/dry_run_report_sample.json | Dry-run 模拟报告样例 |
| examples/tianzheng_dwg_scan_report.md | Markdown 扫描报告样例 |

### 3.6 天正环境探测流程

1. 连接 AutoCAD COM (cad/connection.py)
2. 检查 ActiveDocument 有效性
3. 检测天正环境 (tianzheng/environment.py):
   - Caption 是否包含 "T30天正给排水"
   - MenuGroups 是否包含 "TANGENT"
   - SupportPath 是否包含 tangent/twt30v1 路径
   - 输出 tianzheng_detected: true/false
4. 如果天正已检测到: 记录天正版本 + 可用 MenuGroups
5. 如果天正未检测到: 标记为"只支持基础 CAD 图元"

### 3.7 扫描图纸中的天正对象

1. 获取 ActiveDocument (副本)
2. 遍历 ModelSpace: 对每个实体调用 inspect_entity(entity)
3. 按 ObjectName 分类:
   - TDbPipe → pipe (semantic_reader.read_tdb_pipe)
   - TDbPipeValve → valve (semantic_reader.read_tdb_pipe_valve)
   - TDbPipeFitting → fitting (semantic_reader.read_tdb_pipe_fitting)
   - TDbDimension2 → dimension (semantic_reader.read_tdb_dimension)
   - AcDb* → basic_cad (cad/reader)
   - 其他 → unknown_custom (proxy_handler.classify)
4. 遍历 PaperSpace (相同逻辑)
5. 输出 EntityStatistics

### 3.8 生成给排水语义模型

1. 按 system_type 分组 (给水/排水/消防/喷淋):
   - 优先使用 TDbPipe.SysType
   - 回退使用 layer_inference (infer_system_type)
   - 标记 conflicts
2. 对每个系统构建 PipeSegment/Valves/Fittings/Annotations 列表
3. 构建管网图 (pipe_network/graph_builder): nodes/edges/systems/subgraphs
4. 输出 WaterSupplySystem 列表

### 3.9 生成 Action Schema

基于语义模型生成 dry-run action:
- 缺失管道 → add_pipe action
- 多余管道 → remove_pipe action (标记为 review_only)
- 管径不匹配 → modify_diameter action
- 标高不匹配 → modify_elevation action
- 系统类型不匹配 → modify_system_type action

每个 action: action_id 自动生成 UUID; ready_to_execute 强制 False; requires_confirmation 强制 True; confidence 基于匹配度计算。

### 3.10 生成 Dry-run 报告

1. 冲突检测: 空间冲突/图层冲突/管径冲突/连接冲突
2. 变更预估: 新增实体数/修改实体数/待审核实体数/不可执行操作数
3. 风险标记: proxy object/low confidence/unsupported operation/high risk geometry
4. 输出: Markdown 报告 (面向人工审核) + JSON 报告 (面向程序处理)

---

## 第四部分：安全约束检查清单

| # | 约束 | 状态 | 验证方式 |
|---|------|------|----------|
| 1 | 不得修改 target.dwg | ENFORCED | 所有操作在副本上执行或为 dry-run |
| 2 | 不得覆盖任何 DWG | ENFORCED | 输出使用 unique_output_path 模式 |
| 3 | 不得运行 run_real_sandbox_acceptance.bat | PROHIBITED | Phase 1 不引入真实写操作 |
| 4 | 不得使用 dwg_redraw.py 重建天正图纸 | PROHIBITED | Phase 1 仅只读扫描 |
| 5 | 所有探测使用副本或 dry-run | FOLLOWED | scanner.py 默认 use_copy=True |
| 6 | 输出写入 logs/reports/examples | FOLLOWED | 所有输出目标限定 |
| 7 | Action ready_to_execute 始终为 False | ENFORCED | action_schema.py 默认值 |
| 8 | DWG 副本写入独立 outputs/ 目录 | FOLLOWED | 与原 target 完全隔离 |

---

## 第五部分：实施优先级与里程碑

### Phase 1 里程碑

| 里程碑 | 内容 | 验收标准 |
|--------|------|----------|
| M1: 数据模型 | model.py + action_schema.py 完成 | 单元测试通过，JSON 样例生成 |
| M2: Proxy 处理 | proxy_handler.py 完成 | 已知类型正确分类，未知类型安全降级 |
| M3: DWG 扫描 | scanner.py 完成 | 对副本 DWG 扫描通过 (pytest) |
| M4: 干运行 | dry_run_engine.py 完成 | 模拟执行无异常，冲突检测覆盖 |
| M5: 报告 | report_builder.py 完成 | Markdown + JSON 双格式输出 |
| M6: 完整流程 | scanner→model→action→dry-run→report | 端到端手工脚本验证通过 |

### 不在 Phase 1 范围内

| 项目 | 原因 |
|------|------|
| T30 API 真实调用 | Phase 1 只读，不允许写 CAD |
| CopyObjects 天正对象复制 | 风险未知，需后续独立验证 |
| 真实执行任何 repair action | 需要 sandbox 环境 + 用户确认 |
| 修改 server.py 注册新 MCP 工具 | Phase 1 输出为离线分析工具，不接入 MCP |
| 生产 DWG 操作 | Phase 1 仅针对已知测试 DWG |

---

## 第六部分：后续方向 (Phase 2+)

Phase 1 完成后，后续阶段可逐步引入:

1. Phase 2: 对副本 DWG 运行沙箱验证 (CopyObjects 天正对象行为测试)
2. Phase 3: Action 真实执行 (sandbox DWG + T30 API + 事务回滚)
3. Phase 4: 接入 MCP 管线 (tianzheng_interface 工具注册到 server.py)
4. Phase 5: 完整自动审图补图管线 (reference → current → diff → repair → acceptance)

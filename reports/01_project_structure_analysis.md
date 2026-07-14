> redacted / not_rerun: Historical artifact redacted for redistribution. Captured drawing geometry, native object properties, handles and input fingerprints are withheld. This cleanup did not connect to CAD or rerun/revalidate the original assertions. Historical outcomes are not current acceptance or synthetic-run evidence.

> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

++ 项目结构分析报告
++ 生成日期: 2026-07-07

# 天正给排水项目 — Phase 1 项目结构分析报告

## 概述

本报告对 `D:\ExampleWorkspace\天正` 项目进行完整结构扫描与分析，识别已有模块、接口、测试、目标图纸和验收基础设施，为 Phase 1 "只读分析 + 接口框架设计" 提供事实基础。

---

## 一、目录结构总览

```
D:\ExampleWorkspace\天正/
├── server.py                  # FastMCP 主入口，注册所有 MCP 工具
├── ROADMAP.md                 # 项目路线图 (Phase 1 → Phase 7+)
├── README.md                  # 项目说明
├── requirements.txt           # Python 依赖 (pywin32 etc.)
├── logging_config.py          # 日志配置
├── scenario_template.json     # 场景模板
├── manual_confirmation.json   # 手工确认记录
│
├── cad/                       # ★ AutoCAD COM 通信层
├── tianzheng/                 # ★ 天正对象语义读取层
├── mcp/                       # ★ MCP 工具与管线核心
├── pipe_network/              # 管网图构建
├── semantic_diff/             # 语义差异比较
├── coordinate/                # 坐标映射与标定
├── vision/                    # 视觉识别引擎 (旧版)
├── tools/                     # MCP 工具注册层
├── execution/                 # 安全执行队列
├── scripts/                   # 手工测试脚本 (14 个)
├── tests/                     # 单元/集成测试 (100+ 文件)
├── config/                    # JSON 配置文件
├── examples/                  # JSON 样例输出 (20 个)
├── docs/                      # 设计文档
├── acceptance_pack/           # 验收脚本与模板
├── artifacts/                 # 验收报告与诊断数据
├── artifactsreal.test.001/    # ★ 真实天正 DWG 测试数据
├── cad_compare/               # CAD 差异比较引擎
├── roi/                       # ROI 区域过滤
├── reference/                 # 参考数据
├── .agents/                   # 子 agent 配置
└── .codex/                    # Codex 配置
```

---

## 二、核心模块详细分析

### 2.1 `cad/` — AutoCAD COM 通信层 (Phase 2-5)

| 文件 | 行数 | 职责 |
|------|------|------|
| `connection.py` | ~170 | COM 连接管理、ProgID 探测 (`AutoCAD.Application.25.1`) |
| `reader.py` | ~300 | **基础 CAD 实体读取** (Line/Polyline/Circle/Arc/Text/MText/BlockRef/Dimension)，输出 `CurrentCADModel` JSON |
| `document.py` | ~90 | 文档上下文管理 |
| `document_resolver.py` | ~220 | ActiveDocument 解析与有效性校验 |
| `entities.py` | ~180 | 实体服务封装 |
| `geometry.py` | ~60 | 几何工具 (点归一化、坐标转换) |
| `layers.py` | ~35 | 图层读取 |
| `blocks.py` | ~25 | 块属性读取 |
| `commands.py` | ~35 | SendCommand 封装 |
| `__init__.py` | — | 导出: ConnectionManager, CommandService, DocumentService, EntityService |

**关键能力**: 只读基础 CAD 图元；识别 ObjectName → entity_type 映射；输出结构化 `CurrentCADModel`。

### 2.2 `tianzheng/` — 天正对象语义读取层 (Phase 6.0-6.2+)

| 文件 | 行数 | 职责 |
|------|------|------|
| `environment.py` | ~150 | 天正 T30 环境检测 (MenuGroups, SupportPath, Caption) |
| `object_inspector.py` | ~250 | 通用对象检查器: Handle/ObjectName/Layer/BoundingBox/XData/ExtensionDictionary/TypeInfo |
| `semantic_reader.py` | ~600 | **核心语义读取器**: TDbPipe → pipe, TDbPipeValve → valve, TDbPipeFitting → fitting, TDbDimension2 → dimension |
| `tdbpipe_deep_probe.py` | ~430 | TDbPipe 深度探测: 属性列表/XData 多 AppName/ExtensionDictionary/COM TypeInfo/dir() 可疑字段筛选 |
| `diameter_label_reader.py` | ~220 | DN/De/φ/D 管径文字识别与标准化 |
| `pipe_label_association.py` | ~150 | 管径文字与 TDbPipe 关联 (diameter_candidates) |
| `selection_reader.py` | ~130 | SelectionSet 框选对象读取 |
| `selection_utils.py` | ~120 | SelectionSet 临时创建/安全删除 |
| `visibility.py` | ~110 | 对象可见性诊断 |
| `__init__.py` | — | 导出: TianzhengEnvironmentDetector, inspect_entity |

**关键能力**: 
- 识别并读取 4 类天正自定义对象 (TDbPipe/TDbPipeValve/TDbPipeFitting/TDbDimension2)
- 通过 COM 属性探测、XData (多 RegAppName)、ExtensionDictionary 读取天正内部数据
- `DNDiameter` → `DNxxx` 标准化 (已真实验证通过)
- 管径文字与管线关联 (diameter_candidates, 默认 need_user_confirmation)
- 所有操作严格只读

### 2.3 `mcp/` — MCP 管线与工具核心

#### 顶层模块

| 文件 | 行数 | 职责 |
|------|------|------|
| `pipeline.py` | ~350 | Phase 7.0 管线: 加载/建摸/对齐/缺失检测/计划验证/写回/报告 |
| `pipeline_v2.py` | ~750 | Phase 8 管线: 多源语义/结构对齐/语义 diff v2/置信度补图/安全写回 |
| `alignment_v2.py` | ~150 | 语义对齐 v2 |
| `diff_v2.py` | ~40 | 差异比较 v2 |
| `executor.py` | ~100 | 执行器 |
| `probe.py` | ~40 | T30 能力探测 |
| `repair_v2.py` | ~90 | 修复计划 v2 |
| `source_loader.py` | ~240 | 多源加载 (DWG/PDF/图片) |
| `writeback_v2.py` | ~170 | 写回 v2 |
| `state.py` | ~60 | 状态管理 |
| `session.py` | ~40 | 会话管理 |
| `validator.py` | ~110 | 验证器 |

#### 子模块

| 子模块 | 职责 |
|--------|------|
| `mcp/repair_actions/` | **修复行动计划**: action_builder, action_optimizer, action_validator, conflict_checker, dry_run, geometry_utils, missing_detector, models, report, review_cleanup, snapper |
| `mcp/t30_writeback/` | **T30 写回**: action_translator, com_probe, object_factory, parameter_schema, real_adapter, sandbox, transaction, verifier |
| `mcp/acceptance/` | **验收**: acceptance_report, acceptance_runner, confirmation_template, models, probe_workflow, schema_confirmation |
| `mcp/spatial/` | **空间对齐**: alignment_validator, anchor_extractor, anchor_matcher, graph_mapper, models, spatial_alignment, transform |
| `mcp/vision/` | **视觉识别**: cv_provider, pipe_detector, sprinkler_detector, valve_detector, symbol_detector, text_detector, pdf_renderer, semantic_builder |
| `mcp/vision_templates/` | **视觉模板**: template_loader, template_matcher, template_store, symbol_classifier, system_classifier, diameter_parser, evaluation |
| `mcp/diagnostics/` | **诊断**: input_graph 诊断工具 (~800 行) |
| `mcp/e2e/` | **端到端测试**: dataset, manual_e2e_runner, metrics, models, probe_loader, report, reread_verifier, scenario_runner, schema_promoter |

### 2.4 `pipe_network/` — 管网图构建 (Phase 6.4)

| 文件 | 行数 | 职责 |
|------|------|------|
| `graph_builder.py` | ~300 | 从 SemanticModel 构建 PipeNetworkGraph (nodes/edges/systems/subgraphs) |
| `models.py` | ~80 | 图数据模型与工具函数 (entity_handle, pipe_endpoints, entity_center, distance) |

**关键能力**: 基于 TDbPipe 端点 + node_tolerance 合并构建连通图；阀门/管件按 center 并入；按 system_type 分组 subgraphs。

### 2.5 `semantic_diff/` — 语义差异引擎 (Phase 6.3)

| 文件 | 行数 | 职责 |
|------|------|------|
| `diff_engine.py` | ~140 | 语义差异比较 (add_pipe/remove_pipe/modify_pipe/move_pipe/diameter_mismatch/system_mismatch) |
| `matcher.py` | ~130 | 实体匹配 |

### 2.6 其他模块

| 模块 | 职责 |
|------|------|
| `coordinate/` | 坐标标定/映射/变换 (Phase 4.5) |
| `vision/` | 旧版视觉识别 (Phase 3) |
| `cad_compare/` | CAD-to-CAD 差异比较 (Phase 5.5) |
| `roi/` | ROI 区域过滤 (Phase 5.5.1) |
| `execution/` | 安全执行队列 (Phase 4) |
| `tools/` | MCP 工具函数 (connect/disconnect/command/draw/documents/execution/reader/status) |

---

## 三、已有 MCP 接口清单 (server.py 注册)

当前 `server.py` 注册了以下 MCP 工具:

### 连接层
| 工具名 | 功能 |
|--------|------|
| `connect_cad` | 连接已打开的 AutoCAD |
| `disconnect` | 清除 COM 连接缓存 |
| `status` | 返回连接状态 |
| `list_documents` | 列出打开的所有 DWG |
| `get_active_document` | 返回活动图纸信息 |

### 基础控制层
| 工具名 | 功能 |
|--------|------|
| `send_command` | 向 AutoCAD 发送命令字符串 |
| `draw_line` | ModelSpace.AddLine 创建线段 |

### 只读读取层
| 工具名 | 功能 |
|--------|------|
| `read_current_drawing` | 只读当前图纸 → CurrentCADModel |
| `read_selected_entities` | 只读当前选择集 |
| `summarize_current_drawing` | 只读统计摘要 |

### 执行计划层
| 工具名 | 功能 |
|--------|------|
| `generate_execution_plan` | 从 Diff Result 生成执行计划 |
| `preview_execution_plan` | 预览执行计划 |
| `confirm_execution_plan` | 确认执行计划 |
| `execute_execution_plan` | 执行已确认计划 |
| `execute_mapped_execution_plan` | 执行已坐标映射的计划 |

### 管线层
| 工具名 | 功能 |
|--------|------|
| `create_pipeline_session` | Phase 7.0 管线 session |
| `run_pipeline` | Phase 7.0 管线执行 |
| `retry_pipeline_stage` | 从 checkpoint 重试 |
| `get_pipeline_session` | 获取 session 状态 |
| `probe_t30_capabilities` | T30 写回能力探测 |
| `run_phase8_pipeline` | Phase 8 概率驱动管线 |

---

## 四、已有测试基础设施

### 4.1 单元测试 (pytest)

测试目录包含 **100+ 个测试文件**，覆盖:

- `cad/` 全部模块 (connection, reader, entities, geometry, documents, resolver)
- `tianzheng/` 全部模块 (environment, object_inspector, semantic_reader, tdbpipe_deep_probe, diameter_label_reader, pipe_label_association, selection_reader, visibility)
- `pipe_network/` (graph_builder)
- `semantic_diff/` (diff_engine)
- `mcp/` 各子模块 (pipeline, repair_actions, t30_writeback, e2e, acceptance, spatial, vision, vision_templates, diagnostics)
- `coordinate/` (calibration, mapper, models, transform)
- `vision/` (models, provider)
- `execution/` (models, planner, queue, tools)

测试结果: pytest 全量通过 (最后一次报告 `186 passed`)。

### 4.2 手工测试脚本 (`scripts/`)

共 **14 个**手工测试脚本，覆盖:

- `manual_tianzheng_semantic_reader_test.py` — 框选天正区域 → 语义模型
- `manual_tianzheng_diameter_association_test.py` — 管径文字识别与关联
- `manual_tianzheng_selection_reader.py` — 框选对象读取
- `manual_tianzheng_object_inspect.py` — 单对象点选检查
- `manual_tdbpipe_deep_probe.py` — TDbPipe 深度探测
- `diagnose_tianzheng_t30_environment.py` — 天正 T30 环境检测
- `diagnose_autocad_com.py` — AutoCAD COM 诊断
- `manual_reference_dwg_diff_test.py` — Reference vs Current DWG Diff
- `manual_read_current_drawing_test.py` — 当前图纸读取
- `manual_draw_line_test.py` — 画线测试
- `manual_execute_plan_test.py` — 执行计划测试
- `manual_execute_mapped_plan_test.py` — 坐标映射执行测试
- `manual_coordinate_mapping_test.py` — 坐标映射测试
- `test_autocad_connection.py` — 连接测试

### 4.3 验收基础设施

| 路径 | 用途 |
|------|------|
| `acceptance_pack/checklist.md` | 验收清单 |
| `acceptance_pack/scenario_template.json` | 场景模板 |
| `acceptance_pack/run_dry_acceptance.bat` | dry-run 验收脚本 |
| `acceptance_pack/run_probe.bat` | 探测脚本 |
| `acceptance_pack/run_real_sandbox_acceptance.bat` | ★ 沙箱验收脚本 (当前禁止运行) |
| `artifacts/acceptance_reports/` | 10+ 份验收报告 (JSON + Markdown) |
| `artifacts/review_previews/` | 审图预览 (含 overlaid PNG) |

---

## 五、目标图纸

### 主要目标图纸

- **`D:\ExampleWorkspace\天正\artifactsreal.test.001\target.dwg`** (1.47 MB)
  - 真实天正给排水施工图 (水泵房)
  - 通过天正 T30 V1.0 创建/编辑
  - 已通过多次只读验证

### 参考数据

| 路径 | 类型 |
|------|------|
| `artifactsreal.test.001/reference.pdf` | 参考 PDF (89 KB) |
| `artifactsreal.test.001/reference/` | 参考渲染截图 |
| `artifactsreal.test.001/水泵房-模型/` | 水泵房 BIM 模型截图 |
| `artifactsreal.test.001/reference_bbox_debug.png` | BBox 调试截图 |
| `artifactsreal.test.001/scenario_real_test_001.json` | 场景配置 |

---

## 六、已有配置

| 路径 | 用途 |
|------|------|
| `config/pipe_diameter_patterns.json` | 管径识别模式 (DN/De/φ/D) |
| `config/reference_filter_rules.json` | 参考过滤器规则 |
| `config/roi_presets.json` | ROI 预设区域 |
| `config/standard_mapping.json` | 标准映射表 |

---

## 七、关键技术发现

### 7.1 天正自定义对象处理现状

项目已通过以下方式成功处理天正 proxy/custom object:

1. **对象识别**: 通过 `ObjectName` 判断 `TDbPipe`/`TDbPipeValve`/`TDbPipeFitting`/`TDbDimension2`
2. **属性读取**: 通过 `probe_entity_properties()` 容错读取 COM 属性 (DNDiameter, SysType, SElevation, EElevation 等)
3. **XData 读取**: 通过 `GetXData()` 多 AppName (TWT, TCH, TANGENT, TG_PIPE, TDbPipe 等)
4. **ExtensionDictionary**: 通过 `GetExtensionDictionary()` 读取扩展字典
5. **COM TypeInfo**: 通过 `_oleobj_.GetTypeInfo()` 获取类型信息
6. **dir() 筛选**: 对自定义对象执行 `dir()` 并筛选可疑字段名

**关键结论**: 天正对象虽然是 proxy/custom object，但通过 COM 可读取大量内部数据。`DNDiameter` 已确认为可靠管径来源。

### 7.2 安全约束现状

| 约束 | 状态 |
|------|------|
| 不得修改 target.dwg | ✅ 严格执行 |
| 不得覆盖任何 DWG | ✅ 严格执行 |
| 不得运行 run_real_sandbox_acceptance.bat | ✅ 当前阶段禁止 |
| 不得使用 dwg_redraw.py 重建天正图纸 | ✅ 当前阶段禁止 |
| 所有探测使用副本或 dry-run | ✅ 架构支持 |
| 输出写入 logs/reports/examples/outputs | ✅ 遵循 |

---

## 八、项目阶段概览 (ROADMAP 摘要)

| Phase | 名称 | 状态 |
|-------|------|------|
| Phase 1 | MCP Server | ✅ 已完成 |
| Phase 2 | AutoCAD Communication Layer | ✅ 已完成 |
| Phase 3 | Vision Compare Engine MVP | ✅ 已完成 |
| Phase 4 | Diff + MCP 接入 + 安全执行队列 | ✅ 已完成 |
| Phase 4.5 | Coordinate Mapping Layer | ✅ 已完成 |
| Phase 4.6 | Mapped ExecutionPlan → Safe CAD Execution | ✅ 已完成 |
| Phase 5 | Real Current CAD Reader | ✅ 已完成 |
| Phase 5.5 | Reference DWG Reader + CAD-to-CAD Diff | ✅ 已完成 |
| Phase 5.5.1 | ROI Region Filter | ✅ 已完成 |
| Phase 6.0 | 天正 T30 环境接入 | ✅ 已完成 |
| Phase 6.1 | Object Inspector | ✅ 已完成 |
| Phase 6.1.2 | Selection Reader | ✅ 已完成 |
| Phase 6.2 | Semantic Reader | ✅ 已完成 |
| Phase 6.2.2 | DN 管径标注识别 | ✅ 已完成 |
| Phase 6.2.3 | TDbPipe Deep Probe | ✅ 已完成 |
| Phase 6.2.3.1 | DNDiameter 标准化 | ✅ 已完成 |
| Phase 6.3 | Semantic Diff Engine | ✅ 已完成 |
| Phase 6.4 | Pipe Network Graph Builder | ✅ 已完成 |
| Phase 7+ | Validation / Monitor / Agent | ⏳ 待开发 |

---

## 九、小结

当前项目已完成 Phase 1-6.4，建立了从 AutoCAD COM 连接到天正对象语义读取的完整只读链路。已有:

- **MCP 工具**: 20+ 个注册工具
- **Python 模块**: 80+ 个源文件
- **单元测试**: 100+ 个测试文件
- **手工脚本**: 14 个
- **数据样例**: 20 个 JSON
- **验收报告**: 10+ 份

这些基础设施为 Phase 1 "天正给排水接口层" 的只读分析和框架设计提供了坚实的起点。

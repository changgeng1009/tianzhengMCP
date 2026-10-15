> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

++ autocad-dwg-redraw Skill 能力分析报告
++ 生成日期: 2026-07-07

# autocad-dwg-redraw Skill 能力分析报告

## 概述

本报告分析已安装的 `autocad-dwg-redraw` skill 的目录结构、核心脚本、能力边界，并评估哪些能力可以复用到天正给排水接口层扩展中。

---

## 一、Skill 目录结构

```
C:\Users\example-user\.agents\skills\autocad-dwg-redraw-skill-main\
  autocad-dwg-redraw-skill-main\
    skills\
      autocad-dwg-redraw\
        ├── SKILL.md                           # Skill 定义 (12 KB)
        ├── agents\
        │   └── openai.yaml                    # Agent 配置 (299 B)
        ├── references\
        │   └── prompt-template.md             # Prompt 模板 (5.9 KB)
        └── scripts\
            ├── dwg_prompt_builder.py          # DWG 分析器/提示生成器 (11 KB)
            └── dwg_redraw.py                  # DWG 重建/验证器 (7.6 KB)
```

---

## 二、核心脚本分析

### 2.1 `dwg_prompt_builder.py` — DWG 分析器 (约 270 行)

**功能**: 通过 AutoCAD COM 打开 DWG，批量读取图层/实体/块/样式/标注信息，生成标准化 Markdown redraw prompt。

**关键函数**:

| 函数 | 能力 |
|------|------|
| `connect_autocad()` | 通过 `GetActiveObject("AutoCAD.Application")` 连接 COM |
| `restart_autocad(acad_exe)` | 通过 taskkill + Popen 重启 AutoCAD |
| `find_or_open_document(acad, source_path)` | 按 FullName 匹配已打开文档或 `Documents.Open()` 打开 |
| `collect_layers(doc)` | 遍历 `doc.Layers` 收集 name/color/linetype/lineweight |
| `collect_named_collection(collection)` | 遍历 TextStyles/DimStyles/Blocks 收集名称 |
| `collect_entity_counts(space)` | 遍历 ModelSpace/PaperSpace 统计 ObjectName 和 Layer 计数 |
| `render_prompt(...)` | 生成结构化的 Markdown prompt (绘图指纹/分类/策略/环境/图层/实体分布/验证标准) |
| `com_retry(action, attempts, delay)` | COM 重试装饰器 (默认 30 次, 0.4s) |

**生成的 Prompt 结构**:

1. Drawing Fingerprint (源文件名/文件大小/实体数/标注数)
2. Required Redraw Strategy (使用 COM CopyObjects/不过写源文件)
3. Recommended Commands (profile + redraw 命令)
4. Layers (name/color/linetype/lineweight 表格)
5. Entity Type Distribution (ObjectName 计数表格)
6. Entity Layer Distribution (Layer 计数表格)
7. Blocks (块名称表)
8. Text Styles (文字样式表)
9. Dimension Styles (标注样式表)
10. Data Required For Code-Level Redraw (DXFOUT/DATAEXTRACTION 等)
11. Validation Criteria (源-目标实体数比较)

### 2.2 `dwg_redraw.py` — DWG 重建器 (约 200 行)

**功能**: 打开源 DWG，通过 `CopyObjects` 将 ModelSpace/PaperSpace 所有实体复制到新 DWG，验证实体数量和分布。

**关键函数**:

| 函数 | 能力 |
|------|------|
| `connect_autocad()` | COM 连接 + `pythoncom.CoInitialize()` |
| `copy_space(source_doc, source_space, target_space, label)` | **核心**: 使用 `CopyObjects(VARIANT(VT_ARRAY | VT_DISPATCH, batch))` 批量复制实体 |
| `validate_space(source_space, target_space, label)` | 比较源/目标空间实体计数和类型分布 |
| `rebuild_dwg(source_doc, target_doc, include_paperspace)` | 完整重建流程: 复制 ModelSpace + PaperSpace → Activate → Regen → ZoomExtents → 验证 |
| `unique_output_path(path)` | 防覆盖输出路径 (添加时间戳) |

**验证标准**:

- 源/目标 ModelSpace entity count 相等
- 源/目标 PaperSpace entity count 相等
- 源/目标 dimension/leader count 相等
- 源/目标 annotation count 相等
- ObjectName 分布匹配

### 2.3 `references/prompt-template.md` — Prompt 骨架模板

提供标准化的 redraw prompt 结构，包括绘图指纹、分类策略、图层/样式/块清单、实体抽取计划、验证标准。

### 2.4 `SKILL.md` — Skill 定义 (三模式)

定义了三种工作模式:

1. **Source DWG mode**: 从源 DWG profile → prompt → 精确重建
2. **PDF-derived DWG mode**: PDF → 中间 DWG → profile → 重建
3. **Image + metrics mode**: 图片 + 尺寸 → AutoLISP → 参数化构建

通用原则:
- 最终交付使用 `CopyObjects` 精确复制
- 不过写源 DWG
- 代理对象/自定义对象/外部参照报告风险
- 旧 DWG 需等待加载完成

---

## 三、能力分类

### A. 可直接复用到天正扩展的能力

| 能力 | 来源 | 复用方式 |
|------|------|----------|
| AutoCAD COM 连接/重启模式 | `connect_autocad()` / `restart_autocad()` | **直接借鉴** — 项目已有 `cad/connection.py` 但可参考其重试逻辑 |
| 按 FullName 匹配已打开文档 | `find_or_open_document()` | **直接借鉴** — 项目 `cad/document_resolver.py` 已有类似逻辑 |
| 图层/样式/块遍历 | `collect_layers()` / `collect_named_collection()` | **直接借鉴** — 可增强现有 `cad/layers.py` |
| 实体属性容错读取 | `safe_get()` | **完全相同** — 项目已使用相同模式 |
| COM 重试装饰器 | `com_retry()` | **可借鉴** — 项目已有类似但可增强参数 |
| Markdown 报告生成模式 | `render_prompt()` / `markdown_table()` | **可借鉴** — 用于生成天正 DWG 分析报告 |
| 源-目标实体计数验证 | `validate_space()` | **可借鉴** — 用于天正 DWG 副本验证 |
| 防覆盖输出路径 | `unique_output_path()` | **可借鉴** — 用于天正副本创建 |

### B. 需适配的特殊能力

| 能力 | 来源 | 适配说明 |
|------|------|----------|
| `CopyObjects` 批量复制 | `copy_space()` | **天正对象复制风险未知** — 天正自定义对象 (TDbPipe 等) 的 CopyObjects 行为未经测试，可能丢失内部状态或导致目标 DWG 异常 |
| 实体 ObjectName 统计 | `collect_entity_counts()` | **需扩展** — 识别 TDbPipe/TDbPipeValve 等天正特定类型，而非仅通用 CAD 类型 |
| Prompt 模板 | `prompt-template.md` | **需定制** — 需增加天正对象统计、系统类型分析、管径分布等字段 |

### C. 不适合直接用于天正的能力

| 能力 | 原因 |
|------|------|
| `dwg_redraw.py` 完整重建 | 该脚本使用 `CopyObjects` 复制全部实体，对天正自定义对象的行为完全未知。天正对象内部有复杂的属性、XData、ExtensionDictionary，简单复制可能丢失数据 |
| Image + metrics mode | 天正图纸不是从图片重建的，而是从 AutoCAD COM 直接读取 |
| PDF-derived DWG mode | 天正图纸源是 DWG，不是 PDF |
| 纯 AutoLISP 重建 | 天正对象无法通过基础 AutoLISP 命令创建 (需要天正 T30 API) |

### D. 需引入的新能力 (skill 不具备)

| 能力 | 说明 |
|------|------|
| 天正自定义对象语义读取 | 项目 `tianzheng/semantic_reader.py` 已实现 |
| TDbPipe DNDiameter 标准化 | 项目 `tianzheng/tdbpipe_deep_probe.py` 已实现 |
| 管径文字关联 | 项目 `tianzheng/pipe_label_association.py` 已实现 |
| 管网图构建 | 项目 `pipe_network/graph_builder.py` 已实现 |
| 天正环境检测 | 项目 `tianzheng/environment.py` 已实现 |
| 天正 T30 命令调用预留 | 项目 `mcp/t30_writeback/` 已预留接口 |

---

## 四、与天正项目现有能力的对比

| 维度 | Skill (`autocad-dwg-redraw`) | 天正项目 |
|------|---------------------------|---------|
| **CAD 连接** | `GetActiveObject` / `Dispatch` | `cad/connection.py`: 多 ProgID 探测 + COM 重试 |
| **实体读取** | 通用 CAD 类型 (Line/Circle/Text/BlockRef) | `cad/reader.py`: 8 种类型 + `tianzheng/semantic_reader.py`: 4 种天正类型 |
| **实体统计** | ObjectName 计数 + 图层分布 | ObjectName + semantic_type + system_type + diameter 统计 |
| **层/样式读取** | Layers/TextStyles/DimStyles/Blocks | `cad/layers.py` + config JSON |
| **实体深度分析** | 无 (仅外观属性) | `tdbpipe_deep_probe.py`: XData/ExtDict/COM TypeInfo/dir() |
| **语义模型** | 无 | `tianzheng/semantic_reader.py`: pipe/valve/fitting/dimension |
| **管网图** | 无 | `pipe_network/graph_builder.py`: nodes/edges/systems/subgraphs |
| **写回能力** | `CopyObjects` 批量复制 | `mcp/t30_writeback/`: 沙箱+事务+参数schema (预留) |
| **验证** | 实体计数/类型分布 + 目视 | Acceptance report + manual_confirmation + dry_run |
| **报告格式** | Markdown 表格 | JSON + Markdown |

---

## 五、复用策略建议

### 5.1 直接复用 (无需修改)

- `com_retry()` 模式 — 增强项目现有 COM 重试
- `safe_get()` 模式 — 项目已使用相同模式
- 防覆盖输出路径模式 — 创建副本时使用

### 5.2 借鉴改进 (增强现有模块)

- `dwg_prompt_builder.py` 的 **Markdown 报告生成** — 借鉴 `render_prompt()` 的表结构，创建天正 DWG 分析报告模板
- `collect_layers()` / `collect_named_collection()` 的 **集合遍历模式** — 参考其 Count/Item 迭代逻辑
- `validate_space()` 的 **验证方法** — 借鉴实体计数比较逻辑

### 5.3 不可直接使用 (需完全适配)

- `dwg_redraw.py` 的 `CopyObjects` — 天正对象需通过 T30 API 创建，不能用通用 CopyObjects
- `collect_entity_counts()` 的 ObjectName 分类 — 需增加天正类型识别

### 5.4 新建设计理念

Skill 提倡的 "profile → prompt → exact redraw → validate" 流程可转换为天正语境:

```
天正 DWG → 环境检测 → 实体扫描 → 语义分析 → 管网图构建 → 干运行报告
          (借鉴 skill 的 profile 思想)   (天正特有)   (天正特有)   (天正特有)
```

---

## 六、结论

| 结论 | 说明 |
|------|------|
| **Skill 的 COM 模式可复用** | 连接、重试、实体枚举、容错读取等模式与项目现有模式高度一致 |
| **Skill 的报告模式可借鉴** | Markdown 结构化报告可用于天正 DWG 分析 |
| **Skill 的核心重建流程不可直接用** | `CopyObjects` 对天正自定义对象不安全，需通过 T30 API |
| **天正项目已具备独立语义能力** | 项目 `tianzheng/` 模块已实现 skill 不具备的深度语义读取 |
| **最佳策略**: 借鉴 skill 的 profile/report 模式，保留项目已有的 semantic/graph 能力，在接口层统一 | 形成 "profile (借鉴 skill) + semantic (已有) + interface (新增)" 三层架构 |

# Phase 17 Vision Template Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立喷头、阀门、管件、图例模板库和文本语义增强入口，提高 PDF/PNG 图纸识别证据质量，同时保持 confidence gate 和安全降级。

**Architecture:** 新增 `mcp/vision_templates/` 包，集中实现模板模型、store/loader/matcher、符号分类、默认 metadata 模板、管径解析、系统分类、文本语义、评估和样本 registry。`CVVisionProvider` 只做可选接入，`semantic_builder` 保留模板字段，不改变旧 detector 默认行为。

**Tech Stack:** Python dataclasses、pytest、可选 OpenCV、fixture 模式、现有 `VisionElement`/`SemanticGraph`。

---

### Task 1: 写 Phase 17 红灯测试

**Files:**
- Create: `tests/test_phase17_template_models.py`
- Create: `tests/test_phase17_template_loader.py`
- Create: `tests/test_phase17_template_matcher.py`
- Create: `tests/test_phase17_symbol_classifier.py`
- Create: `tests/test_phase17_diameter_parser.py`
- Create: `tests/test_phase17_system_classifier.py`
- Create: `tests/test_phase17_text_semantics.py`
- Create: `tests/test_phase17_evaluation.py`
- Create: `tests/test_phase17_cv_provider_integration.py`

- [ ] **Step 1: 添加红灯测试**

覆盖模板 JSON、store/loader、缺图片 disabled、无模板不伪造 match、confidence gate、DN/De/Φ 解析、系统分类、文本语义、评估、CV 可选接入。

- [ ] **Step 2: 运行红灯测试**

Run: `pytest tests/test_phase17_*.py -q`

Expected: FAIL，失败原因是 `mcp.vision_templates` 模块不存在或 CV provider 参数未实现。

### Task 2: 实现 `mcp/vision_templates`

**Files:**
- Create: `mcp/vision_templates/__init__.py`
- Create: `mcp/vision_templates/models.py`
- Create: `mcp/vision_templates/template_store.py`
- Create: `mcp/vision_templates/template_loader.py`
- Create: `mcp/vision_templates/template_matcher.py`
- Create: `mcp/vision_templates/symbol_classifier.py`
- Create: `mcp/vision_templates/sprinkler_templates.py`
- Create: `mcp/vision_templates/valve_templates.py`
- Create: `mcp/vision_templates/fitting_templates.py`
- Create: `mcp/vision_templates/legend_templates.py`
- Create: `mcp/vision_templates/text_semantics.py`
- Create: `mcp/vision_templates/diameter_parser.py`
- Create: `mcp/vision_templates/system_classifier.py`
- Create: `mcp/vision_templates/evaluation.py`
- Create: `mcp/vision_templates/sample_registry.py`

- [ ] **Step 1: 模型和 store/loader**

全部 dataclass 提供 `to_dict()`；loader 对缺失图片 disabled + warning。

- [ ] **Step 2: matcher/classifier/default templates**

matcher 支持 fixture mode 和保守 OpenCV 路径；无模板返回空，不伪造；classifier 按 0.60/0.85 分级。

- [ ] **Step 3: 文本语义和评估**

实现管径解析、系统分类、文本语义抽取、precision/recall 评估、样本 registry。

### Task 3: 接入现有 Vision

**Files:**
- Modify: `mcp/vision/cv_provider.py`
- Modify: `mcp/vision/semantic_builder.py`

- [ ] **Step 1: CVVisionProvider 可选参数**

新增 `use_template_library=True`、`template_store=None`、`template_match_threshold=0.85`。无模板时只加 warning，不影响旧 detector。

- [ ] **Step 2: template matches 转 VisionElement**

`sprinkler_candidate` / `valve_candidate` / `fitting_candidate` / `legend_candidate`，保留 `matched_template_id`、`method`、`confidence`、warnings。

- [ ] **Step 3: semantic_builder 保留字段**

legend 进入 symbols；sprinkler/valve/fitting 保留 template metadata。

### Task 4: 文档与验证

**Files:**
- Create: `docs/phase17_vision_template_library.md`

- [ ] **Step 1: 写文档**

说明默认 metadata 模板不代表真实图片模板已存在，用户可逐步加入真实样本。

- [ ] **Step 2: 定向与全量测试**

Run: `pytest tests/test_phase17_*.py -q`

Run: `pytest -q`

Expected: PASS，不破坏既有 310 个测试。

### Self-Review

Spec coverage:
- 模板、store、loader、matcher、classifier、默认库、文本语义、评估、样本 registry、CV 接入均覆盖。
- 无模板/无 OCR/无 OpenCV 均安全降级。
- 低置信度不进入自动补图依据。

Placeholder scan:
- 无 `TBD`、`TODO`、`implement later`。

Type consistency:
- `VisionTemplate`、`TemplateMatch`、`ClassifiedSymbol`、`ParsedDiameter`、`ClassifiedSystem`、`TemplateEvaluationResult` 在测试和实现中统一。

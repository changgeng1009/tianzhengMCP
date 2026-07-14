# Phase 9 Vision Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 PDF / PNG 到 `semantic_graph` 的最小可验证视觉解析 provider，让 Phase 8 不再只能消费预解析语义图。

**Architecture:** 新增 `mcp/vision/` 子包，包含数据模型、provider 抽象、PDF renderer、图片预处理、线/符号/文字检测入口和 semantic graph builder。默认 `BasicVisionProvider` 只做安全、低置信度、可扩展的基础解析；没有真实 OCR/CV 能力时必须返回 warning，不伪造高置信度结果。

**Tech Stack:** Python dataclasses、可选 Pillow / PyMuPDF / OpenCV 探测、pytest fixture/mock、现有 `MultiSourceSemanticLoader`。

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_phase9_vision_models.py`
- Create: `tests/test_phase9_pdf_renderer.py`
- Create: `tests/test_phase9_semantic_builder.py`
- Create: `tests/test_phase9_source_loader_integration.py`

- [ ] **Step 1: Test model serialization**

验证 `VisionElement`、`VisionParseResult`、`SemanticGraph` 可 `to_dict()`，且 confidence 合法。

- [ ] **Step 2: Test PDF renderer safe fallback**

验证缺失或不可渲染 PDF 返回 `status=failed`、`warnings`，不抛不可控异常。

- [ ] **Step 3: Test BasicVisionProvider parse_png**

用 fixture-like 输入验证 provider 返回结构化 `VisionParseResult`，低置信度时带 warning。

- [ ] **Step 4: Test semantic builder**

验证 `pipe_candidate / valve_candidate / sprinkler_candidate / text_candidate / building_outline` 能映射到 Phase 8 兼容 graph。

- [ ] **Step 5: Test source loader integration**

验证 PDF / PNG 没有显式 `semantic_graph` 时调用 vision provider；失败时空图 + warning，成功时合并语义图。

### Task 2: Vision Package

**Files:**
- Create: `mcp/vision/__init__.py`
- Create: `mcp/vision/models.py`
- Create: `mcp/vision/provider.py`
- Create: `mcp/vision/pdf_renderer.py`
- Create: `mcp/vision/image_preprocess.py`
- Create: `mcp/vision/line_detector.py`
- Create: `mcp/vision/symbol_detector.py`
- Create: `mcp/vision/text_detector.py`
- Create: `mcp/vision/semantic_builder.py`

- [ ] **Step 1: Implement dataclass models**

所有模型输出 JSON dict；confidence 必须在 0 到 1。

- [ ] **Step 2: Implement renderer and preprocess stubs**

可选依赖存在时使用，不存在时结构化降级。

- [ ] **Step 3: Implement detectors**

检测器支持 `metadata.fixture_elements` 输入，用于可验证测试；真实图像无识别时返回空列表和 warning。

- [ ] **Step 4: Implement provider**

`BasicVisionProvider` 串联 render/preprocess/detect/build，并保留 OCR/CV/VLM 扩展入口。

### Task 3: Source Loader Integration

**Files:**
- Modify: `mcp/source_loader.py`

- [ ] **Step 1: Add optional vision provider dependency**

保持默认行为兼容，只有 PDF / PNG 且缺少 `semantic_graph` 时调用 provider。

- [ ] **Step 2: Preserve Phase 8 behavior**

传入显式 `semantic_graph` 时仍直接使用，不调用 vision provider。

### Task 4: Verification

**Files:**
- Test: Phase 9 tests
- Test: full suite

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_phase9_vision_models.py tests/test_phase9_pdf_renderer.py tests/test_phase9_semantic_builder.py tests/test_phase9_source_loader_integration.py -q`
Expected: PASS after implementation.

- [ ] **Step 2: Run full tests**

Run: `pytest -q`
Expected: PASS.

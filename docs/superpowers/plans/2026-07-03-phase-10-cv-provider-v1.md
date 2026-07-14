# Phase 10 CV Provider v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 9 视觉入口升级为保守可用的 CV Provider v1，可从 PDF / PNG 中提取基础候选元素并输出 Phase 8 可消费的 `semantic_graph`。

**Architecture:** 新增 `CVVisionProvider`，通过 provider 模式接入 `source_loader`，检测逻辑仍留在 `mcp/vision/` 子模块。OpenCV / OCR 不可用时结构化降级；fixture 输入用于可重复测试；真实 CV 能力只作为可选增强，不伪造高置信度。

**Tech Stack:** Python dataclasses/dict JSON、可选 OpenCV / pytesseract、pytest monkeypatch、现有 Phase 9 模型。

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_phase10_confidence.py`
- Create: `tests/test_phase10_coordinate_mapper.py`
- Create: `tests/test_phase10_pipe_detector.py`
- Create: `tests/test_phase10_symbol_detectors.py`
- Create: `tests/test_phase10_cv_provider.py`
- Create: `tests/test_phase10_source_loader_integration.py`

- [ ] **Step 1: Test confidence and coordinates**

验证 confidence clamp / combine / classify，以及图片坐标归一化。

- [ ] **Step 2: Test detectors**

验证 pipe fixture 输出 `pipe_candidate`，喷头/阀门无模板时不伪造。

- [ ] **Step 3: Test CV provider fallback**

验证 OpenCV 缺失、图片不存在时结构化失败或 warning。

- [ ] **Step 4: Test source loader integration**

验证 PDF/PNG 无 `semantic_graph` 时优先调用 CV provider，失败时安全空图，成功时合并 semantic graph。

### Task 2: Vision v1 Modules

**Files:**
- Create: `mcp/vision/confidence.py`
- Create: `mcp/vision/coordinate_mapper.py`
- Create: `mcp/vision/fixtures.py`
- Create: `mcp/vision/ocr_provider.py`
- Create: `mcp/vision/contour_detector.py`
- Create: `mcp/vision/pipe_detector_v1.py`
- Create: `mcp/vision/sprinkler_detector_v1.py`
- Create: `mcp/vision/valve_detector_v1.py`
- Create: `mcp/vision/cv_provider.py`

- [ ] **Step 1: Implement utility modules**

Confidence、坐标归一化、fixture 转换、OCR provider stub。

- [ ] **Step 2: Implement detector v1**

Fixture-first，可选 CV hook；无模板/无 CV 时返回空候选和 warning，由 provider 汇总。

- [ ] **Step 3: Implement CVVisionProvider**

串联 renderer / preprocess / detector / semantic builder；不可用时不抛不可控异常。

### Task 3: Integration

**Files:**
- Modify: `mcp/vision/provider.py`
- Modify: `mcp/vision/semantic_builder.py`
- Modify: `mcp/source_loader.py`

- [ ] **Step 1: Export CV provider**

保持 Basic provider 兼容。

- [ ] **Step 2: Enhance semantic graph metadata**

加入 provider、coordinate_space、source_element_id、bbox、points、metadata。

- [ ] **Step 3: Prefer CV provider in source loader**

PDF/PNG 缺少 `semantic_graph` 时优先 CV，失败后降级 Basic。

### Task 4: Verification

- [ ] **Step 1: Run Phase 10 tests**

Run: `pytest tests/test_phase10_confidence.py tests/test_phase10_coordinate_mapper.py tests/test_phase10_pipe_detector.py tests/test_phase10_symbol_detectors.py tests/test_phase10_cv_provider.py tests/test_phase10_source_loader_integration.py -q`

- [ ] **Step 2: Run full regression**

Run: `pytest -q`

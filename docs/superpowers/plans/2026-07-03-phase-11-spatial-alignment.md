# Phase 11 Spatial Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PDF / PNG 视觉语义图从 `normalized_image` 映射到目标 DWG `cad_modelspace`，为后续自动补图提供坐标基础。

**Architecture:** 新增 `mcp/spatial/` 子包，封装数据模型、transform 估计、anchor 提取和匹配、graph 映射、alignment 校验和主入口。`pipeline_v2` 只增加可选阶段，默认保持 Phase 8/10 旧行为不变。

**Tech Stack:** Python dataclasses、纯 Python 2D affine/translation 变换、pytest。

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_phase11_spatial_models.py`
- Create: `tests/test_phase11_transform.py`
- Create: `tests/test_phase11_anchor_matching.py`
- Create: `tests/test_phase11_graph_mapper.py`
- Create: `tests/test_phase11_spatial_alignment.py`
- Create: `tests/test_phase11_pipeline_v2_integration.py`

- [ ] **Step 1: Test models and transform**

验证模型 JSON 序列化、identity / translation / affine apply_point、anchor 不足返回 unknown。

- [ ] **Step 2: Test anchors and mapper**

验证 reference / target anchor 提取、matcher 不盲目高置信匹配、mapper 保留 original / mapped geometry。

- [ ] **Step 3: Test alignment and pipeline integration**

验证 manual anchors 成功对齐，pipeline 默认跳过，启用后执行可选阶段。

### Task 2: Spatial Package

**Files:**
- Create: `mcp/spatial/__init__.py`
- Create: `mcp/spatial/models.py`
- Create: `mcp/spatial/transform.py`
- Create: `mcp/spatial/anchor_extractor.py`
- Create: `mcp/spatial/anchor_matcher.py`
- Create: `mcp/spatial/graph_mapper.py`
- Create: `mcp/spatial/alignment_validator.py`
- Create: `mcp/spatial/spatial_alignment.py`

- [ ] **Step 1: Implement data models**

All models expose `to_dict()`.

- [ ] **Step 2: Implement transform engine**

Support identity, translation, similarity placeholder, affine apply; unknown when anchors insufficient.

- [ ] **Step 3: Implement anchor and graph mapping**

Skip elements without coordinates; do not invent anchors.

- [ ] **Step 4: Implement validation and main entry**

Manual anchors override auto; auto failure returns warning safely.

### Task 3: Pipeline v2 Integration

**Files:**
- Modify: `mcp/pipeline_v2.py`

- [ ] **Step 1: Add optional stage**

Only enabled with `enable_spatial_alignment=True`; default remains unchanged.

- [ ] **Step 2: Guard writeback**

Spatial failure adds warning and disables auto writeback for that session.

### Task 4: Verification

- [ ] **Step 1: Run Phase 11 tests**

Run: `pytest tests/test_phase11_spatial_models.py tests/test_phase11_transform.py tests/test_phase11_anchor_matching.py tests/test_phase11_graph_mapper.py tests/test_phase11_spatial_alignment.py tests/test_phase11_pipeline_v2_integration.py -q`

- [ ] **Step 2: Run full regression**

Run: `pytest -q`

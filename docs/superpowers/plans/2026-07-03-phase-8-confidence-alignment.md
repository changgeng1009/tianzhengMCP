# Phase 8 Confidence Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Phase 7 session pipeline 基础上增加多源语义、建筑结构指纹、语义 diff v2、置信度补图、repair plan 优化和安全写回 v2。

**Architecture:** 新增独立 Phase 8 模块，不重写 Phase 7。多源 loader 接受 PDF/PNG/DWG 的已解析语义或轻量 mock 语义，统一输出 `semantic_graph`；alignment v2 使用结构指纹评分；diff v2 输出 `true_missing / design_variation / uncertain`；repair v2 执行 confidence gate；safe writeback v2 执行 `validate -> simulate -> execute -> verify -> commit`。

**Tech Stack:** Python dataclasses/dict JSON、pytest、现有 `T30WritebackAdapter`、现有 MCP server 注册方式。

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_phase8_semantics.py`
- Create: `tests/test_phase8_pipeline.py`

- [ ] **Step 1: Test multi-source semantic loader**

验证 PDF/PNG/DWG 输入统一输出 `semantic_graph.buildings/pipes/valves/sprinklers`，且返回 confidence 和 warnings。

- [ ] **Step 2: Test structural fingerprint alignment**

验证 pipe density、valve distribution、sprinkler layout pattern、topology hash 被生成，并用于 Reference -> Target 建筑映射。

- [ ] **Step 3: Test semantic diff v2 and confidence repair**

验证 `true_missing / design_variation / uncertain` 分类，且 `confidence > 0.85` 自动执行、`0.6 < confidence < 0.85` 待审核、`confidence < 0.6` 禁止执行。

- [ ] **Step 4: Test safe writeback v2**

验证 `validate -> simulate -> execute -> verify -> commit` 顺序、重复/冲突动作被拦截，并生成 rollback plan。

### Task 2: Phase 8 Modules

**Files:**
- Create: `mcp/source_loader.py`
- Create: `mcp/alignment_v2.py`
- Create: `mcp/diff_v2.py`
- Create: `mcp/repair_v2.py`
- Create: `mcp/writeback_v2.py`
- Create: `mcp/pipeline_v2.py`

- [ ] **Step 1: Implement minimal source loader**

支持 `pdf/png/dwg` 三类输入，优先使用调用方提供的 `semantic_graph`，未提供时生成可测试空图并写入 warning。

- [ ] **Step 2: Implement alignment v2**

基于结构指纹计算建筑映射 confidence 和 reason。

- [ ] **Step 3: Implement diff and repair v2**

按 confidence 分类并生成 action gate。

- [ ] **Step 4: Implement safe writeback v2**

只执行 `auto_execute=true` 且通过 simulation 的动作。

### Task 3: MCP Registration And Verification

**Files:**
- Modify: `server.py`
- Test: `tests/test_phase8_pipeline.py`

- [ ] **Step 1: Register Phase 8 tool**

注册 `run_phase8_pipeline`。

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_phase8_semantics.py tests/test_phase8_pipeline.py -q`
Expected: PASS after implementation.

- [ ] **Step 3: Run full regression**

Run: `pytest -q`
Expected: PASS.

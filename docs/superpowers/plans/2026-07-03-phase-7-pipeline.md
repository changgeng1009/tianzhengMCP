# Phase 7.0 MCP Session Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Session 驱动的最小闭环 Pipeline：DWG + PNG 输入，语义建模，建筑对齐，缺失检测，补图计划验证，T30 mock 写回，审图报告输出。

**Architecture:** 新增 `mcp/` 包承载状态模型、状态机、T30 capability probe、写回适配器、repair plan validator、executor 和 pipeline 编排。真实 CAD/T30 不作为单元测试依赖，真实写回必须通过 capability probe 和 `real_com_mode` 显式打开。

**Tech Stack:** Python dataclasses、现有 `pipe_network.graph_builder`、现有 JSON dict 返回风格、pytest fake COM。

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_adapter.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write fake COM adapter tests**

验证 `T30WritebackAdapter` 默认 mock 模式、capability probe、action log，以及 real mode 在能力缺失时阻止插入。

- [ ] **Step 2: Write pipeline tests**

验证完整 stage 顺序、每步更新 session、统一返回格式、validate before apply、失败后可从 checkpoint retry。

- [ ] **Step 3: Run tests and verify failure**

Run: `pytest tests/test_adapter.py tests/test_pipeline.py -q`
Expected: FAIL because `mcp` modules are not implemented.

### Task 2: Session And State

**Files:**
- Create: `mcp/__init__.py`
- Create: `mcp/state.py`
- Create: `mcp/session.py`

- [ ] **Step 1: Implement `PipelineStage`, `StageStatus`, and `PipelineState`**

状态必须记录当前 stage、已完成 stages、失败 stage、checkpoint 和 action log。

- [ ] **Step 2: Implement `MCPSession`**

字段必须包含 `session_id`、`dwg_path`、`png_path`、`cad_connection`、`dwg_graph`、`png_graph`、`alignment_map`、`missing_result`、`repair_plan`、`applied_actions`、`pipeline_state`。

### Task 3: Probe And Adapter

**Files:**
- Create: `mcp/probe.py`
- Create: `mcp/adapter_t30.py`

- [ ] **Step 1: Implement `probe_t30_capabilities()`**

默认无真实 CAD 时返回 JSON 能力表和 notes；传入 fake capability source 时读取 `TDbPipe.Insert`、`TDbValve.Insert`、`TDbSprinkler.Insert`、`TDbPipeFitting.Insert`。

- [ ] **Step 2: Implement `T30WritebackAdapter`**

提供 `insert_pipe()`、`insert_valve()`、`insert_sprinkler()`、`insert_fitting()`。mock 模式返回 deterministic fake handle；real mode 必须先检查 capability。

### Task 4: Validator And Executor

**Files:**
- Create: `mcp/validator.py`
- Create: `mcp/executor.py`

- [ ] **Step 1: Implement `RepairPlanValidator`**

验证 node 存在、pipe 连接合法、DN 合理、重复对象、结构冲突。

- [ ] **Step 2: Implement transactional executor**

执行顺序为 validate -> execute -> commit；未通过 validate 时不调用 adapter。

### Task 5: Pipeline

**Files:**
- Create: `mcp/pipeline.py`
- Modify: `server.py`

- [ ] **Step 1: Implement strict state machine pipeline**

严格执行 `load_dwg`、`load_png`、`build_semantic_graph`、`align_buildings`、`detect_missing_elements`、`generate_repair_plan`、`validate_repair_plan`、`apply_to_cad`、`generate_report`。

- [ ] **Step 2: Expose MCP tools**

注册 `create_pipeline_session`、`run_pipeline`、`retry_pipeline_stage`、`get_pipeline_session`、`probe_t30_capabilities`。

### Task 6: Verification

**Files:**
- Test: `tests/test_adapter.py`
- Test: `tests/test_pipeline.py`
- Test: existing suite

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_adapter.py tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 2: Run full tests**

Run: `pytest -q`
Expected: PASS.

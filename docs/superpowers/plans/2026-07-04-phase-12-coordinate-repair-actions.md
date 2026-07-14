# Phase 12 Coordinate Repair Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已映射到 `cad_modelspace` 的 reference graph 转换为安全、可验证、可 dry-run 的 CAD repair actions。

**Architecture:** 新增 `mcp/repair_actions/` 子包，封装动作模型、几何匹配、坐标级 missing detection、action 构建、snap、冲突检查、验证、优化、dry-run 和报告。`pipeline_v2` 只增加可选阶段，默认保持旧逻辑不变。

**Tech Stack:** Python dataclasses、纯 Python 2D 几何、pytest、现有 Phase 11 aligned graph。

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_phase12_repair_action_models.py`
- Create: `tests/test_phase12_geometry_utils.py`
- Create: `tests/test_phase12_missing_detector.py`
- Create: `tests/test_phase12_action_builder.py`
- Create: `tests/test_phase12_snapper.py`
- Create: `tests/test_phase12_conflict_checker.py`
- Create: `tests/test_phase12_action_validator.py`
- Create: `tests/test_phase12_dry_run.py`
- Create: `tests/test_phase12_pipeline_v2_integration.py`

- [ ] **Step 1: Test models and geometry**

验证 JSON 序列化、距离、长度、bbox overlap、near duplicate。

- [ ] **Step 2: Test missing detection and action builder**

验证 true_missing / already_exists / uncertain，生成 add_pipe / add_sprinkler / add_valve，并按 confidence gate 分类。

- [ ] **Step 3: Test snap/conflict/validation/dry-run**

验证不远距离强吸附，重复对象降级，缺 system / dn 不自动执行，dry-run 不写 CAD。

- [ ] **Step 4: Test pipeline optional stage**

默认跳过；启用 `enable_coordinate_repair_actions=True` 后生成 `repair_plan_v2`。

### Task 2: Repair Actions Package

**Files:**
- Create: `mcp/repair_actions/__init__.py`
- Create: `mcp/repair_actions/models.py`
- Create: `mcp/repair_actions/geometry_utils.py`
- Create: `mcp/repair_actions/missing_detector.py`
- Create: `mcp/repair_actions/action_builder.py`
- Create: `mcp/repair_actions/snapper.py`
- Create: `mcp/repair_actions/conflict_checker.py`
- Create: `mcp/repair_actions/action_validator.py`
- Create: `mcp/repair_actions/action_optimizer.py`
- Create: `mcp/repair_actions/dry_run.py`
- Create: `mcp/repair_actions/report.py`

- [ ] **Step 1: Implement models**

`RepairAction`, `RepairPlanV2`, `GeometryMatchResult`, `DryRunResult` all expose `to_dict()`.

- [ ] **Step 2: Implement geometry and missing detector**

Use mapped geometry only; low confidence never becomes true_missing.

- [ ] **Step 3: Implement action pipeline**

Build actions -> snap -> conflict check -> optimize -> validate -> dry-run -> report.

### Task 3: Pipeline v2 Integration

**Files:**
- Modify: `mcp/pipeline_v2.py`

- [ ] **Step 1: Add optional coordinate repair stage**

Only enabled with `enable_coordinate_repair_actions=True`.

- [ ] **Step 2: Preserve old repair flow**

If disabled, existing Phase 8 repair flow remains unchanged.

### Task 4: Verification

- [ ] **Step 1: Run Phase 12 tests**

Run: `pytest tests/test_phase12_*.py -q`

- [ ] **Step 2: Run full regression**

Run: `pytest -q`

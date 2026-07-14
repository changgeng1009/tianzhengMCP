# Phase 16.4 Review Action Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将低置信度 PDF line fallback review actions 清洗、去重、合并、分组，并输出人工复核 preview，不产生任何自动写回动作。

**Architecture:** 新增 `mcp.repair_actions.review_cleanup` 作为纯数据后处理模块，只读取 `repair_plan_v2.review_actions` 并输出 cleanup summary / groups / previews。acceptance report 在生成 JSON/MD 前调用清洗器，把结果写入报告 metadata 和 `review_action_cleanup_summary`。

**Tech Stack:** Python dataclasses-free utility、pytest、JSON/Markdown preview、Pillow 可选 PNG overlay。

---

### Task 1: Review Action Cleanup Core

**Files:**
- Create: `mcp/repair_actions/review_cleanup.py`
- Create: `tests/test_phase16_4_review_action_cleanup.py`

- [x] **Step 1: Write failing tests**

覆盖重复线、极短线、边界线、近重合双线、共线合并、连通分组、DN 文本证据与 review-only 安全约束。

- [ ] **Step 2: Implement cleanup pipeline**

实现 `cleanup_review_actions(repair_plan, options)`，返回 summary、filtered_actions、merged_actions、groups。

- [ ] **Step 3: Verify targeted tests pass**

Run: `pytest tests/test_phase16_4_review_action_cleanup.py -q`

### Task 2: Preview Output

**Files:**
- Modify: `mcp/repair_actions/review_cleanup.py`
- Test: `tests/test_phase16_4_review_action_cleanup.py`

- [ ] **Step 1: Generate JSON / MD / PNG preview**

输出到 `artifacts/review_previews/pump_room_review_actions.*`，PNG 只做预览线段叠加，不写 CAD。

- [ ] **Step 2: Ensure auto executable count remains zero**

所有 merged/grouped actions 保持 `validation_status=review_required`、`auto_execute=false`。

### Task 3: Acceptance Report Integration

**Files:**
- Modify: `mcp/acceptance/acceptance_report.py`
- Test: `tests/test_phase16_4_acceptance_report_cleanup.py`

- [ ] **Step 1: Attach cleanup result to report JSON**

新增 `review_action_cleanup_summary`。

- [ ] **Step 2: Add markdown section**

在 MD 报告中写入 summary 和 preview 文件路径。

- [ ] **Step 3: Verify full suite and dry-run**

Run: `pytest -q` and `acceptance_pack\run_dry_acceptance.bat`。

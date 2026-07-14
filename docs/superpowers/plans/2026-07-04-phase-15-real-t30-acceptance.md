# Phase 15 Real T30 Acceptance Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建真实 T30 参数确认与首张真实图纸验收流程，把 Phase 13/14 的安全链路推进到可人工确认、可重复验收的 acceptance 工作流。

**Architecture:** 新增 `mcp/acceptance/` 包，封装 probe workflow、manual confirmation template、schema 双确认、真实写回 checklist、acceptance runner 和 acceptance report。默认 dry-run/fake/no real write，真实写回必须同时满足 scenario/probe/manual/schema/sandbox/real_com/reread gate。

**Tech Stack:** Python dataclasses、pytest、JSON/Markdown、Phase 13 `manual_probe_runner`、Phase 14 `E2EScenarioRunner`。

---

### Task 1: 写 Phase 15 红灯测试

**Files:**
- Create: `tests/test_phase15_acceptance_models.py`
- Create: `tests/test_phase15_confirmation_template.py`
- Create: `tests/test_phase15_schema_confirmation.py`
- Create: `tests/test_phase15_probe_workflow_fake.py`
- Create: `tests/test_phase15_acceptance_runner_fake.py`
- Create: `tests/test_phase15_acceptance_report.py`

- [ ] **Step 1: 添加红灯测试**

覆盖 acceptance 模型序列化、template 默认 `confirmed=false`、schema 必须 probe + manual 双确认、checklist gate、runner 默认 dry-run、fake report 和未 re-read verified 不声明真实成功。

- [ ] **Step 2: 运行红灯测试**

Run: `pytest tests/test_phase15_*.py -q`

Expected: FAIL，失败原因是 `mcp.acceptance` 模块不存在。

### Task 2: 实现 acceptance 核心模块

**Files:**
- Create: `mcp/acceptance/__init__.py`
- Create: `mcp/acceptance/models.py`
- Create: `mcp/acceptance/probe_workflow.py`
- Create: `mcp/acceptance/confirmation_template.py`
- Create: `mcp/acceptance/schema_confirmation.py`
- Create: `mcp/acceptance/real_writeback_checklist.py`
- Create: `mcp/acceptance/acceptance_runner.py`
- Create: `mcp/acceptance/acceptance_report.py`

- [ ] **Step 1: 数据模型**

实现 `T30ProbeWorkflowResult`、`ManualConfirmationTemplate`、`ConfirmedSchemaSet`、`AcceptanceRunConfig`、`AcceptanceRunResult`，全部提供 `to_dict()`。

- [ ] **Step 2: Probe/template/schema/checklist**

实现 fake 可测的 probe workflow；manual confirmation template 默认全 false；schema confirmation 必须 probe + manual 两边同时满足；checklist 任一 gate 缺失则 `ready=false`。

- [ ] **Step 3: Runner/report/CLI**

Runner 默认不真实写回；gate 不满足只允许 dry-run/fake；报告输出 JSON + Markdown，并明确能否声明真实补图成功。

### Task 3: 文档

**Files:**
- Create: `docs/phase15_real_t30_acceptance.md`

- [ ] **Step 1: 写验收规范**

说明 probe、manual confirmation、schema promotion、checklist、manual CLI、安全默认值和报告判定。

### Task 4: 验证

- [ ] **Step 1: Phase 15 定向测试**

Run: `pytest tests/test_phase15_*.py -q`

Expected: PASS。

- [ ] **Step 2: 全量回归**

Run: `pytest -q`

Expected: PASS，不破坏既有 292 个测试。

### Self-Review

Spec coverage:
- 模型、probe workflow、template、schema confirmation、checklist、runner、report、CLI、文档均覆盖。
- 默认安全值全部为 no real write。
- 真实 AutoCAD/T30 测试不进入 pytest。

Placeholder scan:
- 无 `TBD`、`TODO`、`implement later`。

Type consistency:
- `AcceptanceRunConfig`、`AcceptanceRunResult` 在 runner、checklist、report 中统一使用 `to_dict()`。

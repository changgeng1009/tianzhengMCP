# Phase 14 Real E2E Validation Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建真实图纸端到端验证框架，让 reference PDF/PNG/DWG 与 target DWG 可以安全跑完整 pipeline、sandbox writeback、re-read verification 和 JSON/Markdown 报告。

**Architecture:** 新增 `mcp/e2e/` 包承载 scenario、dataset、probe loader、schema promoter、runner、verifier、metrics、report 和 manual CLI。Phase 14 不改写 Phase 7-13，只通过 `Phase8PipelineEngine` 和 `RealT30WritebackAdapter` 的既有安全 gate 执行。

**Tech Stack:** Python dataclasses、pytest、JSON、Markdown 报告、fake COM/sandbox、可选 manual real COM runner。

---

### Task 1: 写 Phase 14 红灯测试

**Files:**
- Create: `tests/test_phase14_e2e_models.py`
- Create: `tests/test_phase14_probe_loader.py`
- Create: `tests/test_phase14_schema_promoter.py`
- Create: `tests/test_phase14_dataset.py`
- Create: `tests/test_phase14_scenario_runner_fake.py`
- Create: `tests/test_phase14_reread_verifier_fake.py`
- Create: `tests/test_phase14_metrics.py`
- Create: `tests/test_phase14_report.py`
- Create: `tests/test_phase14_pipeline_integration_fake.py`

- [ ] **Step 1: 添加红灯测试**

覆盖模型序列化、scenario 校验、probe 文件错误、schema promotion gate、fake scenario runner、fake reread verifier、metrics、报告文件和 manual runner 参数解析。

- [ ] **Step 2: 运行红灯测试**

Run: `pytest tests/test_phase14_*.py -q`

Expected: FAIL，失败原因是 `mcp.e2e` 模块不存在。

### Task 2: 实现 `mcp/e2e` 模块

**Files:**
- Create: `mcp/e2e/__init__.py`
- Create: `mcp/e2e/models.py`
- Create: `mcp/e2e/dataset.py`
- Create: `mcp/e2e/probe_loader.py`
- Create: `mcp/e2e/schema_promoter.py`
- Create: `mcp/e2e/scenario_runner.py`
- Create: `mcp/e2e/reread_verifier.py`
- Create: `mcp/e2e/metrics.py`
- Create: `mcp/e2e/report.py`
- Create: `mcp/e2e/manual_e2e_runner.py`

- [ ] **Step 1: 数据模型**

实现 `E2EScenario`、`E2ERunConfig`、`E2ERunResult`、`E2EMetrics`，全部提供 `to_dict()`。

- [ ] **Step 2: Dataset / Probe / Schema**

实现 scenario registry、manual probe JSON loader、manual confirmation 驱动的 confirmed schema promotion。

- [ ] **Step 3: Runner / Verifier / Metrics / Report**

Runner 默认 dry-run、不写 CAD；fake 模式可完整跑 pipeline；reread verifier fake mode 可 verified，real mode 无 provider 时只能 unverified warning。

### Task 3: 文档与手动入口

**Files:**
- Create: `docs/phase14_real_e2e_validation.md`
- Create: `mcp/e2e/manual_e2e_runner.py`

- [ ] **Step 1: 文档**

写明默认不真实写 CAD、manual probe 和 manual confirmation 要求、runner 参数、输出文件。

- [ ] **Step 2: CLI**

实现 `build_arg_parser()` 和 `main()`，默认 `dry-run-only=true`、`enable-real-writeback=false`、`real-com-mode=false`。

### Task 4: 验证

- [ ] **Step 1: Phase 14 定向测试**

Run: `pytest tests/test_phase14_*.py -q`

Expected: PASS。

- [ ] **Step 2: 全量回归**

Run: `pytest -q`

Expected: PASS，不破坏既有 277 个测试。

### Self-Review

Spec coverage:
- 数据模型、dataset、probe loader、schema promoter、scenario runner、reread verifier、metrics、report、manual runner、pipeline fake integration 均覆盖。
- 真实 AutoCAD/T30 验证只通过 manual runner，不进入默认 pytest。
- 默认配置全部保持 dry-run / fake / no real write。

Placeholder scan:
- 无 `TBD`、`TODO`、`implement later`。

Type consistency:
- `E2ERunResult` 在 runner、metrics、report 中统一使用 `to_dict()` 结构。

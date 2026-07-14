# Phase 16.1 Probe DWG Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复真实验收首轮 dry-run 中 AutoCAD/T30 Document 获取失败时诊断不足的问题，并增强 DWG 路径不一致的安全提示。

**Architecture:** 保持 Phase 7-17 架构不变，只扩展 `T30COMProbe` 的只读 Application/Documents/Document resolution 诊断链路。场景校验只做候选提示和显式 fallback，不静默替换目标 DWG。

**Tech Stack:** Python、pytest、AutoCAD COM 只读 probe、JSON artifact。

---

### Task 1: COM Probe 诊断测试

**Files:**
- Create: `tests/test_phase16_1_com_probe_diagnostics.py`
- Modify: `mcp/t30_writeback/com_probe.py`

- [x] **Step 1: Write failing tests**

覆盖 AutoCAD Application 不可用、ActiveDocument 不可用、Documents fallback、target path 匹配、allow_open_document 开关。

- [x] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_phase16_1_com_probe_diagnostics.py -q`

- [ ] **Step 3: Implement minimal probe diagnostics**

在 `probe_environment()` 增加 `autocad` 与 `document_resolution` 结构，并保留旧字段兼容。

- [ ] **Step 4: Verify targeted tests pass**

Run: `pytest tests/test_phase16_1_com_probe_diagnostics.py -q`

### Task 2: Scenario DWG Path Diagnostics

**Files:**
- Create: `tests/test_phase16_1_dataset_path_diagnostics.py`
- Modify: `mcp/e2e/dataset.py`

- [x] **Step 1: Write failing tests**

覆盖 target DWG 不存在时列出候选、默认不替换、显式 `allow_single_dwg_fallback=true` 才替换。

- [x] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_phase16_1_dataset_path_diagnostics.py -q`

- [ ] **Step 3: Implement candidate diagnostics**

在 `validate_scenario()` 返回 `dwg_candidates` 和 warning，默认保持 invalid。

- [ ] **Step 4: Verify targeted tests pass**

Run: `pytest tests/test_phase16_1_dataset_path_diagnostics.py -q`

### Task 3: Probe Runner Path Options

**Files:**
- Modify: `mcp/t30_writeback/manual_probe_runner.py`
- Modify: `mcp/acceptance/probe_workflow.py`
- Modify: `mcp/acceptance_pack/command_builder.py`

- [ ] **Step 1: Pass target_dwg_path/options into manual probe**

`run_manual_probe()` 接受 `target_dwg_path` 和 `options`，CLI 支持 `--target-dwg`、`--allow-open-document`、`--output`。

- [ ] **Step 2: Preserve read-only safety**

默认 `allow_open_document=false`，不启用真实写回，不修改原图。

- [ ] **Step 3: Verify full suite**

Run: `pytest -q`

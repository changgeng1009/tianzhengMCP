# Phase 16 Real Acceptance Execution Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 15 的真实验收流程产品化为可复制的执行包，让用户能安全拿真实图纸跑第一次 dry-run 与 sandbox 验收。

**Architecture:** 新增 `mcp/acceptance_pack/` 负责命令生成、执行包生成、结果收集、失败诊断、人工审核清单。根目录 `acceptance_pack/` 放默认模板与 bat 文件，所有真实写回命令必须显式开启 real flags，默认命令保持 dry-run。

**Tech Stack:** Python、pytest、JSON、Markdown、Windows batch commands、Phase 15 acceptance CLI。

---

### Task 1: 写 Phase 16 红灯测试

**Files:**
- Create: `tests/test_phase16_pack_builder.py`
- Create: `tests/test_phase16_command_builder.py`
- Create: `tests/test_phase16_result_collector.py`
- Create: `tests/test_phase16_failure_diagnoser.py`
- Create: `tests/test_phase16_review_list.py`

- [ ] **Step 1: 添加红灯测试**

覆盖执行包文件生成、安全命令 flags、Windows 路径引用、artifact 缺失识别、失败诊断、人工审核 Markdown/JSON。

- [ ] **Step 2: 运行红灯测试**

Run: `pytest tests/test_phase16_*.py -q`

Expected: FAIL，失败原因是 `mcp.acceptance_pack` 模块不存在。

### Task 2: 实现 acceptance_pack 模块

**Files:**
- Create: `mcp/acceptance_pack/__init__.py`
- Create: `mcp/acceptance_pack/command_builder.py`
- Create: `mcp/acceptance_pack/pack_builder.py`
- Create: `mcp/acceptance_pack/result_collector.py`
- Create: `mcp/acceptance_pack/failure_diagnoser.py`
- Create: `mcp/acceptance_pack/review_list.py`

- [ ] **Step 1: command_builder**

实现 probe、dry acceptance、real sandbox acceptance 三类 Windows 命令。dry 命令必须 `--dry-run-only true --enable-real-writeback false --real-com-mode false`；real sandbox 命令必须显式 `--dry-run-only false --enable-real-writeback true --real-com-mode true --verification-mode reread_dwg`。

- [ ] **Step 2: pack_builder**

生成 README、scenario 模板、manual confirmation 示例、三个 bat、checklist。写入失败结构化 warning。

- [ ] **Step 3: result_collector / failure_diagnoser / review_list**

收集 artifacts，识别 no_confirmed_schema / reread_verification_failed，生成人工审核清单。

### Task 3: 生成根目录执行包与文档

**Files:**
- Create: `acceptance_pack/README.md`
- Create: `acceptance_pack/scenario_template.json`
- Create: `acceptance_pack/manual_confirmation_template.example.json`
- Create: `acceptance_pack/run_probe.bat`
- Create: `acceptance_pack/run_dry_acceptance.bat`
- Create: `acceptance_pack/run_real_sandbox_acceptance.bat`
- Create: `acceptance_pack/checklist.md`
- Create: `docs/phase16_real_acceptance_execution_pack.md`

- [ ] **Step 1: 使用 pack_builder 生成默认执行包**

输出到项目根目录 `acceptance_pack/`。

- [ ] **Step 2: 写 Phase 16 说明文档**

说明执行顺序、安全默认值、真实写回必须手动开启、未 re-read verified 不能声明成功。

### Task 4: 验证

- [ ] **Step 1: Phase 16 定向测试**

Run: `pytest tests/test_phase16_*.py -q`

Expected: PASS。

- [ ] **Step 2: 全量回归**

Run: `pytest -q`

Expected: PASS，不破坏既有 303 个测试。

### Self-Review

Spec coverage:
- 执行包、命令、安全 checklist、结果收集、失败诊断、人工审核清单和文档均覆盖。
- 所有真实写回都必须显式 flags。
- 默认 bat 不真实写 CAD。

Placeholder scan:
- 无 `TBD`、`TODO`、`implement later`。

Type consistency:
- collector、diagnoser、review_list 全部使用 dict JSON 输出，便于报告和人工审核。

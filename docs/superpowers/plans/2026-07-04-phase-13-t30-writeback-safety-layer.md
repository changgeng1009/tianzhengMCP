# Phase 13 T30 Writeback Safety Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 12 的 `repair_plan_v2` 接入 T30 COM 写回前置安全层，默认 fake/simulation，真实写回必须经过 sandbox、capability、schema、transaction 和 verification gate。

**Architecture:** 新增 `mcp/t30_writeback/` 包，按模型、沙箱、探测、schema、动作转换、对象工厂、事务、验证、适配器拆分。`pipeline_v2` 只新增可选阶段 `apply_t30_writeback_v2`，不改写既有 Phase 7-12 流程。

**Tech Stack:** Python dataclasses、pytest、fake COM、Windows 文件复制、可选 pywin32 COM probe。

---

### Task 1: 写入 Phase 13 红灯测试

**Files:**
- Create: `tests/test_phase13_t30_writeback_models.py`
- Create: `tests/test_phase13_sandbox.py`
- Create: `tests/test_phase13_com_probe_fake.py`
- Create: `tests/test_phase13_parameter_schema.py`
- Create: `tests/test_phase13_action_translator.py`
- Create: `tests/test_phase13_transaction.py`
- Create: `tests/test_phase13_real_adapter_fake.py`
- Create: `tests/test_phase13_pipeline_integration.py`

- [ ] **Step 1: 添加模型、沙箱、probe、schema、translator、transaction、adapter、pipeline 测试**

测试必须覆盖 JSON 序列化、sandbox 副本、fake probe、schema confirmed gate、repair action 转换、事务状态流、rollback、adapter 默认 simulation、pipeline 默认关闭与 fake 模式开启。

- [ ] **Step 2: 运行红灯测试**

Run: `pytest tests/test_phase13_*.py -q`

Expected: FAIL，失败原因是 `mcp.t30_writeback` 模块不存在或 pipeline 参数未实现。

### Task 2: 实现 `mcp/t30_writeback` 核心包

**Files:**
- Create: `mcp/t30_writeback/__init__.py`
- Create: `mcp/t30_writeback/models.py`
- Create: `mcp/t30_writeback/sandbox.py`
- Create: `mcp/t30_writeback/com_probe.py`
- Create: `mcp/t30_writeback/parameter_schema.py`
- Create: `mcp/t30_writeback/action_translator.py`
- Create: `mcp/t30_writeback/object_factory.py`
- Create: `mcp/t30_writeback/transaction.py`
- Create: `mcp/t30_writeback/verifier.py`
- Create: `mcp/t30_writeback/real_adapter.py`
- Create: `mcp/t30_writeback/manual_probe_runner.py`

- [ ] **Step 1: 实现 dataclass 模型与 `to_dict()`**

模型包括 `T30Capability`、`T30ParameterSchema`、`T30WritebackAction`、`T30Transaction`、`T30WritebackResult`。

- [ ] **Step 2: 实现 sandbox、fake probe、schema registry、action translator**

所有失败结构化返回；未 confirmed schema 不允许 `ready_to_execute=True`。

- [ ] **Step 3: 实现 object factory、transaction engine、verifier、real adapter**

默认 fake mode；real mode 必须 capability/schema confirmed；commit 前必须 verify；rollback 从 backup 恢复 sandbox。

### Task 3: 接入 `pipeline_v2`

**Files:**
- Modify: `mcp/pipeline_v2.py`
- Test: `tests/test_phase13_pipeline_integration.py`

- [ ] **Step 1: 新增构造参数**

`Phase8PipelineEngine(..., enable_t30_real_writeback=False, t30_writeback_adapter=None, t30_writeback_options=None)`

- [ ] **Step 2: 新增可选 stage**

`apply_t30_writeback_v2` 默认不进入 stage order；开启后追加在 `safe_apply_to_cad_v2` 后、`generate_report_v2` 前。

- [ ] **Step 3: stage 行为**

没有 `phase12_repair_plan_v2` 时跳过；`dry_run_only=True` 时结构化跳过；fake 模式可以执行完整 transaction；真实模式不显式开启不做真实 COM 写入。

### Task 4: 验证

- [ ] **Step 1: Phase 13 定向测试**

Run: `pytest tests/test_phase13_*.py -q`

Expected: PASS。

- [ ] **Step 2: 全量回归**

Run: `pytest -q`

Expected: PASS，不破坏既有 263 个测试。

### Self-Review

Spec coverage:
- 数据模型、sandbox、COM probe、schema registry、object factory、action translator、transaction、verifier、real adapter、manual runner 和 pipeline 集成均有任务覆盖。
- 真实 COM 不在自动测试中执行，只通过 manual runner 暴露只读 probe。
- 默认关闭真实写回，fake COM 覆盖事务闭环。

Placeholder scan:
- 没有留下 `TBD`、`TODO` 或未定义接口。

Type consistency:
- 测试与实现统一使用 `T30WritebackAction`、`T30ParameterSchemaRegistry`、`RealT30WritebackAdapter`、`T30WritebackTransactionEngine`。

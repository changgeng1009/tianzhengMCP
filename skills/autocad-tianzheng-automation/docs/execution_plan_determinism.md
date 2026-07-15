# Execution Plan 确定性

## 当前源码

`ExecutionPlanBuilder`、canonicalizer、hasher 和 validator 已存在于 `runtime/execution_plan.py:84`、`:200`、`:206`、`:212`。Plan Schema version 为 `1.0.0`（`runtime/execution_plan.py:21`）。这些源码尚未完成 WP3 最终报告和正式测试，因此状态为 `IMPLEMENTED_IN_SOURCE_PENDING_VALIDATION`。

## Hash 规则

- Canonical Manifest hash 使用排序键、UTF-8 和路径斜杠规范化。
- Plan hash 输入排除 `plan_id` 与 `plan_hash` 本身。
- `created_at`、`generated_at`、临时运行目录、notes、随机 UUID、run ID 不参与语义投影。
- `plan_id` 由 plan hash 前 16 位派生，不使用随机 UUID。
- `verify_execution_plan()` 同时验证 hash 与派生 ID，失败返回 `PLAN_HASH_MISMATCH`；见 `runtime/execution_plan.py:66`。

## Plan 字段

Schema 要求 project/task、runtime/product/backend/workflow、approval、document requirements、protected regions、allow/deny lists、stages、artifacts、verification、recovery、limitations、`executable`、blocked reasons、manifest hash 和 plan hash。

## 执行边界

- Builder 不读取文档，所有 document requirement 的 `identity_verified=false`。
- L3/L4、Real execution、生产权限或 real CAD access 均应产生 blocked reason。
- `executable=true` 只说明离线合同没有阻断，不代表存在真实 CAD 执行器。
- `simulate_plan()` 只允许 `offline` 或 `nextgen_mock`，输出 `real_execution=false`、连接数为 false/0；源码见 `runtime/simulation.py:13`。

## 待验证

- 同输入同 hash。
- JSON 键序、非语义时间和路径分隔符不改变 hash。
- 语义变化改变 hash。
- 计划篡改触发 mismatch。
- Workflow definitions 完成后端到端 build/simulate。


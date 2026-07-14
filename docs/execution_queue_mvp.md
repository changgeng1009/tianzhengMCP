# Execution Queue MVP

## 定位

Phase 4 不是自动补图，也不是重建整张图纸。本阶段只把 Diff Result 转换为可预览、可确认、可执行的 CAD 增量操作队列。

执行链路：

```text
DiffResult
  -> ExecutionPlan
  -> OperationQueue
  -> 用户确认
  -> MCP Tool
  -> AutoCAD 实时执行
```

## 安全规则

- 所有执行计划必须先 preview。
- 未确认的计划不能执行。
- `delete_suggestion` 永远不能自动执行。
- 批量操作超过 10 个对象时标记为 high risk。
- 执行前记录当前 active_document。
- 执行结果记录成功、失败、handle 和错误信息。

## 当前支持的 OperationType

- `add_line`：真实执行。
- `add_polyline`：真实执行。
- `add_text`：真实执行。
- `move_entity`：只生成计划，执行时返回 `not_implemented`。
- `modify_entity`：只生成计划，执行时返回 `not_implemented`。
- `delete_suggestion`：只能预览，执行时返回 `not_executable`。

## MCP Tools

```text
generate_execution_plan(diff_result_json)
preview_execution_plan(plan_id)
confirm_execution_plan(plan_id)
execute_execution_plan(plan_id)
```

默认只生成和预览。没有确认前，`execute_execution_plan` 会拒绝执行。

## 示例数据

输入：

```text
examples/diff_result_sample.json
```

输出：

```text
examples/execution_plan_sample.json
```

## 手动集成测试

```powershell
python scripts/manual_execute_plan_test.py
```

脚本会读取 `examples/diff_result_sample.json`，生成并预览执行计划。为了验证基础 CAD 执行能力，脚本会额外加入仅用于手动 smoke test 的 `add_line` 和 `add_text` 操作；这些临时操作不会写回示例文件。

## 边界

- 不调用天正给排水命令。
- 不调用 `TPIPE`、`TDRAIN` 或任何天正命令。
- 不删除已有对象。
- 不批量覆盖当前图纸。
- 不导入或复制参考 DWG。
- 不重建整张图纸。

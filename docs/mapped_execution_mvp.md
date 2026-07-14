# Phase 4.6：Mapped ExecutionPlan → Safe CAD Execution

## 定位

本阶段只验证一件事：已经完成坐标映射的 `cad_world` ExecutionPlan，能否通过安全校验、预览、确认后，在当前 AutoCAD 图纸中真实创建基础 CAD 对象。

本阶段不是自动补图，不开发天正给排水工具层，不调用天正命令，不做参考 DWG 同步，也不开发 Agent 或 Monitor。

## 执行链路

```text
Mapped ExecutionPlan
  -> Safety Validation
  -> Preview
  -> User Confirmation
  -> AutoCAD Execution
  -> Execution Result
```

## 坐标安全规则

真实执行前必须满足：

- 可执行操作的 `geometry.coordinate_system` 必须是 `cad_world`。
- 不允许执行 `normalized` 坐标。
- 不允许执行 `image_pixel` 坐标。
- 可执行操作必须包含 `mapping_confidence`。
- 可执行操作必须包含 `calibration_id`。
- 可执行操作必须包含 `transform_type`。

如果不满足，执行入口返回：

```text
Coordinate mapping is not calibrated.
```

## CAD 世界坐标范围

当前 MVP 使用基础范围校验：

```json
{
  "cad_world_bounds": {
    "min_x": -100000,
    "max_x": 100000,
    "min_y": -100000,
    "max_y": 100000
  }
}
```

如果可执行对象坐标超出范围：

- 操作会被标记为 `high` risk。
- 默认不执行。
- 只有显式传入 `allow_high_risk=True` 才允许继续。

## 当前可真实执行的操作

只允许真实执行：

- `add_line`
- `add_polyline`
- `add_text`

以下操作当前只进入预览或结果记录，不会自动执行：

- `move_entity`
- `modify_entity`
- `delete_suggestion`

其中 `delete_suggestion` 永远不能自动执行。

## MCP 工具

新增工具：

```text
execute_mapped_execution_plan(plan_json, confirmed=false, allow_high_risk=false)
```

默认行为：

- 加载 mapped ExecutionPlan。
- 执行坐标和安全校验。
- 生成 preview。
- 不执行 CAD。

只有 `confirmed=true` 时才会进入真实 AutoCAD 执行。

原有 `execute_execution_plan(plan_id)` 也接入了同一套 mapped coordinate 校验，防止未映射计划绕过新安全门禁。

## 手动集成测试

运行前要求：

1. 手动打开 AutoCAD 2026。
2. 打开一个测试 DWG。
3. AutoCAD 当前不能停留在未结束命令状态。
4. Python 与 AutoCAD 权限保持一致。

运行：

```powershell
python scripts/manual_execute_mapped_plan_test.py
```

脚本流程：

1. 连接 AutoCAD。
2. 读取 `examples/mapped_execution_plan_sample.json`。
3. 追加 Phase 4.6 smoke-test `add_line` 和 `add_text`。
4. 校验所有可执行坐标为 `cad_world`。
5. 输出 preview。
6. 用户输入 `YES` 后执行。
7. 返回新增对象的 `handle` 和 `object_name`。
8. 提示用户在 AutoCAD 中执行 `ZOOM EXTENTS` 后肉眼确认。

## 示例文件

- `examples/mapped_execution_plan_sample.json`
- `examples/mapped_execution_result_sample.json`

## 已知限制

- 当前不执行 `move_entity` 和 `modify_entity`。
- 当前不自动执行删除，仅保留 `delete_suggestion`。
- 当前坐标范围是 MVP 配置，不是从图纸 extents 自动读取。
- 当前不处理天正对象或天正命令。
- 当前不做完整自动补图流程。

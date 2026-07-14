# Coordinate Mapping MVP

## 定位

Phase 4.5 只建立坐标映射层，不执行 CAD。它把 Reference Model、Diff Result 或 Execution Plan 中的 `image_pixel` / `normalized` 坐标转换为 AutoCAD 可执行的 `cad_world` 坐标。

## 为什么不能直接执行 normalized 坐标

`normalized` 坐标只表示图像范围内的比例，例如 `[0.2, 0.8]` 表示图像宽度 20%、高度 80% 的位置。AutoCAD 的 `cad_world` 坐标表示真实图纸空间中的单位坐标，例如 `[2000.0, 4000.0, 0.0]`。

如果把 `normalized` 直接当成 `cad_world` 执行，CAD 对象会被画在错误位置，通常会缩成极小对象或落在错误区域。因此未完成坐标校准时，执行队列必须拒绝真实 CAD 执行。

## 模块结构

```text
coordinate/
  models.py       # 坐标类型、点、边界框、校准点、映射结果
  calibration.py  # 2 点相似变换、3 点仿射变换
  transform.py    # normalized/image_pixel/cad_world 变换
  mapper.py       # ExecutionPlan 批量坐标映射
```

## 支持的坐标系统

- `image_pixel`
- `normalized`
- `cad_world`

三者必须显式区分，禁止混用。

## 校准点

示例：

```json
{
  "reference_point": [0.25, 0.40],
  "cad_world_point": [1000.0, 2000.0, 0.0]
}
```

当前支持：

- 2 点校准：平移、缩放、旋转。
- 3 点校准：仿射变换。

少于 2 个校准点时，坐标映射拒绝执行并返回：

```text
Coordinate mapping is not calibrated.
```

## 映射输出

映射后的 Execution Plan 会：

- 保留原始坐标。
- 写入 `cad_world` 坐标。
- 记录 `mapping_confidence`。
- 记录 `calibration_id`。
- 记录 `transform_type`。
- 坐标超出合理 CAD 范围时标记 high risk。

## 示例

输入：

```text
examples/execution_plan_sample.json
examples/calibration_points_sample.json
```

输出：

```text
examples/mapped_execution_plan_sample.json
```

## 手动测试

```powershell
python scripts/manual_coordinate_mapping_test.py
```

该脚本只输出映射前后坐标，不连接 AutoCAD，不执行 CAD。

## 后续接入

后续阶段应把 mapped execution plan 接回 Phase 4 的执行队列。只有当可执行操作的坐标系统已经是 `cad_world` 时，才允许真实 CAD 执行。

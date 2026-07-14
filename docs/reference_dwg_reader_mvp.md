# Phase 5.5：Reference DWG Reader MVP

## 定位

本阶段不是复制 Reference DWG，也不是导入完成版图纸。

Reference DWG 只作为结构化参考来源：先读取为 `ReferenceCADModel`，再与当前图纸的 `CurrentCADModel` 做 CAD-to-CAD Diff。

## 只读边界

本阶段只读：

- 不写入 CAD
- 不删除当前图纸内容
- 不复制 Reference DWG 对象
- 不导入 Reference DWG
- 不绑定外部参照
- 不调用天正命令

## 读取流程

```text
AutoCAD Documents
  -> 用户选择 current document
  -> 用户选择 reference document
  -> 读取 CurrentCADModel
  -> 读取 ReferenceCADModel
```

Reference Reader 复用 Phase 5 的 CAD Reader，但将 `source.kind` 标记为 `reference_dwg`。

## 输出

输出实体尽量对齐 `CurrentCADModel`：

- `id`
- `handle`
- `type`
- `object_name`
- `layer`
- `geometry`
- `bounding_box`
- `properties`
- `confidence`
- `source = reference_dwg`

## 手动脚本

```powershell
python scripts/manual_reference_dwg_diff_test.py
```

脚本会列出当前打开的 DWG，让用户选择 current 和 reference，然后只读生成模型和 Diff。

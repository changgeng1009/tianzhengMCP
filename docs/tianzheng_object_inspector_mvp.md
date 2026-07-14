# Phase 6.1：Interactive Tianzheng Object Inspector

## 目标

本阶段在 Phase 6.0 已确认天正给排水 T30 V1.0 环境可连接的基础上，新增交互式对象检查工具。

用户通过天正给排水 T30 V1.0 打开真实水泵房 DWG 后，运行：

```powershell
python scripts/manual_tianzheng_object_inspect.py
```

脚本会连接当前 AutoCAD 实例，提示用户在 CAD 中点击对象，并输出该对象在 COM 中暴露出的真实属性、元数据和诊断结果。

## 严格边界

- 本阶段只读，不写入 CAD。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不开发 `create_pipe` / `create_valve`。
- 不开发天正 Tool Layer。
- 不执行 CAD-to-CAD Diff 或 ROI Diff。
- 不进入自动补图。
- 不批量分解对象。

## 主要模块

### `tianzheng/object_inspector.py`

核心函数：

```python
inspect_entity(entity)
```

输入为 AutoCAD COM entity 对象，输出 JSON dict。读取内容包括：

- `handle`
- `object_name`
- `entity_name`
- `layer`
- `color`
- `linetype`
- `bounding_box`
- `available_properties`
- `xdata_available`
- `xdata`
- `extension_dictionary_available`
- `extension_dictionary_keys`
- `diagnostic`

所有属性读取都使用容错逻辑。任一属性读取失败，只记录到 `diagnostic.errors`，不会导致脚本崩溃。

### `scripts/manual_tianzheng_object_inspect.py`

脚本流程：

1. 连接当前 AutoCAD COM 实例。
2. 输出当前活动图纸。
3. 输出天正环境检测摘要。
4. 提示用户在 CAD 中点击对象。
5. 使用临时 `SelectionSet.SelectOnScreen()` 获取用户选择对象。
6. 调用 `inspect_entity(entity)`。
7. 输出 JSON 诊断结果。
8. 允许连续点击多个对象。
9. 保存结果到 `examples/tianzheng_object_inspection_sample.json`。

## 天正对象判断信号

`is_tianzheng_like` 不是只依赖单一条件，而是综合以下信号：

- `object_name` 或 `entity_name` 包含 `TCH`、`TWT`、`Tianzheng`、`Tangent`、`TArch`、`天正`。
- 图层名称包含给排水相关关键词，例如给水、排水、管、阀、泵、地漏、pipe、drain、valve、pump。
- 对象为 `AcDbProxyEntity` 或其他 Proxy 对象。
- 对象存在 XData。
- 对象存在 ExtensionDictionary。

## 建议用户点击的对象

手动测试时建议依次点击：

- 天正管线
- 阀门
- 水泵
- 地漏
- 管径标注
- 普通文字
- 普通线段
- 图块
- 标注

每次点击后保存的诊断结果将用于判断下一阶段采用哪种读取策略。

## Phase 6.1.1：对象选择兼容性修复

真实运行发现 `Utility.GetEntity("请选择一个对象: ")` 在 pywin32 下会触发：

```text
TypeError: The Python instance can not be converted to a COM object
```

根因是 AutoCAD COM 的 `Utility.GetEntity` 在 pywin32 中需要 ByRef 输出参数，不能直接按字符串 prompt 方式调用。

当前已改为：

1. 删除同名临时 SelectionSet。
2. 创建 `__TianzhengObjectInspectTemp__`。
3. 调用 `selection_set.SelectOnScreen()`。
4. 用户选择多个对象时只读取第一个。
5. 未选择对象时返回 `未选择任何对象。`。
6. 获取对象后删除临时 SelectionSet。

该修复仍然只读，不写入 CAD，不调用天正绘图命令。

## 输出示例

```json
{
  "index": 1,
  "active_document": "姓名班级学号给排水施工图20251219_t8.dwg",
  "picked_entity": {
    "handle": "ABC",
    "object_name": "AcDbProxyEntity",
    "entity_name": "AcDbProxyEntity",
    "layer": "TWT_给排水",
    "bounding_box": [0.0, 0.0, 0.0, 1000.0, 500.0, 0.0]
  },
  "diagnostic": {
    "is_proxy": true,
    "is_tianzheng_like": true,
    "xdata_available": false,
    "extension_dictionary_available": false,
    "errors": []
  }
}
```

## 测试

单元测试使用 Fake COM 对象，不依赖真实 AutoCAD / 天正：

```powershell
pytest -q
```

当前结果：

```text
115 passed
```

## 已知限制

- 当前仅诊断对象身份和可读取属性，不做天正对象语义解析。
- XData 和 ExtensionDictionary 的结构取决于真实天正对象暴露方式，需以用户点击结果为准。
- `is_tianzheng_like` 是诊断信号，不等同于已完成天正业务分类。
- 本阶段不读取或调用天正内部命令。

## 后续预留

后续需要根据真实点击样本决定进入以下方向之一：

- 天正对象语义读取。
- 天正命令调用可行性验证。
- 图块识别。
- Proxy 降级处理。
- `create_pipe` / `create_valve` Tool Layer。

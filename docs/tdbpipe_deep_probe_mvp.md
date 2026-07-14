# Phase 6.2.3：TDbPipe Diameter / Label Deep Probe

## 目标

本阶段只读探测天正给排水 `TDbPipe` 对象，尝试从对象本身读取管径、标签、管材、系统类型、管线类型、XData、ExtensionDictionary 和 COM TypeInfo。

真实测试已经发现：疑似 DN 管径文字区域被选中后，对象仍然是 `TDbPipe`，并且 XData 中出现 `TG_PIPELABEL_THICK_SHOW`。因此 DN 文字不一定是独立 `AcDbText` / `AcDbMText`，可能是 `TDbPipe` 内部显示内容或天正动态标签。

## 新增模块

- `tianzheng/tdbpipe_deep_probe.py`
- `scripts/manual_tdbpipe_deep_probe.py`
- `examples/tdbpipe_deep_probe_sample.json`
- `tests/test_tdbpipe_deep_probe.py`

## 探测内容

`probe_tdbpipe(entity)` 会读取：

- 基础身份：`Handle`、`ObjectName`、`EntityName`、`Layer`
- `BoundingBox`
- 候选属性：`Radius`、`Diameter`、`PipeDiameter`、`PipeDN`、`DN`、`NominalDiameter`、`PipeSize`、`Label`、`PipeLabel`、`TextString`、`Material`、`SystemType`、`PipeType`、`StartPoint`、`EndPoint` 等
- XData：`GetXData("")`、`GetXData(None)` 和常见 RegAppName
- ExtensionDictionary：keys、对象名、handle、常见字符串属性
- TypeInfo：`entity._oleobj_.GetTypeInfo()`
- `dir(entity)` 中疑似字段名

所有读取都使用 `try / except`。失败只记录到 `failed_properties` 或 `diagnostic.warnings`，不会中断脚本。

## 管径候选

探测器会从属性值、XData 字符串、ExtensionDictionary 字符串中识别：

- `DN200`
- `DN 200`
- `De110`
- `De 110`
- `Φ100`
- `Φ 100`
- `D100`
- `D 100`

识别结果写入 `diameter_candidates`。这些结果仍然只是候选，不会自动写回 CAD。

## 重要限制

- `TDbPipe.Radius` 不能直接当真实 DN 管径。
- `diameter_candidates` 只表示从可读字段中发现了疑似管径。
- TypeInfo 在部分 pywin32 动态 COM 对象上可能不可用。
- ExtensionDictionary 可能因天正对象封装限制无法读取。
- 本阶段不写入 CAD，不调用 `TPIPE` / `TDRAIN`，不调用天正绘图命令。

## 手动测试

运行：

```powershell
python scripts/manual_tdbpipe_deep_probe.py
```

流程：

1. 手动启动天正给排水 T30 V1.0。
2. 打开真实 DWG。
3. 运行脚本。
4. 点击一根带 DN 标注的 `TDbPipe` 管线。
5. 如果选中的不是 `TDbPipe`，脚本会提示重新选择。
6. 输出 JSON，并保存到 `examples/tdbpipe_deep_probe_sample.json`。

## 后续可能方向

如果本阶段仍无法从 `TDbPipe` 属性、XData 或 ExtensionDictionary 中读取 DN，后续需要考虑：

- 天正命令查询。
- 天正对象导出。
- 图面 OCR / 视觉识别。
- 用户确认输入 DN。

## Phase 6.2.3.1 更新：TDbPipe TypeInfo Property Reader

真实 `TDbPipe` 深度探测已经确认，天正对象的 TypeInfo / 动态属性中存在更可靠的管径字段：

- `DNDiameter`
- `SysType`
- `SElevation`
- `EElevation`
- `ModelType`
- `Label`
- `DrawLabel`
- `SysLabel`
- `Radius`
- `Length`

本阶段将 `DNDiameter` 作为 `TDbPipe` 管径读取的优先来源，并标准化为 DN 格式：

- `100` -> `DN100`
- `"100"` -> `DN100`
- `"DN100"` -> `DN100`

输出中新增：

```json
{
  "dn_diameter_raw": 100,
  "normalized_diameter": "DN100",
  "diameter_source": "TDbPipe.DNDiameter",
  "diameter_confidence": 0.95
}
```

`Radius` 只保留为 `display_radius` 或探测属性，不再生成 `diameter_guess`，也不再把 `Radius * 2` 当作真实 DN 管径。

如果 `DNDiameter` 不可读或无法标准化，`normalized_diameter` 为 `null`，并在诊断结果中保留失败原因。本阶段仍然只读，不写 CAD，不调用 `TPIPE` / `TDRAIN`，不调用任何天正绘图命令。

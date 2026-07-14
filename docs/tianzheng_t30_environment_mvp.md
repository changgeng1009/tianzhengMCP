# Phase 6.0：天正给排水 T30 V1.0 环境接入与对象可见性验证

## 定位

本阶段只验证 MCP / Python COM 是否能够连接并读取由天正给排水 T30 V1.0 启动并加载天正插件的 AutoCAD 实例。

本阶段不是自动补图，不开发天正绘图工具，不调用 `TPIPE` / `TDRAIN`，不写入 CAD。

## 用户运行前提

1. 关闭普通 AutoCAD。
2. 启动天正给排水 T30 V1.0。
3. 通过天正给排水 T30 V1.0 启动 AutoCAD 2026。
4. 通过天正打开真实水泵房 DWG。
5. 确认图纸在屏幕中可以正常显示。
6. 再运行诊断脚本。

如果检测不到天正环境，脚本返回：

```text
Tianzheng T30 environment is not detected. Please launch AutoCAD through 天正给排水 T30 V1.0.
```

## 诊断内容

### 天正环境检测

读取以下只读信号：

- AutoCAD Caption
- AutoCAD Version
- ActiveDocument
- MenuGroups
- SupportPath
- TrustedPaths
- `MENUNAME`
- `ACADVER`

只要检测到 `Tianzheng`、`Tangent`、`T30` 或 `天正` 相关线索，即标记为 detected。

### 对象可见性诊断

读取当前图纸对象，统计：

- total entities
- object_name counts
- proxy entities
- Tianzheng-like entities
- unknown CAD entities
- visible basic entities

### 用户点击对象检查

脚本读取当前选择集：

- 如果用户没有选择对象，返回空选择集，不报错。
- 如果用户已选择对象，返回 handle、object_name、layer、color、linetype、是否疑似天正对象。

### 天正命令调用可行性预留

本阶段只记录预留状态：

```json
{
  "send_command_allowed": false,
  "reserved_only": true,
  "message": "Phase 6.0 does not call Tianzheng drawing commands."
}
```

不会调用任何天正绘图命令。

## 手动脚本

```powershell
python scripts/diagnose_tianzheng_t30_environment.py
```

输出示例：

```text
examples/tianzheng_t30_diagnostic_sample.json
```

## 严格边界

- 不写入 CAD。
- 不调用 `AddLine` / `AddPolyline` / `AddText`。
- 不调用 `Delete` / `Move` / `Copy`。
- 不调用天正命令。
- 不进入自动补图。
- 不进入天正 Tool Layer。

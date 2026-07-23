# S5 Real AutoCAD COM Backend 安全边界

## 允许范围

S5 真实 COM 写入只有在全部条件同时成立时才允许：

- `product=generic_autocad`；
- `execution_runtime=com`；
- `backend=real_autocad_com`；
- `safety_level=L3_SANDBOX_WRITE`；
- 当前 job、plan hash、单次审批与注册的 synthetic 文档身份一致；
- 当前测试显式标记为 `external_integration`、`autocad_required`、`com_required`、`synthetic_cad`，并设置 `CAD_S5_AUTOCAD_INTEGRATION=1`。

L3 Manifest 声明不是审批。审批必须绑定 `job_id`、`plan_hash`、backend、product、runtime、synthetic document identity、操作白名单、到期时间与 `single_use=true`。

## 操作白名单

仅允许：`CREATE_LINE`、`CREATE_CIRCLE`、`CREATE_POLYLINE`、`QUERY_ENTITY`、`SAVE_SYNTHETIC_DOCUMENT`、`REOPEN_SYNTHETIC_DOCUMENT`、`VERIFY_SYNTHETIC_DOCUMENT`。

所有用户 DWG/DXF、课程图纸、天正图纸、历史候选图、生产文件和 `D:\CodexWork\天正\图纸` 均不在此白名单中。不得读取、哈希、扫描、复制、打开、保存、关闭或修改它们。

## 永久禁止

- `SendCommand`、LISP、`NETLOAD`、ObjectARX、AutoCAD .NET 插件、天正命令或对象；
- Legacy 实际执行器、NextGen Real listener、Production D1、L4 生产写入；
- 未验证身份的 `ActiveDocument` 回退；
- `taskkill` 或强制终止 `acad.exe`；
- 以合成 Sandbox 证据声明 Production Ready、天正可用或完整 Real Backend。

## 身份与写前复核

每次写入前必须核验 Application 版本、持有的 Document COM 引用、`Name`、`FullName`、canonical Sandbox 路径、job ID、plan hash、synthetic 标记、ownership、readonly 状态和其他用户文档状态。任一项不匹配均返回 `AUTOCAD_DOCUMENT_IDENTITY_MISMATCH`，不尝试选择“当前图纸”。

## 默认测试不变性

默认测试继续排除 external/COM/CAD 标记，并由文件访问守卫保护：

```powershell
pytest -q -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
```

该命令不得启动 AutoCAD、建立 COM 连接或读取任何 DWG/DXF（包括本阶段 synthetic DWG）。只有显式 S5 集成测试可访问当前 run 注册的 synthetic 文件。

## 启动与激活边界

- Real COM 唯一路径为 `COM_ACTIVATION` + `DispatchEx`；禁止普通 `Dispatch`、`GetActiveObject`、已有实例附着和以 `ActiveDocument` 回退。
- `PROCESS_LAUNCH` 只能进行 UI-only / 非 COM 健康检查，必须使用显式 `D:\CadAgentRuntime\s5\launch` cwd 与规范化环境；它不得连接 COM。
- COM activation 在锁保护的临时 cwd/环境上下文中进行，并保证在 `finally` 恢复；不得把临时上下文泄漏到调用方。
- COM HWND 必须映射为激活前后唯一新增的 `acad.exe` PID。不得用“任意 PID 相同”或放宽 PID 条件掩盖双实例风险。

环境边界的受控错误码为：`AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED`、`AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID`、`AUTOCAD_LAUNCH_WORKING_DIRECTORY_UNSAFE`。任一错误均停止，不回退到父 cwd、`T:`、项目目录或异常路径。

以上架构已完成 synthetic sandbox 真实集成人工验收；它不扩大到用户 DWG、生产、天正或任何其他后端。关闭最后一个 synthetic 文档后出现的 AutoCAD 默认空白文档属于 `ALLOWED_DIFFERENCE_AUTOCAD_AUTO_CREATED_DEFAULT_DOCUMENT`：核心验收依赖 synthetic 文档的持久化和幂等验证、用户 DWG/DXF 零操作以及最终 `acad.exe=0`，而不依赖关闭该默认文档。

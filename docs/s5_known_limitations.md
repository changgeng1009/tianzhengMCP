# S5 已知限制

- `RealAutoCadComBackend` 的目标上限是 `REAL_AUTOCAD_COM_MVP_SANDBOX_ONLY`，仅覆盖本阶段新建 synthetic DWG 中的 Line、Circle 和 Polyline。
- 真实 synthetic 集成证据、L3 单次审批、文档 identity 与幂等性核验已通过人工验收，`real_autocad_com` 为 `AVAILABLE_SANDBOX_MVP`；该状态只覆盖当前 job 新建的 synthetic sandbox。
- 用户 DWG/DXF、课程图纸、历史候选图、source/reference/target 图纸和生产文件永远不在 S5 访问范围内。
- 天正给排水、天正暖通、TDb/TCH、专业显示环境、工程语义、拓扑、ObjectARX、AutoCAD .NET 插件、Legacy COM 和 NextGen Real 均未实现。
- 不支持删除、Block、Layout、Xref、Text、Dimension、任意 transform 或生产批量写入。
- 不具备可验证的事务回滚；保存失败后的合成文件状态只能通过 evidence/journal 记录并人工判断。
- XData/RegApp 如在目标 COM 环境不可靠，幂等性只能采用 operation key、fingerprint、专用图层和 journal 的组合策略；该组合不替代通用工程对象语义。
- 默认 pytest 基线继续禁止所有 CAD/COM/真实 DWG 访问。S5 synthetic 集成测试必须显式隔离，不能用其结果放宽默认文件访问守卫。
- `production_allowed=false`、`production_d1_allowed=false`、`user_dwg_access=false`、天正 Real Backend=false 始终保持。
- Real COM 通过 `COM_ACTIVATION` / `DispatchEx` 完成 synthetic sandbox MVP 人工验收：支持 Line、Circle、Polyline、保存、精确路径重开、持久化和幂等验证。AutoCAD 关闭最后一个 synthetic 文档后可能自动创建默认空白文档；若最终 `acad.exe=0` 且未操作用户文件，该差异记录为 `ALLOWED_DIFFERENCE_AUTOCAD_AUTO_CREATED_DEFAULT_DOCUMENT`，不影响核心绘图闭环结论。
- `PROCESS_LAUNCH` 是独立 UI-only 合同，不可连接 COM；其安全 cwd 固定为 `D:\CadAgentRuntime\s5\launch`，且必须显式使用规范化环境。
- 双实例风险只能通过 COM HWND 与激活前后唯一新增 PID 的严格校验处理；不得以放宽 PID 规则、附着既有实例或 ActiveDocument 回退规避。
- 运行环境异常路径仅作为字符串证据保留；不得读取、删除、移动、哈希或枚举该路径内容。

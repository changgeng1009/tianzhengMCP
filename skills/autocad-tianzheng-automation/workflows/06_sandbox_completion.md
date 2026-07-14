# 06 Sandbox 补全

- 适用模式：普通 CAD、给排水；暖通写入仅 `INTERFACE_ONLY`。
- 输入：批准计划、job Sandbox 身份和保护区域。
- 前置条件：未来需 L3 单次审批，源文件与 Sandbox 身份分离。
- 允许操作：本阶段仅 Mock/计划。
- 禁止操作：源 DWG、计划外对象、重复对象、真实产品命令。
- 输出：批次计划、checkpoint、append-only journal。
- 安全门：L3、plan hash、document hash。
- 停止条件：身份变化、保护区域、后端不可用。
- 人工复核点：每批差异与候选图。

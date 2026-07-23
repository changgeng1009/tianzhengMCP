# AutoCAD 会话所有权策略

## 原则

`AutoCadSessionIdentity` 和 `DocumentOwnershipRegistry` 必须以本阶段显式持有的 Application/Document COM 对象为依据。不得通过全局 `application.ActiveDocument`、最近打开文件或文件名猜测取得写目标。

## 新建会话

若 S5 新建 AutoCAD 实例，记录会话创建者、Application 版本、创建时间、run ID 和当前 job。该实例只允许打开/关闭本阶段 synthetic Document。只有关闭后确认不存在用户文档时，才可以正常 `Quit()`；禁止强制结束进程。

## 附着会话

若安全附着到已有 AutoCAD：

- 枚举文档仅用于识别风险，不读取任何文档内容；
- 不打开、保存、关闭、激活或修改任何已有用户文档；
- 只能新建并登记本阶段 synthetic Document；
- 不退出用户启动的 AutoCAD 实例。

若无法可靠区分已有文档与当前 synthetic Document，停止 S5 真实测试并返回 `CAD_S5_BLOCKED_BY_ACTIVE_USER_DOCUMENT` 或 `AUTOCAD_SESSION_UNSAFE`。

## 生命周期

会话管理器必须有界等待每个 COM 阶段，记录启动、创建、写入、保存、关闭、重开的耗时。超时只能标记 `AUTOCAD_TIMEOUT` 和人工处理，不得转而操作其他文档，也不得 `taskkill`。

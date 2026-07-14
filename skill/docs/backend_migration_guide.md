# Backend Migration Guide

## COM → .NET/ObjectARX Bridge

1. 实现 `NetBridgeCadBackend` 的本地 IPC。
2. 将插件返回映射为统一 Backend models。
3. 注册真实 capability 和 evidence。
4. 对每个 create/save/QA capability 完成 sandbox verification。
5. 更新 `backends.yaml` routing。

不得修改 recognition、alignment、diff、task classification、geometry validation、safety、QA schema 或 reporting。

## COM/.NET → 天正官方 API

1. 实现 `TianzhengOfficialApiBackend`。
2. 映射官方给排水对象类型和属性。
3. 注册 `create_tdb_*`、设备、network capability。
4. 增加官方错误映射。
5. 通过对象级 sandbox 和持久化测试。
6. 更新 routing。

同样不得重写完整 Skill。上层任务只改变 `selected_backend` 和 capability evidence。

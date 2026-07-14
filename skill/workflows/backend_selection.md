# Backend Selection

依次检查 task authorization、classification、geometry、source/copy 隔离、required capabilities、availability、capability completeness、sandbox verification 和 fallback policy。

普通 AcDb 只能路由到具备对应 create capability 的 backend。TDb capability 不足时显式进入 manual/blocked；不得改为 AcDbLine。输出完整候选和选择证据。

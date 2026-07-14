# Backend Contract

Protocol 位于 `mcp/backends/base.py`，统一模型位于 `mcp/backends/models.py`。

每次 probe/scan/create/save/close/reopen 必须携带 `backend_id`；执行结果必须记录 capability evidence、created IDs/handles、draw delta、是否真实 CAD 执行及是否修改真实 DWG。异常统一转为 `BackendError`。

## .NET Bridge 消息边界

未来 transport 可为 localhost HTTP、Named Pipe 或显式配置的本地 IPC。业务层不得感知 transport。请求必须包含 `request_id`、`run_id`、`backend_version`、`document_path`、`expected_document_hash`、`operation`、`payload`、`safety_context`、`timeout`、`idempotency_key`。

返回必须包含 success/error、created IDs/handles、draw delta、command started/ended/cancelled/failed、transaction committed 和 document saved。默认 `enabled=false`、`available=false`、`execution_allowed=false`。

## 天正官方 API

只在 `TianzhengOfficialApiBackend` 内映射官方对象、错误和网络操作。当前未检测到官方 API，所有 create TDb capability 为 false。

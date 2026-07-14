# Backend Architecture

`CadBackend` 是专业无关 Protocol。业务层只接收 `ScanResult`、`RepairTask`、`ExecutionResult` 等序列化模型，不接触 COM object、HTTP response、Named Pipe handle 或官方 API 类型。

Safety enforcement 先执行；Router 后执行。Backend 不能改变 classification、补齐猜测 geometry、把 TDb 降级为 AcDb，或静默 fallback。

当前实现：

- COM adapter：已有能力集中封装；只在显式 `connect()` 时导入 pywin32。
- Mock：内存 dry-run，不修改真实文件。
- Net Bridge：禁用契约骨架。
- Tianzheng Official API：禁用契约骨架。

识别、alignment、diff、classification、geometry、QA 和 reporting 不因 backend 变化而改写。

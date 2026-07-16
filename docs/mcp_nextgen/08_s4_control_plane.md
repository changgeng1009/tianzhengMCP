# S4 NextGen MCP Mock-only 控制面

## 结论

S4 将 NextGen MCP 控制面冻结为 `IMPLEMENTED_BASELINE`，但范围严格限于 `offline` 与 `nextgen_mock`。它管理版本化协议、工具发现、Mock job、审批、进度、checkpoint 与 journal；它不连接 AutoCAD、天正或 COM，不读取 DWG/DXF，也没有 listener、Real backend 或生产写入。

## MCP 发现面

- 13 tools：`cad.capabilities`、`cad.documents.list`、`cad.document.inspect`、`cad.entities.query`、`cad.entities.inspect`、`cad.batch.plan`、`cad.batch.clone`、`cad.batch.transform`、`cad.job.status`、`cad.job.approve`、`cad.job.run_mock`、`cad.job.cancel`、`cad.job.events`。
- 3 resources：`cad://nextgen/capabilities`、`cad://nextgen/tool-registry`、`cad://nextgen/safety-boundaries`。
- 2 prompts：`cad.plan_mock_job`、`cad.review_safety_boundary`。

每个 tool 都声明名称、说明、版本化 input/output/error Schema、支持等级和安全字段。`cad.entities.query`、`cad.entities.inspect`、`cad.batch.clone`、`cad.batch.transform` 为 `NOT_IMPLEMENTED`；它们必须安全拒绝，不能因存在 Schema 而被视为可用。

## 作业与进度

`ControlPlaneService` 只维护 Mock job，并验证以下状态转换：

```text
CREATED -> PLANNED -> APPROVED -> RUNNING -> COMPLETED
                 \-> FAILED / CANCELLED
```

进度事件包含 job ID、事件名、当前状态、完成数量、总数量、进度百分比和错误代码。`cad.job.events` 返回已记录事件；它不是订阅式 listener。

## 审批、恢复与审计

`cad.job.approve` 只接受绑定 `job_id`、`plan_hash`、`operation`、`product`、`runtime`、允许操作、到期时间和 `single_use=true` 的审批。所有生产字段必须为 false；审批不能从 Manifest、资源或 prompt 自动继承。

Mock job 使用 append-only、SHA-256 previous-hash 链 journal 与原子 checkpoint。checkpoint 显式记录 `last_completed_batch_id`、`completed_batch_count`、`completed_task_count`、计划哈希及 journal anchor，用于受支持 Mock 状态的恢复与篡改检测。它不是多进程 writer fencing，也不是 DWG 保存或工程语义证据。

## 不变的边界

- `NextGenRealBackend`、Legacy COM、AutoCAD .NET/ObjectARX、天正 Water/HVAC Real 均为 `NOT_IMPLEMENTED`。
- `LegacyAdapter=DISABLED_CONTRACT_ONLY`。
- `production_allowed=false`、`production_d1_allowed=false`、`real_cad_access=false`、`real_backend=false`。
- FastMCP 对象 import-safe 且 `auto_start=false`；没有 stdio、HTTP、TCP、Named Pipe 或本地 listener。

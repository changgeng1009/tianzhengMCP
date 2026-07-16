# MCP NextGen 协议

## 版本

应用协议版本固定为 `1.0.0`：

- `PROTOCOL_VERSION = "1.0.0"`
- 当前只支持该版本。
- `negotiate_version()` 在无共同版本时硬拒绝。
- 核心模型和工具 Schema 均要求 `schema_version=1.0.0`。

JSON-RPC 的 `2.0` 是 transport envelope 版本，不替代应用协议版本。

## 核心结构

当前定义 12 个 canonical 结构：

1. `DocumentIdentity`
2. `OperationIntent`
3. `ExecutionPlan`
4. `ExecutionTask`
5. `JobRecord`
6. `Checkpoint`
7. `JournalEntry`
8. `ApprovalContext`
9. `CapabilityRecord`
10. `ExecutionResult`
11. `ProgressEvent`
12. `ErrorRecord`

关键公共语义包括：

- `schema_version`
- `request_id`、`job_id`、`idempotency_key`
- `created_at`、`updated_at` 或事件时间戳
- `document_full_path`、`document_sha256`、`document_role`
- `operation`、`plan_hash`、`batch_id`、`task_id`
- `approval_level`、`production_allowed`、`dry_run`
- `status`、`error_code`、`evidence_paths`

`ExecutionTask` 与 `JournalEntry` 显式区分 `automatic_dependency`。`Checkpoint` 和 `JobRecord` 分离记录 `last_completed_batch_id`、`completed_batch_count`、`completed_task_count`。

## 13 个工具

| 工具 | 当前审批等级 | 当前行为 |
|---|---|---|
| `cad.capabilities` | L0 | 返回协议、Mock identity 和工具列表 |
| `cad.documents.list` | L0 | 返回空 Mock 文档列表 |
| `cad.document.inspect` | L0 | 校验并回显 Mock 文档身份，不访问文件 |
| `cad.entities.query` | L0 | 当前 `NOT_IMPLEMENTED` |
| `cad.entities.inspect` | L0 | 当前 `NOT_IMPLEMENTED` |
| `cad.batch.plan` | L1/L2 | 强制 `dry_run=true`，创建 `PLANNED` 的 Mock job |
| `cad.batch.clone` | L1/L2 | Mock-only 占位，强制 dry-run，当前 `NOT_IMPLEMENTED` |
| `cad.batch.transform` | L1/L2 | Mock-only 占位，强制 dry-run，当前 `NOT_IMPLEMENTED` |
| `cad.job.status` | L0 | 返回 Mock job 当前状态与计数 |
| `cad.job.approve` | L1/L2 | 将单次、过期受限审批绑定到 `PLANNED` Mock job |
| `cad.job.run_mock` | L1/L2 | 运行确定性 Mock 模拟，禁止真实 CAD |
| `cad.job.cancel` | L1/L2 | 取消未终态的 Mock job |
| `cad.job.events` | L0 | 返回有序 Mock 进度事件，不订阅外部 listener |

工具 registry 全部声明：

- `backend_kind=MOCK`
- `real_backend_available=false`
- `production_d1_allowed=false`
- 严格 `inputSchema` / `outputSchema`
- `additionalProperties=false`

其中 `cad.capabilities`、`cad.documents.list`、`cad.document.inspect`、`cad.batch.plan` 与 `cad.job.*` 为 `IMPLEMENTED_BASELINE`；实体查询以及 clone/transform 仅有协议合同，状态为 `NOT_IMPLEMENTED`。任何 `NOT_IMPLEMENTED` 工具都不得标记为可用。

## Resources 与 Prompts

发现层还声明 3 个只读资源：`cad://nextgen/capabilities`、`cad://nextgen/tool-registry`、`cad://nextgen/safety-boundaries`；以及 2 个无执行副作用提示：`cad.plan_mock_job`、`cad.review_safety_boundary`。它们只返回版本化静态或 Mock-only 描述数据，不打开文件、不启动 listener，也不授予审批。

## 审批等级

协议定义：

- `L0_READ_ONLY`
- `L1_DRY_RUN`
- `L2_SANDBOX_PREP`
- `L3_SANDBOX_WRITE`
- `L4_CONTROLLED_PRODUCTION`

当前 registry 不允许 L3/L4 工具执行。L4 只是协议枚举，不代表生产能力已经实现或授权。

`ApprovalContext` 绑定 request/job/idempotency、完整文档身份、plan hash、allowed operations、expiry 和 single-use。当前所有生产字段必须为 false。

## Schema 校验

内置校验器覆盖 type、required、const、enum、字符串长度、数组数量/唯一性、pattern、数值范围和带时区 date-time。工具 envelope 还校验 request/idempotency 与 params 内字段一致。

FastMCP 外层函数参数是单个 `request` object；canonical 合同以 `NEXTGEN_TOOLS` 和 dispatcher 校验为准，不能绕过 dispatcher。

## 兼容与变更

任何不兼容字段变更必须提升协议版本。旧实验 schema 和正式项目旧 API 只能经 adapter 映射，不能改变 `1.0.0` canonical 字段含义。


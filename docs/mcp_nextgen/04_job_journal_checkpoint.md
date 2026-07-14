# Job、Journal 与 Checkpoint

## 来源裁决

DeepSeek 原 Layer D 被整体拒绝，原因包括 resume 重放、split 重复写、partial journal 不一致、entity/task ID 混用、内存幂等、无 previous-hash、审批不足等。当前 `mcp_nextgen/jobs`、`journal`、`safety` 是隔离重写，不是原 JobExecutor 的修补或复制。

## Job 状态

新状态机包含安全边界和 `MANUAL_SAVE_REQUIRED`。终态不允许继续推进。rollback 明确为 `NotImplementedError`，本阶段不声称具备 CAD/DWG 回滚。

`LayerDCoordinator` 负责：

- 创建 job 与持久幂等 begin
- 显式状态转换
- 完成 task 与提交 batch
- 记录 manual-save
- 完成 job
- journal replay 与 checkpoint 互核
- 返回恢复后的剩余任务视图

## 任务身份与自动依赖

`task_id` 不与 entity ID 混用。任务来源区分：

- `PLANNED`
- `AUTO_DEPENDENCY`

恢复视图分别返回剩余计划任务和剩余自动依赖，避免把自动依赖误判为计划外对象。

## Journal

`FileJournalStore` 使用 append-only JSONL：

- sequence 必须连续
- 每条有完整 SHA-256 `previous_hash` 与 `entry_hash`
- 写前读取并验证现有链
- append 后 flush + `fsync`
- replay 前重算完整 hash chain
- job ID 经路径 allowlist/containment 校验

journal 是恢复事实来源；job 快照只是查询和性能副本，不能覆盖 journal。

## Checkpoint

`FileCheckpointStore`：

1. 写唯一临时文件；
2. flush + 文件 `fsync`；
3. `os.replace` 原子替换；
4. 支持时对目录执行 `fsync`；
5. 清理残留临时文件。

checkpoint 明确包含：

- `last_completed_batch_id`
- `completed_batch_ids` / 动态 `completed_batch_count`
- `completed_task_ids` / 动态 `completed_task_count`
- `journal_sequence`
- `journal_head_hash`
- `manual_save_required`

这些计数从实际 ID 集合计算，不依赖硬编码批次号。

## Resume

恢复流程以 journal replay 重建 job，然后与 checkpoint 核验：

- plan hash
- job status
- completed batch IDs
- completed task IDs
- last completed batch ID
- manual-save 状态
- journal sequence/head hash

resume 只返回未完成任务；已完成任务不会重新进入待执行集合。非连续 batch ID 也按实际集合计数。

## 幂等

`FileIdempotencyStore` 使用 canonical request SHA-256 和原子文件写入：

- 相同 key + 相同请求不重复创建
- 相同 key + 不同请求触发冲突
- 完成结果持久化

## 超时与取消

`SafeBoundaryController` 在普通任务边界检查 deadline/cancel；持久化临界区内延迟抛出，避免破坏 journal/checkpoint/save 的提交边界。

## 当前限制与验证

- 多进程 writer 锁未实现。
- single-use 审批消费账本未独立持久化。
- recover 不自动把运行中 job 提升为 `RECOVERY_REQUIRED`，由上层恢复流程显式处理。
- coordinator 尚未接入 MCP dispatcher。
- 实现 Agent 的隔离自检已通过；正式 `tests/nextgen`、checkpoint 硬编码回归和主线全量回归待 test_agent 最终验证。



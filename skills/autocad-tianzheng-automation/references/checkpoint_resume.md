# Checkpoint 与恢复

Checkpoint 必须原子写入，Journal 必须 append-only。分别记录 `last_completed_batch_id`、`completed_batch_count`、`completed_task_count`，禁止硬编码批次编号。

每个任务使用幂等键；恢复时校验 `plan_hash`，自动分类依赖、计划外对象和重复对象。外层超时后从最后已完成任务恢复，不重复执行。保存验证失败时输出 `MANUAL_SAVE_REQUIRED`。恢复前重新核验 ActiveDocument 身份和哈希。

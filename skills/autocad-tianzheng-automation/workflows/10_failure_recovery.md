# 10 失败恢复

- 适用模式：全部 checkpoint 作业。
- 输入：原子 checkpoint、append-only journal、当前计划。
- 前置条件：plan hash 一致，ActiveDocument 身份重新通过。
- 允许操作：从最后已完成任务之后恢复。
- 禁止操作：硬编码批次、重复执行、继承历史授权。
- 输出：恢复计划、重复/计划外对象分类。
- 安全门：重新审批、幂等键与超时边界。
- 停止条件：checkpoint 不一致、授权无效或文档变化。
- 人工复核点：未归类的 journal 记录。

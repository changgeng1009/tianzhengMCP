# intent_mapper_agent — 提示词模板

## Agent 身份

你是 **intent_mapper_agent**，负责天正 CAD MCP 接口系统中的用户意图解析、自然语言到结构化命令的映射，以及视觉对比和语义差异分析。

## 核心职责

1. 将用户自然语言意图解析为结构化命令。
2. 维护意图模板库和映射规则。
3. 实现视觉对比引擎和语义差异引擎。
4. 负责坐标映射和管网拓扑构建。

## 负责文件

- `vision/` — 视觉对比引擎
- `coordinate/` — 坐标映射
- `semantic_diff/` — 语义差异引擎
- `pipe_network/` — 管网拓扑图
- `cad_compare/` — CAD 对比差异

## 禁止事项

- 禁止直接执行 CAD 操作（应由 cad_bridge_agent 执行）
- 禁止连接 AutoCAD
- 禁止使用 SendCommand
- 禁止修改 `cad/`、`tianzheng/`、`tianzheng_interface/` 模块
- 禁止修改 ROADMAP.md 和 TASK_BOARD.md

## 输入

- 从 `agent_inbox/intent_mapper_agent.md` 读取任务。
- 参考 `AGENTS.md` 了解全局协作规范。
- 参考 `docs/knowledge.md` 了解历史意图模板。

## 输出

- 将任务结果写入 `agent_outbox/intent_mapper_agent_report.md`。
- 报告格式严格遵循 `docs/report_template.md` 模板。

## 工作流程

1. 读取自己的 inbox 文件获取任务。
2. 分析用户意图类型（创建/修改/查询/对比/删除）。
3. 将意图映射到 `command_registry_agent` 已注册的标准命令。
4. 如果涉及视觉对比，构建 Reference Model 和 Current CAD Model 并执行 Diff。
5. 如果涉及坐标，完成坐标映射和管网拓扑分析。
6. 输出结构化的意图解析结果和命令序列。
7. 完成后写入 outbox 报告。

## 意图解析规范

支持的意图类型：
- `create_pipe`: 创建管线
- `modify_pipe`: 修改管线属性
- `delete_pipe`: 删除管线
- `compare_drawings`: 对比两张图纸
- `query_objects`: 查询图纸对象
- `align_models`: 对齐参考模型
- `build_network`: 构建管网拓扑

## 注意事项

- 意图解析结果必须是结构化 JSON，不允许自然语言作为业务输出。
- 不确定的意图应标记置信度并列出候选解释，不要强行映射。
- 坐标映射必须确认 calibration 有效后才能输出 cad_world 坐标。
- 管网拓扑的 `diameter` 仅使用 `diameter.normalized`（来自 TDbPipe.DNDiameter）。

---

# Task for intent_mapper_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-CMP-001

## Task Description

递归对照 DeepSeek 实验项目与正式项目，生成能力矩阵审计素材，至少覆盖：MCP server、transport、action schema、job、journal、checkpoint、resume、idempotency、safety gate、document identity、approval、mock/real backend、COM adapter、plugin interface、capability、progress、timeout、manual save、protected region、original integrity、batch execution、acceptance reports。为每项给出 `deepseek_lab_implementation`、`current_mainline_implementation`、`better_implementation`、`conflict`、`integration_strategy`、`decision`，并审计 OperationIntent/ExecutionPlan/ExecutionTask 等核心结构现状。

## Constraints

- 只读审计，不修改代码、测试、文档或 artifacts；只写 outbox 报告。
- 禁止 AutoCAD/天正/COM，禁止读取或修改 DWG，禁止 P4.1/Production D1。
- 不导入真实执行模块，不以“架构更新”作为优于主线的依据。

## Expected Output

- `agent_outbox/intent_mapper_agent_report.md`
- 至少 24 项完整能力矩阵素材与核心数据结构差距清单，附真实路径/行号。

---

# Task for intent_mapper_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-MIG-LAYERD-005

## Task Description

由于实验 Layer D 已 REJECT，在隔离命名空间实现安全的 nextgen job/journal/checkpoint/safety 基线，不复制实验写路径。实现合法 job 状态转换、append-only journal（sequence + full SHA-256 previous_hash 链）、checkpoint 原子写入与 journal 互校验、动态 `last_completed_batch_id/completed_batch_count/completed_task_count`、resume 跳过已完成任务、计划任务与自动依赖分类、持久幂等与完整 canonical request hash、审批验证、document identity/plan_hash 绑定、crash recovery、MANUAL_SAVE_REQUIRED、timeout/cancellation 不破坏保存/checkpoint 临界区。所有持久化 ID 白名单并做 resolved-path containment。

## Owned Files

- `mcp_nextgen/jobs/**`
- `mcp_nextgen/journal/**`
- `mcp_nextgen/safety/**`

## Constraints

- 依赖 command_registry_agent 的 `mcp_nextgen.protocol`；若尚未完成，可先实现无冲突模块并在最后对齐 import。
- 不修改旧 checkpoint/executor/P4.1、tests 或实验项目。
- 禁止 AutoCAD/天正/COM/DWG/P4.1/Production D1；不运行任何执行器。
- 不实现 rollback 写图；只定义状态/补偿记录，未实现项明确 TODO/NotImplemented。

## Expected Output

- 上述隔离实现与标准 `agent_outbox/intent_mapper_agent_report.md`。
- 报告列出状态机、恢复/幂等/原子性自检与未实现能力。

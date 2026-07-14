# agent_inbox — 任务派发收件箱

## 概述

`agent_inbox/` 是 Manager 向各子 Agent 派发子任务的目录。每个子 Agent 在此目录下拥有一个独立的 Markdown 文件，Manager 通过写入该文件来分派任务。

## 工作方式

### 1. 文件命名规则

每个子 Agent 的 inbox 文件命名格式为 `<agent_name>.md`：

```
agent_inbox/
├── planning_agent.md
├── command_registry_agent.md
├── cad_bridge_agent.md
├── intent_mapper_agent.md
├── safety_audit_agent.md
├── test_agent.md
├── docs_agent.md
└── README.md
```

### 2. 任务写入

Manager 将任务写入对应 Agent 的 inbox 文件，格式如下：

```markdown
# Task for <agent_name>
## Assigned by: Manager
## Phase: <phase_id>
## Task ID: <task_id>
## Priority: high | medium | low
## Deadline: <YYYY-MM-DD>（可选）
## Dependencies
- <dependency_task_id>（可选）
## Task Description
<详细任务描述，建议包含具体可验收的标准>
## Input Files
- <绝对路径或项目相对路径>
## Constraints
- <禁止事项，逐条列出>
## Expected Output
- <输出文件路径列表>
```

### 3. 任务读取

子 Agent 启动时读取自己的 inbox 文件，确认任务内容后开始执行。如果 inbox 文件不存在，子 Agent 应等待 Manager 写入任务，或向 Manager 请求任务。

### 4. 任务生命周期

```
  [Manager 写入] → [子 Agent 读取] → [子 Agent 执行] → [子 Agent 写入 outbox]
       ↓                                                       ↓
  inbox 更新                                         outbox 报告就绪
```

### 5. 注意事项

- Manager 不应同时向同一个子 Agent 写入多个未完成任务。
- 如果有新任务需要在当前任务进行中追加，Manager 应在原 inbox 文件中追加 `## Additional Task` 段落，并递增 Task ID。
- 子 Agent 在完成任务后，应在 outbox 报告中引用对应的 Task ID。
- 子 Agent 不应修改其他 Agent 的 inbox 文件。
- Inbox 文件应使用 UTF-8 编码，换行符为 LF。

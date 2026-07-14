# AGENTS.md — 天正 CAD MCP 接口系统 Multi-Agent 协作规范

## 概述

本项目采用 Multi-Agent 协作架构，由一个总控 Agent（Manager）统一调度七个子 Agent，各自负责独立域的工作。Agent 之间通过 `agent_inbox/` 和 `agent_outbox/` 进行任务派发与结果回传。

> **当前阶段**: Phase M0 已完成 ✅ | 下一阶段：Phase M1。

## 仓库级长期规则

- 这是项目根目录规则文件，优先级高于普通说明文档。
- 默认只读优先，除非当前任务明确要求写入。
- 未经确认，不得修改业务源码、测试逻辑、配置语义或目录结构。
- 版本基线、提交记录、远程配置、`.gitignore` 和本文件是允许的仓库治理范围。
- 所有提交前必须确认变更范围，不得把临时文件、缓存、日志、私钥、密钥、Cookie、Session、`.env`、证书或大体积产物纳入版本库。
- 发现敏感信息时，只记录文件路径、变量名和风险类型，不展示秘密值本身。
- 任何 Git 推送必须是普通安全推送，不得使用 `--force`、`-f` 或重写远程历史。
- 如果仓库中同时存在多个 Git 仓库或子仓库，必须先确认目标根仓库，再处理当前任务范围。

## Agent 角色与职责

### 总控 Agent（Manager）

Manager 是唯一直接与用户交互的 Agent，不亲自执行任何开发任务。

**职责**:
- 接收用户任务请求，对任务进行分解和路由。
- 将子任务写入对应子 Agent 的 `agent_inbox/<agent_name>.md`。
- 读取各子 Agent 的 `agent_outbox/<agent_name>_report.md`，汇总结果。
- 推进项目阶段、维护 ROADMAP.md 和 TASK_BOARD.md。
- 执行跨 Agent 的安全检查与冲突裁决。
- 决定是否进入下一阶段。

### 子 Agent 列表

| Agent 名称 | 职责 | Inbox | Outbox |
|-----------|------|-------|--------|
| `planning_agent` | 阶段规划、路线图更新、任务看板维护 | `agent_inbox/planning_agent.md` | `agent_outbox/planning_agent_report.md` |
| `command_registry_agent` | MCP 工具注册、命令 Schema 定义与维护 | `agent_inbox/command_registry_agent.md` | `agent_outbox/command_registry_agent_report.md` |
| `cad_bridge_agent` | AutoCAD COM 通信层开发、天正接口适配 | `agent_inbox/cad_bridge_agent.md` | `agent_outbox/cad_bridge_agent_report.md` |
| `intent_mapper_agent` | 用户意图解析、自然语言到命令的映射 | `agent_inbox/intent_mapper_agent.md` | `agent_outbox/intent_mapper_agent_report.md` |
| `safety_audit_agent` | 安全审计、操作护栏、冲突检测 | `agent_inbox/safety_audit_agent.md` | `agent_outbox/safety_audit_agent_report.md` |
| `test_agent` | 自动化测试、集成验证、回归测试 | `agent_inbox/test_agent.md` | `agent_outbox/test_agent_report.md` |
| `docs_agent` | 文档编写、架构文档、报告模板 | `agent_inbox/docs_agent.md` | `agent_outbox/docs_agent_report.md` |

### 子 Agent 详细职责

#### planning_agent
- 创建并维护 `ROADMAP.md` 和 `TASK_BOARD.md`。
- 将 Manager 的阶段目标转化为具体任务清单。
- 追踪各阶段完成状态，标记依赖关系。
- 不允许修改其他 agent 的代码或文档。

#### command_registry_agent
- 管理 MCP Tool 注册表。
- 定义命令的 JSON Schema（输入/输出格式）。
- 维护命令版本和兼容性。
- 不允许连接 AutoCAD，不允许执行命令。

#### cad_bridge_agent
- 对接 AutoCAD COM 接口和天正 T30 V1.0 插件。
- 实现 CAD 对象读取、创建、修改的底层操作。
- 提供统一的 `cad/`、`tianzheng/`、`tianzheng_interface/` 模块。
- 每次操作前必须确认 Safety Audit 通过。

#### intent_mapper_agent
- 将用户的自然语言意图解析为结构化命令。
- 维护意图模板库和映射规则。
- 输出可被 `command_registry_agent` 注册的标准命令格式。
- 不允许直接执行 CAD 操作。

#### safety_audit_agent
- 在每个阶段开始前审计安全边界。
- 检查命令是否符合只读/写入/修改安全等级。
- 验证操作不会破坏源 DWG。
- 输出安全审计报告，决定操作是否放行。

#### test_agent
- 编写并执行单元测试、集成测试、回归测试。
- 使用 Fake COM 对象，不依赖真实 AutoCAD。
- 在每个子任务完成后验证代码质量。
- 不允许连接 AutoCAD。

#### docs_agent
- 编写和维护项目文档（架构文档、API 文档、报告模板）。
- 创建各 Agent 的提示词模板。
- 整理阶段报告格式和协作规范。
- 不允许修改代码，不允许连接 AutoCAD。

## 通讯机制

### agent_inbox / agent_outbox

- **Inbox**: Manager 向子 Agent 派发任务时，将任务描述写入 `agent_inbox/<agent_name>.md`。
- **Outbox**: 子 Agent 完成任务后，将报告写入 `agent_outbox/<agent_name>_report.md`。

### 任务派发流程

1. Manager 接收用户请求，进行任务分解。
2. Manager 将子任务写入对应 Agent 的 inbox 文件。
3. 子 Agent 读取自己的 inbox，执行任务。
4. 子 Agent 将结果写入自己的 outbox 文件。
5. Manager 轮询各 outbox，汇总结果。
6. Manager 将综合结果反馈给用户。

### Inbox 文件格式

```markdown
# Task for <agent_name>
## Assigned by: Manager
## Phase: <phase_id>
## Task ID: <task_id>
## Deadline: <optional>
## Task Description
...
## Input Files
- path/to/file1
- path/to/file2
## Constraints
- 禁止事项列表
## Expected Output
- 输出文件列表
```

### Outbox 文件格式

```markdown
# Agent Report
## Agent Name: <agent_name>
## Assigned Task: <task_id>
## Files Read
## Files Modified
## Work Completed
## Tests Run
## Test Result
## Safety Check
## Risks Found
## Remaining Work
## Recommendation
```

## 阶段推进规则

- 所有阶段由 Manager 统一调度，子 Agent 不能自行推进阶段。
- 每个阶段必须完成以下检查后才能进入下一阶段：
  1. 所有子 Agent 任务完成，outbox 报告就绪。
  2. `safety_audit_agent` 安全审计通过。
  3. `test_agent` 全量测试通过。
  4. `docs_agent` 文档更新完毕。
- Manager 在确认全部条件满足后，更新 ROADMAP.md 状态。

## 全局安全规则

所有 Agent 必须遵守以下安全规则（违反即阻止）：

1. **禁止未经确认连接 AutoCAD**：只有 `cad_bridge_agent` 可在获得 Manager 明确授权后连接 AutoCAD。
2. **禁止打开非任务指定的 DWG 文件**：每次 DWG 操作前必须核实文件路径。
3. **禁止使用 SendCommand 执行破坏性操作**：包括但不限于 `ERASE`、`DELETE`、`WBLOCK`、`PURGE`（除非 Safety Audit 明确放行）。
4. **禁止执行天正绘图命令**（如 `TPIPE`、`TDRAIN`、`TSPRINKLER` 等）除非 Manager 明确授权。
5. **禁止保存/覆盖源 DWG**：所有写操作只能针对临时副本或测试文件。
6. **禁止修改源 DWG**：源 DWG 作为参考基准，只读、不写、不改、不覆盖。
7. **只读优先原则**：任何 Agent 在不确定操作安全性时，应选择只读模式并将疑问上报 Safety Audit。

## 子 Agent 输出格式

每个子 Agent 在完成 outbox 报告时，必须包含以下标准字段：

```markdown
# Agent Report
## Agent Name
## Assigned Task
## Files Read
## Files Modified
## Work Completed
## Tests Run
## Test Result
## Safety Check
* Connected to AutoCAD: YES/NO
* Opened DWG: YES/NO
* Opened source DWG: YES/NO
* Used SendCommand: YES/NO
* Executed Tianzheng command: YES/NO
* Saved DWG: YES/NO
* Modified source DWG: YES/NO
## Risks Found
## Remaining Work
## Recommendation
```

## 并行工作规则

- 无依赖关系的子 Agent 可以并行工作（如 `docs_agent` 和 `test_agent` 可同时执行）。
- 有依赖关系的 Agent 必须按序执行（如 `cad_bridge_agent` 必须等待 `safety_audit_agent` 通过）。
- Manager 在派发任务时标注依赖关系。
- 子 Agent 不应修改另一个子 Agent 负责的文件。

## 冲突处理

- 当两个 Agent 的输出产生冲突时，Manager 拥有最终裁决权。
- 子 Agent 在发现冲突时应上报 Manager，不应自行裁决。
- Safety Audit 的裁决优先于其他 Agent 的建议。

## 当前阶段信息（已更新）

- **Phase M0**：Multi-Agent 协作基础设施搭建 — ✅ 已完成。
- **Manager**：由 Codex 总控（当前会话接管）。
- **活跃子 Agent**：planning_agent、command_registry_agent、cad_bridge_agent、safety_audit_agent、test_agent、docs_agent（M0 已完成全部任务）。

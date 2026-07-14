# agent_outbox — 任务结果发件箱

## 概述

`agent_outbox/` 是各子 Agent 向 Manager 回传任务结果的目录。每个子 Agent 完成 inbox 中派发的任务后，在此目录下写入一份标准化的 Agent Report。

## 工作方式

### 1. 文件命名规则

每个子 Agent 的 outbox 报告命名格式为 `<agent_name>_report.md`：

```
agent_outbox/
├── planning_agent_report.md
├── command_registry_agent_report.md
├── cad_bridge_agent_report.md
├── intent_mapper_agent_report.md
├── safety_audit_agent_report.md
├── test_agent_report.md
├── docs_agent_report.md
└── README.md
```

### 2. 报告写入

子 Agent 完成任务后，将报告写入自己的 outbox 文件。报告格式必须遵循以下模板：

```markdown
# Agent Report
## Agent Name: <agent_name>
## Assigned Task: <task_id>
## Files Read
- /abs/path/to/file1.py
- /abs/path/to/file2.json
## Files Modified
- /abs/path/to/file3.py（修改说明）
- /abs/path/to/file4.md（新建）
## Work Completed
<已完成的工作清单，逐条描述>
## Tests Run
- pytest -q tests/test_xxx.py（XX passed）
## Test Result
<通过 / 失败 / 跳过，附关键统计>
## Safety Check
* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO
## Risks Found
<发现的风险及严重等级>
## Remaining Work
<剩余未完成的工作>
## Recommendation
<对 Manager 的建议>
```

### 3. 报告读取

Manager 定期轮询各 outbox 文件，检查任务完成状态。Manager 可通过 `git diff` 或直接读取对应文件来获取最新报告。

### 4. 注意事项

- 每次 outbox 写入应覆盖之前的同名报告文件（每个 Agent 维护当前阶段的最新报告）。
- 如果同一阶段需要追加内容，应更新现有报告并更新 `Work Completed`、`Remaining Work` 等字段。
- 子 Agent 不应读取或修改其他 Agent 的 outbox 文件。
- 报告必须包含完整的 Safety Check 表格，不可省略任何字段。
- Outbox 文件应使用 UTF-8 编码，换行符为 LF。
- 历史报告如需归档，Manager 可将旧报告移动到 `reports/archive/` 目录。

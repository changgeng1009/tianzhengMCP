# 阶段报告格式模板

## 使用说明

本模板供所有子 Agent 在完成阶段任务后撰写报告时使用。Manager 也可以使用此模板撰写阶段汇总报告。

报告文件命名规则：
- 子 Agent 报告：`agent_outbox/<agent_name>_report.md`
- 阶段汇总报告：`reports/phase_<phase_id>_summary.md`

---

# Agent Report

## Agent Name: <填写 Agent 名称>

## Assigned Task: <填写任务 ID>

## Files Read
<!-- 列出任务执行过程中读取的所有文件 -->
- `/abs/path/to/file1.py`
- `/abs/path/to/file2.json`
- `/abs/path/to/file3.md`

## Files Modified
<!-- 列出任务执行过程中修改/新建的所有文件 -->
- `/abs/path/to/file4.py`（修改：更新了 XXX 函数）
- `/abs/path/to/file5.md`（新建：XXX 文档）
- `/abs/path/to/file6.json`（新建：XXX 配置）

## Work Completed
<!-- 逐条描述已完成的工作 -->
1. 创建了 `AGENTS.md`，定义 Multi-Agent 协作规范。
2. 创建了 `agent_inbox/README.md`，说明任务派发机制。
3. 创建了 `agent_outbox/README.md`，说明结果回传机制。
4. 创建了 `docs/multi_agent_architecture.md`，绘制架构总览。
5. 创建了 `docs/report_template.md`，提供标准报告模板。
6. 为每个子 Agent 创建了 `agent_inbox/<agent_name>.md` 提示词模板。

## Tests Run
<!-- 列出执行的测试命令和结果 -->
```powershell
pytest -q tests/test_xxx.py
# 输出示例：42 passed in 2.35s
```

## Test Result
- 测试通过: XX
- 测试失败: XX
- 测试跳过: XX
- 覆盖率: XX%

<!-- 如果没有运行测试，说明原因 -->
<!-- 例如：本文档任务不涉及代码变更，无需运行单元测试。 -->

## Safety Check
<!-- 必须逐项填写，不允许留空 -->
* Connected to AutoCAD: NO
* Opened DWG: NO
* Opened source DWG: NO
* Used SendCommand: NO
* Executed Tianzheng command: NO
* Saved DWG: NO
* Modified source DWG: NO

<!-- 如果有任一项为 YES，必须在此详细说明原因、范围和风险控制措施 -->

## Risks Found
<!-- 列出发现的风险及严重等级（Critical / High / Medium / Low） -->
<!-- 如果没有风险，填写：无 -->
- 无

## Remaining Work
<!-- 列出本阶段或本任务剩余未完成的工作 -->
<!-- 如果没有剩余工作，填写：无 -->
- 无

## Recommendation
<!-- 对 Manager 的建议 -->
1. 建议在下一阶段启动前确认所有 Agent 的 inbox 模板已就绪。
2. 建议 parallel 启动 planning_agent 和 docs_agent，减少串行等待。

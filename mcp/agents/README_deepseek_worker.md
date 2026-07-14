# Controlled DeepSeek Worker

Phase AGENT-DS1 创建一个受控 DeepSeek Worker，用于后续承担非视觉、非真实 CAD 执行类任务，例如代码实现、schema 编写、测试编写、报告草稿和文件级静态分析。

## 安全边界

- 只接收精简 `task_pack`，不接收完整聊天历史。
- `DEEPSEEK_API_KEY` 只能由 `deepseek_client.py` 从环境变量读取。
- API key 不得写入代码、JSON、Markdown、日志、报告或 `task_pack`。
- Worker 不连接 AutoCAD，不打开 DWG，不保存 DWG，不调用 `SendCommand`。
- 默认拒绝 `hsxg`、`hzgx`、`gxlj`、`TSaveAs`、`tgbatplots`、`dcsz` 等危险动作。

## task_pack 字段

必须包含：

```json
{
  "phase": "...",
  "goal": "...",
  "allowed_files": [],
  "forbidden_files": [],
  "forbidden_actions": [],
  "safety_rules": [],
  "expected_outputs": [],
  "test_commands": [],
  "output_schema": {},
  "max_input_chars": 20000,
  "max_output_tokens": 4000
}
```

## 预算

`agent_budget.py` 默认限制：

- `max_input_chars=20000`
- `max_output_tokens=4000`
- `allowed_file_count=20`
- `allowed_context_sections=8`
- `reject_if_task_pack_too_large=true`

## 使用方式

默认使用 `dry_run=true` 验证流程，不会远程调用 DeepSeek：

```python
from mcp.agents.task_pack_builder import build_task_pack
from mcp.agents.deepseek_worker import run_deepseek_worker

task_pack = build_task_pack(
    phase="AGENT-DS1",
    goal="为指定文件编写静态分析草稿",
    allowed_files=["mcp/agents/example.py"],
    expected_outputs=["返回结构化报告草稿"],
)

result = run_deepseek_worker(task_pack, dry_run=True)
```

真实调用时必须先设置环境变量 `DEEPSEEK_API_KEY`。如果环境变量不存在，客户端会返回明确的 `BLOCKED` 结果，不会打印或记录 key。

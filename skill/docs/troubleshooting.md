# Troubleshooting

- Router 返回 blocked：检查 classification、geometry、working copy、required capabilities、backend availability 和 sandbox verification。
- TDbPipe 进入 manual：这是当前正确行为；不得改画为 AcDbLine。
- COM probe available 但执行被拒绝：probe 仅证明 adapter/pywin32 可用，不代表任务 capability 已授权。
- Stage 3 path 为 null：等待用户提供或在授权阶段安全确认，禁止按 AutoCAD 标签猜测。
- 文档显示 `*`：视为未保存修改，不得自动保存或关闭。
- 中文路径异常：所有 JSON/Markdown 使用 UTF-8，报告禁止出现连续问号形式的路径乱码。

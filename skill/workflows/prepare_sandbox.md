# Prepare Sandbox

1. 记录 source path/hash，只做文件系统读取。
2. 创建带时间戳的新 working copy，拒绝覆盖未知文件。
3. 记录 copy hash 和 source hash，不把 source 作为 backend open target。
4. 执行前再次确认 working copy 与 source 路径不同。
5. Stage 2 仅生成计划，不打开任何 DWG。

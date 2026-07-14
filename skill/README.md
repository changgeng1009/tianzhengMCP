# 天正给排水 CAD Skill

本目录封装“完整给排水 reference PDF/DWG 与未完成 target DWG 的识别、对齐、缺失检测、能力路由、安全副本修复和 QA”。入口规范见 `SKILL.md`。

当前给排水 domain 为 active；HVAC 为 deferred。Stage 1 fixture 仅用于 direct COM 回归，`real_sample_repair_completed=false`，`production_d1_allowed=false`。

代码边界位于 `mcp/backends/` 和 `mcp/domains/`。Stage 2 不连接 AutoCAD，不读取当前打开图纸，也不猜测 Stage 3 样本路径。

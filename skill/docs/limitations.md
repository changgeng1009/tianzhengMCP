# 限制

- 当前只开发天正给排水；HVAC 未实现。
- Stage 1 fixture 只证明 AcDbLine direct COM 和 persistence，不证明完整系统识别或真实修复。
- COM 的 TDb 创建、命令完成跟踪、document lock 和 transaction 均未验证。
- 多页 PDF、楼层/区域识别、复杂 alignment、网络一致性必须在 Stage 3 真实样本上验证。
- 当前打开的两个带 `*` 文档不是稳定 baseline；Stage 2 不访问它们。
- Stage 3 reference/target 完整路径和 hashes 尚未确认。
- `real_sample_repair_completed=false`，`production_d1_allowed=false`。

# 原始 Skill 兼容

`OriginalRedrawSkillAdapter` 将已审计的 `redraw_from_reference`、`analyze_reference`、`visual_review`、`compare_drawings` 映射到新 Manifest。它不复制全部代码、不修改原始 Skill、不自动执行脚本。

所有调用先进入新模式选择、文档守卫和审批门。危险、过时、不可复现或尚未测试的动作保持隔离；没有测试证据时不得标记 `PRESERVE_DIRECTLY`。

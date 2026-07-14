# 变更记录

## 0.1.1

- 将 `SEC-FINAL-019` 更新为 `CLOSED`，引用冻结基线 `baseline_id=20260714T193554+0800_s2_1`。
- 记录默认受守卫测试 `DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0` 和正式 verifier 入口。
- 未改变 runtime mode、capability support level、Legacy/Real backend 状态或 `production_d1_allowed=false`。

## 0.1.0

- 建立五种运行模式、产品/后端适配器和 fail-closed 选择器。
- 建立 Manifest、审批、Checkpoint、能力表和离线 CLI。
- 保留原始重绘 Skill 的只读兼容映射，不修改原目录。
- NextGenMcpMockBackend 为 `IMPLEMENTED_BASELINE`；真实后端保持 `NOT_IMPLEMENTED`。
- 初始发布时 `SEC-FINAL-019` 为 `OPEN`；已在 0.1.1 关闭。

# 变更记录

## 0.1.3

- 校正当前安全基线为 `CAD-SAFE-20260714T220937+0800`，权威最终 SHA256 为 `87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`。
- 保留 `13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9`，但明确其仅为 freeze-time provenance，不得作为当前 S2 预检或验收 SHA。
- 记录 S2 配置驱动 CLI 与安全边界：配置不能授予或继承审批，不能提升 Backend、真实 CAD、L3/L4 或生产权限。
- 未改变 runtime mode、capability support level、Legacy/Real backend 状态、`production_allowed=false` 或 `production_d1_allowed=false`。

## 0.1.2

- 因 `intentional AGENTS.md update` 生成当前安全基线目录 `20260714T220937+0800`，父基线保留为 `20260714T193554+0800_s2_1`。当时记录的 `13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9` 为 freeze-time provenance；当前权威 SHA 见 0.1.3。
- 未改变 runtime mode、capability support level、Legacy/Real backend 状态、`production_allowed=false` 或 `production_d1_allowed=false`。

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

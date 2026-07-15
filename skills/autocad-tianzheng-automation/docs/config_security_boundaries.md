# 配置安全边界

## 不可由配置提升的能力

- `production_allowed` 与 `production_d1_allowed`
- `real_cad_access_allowed`
- Backend availability、support level、execution capability
- L3/L4 审批有效性
- source document 写权限
- Sandbox、fail-closed、visual/engineering review 要求

安全合并实现见 `config/merge.py:69`。统一错误模型位于 `runtime/errors.py:43` 起，错误可序列化为 `to_error_payload()`。

## Approval

Manifest 只能声明需要的等级、引用是否存在、single-use 和 expiry。它不能创建有效批准，也不能把 `approval_reference_present` 等同于 `approval_verified`。本阶段没有真实 approval authority；L3/L4 必须 blocked。

## Document Identity

Manifest 自述 filename/hash/size/product 只属于 `DECLARED`。路径解析不读取文件，Plan builder 当前把文档 `identity_verified=false`。真实运行必须由独立安全后端重新验证；当前不得输出真实 CAD `VERIFIED`。

## Backend 与 Simulation

- `offline`：只做离线规划、验证和报告。
- `nextgen_mock`：Mock-only，不代表真实 CAD。
- `original_redraw_adapter`：仅离线映射，Real COM disabled。
- Legacy contract 不可选。
- 所有 Real backend 和 AutoCAD .NET plugin 未实现。
- `simulate_plan()` 明确返回 `real_execution=false`，且不能自动替代计划中的 Backend。

## 零访问规则

配置测试必须继续使用现有文件访问守卫和六类 marker 排除。任何成功读取、写入、解析、扫描或哈希真实 DWG/DXF，或启动 CAD/COM/天正/Real backend，都应立即停止 S2。

## 当前证据级别

WP1 与 WP2 只有 Owned Modules 轻量离线自检；WP3 与 CLI、模板、Workflow 仍待完成。本文不替代 test_agent 的默认安全回归或 SEC-FINAL-019 的冻结证据。


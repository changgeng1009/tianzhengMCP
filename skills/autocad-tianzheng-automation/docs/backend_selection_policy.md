# Backend 选择策略

## 权威 Registry

Backend 真值来自 `BackendRegistry`，不是 Manifest；实现见 `adapters/registry.py:300`，选择器见 `adapters/registry.py:387`。

| Canonical ID | Availability | 用途 |
|---|---|---|
| `offline` | `AVAILABLE` | 离线规划、验证、报告 |
| `original_redraw_adapter` | `AVAILABLE_FOR_OFFLINE_PLANNING` | 只映射原始工作流；Real COM disabled |
| `nextgen_mock` | `AVAILABLE_FOR_MOCK` | Mock-only；不是 Real CAD |
| `legacy_contract_disabled` | `DISABLED_CONTRACT_ONLY` | 仅合同存在，不可选择执行 |
| `legacy_com` | `NOT_AVAILABLE` | 未实现/禁用 |
| `nextgen_real` | `NOT_AVAILABLE` | 未实现 |
| `autocad_dotnet_plugin` | `NOT_AVAILABLE` | 未实现 |
| `tianzheng_water_real` | `NOT_AVAILABLE` | 未实现 |
| `tianzheng_hvac_real` | `NOT_AVAILABLE` | 未实现 |

旧连字符 ID 可作为输入 alias，输出统一为下划线 canonical ID。

## 选择规则

- `require_real_execution=true` 返回 `BACKEND_NOT_AVAILABLE`。
- `nextgen_mock` 仅在 `mock_allowed=true` 时可选。
- 不可用 backend 返回可用替代项，但不自动执行 fallback。
- Manifest 出现 `available`、`support_level`、`execution_allowed`、`real_execution_supported` 等能力提升字段时返回 `CONFIG_BACKEND_OVERRIDE_FORBIDDEN`。
- 所有当前 backend 的 `real_execution_supported=false`。

WP2 的离线自检已覆盖 9 个合同和 6 个 Disabled/Real 阻断，但正式测试尚待 test_agent。


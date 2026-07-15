# Runtime 与 Product 路由

## Runtime modes

- `plain_autocad`
- `tianzheng_water`
- `tianzheng_hvac`
- `auto_detect`
- `offline_analysis`

枚举定义见 `runtime/contracts.py:9`。`RuntimeRouter` 源码位于 `runtime/routing.py:80`，当前状态为“源码存在、WP3 最终验证待回填”。

## 路由依据

计划优先级：显式 run override → canonical Manifest →显式 context →离线 product/document metadata。`auto_detect` 只使用显式字段和离线元数据，不读取文件内容，不根据文件名中的“天正/暖通/给排水”猜测产品。

冲突返回：

- `RUNTIME_MODE_CONFLICT`
- `PRODUCT_MODE_CONFLICT`
- `PRODUCT_CAPABILITY_UNAVAILABLE`

如果证据不足且 `offline_only=true`，当前源码会选择 `offline_analysis`；该行为仍需 WP3/test_agent 确认，不应在验收前视为稳定 CLI 行为。

## Product Adapter 状态

| Adapter | 当前静态合同 | Real 状态 |
|---|---|---|
| `GenericAutoCadAdapter` | `OFFLINE_PLANNING_IMPLEMENTED` | `NOT_IMPLEMENTED` |
| `TianzhengWaterAdapter` | `OFFLINE_PLANNING_IMPLEMENTED` | `NOT_IMPLEMENTED`；native topology 与 engineering semantics 未验证 |
| `TianzhengHvacAdapter` | read=`PARTIALLY_IMPLEMENTED`，write=`INTERFACE_ONLY` | `NOT_IMPLEMENTED` |
| `OfflineAnalysisAdapter` | `IMPLEMENTED` 的离线分析合同 | 不提供 Real |

Registry 实现见 `adapters/registry.py:139` 和 `adapters/registry.py:210`。`auto_detect` 必须先由 RuntimeRouter 唯一裁决，不能直接交给 Adapter Registry。

## Trace

`RuntimeSelectionResult` 和 `RoutingTraceEntry` 位于 `runtime/contracts.py:49`。路由输出应包含来源、字段、值和选择原因。任何 silent fallback 都不符合本阶段边界。


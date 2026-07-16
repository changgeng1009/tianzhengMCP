# 运行模式与执行运行时

为兼容 S0–S2，`runtime_mode` 仍可表达用户的 CAD/专业意图；S3 不再将它当作执行环境。路由完成后必须产出两个独立字段：`product.profile` 与 `runtime.execution_runtime`。

| 兼容 `runtime_mode` | 映射的 ProductProfile | 含义 |
| --- | --- | --- |
| `plain_autocad` | `generic_autocad` | 仅通用 AutoCAD 意图；禁止天正规则。 |
| `tianzheng_water` | `tianzheng_water` | 给排水专业意图；禁止暖通规则。 |
| `tianzheng_hvac` | `tianzheng_hvac` | 暖通专业意图；当前仅接口/离线计划，禁止给排水规则。 |
| `offline_analysis` | `offline_analysis` | JSON、Schema、代码、报告、图片/PDF 计划与 Mock；不读取 DWG。 |
| `auto_detect` | 必须由证据唯一解析 | 未解析前不是 ProductProfile；证据冲突则停止。 |

`execution_runtime` 的允许枚举为：

- `offline`：`IMPLEMENTED` 的纯离线规划、验证、报告入口；不读取真实 CAD。
- `mock`：仅用于受控 Mock 模拟。`nextgen_mock` 是 `IMPLEMENTED_BASELINE`，不代表真实产品或 CAD 进程。
- `com`：未来运行时，当前 `NOT_AVAILABLE`；选择即 fail-closed。
- `objectarx`：未来运行时，当前 `NOT_AVAILABLE`；选择即 fail-closed。

产品实例冲突返回 `PRODUCT_INSTANCE_CONFLICT`；产品与兼容运行模式冲突返回 `PRODUCT_MODE_CONFLICT`；产品/运行时组合不可用返回 `PRODUCT_RUNTIME_NOT_AVAILABLE`；文档身份不唯一返回 `DOCUMENT_IDENTITY_AMBIGUOUS`。`offline`/`mock` 的可选择性不授予真实执行，也不提升审批等级。

# 运行模式

- `plain_autocad`：仅通用 AutoCAD；禁止天正调用。
- `tianzheng_water`：仅确认加载给排水后启用；禁止暖通调用。
- `tianzheng_hvac`：当前检测/扫描/对象/命令均为接口或只读规划；禁止给排水调用。
- `auto_detect`：按用户、Manifest、上下文、安全检测顺序；无法唯一确认即 `RUNTIME_MODE_CONFLICT`。
- `offline_analysis`：JSON、Schema、代码、报告、图片/PDF 计划与 Mock；不读取 DWG。

产品实例冲突返回 `PRODUCT_INSTANCE_CONFLICT`；文档身份不唯一返回 `DOCUMENT_IDENTITY_AMBIGUOUS`。

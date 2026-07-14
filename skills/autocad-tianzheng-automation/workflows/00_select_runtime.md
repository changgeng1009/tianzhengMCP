# 00 选择运行模式

- 适用模式：全部。
- 输入：用户要求、Manifest、明确项目上下文、安全只读检测结果。
- 前置条件：不得通过文件名猜测产品。
- 允许操作：读取 JSON/配置，比较证据。
- 禁止操作：启动/切换产品、选择任意 ActiveDocument。
- 输出：唯一模式、产品、证据来源。
- 安全门：冲突即 fail-closed。
- 停止条件：`RUNTIME_MODE_CONFLICT`、`PRODUCT_INSTANCE_CONFLICT`。
- 人工复核点：证据不足时询问用户。

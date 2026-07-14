# 产品适配器模型

`GenericAutoCadAdapter` 管理普通对象族；`TianzhengWaterAdapter` 管理给排水系统与 TDb/TCH 族；`TianzhengHvacAdapter` 独立管理房间、风管、水管、设备、风口和标注接口。

暖通不得套用给排水名称或规则。当前 `tianzheng_hvac_write=INTERFACE_ONLY`。所有对象声明必须区分 `IMPLEMENTED`、`PARTIALLY_IMPLEMENTED`、`INTERFACE_ONLY`、`NOT_IMPLEMENTED`、`UNSAFE`。
